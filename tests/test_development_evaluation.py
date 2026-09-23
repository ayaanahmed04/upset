"""Verify frozen fold boundaries and provenance for development predictions."""

import json
import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

from upset.data.matchups import AMBIGUOUS_OUTCOME, INPUT_FIELDS, MatchupRow
from upset.modeling.evaluation import (
    DEVELOPMENT_FOLDS,
    development_predictions,
    export_development_evaluation,
)

ALICE = "00000000-0000-4000-8000-000000000001"
BOB = "00000000-0000-4000-8000-000000000002"


def _row(year: int, index: int, *, ambiguous: bool = False) -> MatchupRow:
    return MatchupRow(
        source_bout_id=f"bout-{year}-{index}",
        event_date=f"{year}-06-01",
        fighter_a_id=ALICE,
        fighter_b_id=BOB,
        feature_differences={
            f"{field}_diff": (
                index - 2 if field in ("prior_fights", "prior_fight_seconds")
                else float(index - 2)
            )
            for field in INPUT_FIELDS
        },
        target_a_win=None if ambiguous else index % 2,
        training_exclusion_reason=AMBIGUOUS_OUTCOME if ambiguous else None,
        source_winner_label="Draw/NC" if ambiguous else "Alice",
    )


def _history() -> tuple[MatchupRow, ...]:
    return tuple(
        _row(year, index, ambiguous=(year == 2022 and index == 0))
        for year in range(2017, 2025)
        for index in range(4)
    )


class DevelopmentEvaluationTests(unittest.TestCase):
    def test_folds_save_one_row_per_validation_bout_and_exclude_old_test(self):
        predictions, reports = development_predictions(_history())
        self.assertEqual(len(predictions), 16)
        self.assertEqual(len({p["source_bout_id"] for p in predictions}), 16)
        self.assertEqual([r["name"] for r in reports],
                         [fold.name for fold in DEVELOPMENT_FOLDS])
        self.assertTrue(all(p["event_date"] <= "2023-08-19"
                            for p in predictions))
        self.assertEqual([r["validation_draw_nc"] for r in reports], [0, 0, 1, 0])
        ambiguous = [p for p in predictions if p["target_a_win"] is None]
        self.assertEqual(len(ambiguous), 1)
        self.assertIsNone(ambiguous[0]["probability_a_win"])

    def test_future_rows_cannot_change_predictions(self):
        before, _ = development_predictions(_history())
        altered = tuple(
            replace(
                row, target_a_win=1 - row.target_a_win,
                feature_differences={
                    **row.feature_differences, "prior_fights_diff": 10_000_000.0,
                },
            ) if row.event_date > "2023-08-19" else row
            for row in _history()
        )
        after, _ = development_predictions(altered)
        self.assertEqual(before, after)

    def test_manifest_matches_files_and_records_source_hash(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            matchups = root / "matchups.jsonl"
            matchups.write_text(
                "".join(json.dumps(row.as_record()) + "\n" for row in _history()),
                encoding="utf-8",
            )
            registry = root / "registry.json"
            registry.write_text('{"fixture": true}\n', encoding="utf-8")
            output = root / "output"
            report = export_development_evaluation(
                matchups, registry, output, "fixture-commit"
            )
            saved = json.loads((output / "manifest.json").read_text())
            predictions = [
                json.loads(line)
                for line in (output / "predictions.jsonl").read_text().splitlines()
            ]
            self.assertEqual(saved, report)
            self.assertEqual(report["validation_predictions"], len(predictions))
            self.assertEqual(report["validation_draw_nc"], 1)
            self.assertEqual(report["code_commit"], "fixture-commit")
            self.assertEqual(len(report["matchups_sha256"]), 64)
            self.assertEqual(len(report["registry_sha256"]), 64)


if __name__ == "__main__":
    unittest.main()
