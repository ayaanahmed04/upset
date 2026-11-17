"""Frozen means, concentration tuning and explicit beta-binomial variance."""

from copy import deepcopy

import numpy as np
import pytest
from scipy.stats import binom
from test_defense_validation import history

from upset.skill.defense_validation import augment
from upset.skill.defense_variability import (
    GRID,
    choose,
    cohort_report,
    diagnostic,
    fit_concentration,
    group_label,
    normalized_rps,
    parameters,
    synthetic_recovery,
)


def row(mu=.6, n=3, stopped=2):
    return {"attempts": n, "stopped": stopped, "global25": mu,
            "global_baseline": mu, "prior_attempts": 0, "prior_stopped": 0,
            "event_date": "2020-01-01", "fight_id": "synthetic:a", "fighter_id": "synthetic:b"}


def test_families_keep_the_same_mean_but_have_explicit_different_variances():
    r = row(n=10, stopped=7)
    for family in ("global_binomial", "global_stationary_posterior", "global_bout_variability"):
        dist, n, s, mu = parameters([r], family, 5)
        assert dist.mean()[0] == pytest.approx(6)
        assert n[0] == 10 and s[0] == 7 and mu[0] == .6
    varying = parameters([r], "global_bout_variability", 5)[0]
    assert varying.var()[0] == pytest.approx(10*.6*.4*(1+9/6))
    assert varying.var()[0] > parameters([r], "global_stationary_posterior", 5)[0].var()[0]
    assert varying.var()[0] > parameters([r], "global_binomial", 5)[0].var()[0]


def test_single_attempt_predictions_do_not_identify_concentration():
    r = row(n=1, stopped=1)
    for c in GRID:
        dist, *_ = parameters([r], "global_bout_variability", c)
        assert dist.pmf(1)[0] == pytest.approx(.6, abs=1e-12)
        assert dist.pmf(0)[0] == pytest.approx(.4, abs=1e-12)
    r.update(event_date="2013-01-01", status="observed", raw_career=.6, raw_last5=.6, sample_adjusted=.6)
    with pytest.raises(ValueError, match="informative"):
        fit_concentration([r])


def test_large_concentration_approaches_binomial_and_probabilities_sum_to_one():
    r = row(n=7, stopped=4)
    dist, *_ = parameters([r], "global_bout_variability", 100000)
    for k in range(8):
        assert dist.pmf(k)[0] == pytest.approx(binom.pmf(k, 7, .6), abs=2e-5)
    assert sum(dist.pmf(k)[0] for k in range(8)) == pytest.approx(1, abs=1e-8)


@pytest.mark.parametrize("bad", [0, -1, np.nan, np.inf])
def test_invalid_concentration_is_rejected(bad):
    with pytest.raises(ValueError, match="concentration"):
        parameters([row()], "global_bout_variability", bad)


def test_invalid_counts_and_means_are_not_silently_clipped():
    for r in (row(mu=0), row(mu=1), row(stopped=4), row(n=-1), row(n=True)):
        with pytest.raises(ValueError):
            parameters([r], "global_bout_variability", 10)
    with pytest.raises(ValueError, match="family"):
        parameters([row()], "unknown", 10)


def test_development_outcomes_cannot_change_concentration_or_pre_bout_means():
    sides = history()
    original = augment(sides)
    strength, fit = fit_concentration(original)
    changed = deepcopy(sides)
    changed[-1]["takedowns_stopped"] = 0
    altered = augment(changed)
    assert fit_concentration(altered) == (strength, fit)
    assert [r["global25"] for r in original] == [r["global25"] for r in altered]
    assert fit["training_sides"] == 2


def test_numerical_ties_select_the_first_declared_candidate():
    assert choose([1., 1.+1e-13, 1.]) == 0
    assert choose([2., 1., 1.]) == 1
    with pytest.raises(ValueError):
        choose([1., np.nan])


def test_ranked_probability_score_matches_a_closed_form_example():
    dist, n, s, _ = parameters([row()], "global_binomial", 10)
    expected = (.064**2 + .352**2 + (.784-1)**2)/3
    assert normalized_rps(dist, n, s)[0] == pytest.approx(expected)
    with pytest.raises(ValueError, match="positive"):
        normalized_rps(dist, np.array([0]), s)


def test_interval_diagnostics_are_finite_and_thin_cohorts_are_inconclusive():
    report, losses = diagnostic([row()], "global_bout_variability", 10)
    assert report["levels"]["0.9"]["status"] == "inconclusive_thin_group"
    assert report["levels"]["0.9"]["expected_integer_mass"] >= .9
    assert report["levels"]["0.9"]["mean_interval_score"] >= report["levels"]["0.9"]["mean_integer_width"]
    assert np.isfinite(losses["nll"]).all()
    assert cohort_report([], 10)["status"] == "inconclusive_empty"
    assert group_label({"prior_attempts": 0}, "prior_exposure") == "0"


def test_matching_bout_variability_recovery():
    result = synthetic_recovery()
    assert result["selected_concentration"] == result["true_concentration"] == 10
    assert result["known_mean_and_variance_match"]
    assert result["numerical_check_passed"]
    assert not result["skill_interval_constructed"]
