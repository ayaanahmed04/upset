from dataclasses import replace

import pytest

from upset.data.models import FightStats
from upset.data.normalization import (
    normalize_kaggle_fight,
    normalize_kaggle_fight_stats,
)


def _raw_fight(event_date: str = "2000-01-01") -> dict:
    """Return one complete historical row for focused unit tests."""

    return {
        "Fight_URL": (
            "http://ufcstats.com/fight-details/4acab67848e78327"
        ),
        "Fighter_1": "Scott Morris",
        "Fighter_2": "Sean Daugherty",
        "Winner": "Scott Morris",
        "Weight_Class": "Open Weight Bout",
        "Method": "Submission",
        "End_Round": 1,
        "End_Time": "0:20",
        "Total_Fight_Time_Sec": 20,
        "Time_Format": "No Time Limit",
        "Event_Date": event_date,
        "F1_KD": 0,
        "F2_KD": 0,
        "F1_Sig_Landed": 1,
        "F1_Sig_Att": 2,
        "F2_Sig_Landed": 0,
        "F2_Sig_Att": 1,
        "F1_TD_Landed": 0,
        "F2_TD_Landed": 0,
        "F1_TD_Att": 1,
        "F2_TD_Att": 0,
        "F1_Sub_Att": 1,
        "F2_Sub_Att": 0,
        "F1_Ctrl_Sec": 10,
        "F2_Ctrl_Sec": 0,
        "F1_Head": 1,
        "F2_Head": 0,
        "F1_Body": 0,
        "F2_Body": 0,
        "F1_Leg": 0,
        "F2_Leg": 0,
        "F1_Distance": 0,
        "F2_Distance": 0,
        "F1_Clinch": 1,
        "F2_Clinch": 0,
        "F1_Ground": 0,
        "F2_Ground": 0,
    }


def _linked_fight(raw_fight: dict):
    """Return the normalized fight with both source fighter IDs attached."""

    fight = normalize_kaggle_fight(raw_fight)

    return replace(
        fight,
        source_fighter_1_id="fighter-1",
        source_fighter_2_id="fighter-2",
    )


def test_creates_one_fight_stats_record_per_fighter():
    raw_fight = _raw_fight()
    linked_fight = _linked_fight(raw_fight)

    fighter_1_stats, fighter_2_stats = normalize_kaggle_fight_stats(
        raw_fight,
        linked_fight,
    )

    assert isinstance(fighter_1_stats, FightStats)
    assert isinstance(fighter_2_stats, FightStats)

    assert fighter_1_stats.source == "kaggle_ufc_1994_2026"
    assert fighter_1_stats.source_bout_id == "4acab67848e78327"
    assert fighter_1_stats.source_fighter_id == "fighter-1"
    assert fighter_2_stats.source_fighter_id == "fighter-2"

    assert fighter_1_stats.fight_duration_seconds == 20
    assert fighter_1_stats.source_time_format == "No Time Limit"

    assert fighter_1_stats.sig_strikes_landed == 1
    assert fighter_1_stats.sig_strikes_attempted == 2
    assert fighter_1_stats.submission_attempts == 1
    assert fighter_1_stats.control_seconds == 10

    assert fighter_1_stats.head_landed == 1
    assert fighter_1_stats.clinch_landed == 1

    # This fight is after the coverage boundary, so zero remains zero.
    assert fighter_2_stats.control_seconds == 0


def test_pre_ufc_21_zero_control_becomes_missing():
    raw_fight = _raw_fight(event_date="1999-05-07")
    raw_fight["F1_Ctrl_Sec"] = 0
    linked_fight = _linked_fight(raw_fight)

    records = normalize_kaggle_fight_stats(raw_fight, linked_fight)

    assert records[0].control_seconds is None
    assert records[1].control_seconds is None


def test_pre_ufc_21_nonzero_control_is_preserved():
    raw_fight = _raw_fight(event_date="1999-05-07")
    linked_fight = _linked_fight(raw_fight)

    records = normalize_kaggle_fight_stats(raw_fight, linked_fight)

    assert records[0].control_seconds == 10
    assert records[1].control_seconds is None


def test_ufc_21_boundary_preserves_zero_control():
    raw_fight = _raw_fight(event_date="1999-07-16")
    raw_fight["F1_Ctrl_Sec"] = 0
    linked_fight = _linked_fight(raw_fight)

    records = normalize_kaggle_fight_stats(raw_fight, linked_fight)

    assert records[0].control_seconds == 0
    assert records[1].control_seconds == 0


def test_rejects_fight_without_linked_fighter_ids():
    raw_fight = _raw_fight()
    unlinked_fight = normalize_kaggle_fight(raw_fight)

    with pytest.raises(
        ValueError,
        match="must have both fighter IDs",
    ):
        normalize_kaggle_fight_stats(raw_fight, unlinked_fight)


def test_rejects_linked_fight_that_does_not_match_raw_row():
    raw_fight = _raw_fight()
    linked_fight = replace(
        _linked_fight(raw_fight),
        source_bout_id="different-fight",
    )

    with pytest.raises(
        ValueError,
        match="does not match",
    ):
        normalize_kaggle_fight_stats(raw_fight, linked_fight)


@pytest.mark.parametrize(
    ("field", "value", "error_type"),
    [
        ("F1_KD", -1, ValueError),
        ("F1_Sig_Att", 1.5, ValueError),
        ("F1_Sub_Att", True, TypeError),
    ],
)
def test_rejects_invalid_count_values(field, value, error_type):
    raw_fight = _raw_fight()
    raw_fight[field] = value
    linked_fight = _linked_fight(raw_fight)

    with pytest.raises(error_type, match=field):
        normalize_kaggle_fight_stats(raw_fight, linked_fight)


def test_rejects_more_significant_strikes_landed_than_attempted():
    raw_fight = _raw_fight()
    raw_fight["F1_Sig_Att"] = 0
    linked_fight = _linked_fight(raw_fight)

    with pytest.raises(ValueError, match="cannot exceed"):
        normalize_kaggle_fight_stats(raw_fight, linked_fight)


def test_rejects_more_takedowns_landed_than_attempted():
    raw_fight = _raw_fight()
    raw_fight["F1_TD_Landed"] = 2
    raw_fight["F1_TD_Att"] = 1
    linked_fight = _linked_fight(raw_fight)

    with pytest.raises(ValueError, match="cannot exceed"):
        normalize_kaggle_fight_stats(raw_fight, linked_fight)


@pytest.mark.parametrize(
    ("field", "message"),
    [
        ("F1_Head", "target totals"),
        ("F1_Clinch", "position totals"),
    ],
)
def test_rejects_inconsistent_strike_breakdowns(field, message):
    raw_fight = _raw_fight()
    raw_fight[field] = 0
    linked_fight = _linked_fight(raw_fight)

    with pytest.raises(ValueError, match=message):
        normalize_kaggle_fight_stats(raw_fight, linked_fight)


def test_rejects_zero_fight_duration():
    raw_fight = _raw_fight()
    raw_fight["Total_Fight_Time_Sec"] = 0
    linked_fight = _linked_fight(raw_fight)

    with pytest.raises(ValueError, match="must be greater than zero"):
        normalize_kaggle_fight_stats(raw_fight, linked_fight)


def test_rejects_missing_time_format():
    raw_fight = _raw_fight()
    raw_fight["Time_Format"] = " "
    linked_fight = _linked_fight(raw_fight)

    with pytest.raises(ValueError, match="Time_Format"):
        normalize_kaggle_fight_stats(raw_fight, linked_fight)