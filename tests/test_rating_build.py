"""Selection boundaries, symmetric probability fitting and display protections."""

from copy import deepcopy
from math import log

import pytest

from upset.ratings.build import (
    combine,
    curve_value,
    fit_slope,
    make_ratings,
    score,
    select_model,
)


def parts(value):
    return dict.fromkeys(('striking', 'wrestling', 'grappling', 'resume'), value)


def fights(year):
    return [{'event_date': f'{year}-01-{i+1:02}', 'fight_id': f'{year}-{i}',
             'fighter_ids': ['a', 'b'], 'winner_id': 'a' if i < 8 else 'b',
             'outcome': 'decisive', 'parts': [parts(80), parts(20)], 'prior_bouts': [3, 4]}
            for i in range(10)]


def test_combination_preserves_full_precision_and_missing_parts():
    raw = {'striking': 80, 'wrestling': 60, 'grappling': 40, 'resume': 90}
    value, skills = combine(raw, .5)
    assert skills == pytest.approx(.5*91.2 + .3*83.4 + .2*75.6)
    assert value == pytest.approx(.5*95.1 + .5*skills)
    assert combine({**raw, 'grappling': None}, .5) == (None, None)


def test_positive_symmetric_logistic_fit_agrees_with_analytic_intercept_free_solution():
    fit = fit_slope(fights(2013), .5)
    assert fit['slope'] == pytest.approx(log(4)/23.4, abs=1e-7)
    metrics, losses, probabilities = score(fights(2013), .5, fit['slope'])
    assert probabilities == pytest.approx([.8]*10, abs=1e-7)
    assert metrics['nll'] == pytest.approx(-.8*log(.8)-.2*log(.2))
    swapped = deepcopy(fights(2013))
    for row in swapped:
        row['fighter_ids'].reverse()
        row['parts'].reverse()
    assert score(swapped, .5, fit['slope'])[0]['nll'] == pytest.approx(losses.mean())


def test_selection_ignores_future_and_excludes_unseen_fighters():
    training = fights(2013) + fights(2017)
    selected = select_model(training)
    changed_future = fights(2021)
    for row in changed_future:
        row['winner_id'] = 'b'
    assert select_model(training + changed_future) == selected
    unseen = deepcopy(training)
    for row in unseen:
        row['prior_bouts'][0] = 0
    with pytest.raises(ValueError, match='training periods'):
        select_model(unseen)


def test_frozen_midrank_curve_ties_and_extremes():
    assert curve_value(10, [10]*100) == (77, .5)
    assert curve_value(-1, [0, 1]) == (60, 0.)
    assert curve_value(2, [0, 1]) == (99, 1.)


def test_caps_change_peak_and_future_invariance_of_earlier_curve():
    snapshots = [{'fighter_id': str(i), 'event_date': '2018-01-01', 'bouts': 1,
                  'raw_parts': parts(50), 'metrics': {}, 'coverage': {}, 'elo': 1500., 'division': 'Lightweight'}
                 for i in range(100)]
    snapshots += [{'fighter_id': '0', 'event_date': '2019-01-01', 'bouts': 2,
                   'raw_parts': parts(100), 'metrics': {}, 'coverage': {}, 'elo': 1600., 'division': 'Lightweight'},
                  {'fighter_id': '0', 'event_date': '2020-01-01', 'bouts': 3,
                   'raw_parts': parts(0), 'metrics': {}, 'coverage': {}, 'elo': 1400., 'division': 'Lightweight'}]
    rows, curve = make_ratings(snapshots, [], {'resume_weight': .5})
    own = [row for row in rows if row['fighter_id'] == '0']
    assert [row['score'] for row in own] == [77, 82, 77]
    assert [row['change'] for row in own] == [None, 5, -5]
    assert [row['peak'] for row in own] == [77, 82, 82]
    assert own[1]['small_history_adjustment'] == -11
    assert own[1]['change_adjustment'] == -6
    earlier, earlier_curve = make_ratings(snapshots[:-1], [], {'resume_weight': .5})
    assert earlier_curve == curve and rows[:-1] == earlier
