"""Detect a full-data history error by independently scanning source bouts."""

import unittest
from dataclasses import replace

from upset.data.audit_prefight_defense import audit_prefight_defense
from upset.data.identify_historical import IdentifiedFight, IdentifiedFightStats
from upset.data.models import Fight, FightStats
from upset.data.prefight_defense import build_defensive_history

SOURCE = "kaggle_ufc_1994_2026"
ALICE = "00000000-0000-4000-8000-000000000001"
BOB = "00000000-0000-4000-8000-000000000002"


def _source():
    fights, stats = [], []
    for bout, day, method in (
        ("first", "2020-01-01", "KO/TKO"),
        ("same-day", "2020-01-01", "Submission"),
        ("later", "2020-02-01", "Decision - Unanimous"),
    ):
        fights.append(IdentifiedFight(
            Fight(
                source=SOURCE, source_bout_id=bout,
                fighter_1_name="Alice", fighter_2_name="Bob",
                source_fighter_1_id="a", source_fighter_2_id="b",
                winner_name="Alice", source_winner_label="Alice",
                event_date=day, result_method=method,
            ), ALICE, BOB
        ))
        for source_id, fighter_id, knockdowns in (
            ("a", ALICE, 1), ("b", BOB, 0)
        ):
            stats.append(IdentifiedFightStats(
                FightStats(
                    source=SOURCE, source_bout_id=bout,
                    source_fighter_id=source_id, fight_duration_seconds=300,
                    source_time_format="3 Rnd (5-5-5)", knockdowns=knockdowns,
                    sig_strikes_landed=10, sig_strikes_attempted=20,
                    takedowns_landed=1, takedowns_attempted=2,
                    submission_attempts=0, control_seconds=None,
                    head_landed=10, body_landed=0, leg_landed=0,
                    distance_landed=10, clinch_landed=0, ground_landed=0,
                ), fighter_id
            ))
    return fights, stats


class SourceAuditTests(unittest.TestCase):
    def test_same_day_counts_and_sampled_source_sums(self):
        fights, stats = _source()
        rows = {
            (row.source_bout_id, row.upset_fighter_id): row
            for row in build_defensive_history(fights, stats)
        }
        report = audit_prefight_defense(fights, stats, rows)
        self.assertEqual(report["all_defensive_rows_count_checked"], 6)
        self.assertEqual(report["sampled_rows_all_source_totals_checked"], 6)
        self.assertEqual(report["comparison"], "matched")

        key = "later", BOB
        wrong_count = dict(rows)
        wrong_count[key] = replace(wrong_count[key], prior_fights=1)
        with self.assertRaisesRegex(ValueError, "strictly-earlier count"):
            audit_prefight_defense(fights, stats, wrong_count)

        wrong_damage = dict(rows)
        wrong_damage[key] = replace(
            wrong_damage[key], prior_knockdowns_conceded=0
        )
        with self.assertRaisesRegex(ValueError, "prior_knockdowns_conceded"):
            audit_prefight_defense(fights, stats, wrong_damage)


if __name__ == "__main__":
    unittest.main()
