import pytest

from upset.data.models import Event, Fight
from upset.data.normalization import normalize_cito_fight


@pytest.fixture
def raw_bout():
    """Give each test a fresh example so tests cannot affect each other."""
    return {
        "id": "bout-123",
        "eventSlug": "example-event",
        "winnerFighterSlug": "fighter-a",
        "method": "Decision - Unanimous",
        "resultRound": 3,
        "resultTime": "5:00",
        "weightClass": "Heavyweight",
        "fighters": [
            {
                "id": "participation-a",
                "fighterId": "profile-a",
                "fighterSlug": "fighter-a",
                "fighterName": "Fighter A",
            },
            {
                "id": "participation-b",
                "fighterId": "profile-b",
                "fighterSlug": "fighter-b",
                "fighterName": "Fighter B",
            },
        ],
    }


def test_normalize_fight_preserves_fields(raw_bout):
    fight = normalize_cito_fight(raw_bout)

    assert isinstance(fight, Fight)
    assert fight.source == "cito"
    assert fight.source_bout_id == "bout-123"
    assert fight.fighter_1_name == "Fighter A"
    assert fight.fighter_2_name == "Fighter B"

    # Use the profile IDs, not the surrounding participation-record IDs.
    assert fight.source_fighter_1_id == "profile-a"
    assert fight.source_fighter_2_id == "profile-b"

    assert fight.winner_name == "Fighter A"
    assert fight.result_method == "Decision - Unanimous"
    assert fight.result_round == 3
    assert fight.result_time == "5:00"
    assert fight.weight_class == "Heavyweight"
    assert fight.source_event_id is None


def test_winner_does_not_depend_on_fighter_order(raw_bout):
    raw_bout["fighters"].reverse()

    fight = normalize_cito_fight(raw_bout)

    assert fight.fighter_1_name == "Fighter B"
    assert fight.source_fighter_1_id == "profile-b"
    assert fight.fighter_2_name == "Fighter A"
    assert fight.source_fighter_2_id == "profile-a"
    assert fight.winner_name == "Fighter A"


def test_missing_values_remain_none(raw_bout):
    raw_bout["winnerFighterSlug"] = None
    raw_bout["resultRound"] = None
    raw_bout["resultTime"] = None
    raw_bout["method"] = None
    raw_bout["fighters"][0]["fighterId"] = None
    del raw_bout["fighters"][1]["fighterId"]

    fight = normalize_cito_fight(raw_bout)

    assert fight.winner_name is None
    assert fight.result_round is None
    assert fight.result_time is None
    assert fight.result_method is None
    assert fight.source_fighter_1_id is None
    assert fight.source_fighter_2_id is None


@pytest.mark.parametrize("fighter_count", [0, 1, 3])
def test_rejects_wrong_number_of_fighters(raw_bout, fighter_count):
    raw_bout["fighters"] = [
        raw_bout["fighters"][0].copy()
        for _ in range(fighter_count)
    ]

    with pytest.raises(ValueError, match="exactly two fighters"):
        normalize_cito_fight(raw_bout)


def test_rejects_winner_not_in_fight(raw_bout):
    raw_bout["winnerFighterSlug"] = "someone-else"

    with pytest.raises(ValueError, match="Winner slug"):
        normalize_cito_fight(raw_bout)


def test_connects_matching_event_using_id(raw_bout):
    event = Event(
        source="cito",
        source_event_id="event-456",
        source_event_slug="example-event",
        title="Example Event",
        event_date="2026-09-12",
    )

    fight = normalize_cito_fight(raw_bout, event=event)

    # The connection must use the ID, not "example-event".
    assert fight.source_event_id == "event-456"


@pytest.mark.parametrize(
    ("source", "slug"),
    [
        ("cito", "wrong-event"),
        ("another-provider", "example-event"),
    ],
)
def test_rejects_mismatched_event(raw_bout, source, slug):
    event = Event(
        source=source,
        source_event_id="event-456",
        source_event_slug=slug,
        title="Example Event",
        event_date="2026-09-12",
    )

    with pytest.raises(ValueError, match="Event does not match"):
        normalize_cito_fight(raw_bout, event=event)