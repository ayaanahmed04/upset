"""Attempt-dependent concentration without mean changes or evaluation leakage."""

from copy import deepcopy

import numpy as np
import pytest
from test_defense_validation import history
from test_defense_variability import row

from upset.skill.defense_attempt_scaling import (
    CANDIDATES,
    concentration_at_attempts,
    diagnostic,
    fit_scaling,
    parameters,
    reproduce_v3,
    synthetic_recovery,
)
from upset.skill.defense_validation import augment
from upset.skill.defense_variability import diagnostic as old_diagnostic
from upset.skill.defense_variability import parameters as old_parameters


def test_gamma_zero_reproduces_v3_distribution_exactly():
    rows = [row(n=n, stopped=n//2) for n in (1, 5, 10, 30)]
    new, n, s, mu, kappa = parameters(rows, 5, 0.)
    old, *_ = old_parameters(rows, "global_bout_variability", 5)
    assert np.array_equal(kappa, np.full(4, 5))
    assert np.array_equal(new.logpmf(s), old.logpmf(s))
    assert np.array_equal(new.cdf(s), old.cdf(s))
    assert np.array_equal(new.var(), old.var())
    assert np.allclose(new.mean(), n*mu)


def test_five_attempt_anchor_and_linear_high_attempt_variance_limit():
    for gamma in (0., .5, 1.):
        assert concentration_at_attempts(5, 10, gamma) == 10
    dist, n, _, mu, kappa = parameters([row(n=1000000, stopped=600000)], 5, 1.)
    assert kappa[0] == 1000000
    ratio = dist.var()/(n*mu*(1-mu))
    assert ratio[0] == pytest.approx(1+5/5, abs=3e-6)
    assert concentration_at_attempts(0, 5, 1.) == 1


def test_one_trial_is_concentration_and_exponent_invariant():
    for c, gamma in CANDIDATES:
        dist, *_ = parameters([row(n=1, stopped=1)], c, gamma)
        assert dist.pmf(1)[0] == pytest.approx(.6, abs=1e-12)


@pytest.mark.parametrize("c,gamma", [(0, 1.), (-1, .5), (np.nan, 0.), (5, -.5), (5, 2.), (5, np.nan)])
def test_invalid_scaling_parameters_are_rejected(c, gamma):
    with pytest.raises(ValueError, match="Invalid"):
        concentration_at_attempts(np.array([1, 10]), c, gamma)


def test_counts_still_require_valid_integer_trials():
    for bad in (row(n=True, stopped=1), row(n=1.5, stopped=1), row(n=2, stopped=3)):
        with pytest.raises(ValueError):
            parameters([bad], 5, 1.)


def test_future_outcomes_cannot_select_scaling_or_change_pre_bout_means():
    sides = history()
    before = augment(sides)
    selection = fit_scaling(before)
    changed = deepcopy(sides)
    changed[-1]["takedowns_stopped"] = 0
    after = augment(changed)
    assert fit_scaling(after) == selection
    assert [r["global25"] for r in before] == [r["global25"] for r in after]
    # Both tuning observations have n=5; exponents tie at their anchor.
    assert selection[0][1] == 0.


def test_gamma_zero_matches_v3_calibration_and_scores():
    current, losses = diagnostic([row()], 5, 0.)
    old, old_losses = old_diagnostic([row()], "global_bout_variability", 5)
    assert {k: v for k, v in current.items() if k != "family"} == {k: v for k, v in old.items() if k != "family"}
    assert np.array_equal(losses["nll"], old_losses["nll"])
    assert np.array_equal(losses["normalized_rps"], old_losses["normalized_rps"])


def test_v3_reproduction_rejects_a_changed_original_field():
    sides = history()
    frozen = []
    for r in augment(sides):
        mu, n = r["global25"], r["attempts"]
        valid = mu is not None and 0 < mu < 1
        frozen.append({**r, "bout_concentration": 5,
                       "bout_beta_a": mu*5 if valid else None,
                       "bout_beta_b": (1-mu)*5 if valid else None,
                       "conditional_count_mean": n*mu if valid and n is not None else None,
                       "conditional_count_variance": n*mu*(1-mu)*(1+(n-1)/6) if valid and n is not None else None})
    reproduce_v3(sides, frozen)
    frozen[-1]["conditional_count_variance"] += 1
    with pytest.raises(ValueError, match="reproduce"):
        reproduce_v3(sides, frozen)


def test_scaling_recovery_under_a_known_matching_law():
    result = synthetic_recovery()
    assert (result["selected_c"], result["selected_gamma"]) == (5, 1.)
    assert result["known_mean_and_variance_match"]
    assert result["numerical_check_passed"]
    assert not result["skill_interval_constructed"]
