"""Numerical and chronological gates for the offline opponent fitter."""

from copy import deepcopy

import numpy as np
import pytest
from scipy.special import expit
from scipy.stats import betabinom

from upset.skill.defense_opponent import (
    INTERCEPT_RIDGE,
    KAPPA,
    RIDGE,
    Fit,
    audit,
    design,
    fit,
    objective,
    run,
    synthetic_check,
)

IDS = [f"00000000-0000-4000-8000-{i:012d}" for i in range(6)]


def side(i, j, n, s, bout="one", day="2010-01-01"):
    return {"fighter_id": IDS[i], "opponent_id": IDS[j], "fight_id": bout,
            "event_date": day, "event_id": "event:"+day, "status": "observed" if n else "zero_attempts",
            "opponent_takedown_attempts": n, "takedowns_stopped": s,
            "opponent_takedowns_landed": n-s, "division": "Lightweight",
            "source": "test", "source_bout_id": bout, "source_rows_sha256": "rows",
            "database_sha256": "database", "source_fighter_id": str(i),
            "opponent_source_fighter_id": str(j)}


def example():
    # Includes disconnected role schedules, count edges, and n=1.
    return [side(0, 1, 4, 0), side(1, 0, 8, 8),
            side(2, 3, 1, 1, "two"), side(3, 2, 6, 2, "two")]


def test_gradient_and_independent_log_probability():
    data = design(example(), "2019-01-01")
    theta = np.random.default_rng(123).normal(0, .3, data.size)
    loss, grad = objective(theta, data)
    numerical = []
    for i in range(data.size):
        step = np.zeros(data.size)
        step[i] = 1e-5
        numerical.append((objective(theta+step, data)[0]-objective(theta-step, data)[0])/2e-5)
    np.testing.assert_allclose(grad, numerical, atol=2e-8, rtol=2e-7)
    mu = expit(theta[0]+theta[data.defense_index]-theta[data.attack_index])
    expected = (-betabinom.logpmf(data.s, data.n, KAPPA*mu, KAPPA*(1-mu)).sum()
                +RIDGE/2*np.dot(theta[1:], theta[1:])+INTERCEPT_RIDGE/2*theta[0]**2)
    assert loss == pytest.approx(expected, abs=1e-12)


@pytest.mark.parametrize("value", [-7., 7.])
def test_extreme_legal_parameters_have_finite_loss_gradient(value):
    data = design(example(), "2019-01-01")
    theta = np.full(data.size, value)
    theta[data.attack_index] = -value
    loss, grad = objective(theta, data)
    assert np.isfinite(loss) and np.isfinite(grad).all()


def test_sign_and_cold_start_contract():
    model = Fit({IDS[0]: 1.}, {IDS[1]: 1.}, .4, {})
    probabilities = model.probabilities([side(0, 2, 1, 0), side(2, 1, 1, 0),
                                       side(2, 3, 1, 0), side(0, 1, 1, 0)])
    np.testing.assert_allclose(probabilities, expit([1.4, -.6, .4, .4]))


def test_zero_attempts_and_future_identities_cannot_change_fit():
    rows = example()
    original = fit(rows, "2019-01-01")
    augmented = rows+[side(4, 5, 0, 0, "zero"), side(4, 5, 400, 400, "future", "2019-01-01")]
    changed = fit(augmented, "2019-01-01")
    assert original.coefficients() == changed.coefficients()
    assert IDS[4] not in changed.defenders and IDS[5] not in changed.attackers


def test_input_order_does_not_change_coefficients():
    rows = example()
    assert fit(rows, "2019-01-01").coefficients() == fit(rows[::-1], "2019-01-01").coefficients()


@pytest.mark.parametrize("updates", [
    {"takedowns_stopped": -1}, {"opponent_takedown_attempts": 1.5},
    {"opponent_takedowns_landed": 999}, {"status": "zero_attempts"},
    {"fighter_id": "bad"}, {"opponent_id": IDS[0]},
])
def test_invalid_measurements_or_identities_rejected(updates):
    row = side(0, 1, 3, 2)
    row.update(updates)
    with pytest.raises(ValueError):
        design([row], "2019-01-01")


def test_duplicate_empty_and_bad_date_rejected():
    row = side(0, 1, 3, 2)
    for rows, before in (([row, row], "2019-01-01"), ([], "2019-01-01"), ([row], "no date")):
        with pytest.raises(ValueError):
            design(rows, before)


def test_missing_measurements_excluded_and_zero_counts_add_no_exposure():
    missing = side(4, 5, 3, 2, "missing")
    missing.update(status="missing_opponent_counts", takedowns_stopped=None)
    data = design(example()+[missing, side(4, 5, 0, 0, "zero")], "2019-01-01")
    assert len(data.rows) == 4
    assert IDS[4] not in data.defenders


def test_role_graph_audit_is_not_a_single_fighter_graph():
    report = audit(example(), "2019-01-01")
    assert report["role_graph_components"] == 4
    assert report["component_role_counts_descending"] == [2]*4
    assert report["reciprocal_contract_passed"]


@pytest.mark.parametrize("key,value", [("event_date", "2011-01-01"),
                                      ("source_rows_sha256", "changed"),
                                      ("opponent_source_fighter_id", "bad")])
def test_broken_pair_audit_rejected(key, value):
    rows = deepcopy(example())
    rows[1][key] = value
    with pytest.raises(ValueError):
        audit(rows, "2019-01-01")


def test_failed_optimizer_cannot_produce_accepted_output():
    with pytest.raises(ValueError, match="Numerical fit gate failed"):
        fit(example(), "2019-01-01", maxiter=0)


def test_invalid_penalty_rejected():
    data = design(example(), "2019-01-01")
    for ridge in (0, -1, np.inf):
        with pytest.raises(ValueError):
            objective(np.zeros(data.size), data, ridge)


def test_existing_output_is_never_overwritten(tmp_path):
    with pytest.raises(ValueError, match="immutable"):
        run(tmp_path, tmp_path / "protocol.md", tmp_path)


def test_matching_model_recovers_separate_attack_and_defense():
    result = synthetic_check()
    assert result["passed"]
    assert result["fit_sides"] == 6300
    assert result["heldout_sides"] == 1260
