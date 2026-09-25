"""Current completed bouts require reviewed links and complete paired stats."""

import hashlib
import json
import unittest
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory

from upset.data.models import Fight, FightStats
from upset.data.stage_current import stage_completed_fights

A = "00000000-0000-4000-8000-000000000001"
B = "00000000-0000-4000-8000-000000000002"
NOW = datetime(2026, 9, 25, 12, tzinfo=UTC)


def _prepare(root: Path):
    historic = asdict(Fight(
        source="kaggle", source_bout_id="old", fighter_1_name="A",
        fighter_2_name="B", source_fighter_1_id="hist-a",
        source_fighter_2_id="hist-b", winner_name="A", source_winner_label="A",
        event_date="2026-03-07",
    ))
    historical = root / "historical.jsonl"
    historical.write_text(json.dumps({**historic, "upset_fighter_1_id": A,
                                      "upset_fighter_2_id": B}) + "\n")
    fight = asdict(Fight(
        source="cito", source_bout_id="new", fighter_1_name="A",
        fighter_2_name="B", source_fighter_1_id="cito-a",
        source_fighter_2_id="cito-b", winner_name="B", source_winner_label="B",
        event_date="2026-09-20", source_url="https://example.org/new",
    ))
    fights = root / "fights.jsonl"
    fights.write_text(json.dumps(fight) + "\n")
    stats = root / "stats.jsonl"
    values = [asdict(FightStats(
        source="cito", source_bout_id="new", source_fighter_id=source,
        fight_duration_seconds=900, source_time_format="3x5",
        knockdowns=0, sig_strikes_landed=5, sig_strikes_attempted=10,
        takedowns_landed=1, takedowns_attempted=3, submission_attempts=0,
        control_seconds=12, head_landed=3, body_landed=2, leg_landed=0,
        distance_landed=4, clinch_landed=1, ground_landed=0,
    )) for source in ("cito-a", "cito-b")]
    stats.write_text("".join(json.dumps(row) + "\n" for row in values))
    registry = root / "registry.json"
    registry.write_text(json.dumps({
        "schema_version": 1,
        "identities": [{"upset_fighter_id": f, "display_name": f} for f in (A, B)],
        "provider_links": [{"provider": "cito", "provider_fighter_id": s,
                            "upset_fighter_id": f, "evidence": "fixture"}
                           for f, s in ((A, "cito-a"), (B, "cito-b"))],
    }))
    return fights, stats, registry, historical


def _stage(paths, output, **kwargs):
    return stage_completed_fights(
        *paths, output,
        expected_historical_sha256=hashlib.sha256(paths[3].read_bytes()).hexdigest(),
        observed_at=NOW, **kwargs,
    )


class StageCurrentTests(unittest.TestCase):
    def test_readback_and_no_overwrite(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            paths = _prepare(root)
            output = root / "staged"
            report = _stage(paths, output)
            self.assertEqual((report["fights"], report["fighter_stats"]), (1, 2))
            saved = json.loads((output / "fights_identified.jsonl").read_text())
            self.assertEqual((saved["upset_fighter_1_id"],
                              saved["upset_fighter_2_id"]), (A, B))
            with self.assertRaisesRegex(ValueError, "Output exists"):
                _stage(paths, output)

    def test_rejects_unreviewed_link_duplicate_pair_and_missing_opponent_stats(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            fights, stats, _, _ = paths = _prepare(root)
            original = json.loads(fights.read_text())
            for change, message in (
                ({"source_fighter_1_id": "not-reviewed"}, "Unreviewed"),
                ({"event_date": "2026-03-07"}, "pre-cutoff"),
                ({"winner_name": "unknown"}, "Unresolved"),
            ):
                fights.write_text(json.dumps({**original, **change}) + "\n")
                with self.assertRaisesRegex(ValueError, message):
                    _stage(paths, root / "output")
            fights.write_text(json.dumps(original) + "\n")
            stats.write_text(stats.read_text().splitlines()[0] + "\n")
            with self.assertRaisesRegex(ValueError, "Missing statistics"):
                _stage(paths, root / "output")
            self.assertFalse((root / "output").exists())

    def test_rejects_changed_historical_snapshot_before_staging(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            paths = _prepare(root)
            with self.assertRaisesRegex(ValueError, "accepted snapshot"):
                stage_completed_fights(*paths, root / "output", observed_at=NOW)


if __name__ == "__main__":
    unittest.main()
