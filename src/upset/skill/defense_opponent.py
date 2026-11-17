"""Offline opponent attack/defense fitter: numerical contract, no release."""

import argparse
import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter

import numpy as np
import scipy
from scipy.optimize import minimize
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
from scipy.special import betaln, digamma, expit, gammaln, logit

from upset.data.identity import validate_upset_fighter_id
from upset.skill.takedown_defense import digest

KAPPA = 5.
RIDGE = 4.
INTERCEPT_RIDGE = .01
SEED = 20261026


def eligible(rows, before):
    """The cutoff applies before constructing any role dictionary."""
    if date.fromisoformat(before).isoformat() != before:
        raise ValueError("Use an exclusive ISO date.")
    result = []
    seen = set()
    for row in rows:
        day = row["event_date"]
        if date.fromisoformat(day).isoformat() != day:
            raise ValueError("Invalid date.")
        if day >= before:
            continue
        if row["status"] not in ("observed", "zero_attempts"):
            continue
        for key in ("fighter_id", "opponent_id"):
            validate_upset_fighter_id(row[key])
        if row["fighter_id"] == row["opponent_id"]:
            raise ValueError("A fighter cannot face themselves.")
        key = row["fight_id"], row["fighter_id"]
        if key in seen:
            raise ValueError("Duplicate side.")
        seen.add(key)
        n, s, landed = (row[k] for k in (
            "opponent_takedown_attempts", "takedowns_stopped", "opponent_takedowns_landed"))
        if (any(type(v) is not int for v in (n, s, landed))
                or not 0 <= s <= n or landed != n-s
                or (n == 0) != (row["status"] == "zero_attempts")):
            raise ValueError("Invalid trial counts/status.")
        if n:
            result.append(row)
    return sorted(result, key=lambda r: (r["event_date"], r["fight_id"], r["fighter_id"]))


@dataclass
class Design:
    rows: list
    defenders: list
    attackers: list
    defense_index: np.ndarray
    attack_index: np.ndarray
    n: np.ndarray
    s: np.ndarray

    @property
    def size(self):
        return 1+len(self.defenders)+len(self.attackers)


def design(rows, before):
    rows = eligible(rows, before)
    if not rows:
        raise ValueError("No positive earlier-date trials.")
    defenders = sorted({r["fighter_id"] for r in rows})
    attackers = sorted({r["opponent_id"] for r in rows})
    di = {uid: i+1 for i, uid in enumerate(defenders)}
    ai = {uid: i+1+len(defenders) for i, uid in enumerate(attackers)}
    return Design(rows, defenders, attackers,
                  np.array([di[r["fighter_id"]] for r in rows]),
                  np.array([ai[r["opponent_id"]] for r in rows]),
                  np.array([r["opponent_takedown_attempts"] for r in rows]),
                  np.array([r["takedowns_stopped"] for r in rows]))


def objective(theta, data, ridge=RIDGE):
    """Summed beta-binomial NLL with exact analytic gradient and ridge."""
    if not np.isfinite(ridge) or ridge <= 0:
        raise ValueError("Role penalty must be positive.")
    theta = np.asarray(theta, dtype=float)
    if theta.shape != (data.size,) or not np.isfinite(theta).all() or np.any(abs(theta) > 8):
        raise ValueError("Invalid or out-of-contract parameters.")
    mu = expit(theta[0]+theta[data.defense_index]-theta[data.attack_index])
    a, b = KAPPA*mu, KAPPA*(1-mu)
    n, s = data.n, data.s
    log_combination = gammaln(n+1)-gammaln(s+1)-gammaln(n-s+1)
    log_mass = log_combination+betaln(s+a, n-s+b)-betaln(a, b)
    penalty = np.full(data.size, ridge)
    penalty[0] = INTERCEPT_RIDGE
    loss = -log_mass.sum()+.5*np.dot(penalty*theta, theta)
    # da/deta = -db/deta = kappa*mu*(1-mu); constant a+b terms cancel.
    residual = -KAPPA*mu*(1-mu)*(digamma(s+a)-digamma(a)
                                             -digamma(n-s+b)+digamma(b))
    gradient = penalty*theta
    gradient[0] += residual.sum()
    gradient += np.bincount(data.defense_index, weights=residual, minlength=data.size)
    gradient -= np.bincount(data.attack_index, weights=residual, minlength=data.size)
    return float(loss), gradient


@dataclass
class Fit:
    defenders: dict
    attackers: dict
    intercept: float
    diagnostics: dict

    def probabilities(self, rows):
        eta = [self.intercept+self.defenders.get(r["fighter_id"], 0.)
               -self.attackers.get(r["opponent_id"], 0.) for r in rows]
        return expit(np.asarray(eta))

    def coefficients(self):
        return {"intercept": self.intercept, "defense": self.defenders,
                "attack": self.attackers}


def fit(rows, before, ridge=RIDGE, maxiter=2000):
    data = design(rows, before)
    base = np.zeros(data.size)
    base[0] = logit((data.s.sum()+1)/(data.n.sum()+2))
    rng = np.random.default_rng(SEED)
    perturbation = rng.normal(0, .1, data.size)
    perturbation[0] = 0
    runs, summaries = [], []
    start = perf_counter()
    for offset in (np.zeros(data.size), perturbation, -perturbation):
        t0 = perf_counter()
        result = minimize(objective, base+offset, args=(data, ridge), jac=True,
                          method="L-BFGS-B", bounds=[(-8., 8.)]*data.size,
                          options={"maxiter": maxiter, "gtol": 1e-7,
                                   "ftol": 1e-16, "maxls": 40})
        loss, gradient = objective(result.x, data, ridge)
        summaries.append({"success": bool(result.success), "message": str(result.message),
                          "iterations": int(result.nit), "function_evaluations": int(result.nfev),
                          "objective": loss, "max_absolute_gradient": float(abs(gradient).max()),
                          "max_absolute_coefficient": float(abs(result.x).max()),
                          "seconds": perf_counter()-t0})
        runs.append(result)
    best = min(runs, key=lambda r: r.fun)
    predictions = [expit(r.x[0]+r.x[data.defense_index]-r.x[data.attack_index]) for r in runs]
    spread = float(np.ptp([r.fun for r in runs]))
    prediction_spread = float(np.ptp(predictions, axis=0).max())
    passed = (all(r["success"] and r["max_absolute_gradient"] <= 1e-4
                  and r["max_absolute_coefficient"] < 8-1e-5 for r in summaries)
              and spread <= 1e-6 and prediction_spread <= 1e-5)
    if not passed:
        raise ValueError(f"Numerical fit gate failed: {summaries}, spreads={spread,prediction_spread}")
    theta = best.x
    diagnostics = {"before_exclusive": before, "positive_sides": len(data.rows),
                   "trials": int(data.n.sum()), "date_clusters": len({r["event_date"] for r in data.rows}),
                   "defender_roles": len(data.defenders), "attacker_roles": len(data.attackers),
                   "parameters": data.size, "ridge": ridge, "intercept_ridge": INTERCEPT_RIDGE,
                   "fixed_concentration": KAPPA, "starts": summaries,
                   "objective_spread": spread, "prediction_spread": prediction_spread,
                   "total_seconds": perf_counter()-start, "numerical_gate_passed": passed}
    return Fit(dict(zip(data.defenders, map(float, theta[1:1+len(data.defenders)]), strict=True)),
               dict(zip(data.attackers, map(float, theta[1+len(data.defenders):]), strict=True)),
               float(theta[0]), diagnostics)


def audit(rows, before):
    """Audit paired identity/event/source contracts and role graph separately."""
    past = [r for r in rows if r["event_date"] < before]
    by_fight = defaultdict(list)
    events = defaultdict(set)
    for row in past:
        by_fight[row["fight_id"]].append(row)
        events[row["event_id"]].add(row["event_date"])
    if any(len(days) != 1 for days in events.values()):
        raise ValueError("Event ID spans multiple dates.")
    for pair in by_fight.values():
        if len(pair) != 2:
            raise ValueError("Expected exactly two source sides.")
        a, b = pair
        if (a["fighter_id"] != b["opponent_id"] or b["fighter_id"] != a["opponent_id"]
                or any(a[k] != b[k] for k in (
                    "event_id", "event_date", "division", "source", "source_bout_id",
                    "database_sha256", "source_rows_sha256"))
                or a["source_fighter_id"] != b["opponent_source_fighter_id"]
                or b["source_fighter_id"] != a["opponent_source_fighter_id"]):
            raise ValueError("Broken reciprocal identity/event/source contract.")
    data = design(rows, before)
    d, a = data.defense_index-1, data.attack_index-1
    graph = coo_matrix((np.ones(len(d)*2), (np.r_[d, a], np.r_[a, d])),
                       shape=(data.size-1, data.size-1)).tocsr()
    count, labels = connected_components(graph, directed=False)
    sizes = sorted(Counter(labels).values(), reverse=True)
    exposures = Counter(r["fighter_id"] for r in data.rows)
    attack_exposures = Counter(r["opponent_id"] for r in data.rows)
    return {"before_exclusive": before, "all_sides": len(past), "fights": len(by_fight),
            "positive_sides": len(data.rows), "trials": int(data.n.sum()),
            "statuses": dict(Counter(r["status"] for r in past)),
            "date_clusters": len({r["event_date"] for r in data.rows}),
            "event_clusters": len(events), "defender_roles": len(data.defenders),
            "attacker_roles": len(data.attackers), "role_graph_components": int(count),
            "component_role_counts_descending": sizes,
            "single_bout_defender_roles": sum(n == 1 for n in exposures.values()),
            "single_bout_attacker_roles": sum(n == 1 for n in attack_exposures.values()),
            "positive_by_division": dict(Counter(r["division"] or "unknown" for r in data.rows)),
            "positive_by_year": dict(sorted(Counter(r["event_date"][:4] for r in data.rows).items())),
            "positive_by_source": dict(Counter(r["source"] for r in data.rows)),
            "reciprocal_contract_passed": True,
            "context": "global intercept only; division/era/source confounding unresolved"}


def synthetic_rows():
    rng = np.random.default_rng(SEED)
    ids = [f"00000000-0000-4000-8000-{i:012d}" for i in range(36)]
    defense, attack = rng.normal(0, .6, (2, len(ids)))
    defense -= defense.mean()
    attack -= attack.mean()
    rows = []
    for repetition in range(6):
        for i, uid in enumerate(ids):
            for j, opponent in enumerate(ids):
                if i == j:
                    continue
                mu = expit(.4+defense[i]-attack[j])
                n = int(rng.integers(1, 19))
                s = int(rng.binomial(n, rng.beta(KAPPA*mu, KAPPA*(1-mu))))
                rows.append({"fighter_id": uid, "opponent_id": opponent,
                             "event_date": f"200{repetition}-01-01", "status": "observed",
                             "fight_id": f"synthetic:{repetition}:{i}:{j}",
                             "opponent_takedown_attempts": n, "takedowns_stopped": s,
                             "opponent_takedowns_landed": n-s, "true_probability": float(mu)})
    return rows, ids, defense, attack


def synthetic_check():
    rows, ids, defense, attack = synthetic_rows()
    fitted = fit(rows, "2005-01-01")
    result = {"fit_sides": 6300, "heldout_sides": 1260, "seed": SEED,
              "matching_model_only": True, "fit": fitted.diagnostics}
    for role, truth, effects in (("defense", defense, fitted.defenders),
                                 ("attack", attack, fitted.attackers)):
        estimated = np.array([effects[uid] for uid in ids])
        estimated -= estimated.mean()
        result[role+"_correlation"] = float(np.corrcoef(truth, estimated)[0, 1])
        result[role+"_centered_rmse"] = float(np.sqrt(np.mean((truth-estimated)**2)))
    heldout = [r for r in rows if r["event_date"] >= "2005-01-01"]
    predictions = fitted.probabilities(heldout)
    truth = np.array([r["true_probability"] for r in heldout])
    result["heldout_mean_probability_error"] = float(np.mean(predictions-truth))
    result["heldout_probability_rmse"] = float(np.sqrt(np.mean((predictions-truth)**2)))
    result["passed"] = (all(result[role+"_correlation"] > .85
                            and result[role+"_centered_rmse"] < .3 for role in ("defense", "attack"))
                        and abs(result["heldout_mean_probability_error"]) < .05)
    if not result["passed"]:
        raise ValueError(f"Matching-model recovery failed: {result}")
    return result


def run(adapter, protocol, output):
    if output.exists():
        raise ValueError("Use a new immutable output directory.")
    manifest = adapter / "manifest.json"
    sides = adapter / "sides.jsonl"
    metadata = json.loads(manifest.read_text())
    if digest(sides) != metadata["output_sha256"]["sides.jsonl"]:
        raise ValueError("Adapter sides hash mismatch.")
    database = Path(metadata["input_database"])
    if digest(database) != metadata["input_sha256"]["database_sha256"]:
        raise ValueError("Serving database hash mismatch.")
    hashes = {str(p): digest(p) for p in (manifest, sides, database, protocol, Path(__file__))}
    rows = [json.loads(line) for line in sides.read_text().splitlines()]
    if len(rows) != metadata["side_rows"] or any(
            r["database_sha256"] != metadata["input_sha256"]["database_sha256"] for r in rows):
        raise ValueError("Adapter provenance mismatch.")
    report = {"study": "opponent_fitter_contract_v1", "input_sha256": hashes,
              "versions": {"numpy": np.__version__, "scipy": scipy.__version__},
              "synthetic": synthetic_check(), "benchmarks": {},
              "public_release": False, "real_heldout_scores_computed": False,
              "opponent_fitter_implemented": True, "opponent_adjustment_validated": False,
              "skill_intervals": False}
    coefficients = {}
    for label, before in (("small", "2006-01-01"), ("representative", "2019-01-01")):
        design_audit = audit(rows, before)
        fitted = fit(rows, before)
        report["benchmarks"][label] = {"audit": design_audit, "fit": fitted.diagnostics}
        coefficients[label] = fitted.coefficients()
    repeat = fit(rows, "2019-01-01")
    original = coefficients["representative"]
    differences = [abs(original["intercept"]-repeat.intercept)]
    for role, effects in (("defense", repeat.defenders), ("attack", repeat.attackers)):
        differences.extend(abs(original[role][uid]-value) for uid, value in effects.items())
    report["repeat_representative_fit"] = repeat.diagnostics
    report["repeat_max_coefficient_difference"] = max(differences)
    if max(differences) > 1e-10:
        raise ValueError("Representative fit is not reproducible.")
    if any(digest(Path(p)) != value for p, value in hashes.items()):
        raise ValueError("An input changed during the study.")
    output.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=output.parent, prefix=".upset-opponent-") as temporary:
        folder = Path(temporary) / "study"
        folder.mkdir()
        path = folder / "coefficients.json"
        path.write_text(json.dumps(coefficients, indent=2, sort_keys=True)+"\n")
        report["output_sha256"] = {path.name: digest(path)}
        (folder / "report.json").write_text(json.dumps(report, indent=2, sort_keys=True)+"\n")
        folder.rename(output)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--adapter", type=Path, required=True)
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = run(args.adapter, args.protocol, args.output)
    print(json.dumps({"output": str(args.output), "synthetic_passed": report["synthetic"]["passed"],
                      "benchmarks": {key: value["fit"] for key, value in report["benchmarks"].items()},
                      "public_release": False}, indent=2))


if __name__ == "__main__":
    main()
