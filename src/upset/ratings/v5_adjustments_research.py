"""Does the UPSET forecast improve if it accounts for inactivity, age, or a market-based starting point?

Walk-forward research on the v5.1 forecasts, which were themselves made from earlier fights only.
Every candidate is an adjustment on top of the forecast:

    logit p = a * logit(forecast) + b1 * x1 + b2 * x2 + ...

fit on 2010-2018 decided UFC fights and scored once on 2019 onward. The features are differences
between the two fighters, so swapping corners just flips the sign (no corner bias can sneak in).

x candidates
* layoff: years since the fighter's previous UFC fight, beyond the first year (capped at 5).
  Only UFC fights are known, so a fighter busy elsewhere looks "inactive"; that limit is reported.
* age: years of age past 32 (date of birth from the fighter profile; 0 if unknown).
* starting point (strict): what the betting market knew about a fighter at their UFC debut beyond
  the UPSET forecast (logit market - logit forecast, debut fight only), carried into their next
  fights with a decaying weight. The current fight's odds are never used.
* debut odds (reference only): the same edge taken from the current fight's odds when a fighter is
  debuting. This copies the market for debuts and is reported for comparison, not proposed.
"""

import argparse
import json
import math
import random
import sqlite3
from bisect import bisect_left
from collections import defaultdict
from contextlib import closing
from datetime import date
from pathlib import Path

TRAIN = ("2010-01-01", "2018-12-31")
TEST_FROM = "2019-01-01"
CLASSES = {}


def logit(p):
    p = min(max(p, 1e-6), 1 - 1e-6)
    return math.log(p / (1 - p))


def sigmoid(x):
    return 1 / (1 + math.exp(-max(min(x, 40), -40)))


def solve(matrix, vector):
    n = len(vector)
    m = [row[:] + [vector[i]] for i, row in enumerate(matrix)]
    for col in range(n):
        pivot = max(range(col, n), key=lambda r: abs(m[r][col]))
        m[col], m[pivot] = m[pivot], m[col]
        for r in range(n):
            if r != col and m[col][col]:
                f = m[r][col] / m[col][col]
                m[r] = [a - f * b for a, b in zip(m[r], m[col])]
    return [m[i][n] / m[i][i] if m[i][i] else 0.0 for i in range(n)]


def fit(rows, ridge=1e-6):
    """Logistic regression without intercept on symmetric rows (x, y), Newton's method."""
    k = len(rows[0][0])
    w = [1.0] + [0.0] * (k - 1)
    for _ in range(60):
        g = [0.0] * k
        hess = [[ridge * (i == j) for j in range(k)] for i in range(k)]
        for x, y in rows:
            p = sigmoid(sum(a * b for a, b in zip(w, x)))
            r, s = p - y, p * (1 - p)
            for i in range(k):
                g[i] += r * x[i]
                for j in range(k):
                    hess[i][j] += s * x[i] * x[j]
        step = solve(hess, g)
        w = [a - b for a, b in zip(w, step)]
        if sum(abs(b) for b in step) < 1e-9:
            break
    return w


def loss(p):
    return -math.log(min(max(p, 1e-9), 1 - 1e-9))


def load(database, forecasts_path, odds_path):
    with closing(sqlite3.connect(database)) as db:
        births = {}
        for uid, profile in db.execute("SELECT id,profile FROM fighters"):
            dob = (json.loads(profile or "{}") or {}).get("date_of_birth")
            if dob:
                try:
                    births[uid] = date.fromisoformat(dob)
                except ValueError:
                    pass
        appearances = defaultdict(list)
        classes = {}
        for fid, day, payload in db.execute("SELECT id,event_date,payload FROM fights"):
            p = json.loads(payload)
            classes[fid] = (p.get("weight_class") or "").lower()
            for key in ("upset_fighter_1_id", "upset_fighter_2_id"):
                if p.get(key):
                    appearances[p[key]].append(day)
    for days in appearances.values():
        days.sort()
    forecasts = [json.loads(line) for line in open(forecasts_path)]
    odds = json.loads(Path(odds_path).read_text())
    return births, appearances, forecasts, odds, classes


def build_rows(births, appearances, forecasts, odds):
    """One record per decided fight, with per-fighter context, in date order."""
    debut_edge = {}
    records = []
    for item in sorted(forecasts, key=lambda r: (r["event_date"], r["fight_id"])):
        day = item["event_date"]
        ids, f = item["fighter_ids"], item["forecast"]
        market = odds.get(item["fight_id"])
        m = None
        if market and set(market["fighter_ids"]) == set(ids):
            m = market["probability_a"] if market["fighter_ids"][0] == ids[0] else 1 - market["probability_a"]
        sides = []
        for i, uid in enumerate(ids):
            dates = appearances.get(uid, [])
            prior = bisect_left(dates, day)
            last = dates[prior - 1] if prior else None
            layoff = (date.fromisoformat(day) - date.fromisoformat(last)).days / 365.25 if last else None
            born = births.get(uid)
            age = (date.fromisoformat(day) - born).days / 365.25 if born else None
            p_side = f if i == 0 else 1 - f
            m_side = None if m is None else (m if i == 0 else 1 - m)
            sides.append({"uid": uid, "prior": prior, "layoff": layoff, "age": age,
                          "edge_now": None if m_side is None else logit(m_side) - logit(p_side),
                          "debut_edge": debut_edge.get(uid)})
        # Remember what the market knew at each fighter's UFC debut (used only in later fights).
        for s in sides:
            if s["prior"] == 0 and s["edge_now"] is not None and s["uid"] not in debut_edge:
                debut_edge[s["uid"]] = s["edge_now"]
        if item["y"] is None or day < TRAIN[0]:
            continue
        records.append({"day": day, "f": f, "m": m, "y": item["y"], "sides": sides, "fight_id": item["fight_id"],
                        "heavy": "heavyweight" in CLASSES.get(item["fight_id"], "")})
    return records


def features(rec, spec):
    a, b = rec["sides"]
    x = [logit(rec["f"])]
    if "layoff" in spec:
        g = lambda s: min(max((s["layoff"] or 0) - 1, 0), 5)
        x.append(g(a) - g(b))
    if "age" in spec:
        g = lambda s: max((s["age"] or 32) - 32, 0)
        x.append(g(a) - g(b))
    if "age_split" in spec:
        g = lambda s: max((s["age"] or 32) - 32, 0)
        heavy = rec.get("heavy", False)
        x.append((g(a) - g(b)) * (0 if heavy else 1))
        x.append((g(a) - g(b)) * (1 if heavy else 0))
    if "start" in spec:
        decay = spec["start"]
        g = lambda s: (s["debut_edge"] or 0) * (decay ** (s["prior"] - 1)) if s["prior"] >= 1 else 0
        x.append(g(a) - g(b))
    if "debut_odds" in spec:
        g = lambda s: (s["edge_now"] or 0) if s["prior"] == 0 else 0
        x.append(g(a) - g(b))
    return x


def symmetric(rows):
    out = []
    for x, y in rows:
        out.append((x, y))
        out.append(([-v for v in x], 1 - y))
    return out


_fits = {}


def evaluate(records, spec, subset=lambda r: True):
    key = json.dumps(spec, sort_keys=True)
    if key not in _fits:
        train = [(features(r, spec), r["y"]) for r in records if TRAIN[0] <= r["day"] <= TRAIN[1]]
        _fits[key] = fit(symmetric(train))
    w = _fits[key]
    test = [r for r in records if r["day"] >= TEST_FROM and subset(r)]
    probs = [sigmoid(sum(a * b for a, b in zip(w, features(r, spec)))) for r in test]
    return w, test, probs


def summary(test, probs):
    n = len(test)
    ll = sum(loss(p if r["y"] else 1 - p) for r, p in zip(test, probs)) / n
    acc = sum((p > .5) == bool(r["y"]) for r, p in zip(test, probs)) / n
    return {"bouts": n, "log_loss": round(ll, 4), "accuracy": round(acc, 4)}


def bootstrap(test, base, cand, draws=400, seed=7):
    """95% interval for the log-loss change (candidate - base), resampling event dates."""
    by_day = defaultdict(list)
    for r, p0, p1 in zip(test, base, cand):
        by_day[r["day"]].append(loss(p1 if r["y"] else 1 - p1) - loss(p0 if r["y"] else 1 - p0))
    days = list(by_day)
    rng = random.Random(seed)
    means = []
    for _ in range(draws):
        picked = [rng.choice(days) for _ in days]
        diffs = [d for day in picked for d in by_day[day]]
        means.append(sum(diffs) / len(diffs))
    means.sort()
    return [round(means[int(.025 * draws)], 4), round(means[int(.975 * draws)], 4)]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--forecasts", type=Path, required=True)
    parser.add_argument("--odds", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--example", type=Path, help="A frozen picks.json to show what each version would say.")
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit(f"{args.output} exists; write a new version instead.")
    births, appearances, forecasts, odds, classes = load(args.database, args.forecasts, args.odds / "odds.json")
    CLASSES.update(classes)
    records = build_rows(births, appearances, forecasts, odds)

    # Pick the starting-point decay on the training years only.
    decays = {}
    for decay in (0.3, 0.5, 0.7, 0.85, 1.0):
        train = [(features(r, {"start": decay}), r["y"]) for r in records if TRAIN[0] <= r["day"] <= TRAIN[1]]
        w = fit(symmetric(train))
        decays[decay] = sum(loss(sigmoid(sum(a * b for a, b in zip(w, x))) if y else 1 - sigmoid(sum(a * b for a, b in zip(w, x))))
                            for x, y in train) / len(train)
    decay = min(decays, key=decays.get)

    specs = {"forecast (recalibrated)": {}, "+ layoff": {"layoff": 1}, "+ age": {"age": 1},
             "+ layoff + age": {"layoff": 1, "age": 1},
             "+ market starting point (strict)": {"start": decay},
             "+ age + starting point": {"age": 1, "start": decay},
             "+ age (heavyweight and light heavyweight separate) + starting point": {"age_split": 1, "start": decay},
             "+ layoff + age + starting point": {"layoff": 1, "age": 1, "start": decay},
             "reference: + debut odds (copies the market for debuts)": {"layoff": 1, "age": 1, "start": decay, "debut_odds": 1}}
    subsets = {"all": lambda r: True,
               "a fighter back from 2+ years away": lambda r: any((s["layoff"] or 0) >= 2 for s in r["sides"]),
               "a fighter with 1-4 UFC fights": lambda r: any(1 <= s["prior"] <= 4 for s in r["sides"]),
               "a fighter aged 35+": lambda r: any((s["age"] or 0) >= 35 for s in r["sides"]),
               "both fighters with 5+ UFC fights": lambda r: all(s["prior"] >= 5 for s in r["sides"]),
               "heavyweight and light heavyweight": lambda r: r.get("heavy", False)}
    report = {"train": TRAIN, "test_from": TEST_FROM, "starting_point_decay": decay, "decay_train_loss": decays,
              "models": {}, "market_on_same_fights": {}}
    base_probs = {}
    for name, spec in specs.items():
        entry = {}
        for label, keep in subsets.items():
            w, test, probs = evaluate(records, spec, keep)
            entry[label] = summary(test, probs)
            if name == "forecast (recalibrated)":
                base_probs[label] = probs
            else:
                entry[label]["change_vs_forecast_95pct"] = bootstrap(test, base_probs[label], probs)
            entry["weights"] = [round(v, 4) for v in w]
        report["models"][name] = entry
    for label, keep in subsets.items():
        test = [r for r in records if r["day"] >= TEST_FROM and keep(r) and r["m"] is not None]
        report["market_on_same_fights"][label] = {
            "market": summary(test, [r["m"] for r in test]),
            "forecast": summary(test, [r["f"] for r in test])}
    if args.example:
        picks = json.loads(Path(args.example).read_text())
        day = picks["event"]["date"]
        debut_edge = {}
        for r in records:
            for s in r["sides"]:
                if s["debut_edge"] is not None:
                    debut_edge[s["uid"]] = s["debut_edge"]
        # Debut edges for fighters whose debut was the latest fight in the data.
        for rec in records:
            for s in rec["sides"]:
                if s["prior"] == 0 and s["edge_now"] is not None:
                    debut_edge.setdefault(s["uid"], s["edge_now"])
        report["example"] = {"event": picks["event"]["name"], "rows": []}
        for pick in picks["picks"]:
            ids = [f["id"] for f in pick["fighters"]]
            sides = []
            for uid in ids:
                dates = appearances.get(uid, [])
                prior = bisect_left(dates, day)
                last = dates[prior - 1] if prior else None
                born = births.get(uid)
                sides.append({"uid": uid, "prior": prior,
                              "layoff": (date.fromisoformat(day) - date.fromisoformat(last)).days / 365.25 if last else None,
                              "age": (date.fromisoformat(day) - born).days / 365.25 if born else None,
                              "edge_now": None, "debut_edge": debut_edge.get(uid)})
            rec = {"f": pick["probabilities"][0], "sides": sides, "heavy": "heavyweight" in (pick.get("division") or "").lower()}
            row = {"fight": " vs ".join(f["name"] for f in pick["fighters"]), "forecast": pick["probabilities"][0],
                   "market": pick.get("market", {}).get("probabilities", [None])[0],
                   "ages": [None if s["age"] is None else round(s["age"], 1) for s in sides],
                   "years_out": [None if s["layoff"] is None else round(s["layoff"], 1) for s in sides]}
            for name in ("+ age", "+ age + starting point", "+ age (heavyweight and light heavyweight separate) + starting point"):
                w = _fits[json.dumps(specs[name], sort_keys=True)]
                row[name] = round(sigmoid(sum(a * b for a, b in zip(w, features(rec, specs[name])))), 3)
            report["example"]["rows"].append(row)
    args.output.mkdir(parents=True)
    (args.output / "report.json").write_text(json.dumps(report, indent=1) + "\n")
    print(json.dumps(report, indent=1))


if __name__ == "__main__":
    main()
