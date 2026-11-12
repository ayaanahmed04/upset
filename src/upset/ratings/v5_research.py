"""UPSET rating v5 research: a results-first Bayesian fighter rating with a skill prior.

Walk-forward only. Every prediction uses bouts strictly before its event date, and
all bouts on one date are scored before any rating on that date changes.

Model (log-odds scale, 0 = a typical UFC opponent):
    strength_i = r_i + beta * s_i
    P(i beats j) = sigmoid(g * (strength_i - strength_j)),  g = 1/sqrt(1 + 3(v_i+v_j)/pi^2)
r_i is a results rating with variance v_i (Laplace / Glicko-style update weighted by
method of victory). Variance grows with inactivity. s_i is the pre-fight v4 skill
profile (striking, wrestling, grappling) collapsed with weights fitted on training years.

Hyperparameters are chosen on 2010-2018 bouts only; 2019-01-01 onward is the test set.
"""

import argparse
import json
import math
from bisect import bisect_left
from collections import defaultdict
from itertools import groupby, product
from pathlib import Path
from statistics import NormalDist

from upset.ratings.data import load_bouts

TRAIN = ("2010-01-01", "2019-01-01")
TEST = ("2019-01-01", "2099-01-01")
NORMAL = NormalDist()


def sigmoid(x):
    return 1 / (1 + math.exp(-x)) if x >= 0 else math.exp(x) / (1 + math.exp(x))


def years(a, b):
    from datetime import date
    return (date.fromisoformat(b) - date.fromisoformat(a)).days / 365.25


def method_kind(bout):
    text = (bout.get("result_method") or "").casefold()
    if bout["method_group"] in ("ko", "sub"):
        return "finish"
    if "split" in text or "majority" in text:
        return "close"
    if bout["method_group"] == "decision":
        return "decision"
    return "other"


def load_v4(path):
    rows = defaultdict(list)
    with open(path) as stream:
        for line in stream:
            row = json.loads(line)
            z = {}
            for part in row["parts"]:
                if part["key"] in ("striking", "wrestling", "grappling"):
                    raw = part.get("raw_score")
                    z[part["key"]] = None if raw is None else NORMAL.inv_cdf(min(.9999, max(.0001, raw / 100)))
            rows[row["fighter_id"]].append((row["event_date"], row["raw_combined"], z, row["score"]))
    return {uid: ([r[0] for r in sorted(v)], sorted(v)) for uid, v in rows.items()}


def v4_prior(v4, uid, day):
    days, rows = v4.get(uid, ((), ()))
    i = bisect_left(days, day)
    return rows[i - 1] if i else None


def prepare(bouts, v4):
    prepared = []
    for bout in bouts:
        priors = [v4_prior(v4, uid, bout["event_date"]) for uid in bout["fighter_ids"]]
        prepared.append({**{k: bout[k] for k in ("fight_id", "event_date", "fighter_ids", "winner_id", "outcome", "names")},
                         "kind": method_kind(bout), "v4": priors,
                         "title": "title" in (bout.get("result_method") or "").casefold()})
    return prepared


def skill_vector(prior):
    if prior is None:
        return None
    z = prior[2]
    return [z.get(k) or 0. for k in ("striking", "wrestling", "grappling")]


def fit_logistic(rows, iterations=30, ridge=1e-3):
    """Newton logistic regression without intercept: rows are (x vector, y)."""
    k = len(rows[0][0])
    w = [0.] * k
    for _ in range(iterations):
        grad = [0.] * k
        hess = [[0.] * k for _ in range(k)]
        for x, y in rows:
            p = sigmoid(sum(a * b for a, b in zip(w, x)))
            for i in range(k):
                grad[i] += (y - p) * x[i]
                for j in range(k):
                    hess[i][j] += p * (1 - p) * x[i] * x[j]
        for i in range(k):
            grad[i] -= ridge * w[i]
            hess[i][i] += ridge
        # Solve hess * step = grad (small k, Gaussian elimination).
        m = [row[:] + [g] for row, g in zip(hess, grad)]
        for i in range(k):
            pivot = max(range(i, k), key=lambda r: abs(m[r][i]))
            m[i], m[pivot] = m[pivot], m[i]
            for r in range(k):
                if r != i and m[i][i]:
                    f = m[r][i] / m[i][i]
                    m[r] = [a - f * b for a, b in zip(m[r], m[i])]
        step = [m[i][k] / m[i][i] for i in range(k)]
        w = [a + b for a, b in zip(w, step)]
        if max(abs(s) for s in step) < 1e-8:
            break
    return w


def replay(prepared, cfg, skill_weights, trace=False):
    """Return per-bout predictions and (optionally) every fighter's dated states."""
    v0, tau2, beta, w_finish, w_close, m0, pass_rule = (cfg[k] for k in
        ("v0", "tau2", "beta", "w_finish", "w_close", "m0", "pass_rule"))
    weight = {"finish": w_finish, "decision": 1., "close": w_close, "other": .5}
    r, v, last, n = {}, {}, {}, defaultdict(int)
    skill = {}
    out, states = [], defaultdict(list)

    def s_of(prior):
        vec = skill_vector(prior)
        return 0. if vec is None else sum(a * b for a, b in zip(skill_weights, vec))

    for day, batch in groupby(prepared, key=lambda b: b["event_date"]):
        updates = defaultdict(list)
        for bout in batch:
            ids = bout["fighter_ids"]
            pre = []
            for side, uid in enumerate(ids):
                if uid not in r:
                    r[uid], v[uid] = m0, v0
                var = v[uid] if uid not in last else min(v0, v[uid] + tau2 * max(0., years(last[uid], day)))
                s = beta * s_of(bout["v4"][side])
                skill[uid] = s
                pre.append((r[uid], var, s))
            (ra, va, sa), (rb, vb, sb) = pre
            g = 1 / math.sqrt(1 + 3 * (va + vb) / math.pi ** 2)
            delta = (ra + sa) - (rb + sb)
            p = sigmoid(g * delta)
            out.append({"fight_id": bout["fight_id"], "event_date": day, "p": p, "names": bout["names"],
                        "y": None if bout["winner_id"] is None else int(bout["winner_id"] == ids[0]),
                        "prior_bouts": [n[ids[0]], n[ids[1]]], "kind": bout["kind"],
                        "strength": [ra + sa, rb + sb], "v4": [None if x is None else x[1] for x in bout["v4"]]})
            if bout["winner_id"] is None:
                continue
            w = weight[bout["kind"]]
            for side, uid in enumerate(ids):
                y = int(bout["winner_id"] == uid)
                (ri, vi, si), (rj, vj, sj) = pre[side], pre[1 - side]
                q = sigmoid(g * ((ri + si) - (rj + sj)))
                post_v = 1 / (1 / vi + w * g * g * q * (1 - q))
                updates[uid].append((post_v * w * g * (y - q), post_v, ids[1 - side], y))
        for uid, changes in updates.items():
            r[uid] += sum(c[0] for c in changes)
            v[uid] = min(c[1] for c in changes)
            last[uid] = day
            n[uid] += len(changes)
        if pass_rule:
            # A decisive winner is never left below the opponent they just beat.
            for uid, changes in updates.items():
                for _, _, opp, y in changes:
                    if y == 1:
                        gap = (r[opp] + skill.get(opp, 0.)) - (r[uid] + skill.get(uid, 0.))
                        if gap > 0:
                            if pass_rule == "winner_up":
                                r[uid] += gap + 1e-6
                            else:
                                shift = gap / 2 + 1e-6
                                r[uid] += shift
                                r[opp] -= shift
        if trace:
            for uid in updates:
                states[uid].append((day, r[uid], v[uid], skill.get(uid, 0.), n[uid]))
    return out, states


def metrics(rows):
    rows = [r for r in rows if r["y"] is not None]
    if not rows:
        return None
    ll = -sum(math.log(r["p"] if r["y"] else 1 - r["p"]) for r in rows) / len(rows)
    brier = sum((r["p"] - r["y"]) ** 2 for r in rows) / len(rows)
    acc = sum(.5 if r["p"] == .5 else float((r["p"] > .5) == bool(r["y"])) for r in rows) / len(rows)
    return {"bouts": len(rows), "log_loss": round(ll, 5), "brier": round(brier, 5), "accuracy": round(acc, 4)}


def eligible(rows, start, end):
    return [r for r in rows if start <= r["event_date"] < end and r["y"] is not None
            and min(r["prior_bouts"]) >= 1 and None not in r["v4"]]


def v4_rows(prepared_rows, slope):
    return [{**r, "p": sigmoid(slope * (r["v4"][0] - r["v4"][1]))} for r in prepared_rows]


def elo_rows(prepared, k, half_life=None):
    state, out = {}, []
    for day, batch in groupby(prepared, key=lambda b: b["event_date"]):
        changes = defaultdict(float)
        for bout in batch:
            a, b = bout["fighter_ids"]
            vals = []
            for uid in (a, b):
                value, prev = state.get(uid, (1500., day))
                if half_life:
                    value = 1500 + (value - 1500) * 2 ** (-years(prev, day) * 365.25 / half_life)
                vals.append(value)
            p = 1 / (1 + 10 ** ((vals[1] - vals[0]) / 400))
            out.append({"fight_id": bout["fight_id"], "p": p})
            if bout["winner_id"] is not None:
                d = k * (int(bout["winner_id"] == a) - p)
                changes[a] += d
                changes[b] -= d
        for uid, d in changes.items():
            value, prev = state.get(uid, (1500., day))
            if half_life:
                value = 1500 + (value - 1500) * 2 ** (-years(prev, day) * 365.25 / half_life)
            state[uid] = (value + d, day)
    return {row["fight_id"]: row["p"] for row in out}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--v4", type=Path, required=True)
    parser.add_argument("--before", default="2026-11-08")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--stage", choices=("grid", "final"), default="grid")
    args = parser.parse_args()
    if args.output.exists() and any(args.output.iterdir()):
        raise SystemExit("Output folder already has files; use a new folder.")
    args.output.mkdir(parents=True, exist_ok=True)
    bouts, meta = load_bouts(args.database, args.before)
    v4 = load_v4(args.v4 / "ratings.jsonl")
    prepared = prepare(bouts, v4)

    # Skill weights: logistic regression on pre-fight skill differences, training years only.
    rows = []
    for bout in prepared:
        if not (TRAIN[0] <= bout["event_date"] < TRAIN[1]) or bout["winner_id"] is None:
            continue
        a, b = (skill_vector(p) for p in bout["v4"])
        if a is None or b is None:
            continue
        rows.append(([x - y for x, y in zip(a, b)], int(bout["winner_id"] == bout["fighter_ids"][0])))
    raw_weights = fit_logistic(rows)
    norm = math.sqrt(sum(w * w for w in raw_weights)) or 1.
    skill_weights = [w / norm for w in raw_weights]

    grid = [dict(v0=v0, tau2=t, beta=b, w_finish=1., w_close=.6, m0=0., pass_rule=pr)
            for v0, t, b, pr in product((.1, .2, .4), (0., .03), (1.1, 1.3, 1.6, 2.0), (None, "meet", "winner_up"))]
    results = []
    for cfg in grid:
        preds, _ = replay(prepared, cfg, skill_weights)
        train = metrics(eligible(preds, *TRAIN))
        results.append({"config": cfg, "train": train})
    results.sort(key=lambda x: x["train"]["log_loss"])
    best = dict(results[0]["config"])
    passing = [x for x in results if x["config"]["pass_rule"]]
    best_pass = dict(passing[0]["config"])

    # Test-period comparison for the selected configuration and its pass-rule twin.
    final = {}
    for label, cfg in (("v5", best), ("v5_pass_rule", best_pass),
                       ("results_only", {**best, "beta": 0., "pass_rule": None}),
                       ("skills_only_prior", {**best, "v0": 1e-6, "tau2": 0., "pass_rule": None})):
        preds, _ = replay(prepared, cfg, skill_weights)
        final[label] = {"test": metrics(eligible(preds, *TEST)), "train": metrics(eligible(preds, *TRAIN)),
                        "test_2025_26": metrics(eligible(preds, "2025-01-01", "2099-01-01"))}
        if label == "v5":
            base_preds = preds
    test_rows = eligible(base_preds, *TEST)
    # v4 raw combined, using its own declared probability slope fitted before 2019.
    final["v4_declared_slope"] = {"test": metrics(v4_rows(test_rows, .15130209582513166)),
                                  "test_2025_26": metrics(v4_rows([r for r in test_rows if r["event_date"] >= "2025-01-01"], .15130209582513166))}
    for label, k, hl in (("elo32", 32, None), ("elo64_decay", 64, 730)):
        probs = elo_rows(prepared, k, hl)
        final[label] = {"test": metrics([{**r, "p": probs[r["fight_id"]]} for r in test_rows]),
                        "test_2025_26": metrics([{**r, "p": probs[r["fight_id"]]} for r in test_rows if r["event_date"] >= "2025-01-01"])}
    summary = {"database_sha256": meta["database_sha256"], "before_exclusive": args.before,
               "train_window": TRAIN, "test_window": TEST, "skill_weights_striking_wrestling_grappling": skill_weights,
               "skill_weight_raw": raw_weights, "grid_size": len(grid), "selected": best, "selected_pass_rule": best_pass,
               "top_configs": results[:8], "comparison": final}
    (args.output / "summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps({k: summary[k] for k in ("skill_weights_striking_wrestling_grappling", "skill_weight_raw", "selected", "selected_pass_rule")}, indent=1))
    for label, value in final.items():
        print(label, value)


if __name__ == "__main__":
    main()
