"""Check paired cohort, reference scores and train-only group comparisons."""

import json
import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

from test_defense_ablation import _data

from upset.modeling.defense_ablation import compare_defense
from upset.modeling.defense_groups import (
    GROUPS,
    VARIANTS,
    compare_groups,
    export_defense_groups,
)


class DefensiveGroupTests(unittest.TestCase):
    def test_same_cohort_and_exact_reference_predictions(self):
        rows, defense = _data()
        paired, reference = compare_defense(rows, defense)
        predictions, report = compare_groups(rows, defense)
        self.assertEqual([r["source_bout_id"] for r in predictions],
                         [r["source_bout_id"] for r in paired])
        self.assertEqual(len(GROUPS), 4)
        self.assertEqual(len(VARIANTS), 10)
        for group, original in zip(predictions, paired, strict=True):
            p = group["probabilities_a_win"]
            self.assertEqual(set(p), set(VARIANTS))
            self.assertEqual(p["baseline"],
                             original["baseline_probability_a_win"])
            self.assertEqual(p["all_defense"],
                             original["defense_probability_a_win"])
            self.assertEqual(all(value is None for value in p.values()),
                             group["target_a_win"] is None)
        self.assertEqual(report["validation_bouts"], 16)
        self.assertEqual(report["decisive_bouts"], 15)
        self.assertEqual(report["draw_nc_exclusions"], 1)
        self.assertEqual(report["pooled"]["baseline"]["accuracy"],
                         reference["paired_all_validation"]["baseline"]["accuracy"])
        self.assertTrue(all(fold["scores"]["all_defense"]["decisive_bouts"]
                            == fold["scores"]["baseline"]["decisive_bouts"]
                            for fold in report["folds"]))

    def test_future_history_cannot_change_earlier_forecasts(self):
        rows, defense = _data()
        before, _ = compare_groups(rows, defense)
        changed = {
            key: replace(item, prior_ko_tko_losses=100)
            if item.event_date > "2023-08-19" else item
            for key, item in defense.items()
        }
        after, _ = compare_groups(rows, changed)
        self.assertEqual(before, after)

    def test_export_saves_all_variants_and_source_hashes(self):
        rows, defense = _data()
        with TemporaryDirectory() as directory:
            root = Path(directory)
            matchups, histories = root / "matchups.jsonl", root / "defense.jsonl"
            registry, output = root / "registry.json", root / "results"
            matchups.write_text(
                "".join(json.dumps(row.as_record()) + "\n" for row in rows),
                encoding="utf-8",
            )
            histories.write_text(
                "".join(json.dumps(row.as_record()) + "\n"
                        for row in defense.values()), encoding="utf-8",
            )
            registry.write_text('{"fixture":true}\n', encoding="utf-8")
            report = export_defense_groups(
                matchups, histories, registry, output, "fixture-commit"
            )
            self.assertEqual(report,
                             json.loads((output / "manifest.json").read_text()))
            self.assertEqual(len((output / "predictions.jsonl").read_text()
                                 .splitlines()), 16)
            self.assertEqual(len(report["defensive_history_sha256"]), 64)
            self.assertEqual(report["source_bouts_after_development"], 4)


if __name__ == "__main__":
    unittest.main()
