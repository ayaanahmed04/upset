"""Check source auditing, identical cohorts and fixed reference forecasts."""

import json
import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

from test_defense_ablation import _data
from test_prefight_defense import _bout

from upset.data.prefight_outcomes import build_outcome_history
from upset.modeling.defense_ablation import compare_defense
from upset.modeling.outcome_recency import (
    VARIANTS,
    compare_outcome_recency,
    export_outcome_comparison,
    join_outcomes,
)


def _fixture():
    rows, defensive = _data()
    fights = [_bout(
        row.source_bout_id, row.event_date,
        winner=(None if row.target_a_win is None
                else "Alice" if row.target_a_win else "Bob"),
    ) for row in rows]
    outcomes = build_outcome_history(fights)
    return rows, defensive, fights, {
        (row.source_bout_id, row.upset_fighter_id): row for row in outcomes
    }


class OutcomeRecencyTests(unittest.TestCase):
    def test_exact_prior_references_and_same_cohort(self):
        rows, defensive, _, outcomes = _fixture()
        original, _ = compare_defense(rows, defensive)
        predictions, report = compare_outcome_recency(rows, defensive, outcomes)
        self.assertEqual([r["source_bout_id"] for r in predictions],
                         [r["source_bout_id"] for r in original])
        self.assertEqual((report["decisive_bouts"],
                          report["draw_nc_exclusions"]), (15, 1))
        self.assertEqual(len(report["folds"]), 4)
        for row, reference in zip(predictions, original, strict=True):
            probabilities = row["probabilities_a_win"]
            self.assertEqual(set(probabilities), set(VARIANTS))
            self.assertEqual(probabilities["baseline"],
                             reference["baseline_probability_a_win"])
            self.assertEqual(probabilities["all_defense"],
                             reference["defense_probability_a_win"])
            self.assertEqual(all(p is None for p in probabilities.values()),
                             row["target_a_win"] is None)

    def test_future_results_cannot_change_earlier_predictions(self):
        rows, defensive, fights, outcomes = _fixture()
        before, _ = compare_outcome_recency(rows, defensive, outcomes)
        changed = [replace(f, fight=replace(f.fight,
                   winner_name="Alice", source_winner_label="Alice"))
                   if f.fight.event_date > "2023-08-19" else f
                   for f in fights]
        new = {(r.source_bout_id, r.upset_fighter_id): r
               for r in build_outcome_history(changed)}
        after, _ = compare_outcome_recency(rows, defensive, new)
        self.assertEqual(before, after)

    def test_join_rejects_missing_id_and_wrong_date(self):
        rows, _, _, outcomes = _fixture()
        missing = dict(outcomes)
        key = rows[0].source_bout_id, rows[0].fighter_a_id
        missing.pop(key)
        with self.assertRaisesRegex(ValueError, "Outcome join keys"):
            join_outcomes(rows, missing)
        wrong_date = dict(outcomes)
        wrong_date[key] = replace(wrong_date[key], event_date="2020-01-01")
        with self.assertRaisesRegex(ValueError, "dates differ"):
            join_outcomes(rows, wrong_date)

    def test_export_saves_audited_rows_and_hashes(self):
        rows, defensive, fights, outcomes = _fixture()
        with TemporaryDirectory() as directory:
            root = Path(directory)
            matchups, defenses = root / "matchups.jsonl", root / "defense.jsonl"
            histories, sources = root / "outcomes.jsonl", root / "fights.jsonl"
            registry, output = root / "registry.json", root / "output"
            for path, records in (
                (matchups, rows), (defenses, defensive.values()),
                (histories, outcomes.values()), (sources, fights),
            ):
                path.write_text("".join(json.dumps(r.as_record()) + "\n"
                                        for r in records), encoding="utf-8")
            registry.write_text('{"fixture":true}\n', encoding="utf-8")
            report = export_outcome_comparison(
                matchups, defenses, histories, sources, registry, output,
                "fixture-commit",
            )
            self.assertEqual(report,
                             json.loads((output / "manifest.json").read_text()))
            self.assertEqual(report["outcome_audit"]["all_outcome_rows_checked"],
                             64)
            self.assertEqual(len((output / "predictions.jsonl").read_text()
                                 .splitlines()), 16)
            self.assertEqual(report["source_bouts_after_development"], 4)
            self.assertEqual(len(report["identified_fights_sha256"]), 64)


if __name__ == "__main__":
    unittest.main()
