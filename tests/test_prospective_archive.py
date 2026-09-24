"""Forecast records must be pre-event, source-linked and resistant to edits."""

import hashlib
import json
import unittest
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

from upset.modeling.baseline import FEATURE_COLUMNS
from upset.modeling.prospective_archive import (
    record_forecast_batch,
    verify_forecast_batch,
)

ALICE = "00000000-0000-4000-8000-000000000001"
BOB = "00000000-0000-4000-8000-000000000002"
NOW = datetime(2026, 9, 24, 20, 0, tzinfo=timezone.utc)


def _inputs(root: Path) -> tuple[Path, ...]:
    schedule = root / "schedule.jsonl"
    forecasts = root / "forecasts.jsonl"
    spec = root / "model_spec.json"
    model = root / "model.bin"
    registry = root / "registry.json"
    schedule.write_text(json.dumps({
        "provider": "cito", "source_bout_id": "future-bout",
        "source_fighter_a_id": "cito-a", "source_fighter_b_id": "cito-b",
        "fighter_a_id": ALICE, "fighter_b_id": BOB,
        "scheduled_start_utc": "2026-09-26T00:00:00Z",
        "source_observed_at_utc": "2026-09-24T19:50:00Z",
        "source_url": "https://example.org/schedule/bout",
    }) + "\n", encoding="utf-8")
    forecasts.write_text(json.dumps({
        "source_bout_id": "future-bout", "fighter_a_id": ALICE,
        "fighter_b_id": BOB, "probability_a_win": 0.61,
        "feature_differences": {column: None for column in FEATURE_COLUMNS},
    }) + "\n", encoding="utf-8")
    model.write_bytes(b"synthetic model artifact; never execute")
    spec.write_text(json.dumps({
        "model_name": "synthetic baseline",
        "code_commit": "a" * 40,
        "training_through_date": "2026-03-07",
        "training_input_sha256": "b" * 64,
        "model_artifact_sha256": hashlib.sha256(model.read_bytes()).hexdigest(),
        "feature_columns": list(FEATURE_COLUMNS),
    }), encoding="utf-8")
    registry.write_text(json.dumps({
        "schema_version": 1,
        "identities": [
            {"upset_fighter_id": ALICE, "display_name": "Alice"},
            {"upset_fighter_id": BOB, "display_name": "Bob"},
        ],
        "provider_links": [
            {"provider": "cito", "provider_fighter_id": "cito-a",
             "upset_fighter_id": ALICE, "evidence": "fixture"},
            {"provider": "cito", "provider_fighter_id": "cito-b",
             "upset_fighter_id": BOB, "evidence": "fixture"},
        ],
    }), encoding="utf-8")
    return schedule, forecasts, spec, model, registry


class ProspectiveArchiveTests(unittest.TestCase):
    def test_verified_batch_is_locked_and_copied_bytes_detect_edits(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            inputs = _inputs(root)
            archive = root / "archive"
            batch = record_forecast_batch(*inputs, archive, recorded_at=NOW)
            report = verify_forecast_batch(batch)
            self.assertEqual(report["bout_keys"], [["cito", "future-bout"]])
            self.assertEqual(report["recorded_at_utc"], "2026-09-24T20:00:00Z")
            self.assertEqual((batch / "model.bin").read_bytes(), inputs[3].read_bytes())
            with self.assertRaisesRegex(ValueError, "already has a locked"):
                record_forecast_batch(*inputs, archive, recorded_at=NOW)
            (batch / "forecasts.jsonl").write_text("changed\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "was modified"):
                verify_forecast_batch(batch)

    def test_rejects_late_or_stale_schedule_and_unreviewed_links(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            inputs = _inputs(root)
            schedule = inputs[0]
            original = json.loads(schedule.read_text())
            for change, error in (
                ({"scheduled_start_utc": "2026-09-24T20:30:00Z"},
                 "stale or too close"),
                ({"source_observed_at_utc": "2026-09-20T20:00:00Z"},
                 "stale or too close"),
                ({"source_fighter_a_id": "unreviewed"},
                 "Unreviewed provider fighter link"),
            ):
                schedule.write_text(json.dumps({**original, **change}) + "\n",
                                    encoding="utf-8")
                with self.assertRaisesRegex(ValueError, error):
                    record_forecast_batch(*inputs, root / "archive",
                                          recorded_at=NOW)
            self.assertFalse((root / "archive").exists())

    def test_rejects_results_and_changed_model_before_any_write(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            inputs = _inputs(root)
            forecast = json.loads(inputs[1].read_text())
            inputs[1].write_text(json.dumps({**forecast, "winner": "Alice"}) + "\n",
                                 encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Unexpected fields"):
                record_forecast_batch(*inputs, root / "archive", recorded_at=NOW)
            inputs[1].write_text(json.dumps(forecast) + "\n", encoding="utf-8")
            inputs[3].write_bytes(b"changed model")
            with self.assertRaisesRegex(ValueError, "does not match"):
                record_forecast_batch(*inputs, root / "archive", recorded_at=NOW)
            self.assertFalse((root / "archive").exists())


if __name__ == "__main__":
    unittest.main()
