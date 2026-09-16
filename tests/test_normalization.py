from upset.data.models import Event, Fight, Fighter, RoundStats
from upset.data.normalization import (
    normalize_cito_event,
    normalize_cito_fighter,
    normalize_cito_round,
    parse_control_time,
    parse_landed_attempted,
)


def test_parse_landed_attempted():
    assert parse_landed_attempted("7 of 27") == (7, 27)
    assert parse_landed_attempted("0 of 0") == (0, 0)
    assert parse_landed_attempted("12 of 36") == (12, 36)


def test_parse_control_time():
    assert parse_control_time("1:13") == 73
    assert parse_control_time("0:00") == 0
    assert parse_control_time("2:05") == 125

def test_normalize_cito_round():




    raw_round = {
        "id": "round-123",
        "boutId": "bout-456",
        "fighterSlug": "curtis-blaydes",
        "fighterName": "Curtis Blaydes",
        "round": 1,
        "knockdowns": 0,
        "significantStrikes": "7 of 27",
        "totalStrikes": "7 of 27",
        "takedowns": "1 of 3",
        "submissionAttempts": 0,
        "reversals": 0,
        "controlTime": "1:13",
        "head": "1 of 20",
        "body": "2 of 2",
        "leg": "4 of 5",
        "distance": "6 of 26",
        "clinch": "0 of 0",
        "ground": "1 of 1",
        "lastSyncedAt": "2026-09-12T22:57:42.270Z",
    }

    normalized = normalize_cito_round(raw_round)
    assert isinstance(normalized, RoundStats)

    assert normalized.source == "cito"
    assert normalized.fighter_name == "Curtis Blaydes"
    assert normalized.round_number == 1

    assert normalized.sig_strikes_landed == 7
    assert normalized.sig_strikes_attempted == 27

    assert normalized.takedowns_landed == 1
    assert normalized.takedowns_attempted == 3

    assert normalized.control_seconds == 73

    assert normalized.head_landed == 1
    assert normalized.body_landed == 2
    assert normalized.leg_landed == 4

def test_normalize_cito_fighter():
    raw_fighter = {
        "id": "2df4f188-a33e-463a-a66b-471cfa23e2a0",
        "slug": "islam-makhachev",
        "name": "Islam Makhachev",
        "division": "Welterweight",
        "status": "Active",
        "championStatus": "champion",
        "heightInches": "70",
        "weightLbs": "170",
        "reachInches": "70.5",
        "stance": "Southpaw",
    }

    fighter = normalize_cito_fighter(raw_fighter)

    assert isinstance(fighter, Fighter)

    assert fighter.source == "cito"
    assert fighter.source_fighter_slug == "islam-makhachev"
    assert fighter.name == "Islam Makhachev"

    assert fighter.height_inches == 70.0
    assert fighter.weight_lbs == 170.0
    assert fighter.reach_inches == 70.5

    assert fighter.stance == "Southpaw"
    assert fighter.division == "Welterweight"
    assert fighter.status == "Active"
    assert fighter.champion_status == "champion"

def test_normalize_cito_event():
    raw_event = {
        "id": "event-123",
        "slug": "ufc-fight-night-september-12-2026",
        "title": "Noche UFC",
        "eventDate": "2026-09-12",
        "hasStats": True,
    }

    event = normalize_cito_event(raw_event)

    assert isinstance(event, Event)

    assert event.source == "cito"
    assert event.source_event_id == "event-123"
    assert event.source_event_slug == "ufc-fight-night-september-12-2026"
    assert event.title == "Noche UFC"
    assert event.event_date == "2026-09-12"
    assert event.has_stats is True

def test_fight_model():
    fight = Fight(
        source="cito",
        source_bout_id="12975",
        source_event_id="event-123",
        fighter_1_name="Curtis Blaydes",
        fighter_2_name="Waldo Cortes Acosta",
        winner_name="Curtis Blaydes",
        result_method="Decision - Unanimous",
        result_round=3,
        result_time="5:00",
        weight_class="Heavyweight",
    )

    assert isinstance(fight, Fight)

    assert fight.source == "cito"
    assert fight.source_bout_id == "12975"

    assert fight.fighter_1_name == "Curtis Blaydes"
    assert fight.fighter_2_name == "Waldo Cortes Acosta"

    assert fight.winner_name == "Curtis Blaydes"
    assert fight.result_round == 3