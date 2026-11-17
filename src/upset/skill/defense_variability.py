"""Offline fight-variability study with frozen global defense means."""

import argparse
import json
from collections import Counter
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np
from scipy.stats import betabinom, binom

from upset.skill.defense_validation import augment, cluster_interval, pit_uniforms
from upset.skill.shrink_defense import common_support
from upset.skill.takedown_defense import digest

GRID = (2, 5, 10, 20, 50, 100, 500)
REFERENCES = ("global_binomial", "global_stationary_posterior")
FAMILIES = (*REFERENCES, "global_bout_variability")
SEED = 20261026


def parameters(rows, family, concentration):
    if not rows:
        raise ValueError("Require observations.")
    n = np.asarray([r["attempts"] for r in rows])
    s = np.asarray([r["stopped"] for r in rows])
    mu = np.asarray([r["global25"] for r in rows], dtype=float)
    if (not np.isfinite(mu).all() or np.any((mu <= 0) | (mu >= 1))
            or any(type(r["attempts"]) is not int or type(r["stopped"]) is not int for r in rows)
            or np.any((n < 0) | (s < 0) | (s > n))):
        raise ValueError("Invalid conditional observations or frozen means.")
    if family == "global_binomial":
        return binom(n, mu), n, s, mu
    if family == "global_stationary_posterior":
        a = np.array([r["prior_stopped"] + 25*r["global_baseline"] for r in rows])
        b = np.array([r["prior_attempts"]-r["prior_stopped"] + 25*(1-r["global_baseline"]) for r in rows])
        if np.any(a <= 0) or np.any(b <= 0) or not np.allclose(a/(a+b), mu, rtol=0, atol=1e-14):
            raise ValueError("Stationary posterior does not preserve the frozen mean.")
    elif family == "global_bout_variability":
        if not np.isfinite(concentration) or concentration <= 0:
            raise ValueError("Require positive finite concentration.")
        a, b = mu*concentration, (1-mu)*concentration
    else:
        raise ValueError("Unknown predictive family.")
    return betabinom(n, a, b), n, s, mu


def choose(scores):
    """First listed minimum, with numerical ties below 1e-12 treated as ties."""
    scores = np.asarray(scores)
    if not np.isfinite(scores).all():
        raise ValueError("Nonfinite concentration scores.")
    return int(np.flatnonzero(scores <= scores.min()+1e-12)[0])


def fit_concentration(rows):
    training = [r for r in rows if "2012-01-01" <= r["event_date"] < "2019-01-01" and common_support(r)]
    if not training or not any(r["attempts"] >= 2 for r in training):
        raise ValueError("No informative n>=2 training observations for concentration.")
    losses = np.column_stack([-parameters(training, "global_bout_variability", c)[0].logpmf(
        [r["stopped"] for r in training]) for c in GRID])
    means = losses.mean(axis=0)
    selected_index = choose(means)
    days = sorted({r["event_date"] for r in training})
    totals = np.array([losses[[r["event_date"] == day for r in training]].sum(axis=0) for day in days])
    weights = np.array([sum(r["event_date"] == day for r in training) for day in days])
    rng = np.random.default_rng(SEED)
    indices = rng.integers(0, len(days), size=(1000, len(days)))
    samples = totals[indices].sum(axis=1)/weights[indices].sum(axis=1)[:, None]
    winners = Counter(GRID[choose(scores)] for scores in samples)
    report = {"period": "2012-2018", "training_sides": len(training),
              "concentration_informative_sides_n_ge_2": sum(r["attempts"] >= 2 for r in training),
              "date_clusters": len(days), "grid": list(GRID),
              "mean_predictive_nll": {str(c): float(v) for c, v in zip(GRID, means, strict=True)},
              "selected": GRID[selected_index], "selected_grid_edge": selected_index in (0, len(GRID)-1),
              "date_bootstrap_selection_counts": {str(c): winners[c] for c in GRID},
              "replicates": 1000, "seed": SEED}
    return GRID[selected_index], report


def normalized_rps(dist, n, s):
    if np.any(n <= 0):
        raise ValueError("RPS rate normalization requires positive attempt counts.")
    thresholds = np.arange(int(n.max()))[:, None]
    cdf = dist.cdf(thresholds)
    return (((cdf - (s[None, :] <= thresholds))**2) * (thresholds < n[None, :])).sum(axis=0)/n


def diagnostic(rows, family, concentration, minimum_rows=500):
    dist, n, s, mu = parameters(rows, family, concentration)
    if np.any(n <= 0):
        raise ValueError("Calibration requires positive held-out trials.")
    if not np.allclose(dist.mean(), n*mu, atol=1e-10, rtol=1e-12):
        raise ValueError("Predictive family changed a conditional mean.")
    dates = [r["event_date"] for r in rows]
    nll = -dist.logpmf(s)
    if not np.isfinite(nll).all():
        raise ValueError("Predictive scores must be finite.")
    rps = normalized_rps(dist, n, s)
    left, mass = np.clip(dist.cdf(s-1), 0, 1), dist.pmf(s)
    pit = np.clip(left + pit_uniforms(rows, SEED+1)*mass, 0, 1)
    enough = len(rows) >= minimum_rows and len(set(dates)) >= 20
    levels = {}
    interval_scores = {}
    for level in (.5, .9):
        tail = (1-level)/2
        low, high = dist.ppf(tail), dist.ppf(1-tail)
        inside = (s >= low) & (s <= high)
        score = high-low + 2/(1-level)*(np.maximum(low-s, 0)+np.maximum(s-high, 0))
        central = (pit >= tail) & (pit <= 1-tail)
        band = (.45, .55) if level == .5 else (.87, .93)
        status = "within_band" if band[0] <= central.mean() <= band[1] else "outside_band"
        if not enough:
            status = "inconclusive_thin_group"
        sensitivity = []
        for seed in (SEED+1, SEED+2, SEED+3):
            v = np.clip(left + pit_uniforms(rows, seed)*mass, 0, 1)
            sensitivity.append({"seed": seed, "coverage": float(((v >= tail) & (v <= 1-tail)).mean())})
        levels[str(level)] = {
            "integer_count_coverage": cluster_interval(inside, dates),
            "expected_integer_mass": float((dist.cdf(high)-dist.cdf(low-1)).mean()),
            "mean_integer_width": float((high-low).mean()),
            "mean_interval_score": float(score.mean()),
            "randomized_pit_coverage": cluster_interval(central, dates),
            "diagnostic_band": list(band), "status": status, "seed_sensitivity": sensitivity,
        }
        interval_scores[str(level)] = score
    report = {"family": family, "side_bouts": len(rows), "attempts": int(n.sum()),
              "date_clusters": len(set(dates)), "mean_predictive_nll": float(nll.mean()),
              "mean_normalized_rps": float(rps.mean()),
              "levels": levels, "pit_histogram_10_bins": np.histogram(pit, bins=np.linspace(0, 1, 11))[0].tolist()}
    return report, {"nll": nll, "normalized_rps": rps, "interval_scores": interval_scores}


def cohort_report(rows, concentration, minimum_rows=500):
    if not rows:
        return {"side_bouts": 0, "status": "inconclusive_empty"}
    reports, losses = {}, {}
    for family in FAMILIES:
        reports[family], losses[family] = diagnostic(rows, family, concentration, minimum_rows)
    dates = [r["event_date"] for r in rows]
    comparisons = {}
    for reference in REFERENCES:
        new = losses["global_bout_variability"]
        old = losses[reference]
        comparisons[reference] = {
            key: cluster_interval(new[key]-old[key], dates) for key in ("nll", "normalized_rps")}
        comparisons[reference]["interval_scores"] = {
            level: cluster_interval(new["interval_scores"][level]-old["interval_scores"][level], dates)
            for level in ("0.5", "0.9")}
    enough = len(rows) >= minimum_rows and len(set(dates)) >= 20
    flags = [reference for reference, values in comparisons.items()
             if enough and values["nll"]["mean"] > .05 and values["nll"]["interval_95"][0] > 0]
    return {"side_bouts": len(rows), "date_clusters": len(set(dates)),
            "status": "sized_for_diagnostic" if enough else "inconclusive_thin_group",
            "families": reports, "new_minus_reference": comparisons,
            "material_regression_flags": flags}


def group_label(row, field):
    if field == "year":
        return row["event_date"][:4]
    if field == "era":
        return "2019-2022" if row["event_date"] < "2023-01-01" else "2023+"
    if field == "division":
        return row["division"] or "Unknown"
    if field == "prior_exposure":
        n = row["prior_attempts"]
        return "0" if n == 0 else "1-9" if n < 10 else "10-24" if n < 25 else "25-49" if n < 50 else "50+"
    if field == "actual_attempts":
        n = row["attempts"]
        return "1" if n == 1 else "2-3" if n <= 3 else "4-9" if n < 10 else "10+"
    raise ValueError("Unknown subgroup field.")


def synthetic_recovery():
    rng = np.random.default_rng(SEED)
    count = 8000
    mu = rng.beta(6, 4, count)
    n = rng.integers(1, 21, count)
    q = rng.beta(mu*10, (1-mu)*10)
    s = rng.binomial(n, q)
    rows = [{"global25": float(mu[i]), "attempts": int(n[i]), "stopped": int(s[i]),
             "event_date": ("2013-01-" if i < 4000 else "2020-01-")+str(i % 28 + 1).zfill(2),
             "fight_id": "synthetic:"+str(i), "fighter_id": "synthetic:"+str(i),
             "prior_attempts": 0, "prior_stopped": 0, "global_baseline": float(mu[i]),
             "status": "observed", "raw_career": float(mu[i]), "raw_last5": float(mu[i]), "sample_adjusted": float(mu[i])}
            for i in range(count)]
    selected, training = fit_concentration(rows[:4000])
    heldout, _ = diagnostic(rows[4000:], "global_bout_variability", selected)
    correct = betabinom(n, mu*10, (1-mu)*10)
    expected_var = n*mu*(1-mu)*(1+(n-1)/11)
    moments_match = bool(np.allclose(correct.mean(), n*mu) and np.allclose(correct.var(), expected_var))
    calibrated = all(heldout["levels"][str(level)]["status"] == "within_band" for level in (.5, .9))
    return {"synthetic_bouts": count, "training_bouts": 4000, "heldout_bouts": 4000,
            "true_concentration": 10, "selected_concentration": selected, "training": training,
            "known_mean_and_variance_match": moments_match, "heldout": heldout,
            "numerical_check_passed": selected == 10 and calibrated and moments_match,
            "matching_model_only": True, "skill_interval_constructed": False, "seed": SEED}


def evaluate(rows, progress=print):
    concentration, training = fit_concentration(rows)
    progress("Concentration selected using 2012-2018 only.")
    development = [r for r in rows if r["event_date"] >= "2019-01-01"]
    primary_rows = [r for r in development if common_support(r)]
    positive = [r for r in development if r["status"] == "observed" and r["global25"] is not None]
    established = [r for r in primary_rows if r["prior_bouts"] >= 3 and r["prior_attempts"] >= 10]
    cold = [r for r in positive if r["prior_attempts"] == 0]
    primary = cohort_report(primary_rows, concentration)
    progress("Primary matched-family predictive comparison complete.")
    secondary = {"established": cohort_report(established, concentration),
                 "broader_positive_trials": cohort_report(positive, concentration),
                 "cold_start": cohort_report(cold, concentration)}
    subgroups = {}
    for field in ("year", "era", "division", "prior_exposure", "actual_attempts"):
        # Exposure, including zero-history fighters, is assessed in the broader
        # population. The other slices retain exact primary common support.
        population = positive if field == "prior_exposure" else primary_rows
        subgroups[field] = {}
        for label in sorted({group_label(r, field) for r in population}):
            subset = [r for r in population if group_label(r, field) == label]
            subgroups[field][label] = cohort_report(subset, concentration, minimum_rows=100)
        progress("Predictive subgroup checks complete: "+field)
    synthetic = synthetic_recovery()
    flags = []
    calibration_failures = []
    inconclusive = []
    for field, groups in subgroups.items():
        for name, summary in groups.items():
            identifier = field+":"+name
            flags.extend(identifier+":"+ref for ref in summary["material_regression_flags"])
            if summary["status"] != "sized_for_diagnostic":
                inconclusive.append(identifier)
                continue
            for level, result in summary["families"]["global_bout_variability"]["levels"].items():
                if result["status"] == "outside_band":
                    calibration_failures.append(identifier+":"+level)
    all_scores_better = all(values["nll"]["interval_95"][1] < 0 for values in primary["new_minus_reference"].values())
    interval_score_better = {level: all(values["interval_scores"][level]["interval_95"][1] < 0
                                       for values in primary["new_minus_reference"].values()) for level in ("0.5", "0.9")}
    calibrated = all(r["status"] == "within_band" for r in primary["families"]["global_bout_variability"]["levels"].values())
    return {"study_version": "td_defense_variability_v3", "public_release": False,
            "opponent_adjusted": False, "point_means_changed": False,
            "estimand": "Stopped count conditional on actual opposing attempts, with frozen global defense mean.",
            "training": training, "primary_common_support": primary, "secondary_populations": secondary,
            "subgroups": subgroups, "synthetic_recovery": synthetic,
            "coverage": {"development_side_rows": len(development), "common_support": len(primary_rows),
                         "positive_trial_rows": len(positive), "cold_start_positive_rows": len(cold),
                         "development_status_counts": dict(Counter(r["status"] for r in development))},
            "decision": {"predictive_nll_evidence_against_both_references": all_scores_better,
                         "interval_score_evidence_against_both_references": interval_score_better,
                         "overall_calibration_bands_passed": calibrated,
                         "material_regression_flags": flags, "subgroup_calibration_failures": calibration_failures,
                         "inconclusive_subgroups": inconclusive, "synthetic_check_passed": synthetic["numerical_check_passed"],
                         "public_release": False,
                         "reason": "Development iteration only; no protected future evaluation or completed skill-layer release gates."},
            "limitations": ["Mean and concentration uncertainty not propagated", "Concentration is not a measured physical correlation",
                            "Conditional on observed attempts; no future attempt-count forecast", "No fighter skill intervals",
                            "Date bootstrap preserves event dependence, not all longitudinal fighter dependence",
                            "Repeated development inspection; no untouched holdout"]}


def run(adapter, validation, protocol, output):
    if output.exists() or any(output.resolve().is_relative_to(p.resolve()) for p in (adapter, validation)):
        raise ValueError("Use a new immutable output directory separate from inputs.")
    am = json.loads((adapter / "manifest.json").read_text())
    vm = json.loads((validation / "report.json").read_text())
    paths = [adapter / "manifest.json", adapter / "sides.jsonl", validation / "report.json",
             validation / "predictions.jsonl", protocol, Path(__file__)]
    hashes = {str(p): digest(p) for p in paths}
    if hashes[str(adapter / "sides.jsonl")] != am["output_sha256"]["sides.jsonl"] or hashes[str(validation / "predictions.jsonl")] != vm["output_sha256"]["predictions.jsonl"]:
        raise ValueError("An adapter or v2 prediction hash differs.")
    if am["before_exclusive"] != vm["before_exclusive"]:
        raise ValueError("Input cutoff contracts differ.")
    for path, h in vm["input_sha256"].items():
        if digest(Path(path)) != h:
            raise ValueError("A frozen v2 input changed.")
        hashes[path] = h
    sides = [json.loads(line) for line in (adapter / "sides.jsonl").read_text().splitlines()]
    rows = [json.loads(line) for line in (validation / "predictions.jsonl").read_text().splitlines()]
    if augment(sides) != rows:
        raise ValueError("Every frozen v2 prediction must reproduce exactly.")
    print("All frozen v2 predictions reproduced; mean model unchanged.", flush=True)
    report = evaluate(rows, lambda message: print(message, flush=True))
    if report["primary_common_support"]["side_bouts"] != vm["primary_common_support"]["side_bouts"]:
        raise ValueError("Primary comparison lost common support.")
    concentration = report["training"]["selected"]
    report.update(input_sha256=hashes, before_exclusive=am["before_exclusive"],
                  reproduced_v2_predictions=len(rows), runtime_versions={"numpy": np.__version__, "scipy": __import__("scipy").__version__})
    output.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=output.parent, prefix=".upset-defense-variability-") as temporary:
        folder = Path(temporary) / "study"
        folder.mkdir()
        path = folder / "predictions.jsonl"
        extended = []
        for row in rows:
            mu, n = row["global25"], row["attempts"]
            eligible = mu is not None and 0 < mu < 1
            item = {**row, "bout_concentration": concentration,
                    "bout_beta_a": mu*concentration if eligible else None,
                    "bout_beta_b": (1-mu)*concentration if eligible else None,
                    "conditional_count_mean": n*mu if eligible and n is not None else None,
                    "conditional_count_variance": n*mu*(1-mu)*(1+(n-1)/(concentration+1)) if eligible and n is not None else None}
            extended.append(item)
        path.write_text("".join(json.dumps(r, sort_keys=True, allow_nan=False)+"\n" for r in extended))
        report["output_sha256"] = {"predictions.jsonl": digest(path)}
        if any(digest(Path(p)) != h for p, h in hashes.items()):
            raise ValueError("An input changed during the study.")
        (folder / "report.json").write_text(json.dumps(report, indent=2, sort_keys=True, allow_nan=False)+"\n")
        folder.rename(output)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--adapter", type=Path, required=True)
    parser.add_argument("--validation", type=Path, required=True)
    parser.add_argument("--protocol", type=Path, default=Path("docs/TAKEDOWN_DEFENSE_VARIABILITY_PROTOCOL_V3.md"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = run(args.adapter, args.validation, args.protocol, args.output)
    print(json.dumps({k: report[k] for k in ("training", "coverage", "decision")}, indent=2))


if __name__ == "__main__":
    main()
