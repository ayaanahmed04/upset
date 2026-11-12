"""v5.1 research: shrink the skill term toward the average for short UFC records.

The v5 skill term used each fighter's opponent-adjusted profile at full weight even after one
or two fights, so a two-fight fighter with extreme numbers could out-rate a long-time champion.
Here the term is multiplied by n / (n + k), n = prior UFC bouts in the profile. k is chosen on
2010-2018 fights only (training log loss), for the displayed rating and the forecast separately;
2019+ is reported once. k = 0 reproduces v5 exactly.
"""

import argparse
import json
import math
import time
from collections import defaultdict
from pathlib import Path
from statistics import NormalDist

from upset.ratings import build_v5 as B
from upset.ratings import v5_research as R
from upset.ratings.data import load_bouts

NORMAL = NormalDist()


load_v4_with_bouts = B.load_v4_with_bouts


def scored(preds):
    def few(rows):
        return [r for r in rows if min(r["prior_bouts"]) <= 3]
    test = R.eligible(preds, *R.TEST)
    return {"train": R.metrics(R.eligible(preds, *R.TRAIN)), "test": R.metrics(test),
            "recent": R.metrics(R.eligible(preds, "2025-01-01", "2099-01-01")),
            "test_short_records": R.metrics(few(test))}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--v4", type=Path, required=True)
    parser.add_argument("--research", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--part", choices=("rating", "forecast"), required=True)
    args = parser.parse_args()
    summary = json.loads((args.research / "summary.json").read_text())
    weights = summary["skill_weights_striking_wrestling_grappling"]
    base = summary["selected_pass_rule"] if args.part == "rating" else summary["selected"]
    bouts, meta = load_bouts(args.database.resolve(), summary["before_exclusive"])
    v4 = load_v4_with_bouts(args.v4 / "ratings.jsonl")
    prepared = R.prepare(bouts, v4)
    results, started = [], time.time()
    grid = [(base["beta"], k, 0.) for k in (0., 1., 2., 3., 5., 8.)] + [(base["beta"] + .3, k, 0.) for k in (0., 1., 2.)]
    grid += [(beta, 0., vs) for beta in (base["beta"], base["beta"] + .3, base["beta"] + .6) for vs in (.1, .2, .4, .8, 1.6)]
    for beta, k, vs in grid:
            cfg = {**base, "beta": beta, "k": k, "vs": vs}
            preds, _ = B.replay(prepared, v4, cfg, weights)
            results.append({"config": cfg, **scored(preds)})
            print(args.part, beta, k, vs, results[-1]["train"]["log_loss"], results[-1]["test"]["log_loss"],
                  results[-1]["test_short_records"], f"{time.time() - started:.0f}s", flush=True)
    results.sort(key=lambda x: x["train"]["log_loss"])
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / f"{args.part}.json").write_text(json.dumps({"part": args.part, "selected": results[0]["config"],
        "baseline_k0": next(r for r in results if r["config"]["k"] == 0 and r["config"]["vs"] == 0 and r["config"]["beta"] == base["beta"]),
        "results": results}, indent=1))


if __name__ == "__main__":
    main()
