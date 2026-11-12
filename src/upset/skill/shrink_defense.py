"""Chronological offline sample-size-adjusted defense prototype; never a release."""

import argparse
import json
from collections import Counter, defaultdict, deque
from itertools import groupby
from math import lgamma, log, log1p
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np

from upset.skill.takedown_defense import digest

STRENGTHS = (5, 10, 25, 50, 100)
MODELS = ("raw_career", "raw_last5", "sample_adjusted")
EPSILON = 1e-6


def adjusted_mean(stopped, attempts, baseline, strength):
    if (type(stopped) is not int or type(attempts) is not int
            or not 0 <= stopped <= attempts or strength <= 0
            or baseline is not None and not 0 <= baseline <= 1):
        raise ValueError("Invalid counts, baseline or prior strength.")
    return None if baseline is None else (stopped + strength*baseline)/(attempts+strength)


def predict(sides, strength):
    """Predict an entire date first, then update all histories from that date."""
    keys = {(r["fight_id"], r["fighter_id"]) for r in sides}
    if len(keys) != len(sides):
        raise ValueError("Duplicate side observations.")
    career = defaultdict(lambda: [0, 0, 0])  # stopped, attempts, all recorded bouts
    recent = defaultdict(lambda: deque(maxlen=5))
    pools = defaultdict(lambda: [0, 0])
    predictions = []
    ordered = sorted(sides, key=lambda r: (r["event_date"], r["fight_id"], r["fighter_id"]))
    for day, group in groupby(ordered, key=lambda r: r["event_date"]):
        batch = list(group)
        for row in batch:
            uid, scope = row["fighter_id"], row["division"]
            success, trials, bouts = career[uid]
            last_success = sum(s for s, n in recent[uid])
            last_trials = sum(n for s, n in recent[uid])
            pool_scope = scope if scope is not None and pools[scope][1] >= 200 else "All divisions"
            pool_success, pool_trials = pools[pool_scope]
            baseline = pool_success/pool_trials if pool_trials else None
            predictions.append({
                "event_date": day, "event_id": row["event_id"],
                "fight_id": row["fight_id"], "fighter_id": uid,
                "division": scope, "status": row["status"],
                "attempts": row["opponent_takedown_attempts"],
                "stopped": row["takedowns_stopped"],
                "prior_bouts": bouts, "prior_attempts": trials,
                "last5_attempts": last_trials, "baseline": baseline,
                "baseline_scope": pool_scope, "baseline_prior_attempts": pool_trials,
                "raw_career": success/trials if trials else None,
                "raw_last5": last_success/last_trials if last_trials else None,
                "sample_adjusted": adjusted_mean(success, trials, baseline, strength),
            })
        for row in batch:
            uid = row["fighter_id"]
            success, trials = row["takedowns_stopped"], row["opponent_takedown_attempts"]
            career[uid][2] += 1
            if row["status"] not in ("observed", "zero_attempts"):
                recent[uid].append((0, 0))  # consumes a bout slot, contributes no measurement
                continue
            career[uid][0] += success
            career[uid][1] += trials
            recent[uid].append((success, trials))
            for scope in ("All divisions", row["division"]):
                if scope is not None:
                    pools[scope][0] += success
                    pools[scope][1] += trials
    return predictions


def score(row, model):
    s, n = row["stopped"], row["attempts"]
    p = min(1-EPSILON, max(EPSILON, row[model]))
    cross_entropy = -s*log(p) - (n-s)*log1p(-p)
    coefficient = lgamma(n+1) - lgamma(s+1) - lgamma(n-s+1)
    return cross_entropy-coefficient, cross_entropy


def common_support(row):
    return (row["status"] == "observed" and row["attempts"] > 0
            and all(row[m] is not None for m in MODELS))


def summarize(rows):
    if not rows:
        return {"side_bouts": 0, "attempts": 0, "scores": {}}
    trials = sum(r["attempts"] for r in rows)
    return {"side_bouts": len(rows), "attempts": trials,
            "date_clusters": len({r["event_date"] for r in rows}),
            "scores": {m: {"mean_binomial_nll": sum(score(r, m)[0] for r in rows)/len(rows),
                           "attempt_weighted_cross_entropy": sum(score(r, m)[1] for r in rows)/trials}
                       for m in MODELS}}


def bootstrap(rows):
    if not rows:
        return {}
    days = sorted({r["event_date"] for r in rows})
    counts = Counter(r["event_date"] for r in rows)
    totals = {m: defaultdict(float) for m in ("raw_career", "raw_last5")}
    for row in rows:
        for model, values in totals.items():
            values[row["event_date"]] += score(row, "sample_adjusted")[0] - score(row, model)[0]
    rng = np.random.default_rng(20261026)
    index = rng.integers(0, len(days), size=(1000, len(days)))
    weights = np.array([counts[d] for d in days])[index].sum(axis=1)
    result = {}
    for model, values in totals.items():
        observed = sum(values.values())/len(rows)
        sampled = np.array([values[d] for d in days])[index].sum(axis=1)/weights
        result[model] = {"adjusted_minus_baseline_nll": observed,
                         "date_cluster_bootstrap_95_interval": np.quantile(sampled, [.025, .975]).tolist(),
                         "replicates": 1000, "seed": 20261026, "lower_is_better": True}
    return result


def evaluate(sides):
    tuning = []
    for strength in STRENGTHS:
        predictions = predict(sides, strength)
        rows = [r for r in predictions if "2012-01-01" <= r["event_date"] < "2019-01-01" and common_support(r)]
        summary = summarize(rows)
        tuning.append({"strength": strength, **summary})
    eligible = [r for r in tuning if r["side_bouts"]]
    if not eligible:
        raise ValueError("No common-support tuning observations in 2012-2018.")
    chosen = min(eligible, key=lambda r: (r["scores"]["sample_adjusted"]["mean_binomial_nll"], r["strength"]))["strength"]
    predictions = predict(sides, chosen)
    development = [r for r in predictions if r["event_date"] >= "2019-01-01"]
    common = [r for r in development if common_support(r)]
    established = [r for r in common if r["prior_bouts"] >= 3 and r["prior_attempts"] >= 10]
    cold_start = [r for r in development if r["status"] == "observed"
                  and r["prior_attempts"] == 0 and r["sample_adjusted"] is not None]
    coverage = {"all_development_side_rows": len(development),
                "status_counts": dict(Counter(r["status"] for r in development)),
                "positive_trial_rows": sum(r["status"] == "observed" for r in development),
                "no_prior_recorded_bouts": sum(r["prior_bouts"] == 0 for r in development),
                "no_prior_attempts": sum(r["prior_attempts"] == 0 for r in development),
                "last5_zero_attempt_denominator": sum(r["last5_attempts"] == 0 for r in development),
                "no_population_baseline": sum(r["baseline"] is None for r in development)}
    report = {"prototype_version": "td_defense_shrink_v1", "opponent_adjusted": False,
              "public_release": False, "release_decision": "Offline prototype only; full release gates not run.",
              "evaluation_label": "Previously inspected development years, not a pristine holdout.",
              "estimand": "Defense probability conditional on recorded opponent takedown attempts.",
              "selected_prior_attempts": chosen, "tuning_2012_2018": tuning,
              "development_2019_plus": summarize(common), "coverage": coverage,
              "cold_start_adjusted_only": {"side_bouts": len(cold_start),
                  "attempts": sum(r["attempts"] for r in cold_start),
                  "mean_binomial_nll": sum(score(r, "sample_adjusted")[0] for r in cold_start)/len(cold_start) if cold_start else None,
                  "note": "No raw-career/last-five comparison is possible without prior attempt exposure."},
              "paired_comparisons": bootstrap(common),
              "established_common_support": {**summarize(established), "paired_comparisons": bootstrap(established)},
              "by_year": {str(y): summarize([r for r in common if r["event_date"].startswith(str(y))]) for y in sorted({int(r["event_date"][:4]) for r in common})},
              "by_division": {d: summarize([r for r in common if (r["division"] or "Unknown")==d]) for d in sorted({r["division"] or "Unknown" for r in common})},
              "uncertainty": "Only score-difference bootstrap intervals; no fighter skill or predictive intervals.",
              "limitations": ["No opponent-quality adjustment", "No attempt-count or duration forecast",
                              "Shared bouts/date clusters are dependent", "Small slices are descriptive, not release decisions",
                              "Prior mean and strength uncertainty are not propagated"]}
    return predictions, report


def run(adapter, protocol, output):
    if output.exists() or output.resolve().is_relative_to(adapter.resolve()):
        raise ValueError("Use a new output separate from the adapter.")
    manifest = json.loads((adapter / "manifest.json").read_text())
    source = adapter / "sides.jsonl"
    if digest(source) != manifest["output_sha256"]["sides.jsonl"]:
        raise ValueError("Adapter rows differ from the manifest hash.")
    hashes = {str(p): digest(p) for p in (source, adapter / "manifest.json", protocol, Path(__file__))}
    sides = [json.loads(line) for line in source.read_text().splitlines()]
    predictions, report = evaluate(sides)
    report["input_sha256"] = hashes
    report["before_exclusive"] = manifest["before_exclusive"]
    output.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=output.parent, prefix=".upset-defense-prototype-") as temporary:
        folder = Path(temporary) / "prototype"
        folder.mkdir()
        path = folder / "predictions.jsonl"
        path.write_text("".join(json.dumps(r, sort_keys=True) + "\n" for r in predictions))
        report["output_sha256"] = {"predictions.jsonl": digest(path)}
        if any(digest(Path(p)) != h for p, h in hashes.items()):
            raise ValueError("Prototype inputs changed during evaluation.")
        (folder / "report.json").write_text(json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n")
        folder.rename(output)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--adapter", type=Path, required=True)
    parser.add_argument("--protocol", type=Path, default=Path("docs/TAKEDOWN_DEFENSE_PROTOCOL_V1.md"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = run(args.adapter, args.protocol, args.output)
    print(json.dumps({k: report[k] for k in ("selected_prior_attempts", "coverage", "development_2019_plus", "paired_comparisons", "public_release")}, indent=2))


if __name__ == "__main__":
    main()
