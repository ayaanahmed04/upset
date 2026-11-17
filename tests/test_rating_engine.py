"""Chronology, opportunity handling and opponent direction for rating features."""

from copy import deepcopy
from math import isfinite

import pytest

from upset.ratings.engine import FEATURES, elo_expectation, normal_score, replay


def stats(landed=50, attempts=100, *, control=None, td=0, td_attempts=0,
          subs=0, kd=0, ground=0, duration=900):
    return {"sig_strikes_landed": landed, "sig_strikes_attempted": attempts,
            "knockdowns": kd, "takedowns_landed": td, "takedowns_attempted": td_attempts,
            "submission_attempts": subs, "ground_landed": ground,
            "control_seconds": control, "fight_duration_seconds": duration}


def bout(key, day, a="A", b="B", winner="A", first=None, second=None,
         method="decision", division="Lightweight", duration=900, outcome="decisive"):
    return {"fight_id": key, "event_date": day, "fighter_ids": [a, b], "names": [a, b],
            "winner_id": winner, "outcome": outcome, "method_group": method,
            "division": division, "duration_seconds": duration,
            "stats": [first if first is not None else stats(),
                      second if second is not None else stats()]}


def by_uid(snapshots, uid):
    return [row for row in snapshots if row["fighter_id"] == uid]


def test_first_date_neutral_modeling_parts_are_not_postfight_outcomes():
    snapshots, pre = replay([bout("one", "2020-01-01")])
    assert pre[0]["parts"] == [dict.fromkeys(("striking", "wrestling", "grappling", "resume"), 50.)]*2
    assert pre[0]["prior_bouts"] == [0, 0]
    assert pre[0]["prior_snapshot_dates"] == [None, None]
    a = by_uid(snapshots, "A")[0]
    assert a["elo"] == 1516 and a["bouts"] == 1
    assert a["raw_parts"]["resume"] == pytest.approx(normal_score(16/200))
    assert a["coverage"]["context_by_feature"]["sig_diff"]["basis"] == "floor_only"


def test_later_bouts_and_their_outcomes_cannot_change_prefix_snapshots():
    early = [bout("one", "2020-01-01"), bout("two", "2020-02-01", "A", "C")]
    baseline = replay(early)
    later = bout("later", "2025-01-01", "A", "D", "D", first=stats(1, 500), method="ko")
    snapshots, pre = replay(early+[later])
    assert snapshots[:len(baseline[0])] == baseline[0]
    assert pre[:len(baseline[1])] == baseline[1]
    assert all(day is None or day < row["event_date"] for row in pre for day in row["prior_snapshot_dates"])


def test_same_date_bouts_freeze_elo_baselines_and_ignore_input_order():
    rows = [bout("one", "2020-01-01", "A", "B"),
            bout("two", "2020-01-01", "A", "C")]
    expected = replay(rows)
    assert replay(list(reversed(rows))) == expected
    assert all(row["prior_bouts"] == [0, 0] for row in expected[1])
    a = by_uid(expected[0], "A")
    assert len(a) == 1 and a[0]["bouts"] == 2 and a[0]["elo"] == 1532


def test_missing_control_and_zero_attempts_are_unavailable_not_favorable_zeros():
    row = bout("one", "2020-01-01", first=stats(0, 0), second=stats(0, 0))
    snapshots, _ = replay([row])
    a = by_uid(snapshots, "A")[0]
    assert a["metrics"]["striking_accuracy"] is None
    assert a["metrics"]["striking_defense"] is None
    assert a["metrics"]["takedown_accuracy"] is None
    assert a["metrics"]["takedown_defense"] is None
    assert a["metrics"]["control_share"] is None
    assert "control_share" not in a["coverage"]["available_features"]["wrestling"]
    assert "sig_accuracy" not in a["coverage"]["available_features"]["striking"]
    assert a["metrics"]["sig_landed_per_minute"] == 0


def test_zero_clock_does_not_contribute_rate_opportunities():
    row = bout("one", "2020-01-01", first=stats(0, 0, duration=0),
               second=stats(0, 0, duration=0), duration=0)
    snapshots, _ = replay([row])
    a = by_uid(snapshots, "A")[0]
    assert a["metrics"]["sig_landed_per_minute"] is None
    assert a["raw_parts"]["wrestling"] is None
    assert a["raw_parts"]["resume"] > 50


@pytest.mark.parametrize("outcome", ["draw", "nc", "other"])
def test_nondecisive_results_do_not_change_elo(outcome):
    snapshots, _ = replay([bout("one", "2020-01-01", winner=None, outcome=outcome)])
    assert all(row["elo"] == 1500 and row["raw_parts"]["resume"] == 50 for row in snapshots)


def test_win_against_stronger_opponent_has_larger_elo_increment():
    first = [bout("b1", "2020-01-01", "B", "C", "B"),
             bout("d1", "2020-01-01", "D", "E", "E")]
    rows = first+[bout("high", "2020-02-01", "A", "B", "A"),
                  bout("low", "2020-02-01", "F", "D", "F")]
    snapshots, _ = replay(rows)
    assert by_uid(snapshots, "A")[0]["elo"] > by_uid(snapshots, "F")[0]["elo"]
    assert elo_expectation(1500, 1516) < elo_expectation(1500, 1484)


def test_equal_accuracy_against_stricter_earlier_defense_receives_more_credit():
    rows = [bout("b1", "2020-01-01", "B", "C", "B", first=stats(), second=stats(10, 100)),
            bout("d1", "2020-01-01", "D", "E", "D", first=stats(), second=stats(90, 100)),
            bout("a1", "2020-02-01", "A", "B", "A"),
            bout("f1", "2020-02-01", "F", "D", "F")]
    snapshots, _ = replay(rows)
    a, f = by_uid(snapshots, "A")[0], by_uid(snapshots, "F")[0]
    assert a["metrics"]["striking_accuracy"] == f["metrics"]["striking_accuracy"] == .5
    assert a["coverage"]["feature_z"]["sig_accuracy"] > f["coverage"]["feature_z"]["sig_accuracy"]


def test_recent_sufficient_counts_decay_by_bouts_not_calendar_time():
    first = bout("one", "2020-01-01", first=stats(50))
    second = bout("two", "2020-01-02", "A", "C", first=stats(100))
    later_second = deepcopy(second)
    later_second["event_date"] = "2025-01-01"
    a = by_uid(replay([first, second])[0], "A")[-1]
    b = by_uid(replay([first, later_second])[0], "A")[-1]
    assert a["metrics"] == b["metrics"]
    assert a["raw_parts"] == b["raw_parts"]
    assert a["metrics"]["sig_landed_per_minute"] == pytest.approx((50*.85+100)/(15*.85+15))


def test_idle_fighter_prefight_features_remain_latched_when_other_fighters_compete():
    rows = [bout("one", "2020-01-01"), bout("elsewhere", "2020-02-01", "C", "D", "D"),
            bout("return", "2020-03-01", "A", "E", "A")]
    snapshots, pre = replay(rows)
    a = by_uid(snapshots, "A")[0]
    assert pre[-1]["parts"][0] == a["raw_parts"]
    assert pre[-1]["prior_snapshot_dates"][0] == "2020-01-01"


def test_submission_loss_with_no_recorded_opposing_attempt_stays_unavailable():
    snapshots, _ = replay([bout("one", "2020-01-01", winner="B", method="sub")])
    a = by_uid(snapshots, "A")[0]
    assert a["metrics"]["submission_losses_per_opponent_attempt"] is None
    assert "sub_avoided" not in a["coverage"]["available_features"]["grappling"]
    assert a["metrics"]["submission_wins_per_bout"] == 0


def test_unclassified_later_bout_preserves_latest_known_division():
    rows = [bout("one", "2020-01-01"),
            bout("two", "2020-02-01", "A", "C", division=None)]
    assert by_uid(replay(rows)[0], "A")[-1]["division"] == "Lightweight"


def test_repeatability_input_preservation_finite_bounded_outputs_and_declared_floors():
    rows = [bout("one", "2020-01-01", first=stats(90, td=2, td_attempts=3, control=500, subs=2, ground=20),
                 second=stats(10, td=0, td_attempts=2, control=100, subs=1, ground=1))]
    untouched = deepcopy(rows)
    expected = replay(rows)
    assert rows == untouched and replay(rows) == expected
    for state in expected[0]:
        assert all(value is None or isfinite(value) and 0 <= value <= 100 for value in state["raw_parts"].values())
        for key, info in state["coverage"]["context_by_feature"].items():
            assert info["std"] >= FEATURES[key].floor
        assert all(abs(value) <= 3 for value in state["coverage"]["feature_z"].values())


@pytest.mark.parametrize("prior,recency", [(0, .85), (45, 0), (45, 1.1)])
def test_invalid_configuration_rejected(prior, recency):
    with pytest.raises(ValueError):
        replay([], minutes_prior=prior, recency=recency)


def test_duplicate_bout_rejected():
    row = bout("one", "2020-01-01")
    with pytest.raises(ValueError):
        replay([row, row])
