"""Validate challenger chronology, predictive families and reliability windows."""

from copy import deepcopy

import numpy as np
import pytest
from scipy.stats import beta, betabinom, binom
from test_research_app import A, B
from test_takedown_defense_skill import observation

from upset.skill.defense_validation import (
    augment,
    calibration,
    cluster_interval,
    correlation,
    distribution_arrays,
    pit_uniforms,
    point_losses,
    posterior,
    reliability,
    synthetic_recovery,
)


def history():
    return [observation("2013-01-01", "a", 8, 10),
            observation("2013-01-01", "b", 3, 10, uid=B),
            observation("2013-02-01", "c", 1, 5),
            observation("2013-02-01", "d", 4, 5),
            observation("2020-01-01", "e", 3, 4)]


def test_challenger_known_counts_and_no_same_day_or_future_leakage():
    original = augment(history())
    first = next(r for r in original if r["fight_id"] == "c")
    assert first["prior_stopped"] == 8 and first["prior_attempts"] == 10
    assert first["jeffreys_career"] == 8.5/11
    assert first["laplace_career"] == 9/12
    assert first["global_baseline"] == 11/20
    assert first["global25"] == (8+25*11/20)/35
    assert first["pool_only"] == first["baseline"]
    changed = deepcopy(history())
    changed[2]["takedowns_stopped"] = 5
    changed[-1]["takedowns_stopped"] = 0
    altered = augment(changed)
    for before, after in zip(original[:4], altered[:4], strict=True):
        assert all(before[k] == after[k] for k in (
            "sample_adjusted", "jeffreys_career", "laplace_career",
            "jeffreys_last5", "global25", "pool_only"))


def test_parameter_intervals_and_predictive_intervals_have_different_estimands():
    row = augment(history())[-1]
    a, b = posterior(row, "sample_adjusted")
    assert a == row["prior_stopped"]+25*row["baseline"]
    assert b == row["prior_attempts"]-row["prior_stopped"]+25*(1-row["baseline"])
    assert a/(a+b) == row["sample_adjusted"]
    dist, n, _ = distribution_arrays([row], "sample_adjusted", "beta_binomial")
    assert dist.mean()[0] == pytest.approx(n[0]*row["sample_adjusted"])
    assert dist.var()[0] > binom(n[0], row["sample_adjusted"]).var()
    lo, hi = beta.ppf([.05, .95], a, b)
    assert 0 < lo < hi < 1  # latent probability, not an observed integer outcome


def test_posterior_predictive_matches_beta_mixture_by_direct_enumeration():
    n, a, b = 4, 3, 2
    grid = np.arange(n+1)
    mass = betabinom.pmf(grid, n, a, b)
    assert mass.sum() == pytest.approx(1)
    assert np.dot(grid, mass) == pytest.approx(n*a/(a+b))
    row = {"prior_stopped": 2, "prior_attempts": 3, "last5_stopped": 1,
           "last5_attempts": 1, "baseline": None}
    assert posterior(row, "laplace_career") == (3, 2)
    assert posterior(row, "jeffreys_last5") == (1.5, .5)
    assert posterior(row, "sample_adjusted") is None


def test_point_scores_match_the_frozen_binomial_definition_and_brier_counts():
    row = {"stopped": 2, "attempts": 3, "raw_career": .6}
    nll, cross, brier = point_losses([row], "raw_career")
    assert nll[0] == pytest.approx(-binom.logpmf(2, 3, .6))
    assert cross[0] == pytest.approx(-2*np.log(.6)-np.log(.4))
    assert brier[0] == pytest.approx(2*.4**2+.6**2)


def test_pit_randomization_is_fixed_by_identity_not_row_order_or_method():
    rows = [{"fight_id": "a", "fighter_id": A}, {"fight_id": "b", "fighter_id": B}]
    first = pit_uniforms(rows, 20261027)
    assert np.array_equal(first, pit_uniforms(rows, 20261027))
    assert np.array_equal(first, pit_uniforms(rows[::-1], 20261027)[::-1])
    assert np.all((first >= 0) & (first < 1))
    assert not np.array_equal(first, pit_uniforms(rows, 20261028))


def test_discrete_ranges_report_their_actual_mass_and_thin_groups_are_inconclusive():
    row = augment(history())[-1]
    result = calibration([row], "sample_adjusted", "beta_binomial")
    ninety = result["levels"]["0.9"]
    assert ninety["status"] == "inconclusive_thin_group"
    assert ninety["expected_integer_mass"] >= .9
    assert sum(result["pit_histogram_10_bins"]) == 1
    assert len(ninety["seed_sensitivity"]) == 3


def test_cluster_bootstrap_resamples_dates_and_handles_empty_input():
    assert cluster_interval([], []) is None
    result = cluster_interval([1, 1, 0], ["a", "a", "b"])
    assert result["mean"] == 2/3 and result["date_clusters"] == 2
    assert result == cluster_interval([1, 1, 0], ["a", "a", "b"])


def test_split_half_reliability_does_not_cut_a_same_date_or_skip_zero_bouts():
    sides = [observation("2013-01-01", "a", 5, 10),
             observation("2013-02-01", "b", 0, 0),
             observation("2013-02-01", "c", 5, 10),
             observation("2013-03-01", "d", 5, 10)]
    result = reliability(sides)["2"]
    assert result["attrition"]["same_date_split_boundary"] == 1
    assert result["primary_ten_attempts_per_half"]["fighters"] == 0
    assert correlation([1, 1, 1], [1, 2, 3]) is None
    assert correlation([1, 2, 3], [3, 2, 1], ranked=True) == -1


def test_matching_model_recovery_covers_latent_truth_not_individual_observations():
    result = synthetic_recovery()
    assert result["numerical_check_passed"]
    assert result["overall"]["fighters"] == 8000
    for group in result["by_prior_attempts"].values():
        assert .86 < group["latent_rate_interval_90_coverage"] < .94
        assert .86 < group["randomized_predictive_90_coverage"] < .94
    assert result["by_prior_attempts"]["100"]["mean_rmse"] < result["by_prior_attempts"]["0"]["mean_rmse"]
