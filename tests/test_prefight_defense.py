"""Defensive history must use only paired, earlier fight observations."""

import unittest
import json
from dataclasses import asdict, replace
from pathlib import Path
from tempfile import TemporaryDirectory

from upset.data.export_prefight_defense import export_prefight_defense
from upset.data.identify_historical import IdentifiedFight, IdentifiedFightStats
from upset.data.models import Fight, FightStats
from upset.data.prefight_defense import build_defensive_history

SOURCE = "kaggle_ufc_1994_2026"
ALICE = "00000000-0000-4000-8000-000000000001"
BOB = "00000000-0000-4000-8000-000000000002"


def _bout(bout: str, date: str, *, winner="Alice", method="KO/TKO"):
    return IdentifiedFight(
        Fight(
            source=SOURCE, source_bout_id=bout,
            fighter_1_name="Alice", fighter_2_name="Bob",
            source_fighter_1_id="a", source_fighter_2_id="b",
            event_date=date, winner_name=winner,
            source_winner_label=winner if winner else "Draw/NC",
            result_method=method,
        ),
        ALICE, BOB,
    )


def _pair(bout: str, *, seconds=300, a_kd=2, b_kd=0, a_sig=10, b_sig=5):
    def make(source_id, fighter_id, kd, sig, attempts, td):
        return IdentifiedFightStats(
            FightStats(
                source=SOURCE, source_bout_id=bout, source_fighter_id=source_id,
                fight_duration_seconds=seconds, source_time_format="3 Rnd (5-5-5)",
                knockdowns=kd,
                sig_strikes_landed=sig, sig_strikes_attempted=attempts,
                takedowns_landed=td, takedowns_attempted=2,
                submission_attempts=0, control_seconds=None,
                head_landed=sig, body_landed=0, leg_landed=0,
                distance_landed=sig, clinch_landed=0, ground_landed=0,
            ),
            fighter_id,
        )
    return [make("a", ALICE, a_kd, a_sig, 20, 1),
            make("b", BOB, b_kd, b_sig, 10, 0)]


class DefensiveHistoryTests(unittest.TestCase):
    def test_export_reads_identified_records_and_verifies_saved_rows(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            fights_path = root / "fights.jsonl"
            stats_path = root / "stats.jsonl"
            output = root / "defense.jsonl"
            fights = [_bout("first", "2020-01-01"),
                      _bout("second", "2020-02-01")]
            stats = _pair("first") + _pair("second")
            fights_path.write_text(
                "".join(json.dumps(f.as_record()) + "\n" for f in fights),
                encoding="utf-8",
            )
            stats_path.write_text(
                "".join(json.dumps(s.as_record()) + "\n" for s in stats),
                encoding="utf-8",
            )
            self.assertEqual(export_prefight_defense(
                fights_path, stats_path, output
            ), 4)
            first = output.read_bytes()
            self.assertEqual(export_prefight_defense(
                fights_path, stats_path, output
            ), 4)
            self.assertEqual(first, output.read_bytes())
            expected = [asdict(row) for row in build_defensive_history(fights, stats)]
            self.assertEqual(
                [json.loads(line) for line in output.read_text().splitlines()],
                expected,
            )

    def test_conceded_stats_and_finish_losses_belong_to_opponent(self):
        fights = [_bout("first", "2020-01-01"),
                  _bout("second", "2020-02-01", winner="Bob",
                        method="Submission")]
        stats = _pair("first") + _pair("second", a_kd=0, b_kd=1)
        rows = build_defensive_history(fights, list(reversed(stats)))
        first_bob = next(r for r in rows if r.source_bout_id == "second"
                         and r.upset_fighter_id == BOB)
        self.assertEqual(first_bob.prior_knockdowns_conceded, 2)
        self.assertEqual(first_bob.prior_bouts_with_knockdown_conceded, 1)
        self.assertEqual(first_bob.prior_ko_tko_losses, 1)
        self.assertEqual(first_bob.prior_submission_losses, 0)
        self.assertAlmostEqual(first_bob.sig_strikes_absorbed_per_minute, 2.0)
        self.assertEqual(first_bob.sig_strike_defense, 0.5)
        self.assertEqual(first_bob.takedown_defense, 0.5)
        first_alice = next(r for r in rows if r.source_bout_id == "second"
                           and r.upset_fighter_id == ALICE)
        self.assertEqual(first_alice.prior_knockdowns_conceded, 0)
        self.assertEqual(first_alice.prior_ko_tko_losses, 0)

    def test_same_day_and_later_fights_do_not_change_earlier_snapshots(self):
        first = _bout("first", "2020-01-01")
        initial = build_defensive_history([first], _pair("first"))
        later = _bout("later", "2021-01-01")
        same_day = _bout("same-day", "2020-01-01")
        changed = build_defensive_history(
            [later, same_day, first],
            _pair("later", a_kd=50) + _pair("same-day", a_kd=30)
            + _pair("first"),
        )
        self.assertEqual(
            [r for r in changed if r.source_bout_id == "first"], list(initial)
        )
        self.assertTrue(all(r.prior_fights == 0 for r in changed
                            if r.event_date == "2020-01-01"))

    def test_draw_nc_and_unknown_method_never_become_finish_losses(self):
        rows = build_defensive_history(
            [_bout("ambiguous", "2020-01-01", winner=None),
             _bout("unknown", "2020-02-01", method="Could Not Continue"),
             _bout("future", "2020-03-01", method="Overturned")],
            _pair("ambiguous") + _pair("unknown") + _pair("future"),
        )
        final = [r for r in rows if r.source_bout_id == "future"]
        self.assertTrue(all(r.prior_ko_tko_losses == 0
                            and r.prior_submission_losses == 0 for r in final))

    def test_inconsistent_pairs_and_duration_are_rejected(self):
        fight, pair = _bout("first", "2020-01-01"), _pair("first")
        with self.assertRaisesRegex(ValueError, "Missing paired"):
            build_defensive_history([fight], pair[:1])
        bad_id = replace(pair[1], upset_fighter_id=ALICE)
        with self.assertRaisesRegex(ValueError, "identity or duration"):
            build_defensive_history([fight], [pair[0], bad_id])
        bad_time = replace(pair[1], stats=replace(pair[1].stats,
                                                   fight_duration_seconds=301))
        with self.assertRaisesRegex(ValueError, "identity or duration"):
            build_defensive_history([fight], [pair[0], bad_time])
        bad_count = replace(pair[1], stats=replace(pair[1].stats,
                                                    sig_strikes_attempted=1))
        with self.assertRaisesRegex(ValueError, "Landed exceeds"):
            build_defensive_history([fight], [pair[0], bad_count])


if __name__ == "__main__":
    unittest.main()
