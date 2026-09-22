"""Check source coverage before turning durability observations into features."""

import unittest
from dataclasses import replace

from upset.data.audit_durability_sources import audit_durability_sources
from upset.data.identify_historical import IdentifiedFight, IdentifiedFightStats
from upset.data.models import Fight, FightStats
from upset.data.probe_cito_rounds import describe_round_payload

SOURCE = "kaggle_ufc_1994_2026"
ALICE = "00000000-0000-4000-8000-000000000001"
BOB = "00000000-0000-4000-8000-000000000002"


def _fight(bout="bout-1", *, method="KO/TKO"):
    return IdentifiedFight(
        Fight(
            source=SOURCE,
            source_bout_id=bout,
            fighter_1_name="Alice",
            fighter_2_name="Bob",
            source_fighter_1_id="profile-a",
            source_fighter_2_id="profile-b",
            event_date="2020-01-01",
            winner_name="Alice",
            source_winner_label="Alice",
            result_method=method,
        ),
        ALICE,
        BOB,
    )


def _stats(bout="bout-1", *, knockdowns_a=2, knockdowns_b=0):
    def one(source_id, fighter_id, knockdowns):
        return IdentifiedFightStats(
            FightStats(
                source=SOURCE,
                source_bout_id=bout,
                source_fighter_id=source_id,
                fight_duration_seconds=300,
                source_time_format="3 Rnd (5-5-5)",
                knockdowns=knockdowns,
                sig_strikes_landed=10,
                sig_strikes_attempted=20,
                takedowns_landed=0,
                takedowns_attempted=0,
                submission_attempts=0,
                control_seconds=None,
                head_landed=10,
                body_landed=0,
                leg_landed=0,
                distance_landed=10,
                clinch_landed=0,
                ground_landed=0,
            ),
            fighter_id,
        )

    return [
        one("profile-a", ALICE, knockdowns_a),
        one("profile-b", BOB, knockdowns_b),
    ]


class DurabilitySourceAuditTests(unittest.TestCase):
    def test_opponent_knockdowns_are_conceded_by_the_other_fighter(self):
        report = audit_durability_sources([_fight()], list(reversed(_stats())))
        self.assertEqual(report["recorded_knockdowns"], 2)
        self.assertEqual(
            report["fighter_fight_rows_with_opponent_recorded_knockdown"], 1
        )
        self.assertEqual(report["fighters_with_recorded_knockdowns_conceded"], 1)
        self.assertEqual(report["max_recorded_knockdowns_conceded_by_one_fighter"], 2)
        self.assertEqual(report["method_labels"], {"KO/TKO": 1})

    def test_methods_are_counted_verbatim_without_guessing_stoppages(self):
        fight = _fight()
        second = _fight("bout-2", method="Overturned")
        ambiguous = replace(
            second,
            fight=replace(
                second.fight, winner_name=None, source_winner_label="Draw/NC"
            ),
        )
        report = audit_durability_sources(
            [fight, ambiguous], _stats() + _stats("bout-2", knockdowns_a=0)
        )
        self.assertEqual(report["fights"], 2)
        self.assertEqual(report["fighter_fight_rows"], 4)
        self.assertEqual(report["combined_draw_nc"], 1)
        self.assertEqual(report["method_labels"], {"KO/TKO": 1, "Overturned": 1})

    def test_missing_extra_duplicate_and_mismatched_stats_are_rejected(self):
        fight, stats = _fight(), _stats()
        problems = (
            (stats[:1], "Missing fight statistics"),
            (stats + _stats("unknown"), "Unexpected fight statistics outside"),
            (stats + stats[:1], "duplicate fight statistics"),
            ([replace(stats[0], upset_fighter_id=BOB), stats[1]], "identities differ"),
            (
                [
                    replace(stats[0], stats=replace(stats[0].stats, knockdowns=-1)),
                    stats[1],
                ],
                "Invalid knockdown",
            ),
        )
        for records, message in problems:
            with self.subTest(message=message), self.assertRaisesRegex(
                ValueError, message
            ):
                audit_durability_sources([fight], records)

    def test_cito_probe_reports_shape_without_record_values(self):
        flat = describe_round_payload(
            {"success": True, "data": [{"round": 1, "fighterSlug": "alice"}]}
        )
        self.assertEqual(flat["row_count"], 1)
        self.assertEqual(flat["first_row_keys"], ["fighterSlug", "round"])
        self.assertNotIn("alice", str(flat))

        nested = describe_round_payload(
            {"data": {"rounds": [{"boutId": "bout-1"}], "total": 1}}
        )
        self.assertEqual(nested["list_fields"]["rounds"]["rows"], 1)
        self.assertEqual(nested["list_fields"]["rounds"]["first_row_keys"], ["boutId"])


if __name__ == "__main__":
    unittest.main()
