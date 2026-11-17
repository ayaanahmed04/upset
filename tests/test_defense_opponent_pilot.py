"""Chronology, matched-support and decision checks for the annual pilot."""

from copy import deepcopy

import numpy as np
import pytest
from scipy.special import expit
from scipy.stats import betabinom

from upset.skill.defense_opponent import design, objective
from upset.skill.defense_opponent_pilot import (
    defense_objective,
    evaluate,
    fighter_weights,
    fit_defense,
    fit_with_retry,
    metric_arrays,
    nll,
    proceed_gate,
    run,
    select_penalties,
    snapshot,
    weighted_interval,
)

IDS = [f"00000000-0000-4000-8000-{i:012d}" for i in range(6)]


def side(i, j, n, s, bout, day):
    return {"fighter_id": IDS[i], "opponent_id": IDS[j], "fight_id": bout,
            "event_date": day, "status": "observed" if n else "zero_attempts",
            "opponent_takedown_attempts": n, "takedowns_stopped": s,
            "opponent_takedowns_landed": n-s, "division": "Lightweight"}


def example():
    return [side(0, 1, 4, 0, "one", "2010-01-01"),
            side(1, 0, 8, 8, "one", "2010-01-01"),
            side(0, 2, 3, 2, "two", "2011-01-01"),
            side(2, 0, 1, 1, "two", "2011-01-01"),
            side(0, 1, 4, 3, "three", "2012-01-01"),
            side(3, 1, 4, 0, "four", "2012-01-01")]


def test_defense_objective_is_restricted_original_and_gradient_matches():
    data = design(example(), "2012-01-01")
    theta = np.random.default_rng(2).normal(0, .2, 1+len(data.defenders))
    actual, gradient = defense_objective(theta, data, 4)
    expected, full_gradient = objective(np.r_[theta, np.zeros(len(data.attackers))], data, 4.)
    assert actual == expected
    np.testing.assert_array_equal(gradient, full_gradient[:len(theta)])
    numerical = []
    for i in range(len(theta)):
        step = np.zeros_like(theta)
        step[i] = 1e-5
        numerical.append((defense_objective(theta+step, data, 4)[0]
                          -defense_objective(theta-step, data, 4)[0])/2e-5)
    np.testing.assert_allclose(gradient, numerical, atol=1e-8)
    mu = expit(theta[0]+theta[data.defense_index])
    independent = (-betabinom.logpmf(data.s, data.n, 5*mu, 5*(1-mu)).sum()
                   +2*float(theta[1:]@theta[1:])+.005*theta[0]**2)
    assert actual == pytest.approx(independent, abs=1e-12)


def test_defense_only_fitter_future_and_unknown_opponents():
    rows = example()
    model = fit_defense(rows, "2012-01-01", 4)
    changed = rows+[side(4, 5, 100, 100, "future", "2018-01-01")]
    assert model.coefficients() == fit_defense(changed, "2012-01-01", 4).coefficients()
    assert model.attackers == {}
    a, b = side(0, 1, 1, 1, "a", "2012-01-01"), side(0, 5, 1, 1, "b", "2012-01-01")
    assert model.probabilities([a])[0] == model.probabilities([b])[0]
    assert model.probabilities([side(4, 5, 1, 1, "c", "2012-01-01")])[0] == expit(model.intercept)


def test_defense_fit_failure_stops_comparison():
    with pytest.raises(ValueError, match="numerical gate failed"):
        fit_defense(example(), "2012-01-01", 4, maxiter=0)


def test_stationary_error_gets_one_retry_without_relaxing_acceptance(monkeypatch):
    from upset.skill import defense_opponent_pilot as pilot
    original = pilot.minimize
    calls = []

    def failed_first(*args, **kwargs):
        calls.append(kwargs["options"]["ftol"])
        result = original(*args, **kwargs)
        if len(calls) == 1:
            result.success = False
            result.message = "ABNORMAL: synthetic stationary termination"
        return result

    monkeypatch.setattr(pilot, "minimize", failed_first)
    fitted = fit_with_retry(example(), "2012-01-01", 4, defense_only=True)
    assert calls == [1e-16, 1e-14, 1e-16, 1e-16]
    assert fitted.diagnostics["stationary_retries"] == 1
    assert not fitted.diagnostics["starts"][0]["initial_result"]["success"]
    assert fitted.diagnostics["starts"][0]["success"]
    assert all(r["max_absolute_gradient"] <= 1e-4 for r in fitted.diagnostics["starts"])


def test_nonstationary_failure_does_not_qualify_for_retry():
    with pytest.raises(ValueError, match="V2 numerical fit gate failed"):
        fit_with_retry(example(), "2012-01-01", 4, maxiter=0)


def test_aligned_stopping_keeps_original_acceptance_and_close_predictions():
    original = fit_defense(example(), "2012-01-01", 4)
    aligned = fit_with_retry(example(), "2012-01-01", 4, defense_only=True, aligned_tolerance=True)
    assert aligned.diagnostics["optimizer_gtol"] == 5e-5
    assert aligned.diagnostics["stationary_retries"] == 0
    assert all(r["success"] and r["max_absolute_gradient"] <= 1e-4
               for r in aligned.diagnostics["starts"])
    np.testing.assert_allclose(original.probabilities(example()), aligned.probabilities(example()), atol=1e-5)


def test_evaluation_keeps_cold_start_secondary_and_thin_groups_inconclusive():
    rows = snapshot(example(), 2012)
    for row in rows:
        row.update(defense_only=.5, opponent=.5)
    result = evaluate(rows)
    assert result["primary"]["side_bouts"] == 1
    assert result["primary"]["status"] == "inconclusive_thin_group"
    assert result["defender_cold_start"]["side_bouts"] == 1
    assert "raw_career" not in result["broader_positive"]["models"]
    assert result["primary"]["opponent_minus_reference"]["defense_only"]["nll"]["date_bootstrap"]["interval_95"] == [0, 0]


def test_snapshot_freezes_prior_counts_and_role_components():
    predictions = snapshot(example(), 2012)
    by_id = {r["fighter_id"]: r for r in predictions}
    row, cold = by_id[IDS[0]], by_id[IDS[3]]
    assert row["cutoff"] == "2012-01-01"
    assert row["defender_prior_bouts"] == 2
    assert row["defender_prior_attempts"] == 7
    assert row["attacker_prior_bouts"] == 1
    assert row["primary"]
    assert row["raw_career"] == 2/7
    assert row["global25"] == pytest.approx((2+25*11/16)/32)
    assert row["component_relation"] == "within_component"
    assert cold["component_relation"] == "unseen_role"
    assert cold["defender_component"] is None
    assert cold["defender_prior_bouts"] == 0
    assert cold["raw_career"] is None
    assert cold["global25"] == 11/16


def test_same_year_outcomes_and_later_rows_cannot_change_snapshot_means():
    original = snapshot(example(), 2012)
    rows = deepcopy(example())
    rows[-2].update(takedowns_stopped=0, opponent_takedowns_landed=4)
    rows += [side(4, 5, 1000, 1000, "future", "2019-01-01")]
    changed = snapshot(rows, 2012)
    for a, b in zip(original, changed, strict=True):
        for key in ("raw_career", "global25", "global_prior_rate", "defender_prior_bouts",
                    "attacker_prior_bouts", "defender_component", "attacker_component"):
            assert a[key] == b[key]


def test_clipping_is_explicit_and_zero_attempts_do_not_count():
    rows = [side(0, 1, 1, 1, "a", "2010-01-01"), side(1, 0, 1, 0, "a", "2010-01-01"),
            side(0, 2, 0, 0, "zero", "2011-01-01"), side(0, 1, 1, 1, "b", "2012-01-01")]
    row = snapshot(rows, 2012)[0]
    assert row["raw_career"] == 1-1e-6
    assert row["raw_clipped"] and not row["primary"]
    assert row["defender_prior_bouts"] == 1


def scored_row(year=2012):
    row = {**side(0, 1, 4, 2, "a", f"{year}-01-01"),
           "year": year, "attempts": 4, "stopped": 2, "primary": True}
    for model in ("defense_only", "opponent"):
        for ridge in (1, 4, 16):
            row[f"{model}_ridge{ridge}"] = .5
    return row


def test_penalty_selection_numerical_ties_choose_larger_and_exclude_2018():
    row = scored_row()
    future = scored_row(2018)
    future["opponent_ridge16"] = .99999
    selected, scores = select_penalties([row, future])
    assert selected == {"defense_only": 16, "opponent": 16}
    assert all(r["primary_sides"] == 1 for rows in scores.values() for r in rows)


def test_selection_uses_primary_support_and_pooled_side_weights():
    one, two = scored_row(), scored_row(2013)
    two["opponent_ridge1"] = .1
    cold = scored_row()
    cold["primary"] = False
    cold["opponent_ridge16"] = .99999
    selected, table = select_penalties([one, two, cold])
    assert selected["opponent"] == 16
    expected = float(nll([one, two], "opponent_ridge1").mean())
    assert table["opponent"][0]["mean_nll"] == expected


def test_metric_arrays_do_not_fabricate_raw_cold_start_scores():
    rows = snapshot(example(), 2012)
    values = metric_arrays(rows, "raw_career")
    known = next(i for i, r in enumerate(rows) if r["fighter_id"] == IDS[0])
    cold = next(i for i, r in enumerate(rows) if r["fighter_id"] == IDS[3])
    assert np.isfinite(values["nll"][known])
    assert np.isnan(values["nll"][cold])
    assert values["nll"][known] == pytest.approx(-betabinom.logpmf(3, 4, 5*2/7, 5*5/7))


def test_fighter_weights_reproducible_and_share_paired_bout_weights():
    rows = [side(0, 1, 1, 0, "a", "2010-01-01"), side(1, 0, 1, 1, "a", "2010-01-01"),
            side(0, 2, 1, 1, "b", "2010-01-01")]
    weights = fighter_weights(rows)
    np.testing.assert_array_equal(weights, fighter_weights(rows))
    np.testing.assert_array_equal(weights[:, 0], weights[:, 1])
    np.testing.assert_allclose(weights.sum(axis=1), 1)
    np.testing.assert_allclose(weights[:, ::-1], fighter_weights(rows[::-1]), atol=3e-16, rtol=1e-15)
    interval = weighted_interval(np.zeros(3), weights)
    assert interval["interval_95"] == [0, 0]


def gate_evaluation():
    def comparison():
        return {"nll": {scheme: {"mean": -.02, "interval_95": [-.03, -.01]}
                        for scheme in ("date_bootstrap", "fighter_sensitivity")},
                "normalized_rps": {"date_bootstrap": {"mean": -.001}}}
    return {"primary": {"side_bouts": 501, "opponent_minus_reference": {
                "global25": comparison(), "defense_only": comparison()}}, "subgroups": {}}


def test_backfill_gate_requires_every_comparator_and_both_intervals():
    value = gate_evaluation()
    assert proceed_gate(value)["proceed_to_event_updated_backfill"]
    value["primary"]["opponent_minus_reference"]["defense_only"]["nll"]["fighter_sensitivity"]["interval_95"][1] = .001
    assert not proceed_gate(value)["proceed_to_event_updated_backfill"]


def test_rps_worsening_and_subgroup_regression_block_backfill():
    value = gate_evaluation()
    value["primary"]["opponent_minus_reference"]["global25"]["normalized_rps"]["date_bootstrap"]["mean"] = .0001
    assert not proceed_gate(value)["proceed_to_event_updated_backfill"]
    value = gate_evaluation()
    value["subgroups"] = {"attempts": {"10+": {"material_regression_flags": ["global25"]}}}
    assert not proceed_gate(value)["proceed_to_event_updated_backfill"]


def test_existing_outputs_are_never_overwritten(tmp_path):
    with pytest.raises(ValueError, match="immutable"):
        run(tmp_path, tmp_path/"protocol", tmp_path/"notes", tmp_path)
