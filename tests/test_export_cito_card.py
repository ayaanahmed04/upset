"""Card conversion must reconcile provider endpoints without guessing identities."""

import json
from copy import deepcopy
from pathlib import Path

import pytest

from upset.data.collect_cito_card import collect_card
from upset.data.export_cito_card import _normalize_card, export_cito_card


def _stat(bout, name, slug, identifier, *, strikes="0 of 0", round_number=None):
    row = {
        "id": identifier, "boutId": bout, "fighterName": name,
        "fighterSlug": slug, "knockdowns": 0, "submissionAttempts": 0,
        "reversals": 0, "significantStrikes": strikes,
        "totalStrikes": strikes, "takedowns": "0 of 0",
        "head": strikes, "body": "0 of 0", "leg": "0 of 0",
        "distance": strikes, "clinch": "0 of 0", "ground": "0 of 0",
        "controlTime": "0:00",
    }
    if round_number is not None:
        row["round"] = round_number
    return row


def _card():
    event = {
        "id": "event-1", "slug": "ufc-test-card", "title": "UFC Test",
        "eventDate": "2026-08-29", "status": "completed", "hasStats": True,
    }
    bout = {
        "id": "bout-1", "eventSlug": event["slug"], "status": "completed",
        "isCancelled": False, "hasStats": True, "winnerFighterSlug": "fighter-a",
        "method": "SUB", "resultRound": 2, "resultTime": "1:48",
        "fighters": [
            {"fighterId": "profile-a", "fighterSlug": "fighter-a",
             "fighterName": "Fighter A", "outcome": "win"},
            {"fighterId": "profile-b", "fighterSlug": "fighter-b-alias",
             "fighterName": "Fighter B", "outcome": "loss"},
        ],
    }
    totals = [
        _stat("bout-1", "Fighter A", "fighter-a", "total-a", strikes="2 of 3"),
        _stat("bout-1", "Fighter B", "fighter-b", "total-b"),
    ]
    bout["boutStats"] = totals
    event["bouts"] = [bout]
    stats = {
        "event": dict(event), "bouts": [dict(bout)], "boutStats": totals,
        "roundStats": [
            _stat("bout-1", "Fighter A", "fighter-a", "a-1", round_number=1),
            _stat("bout-1", "Fighter A", "fighter-a", "a-2",
                  strikes="2 of 3", round_number=2),
            _stat("bout-1", "Fighter B", "fighter-b", "b-1", round_number=1),
            _stat("bout-1", "Fighter B", "fighter-b", "b-2", round_number=2),
        ],
    }
    return {"event": event, "bouts": [bout], "stats": stats}


class Response:
    status_code = 200

    def __init__(self, data):
        self.data = data

    def json(self):
        return {"success": True, "data": self.data}


def test_real_shape_exports_paired_totals_and_flags_slug_alias(tmp_path):
    payloads = _card()
    responses = iter(Response(payloads[k]) for k in ("event", "bouts", "stats"))
    card = tmp_path / "raw"
    collect_card("ufc-test-card", card, "secret-key",
                 lambda *a, **k: next(responses), delay=0)
    output = tmp_path / "canonical"
    registry = Path(__file__).resolve().parents[1] / "data/mappings/fighter_registry.json"
    report = export_cito_card(card, registry, output)
    assert (report["fights"], report["fighter_stats"], report["round_rows_reconciled"]) == (
        1, 2, 4
    )
    assert report["unlinked_provider_fighters"] == 2
    assert report["provider_slug_differences"] == [{
        "source_bout_id": "bout-1", "cito_fighter_id": "profile-b",
        "bout_fighter_slug": "fighter-b-alias", "stats_fighter_slug": "fighter-b",
    }]
    fight = json.loads((output / "fights.jsonl").read_text())
    rows = [json.loads(line) for line in (output / "fight_stats.jsonl").read_text().splitlines()]
    assert (fight["source_winner_label"], fight["result_method"],
            fight["event_date"]) == ("Fighter A", "Submission", "2026-08-29")
    assert {row["source_fighter_id"] for row in rows} == {"profile-a", "profile-b"}
    assert all(row["fight_duration_seconds"] == 408 for row in rows)
    assert all(row["source_time_format"] == "5 min rounds" for row in rows)
    review = json.loads((output / "fighter_link_review.json").read_text())
    assert all(row["reviewed_upset_fighter_id"] is None for row in review)
    assert json.loads((output / "manifest.json").read_text()) == report
    with pytest.raises(ValueError, match="Output exists"):
        export_cito_card(card, registry, output)


def test_disagreed_bout_outcome_is_rejected():
    payloads = _card()
    payloads["stats"]["bouts"][0]["winnerFighterSlug"] = "fighter-b-alias"
    with pytest.raises(ValueError, match="stats bout list differs"):
        _normalize_card(payloads)


def test_incorrect_round_sum_is_rejected():
    payloads = _card()
    payloads["stats"]["roundStats"][1]["significantStrikes"] = "1 of 3"
    payloads["stats"]["roundStats"][1]["head"] = "1 of 3"
    payloads["stats"]["roundStats"][1]["distance"] = "1 of 3"
    with pytest.raises(ValueError, match="Round totals differ"):
        _normalize_card(payloads)


def test_embedded_event_stats_disagreement_is_rejected():
    payloads = _card()
    payloads["event"]["bouts"] = deepcopy(payloads["event"]["bouts"])
    payloads["event"]["bouts"][0]["boutStats"][0]["head"] = "1 of 3"
    with pytest.raises(ValueError, match="event fighter totals disagree"):
        _normalize_card(payloads)


def test_changed_raw_snapshot_does_not_export(tmp_path):
    payloads = _card()
    responses = iter(Response(payloads[k]) for k in ("event", "bouts", "stats"))
    card = tmp_path / "raw"
    collect_card("ufc-test-card", card, "secret-key",
                 lambda *a, **k: next(responses), delay=0)
    (card / "bouts.json").write_text((card / "bouts.json").read_text() + " ")
    output = tmp_path / "canonical"
    registry = Path(__file__).resolve().parents[1] / "data/mappings/fighter_registry.json"
    with pytest.raises(ValueError, match="hash differs"):
        export_cito_card(card, registry, output)
    assert not output.exists()
