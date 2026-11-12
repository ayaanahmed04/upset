"""Offline v4 conditional variance scaling; all defense means remain frozen."""

import argparse
import json
from collections import Counter
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np
from scipy.stats import betabinom

from upset.skill.defense_validation import augment, cluster_interval, pit_uniforms
from upset.skill.defense_variability import (
    FAMILIES as REFERENCES,
)
from upset.skill.defense_variability import (
    choose,
    group_label,
    normalized_rps,
)
from upset.skill.defense_variability import (
    diagnostic as reference_diagnostic,
)
from upset.skill.defense_variability import (
    parameters as reference_parameters,
)
from upset.skill.shrink_defense import common_support
from upset.skill.takedown_defense import digest

CONCENTRATIONS = (2, 5, 10, 20, 50, 100)
EXPONENTS = (0., .5, 1.)
CANDIDATES = tuple((c, g) for g in EXPONENTS for c in CONCENTRATIONS)
MODEL = "attempt_scaled_variability"
SEED = 20261026


def concentration_at_attempts(n, c, gamma):
    n = np.asarray(n)
    if (not np.isfinite(c) or c <= 0 or gamma not in EXPONENTS
            or not np.isfinite(n).all() or np.any(n < 0)):
        raise ValueError("Invalid concentration, exponent or attempts.")
    return c*(np.maximum(n, 1)/5.)**gamma


def parameters(rows, c, gamma):
    _, n, s, mu = reference_parameters(rows, "global_binomial", 5)
    kappa = concentration_at_attempts(n, c, gamma)
    return betabinom(n, mu*kappa, (1-mu)*kappa), n, s, mu, kappa


def candidate_name(c, gamma):
    return f"c={c},gamma={gamma:g}"


def fit_scaling(rows):
    training = [r for r in rows if "2012-01-01" <= r["event_date"] < "2019-01-01" and common_support(r)]
    if not training or not any(r["attempts"] >= 2 for r in training):
        raise ValueError("No informative n>=2 training observations.")
    stopped = np.array([r["stopped"] for r in training])
    losses = np.column_stack([-parameters(training, c, g)[0].logpmf(stopped) for c, g in CANDIDATES])
    scores = losses.mean(axis=0)
    selected_index = choose(scores)
    c, gamma = CANDIDATES[selected_index]
    days = sorted({r["event_date"] for r in training})
    totals = np.array([losses[[r["event_date"] == day for r in training]].sum(axis=0) for day in days])
    weights = np.array([sum(r["event_date"] == day for r in training) for day in days])
    rng = np.random.default_rng(SEED)
    indices = rng.integers(0, len(days), size=(1000, len(days)))
    samples = totals[indices].sum(axis=1)/weights[indices].sum(axis=1)[:, None]
    selections = Counter(choose(values) for values in samples)
    report = {"period": "2012-2018", "training_sides": len(training), "date_clusters": len(days),
              "concentration_informative_sides_n_ge_2": sum(r["attempts"] >= 2 for r in training),
              "anchor_attempts": 5, "selected_c": c, "selected_gamma": gamma,
              "concentration_grid_edge": c in (CONCENTRATIONS[0], CONCENTRATIONS[-1]),
              "exponent_boundary": gamma in (EXPONENTS[0], EXPONENTS[-1]),
              "candidates": [{"c": cc, "gamma": gg, "mean_predictive_nll": float(value),
                              "bootstrap_selections": selections[i]}
                             for i, ((cc, gg), value) in enumerate(zip(CANDIDATES, scores, strict=True))],
              "replicates": 1000, "seed": SEED}
    return (c, gamma), report


def diagnostic(rows, c, gamma, minimum_rows=500):
    # Match v3 diagnostics exactly; only the concentration law changes.
    dist, n, s, mu, _ = parameters(rows, c, gamma)
    if np.any(n <= 0):
        raise ValueError("Calibration requires positive held-out trials.")
    if not np.allclose(dist.mean(), n*mu, atol=1e-10, rtol=1e-12):
        raise ValueError("Attempt scaling changed a frozen count mean.")
    dates = [r["event_date"] for r in rows]
    nll = -dist.logpmf(s)
    if not np.isfinite(nll).all():
        raise ValueError("Predictive scores must remain finite.")
    rps = normalized_rps(dist, n, s)
    left, mass = np.clip(dist.cdf(s-1), 0, 1), dist.pmf(s)
    pit = np.clip(left + pit_uniforms(rows, SEED+1)*mass, 0, 1)
    enough = len(rows) >= minimum_rows and len(set(dates)) >= 20
    levels, interval_scores = {}, {}
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
        levels[str(level)] = {"integer_count_coverage": cluster_interval(inside, dates),
                              "expected_integer_mass": float((dist.cdf(high)-dist.cdf(low-1)).mean()),
                              "mean_integer_width": float((high-low).mean()),
                              "mean_interval_score": float(score.mean()),
                              "randomized_pit_coverage": cluster_interval(central, dates),
                              "diagnostic_band": list(band), "status": status, "seed_sensitivity": sensitivity}
        interval_scores[str(level)] = score
    return {"family": MODEL, "side_bouts": len(rows), "attempts": int(n.sum()),
            "date_clusters": len(set(dates)), "mean_predictive_nll": float(nll.mean()),
            "mean_normalized_rps": float(rps.mean()), "levels": levels,
            "pit_histogram_10_bins": np.histogram(pit, bins=np.linspace(0, 1, 11))[0].tolist()}, {
                "nll": nll, "normalized_rps": rps, "interval_scores": interval_scores}


def cohort_report(rows, c, gamma, minimum_rows=500):
    if not rows:
        return {"side_bouts": 0, "status": "inconclusive_empty"}
    reports, losses = {}, {}
    for family in REFERENCES:
        reports[family], losses[family] = reference_diagnostic(rows, family, 5, minimum_rows)
    reports[MODEL], losses[MODEL] = diagnostic(rows, c, gamma, minimum_rows)
    dates = [r["event_date"] for r in rows]
    comparisons = {}
    for reference in REFERENCES:
        new, old = losses[MODEL], losses[reference]
        comparisons[reference] = {key: cluster_interval(new[key]-old[key], dates) for key in ("nll", "normalized_rps")}
        comparisons[reference]["interval_scores"] = {
            level: cluster_interval(new["interval_scores"][level]-old["interval_scores"][level], dates)
            for level in ("0.5", "0.9")}
    enough = len(rows) >= minimum_rows and len(set(dates)) >= 20
    flags = [reference for reference, values in comparisons.items()
             if enough and values["nll"]["mean"] > .05 and values["nll"]["interval_95"][0] > 0]
    return {"side_bouts": len(rows), "date_clusters": len(set(dates)),
            "status": "sized_for_diagnostic" if enough else "inconclusive_thin_group",
            "families": reports, "new_minus_reference": comparisons, "material_regression_flags": flags}


def synthetic_recovery():
    rng = np.random.default_rng(SEED)
    count = 8000
    mu = rng.beta(6, 4, count)
    n = rng.integers(1, 31, count)
    kappa = concentration_at_attempts(n, 5, 1.)
    q = rng.beta(mu*kappa, (1-mu)*kappa)
    s = rng.binomial(n, q)
    rows = [{"global25": float(mu[i]), "attempts": int(n[i]), "stopped": int(s[i]),
             "event_date": ("2013-01-" if i < 4000 else "2020-01-")+str(i % 28+1).zfill(2),
             "fight_id": "synthetic:"+str(i), "fighter_id": "synthetic:"+str(i),
             "prior_attempts": 0, "prior_stopped": 0, "global_baseline": float(mu[i]),
             "status": "observed", "raw_career": float(mu[i]), "raw_last5": float(mu[i]), "sample_adjusted": float(mu[i])}
            for i in range(count)]
    (c, gamma), training = fit_scaling(rows[:4000])
    heldout, _ = diagnostic(rows[4000:], c, gamma)
    true = betabinom(n, mu*kappa, (1-mu)*kappa)
    moments = bool(np.allclose(true.mean(), n*mu) and np.allclose(true.var(), n*mu*(1-mu)*(1+(n-1)/(kappa+1))))
    calibrated = all(heldout["levels"][str(level)]["status"] == "within_band" for level in (.5, .9))
    return {"synthetic_bouts": count, "training_bouts": 4000, "heldout_bouts": 4000,
            "true_c": 5, "true_gamma": 1., "selected_c": c, "selected_gamma": gamma,
            "training": training, "heldout": heldout, "known_mean_and_variance_match": moments,
            "numerical_check_passed": c == 5 and gamma == 1. and moments and calibrated,
            "matching_model_only": True, "skill_interval_constructed": False, "seed": SEED}


def evaluate(rows, progress=print):
    (c, gamma), training = fit_scaling(rows)
    progress("Scaling parameters selected using 2012-2018 only.")
    development = [r for r in rows if r["event_date"] >= "2019-01-01"]
    primary_rows = [r for r in development if common_support(r)]
    positive = [r for r in development if r["status"] == "observed" and r["global25"] is not None]
    established = [r for r in primary_rows if r["prior_bouts"] >= 3 and r["prior_attempts"] >= 10]
    cold = [r for r in positive if r["prior_attempts"] == 0]
    primary = cohort_report(primary_rows, c, gamma)
    progress("Primary comparison against frozen v3 complete.")
    secondary = {"established": cohort_report(established, c, gamma),
                 "broader_positive_trials": cohort_report(positive, c, gamma),
                 "cold_start": cohort_report(cold, c, gamma)}
    subgroups = {}
    for field in ("year", "era", "division", "prior_exposure", "actual_attempts"):
        population = positive if field == "prior_exposure" else primary_rows
        subgroups[field] = {label: cohort_report([r for r in population if group_label(r, field) == label], c, gamma, 100)
                            for label in sorted({group_label(r, field) for r in population})}
        progress("Attempt-scaling subgroup checks complete: "+field)
    synthetic = synthetic_recovery()
    regression_flags, failures, inconclusive = [], [], []
    for field, groups in subgroups.items():
        for name, summary in groups.items():
            identifier = field+":"+name
            regression_flags.extend(identifier+":"+ref for ref in summary["material_regression_flags"])
            if summary["status"] != "sized_for_diagnostic":
                inconclusive.append(identifier)
                continue
            failures.extend(identifier+":"+level for level, result in summary["families"][MODEL]["levels"].items()
                            if result["status"] == "outside_band")
    calibration = all(g["status"] == "within_band" for g in primary["families"][MODEL]["levels"].values())
    return {"study_version": "td_defense_attempt_scaling_v4", "public_release": False,
            "opponent_adjusted": False, "point_means_changed": False,
            "estimand": "Stopped count conditional on actual opposing attempts, frozen global defense mean.",
            "training": training, "primary_common_support": primary, "secondary_populations": secondary,
            "subgroups": subgroups, "synthetic_recovery": synthetic,
            "coverage": {"development_side_rows": len(development), "common_support": len(primary_rows),
                         "positive_trial_rows": len(positive), "cold_start_positive_rows": len(cold),
                         "development_status_counts": dict(Counter(r["status"] for r in development))},
            "decision": {"predictive_nll_evidence_beyond_v3": primary["new_minus_reference"]["global_bout_variability"]["nll"]["interval_95"][1] < 0,
                         "predictive_nll_evidence_against_all_references": all(g["nll"]["interval_95"][1] < 0 for g in primary["new_minus_reference"].values()),
                         "interval_score_evidence_beyond_v3": {level: primary["new_minus_reference"]["global_bout_variability"]["interval_scores"][level]["interval_95"][1] < 0 for level in ("0.5", "0.9")},
                         "overall_calibration_bands_passed": calibration,
                         "material_regression_flags": regression_flags, "subgroup_calibration_failures": failures,
                         "inconclusive_subgroups": inconclusive, "synthetic_check_passed": synthetic["numerical_check_passed"],
                         "public_release": False, "reason": "Repeatedly inspected development data; no protected future evaluation or completed release gates."},
            "limitations": ["Conditional on observed attempt counts, not an attempt-count forecast",
                            "Mean and hyperparameter uncertainty not propagated", "No opponent-quality adjustment or skill intervals",
                            "Date bootstrap does not preserve all longitudinal fighter dependence", "Multiple exploratory slices, no untouched holdout"]}


def reproduce_v3(sides, rows):
    original = augment(sides)
    if len(original) != len(rows):
        raise ValueError("Frozen v3 row count differs.")
    for row, frozen in zip(original, rows, strict=True):
        mu, n = row["global25"], row["attempts"]
        eligible = mu is not None and 0 < mu < 1
        expected = {**row, "bout_concentration": 5,
                    "bout_beta_a": mu*5 if eligible else None,
                    "bout_beta_b": (1-mu)*5 if eligible else None,
                    "conditional_count_mean": n*mu if eligible and n is not None else None,
                    "conditional_count_variance": n*mu*(1-mu)*(1+(n-1)/6) if eligible and n is not None else None}
        if expected != frozen:
            raise ValueError("A frozen v3 prediction did not reproduce exactly.")


def run(adapter, variability, protocol, output):
    if output.exists() or any(output.resolve().is_relative_to(p.resolve()) for p in (adapter, variability)):
        raise ValueError("Use a new immutable output directory separate from inputs.")
    am = json.loads((adapter / "manifest.json").read_text())
    previous = json.loads((variability / "report.json").read_text())
    paths = [adapter / "manifest.json", adapter / "sides.jsonl", variability / "report.json",
             variability / "predictions.jsonl", protocol, Path(__file__)]
    hashes = {str(p): digest(p) for p in paths}
    if (hashes[str(adapter / "sides.jsonl")] != am["output_sha256"]["sides.jsonl"]
            or hashes[str(variability / "predictions.jsonl")] != previous["output_sha256"]["predictions.jsonl"]):
        raise ValueError("An adapter or v3 prediction hash differs.")
    if previous["training"]["selected"] != 5 or am["before_exclusive"] != previous["before_exclusive"]:
        raise ValueError("The frozen v3 concentration/cutoff contract differs.")
    for path, h in previous["input_sha256"].items():
        if digest(Path(path)) != h:
            raise ValueError("A frozen v3 input changed.")
        hashes[path] = h
    sides = [json.loads(line) for line in (adapter / "sides.jsonl").read_text().splitlines()]
    rows = [json.loads(line) for line in (variability / "predictions.jsonl").read_text().splitlines()]
    reproduce_v3(sides, rows)
    print("Every frozen v3 prediction reproduced; point means unchanged.", flush=True)
    report = evaluate(rows, lambda message: print(message, flush=True))
    if report["primary_common_support"]["side_bouts"] != previous["primary_common_support"]["side_bouts"]:
        raise ValueError("The primary comparison lost common support.")
    c, gamma = report["training"]["selected_c"], report["training"]["selected_gamma"]
    report.update(input_sha256=hashes, before_exclusive=am["before_exclusive"], reproduced_v3_predictions=len(rows),
                  runtime_versions={"numpy": np.__version__, "scipy": __import__("scipy").__version__})
    output.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=output.parent, prefix=".upset-defense-attempt-scaling-") as temporary:
        folder = Path(temporary) / "study"
        folder.mkdir()
        extended = []
        for row in rows:
            mu, n = row["global25"], row["attempts"]
            valid = mu is not None and 0 < mu < 1 and n is not None
            kappa = float(concentration_at_attempts(n, c, gamma)) if valid else None
            extended.append({**row, "attempt_scaling_c": c, "attempt_scaling_gamma": gamma,
                             "attempt_scaled_concentration": kappa,
                             "attempt_scaled_beta_a": mu*kappa if valid else None,
                             "attempt_scaled_beta_b": (1-mu)*kappa if valid else None,
                             "attempt_scaled_conditional_mean": n*mu if valid else None,
                             "attempt_scaled_conditional_variance": n*mu*(1-mu)*(1+(n-1)/(kappa+1)) if valid else None})
        path = folder / "predictions.jsonl"
        path.write_text("".join(json.dumps(row, sort_keys=True, allow_nan=False)+"\n" for row in extended))
        report["output_sha256"] = {"predictions.jsonl": digest(path)}
        if any(digest(Path(path)) != h for path, h in hashes.items()):
            raise ValueError("An input changed during the study.")
        (folder / "report.json").write_text(json.dumps(report, indent=2, sort_keys=True, allow_nan=False)+"\n")
        folder.rename(output)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--adapter", type=Path, required=True)
    parser.add_argument("--variability", type=Path, required=True)
    parser.add_argument("--protocol", type=Path, default=Path("docs/TAKEDOWN_DEFENSE_ATTEMPT_SCALING_PROTOCOL_V4.md"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = run(args.adapter, args.variability, args.protocol, args.output)
    print(json.dumps({k: report[k] for k in ("training", "coverage", "decision")}, indent=2))


if __name__ == "__main__":
    main()
