"""Chronological significant-strike accuracy development prototype; no release."""

import argparse
import hashlib
import json
import platform
from collections import Counter, defaultdict, deque
from itertools import groupby
from math import isfinite, lgamma, log, log1p
from pathlib import Path

import numpy as np

from upset.skill.striking_adapter import (
    audit_rows,
    digest,
    encoded,
    load_adapter,
    verify_hashes,
    write_artifact,
)

CONFIG = {"version": "significant_strike_accuracy_v1", "strengths": [1, 5, 20, 100, 500],
          "tune_start": "2012-01-01", "development_start": "2019-01-01",
          "clip": 1e-6, "bootstrap_replicates": 1000, "seed": 20261103,
          "established_prior_bouts": 3, "established_prior_attempts": 100,
          "public_release": False, "opponent_adjusted": False}
MODELS = ("raw_career", "raw_last5", "career_jeffreys", "last5_jeffreys",
          "population_mean", "sample_adjusted")
REFERENCES = MODELS[:-1]


def adjusted_mean(landed, attempts, population, strength):
    if (type(landed) is not int or type(attempts) is not int or not 0 <= landed <= attempts
            or type(strength) not in (int, float) or not isfinite(strength) or strength <= 0
            or population is not None and (not isfinite(population) or not 0 <= population <= 1)):
        raise ValueError("Invalid counts, population mean or prior strength.")
    return None if population is None else (landed + strength * population) / (attempts + strength)


def predict(rows, strength):
    if len({(r["fight_id"], r["fighter_id"]) for r in rows}) != len(rows):
        raise ValueError("Duplicate side observations.")
    career = defaultdict(lambda: [0, 0, 0])
    recent = defaultdict(lambda: deque(maxlen=5))
    last_discarded_day = {}
    pooled_landed = pooled_attempts = 0
    predictions = []
    for day, group in groupby(sorted(rows, key=lambda r: (
            r["event_date"], r["fight_id"], r["fighter_id"])), key=lambda r: r["event_date"]):
        batch = list(group)
        population = pooled_landed / pooled_attempts if pooled_attempts else None
        for row in batch:
            uid = row["fighter_id"]
            landed, attempts, bouts = career[uid]
            last_landed = sum(r[1] for r in recent[uid])
            last_attempts = sum(r[2] for r in recent[uid])
            boundary = bool(recent[uid] and last_discarded_day.get(uid) == recent[uid][0][0])
            predictions.append({
                **{k: row[k] for k in ("fight_id", "fighter_id", "opponent_id", "event_date",
                                      "event_id", "division", "source", "status", "landed",
                                      "attempts", "duration_seconds", "short_fight")},
                "prior_bouts": bouts, "prior_landed": landed, "prior_attempts": attempts,
                "last5_landed": last_landed, "last5_attempts": last_attempts,
                "last5_splits_same_day_boundary": boundary,
                "population_prior_attempts": pooled_attempts,
                "raw_career": landed / attempts if attempts else None,
                "raw_last5": last_landed / last_attempts if last_attempts else None,
                "career_jeffreys": (landed + .5) / (attempts + 1),
                "last5_jeffreys": (last_landed + .5) / (last_attempts + 1),
                "population_mean": population,
                "sample_adjusted": adjusted_mean(landed, attempts, population, strength),
            })
        # Every prediction on this calendar date precedes all same-date updates.
        for row in batch:
            uid = row["fighter_id"]
            usable = row["status"] in ("observed", "zero_attempts")
            landed, attempts = (row["landed"], row["attempts"]) if usable else (0, 0)
            career[uid][0] += landed
            career[uid][1] += attempts
            career[uid][2] += 1
            if len(recent[uid]) == 5:
                last_discarded_day[uid] = recent[uid][0][0]
            recent[uid].append((day, landed, attempts))
            pooled_landed += landed
            pooled_attempts += attempts
    return predictions


def score(row, model, clip=CONFIG["clip"]):
    y, n, p = row["landed"], row["attempts"], row[model]
    if (type(y) is not int or type(n) is not int or not 0 <= y <= n or n == 0
            or p is None or not isfinite(p) or not 0 <= p <= 1
            or not 0 < clip < .5):
        raise ValueError("Scoring requires positive valid trials and a probability.")
    p = min(1 - clip, max(clip, p))
    cross_entropy = -y * log(p) - (n-y) * log1p(-p)
    coefficient = lgamma(n+1) - lgamma(y+1) - lgamma(n-y+1)
    brier = y * (1-p)**2 + (n-y) * p**2
    return cross_entropy - coefficient, cross_entropy, brier


def common_support(row):
    return (row["status"] == "observed" and row["attempts"] > 0
            and all(row[model] is not None for model in MODELS))


def summarize(rows, models=MODELS, clip=CONFIG["clip"]):
    exposure = sum(r["attempts"] for r in rows)
    scores = {}
    for model in models:
        values = [score(r, model, clip) for r in rows]
        scores[model] = {
            "mean_binomial_nll": sum(v[0] for v in values) / len(values) if values else None,
            "attempt_weighted_cross_entropy": sum(v[1] for v in values) / exposure if exposure else None,
            "attempt_level_brier": sum(v[2] for v in values) / exposure if exposure else None,
        }
    return {"side_bouts": len(rows), "attempts": exposure,
            "date_clusters": len({r["event_date"] for r in rows}), "scores": scores}


def paired_comparisons(rows):
    dates = sorted({r["event_date"] for r in rows})
    if not rows:
        return {}
    counts = Counter(r["event_date"] for r in rows)
    rng = np.random.default_rng(CONFIG["seed"])
    indices = rng.integers(0, len(dates), size=(CONFIG["bootstrap_replicates"], len(dates)))
    denominator = np.array([counts[day] for day in dates])[indices].sum(axis=1)
    result = {}
    for model in REFERENCES:
        totals = defaultdict(float)
        for row in rows:
            totals[row["event_date"]] += score(row, "sample_adjusted")[0] - score(row, model)[0]
        observed = sum(totals.values()) / len(rows)
        interval = None
        if len(dates) >= 2:
            samples = np.array([totals[day] for day in dates])[indices].sum(axis=1) / denominator
            interval = np.quantile(samples, [.025, .975]).tolist()
        result[model] = {"candidate_minus_reference_nll": observed,
                         "date_cluster_bootstrap_95_interval": interval,
                         "date_clusters": len(dates), "replicates": CONFIG["bootstrap_replicates"],
                         "seed": CONFIG["seed"], "lower_is_better": True}
    return result


def exposure_group(row):
    n = row["prior_attempts"]
    return "0" if n == 0 else "1-99" if n < 100 else "100-499" if n < 500 else "500+"


def duration_group(row):
    n = row["duration_seconds"]
    return "missing_or_zero" if n is None or n == 0 else "under_60s" if n < 60 else "60s_or_longer"


def grouped(rows, key):
    groups = defaultdict(list)
    for row in rows:
        groups[str(key(row))].append(row)
    return {name: summarize(values) for name, values in sorted(groups.items())}


def synthetic_recovery():
    rng = np.random.default_rng(CONFIG["seed"])
    truth = rng.beta(4, 6, size=8000)
    results = []
    for attempts in (0, 10, 100, 1000):
        landed = rng.binomial(attempts, truth)
        # Known, matching Beta(4,6) prior; independent of real-data k selection.
        estimate = (landed + 4) / (attempts + 10)
        raw = landed / attempts if attempts else None
        results.append({"prior_attempts": attempts, "fighters": len(truth),
                        "mean_bias": float(np.mean(estimate-truth)),
                        "shrink_rmse": float(np.sqrt(np.mean((estimate-truth)**2))),
                        "raw_rmse": float(np.sqrt(np.mean((raw-truth)**2)))
                        if raw is not None else None})
    return {"seed": CONFIG["seed"], "matching_prior": "Beta(4,6)", "results": results,
            "interpretation": "Matching-model arithmetic/recovery check, not MMA validation."}


def evaluate(rows):
    tuning = []
    for strength in CONFIG["strengths"]:
        predictions = predict(rows, strength)
        support = [r for r in predictions if CONFIG["tune_start"] <= r["event_date"]
                   < CONFIG["development_start"] and common_support(r)]
        tuning.append({"strength": strength, **summarize(support)})
    eligible = [r for r in tuning if r["side_bouts"]]
    if not eligible:
        raise ValueError("No common-support tuning observations in 2012-2018.")
    chosen = min(eligible, key=lambda r: (
        r["scores"]["sample_adjusted"]["mean_binomial_nll"], r["strength"]))["strength"]
    predictions = predict(rows, chosen)
    development = [r for r in predictions if r["event_date"] >= CONFIG["development_start"]]
    common = [r for r in development if common_support(r)]
    established = [r for r in common if r["prior_bouts"] >= CONFIG["established_prior_bouts"]
                   and r["prior_attempts"] >= CONFIG["established_prior_attempts"]]
    broader = {model: summarize([r for r in development if r["status"] == "observed"
                                and r[model] is not None], (model,)) for model in MODELS}
    cold = [r for r in development if r["status"] == "observed" and r["prior_attempts"] == 0
            and r["sample_adjusted"] is not None]
    comparison = paired_comparisons(common)
    candidate_nll = summarize(common)["scores"]["sample_adjusted"]["mean_binomial_nll"]
    report = {
        "prototype_version": CONFIG["version"], "config": CONFIG,
        "public_release": False, "opponent_adjusted": False,
        "release_decision": "Offline development prototype; release requirements remain incomplete.",
        "evaluation_label": "Previously inspected historical development years; not a pristine holdout.",
        "estimand": "Significant strikes landed conditional on actual recorded own attempts.",
        "selected_prior_attempts": chosen, "selected_at_grid_boundary": chosen in (
            CONFIG["strengths"][0], CONFIG["strengths"][-1]),
        "tuning_2012_2018": tuning,
        "development_common_support": {**summarize(common), "paired_comparisons": comparison},
        "established_common_support": {**summarize(established),
                                       "paired_comparisons": paired_comparisons(established)},
        "coverage": {"all_development_side_rows": len(development),
                     "statuses": dict(Counter(r["status"] for r in development)),
                     "positive_trial_sides": sum(r["status"] == "observed" for r in development),
                     "no_prior_bouts": sum(r["prior_bouts"] == 0 for r in development),
                     "no_prior_attempts": sum(r["prior_attempts"] == 0 for r in development),
                     "no_last5_attempts": sum(r["last5_attempts"] == 0 for r in development),
                     "no_population_history": sum(r["population_mean"] is None for r in development),
                     "last5_splits_same_day_boundary": sum(
                         r["last5_splits_same_day_boundary"] for r in development),
                     "primary_excluded_positive_trial_sides": sum(
                         r["status"] == "observed" and not common_support(r) for r in development)},
        "broader_method_coverage_not_paired": broader,
        "cold_start_adjusted_only": summarize(cold, ("sample_adjusted",)),
        "clip_sensitivity_same_support": {str(clip): summarize(common, clip=clip)
                                          for clip in (1e-3, 1e-2)},
        "by_year": grouped(common, lambda r: r["event_date"][:4]),
        "by_division": grouped(common, lambda r: r["division"] or "Unknown"),
        "by_source": grouped(common, lambda r: r["source"]),
        "by_duration": grouped(common, duration_group),
        "by_prior_exposure": grouped(common, exposure_group),
        "synthetic_recovery": synthetic_recovery(),
        "candidate_has_lower_development_nll_than_every_reference": bool(common) and all(
            candidate_nll < summarize(common)["scores"][model]["mean_binomial_nll"]
            for model in REFERENCES),
        "limitations": ["No opponent adjustment or future attempt/duration forecast",
                        "Working binomial score does not validate within-bout independence",
                        "Date bootstrap does not resolve repeated-fighter dependence across dates",
                        "No skill or predictive intervals, calibration/reliability gate, or future validation",
                        "Small subgroup results are descriptive; no release thresholds selected",
                        "Earlier pooled rate and selected k uncertainty are not propagated"],
    }
    return predictions, report


def run(adapter, protocol, output):
    if output.exists() or output.resolve().is_relative_to(adapter.resolve()):
        raise ValueError("Use a new output separate from the adapter.")
    rows, manifest, hashes = load_adapter(adapter)
    audit_rows(rows, manifest["before_exclusive"], manifest["database_sha256"])
    hashes.update({str(p.resolve()): digest(p) for p in (protocol, Path(__file__))})
    predictions, report = evaluate(rows)
    report.update(before_exclusive=manifest["before_exclusive"], input_sha256=hashes,
                  versions={"python": platform.python_version(), "numpy": np.__version__})
    body = "".join(json.dumps(r, sort_keys=True, allow_nan=False) + "\n" for r in predictions)
    config_body, protocol_body = encoded(CONFIG), protocol.read_text()
    outputs = {"predictions.jsonl": body, "config.json": config_body, "protocol.md": protocol_body}
    report["output_sha256"] = {name: hashlib.sha256(contents.encode()).hexdigest()
                               for name, contents in outputs.items()}
    verify_hashes(hashes)
    write_artifact(output, {**outputs, "report.json": encoded(report)})
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--adapter", type=Path, required=True)
    parser.add_argument("--protocol", type=Path, default=Path("docs/STRIKING_ACCURACY_PROTOCOL_V1.md"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = run(args.adapter, args.protocol, args.output)
    print(encoded({k: result[k] for k in ("selected_prior_attempts", "development_common_support",
                                         "coverage", "public_release", "release_decision")}))


if __name__ == "__main__":
    main()
