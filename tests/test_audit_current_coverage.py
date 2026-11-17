"""Reconcile independently listed events, provider bouts and staged statistics."""

import json
from pathlib import Path

import pytest
from test_stage_current import _prepare, _stage

from upset.data.audit_current_coverage import audit_current_coverage


def _audit(calendar, inventory, stage):
    manifest = json.loads((stage / "manifest.json").read_text())
    return audit_current_coverage(
        calendar, inventory, [stage], "2026-09-25",
        expected_historical_sha256=manifest["input_sha256"]["historical"],
    )


def _inputs(root: Path):
    paths = _prepare(root)
    fight = json.loads(paths[0].read_text())
    paths[0].write_text(json.dumps({**fight, "source_event_id": "event-1"}) + "\n")
    stage = root / "stage"
    _stage(paths, stage)
    calendar = root / "calendar.jsonl"
    calendar.write_text(json.dumps({
        "event_key": "ufc-event-1", "event_date": "2026-09-20",
        "source_url": "https://independent.example/event-1",
        "observed_at_utc": "2026-09-25T10:00:00Z",
    }) + "\n")
    inventory = root / "provider.jsonl"
    inventory.write_text(json.dumps({
        "event_key": "ufc-event-1", "event_date": "2026-09-20",
        "provider": "cito", "source_event_id": "event-1",
        "completed_bout_ids": ["new"],
        "source_url": "https://provider.example/event-1",
        "observed_at_utc": "2026-09-25T11:00:00Z",
    }) + "\n")
    return calendar, inventory, stage


def test_exact_match_is_only_supplied_inventory_match(tmp_path):
    calendar, inventory, stage = _inputs(tmp_path)
    report = _audit(calendar, inventory, stage)
    assert (report["calendar_events"], report["provider_completed_bouts"],
            report["staged_bouts"], report["staged_fighter_stats"]) == (1, 1, 1, 2)
    assert all(not v for v in report["issues"].values())
    assert report["prospective_ready"] is False


def test_missing_whole_event_and_single_bout_reported_separately(tmp_path):
    calendar, inventory, stage = _inputs(tmp_path)
    calendar.write_text(calendar.read_text() + json.dumps({
        "event_key": "ufc-event-2", "event_date": "2026-09-22",
        "source_url": "https://independent.example/event-2",
        "observed_at_utc": "2026-09-25T10:00:00Z",
    }) + "\n")
    row = json.loads(inventory.read_text())
    inventory.write_text(json.dumps({**row, "completed_bout_ids": ["new", "missing"]})
                         + "\n")
    report = _audit(calendar, inventory, stage)
    assert report["issues"]["calendar_events_missing_from_provider_inventory"] == [
        "ufc-event-2"
    ]
    assert report["issues"]["listed_bouts_missing_from_stages"] == [[
        "cito", "missing"
    ]]
    assert report["status"] == "incomplete supplied current data"


def test_wrong_event_and_modified_stage_are_rejected(tmp_path):
    calendar, inventory, stage = _inputs(tmp_path)
    row = json.loads(inventory.read_text())
    inventory.write_text(json.dumps({**row, "source_event_id": "other"}) + "\n")
    report = _audit(calendar, inventory, stage)
    assert report["issues"]["staged_bouts_with_wrong_event"] == [["cito", "new"]]
    path = stage / "fight_stats_identified.jsonl"
    path.write_text(path.read_text() + "\n")
    with pytest.raises(ValueError, match="Changed stage file"):
        _audit(calendar, inventory, stage)


def test_calendar_cannot_claim_future_or_duplicate_events(tmp_path):
    calendar, inventory, stage = _inputs(tmp_path)
    calendar.write_text(calendar.read_text() * 2)
    with pytest.raises(ValueError, match="Duplicate calendar"):
        _audit(calendar, inventory, stage)
