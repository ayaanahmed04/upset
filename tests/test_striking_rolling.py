"""Pre-date online calibration is distinct from post-hoc outcome correction."""

from copy import deepcopy

import numpy as np
import pytest
from scipy.optimize import minimize_scalar
from scipy.special import expit, logit
from test_striking_adaptation import history

from upset.skill import striking_accuracy as original
from upset.skill import striking_adaptation as repair
from upset.skill.striking_rolling import fit_intercept, rolling_predictions


def rows():
    sides = history()
    result = repair.recent_predictions(sides, 2920, 500, original.predict(sides, 500))
    for row in result:
        row['recent_calibrated'] = row['recent_uncalibrated']
    return result


def test_root_solution_agrees_with_independent_binomial_minimization():
    sample = [{'landed': 8, 'attempts': 20, 'recent_uncalibrated': .3},
              {'landed': 15, 'attempts': 20, 'recent_uncalibrated': .7}]
    solution = fit_intercept(sample)
    def objective(delta):
        p = expit(logit(np.array([.3, .7]))+delta)
        return float(-np.dot([8, 15], np.log(p))-np.dot([12, 5], np.log1p(-p)))
    fit = minimize_scalar(objective, bounds=(-.5, .5), method='bounded', options={'xatol': 1e-10})
    assert solution == pytest.approx(fit.x, abs=1e-6)
    assert fit_intercept([]) == 0
    assert fit_intercept([{'landed': 20, 'attempts': 20, 'recent_uncalibrated': .5}]) == .5
    assert fit_intercept([{'landed': 0, 'attempts': 20, 'recent_uncalibrated': .5}]) == -.5


def test_current_and_future_outcomes_cannot_change_current_intercept():
    data = rows()
    old = rolling_predictions(data)
    altered = deepcopy(data)
    altered[-1]['landed'], altered[-2]['landed'] = 0, 20
    new = rolling_predictions(altered)
    for a, b in zip(old[:-1], new[:-1], strict=True):
        assert a['rolling_intercept'] == b['rolling_intercept']
        assert a['recent_calibrated'] == b['recent_calibrated']
    assert old[-1]['rolling_intercept'] != new[-1]['rolling_intercept']
    assert all(r['calibration_latest_date'] is None or r['calibration_latest_date'] < r['event_date'] for r in old)


def test_same_date_predictions_share_calibration_history():
    data = rows()
    data[-1]['event_date'] = data[-2]['event_date']
    result = rolling_predictions(data)
    assert result[-1]['rolling_intercept'] == result[-2]['rolling_intercept']
    assert result[-1]['calibration_sides'] == result[-2]['calibration_sides']


def test_730_day_lower_boundary_is_inclusive_and_expired_rows_leave_window():
    row = rows()[1]
    data = [{**row, 'event_date': '2017-01-01', 'fight_id': 'a', 'landed': 16},
            {**row, 'event_date': '2019-01-01', 'fight_id': 'b'},
            {**row, 'event_date': '2019-01-02', 'fight_id': 'c'}]
    result = rolling_predictions(data)
    assert result[1]['calibration_sides'] == 1
    assert result[2]['calibration_sides'] == 1
    assert result[2]['calibration_latest_date'] == '2019-01-01'


def test_missing_or_zero_exposure_does_not_enter_calibration_fit():
    data = rows()[-2:]
    data[0].update(status='zero_attempts', landed=0, attempts=0)
    result = rolling_predictions(data)
    assert result[-1]['calibration_sides'] == 0 and result[-1]['rolling_intercept'] == 0
    with pytest.raises(ValueError):
        fit_intercept([{'landed': 1.5, 'attempts': 10, 'recent_uncalibrated': .5}])
