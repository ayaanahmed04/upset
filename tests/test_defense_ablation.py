"""Pair defensive and original forecasts on the same dated validation bouts."""

import json
import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

from upset.data.matchups import AMBIGUOUS_OUTCOME, INPUT_FIELDS, MatchupRow
from upset.data.prefight_defense import DefensiveHistory
from upset.modeling.defense_ablation import (
    compare_defense,
    export_defense_ablation,
    join_defense,
    read_defensive_history,
)
from upset.modeling.evaluation import development_predictions

ALICE = "00000000-0000-4000-8000-000000000001"
BOB = "00000000-0000-4000-8000-000000000002"


def _data():
    rows, defensive = [], {}
    for year in range(2017, 2025):
        for index in range(4):
            bout = f"bout-{year}-{index}"
            ambiguous = year == 2022 and index == 0
            rows.append(MatchupRow(
                source_bout_id=bout,
                event_date=f"{year}-06-01",
                fighter_a_id=ALICE, fighter_b_id=BOB,
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
            ))
            for fighter_id, value in ((ALICE, index + 1), (BOB, 4 - index)):
                fights = year - 2017
                seconds = fights * 300
                sig = fights * value
                sig_attempts = fights * 10
                td = fights * (value % 2)
                td_attempts = fights * 2
                knockdowns = fights * (value % 2)
                defensive[(bout, fighter_id)] = DefensiveHistory(
                    source_bout_id=bout,
                    event_date=f"{year}-06-01",
                    upset_fighter_id=fighter_id,
                    prior_fights=fights,
                    prior_fight_seconds=seconds,
                    prior_sig_strikes_absorbed=sig,
                    prior_opponent_sig_strikes_attempted=sig_attempts,
                    prior_takedowns_conceded=td,
                    prior_opponent_takedowns_attempted=td_attempts,
                    prior_knockdowns_conceded=knockdowns,
                    prior_bouts_with_knockdown_conceded=knockdowns,
                    prior_ko_tko_losses=fights if fighter_id == ALICE else 0,
                    prior_submission_losses=fights if fighter_id == BOB else 0,
                    sig_strikes_absorbed_per_minute=sig * 60 / seconds
                    if seconds else None,
                    sig_strike_defense=1 - sig / sig_attempts
                    if sig_attempts else None,
                    takedowns_conceded_per_15_minutes=td * 900 / seconds
                    if seconds else None,
                    takedown_defense=1 - td / td_attempts
                    if td_attempts else None,
                    knockdowns_conceded_per_15_minutes=knockdowns * 900 / seconds
                    if seconds else None,
                )
    return tuple(rows), defensive


class DefensiveAblationTests(unittest.TestCase):
    def test_identical_cohort_and_baseline_probabilities(self):
        rows, defense = _data()
        paired, report = compare_defense(rows, defense)
        original, _ = development_predictions(rows)
        self.assertEqual(len(paired), len(original))
        self.assertEqual([p["source_bout_id"] for p in paired],
                         [p["source_bout_id"] for p in original])
        for current, before in zip(paired, original, strict=True):
            self.assertEqual(current["baseline_probability_a_win"],
                             before["probability_a_win"])
            self.assertEqual(current["target_a_win"], before["target_a_win"])
            self.assertEqual(current["defense_probability_a_win"] is None,
                             before["target_a_win"] is None)
            self.assertLessEqual(current["event_date"], "2023-08-19")
        self.assertEqual(report["paired_all_validation"]["decisive_bouts"], 15)
        self.assertEqual(report["paired_all_validation"]["draw_nc_exclusions"], 1)
        self.assertEqual(len(report["folds"]), 4)
        self.assertEqual(
            len(report["paired_all_validation"]["date_cluster_bootstrap_95_percent"]
                ["accuracy_delta"]),
            2,
        )

    def test_missing_or_mismatched_identity_and_date_rejected(self):
        rows, defense = _data()
        missing = dict(defense)
        missing.pop((rows[0].source_bout_id, ALICE))
        with self.assertRaisesRegex(ValueError, "join mismatch"):
            join_defense(rows, missing)
        wrong_date = dict(defense)
        key = rows[0].source_bout_id, ALICE
        wrong_date[key] = replace(wrong_date[key], event_date="2018-06-01")
        with self.assertRaisesRegex(ValueError, "dates differ"):
            join_defense(rows, wrong_date)

    def test_later_defensive_rows_cannot_change_earlier_predictions(self):
        rows, defense = _data()
        original, _ = compare_defense(rows, defense)
        changed = dict(defense)
        for key, item in defense.items():
            if item.event_date > "2023-08-19":
                changed[key] = replace(item, prior_ko_tko_losses=100)
        after, _ = compare_defense(rows, changed)
        self.assertEqual(original, after)

    def test_reader_rejects_inconsistent_rate_and_duplicate(self):
        _, defense = _data()
        populated = next(row for row in defense.values() if row.prior_fights > 0)
        with TemporaryDirectory() as directory:
            path = Path(directory) / "defense.jsonl"
            record = populated.as_record()
            record["sig_strike_defense"] = 0.0
            path.write_text(json.dumps(record) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Inconsistent sig_strike_defense"):
                read_defensive_history(path)
            line = json.dumps(populated.as_record()) + "\n"
            path.write_text(line * 2, encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Duplicate defensive row"):
                read_defensive_history(path)

    def test_export_writes_paired_rows_and_source_hashes(self):
        rows, defense = _data()
        with TemporaryDirectory() as directory:
            root = Path(directory)
            matchups = root / "matchups.jsonl"
            defenses = root / "defenses.jsonl"
            registry = root / "registry.json"
            output = root / "output"
            matchups.write_text(
                "".join(json.dumps(row.as_record()) + "\n" for row in rows),
                encoding="utf-8",
            )
            defenses.write_text(
                "".join(json.dumps(row.as_record()) + "\n"
                        for row in defense.values()),
                encoding="utf-8",
            )
            registry.write_text('{"fixture": true}\n', encoding="utf-8")
            report = export_defense_ablation(
                matchups, defenses, registry, output, "fixture-commit"
            )
            saved = json.loads((output / "manifest.json").read_text())
            lines = (output / "predictions.jsonl").read_text().splitlines()
            self.assertEqual(report, saved)
            self.assertEqual(len(lines), 16)
            self.assertEqual(report["code_commit"], "fixture-commit")
            self.assertEqual(len(report["defensive_history_sha256"]), 64)


if __name__ == "__main__":
    unittest.main()
