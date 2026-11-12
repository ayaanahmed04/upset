"""Decay, strict chronology and train-only selection of striking repairs."""

from copy import deepcopy

import numpy as np
import pytest
from test_striking_skill import observation

from upset.skill import striking_accuracy as original
from upset.skill import striking_adaptation as repair


def history():
    return [observation('2011-01-01', 'seed', 20, 40),
            observation('2013-01-01', 'a', 8, 20),
            observation('2014-01-01', 'b', 9, 20),
            observation('2016-01-01', 'c', 12, 20),
            observation('2017-01-01', 'd', 7, 20),
            observation('2020-01-01', 'e', 11, 20),
            observation('2020-02-01', 'f', 13, 20)]


def test_exact_decay_and_mean_arithmetic():
    assert repair.decay_factor(0, 365) == 1
    assert repair.decay_factor(365, 365) == .5
    assert repair.decay_factor(730, 365) == .25
    sides = [observation('2011-01-01', 'a', 20, 40), observation('2012-01-01', 'b', 6, 10)]
    rows = repair.recent_predictions(sides, 365, 100)
    assert rows[0]['recent_uncalibrated'] is None
    assert rows[1]['weighted_prior_landed'] == 10
    assert rows[1]['weighted_prior_attempts'] == 20
    assert rows[1]['recent_uncalibrated'] == .5
    assert rows[1]['recent_population_mean'] == .5


@pytest.mark.parametrize('days,half', [(-1, 365), (365, 0), (float('nan'), 365), (True, 365)])
def test_invalid_decay_rejected(days, half):
    with pytest.raises(ValueError):
        repair.decay_factor(days, half)


def test_same_date_rows_use_identical_prior_history_and_ignore_future_outcomes():
    sides = history()[:3] + [observation('2016-01-01', 'c', 2, 20),
                             observation('2016-01-01', 'd', 18, 20)]
    before = repair.recent_predictions(sides, 730, 500)
    altered = deepcopy(sides)
    altered[-1]['landed'] = 0
    altered[-2]['landed'] = 20
    after = repair.recent_predictions(altered, 730, 500)
    fields = ['recent_uncalibrated', 'weighted_prior_landed', 'weighted_prior_attempts',
              'recent_population_mean', 'weighted_population_attempts']
    for x, y in zip(before, after, strict=True):
        assert all(x[k] == y[k] for k in fields)
    assert before[-1]['weighted_prior_attempts'] == before[-2]['weighted_prior_attempts']
    assert repair.recent_predictions(sides[::-1], 730, 500) == before


def test_missing_and_zero_rows_add_no_weighted_exposure():
    sides = [observation('2011-01-01', 'a', 20, 40), observation('2012-01-01', 'b', None, None),
             observation('2012-01-01', 'c', 0, 0), observation('2013-01-01', 'd', 1, 10)]
    row = repair.recent_predictions(sides, 365, 100)[-1]
    assert row['weighted_prior_attempts'] == pytest.approx(10*2**(-1/365))
    assert row['prior_bouts'] == 3
    assert row['recent_uncalibrated'] == .5


def test_logit_intercept_known_values_and_bounds():
    assert repair.calibrated_mean(None, .1) is None
    assert repair.calibrated_mean(.5, 0) == .5
    assert repair.calibrated_mean(.5, .2) == pytest.approx(1/(1+np.exp(-.2)))
    assert np.allclose(repair.calibrated_mean([.2, .5, .8], 0), [.2, .5, .8])
    with pytest.raises(ValueError):
        repair.calibrated_mean(.5, .6)


def test_fit_and_intercept_do_not_use_development_outcomes():
    sides = history()
    rows, fit = repair.fit_recent_mean(sides, original.predict(sides, 500))
    altered = deepcopy(sides)
    for row in altered[-2:]:
        row['landed'] = 0
    changed_rows, changed = repair.fit_recent_mean(altered, original.predict(altered, 500))
    assert changed == fit
    assert fit['mean_tuning_period'] == '2012-2015'
    assert fit['intercept_fit_sides'] == 2
    for before, after in zip(rows[:-1], changed_rows[:-1], strict=True):
        assert before['recent_calibrated'] == after['recent_calibrated']


def test_calibration_period_does_not_select_the_recent_history_grid():
    sides = history()
    _, before = repair.fit_recent_mean(sides, original.predict(sides, 500))
    changed = deepcopy(sides)
    changed[3]['landed'], changed[4]['landed'] = 0, 0
    _, after = repair.fit_recent_mean(changed, original.predict(changed, 500))
    assert before['grid_scores'] == after['grid_scores']
    assert before['selected_half_life_days'] == after['selected_half_life_days']
    assert before['selected_strength'] == after['selected_strength']


def test_exposure_variation_nests_constant_concentration_and_preserves_mean():
    assert np.array_equal(repair.concentration(np.array([1, 100, 300]), 20, 0), [20, 20, 20])
    assert np.allclose(repair.concentration(np.array([10, 100, 300]), 20, 1), [2, 20, 60])
    rows = [{'attempts': n, 'landed': 2, 'p': .4} for n in [10, 100, 300]]
    dist, n, _, p, c = repair.parameters(rows, 'p', 20, 1)
    assert np.allclose(dist.mean(), n*p)
    assert np.allclose(dist.var(), n*p*(1-p)*(n+c)/(1+c))
    for attempts in [[1.5], [-1], [True]]:
        with pytest.raises(ValueError):
            repair.concentration(attempts, 20, 1)


def test_dispersion_fit_excludes_development_outcomes():
    sides = history()
    rows, _ = repair.fit_recent_mean(sides, original.predict(sides, 500))
    first = repair.fit_dispersion(rows, 'recent_calibrated')
    changed = deepcopy(rows)
    changed[-1]['landed'], changed[-2]['landed'] = 0, 20
    assert repair.fit_dispersion(changed, 'recent_calibrated') == first


def test_matching_synthetic_model_recovers_exposure_slope():
    result = repair.synthetic_recovery()
    assert result['numerical_check_passed']
    assert result['selected']['c100'] == 20 and result['selected']['gamma'] == 1
