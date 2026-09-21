from dataclasses import asdict

import pytest

from upset.data.models import Fighter
from upset.data.normalization import (
    normalize_kaggle_fighter,
    parse_kaggle_measurement,
)


@pytest.fixture
def profile_row():
    """A synthetic profile using the historical CSV's field formats."""
    return {
        "Fighter_Name": "Example Fighter",
        "Fighter_URL": (
            "http://ufcstats.com/fighter-details/0000000000000001"
        ),
        "Height": "5' 11\"",
        "Weight": "155 lbs.",
        "Reach": '72.0"',
        "Stance": "Orthodox",
        "DOB": "1990-02-28",
        "Wins": "20",
        "Losses": "3",
        "SLpM": "4.5",
    }


def test_normalize_profile(profile_row):
    fighter = normalize_kaggle_fighter(profile_row)

    assert isinstance(fighter, Fighter)
    assert fighter.source == "kaggle_ufc_1994_2026"
    assert fighter.source_fighter_id == "0000000000000001"
    assert fighter.source_fighter_slug is None
    assert fighter.name == "Example Fighter"
    assert fighter.height_inches == 71.0
    assert fighter.weight_lbs == 155.0
    assert fighter.reach_inches == 72.0
    assert fighter.stance == "Orthodox"
    assert fighter.date_of_birth == "1990-02-28"
    assert fighter.source_url == profile_row["Fighter_URL"]
    assert fighter.division is None
    assert fighter.status is None
    assert fighter.champion_status is None


@pytest.mark.parametrize("missing_value", ["", "   ", None])
def test_preserves_missing_profile_values(profile_row, missing_value):
    for field in ("Height", "Weight", "Reach", "Stance", "DOB"):
        profile_row[field] = missing_value

    fighter = normalize_kaggle_fighter(profile_row)

    assert fighter.height_inches is None
    assert fighter.weight_lbs is None
    assert fighter.reach_inches is None
    assert fighter.stance is None
    assert fighter.date_of_birth is None


@pytest.mark.parametrize(
    ("field", "value", "expected"),
    [
        ("Height", "6' 0\"", 72.0),
        ("Height", " 5' 11\" ", 71.0),
        ("Weight", "155 lbs.", 155.0),
        ("Weight", "770 lbs.", 770.0),
        ("Reach", '72.5"', 72.5),
    ],
)
def test_measurement_conversion(field, value, expected):
    assert parse_kaggle_measurement(value, field=field) == expected


@pytest.mark.parametrize(
    ("field", "value", "error_type"),
    [
        ("Height", "5' 12\"", ValueError),
        ("Height", "0' 0\"", ValueError),
        ("Weight", "0 lbs.", ValueError),
        ("Weight", "155 kg", ValueError),
        ("Reach", "unknown", ValueError),
        ("Reach", float("nan"), TypeError),
        ("Weight", True, TypeError),
    ],
)
def test_rejects_invalid_measurements(field, value, error_type):
    with pytest.raises(error_type):
        parse_kaggle_measurement(value, field=field)


@pytest.mark.parametrize(
    ("field", "value", "error_type"),
    [
        ("Fighter_Name", "   ", ValueError),
        (
            "Fighter_URL",
            "http://example.com/fighter-details/0000000000000001",
            ValueError,
        ),
        (
            "Fighter_URL",
            "http://ufcstats.com/fighter-details/invalid",
            ValueError,
        ),
        ("DOB", "1990-02-30", ValueError),
        ("DOB", "02/28/1990", ValueError),
        ("Stance", 123, TypeError),
    ],
)
def test_rejects_invalid_profile_fields(
    profile_row, field, value, error_type
):
    profile_row[field] = value

    with pytest.raises(error_type):
        normalize_kaggle_fighter(profile_row)


def test_same_name_can_have_different_ids(profile_row):
    second_row = {
        **profile_row,
        "Fighter_URL": (
            "http://ufcstats.com/fighter-details/0000000000000002"
        ),
    }

    first = normalize_kaggle_fighter(profile_row)
    second = normalize_kaggle_fighter(second_row)

    assert first.name == second.name
    assert first.source_fighter_id != second.source_fighter_id


def test_career_statistics_do_not_change_profile(profile_row):
    changed_stats = {
        **profile_row,
        "Wins": "100",
        "Losses": "50",
        "SLpM": "9.9",
    }

    original = normalize_kaggle_fighter(profile_row)
    changed = normalize_kaggle_fighter(changed_stats)

    assert asdict(original) == asdict(changed)


def test_does_not_change_input(profile_row):
    original = profile_row.copy()

    normalize_kaggle_fighter(profile_row)

    assert profile_row == original