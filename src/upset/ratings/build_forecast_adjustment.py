"""Build the UPSET forecast adjustment (forecast revision 5.2): age and a market starting point.

On top of the v5.1 walk-forward forecast:

    logit p = a * logit(v5.1 forecast)
              + b_light * (years past 32: A - B)      for most divisions
              + b_heavy * (years past 32: A - B)      for heavyweight and light heavyweight
              + c * (start_A - start_B)

start = what the betting market knew about a fighter at their UFC debut beyond the v5.1 forecast
(logit market - logit forecast, debut fight only), times decay^(UFC fights since the debut). The
odds of the fight being forecast are never used. The settings were chosen on 2010-2018 and tested
on 2019 onward (docs/RATING_V5_ADJUSTMENTS_2026_11_12.md); this script fits them on 2010-2018 again,
writes the adjusted walk-forward forecast for every fight, and records before/after metrics.

The UPSET rating itself (the 60-99 number) is unchanged.
"""

import argparse
import hashlib
import json
import math
from bisect import bisect_left
from datetime import date
from pathlib import Path

from upset.ratings import v5_adjustments_research as R

VERSION = "forecast_adjustment_v1"
REVISION = "5.2"
AGE_PIVOT = 32
DECAY = 0.85
HEAVY = ("heavyweight",)  # matches "Heavyweight" and "Light Heavyweight"


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def age_term(age):
    return max((age if age is not None else AGE_PIVOT) - AGE_PIVOT, 0)


def score(rows, key):
    rows = [r for r in rows if r["y"] is not None]
    ll = -sum(math.log(min(max(r[key] if r["y"] else 1 - r[key], 1e-9), 1)) for r in rows) / len(rows)
    brier = sum((r[key] - r["y"]) ** 2 for r in rows) / len(rows)
    acc = sum(.5 if r[key] == .5 else float((r[key] > .5) == bool(r["y"])) for r in rows) / len(rows)
    return {"bouts": len(rows), "log_loss": round(ll, 5), "brier": round(brier, 5), "accuracy": round(acc, 4)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--rating-snapshot", type=Path, required=True)
    parser.add_argument("--market-odds", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit(f"{args.output} exists; write a new version instead.")
    births, appearances, forecasts, odds, classes = R.load(args.database, args.rating_snapshot / "forecasts.jsonl",
                                                            args.market_odds / "odds.json")
    R.CLASSES.update(classes)
    spec = {"age_split": 1, "start": DECAY}
    records = R.build_rows(births, appearances, forecasts, odds)
    train = [(R.features(r, spec), r["y"]) for r in records if R.TRAIN[0] <= r["day"] <= R.TRAIN[1]]
    a, b_light, b_heavy, c = R.fit(R.symmetric(train))
    weights = {"forecast": round(a, 6), "age_light": round(b_light, 6), "age_heavy": round(b_heavy, 6), "start": round(c, 6)}

    # Adjusted forecast for every fight, walking forward so a debut edge is only known after the debut.
    debut_edge, out, rows = {}, [], []
    for item in sorted(forecasts, key=lambda r: (r["event_date"], r["fight_id"])):
        day, ids, f = item["event_date"], item["fighter_ids"], item["forecast"]
        market = odds.get(item["fight_id"])
        m = None
        if market and set(market["fighter_ids"]) == set(ids):
            m = market["probability_a"] if market["fighter_ids"][0] == ids[0] else 1 - market["probability_a"]
        heavy = any(word in classes.get(item["fight_id"], "") for word in HEAVY)
        terms = []
        for i, uid in enumerate(ids):
            prior = bisect_left(appearances.get(uid, []), day)
            born = births.get(uid)
            age = (date.fromisoformat(day) - born).days / 365.25 if born else None
            edge = debut_edge.get(uid)
            start = edge["edge"] * DECAY ** (prior - 1) if edge is not None and prior >= 1 else 0.0
            terms.append((age_term(age), start, prior))
        d_age = terms[0][0] - terms[1][0]
        d_start = terms[0][1] - terms[1][1]
        x = a * R.logit(f) + (b_heavy if heavy else b_light) * d_age + c * d_start
        p = R.sigmoid(x)
        out.append({"fight_id": item["fight_id"], "forecast": round(p, 6), "forecast_v5_1": f})
        rows.append({"day": day, "y": item["y"], "p": p, "f": f, "eligible": min(item["prior_decisive_bouts"]) >= 1})
        for i, uid in enumerate(ids):
            if terms[i][2] == 0 and m is not None and uid not in debut_edge:
                p_side = f if i == 0 else 1 - f
                m_side = m if i == 0 else 1 - m
                debut_edge[uid] = {"date": day, "edge": round(R.logit(m_side) - R.logit(p_side), 6)}
    edges = debut_edge

    windows = {"train": ("2010-01-01", "2019-01-01"), "test": ("2019-01-01", "2099-01-01"),
               "recent": ("2025-01-01", "2099-01-01")}
    metrics = {}
    for name, (start, end) in windows.items():
        chosen = [r for r in rows if start <= r["day"] < end and r["eligible"] and r["y"] is not None]
        metrics[name] = {"v5_1": score(chosen, "f"), "adjusted": score(chosen, "p")}

    args.output.mkdir(parents=True)
    body = "".join(json.dumps(row, separators=(",", ":")) + "\n" for row in out).encode()
    (args.output / "forecasts.jsonl").write_bytes(body)
    edges_body = json.dumps(edges, separators=(",", ":"), sort_keys=True).encode()
    (args.output / "debut_edges.json").write_bytes(edges_body)
    db_manifest = json.loads((args.database.parent / "manifest.json").read_text())
    manifest = {
        "version": VERSION, "revision": REVISION,
        "model": {"weights": weights, "age_pivot": AGE_PIVOT, "decay": DECAY, "heavy_divisions": "Heavyweight, Light Heavyweight",
                  "fit_on": "2010-01-01..2018-12-31",
                  "description": "v5.1 forecast adjusted for age (years past 32, heavier divisions separate) and a starting "
                                 "point from the market at each fighter's UFC debut. The current fight's odds are never used."},
        "metrics": metrics,
        "inputs": {"database_sha256": db_manifest["database_sha256"],
                   "rating_manifest_sha256": digest(args.rating_snapshot / "manifest.json"),
                   "market_odds_sha256": json.loads((args.market_odds / "manifest.json").read_text())["output_sha256"]["odds.json"]},
        "output_sha256": {"forecasts.jsonl": hashlib.sha256(body).hexdigest(),
                          "debut_edges.json": hashlib.sha256(edges_body).hexdigest()},
        "tool": "src/upset/ratings/build_forecast_adjustment.py"}
    (args.output / "manifest.json").write_text(json.dumps(manifest, indent=1) + "\n")
    print(json.dumps({"weights": weights, "metrics": metrics, "debut_edges": len(edges)}, indent=1))


if __name__ == "__main__":
    main()
