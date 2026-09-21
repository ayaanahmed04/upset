from dataclasses import replace

import pytest

from upset.data.linking import link_historical_fights
from upset.data.models import Fight, Fighter


@pytest.fixture
def example_data():
    source = "kaggle_ufc_1994_2026"

    profiles = [
        Fighter(
            source=source,
            source_fighter_id="profile-a",
            source_fighter_slug=None,
            name="Alex",
        ),
        Fighter(
            source=source,
            source_fighter_id="profile-b",
            source_fighter_slug=None,
            name="Sam",
        ),
    ]

    fight = Fight(
        source=source,
        source_bout_id="fight-1",
        fighter_1_name="Alex",
        fighter_2_name="Sam",
        event_date="2020-01-01",
        winner_name="Alex",
        source_winner_label="Alex",
    )

    return fight, profiles


@pytest.fixture
def ambiguous_data(example_data):
    fight, profiles = example_data

    # A second, distinct person shares Alex's name.
    profiles = [
        *profiles,
        replace(profiles[0], source_fighter_id="profile-c"),
    ]

    override = {
        "source": fight.source,
        "source_bout_id": fight.source_bout_id,
        "fighter_side": 1,
        "fighter_name": "Alex",
        "source_fighter_id": "profile-c",
        "event_date": fight.event_date,
        "opponent_name": "Sam",
    }

    return fight, profiles, override


def test_links_unique_names_without_changing_input(example_data):
    fight, profiles = example_data

    linked = link_historical_fights([fight], profiles, [])

    assert linked[0] == replace(
        fight,
        source_fighter_1_id="profile-a",
        source_fighter_2_id="profile-b",
    )
    assert fight.source_fighter_1_id is None
    assert fight.source_fighter_2_id is None
    assert linked[0] is not fight


def test_reviewed_override_selects_correct_same_name_profile(ambiguous_data):
    fight, profiles, override = ambiguous_data

    linked = link_historical_fights([fight], profiles, [override])

    assert linked[0].source_fighter_1_id == "profile-c"
    assert linked[0].source_fighter_2_id == "profile-b"


def test_ambiguous_name_requires_override(ambiguous_data):
    fight, profiles, _ = ambiguous_data

    with pytest.raises(ValueError, match="Unresolved participant"):
        link_historical_fights([fight], profiles, [])


def test_missing_profile_is_rejected(example_data):
    fight, profiles = example_data

    with pytest.raises(ValueError, match="Unresolved participant"):
        link_historical_fights([fight], profiles[:1], [])


def test_same_name_from_other_source_is_not_matched(example_data):
    fight, profiles = example_data
    profiles[0] = replace(profiles[0], source="another_provider")

    with pytest.raises(ValueError, match="Unresolved participant"):
        link_historical_fights([fight], profiles, [])


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("fighter_name", "Someone Else", "does not match fight details"),
        ("event_date", "2021-01-01", "does not match fight details"),
        ("opponent_name", "Someone Else", "does not match fight details"),
        ("source_fighter_id", "profile-b", "invalid profile"),
        ("fighter_side", True, "fighter_side must be"),
        ("fighter_side", 3, "fighter_side must be"),
    ],
)
def test_rejects_inconsistent_overrides(
    ambiguous_data, field, value, message
):
    fight, profiles, override = ambiguous_data
    override = {**override, field: value}

    with pytest.raises(ValueError, match=message):
        link_historical_fights([fight], profiles, [override])


def test_duplicate_profile_ids_are_rejected(example_data):
    fight, profiles = example_data

    with pytest.raises(ValueError, match="Duplicate profile ID"):
        link_historical_fights([fight], [*profiles, profiles[0]], [])


def test_duplicate_fight_ids_are_rejected(example_data):
    fight, profiles = example_data

    with pytest.raises(ValueError, match="Duplicate fight ID"):
        link_historical_fights([fight, fight], profiles, [])


def test_duplicate_overrides_are_rejected(ambiguous_data):
    fight, profiles, override = ambiguous_data

    with pytest.raises(ValueError, match="Duplicate override"):
        link_historical_fights([fight], profiles, [override, override])


def test_unused_override_is_rejected(example_data):
    fight, profiles = example_data
    override = {
        "source": fight.source,
        "source_bout_id": "absent-fight",
        "fighter_side": 1,
    }

    with pytest.raises(ValueError, match="fights not supplied"):
        link_historical_fights([fight], profiles, [override])


def test_existing_conflicting_link_is_rejected(example_data):
    fight, profiles = example_data
    fight = replace(fight, source_fighter_1_id="different-profile")

    with pytest.raises(ValueError, match="Existing fighter ID conflicts"):
        link_historical_fights([fight], profiles, [])


def test_cannot_assign_same_profile_to_both_participants(example_data):
    fight, profiles = example_data
    fight = replace(fight, fighter_2_name="Alex")

    with pytest.raises(ValueError, match="Both participants have the same ID"):
        link_historical_fights([fight], profiles, [])