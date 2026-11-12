"""Offline v2 smoothing, predictive-calibration and repeatability diagnostics."""

import argparse
import hashlib
import json
from collections import Counter, defaultdict, deque
from itertools import groupby
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np
from scipy.stats import beta, betabinom, binom, rankdata

from upset.skill.shrink_defense import common_support, predict
from upset.skill.takedown_defense import digest

SIMPLE = ("jeffreys_career", "laplace_career", "jeffreys_last5", "global25", "pool_only")
MODELS = ("raw_career", "raw_last5", *SIMPLE, "sample_adjusted")
POSTERIORS = ("jeffreys_career", "laplace_career", "jeffreys_last5", "sample_adjusted")
SEED = 20261026


def augment(sides):
    """Keep v1 means fixed and independently reconstruct integer sufficient counts."""
    base = predict(sides, 25)
    counts = defaultdict(lambda: [0, 0])
    recent = defaultdict(lambda: deque(maxlen=5))
    global_counts = [0, 0]
    source = {(r["fight_id"], r["fighter_id"]): r for r in sides}
    result = []
    for _, group in groupby(base, key=lambda r: r["event_date"]):
        batch = list(group)
        for row in batch:
            uid = row["fighter_id"]
            s, n = counts[uid]
            ls = sum(v for v, _ in recent[uid])
            ln = sum(v for _, v in recent[uid])
            if n != row["prior_attempts"] or ln != row["last5_attempts"]:
                raise ValueError("Reconstructed prior exposure differs from v1.")
            baseline = global_counts[0]/global_counts[1] if global_counts[1] else None
            result.append({**row, "prior_stopped": s, "last5_stopped": ls,
                           "global_baseline": baseline,
                           "jeffreys_career": (s+.5)/(n+1),
                           "laplace_career": (s+1)/(n+2),
                           "jeffreys_last5": (ls+.5)/(ln+1),
                           "global25": (s+25*baseline)/(n+25) if baseline is not None else None,
                           "pool_only": row["baseline"]})
        for row in batch:
            item = source[row["fight_id"], row["fighter_id"]]
            if item["status"] not in ("observed", "zero_attempts"):
                recent[row["fighter_id"]].append((0, 0))
                continue
            s, n = item["takedowns_stopped"], item["opponent_takedown_attempts"]
            counts[row["fighter_id"]][0] += s
            counts[row["fighter_id"]][1] += n
            recent[row["fighter_id"]].append((s, n))
            global_counts[0] += s
            global_counts[1] += n
    return result


def posterior(row, model):
    s, n = row["prior_stopped"], row["prior_attempts"]
    if model == "jeffreys_career":
        a, b = s+.5, n-s+.5
    elif model == "laplace_career":
        a, b = s+1, n-s+1
    elif model == "jeffreys_last5":
        s, n = row["last5_stopped"], row["last5_attempts"]
        a, b = s+.5, n-s+.5
    elif model == "sample_adjusted" and row["baseline"] is not None:
        a, b = s+25*row["baseline"], n-s+25*(1-row["baseline"])
    else:
        return None
    return (a, b) if a > 0 and b > 0 else None


def point_losses(rows, model, clip=1e-6):
    s = np.array([r["stopped"] for r in rows])
    n = np.array([r["attempts"] for r in rows])
    p = np.clip([r[model] for r in rows], clip, 1-clip)
    nll = -binom.logpmf(s, n, p)
    cross = -s*np.log(p) - (n-s)*np.log1p(-p)
    brier = s*(1-p)**2 + (n-s)*p**2
    return nll, cross, brier


def cluster_interval(values, dates, replicates=1000):
    values = np.asarray(values, dtype=float)
    if not len(values):
        return None
    grouped = defaultdict(list)
    for day, value in zip(dates, values, strict=True):
        grouped[day].append(float(value))
    groups = [grouped[d] for d in sorted(grouped)]
    totals = np.array([sum(v) for v in groups])
    weights = np.array([len(v) for v in groups])
    rng = np.random.default_rng(SEED)
    idx = rng.integers(0, len(groups), size=(replicates, len(groups)))
    draws = totals[idx].sum(axis=1)/weights[idx].sum(axis=1)
    return {"mean": float(values.mean()), "interval_95": np.quantile(draws, [.025, .975]).tolist(),
            "date_clusters": len(groups), "replicates": replicates, "seed": SEED}


def point_summary(rows, challenger):
    if not rows:
        return {"side_bouts": 0, "status": "inconclusive"}
    dates = [r["event_date"] for r in rows]
    n = sum(r["attempts"] for r in rows)
    scores = {}
    for model in MODELS:
        loss, cross, brier = point_losses(rows, model)
        scores[model] = {"mean_binomial_nll": float(loss.mean()),
                         "attempt_weighted_cross_entropy": float(cross.sum()/n),
                         "attempt_brier": float(brier.sum()/n)}
    comparisons = {}
    for model in ("raw_career", "raw_last5", challenger):
        values = point_losses(rows, "sample_adjusted")[0] - point_losses(rows, model)[0]
        comparisons[model] = cluster_interval(values, dates)
    enough = len(rows) >= 100 and len(set(dates)) >= 20
    comparison = comparisons[challenger]
    regression = (enough and comparison["mean"] > .05 and comparison["interval_95"][0] > 0)
    return {"side_bouts": len(rows), "attempts": n, "date_clusters": len(set(dates)),
            "scores": scores, "adjusted_minus_reference": comparisons,
            "subgroup_status": "sized_for_diagnostic" if enough else "inconclusive_thin_group",
            "material_regression_flag": regression}


def pit_uniforms(rows, seed):
    return np.array([int.from_bytes(hashlib.sha256(
        f"{seed}:{r['fight_id']}:{r['fighter_id']}".encode()).digest()[:8], "big")/2**64 for r in rows])


def distribution_arrays(rows, model, family):
    n = np.array([r["attempts"] for r in rows])
    s = np.array([r["stopped"] for r in rows])
    if family == "binomial":
        p = np.clip([r[model] for r in rows], 1e-6, 1-1e-6)
        return binom(n, p), n, s
    parameters = [posterior(r, model) for r in rows]
    if any(p is None for p in parameters):
        raise ValueError("Improper or unavailable beta prior in calibration cohort.")
    a, b = np.asarray(parameters).T
    return betabinom(n, a, b), n, s


def calibration(rows, model, family):
    dist, _n, s = distribution_arrays(rows, model, family)
    left = np.clip(dist.cdf(s-1), 0, 1)
    mass = np.exp(dist.logpmf(s))
    pit = np.clip(left + pit_uniforms(rows, SEED+1)*mass, 0, 1)
    dates = [r["event_date"] for r in rows]
    levels = {}
    enough = len(rows) >= 100 and len(set(dates)) >= 20
    for level in (.5, .9):
        tail = (1-level)/2
        lo, hi = dist.ppf(tail), dist.ppf(1-tail)
        included = (s >= lo) & (s <= hi)
        expected = dist.cdf(hi) - dist.cdf(lo-1)
        central = (pit >= tail) & (pit <= 1-tail)
        bounds = (.45, .55) if level == .5 else (.87, .93)
        observed = float(central.mean())
        sensitivity = []
        for seed in (SEED+1, SEED+2, SEED+3):
            v = np.clip(left + pit_uniforms(rows, seed)*mass, 0, 1)
            sensitivity.append({"seed": seed, "coverage": float(((v >= tail) & (v <= 1-tail)).mean())})
        levels[str(level)] = {"integer_count_coverage": cluster_interval(included, dates),
                              "expected_integer_mass": float(expected.mean()),
                              "mean_integer_width": float((hi-lo).mean()),
                              "randomized_pit_coverage": cluster_interval(central, dates),
                              "diagnostic_band": list(bounds),
                              "status": ("within_band" if bounds[0] <= observed <= bounds[1] else "outside_band") if enough else "inconclusive_thin_group",
                              "seed_sensitivity": sensitivity}
    return {"side_bouts": len(rows), "family": family, "model": model,
            "mean_predictive_nll": float(-dist.logpmf(s).mean()),
            "pit_histogram_10_bins": np.histogram(pit, bins=np.linspace(0, 1, 11))[0].tolist(),
            "levels": levels}


def correlation(x, y, ranked=False):
    x, y = np.asarray(x), np.asarray(y)
    if len(x) < 3 or np.ptp(x) == 0 or np.ptp(y) == 0:
        return None
    if ranked:
        x, y = rankdata(x), rankdata(y)
    return float(np.corrcoef(x, y)[0, 1])


def repeatability_summary(pairs):
    if len(pairs) < 3:
        return {"fighters": len(pairs), "status": "inconclusive"}
    x, y = np.array([r["first_rate"] for r in pairs]), np.array([r["second_rate"] for r in pairs])
    result = {"fighters": len(pairs), "first_attempts": sum(r["first_attempts"] for r in pairs),
              "second_attempts": sum(r["second_attempts"] for r in pairs)}
    rng = np.random.default_rng(SEED)
    indices = rng.integers(0, len(pairs), size=(500, len(pairs)))
    for name, ranked in (("pearson", False), ("spearman", True)):
        values = [correlation(x[idx], y[idx], ranked) for idx in indices]
        finite = [v for v in values if v is not None and np.isfinite(v)]
        result[name] = {"correlation": correlation(x, y, ranked),
                        "fighter_bootstrap_95_interval": np.quantile(finite, [.025, .975]).tolist() if finite else None,
                        "finite_replicates": len(finite)}
    return result


def reliability(sides):
    fighters = defaultdict(list)
    for row in sorted(sides, key=lambda r: (r["event_date"], r["fight_id"])):
        fighters[row["fighter_id"]].append(row)
    output = {}
    for half in (2, 3, 5, 8, 10):
        attrition = Counter()
        pairs = []
        for uid, history in fighters.items():
            if len(history) < 2*half:
                attrition["fewer_than_twice_half_bouts"] += 1
                continue
            first, second = history[:half], history[half:2*half]
            if first[-1]["event_date"] == second[0]["event_date"]:
                attrition["same_date_split_boundary"] += 1
                continue
            counts = []
            for block in (first, second):
                available = [r for r in block if r["status"] in ("observed", "zero_attempts")]
                counts.append((sum(r["takedowns_stopped"] for r in available), sum(r["opponent_takedown_attempts"] for r in available)))
            if any(n == 0 for s, n in counts):
                attrition["zero_attempts_in_a_half"] += 1
                continue
            (s1, n1), (s2, n2) = counts
            divisions = {r["division"] for r in first+second}
            pairs.append({"fighter_id": uid, "first_rate": s1/n1, "second_rate": s2/n2,
                          "first_attempts": n1, "second_attempts": n2,
                          "stable_division": next(iter(divisions)) if len(divisions)==1 and None not in divisions else None})
        primary = [r for r in pairs if min(r["first_attempts"], r["second_attempts"]) >= 10]
        attrition["below_ten_attempts_in_a_half"] = len(pairs)-len(primary)
        slices = {d: repeatability_summary([r for r in primary if r["stable_division"] == d])
                  for d in sorted({r["stable_division"] for r in primary if r["stable_division"]})
                  if sum(r["stable_division"] == d for r in primary) >= 50}
        output[str(half)] = {"recorded_bouts_per_half": half, "all_fighters": len(fighters),
                             "attrition": dict(attrition), "primary_ten_attempts_per_half": repeatability_summary(primary),
                             "positive_attempts_per_half": repeatability_summary(pairs),
                             "stable_division_slices_50_plus": slices}
    return output


def synthetic_recovery():
    rng = np.random.default_rng(SEED)
    size = 8000
    truth = rng.beta(6, 4, size)
    prior_n = rng.choice([0, 5, 20, 100], size=size)
    prior_s = rng.binomial(prior_n, truth)
    a, b = 6+prior_s, 4+prior_n-prior_s
    mean = a/(a+b)
    lo, hi = beta.ppf(.05, a, b), beta.ppf(.95, a, b)
    future_n = rng.integers(1, 21, size=size)
    future_s = rng.binomial(future_n, truth)
    dist = betabinom(future_n, a, b)
    lower, upper = dist.ppf(.05), dist.ppf(.95)
    pit = dist.cdf(future_s-1) + rng.uniform(size=size)*dist.pmf(future_s)
    def summary(mask):
        return {"fighters": int(mask.sum()), "mean_bias": float((mean[mask]-truth[mask]).mean()),
                "mean_rmse": float(np.sqrt(np.mean((mean[mask]-truth[mask])**2))),
                "latent_rate_interval_90_coverage": float(((truth >= lo) & (truth <= hi))[mask].mean()),
                "integer_predictive_90_coverage": float(((future_s >= lower) & (future_s <= upper))[mask].mean()),
                "expected_integer_predictive_mass": float((dist.cdf(upper)-dist.cdf(lower-1))[mask].mean()),
                "randomized_predictive_90_coverage": float(((pit >= .05) & (pit <= .95))[mask].mean())}
    result = {"overall": summary(np.ones(size, dtype=bool)),
              "by_prior_attempts": {str(n): summary(prior_n == n) for n in (0, 5, 20, 100)},
              "seed": SEED, "matching_model_only": True}
    check = result["overall"]
    result["numerical_check_passed"] = (abs(check["mean_bias"]) < .01
        and .87 <= check["latent_rate_interval_90_coverage"] <= .93
        and .87 <= check["randomized_predictive_90_coverage"] <= .93)
    return result


def evaluate(sides, progress=print):
    rows = augment(sides)
    tuning = [r for r in rows if "2012-01-01" <= r["event_date"] < "2019-01-01" and common_support(r)]
    if not tuning:
        raise ValueError("Missing common-support tuning observations.")
    tuning_scores = {m: float(point_losses(tuning, m)[0].mean()) for m in SIMPLE}
    challenger = min(SIMPLE, key=lambda m: tuning_scores[m])
    progress("Simple challenger selected using 2012-2018 only.")
    development = [r for r in rows if r["event_date"] >= "2019-01-01"]
    common = [r for r in development if common_support(r)]
    established = [r for r in common if r["prior_bouts"] >= 3 and r["prior_attempts"] >= 10]
    nonboundary = [r for r in common if 0 < r["raw_career"] < 1 and 0 < r["raw_last5"] < 1]
    subgroups = {}
    for field, labels in (
        ("year", sorted({r["event_date"][:4] for r in common})),
        ("era", ("2019-2022", "2023+")),
        ("division", sorted({r["division"] or "Unknown" for r in common})),
        ("exposure", ("1-9", "10-24", "25-49", "50+")),
    ):
        def label(row, field=field):
            if field == "year":
                return row["event_date"][:4]
            if field == "era":
                return "2019-2022" if row["event_date"] < "2023-01-01" else "2023+"
            if field == "division":
                return row["division"] or "Unknown"
            return "1-9" if row["prior_attempts"] < 10 else "10-24" if row["prior_attempts"] < 25 else "25-49" if row["prior_attempts"] < 50 else "50+"
        subgroups[field] = {name: point_summary([r for r in common if label(r) == name], challenger) for name in labels}
    progress("Point scores and date-cluster subgroup comparisons complete.")
    calibration_report = {}
    for model in MODELS:
        calibration_report["binomial:"+model] = calibration(common, model, "binomial")
    for model in POSTERIORS:
        calibration_report["beta_binomial:"+model] = calibration(common, model, "beta_binomial")
        progress("Predictive interval checks: "+model)
    primary_calibration = calibration_report["beta_binomial:sample_adjusted"]
    cal_subgroups = {}
    for field in ("year", "era", "division"):
        cal_subgroups[field] = {}
        for name, summary in subgroups[field].items():
            if summary["side_bouts"] < 100 or summary["date_clusters"] < 20:
                cal_subgroups[field][name] = {"status": "inconclusive_thin_group", "side_bouts": summary["side_bouts"]}
                continue
            subset = [r for r in common if (r["event_date"][:4] if field == "year" else ("2019-2022" if r["event_date"] < "2023-01-01" else "2023+") if field == "era" else r["division"] or "Unknown") == name]
            cal_subgroups[field][name] = calibration(subset, "sample_adjusted", "beta_binomial")
    positive = [r for r in development if r["status"] == "observed" and posterior(r, "sample_adjusted") is not None]
    broader = calibration(positive, "sample_adjusted", "beta_binomial")
    progress("Calibration strata complete; checking split-half reliability.")
    reliability_report = reliability(sides)
    progress("Split-half reliability complete; running matching-model synthetic recovery.")
    synthetic = synthetic_recovery()
    primary = point_summary(common, challenger)
    regression_flags = [field+":"+name for field, groups in subgroups.items() for name, r in groups.items() if r["material_regression_flag"]]
    calibrated = all(primary_calibration["levels"][str(level)]["status"] == "within_band" for level in (.5, .9))
    score_evidence = primary["adjusted_minus_reference"][challenger]["interval_95"][1] < 0
    return rows, {"study_version": "td_defense_validation_v2", "public_release": False,
        "opponent_adjusted": False, "evaluation_label": "Previously inspected development data; not an untouched holdout.",
        "tuning_simple_challengers": {"period": "2012-2018", "side_bouts": len(tuning), "nll": tuning_scores, "selected": challenger},
        "primary_common_support": primary, "established_common_support": point_summary(established, challenger),
        "raw_nonboundary_common_support": point_summary(nonboundary, challenger), "subgroups": subgroups,
        "raw_clip_sensitivity": {str(eps): {m: float(point_losses(common, m, eps)[0].mean()) for m in ("raw_career", "raw_last5")} for eps in (1e-6, 1e-3, 1e-2)},
        "calibration_primary": calibration_report, "calibration_subgroups_sample_adjusted": cal_subgroups,
        "broader_positive_trial_calibration": broader, "reliability": reliability_report,
        "synthetic_recovery": synthetic,
        "coverage": {"all_development_side_rows": len(development), "positive_trial_rows": len(positive),
                     "common_support_rows": len(common), "status_counts": dict(Counter(r["status"] for r in development)),
                     "cold_start_positive_rows": sum(r["prior_attempts"] == 0 for r in positive)},
        "decision": {"point_score_evidence_beyond_selected_simple_baseline": score_evidence,
                     "material_point_regression_flags": regression_flags,
                     "posterior_predictive_diagnostic_bands_passed": calibrated,
                     "synthetic_matching_model_check_passed": synthetic["numerical_check_passed"],
                     "minimum_history_threshold": "Not established; report descriptive repeatability and attrition.",
                     "public_release": False,
                     "reason": "Development diagnostics only. No protected future evaluation; all handoff gates are not satisfied."}}


def run(adapter, prototype, protocol, output):
    if output.exists() or any(output.resolve().is_relative_to(p.resolve()) for p in (adapter, prototype)):
        raise ValueError("Use a new, separate immutable output directory.")
    am = json.loads((adapter / "manifest.json").read_text())
    previous = json.loads((prototype / "report.json").read_text())
    paths = [adapter / "manifest.json", adapter / "sides.jsonl", prototype / "report.json",
             prototype / "predictions.jsonl", protocol, Path(__file__)]
    hashes = {str(p): digest(p) for p in paths}
    if hashes[str(adapter / "sides.jsonl")] != am["output_sha256"]["sides.jsonl"] or hashes[str(prototype / "predictions.jsonl")] != previous["output_sha256"]["predictions.jsonl"]:
        raise ValueError("Adapter or frozen prototype output hash differs.")
    if previous["selected_prior_attempts"] != 25 or previous["before_exclusive"] != am["before_exclusive"]:
        raise ValueError("The frozen prototype contract differs.")
    for path, h in previous["input_sha256"].items():
        if digest(Path(path)) != h:
            raise ValueError("A frozen v1 input changed.")
        hashes[path] = h
    sides = [json.loads(line) for line in (adapter / "sides.jsonl").read_text().splitlines()]
    frozen = [json.loads(line) for line in (prototype / "predictions.jsonl").read_text().splitlines()]
    if predict(sides, 25) != frozen:
        raise ValueError("Independent rerun did not reproduce every frozen v1 prediction.")
    print("Every frozen v1 prediction reproduced.", flush=True)
    predictions, report = evaluate(sides, lambda message: print(message, flush=True))
    report.update(input_sha256=hashes, before_exclusive=am["before_exclusive"], reproduced_v1_predictions=len(frozen),
                  runtime_versions={"numpy": np.__version__, "scipy": __import__("scipy").__version__})
    output.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=output.parent, prefix=".upset-defense-validation-") as temporary:
        folder = Path(temporary) / "validation"
        folder.mkdir()
        path = folder / "predictions.jsonl"
        path.write_text("".join(json.dumps(r, sort_keys=True, allow_nan=False)+"\n" for r in predictions))
        report["output_sha256"] = {"predictions.jsonl": digest(path)}
        if any(digest(Path(p)) != h for p, h in hashes.items()):
            raise ValueError("A study input changed during validation.")
        (folder / "report.json").write_text(json.dumps(report, indent=2, sort_keys=True, allow_nan=False)+"\n")
        folder.rename(output)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--adapter", type=Path, required=True)
    parser.add_argument("--prototype", type=Path, required=True)
    parser.add_argument("--protocol", type=Path, default=Path("docs/TAKEDOWN_DEFENSE_VALIDATION_PROTOCOL_V2.md"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = run(args.adapter, args.prototype, args.protocol, args.output)
    print(json.dumps({k: report[k] for k in ("tuning_simple_challengers", "decision", "coverage")}, indent=2))


if __name__ == "__main__":
    main()
