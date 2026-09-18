import pytest

from upset.data.models import Fight
from upset.data.normalization import normalize_kaggle_fight


@pytest.fixture
def historical_row():
    """A small example using the historical CSV's field structure."""
    return {
        "Fight_URL": "http://ufcstats.com/fight-details/4acab67848e78327",
        "Fighter_1": "Scott Morris",
        "Fighter_2": "Sean Daugherty",
        "Winner": "Scott Morris",
        "Weight_Class": "Open Weight Bout",
        "Method": "Submission",
        "End_Round": 1,
        "End_Time": "0:20",
        "Event_Date": "1994-03-11",
    }


def test_normalize_historical_fight(historical_row):
    fight = normalize_kaggle_fight(historical_row)

    assert isinstance(fight, Fight)
    assert fight.source == "kaggle_ufc_1994_2026"
    assert fight.source_bout_id == "4acab67848e78327"
    assert fight.source_url == historical_row["Fight_URL"]
    assert fight.event_date == "1994-03-11"
    assert fight.fighter_1_name == "Scott Morris"
    assert fight.fighter_2_name == "Sean Daugherty"
    assert fight.winner_name == "Scott Morris"
    assert fight.source_winner_label == "Scott Morris"
    assert fight.result_method == "Submission"
    assert fight.result_round == 1
    assert fight.result_time == "0:20"
    assert fight.weight_class == "Open Weight Bout"

    # The CSV does not provide these identifiers.
    assert fight.source_event_id is None
    assert fight.source_fighter_1_id is None
    assert fight.source_fighter_2_id is None


def test_second_fighter_can_be_winner(historical_row):
    historical_row["Winner"] = "Sean Daugherty"

    fight = normalize_kaggle_fight(historical_row)

    assert fight.winner_name == "Sean Daugherty"


def test_preserves_combined_draw_nc_label(historical_row):
    historical_row["Winner"] = "Draw/NC"
    historical_row["Method"] = "Other"

    fight = normalize_kaggle_fight(historical_row)

    assert fight.winner_name is None
    assert fight.source_winner_label == "Draw/NC"
    assert fight.result_method == "Other"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("Winner", "Someone Else"),
        ("Fighter_1", None),
        ("Fighter_2", float("nan")),
        ("Winner", ""),
        ("Fight_URL", "http://ufcstats.com/fight-details/invalid"),
        ("Fight_URL", "http://example.com/fight-details/4acab67848e78327"),
        ("Event_Date", "1994-02-30"),
        ("End_Round", 0),
        ("End_Round", 1.5),
        ("End_Round", True),
    ],
)
def test_rejects_invalid_historical_values(historical_row, field, value):
    historical_row[field] = value

    with pytest.raises((ValueError, TypeError)):
        normalize_kaggle_fight(historical_row)


def test_does_not_change_input_record(historical_row):
    original = historical_row.copy()

    normalize_kaggle_fight(historical_row)

    assert historical_row == original