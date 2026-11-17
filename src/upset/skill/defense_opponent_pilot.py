"""Annual-snapshot opponent pilot with fixed training selection and release gates."""

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter

import numpy as np
import scipy
from scipy.optimize import minimize
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
from scipy.special import expit, logit
from scipy.stats import betabinom

from upset.skill import defense_opponent as fitter
from upset.skill.defense_validation import cluster_interval, pit_uniforms
from upset.skill.defense_variability import normalized_rps
from upset.skill.takedown_defense import digest

GRID = (1, 4, 16)
MODELS = ("raw_career", "global25", "defense_only", "opponent")
REFERENCES = ("global25", "defense_only")
SEED = 20261026


def defense_objective(theta, data, ridge):
    """Same v1 likelihood/penalty, with attack coefficients fixed to zero."""
    full = np.r_[theta, np.zeros(len(data.attackers))]
    value, gradient = fitter.objective(full, data, float(ridge))
    return value, gradient[:len(theta)]


def fit_defense(rows, before, ridge, maxiter=2000):
    data = fitter.design(rows, before)
    size = 1+len(data.defenders)
    base = np.zeros(size)
    base[0] = logit((data.s.sum()+1)/(data.n.sum()+2))
    perturbation = np.random.default_rng(SEED).normal(0, .1, size)
    perturbation[0] = 0
    runs, diagnostics = [], []
    start = perf_counter()
    for offset in (np.zeros(size), perturbation, -perturbation):
        t0 = perf_counter()
        result = minimize(defense_objective, base+offset, args=(data, ridge), jac=True,
                          method="L-BFGS-B", bounds=[(-8., 8.)]*size,
                          options={"maxiter": maxiter, "gtol": 1e-7, "ftol": 1e-16, "maxls": 40})
        value, gradient = defense_objective(result.x, data, ridge)
        diagnostics.append({"success": bool(result.success), "message": str(result.message),
                            "iterations": int(result.nit), "function_evaluations": int(result.nfev),
                            "objective": value, "max_absolute_gradient": float(abs(gradient).max()),
                            "max_absolute_coefficient": float(abs(result.x).max()),
                            "seconds": perf_counter()-t0})
        runs.append(result)
    best = min(runs, key=lambda r: r.fun)
    prediction = [expit(r.x[0]+r.x[data.defense_index]) for r in runs]
    objective_spread = float(np.ptp([r.fun for r in runs]))
    prediction_spread = float(np.ptp(prediction, axis=0).max())
    passed = (all(r["success"] and r["max_absolute_gradient"] <= 1e-4
                  and r["max_absolute_coefficient"] < 8-1e-5 for r in diagnostics)
              and objective_spread <= 1e-6 and prediction_spread <= 1e-5)
    if not passed:
        raise ValueError(f"Defense-only numerical gate failed: {diagnostics}, "
                         f"spreads={objective_spread,prediction_spread}")
    report = {"before_exclusive": before, "positive_sides": len(data.rows), "ridge": ridge,
              "parameters": size, "fixed_concentration": 5, "intercept_ridge": .01,
              "starts": diagnostics, "objective_spread": objective_spread,
              "prediction_spread": prediction_spread, "numerical_gate_passed": passed,
              "total_seconds": perf_counter()-start}
    return fitter.Fit(dict(zip(data.defenders, map(float, best.x[1:]), strict=True)),
                      {}, float(best.x[0]), report)


def fit_with_retry(rows, before, ridge, defense_only=False, maxiter=2000, aligned_tolerance=False):
    """V2: one stationary-error restart, with unchanged final acceptance gates."""
    data = fitter.design(rows, before)
    size = 1+len(data.defenders) if defense_only else data.size
    function = defense_objective if defense_only else fitter.objective
    ridge = float(ridge)  # Preserve the fractional intercept penalty in the v1 API.
    base = np.zeros(size)
    base[0] = logit((data.s.sum()+1)/(data.n.sum()+2))
    perturbation = np.random.default_rng(SEED).normal(0, .1, size)
    perturbation[0] = 0
    runs, summaries = [], []
    start = perf_counter()

    def describe(result):
        value, gradient = function(result.x, data, ridge)
        return {"success": bool(result.success), "message": str(result.message),
                "iterations": int(result.nit), "function_evaluations": int(result.nfev),
                "objective": value, "max_absolute_gradient": float(abs(gradient).max()),
                "max_absolute_coefficient": float(abs(result.x).max())}

    for offset in (np.zeros(size), perturbation, -perturbation):
        t0 = perf_counter()
        options = {"maxiter": maxiter, "gtol": 5e-5 if aligned_tolerance else 1e-7,
                   "ftol": 1e-16, "maxls": 40}
        result = minimize(function, base+offset, args=(data, ridge), jac=True,
                          method="L-BFGS-B", bounds=[(-8., 8.)]*size, options=options)
        initial = describe(result)
        retried = (not aligned_tolerance and not initial["success"] and np.isfinite(initial["max_absolute_gradient"])
                   and initial["max_absolute_gradient"] <= 1e-4
                   and initial["max_absolute_coefficient"] < 8-1e-5)
        if retried:
            options["ftol"] = 1e-14
            result = minimize(function, result.x, args=(data, ridge), jac=True,
                              method="L-BFGS-B", bounds=[(-8., 8.)]*size, options=options)
        final = describe(result)
        final.update(initial_result=initial, stationary_retry=retried, seconds=perf_counter()-t0)
        summaries.append(final)
        runs.append(result)
    best = min(runs, key=lambda r: r.fun)
    prediction = [expit(r.x[0]+r.x[data.defense_index]
                        -(0 if defense_only else r.x[data.attack_index])) for r in runs]
    objective_spread = float(np.ptp([r.fun for r in runs]))
    prediction_spread = float(np.ptp(prediction, axis=0).max())
    passed = (all(r["success"] and r["max_absolute_gradient"] <= 1e-4
                  and r["max_absolute_coefficient"] < 8-1e-5 for r in summaries)
              and objective_spread <= 1e-6 and prediction_spread <= 1e-5)
    if not passed:
        raise ValueError(f"V2 numerical fit gate failed: {summaries}, "
                         f"spreads={objective_spread,prediction_spread}")
    report = {"before_exclusive": before, "positive_sides": len(data.rows), "ridge": ridge,
              "parameters": size, "fixed_concentration": 5, "intercept_ridge": .01,
              "starts": summaries, "objective_spread": objective_spread,
              "prediction_spread": prediction_spread, "numerical_gate_passed": passed,
              "stationary_retries": sum(r["stationary_retry"] for r in summaries),
              "optimizer_gtol": 5e-5 if aligned_tolerance else 1e-7,
              "total_seconds": perf_counter()-start}
    defenders = dict(zip(data.defenders, map(float, best.x[1:1+len(data.defenders)]), strict=True))
    attackers = ({} if defense_only else dict(zip(data.attackers, map(float, best.x[1+len(data.defenders):]), strict=True)))
    return fitter.Fit(defenders, attackers, float(best.x[0]), report)


def components(data):
    d, a = data.defense_index-1, data.attack_index-1
    graph = coo_matrix((np.ones(2*len(d)), (np.r_[d, a], np.r_[a, d])),
                       shape=(data.size-1, data.size-1)).tocsr()
    _, labels = connected_components(graph, directed=False)
    return (dict(zip(data.defenders, map(int, labels[:len(data.defenders)]), strict=True)),
            dict(zip(data.attackers, map(int, labels[len(data.defenders):]), strict=True)))


def snapshot(rows, year):
    cutoff = f"{year}-01-01"
    data = fitter.design(rows, cutoff)
    observed = [r for r in fitter.eligible(rows, f"{year+1}-01-01") if r["event_date"] >= cutoff]
    if not observed:
        raise ValueError("No evaluation observations in year.")
    counts = defaultdict(lambda: [0, 0, 0])
    attack_counts = Counter()
    for r in data.rows:
        history = counts[r["fighter_id"]]
        history[0] += r["takedowns_stopped"]
        history[1] += r["opponent_takedown_attempts"]
        history[2] += 1
        attack_counts[r["opponent_id"]] += 1
    rate = float(data.s.sum()/data.n.sum())
    if not 0 < rate < 1:
        raise ValueError("A nondegenerate earlier global rate is required.")
    dc, ac = components(data)
    result = []
    for r in observed:
        s, n, bouts = counts[r["fighter_id"]]
        raw = s/n if n else None
        clipped = float(np.clip(raw, 1e-6, 1-1e-6)) if raw is not None else None
        dcomp, acomp = dc.get(r["fighter_id"]), ac.get(r["opponent_id"])
        relation = ("unseen_role" if dcomp is None or acomp is None else
                    "within_component" if dcomp == acomp else "across_component")
        result.append({**r, "cutoff": cutoff, "year": year,
                       "attempts": r["opponent_takedown_attempts"], "stopped": r["takedowns_stopped"],
                       "defender_prior_bouts": bouts, "defender_prior_attempts": n,
                       "defender_prior_stopped": s,
                       "attacker_prior_bouts": attack_counts[r["opponent_id"]],
                       "defender_component": dcomp, "attacker_component": acomp,
                       "component_relation": relation, "global_prior_rate": rate,
                       "raw_career": clipped, "raw_clipped": raw is not None and raw != clipped,
                       "global25": (s+25*rate)/(n+25), "primary": bouts >= 2})
    return result


def predict_model(training, output_rows, model, ridge, stationary_retry=False, aligned_tolerance=False):
    cutoff = output_rows[0]["cutoff"]
    if stationary_retry or aligned_tolerance:
        fitted = fit_with_retry(training, cutoff, ridge, defense_only=model == "defense_only",
                                aligned_tolerance=aligned_tolerance)
    else:
        fitted = (fit_defense(training, cutoff, ridge) if model == "defense_only"
                  else fitter.fit(training, cutoff, float(ridge)))
    values = fitted.probabilities(output_rows)
    if not np.isfinite(values).all() or np.any((values <= 0) | (values >= 1)):
        raise ValueError("Invalid predictions.")
    return values, fitted.diagnostics


def nll(rows, model):
    mu = np.array([r[model] for r in rows])
    n = np.array([r["attempts"] for r in rows])
    s = np.array([r["stopped"] for r in rows])
    values = -betabinom.logpmf(s, n, 5*mu, 5*(1-mu))
    if not np.isfinite(values).all():
        raise ValueError("Nonfinite proper scores.")
    return values


def select_penalties(rows):
    """Only 2012-2017 primary outcomes may influence selection."""
    primary = [r for r in rows if 2012 <= r["year"] <= 2017 and r["primary"]]
    if not primary:
        raise ValueError("No selection support.")
    scores, selected = {}, {}
    for model in ("defense_only", "opponent"):
        scores[model] = []
        for ridge in GRID:
            key = f"{model}_ridge{ridge}"
            scores[model].append({"ridge": ridge, "mean_nll": float(nll(primary, key).mean()),
                                  "primary_sides": len(primary),
                                  "by_year": {str(year): {"sides": sum(r["year"] == year for r in primary),
                                               "mean_nll": float(nll([r for r in primary if r["year"] == year], key).mean())}
                                              for year in sorted({r["year"] for r in primary})}})
        best = min(r["mean_nll"] for r in scores[model])
        selected[model] = max(r["ridge"] for r in scores[model] if r["mean_nll"] <= best+1e-12)
    return selected, scores


def metric_arrays(rows, model):
    if model == "raw_career" and any(r[model] is None for r in rows):
        indices = np.array([i for i, r in enumerate(rows) if r[model] is not None], dtype=int)
        if not len(indices):
            raise ValueError("No available raw history.")
        available = metric_arrays([rows[i] for i in indices], model)

        def expand(value):
            if isinstance(value, dict):
                return {key: expand(item) for key, item in value.items()}
            result = np.full((len(rows), *value.shape[1:]), np.nan)
            result[indices] = value
            return result

        return expand(available)
    mu = np.array([r[model] for r in rows], dtype=float)
    n = np.array([r["attempts"] for r in rows])
    s = np.array([r["stopped"] for r in rows])
    dist = betabinom(n, 5*mu, 5*(1-mu))
    left, mass = np.clip(dist.cdf(s-1), 0, 1), dist.pmf(s)
    result = {"nll": nll(rows, model), "rps": normalized_rps(dist, n, s)}
    for level in (.5, .9):
        tail = (1-level)/2
        low, high = dist.ppf(tail), dist.ppf(1-tail)
        key = str(level)
        result[key] = {"integer_coverage": ((s >= low) & (s <= high)).astype(float),
                       "expected_mass": dist.cdf(high)-dist.cdf(low-1), "width": high-low,
                       "interval_score": high-low+2/(1-level)*(np.maximum(low-s, 0)+np.maximum(s-high, 0)),
                       "pit": np.column_stack([((v >= tail) & (v <= 1-tail)).astype(float)
                                               for v in [np.clip(left+pit_uniforms(rows, seed)*mass, 0, 1)
                                                         for seed in (SEED+1, SEED+2, SEED+3)]])}
    result["pit"] = np.clip(left+pit_uniforms(rows, SEED+1)*mass, 0, 1)
    return result


def fighter_weights(rows, replicates=1000):
    ids = sorted({r[k] for r in rows for k in ("fighter_id", "opponent_id")})
    indices = {uid: i for i, uid in enumerate(ids)}
    draws = np.random.default_rng(SEED+4).exponential(size=(replicates, len(ids)))
    weights = draws[:, [indices[r["fighter_id"]] for r in rows]]*draws[:, [indices[r["opponent_id"]] for r in rows]]
    return weights/weights.sum(axis=1)[:, None]


def weighted_interval(values, weights):
    values = np.asarray(values)
    draws = (weights*values[None, :]).sum(axis=1)
    return {"mean": float(values.mean()), "interval_95": np.quantile(draws, [.025, .975]).tolist(),
            "replicates": len(weights), "seed": SEED+4, "method": "crossed_fighter_weight_sensitivity"}


def summarize(rows, metrics, models, indices, minimum=500):
    if not len(indices):
        return {"side_bouts": 0, "status": "inconclusive_empty"}
    group = [rows[i] for i in indices]
    dates = [r["event_date"] for r in group]
    enough = len(group) >= minimum and len(set(dates)) >= 20
    report = {"side_bouts": len(group), "date_clusters": len(set(dates)),
              "attempts": sum(r["attempts"] for r in group),
              "status": "sized_for_diagnostic" if enough else "inconclusive_thin_group",
              "models": {}, "opponent_minus_reference": {}, "material_regression_flags": []}
    for model in models:
        m = metrics[model]
        result = {"mean_predictive_nll": float(m["nll"][indices].mean()),
                  "mean_normalized_rps": float(m["rps"][indices].mean()), "levels": {},
                  "pit_histogram_10_bins": np.histogram(m["pit"][indices], bins=np.linspace(0, 1, 11))[0].tolist()}
        for level in ("0.5", "0.9"):
            v = m[level]
            pit = v["pit"][indices]
            band = (.45, .55) if level == "0.5" else (.87, .93)
            status = "within_band" if band[0] <= pit[:, 0].mean() <= band[1] else "outside_band"
            result["levels"][level] = {
                "integer_count_coverage": cluster_interval(v["integer_coverage"][indices], dates),
                "expected_integer_mass": float(v["expected_mass"][indices].mean()),
                "mean_integer_width": float(v["width"][indices].mean()),
                "mean_interval_score": float(v["interval_score"][indices].mean()),
                "randomized_pit_coverage": cluster_interval(pit[:, 0], dates),
                "diagnostic_band": list(band), "status": status if enough else "inconclusive_thin_group",
                "seed_sensitivity": [{"seed": SEED+1+i, "coverage": float(pit[:, i].mean())} for i in range(3)]}
        report["models"][model] = result
    weights = fighter_weights(group)
    for reference in REFERENCES:
        new, old = metrics["opponent"], metrics[reference]
        differences = {"nll": new["nll"][indices]-old["nll"][indices],
                       "normalized_rps": new["rps"][indices]-old["rps"][indices]}
        differences.update({f"interval_score_{level}": new[level]["interval_score"][indices]-old[level]["interval_score"][indices]
                            for level in ("0.5", "0.9")})
        report["opponent_minus_reference"][reference] = {
            key: {"date_bootstrap": cluster_interval(value, dates),
                  "fighter_sensitivity": weighted_interval(value, weights)} for key, value in differences.items()}
        difference = report["opponent_minus_reference"][reference]["nll"]["date_bootstrap"]
        if enough and difference["mean"] > .05 and difference["interval_95"][0] > 0:
            report["material_regression_flags"].append(reference)
    return report


def history_group(n):
    return "0" if n == 0 else "1" if n == 1 else "2-4" if n < 5 else "5-9" if n < 10 else "10+"


def attempt_group(n):
    return "1" if n == 1 else "2-4" if n < 5 else "5-9" if n < 10 else "10+"


def evaluate(rows, models=MODELS):
    metrics = {model: metric_arrays(rows, model) for model in models}
    primary = np.array([i for i, r in enumerate(rows) if r["primary"]], dtype=int)
    result = {"primary": summarize(rows, metrics, models, primary), "subgroups": {}}
    for field, label in (("division", lambda r: r["division"] or "unknown"),
                         ("year", lambda r: str(r["year"])),
                         ("defender_history", lambda r: history_group(r["defender_prior_bouts"])),
                         ("attacker_history", lambda r: history_group(r["attacker_prior_bouts"])),
                         ("attempts", lambda r: attempt_group(r["attempts"])),
                         ("components", lambda r: r["component_relation"])):
        result["subgroups"][field] = {
            value: summarize(rows, metrics, models, np.array([i for i in primary if label(rows[i]) == value], dtype=int), 100)
            for value in sorted({label(rows[i]) for i in primary})}
    secondary_models = tuple(m for m in models if m != "raw_career")
    for name, predicate in (("broader_positive", lambda r: True),
                            ("defender_cold_start", lambda r: r["defender_prior_bouts"] == 0),
                            ("attacker_cold_start", lambda r: r["attacker_prior_bouts"] == 0)):
        indices = np.array([i for i, r in enumerate(rows) if predicate(r)], dtype=int)
        result[name] = summarize(rows, metrics, secondary_models, indices)
    return result


def proceed_gate(evaluation):
    primary = evaluation["primary"]
    if not primary["side_bouts"]:
        return {"proceed_to_event_updated_backfill": False, "failed_gates": ["empty_primary"]}
    failures = []
    for reference in REFERENCES:
        values = primary["opponent_minus_reference"][reference]
        if values["nll"]["date_bootstrap"]["mean"] >= 0:
            failures.append(f"nll_improvement:{reference}")
        if values["normalized_rps"]["date_bootstrap"]["mean"] > 0:
            failures.append(f"rps_nonworsening:{reference}")
        for scheme in ("date_bootstrap", "fighter_sensitivity"):
            if values["nll"][scheme]["interval_95"][1] >= 0:
                failures.append(f"nll_upper_bound:{reference}:{scheme}")
    for field, groups in evaluation["subgroups"].items():
        for name, report in groups.items():
            failures.extend(f"subgroup_regression:{field}:{name}:{reference}"
                            for reference in report.get("material_regression_flags", []))
    return {"proceed_to_event_updated_backfill": not failures, "failed_gates": failures,
            "fit_gates_passed": True, "public_release": False}


def run(adapter, protocol, implementation, output, progress=lambda value: None,
        stationary_retry=False, aligned_tolerance=False):
    if output.exists():
        raise ValueError("Use a new immutable output directory.")
    manifest_path = adapter / "manifest.json"
    sides = adapter / "sides.jsonl"
    manifest = json.loads(manifest_path.read_text())
    database = Path(manifest["input_database"])
    if (digest(sides) != manifest["output_sha256"]["sides.jsonl"]
            or digest(database) != manifest["input_sha256"]["database_sha256"]):
        raise ValueError("Input hashes do not match their manifest.")
    paths = [manifest_path, sides, database, protocol, implementation, Path(__file__), Path(fitter.__file__)]
    if stationary_retry or aligned_tolerance:
        paths.append(protocol.with_name("TAKEDOWN_DEFENSE_OPPONENT_PILOT_PROTOCOL_V1.md"))
    if aligned_tolerance:
        paths.append(protocol.with_name("TAKEDOWN_DEFENSE_OPPONENT_PILOT_PROTOCOL_V2.md"))
    hashes = {str(p): digest(p) for p in paths}
    rows = [json.loads(line) for line in sides.read_text().splitlines()]
    if len(rows) != manifest["side_rows"] or any(
            r["database_sha256"] != manifest["input_sha256"]["database_sha256"] for r in rows):
        raise ValueError("Adapter provenance mismatch.")
    audited = fitter.audit(rows, "2019-01-01")
    predictions, fits = [], []
    for year in range(2012, 2018):
        current = snapshot(rows, year)
        for model in ("defense_only", "opponent"):
            for ridge in GRID:
                values, diagnostics = predict_model(rows, current, model, ridge, stationary_retry, aligned_tolerance)
                for row, value in zip(current, values, strict=True):
                    row[f"{model}_ridge{ridge}"] = float(value)
                fits.append({"year": year, "model": model, "ridge": ridge, "diagnostics": diagnostics})
        predictions.extend(current)
        progress(f"Completed {year} selection snapshot: {len(current)} sides")
    selected, selection = select_penalties(predictions)
    # Penalties are frozen here, before any 2018 outcome is scored.
    for row in predictions:
        for model, ridge in selected.items():
            row[model] = row[f"{model}_ridge{ridge}"]
    current = snapshot(rows, 2018)
    for model, ridge in selected.items():
        values, diagnostics = predict_model(rows, current, model, ridge, stationary_retry, aligned_tolerance)
        for row, value in zip(current, values, strict=True):
            row[model] = float(value)
        fits.append({"year": 2018, "model": model, "ridge": ridge, "diagnostics": diagnostics})
    progress(f"Selected penalties {selected}; completed 2018 fit; computing fixed diagnostics")
    # Raw career is undefined at zero history. Compute raw arrays only where available.
    # Secondary evaluation uses the other three models and must never fabricate raw means.
    evaluation = evaluate(current)
    training_evaluation = evaluate(predictions)
    report = {"study": ("opponent_annual_pilot_v3" if aligned_tolerance else
                        "opponent_annual_pilot_v2" if stationary_retry else "opponent_annual_pilot_v1"),
              "input_sha256": hashes, "adapter_audit": audited,
              "versions": {"numpy": np.__version__, "scipy": scipy.__version__},
              "selection_period": "2012-2017", "diagnostic_year": 2018,
              "selected_penalties": selected, "selection_table": selection, "fits": fits,
              "selection_diagnostics": training_evaluation, "development_2018": evaluation,
              "decision": proceed_gate(evaluation), "public_release": False,
              "protected_validation": False, "scored_2019_plus": False,
              "raw_clipped_primary": sum(r["raw_clipped"] and r["primary"] for r in predictions+current),
              "raw_clipped_positive": sum(r["raw_clipped"] for r in predictions+current),
              "scored_positive_sides": len(predictions)+len(current)}
    report["stationary_retries"] = sum(f["diagnostics"].get("stationary_retries", 0) for f in fits)
    if any(digest(Path(p)) != h for p, h in hashes.items()):
        raise ValueError("An input changed during the pilot.")
    output.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=output.parent, prefix=".upset-opponent-pilot-") as temporary:
        folder = Path(temporary) / "study"
        folder.mkdir()
        path = folder / "predictions.jsonl"
        path.write_text("".join(json.dumps(r, sort_keys=True)+"\n" for r in predictions+current))
        report["output_sha256"] = {path.name: digest(path)}
        (folder / "report.json").write_text(json.dumps(report, indent=2, sort_keys=True)+"\n")
        folder.rename(output)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--adapter", type=Path, required=True)
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--implementation", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--stationary-retry", action="store_true")
    parser.add_argument("--aligned-tolerance", action="store_true")
    args = parser.parse_args()
    report = run(args.adapter, args.protocol, args.implementation, args.output,
                 progress=lambda value: print(value, flush=True), stationary_retry=args.stationary_retry,
                 aligned_tolerance=args.aligned_tolerance)
    print(json.dumps({"output": str(args.output), "selected_penalties": report["selected_penalties"],
                      "decision": report["decision"]}, indent=2))


if __name__ == "__main__":
    main()
