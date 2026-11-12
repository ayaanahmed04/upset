"""Multi-skill fighter model (research): separate, changing skills for every fighter, with uncertainty.

Each fighter carries an offense and a defense skill for nine things that happen in a fight:

    str     strikes landed at distance        clinch  strikes landed in the clinch
    gnd     strikes landed on the ground      kd      knockdowns
    td      takedowns landed                  ctrl    control time
    sub     submission attempts               ko      winning by KO/TKO (defense = durability)
    subwin  winning by submission

A fight is read as counts over fight minutes. For A against B the expected rate is

    league rate * exp(A's offense - B's defense)

so every number is opponent-adjusted: landing 5 takedowns on an elite defender moves the offense
skill more than landing 5 on a weak one. Skills are tracked with an approximate Kalman filter
(mean and variance per skill), drift between fights, and start at the league average with a wide
variance. Over-dispersion per stat and the starting variances are estimated from fights through
2018 only. League rates are a decayed running average of earlier fights only.

The test is the same as every other UPSET experiment: fit on 2010-2018, score once on 2019 onward,
on the same 3,177-fight record set. Matchups use skill against skill, plus pre-declared interaction
terms where style effects would show up if they exist.
"""

import argparse
import json
import math
import random
import sqlite3
from collections import defaultdict
from contextlib import closing
from datetime import date
from itertools import groupby
from pathlib import Path

import numpy as np

TRAIN = ("2010-01-01", "2018-12-31")
INNER = "2016-01-01"          # inner validation inside the training years
TEST_FROM = "2019-01-01"
EM_FROM = "2005-01-01"
STATS = ["str", "clinch", "gnd", "kd", "td", "ctrl", "sub", "ko", "subwin"]
K = len(STATS)
IDX = {name: i for i, name in enumerate(STATS)}
PRIOR_RATE = np.array([1.5, .3, .4, .02, .1, 1.2, .06, .03, .02])   # per minute, only to start the league average
HALF_LIFE_DAYS = 1095.0
ELO_K = 40.0
LABELS = {"str": "Striking at range", "clinch": "Clinch striking", "gnd": "Ground striking", "kd": "Knockdown power",
          "td": "Takedowns", "ctrl": "Control", "sub": "Submission threat", "ko": "KO finishing", "subwin": "Submission finishing"}
DEF_LABELS = {"str": "Striking defense", "kd": "Chin (knockdowns avoided)", "td": "Takedown defense",
              "ctrl": "Staying out of control", "ko": "Durability (not being stopped)", "subwin": "Submission defense"}


def load(database):
    with closing(sqlite3.connect(database)) as db:
        names = dict(db.execute("SELECT id,name FROM fighters"))
        stats = defaultdict(dict)
        for fid, uid, payload in db.execute("SELECT fight_id,fighter_id,payload FROM stats"):
            stats[fid][uid] = json.loads(payload)
        fights = []
        for fid, day, payload in db.execute("SELECT id,event_date,payload FROM fights ORDER BY event_date,id"):
            p = json.loads(payload)
            result = p.get("reviewed_result") or p
            ids = [p.get("upset_fighter_1_id"), p.get("upset_fighter_2_id")]
            pair = [p["fighter_1_name"], p["fighter_2_name"]]
            winner = result.get("winner_name")
            win = None if winner is None else (0 if winner == pair[0] else 1 if winner == pair[1] else None)
            method = result.get("result_method") or ""
            kind = "ko" if method.startswith(("KO", "TKO")) else "sub" if method.startswith("Submission") else "other"
            rows = stats.get(fid, {})
            any_row = next(iter(rows.values()), {})
            fmt = any_row.get("source_time_format") or ""
            long_fight = fmt.startswith("5 Rnd") or (any_row.get("fight_duration_seconds") or 0) > 15 * 60 + 5
            wclass = " ".join(w for w in (p.get("weight_class") or "").replace("UFC", "").split()
                              if w.lower() not in ("bout", "title", "interim", "tournament")).lower() or "unknown"
            fights.append({"id": fid, "day": day, "ids": ids, "win": win, "kind": kind, "rows": rows,
                           "minutes": 25.0 if long_fight else 15.0, "wclass": wclass})
    return fights, names


def counts(row, won, kind, decided):
    """Observed counts for one fighter in one fight; NaN where the stat was not recorded."""
    get = lambda key: float("nan") if row.get(key) is None else float(row[key])
    ctrl = row.get("control_seconds")
    return np.array([get("distance_landed"), get("clinch_landed"), get("ground_landed"), get("knockdowns"),
                     get("takedowns_landed"), float("nan") if ctrl is None else ctrl / 10.0, get("submission_attempts"),
                     (1.0 if won and kind == "ko" else 0.0) if decided else float("nan"),
                     (1.0 if won and kind == "sub" else 0.0) if decided else float("nan")])


class Fighter:
    __slots__ = ("o", "d", "vo", "vd", "last", "fights", "elo", "tot", "minutes")

    def __init__(self, v0):
        self.o, self.d = np.zeros(K), np.zeros(K)
        self.vo, self.vd = v0.copy(), v0.copy()
        self.last, self.fights, self.elo = None, 0, 1500.0
        self.tot, self.minutes = np.zeros(K), np.zeros(K)


def run(fights, phi, v0, q, collect_em=False):
    """One pass through history. Returns pre-fight records, per-stat diagnostics and the final states."""
    state = {}
    league_c, league_m = PRIOR_RATE * 200.0, np.full(K, 200.0)
    last_day = None
    records, em_num, em_den = {}, np.zeros(K), np.zeros(K)
    stat_eval = {"model": np.zeros(K), "base": np.zeros(K), "n": np.zeros(K), "z2": np.zeros(K)}

    def get(uid):
        if uid not in state:
            state[uid] = Fighter(v0)
        return state[uid]

    def variances(f, day):
        if f.last is None:
            return f.vo, f.vd
        years = (date.fromisoformat(day) - date.fromisoformat(f.last)).days / 365.25
        return np.minimum(v0, f.vo + q * years), np.minimum(v0, f.vd + q * years)

    for day, batch in groupby(fights, key=lambda f: f["day"]):
        batch = list(batch)
        if last_day is not None:
            decay = .5 ** ((date.fromisoformat(day) - date.fromisoformat(last_day)).days / HALF_LIFE_DAYS)
            league_c, league_m = league_c * decay, league_m * decay
        last_day = day
        mu = np.log(league_c / league_m)
        pre = {}
        for fight in batch:
            a, b = fight["ids"]
            if not a or not b:
                continue
            fa, fb = get(a), get(b)
            voa, vda = variances(fa, day)
            vob, vdb = variances(fb, day)
            pre[fight["id"]] = (fa.o.copy(), fa.d.copy(), voa, vda, fb.o.copy(), fb.d.copy(), vob, vdb,
                                fa.elo, fb.elo, fa.fights, fb.fights, fa.tot.copy(), fa.minutes.copy(),
                                fb.tot.copy(), fb.minutes.copy())
            records[fight["id"]] = {"day": day, "ids": (a, b), "a2b": fa.o - fb.d, "b2a": fb.o - fa.d,
                                    "elo": (fa.elo - fb.elo) / 400 * math.log(10), "n": (fa.fights, fb.fights),
                                    "mu": mu.copy()}
        add_c, add_m = np.zeros(K), np.zeros(K)
        for fight in batch:
            if fight["id"] not in pre:
                continue
            a, b = fight["ids"]
            fa, fb = get(a), get(b)
            (oa, da, voa, vda, ob, db, vob, vdb, ea, eb, _, _, ta, ma, tb, mb) = pre[fight["id"]]
            decided = fight["win"] is not None
            if decided:
                expected = 1 / (1 + 10 ** ((eb - ea) / 400))
                score = 1.0 if fight["win"] == 0 else 0.0
                fa.elo += ELO_K * (score - expected)
                fb.elo -= ELO_K * (score - expected)
            ra, rb = fight["rows"].get(a), fight["rows"].get(b)
            seconds = (ra or {}).get("fight_duration_seconds") or 0
            if not ra or not rb or seconds <= 0:
                continue
            t = seconds / 60.0
            ya = counts(ra, fight["win"] == 0, fight["kind"], decided)
            yb = counts(rb, fight["win"] == 1, fight["kind"], decided)
            for (f_off, f_def, o, vo, d, vd, y, own_tot, own_min) in (
                    (fa, fb, oa, voa, db, vdb, ya, ta, ma), (fb, fa, ob, vob, da, vda, yb, tb, mb)):
                ok = ~np.isnan(y)
                yv = np.where(ok, y, 0.0)
                e = np.exp(np.clip(mu + o - d, -12, 6)) * t
                s = vo + vd
                denom = s * e + phi
                delta = np.where(ok, (yv - e) / denom, 0.0)
                step_o, step_d = vo * delta, -vd * delta
                total = np.abs(step_o - step_d)
                scale = np.where(total > 1.0, 1.0 / np.maximum(total, 1e-9), 1.0)   # cap one fight's move
                shrink = np.where(ok, e / denom, 0.0)
                f_off.o = np.where(ok, f_off.o + scale * step_o, f_off.o)
                f_def.d = np.where(ok, f_def.d + scale * step_d, f_def.d)
                f_off.vo = np.where(ok, vo - vo * vo * shrink, vo)
                f_def.vd = np.where(ok, vd - vd * vd * shrink, vd)
                if collect_em and EM_FROM <= day <= TRAIN[1]:
                    em_num += np.where(ok, ((yv - e) ** 2 - e * e * s) / np.maximum(e, 1e-9), 0.0)
                    em_den += ok
                if day >= TEST_FROM:
                    base = (own_tot + np.exp(mu) * 30.0) / (own_min + 30.0) * t   # shrunk career rate, no opponent
                    dev = lambda pred: 2 * (np.where(yv > 0, yv * np.log(np.maximum(yv, 1e-12) / pred), 0.0) - (yv - pred))
                    stat_eval["model"] += np.where(ok, dev(e), 0.0)
                    stat_eval["base"] += np.where(ok, dev(np.maximum(base, 1e-9)), 0.0)
                    stat_eval["z2"] += np.where(ok, (yv - e) ** 2 / (phi * e + e * e * s), 0.0)
                    stat_eval["n"] += ok
                f_off.tot = f_off.tot + yv
                f_off.minutes = f_off.minutes + np.where(ok, t, 0.0)
                add_c += yv
                add_m += np.where(ok, t, 0.0)
            for f in (fa, fb):
                f.last, f.fights = day, f.fights + 1
        league_c, league_m = league_c + add_c, league_m + add_m
    return records, {"em_num": em_num, "em_den": em_den, "stat_eval": stat_eval}, state


def empirical_bayes(fights):
    """Dispersion and starting variances from fights through 2018 only."""
    cut = [f for f in fights if f["day"] <= TRAIN[1]]
    phi, v0 = np.full(K, 3.0), np.full(K, .25)
    for _ in range(4):
        _, diag, state = run(cut, phi, v0, .01, collect_em=True)
        phi = np.clip(diag["em_num"] / np.maximum(diag["em_den"], 1), 1.0, 60.0)
        seasoned = [f for f in state.values() if f.fights >= 6]
        spread = np.array([np.var([f.o[k] for f in seasoned]) + np.mean([f.vo[k] for f in seasoned]) +
                           np.var([f.d[k] for f in seasoned]) + np.mean([f.vd[k] for f in seasoned]) for k in range(K)]) / 2
        v0 = np.clip(spread, .02, 1.0)
    return phi, v0


# ---------------------------------------------------------------- matchup features and fitting

INTERACTIONS = [("td", "str"), ("ctrl", "str"), ("kd", "td"), ("str", "kd"), ("sub", "td")]


def feature_blocks(rec):
    a2b, b2a = rec["a2b"], rec["b2a"]
    skills = a2b - b2a
    inter = np.array([a2b[IDX[x]] * b2a[IDX[y]] - b2a[IDX[x]] * a2b[IDX[y]] for x, y in INTERACTIONS])
    base_share = min(.45, math.exp(rec["mu"][IDX["ctrl"]]) / 6.0)          # league control share of fight time
    share_a = min(.8, base_share * math.exp(a2b[IDX["ctrl"]]))
    share_b = min(.8, base_share * math.exp(b2a[IDX["ctrl"]]))
    standing = max(.05, 1 - share_a - share_b)
    usual = 1 - 2 * base_share
    mech = np.array([(standing - usual) * skills[IDX["str"]], (standing - usual) * skills[IDX["kd"]], share_a - share_b])
    return skills, inter, mech


def design(rows, spec):
    cols = []
    for r in rows:
        x = []
        if "p52" in spec:
            x.append(r["l52"])
        if "p51" in spec:
            x.append(r["l51"])
        if "elo" in spec:
            x.append(r["elo"])
        if "sim" in spec:
            x.append(r["lsim"])
        if "skills" in spec:
            x.extend(r["skills"])
        if "inter" in spec:
            x.extend(r["inter"])
        if "mech" in spec:
            x.extend(r["mech"])
        cols.append(x)
    return np.array(cols, dtype=float)


def fit(X, y, lam, free):
    """Ridge logistic regression without intercept on corner-symmetric data. `free` columns are not penalised."""
    Xs, ys = np.vstack([X, -X]), np.concatenate([y, 1 - y])
    pen = np.array([0.0 if i < free else lam for i in range(X.shape[1])])
    w = np.zeros(X.shape[1])
    if free:
        w[0] = 1.0
    for _ in range(60):
        p = 1 / (1 + np.exp(-np.clip(Xs @ w, -30, 30)))
        g = Xs.T @ (p - ys) + pen * w
        h = (Xs * (p * (1 - p))[:, None]).T @ Xs + np.diag(pen + 1e-9)
        step = np.linalg.solve(h, g)
        w -= step
        if np.abs(step).max() < 1e-9:
            break
    return w


def predict(X, w):
    return 1 / (1 + np.exp(-np.clip(X @ w, -30, 30)))


def losses(p, y):
    return -np.log(np.clip(np.where(y == 1, p, 1 - p), 1e-9, 1))


def summary(p, y):
    acc = np.where(p == .5, .5, ((p > .5) == (y == 1)).astype(float)).mean()
    return {"bouts": int(len(y)), "log_loss": round(float(losses(p, y).mean()), 5), "accuracy": round(float(acc), 4)}


def bootstrap(days, base, cand, draws=500, seed=5):
    by_day = defaultdict(list)
    for d, x in zip(days, cand - base):
        by_day[d].append(x)
    keys, rng, means = list(by_day), random.Random(seed), []
    for _ in range(draws):
        picked = [x for k in (rng.choice(keys) for _ in keys) for x in by_day[k]]
        means.append(sum(picked) / len(picked))
    means.sort()
    return [round(means[int(.025 * draws)], 4), round(means[int(.975 * draws)], 4)]


def assemble(records, forecasts, adjusted, by_id):
    rows = []
    for fid, item in forecasts.items():
        rec = records.get(fid)
        if rec is None or item["y"] is None or item["event_date"] < TRAIN[0] or fid not in adjusted:
            continue
        flip = rec["ids"][0] != item["fighter_ids"][0]
        if flip:
            rec = {**rec, "a2b": rec["b2a"], "b2a": rec["a2b"], "elo": -rec["elo"], "n": rec["n"][::-1]}
        skills, inter, mech = feature_blocks(rec)
        logit = lambda p: math.log(min(max(p, 1e-6), 1 - 1e-6) / (1 - min(max(p, 1e-6), 1 - 1e-6)))
        fight = by_id[fid]
        rate_a, rate_b = np.exp(rec["mu"] + rec["a2b"]), np.exp(rec["mu"] + rec["b2a"])
        rows.append({"haz": (rate_a[IDX["ko"]], rate_a[IDX["subwin"]], rate_b[IDX["ko"]], rate_b[IDX["subwin"]]),
                     "dec_x": (rate_a - rate_b)[:7], "minutes": fight["minutes"], "kind": fight["kind"], "wclass": fight["wclass"],
                     "p52": adjusted[fid],
                     "fid": fid, "day": item["event_date"], "y": item["y"], "l52": logit(adjusted[fid]),
                     "l51": logit(item["forecast"]), "elo": rec["elo"], "skills": skills, "inter": inter, "mech": mech,
                     "eligible": min(item["prior_decisive_bouts"]) >= 1, "n": rec["n"]})
    rows.sort(key=lambda r: (r["day"], r["fid"]))
    return rows


CLASSES = ("ko", "sub", "other")   # how the winner won; "other" is a decision (plus rare DQs)


def simulate(rows):
    """Fight simulation from the skills: finish hazards each way, then a decision model.

    Fitted on 2010-2018 only: one scale for how often fights end early, and the weights that turn
    expected per-minute edges (strikes, knockdowns, takedowns, control...) into decision wins.
    Adds to every row: the simulated win chance (lsim) and six outcome chances (winner x method).
    """
    train = [r for r in rows if TRAIN[0] <= r["day"] <= TRAIN[1]]

    def finish_loss(kappa):
        total = 0.0
        for r in train:
            p = 1 - math.exp(-kappa * sum(r["haz"]) * r["minutes"])
            p = min(max(p, 1e-6), 1 - 1e-6)
            total -= math.log(p if r["kind"] != "other" else 1 - p)
        return total / len(train)

    kappa = min((k / 20 for k in range(4, 81)), key=finish_loss)
    # Calibrate the finish chance with the division's 2010-2018 finish rate (heavier divisions finish more).
    overall = sum(r["kind"] != "other" for r in train) / len(train)
    groups = defaultdict(list)
    for r in train:
        groups[r["wclass"]].append(r["kind"] != "other")
    base_finish = lambda wclass: (sum(groups[wclass]) / len(groups[wclass])) if len(groups.get(wclass, ())) >= 100 else overall
    lg = lambda v: math.log(min(max(v, 1e-6), 1 - 1e-6) / (1 - min(max(v, 1e-6), 1 - 1e-6)))
    raw = lambda r: 1 - math.exp(-kappa * sum(r["haz"]) * r["minutes"])
    F = np.array([[lg(raw(r)), lg(base_finish(r["wclass"])), 1.0] for r in train])
    f_y = np.array([r["kind"] != "other" for r in train], dtype=float)
    cal = np.array([1.0, 0.0, 0.0])
    for _ in range(40):
        pr = 1 / (1 + np.exp(-F @ cal))
        step = np.linalg.solve((F * (pr * (1 - pr))[:, None]).T @ F + 1e-9 * np.eye(3), F.T @ (pr - f_y))
        cal -= step
    decisions = [r for r in train if r["kind"] == "other"]
    X = np.array([r["dec_x"] for r in decisions])
    y = np.array([r["y"] for r in decisions], dtype=float)
    scale = np.sqrt((X ** 2).mean(axis=0)) + 1e-12
    inner_t = [i for i, r in enumerate(decisions) if r["day"] < INNER]
    inner_v = [i for i, r in enumerate(decisions) if r["day"] >= INNER]
    lam = min(LAMBDAS, key=lambda l: float(losses(predict(X[inner_v] / scale, fit(X[inner_t] / scale, y[inner_t], l, 0)), y[inner_v]).mean()))
    w = fit(X / scale, y, lam, 0)
    for r in rows:
        ka, sa, kb, sb = r["haz"]
        total = ka + sa + kb + sb
        p_fin = 1 / (1 + math.exp(-(cal[0] * lg(raw(r)) + cal[1] * lg(base_finish(r["wclass"])) + cal[2])))
        p_dec_a = float(predict((np.array(r["dec_x"]) / scale)[None, :], w)[0])
        six = {("a", "ko"): p_fin * ka / total, ("a", "sub"): p_fin * sa / total, ("a", "other"): (1 - p_fin) * p_dec_a,
               ("b", "ko"): p_fin * kb / total, ("b", "sub"): p_fin * sb / total, ("b", "other"): (1 - p_fin) * (1 - p_dec_a)}
        p_a = min(max(six[("a", "ko")] + six[("a", "sub")] + six[("a", "other")], 1e-6), 1 - 1e-6)
        r["six"], r["lsim"] = six, math.log(p_a / (1 - p_a))
    return {"finish_scale": kappa, "finish_calibration": [round(float(v), 3) for v in cal], "decision_ridge": lam,
            "decision_weights_standardised": dict(zip(STATS[:7], [round(float(v), 3) for v in w]))}


def method_scores(rows):
    """Winner-and-method predictions on 2019+: simulation vs division base rates."""
    train = [r for r in rows if TRAIN[0] <= r["day"] <= TRAIN[1]]
    test = [r for r in rows if r["day"] >= TEST_FROM and r["eligible"]]
    overall, by_class = defaultdict(int), defaultdict(lambda: defaultdict(int))
    for r in train:
        overall[r["kind"]] += 1
        by_class[r["wclass"]][r["kind"]] += 1

    def base(wclass):
        c = by_class[wclass] if sum(by_class[wclass].values()) >= 100 else overall
        n = sum(c.values())
        return {k: c[k] / n for k in CLASSES}

    out = {name: {"six": 0.0, "method": 0.0, "hit": 0} for name in
           ("5.2 winner x division base rates", "simulation alone", "5.2 winner x simulation method")}
    finish = {"predicted": [], "actual": []}
    for r in test:
        won, lost = ("a", "b") if r["y"] == 1 else ("b", "a")
        b, six, p = base(r["wclass"]), r["six"], r["p52"]
        sim_a = sum(six[("a", k)] for k in CLASSES)
        cond = {side: {k: six[(side, k)] / max(sum(six[(side, j)] for j in CLASSES), 1e-9) for k in CLASSES} for side in "ab"}
        tables = {
            "5.2 winner x division base rates": {("a", k): p * b[k] for k in CLASSES} | {("b", k): (1 - p) * b[k] for k in CLASSES},
            "simulation alone": six,
            "5.2 winner x simulation method": {("a", k): p * cond["a"][k] for k in CLASSES} | {("b", k): (1 - p) * cond["b"][k] for k in CLASSES}}
        for name, t in tables.items():
            out[name]["six"] -= math.log(max(t[(won, r["kind"])], 1e-9))
            m = {k: t[("a", k)] + t[("b", k)] for k in CLASSES}
            out[name]["method"] -= math.log(max(m[r["kind"]], 1e-9))
            out[name]["hit"] += max(m, key=m.get) == r["kind"]
        finish["predicted"].append(six[("a", "ko")] + six[("a", "sub")] + six[("b", "ko")] + six[("b", "sub")])
        finish["actual"].append(r["kind"] != "other")
    n = len(test)
    order = sorted(range(n), key=lambda i: finish["predicted"][i])
    thirds = [order[:n // 3], order[n // 3:2 * n // 3], order[2 * n // 3:]]
    return {"bouts": n,
            "models": {name: {"winner_and_method_log_loss": round(v["six"] / n, 4), "method_only_log_loss": round(v["method"] / n, 4),
                              "method_called_right": round(v["hit"] / n, 4)} for name, v in out.items()},
            "finish_chance_check": [{"predicted_finish": round(sum(finish["predicted"][i] for i in g) / len(g), 3),
                                     "actual_finish": round(sum(finish["actual"][i] for i in g) / len(g), 3), "bouts": len(g)}
                                    for g in thirds]}


MODELS = {
    "v5.1 forecast": (["p51"], 1),
    "forecast 5.2 (live)": (["p52"], 1),
    "multi-skill alone (Elo + 9 skills)": (["elo", "skills"], 0),
    "multi-skill alone + style interactions": (["elo", "skills", "inter", "mech"], 0),
    "fight simulation alone": (["sim"], 1),
    "5.2 + fight simulation": (["p52", "sim"], 1),
    "5.2 + 9 skills": (["p52", "skills"], 1),
    "5.2 + style interactions only": (["p52", "inter", "mech"], 1),
    "5.2 + skills + style interactions": (["p52", "skills", "inter", "mech"], 1),
}
LAMBDAS = (0.0, 3.0, 10.0, 30.0, 100.0, 300.0, 1000.0)


def choose_lambda(rows, spec, free):
    inner_train = [r for r in rows if TRAIN[0] <= r["day"] < INNER and r["eligible"]]
    inner_val = [r for r in rows if INNER <= r["day"] <= TRAIN[1] and r["eligible"]]
    Xt, yt = design(inner_train, spec), np.array([r["y"] for r in inner_train], dtype=float)
    Xv, yv = design(inner_val, spec), np.array([r["y"] for r in inner_val], dtype=float)
    scale = np.sqrt((Xt ** 2).mean(axis=0)) + 1e-12
    best = None
    for lam in LAMBDAS if Xt.shape[1] > free + 0 and Xt.shape[1] > 1 else (0.0,):
        w = fit(Xt / scale, yt, lam, free)
        loss = float(losses(predict(Xv / scale, w), yv).mean())
        if best is None or loss < best[1] - 1e-9:
            best = (lam, loss)
    return best


def evaluate(rows):
    train = [r for r in rows if TRAIN[0] <= r["day"] <= TRAIN[1] and r["eligible"]]
    test = [r for r in rows if r["day"] >= TEST_FROM and r["eligible"]]
    yt, ys = np.array([r["y"] for r in train], dtype=float), np.array([r["y"] for r in test], dtype=float)
    days = [r["day"] for r in test]
    seasoned = np.array([min(r["n"]) >= 5 for r in test])
    out, probs = {}, {}
    for name, (spec, free) in MODELS.items():
        lam, inner_loss = choose_lambda(rows, spec, free)
        Xt, Xs = design(train, spec), design(test, spec)
        scale = np.sqrt((Xt ** 2).mean(axis=0)) + 1e-12
        w = fit(Xt / scale, yt, lam, free)
        p = predict(Xs / scale, w)
        probs[name] = p
        out[name] = {"ridge": lam, "inner_validation_log_loss": round(inner_loss, 5), **summary(p, ys),
                     "both_5plus_fights": summary(p[seasoned], ys[seasoned]),
                     "weights_standardised": [round(float(v), 3) for v in w]}
    base, old = losses(probs["forecast 5.2 (live)"], ys), losses(probs["v5.1 forecast"], ys)
    for name in MODELS:
        cand = losses(probs[name], ys)
        out[name]["change_vs_5_2_95pct"] = [round(float((cand - base).mean()), 4)] + bootstrap(days, base, cand)
        out[name]["change_vs_5_1_95pct"] = [round(float((cand - old).mean()), 4)] + bootstrap(days, old, cand)
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--rating-snapshot", type=Path, required=True)
    parser.add_argument("--forecast-adjustment", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit(f"{args.output} exists; write a new version instead.")
    fights, names = load(args.database)
    forecasts = {}
    for line in open(args.rating_snapshot / "forecasts.jsonl"):
        item = json.loads(line)
        forecasts[item["fight_id"]] = item
    adjusted = {}
    for line in open(args.forecast_adjustment / "forecasts.jsonl"):
        row = json.loads(line)
        adjusted[row["fight_id"]] = row["forecast"]

    by_id = {f["id"]: f for f in fights}
    phi, v0 = empirical_bayes(fights)
    drift = {}
    for q in (0.0, 0.06, 0.12, 0.25, 0.5, 1.0):
        records, _, _ = run(fights, phi, v0, q)
        rows = assemble(records, forecasts, adjusted, by_id)
        drift[q] = choose_lambda(rows, *MODELS["multi-skill alone (Elo + 9 skills)"])[1]
    q = min(k for k, v in drift.items() if v <= min(drift.values()) + 2e-4)   # least drift within 0.0002 of the best
    records, diag, state = run(fights, phi, v0, q)
    rows = assemble(records, forecasts, adjusted, by_id)
    sim = simulate(rows)

    ev = diag["stat_eval"]
    latest = max(f["day"] for f in fights)
    active = {uid: f for uid, f in state.items() if f.last and f.last >= "2024-11-12" and f.fights >= 5}

    def leaders(values, top=5, reverse=True):
        ranked = sorted(active, key=lambda uid: values(active[uid]), reverse=reverse)[:top]
        return [{"name": names.get(uid, uid), "skill": round(float(values(active[uid])), 2), "fights": active[uid].fights} for uid in ranked]

    report = {
        "train": TRAIN, "inner_validation_from": INNER, "test_from": TEST_FROM, "data_through": latest,
        "stats": STATS,
        "dispersion": {s: round(float(phi[i]), 2) for i, s in enumerate(STATS)},
        "starting_variance": {s: round(float(v0[i]), 3) for i, s in enumerate(STATS)},
        "drift_per_year_tried": {str(k): round(v, 5) for k, v in drift.items()}, "drift_per_year": q,
        "stat_prediction_2019_on": {s: {"fighter_fights": int(ev["n"][i]),
                                         "deviance_career_average": round(float(ev["base"][i] / ev["n"][i]), 3),
                                         "deviance_multiskill": round(float(ev["model"][i] / ev["n"][i]), 3),
                                         "improvement": round(float(1 - ev["model"][i] / ev["base"][i]), 4),
                                         "uncertainty_check_should_be_near_1": round(float(ev["z2"][i] / ev["n"][i]), 3)}
                                    for i, s in enumerate(STATS)},
        "win_models": evaluate(rows),
        "simulation": sim, "method_of_victory_2019_on": method_scores(rows),
        "leaders_active_5plus_fights": {
            **{LABELS[s]: leaders(lambda f, i=IDX[s]: f.o[i]) for s in ("str", "kd", "td", "ctrl", "sub", "ko")},
            **{DEF_LABELS[s]: leaders(lambda f, i=IDX[s]: f.d[i]) for s in ("str", "td", "ko")}},
    }
    args.output.mkdir(parents=True)
    (args.output / "report.json").write_text(json.dumps(report, indent=1) + "\n")
    skills = {uid: {"name": names.get(uid), "fights": f.fights, "last_fight": f.last,
                    "offense": {s: [round(float(f.o[i]), 3), round(float(math.sqrt(f.vo[i])), 3)] for i, s in enumerate(STATS)},
                    "defense": {s: [round(float(f.d[i]), 3), round(float(math.sqrt(f.vd[i])), 3)] for i, s in enumerate(STATS)}}
              for uid, f in state.items() if f.last and f.last >= "2024-11-12"}
    (args.output / "skills_active.json").write_text(json.dumps(skills, separators=(",", ":")) + "\n")
    print(json.dumps(report, indent=1))


if __name__ == "__main__":
    main()
