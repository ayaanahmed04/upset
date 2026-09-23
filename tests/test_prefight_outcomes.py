"""Verify outcome history uses only strictly earlier UFC dates."""

import json
import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

from test_prefight_defense import ALICE, BOB, _bout

from upset.data.audit_prefight_outcomes import audit_prefight_outcomes
from upset.data.export_prefight_outcomes import export_prefight_outcomes
from upset.data.prefight_outcomes import (
    build_outcome_history,
    read_outcome_history,
)


class OutcomeHistoryTests(unittest.TestCase):
    def test_dates_wins_draws_recent_boundary_and_debut(self):
        fights = [
            _bout("first", "2020-01-02", winner="Alice"),
            _bout("same", "2020-01-02", winner="Bob"),
            _bout("draw", "2020-12-31", winner=None),
            _bout("boundary", "2021-01-01", winner="Alice"),
            _bout("later", "2021-01-02", winner="Bob"),
        ]
        rows = build_outcome_history(list(reversed(fights)))
        by_key = {(r.source_bout_id, r.upset_fighter_id): r for r in rows}
        self.assertEqual(by_key["first", ALICE].prior_fights, 0)
        self.assertIsNone(by_key["same", BOB].days_since_last_bout)
        self.assertIsNone(by_key["first", ALICE].prior_win_rate)
        previous = by_key["draw", ALICE]
        self.assertEqual((previous.prior_fights, previous.prior_wins,
                          previous.prior_losses, previous.prior_win_rate),
                         (2, 1, 1, 0.5))
        boundary = by_key["boundary", ALICE]
        self.assertEqual((boundary.prior_fights, boundary.prior_decisive_fights),
                         (3, 2))
        self.assertEqual((boundary.prior_365_day_wins,
                          boundary.prior_365_day_losses), (1, 1))
        self.assertEqual(boundary.days_since_last_bout, 1)
        later = by_key["later", ALICE]
        self.assertEqual((later.prior_365_day_wins,
                          later.prior_365_day_losses), (1, 0))
        self.assertEqual((later.prior_wins, later.prior_losses), (2, 1))
        self.assertEqual(later.days_since_last_bout, 1)
        self.assertEqual(audit_prefight_outcomes(fights, by_key)[
            "all_outcome_rows_checked"], 10)

    def test_future_result_does_not_change_prior_snapshots(self):
        early = _bout("early", "2020-01-01")
        later = _bout("later", "2021-01-01", winner="Bob")
        before = build_outcome_history([early, later])
        changed = build_outcome_history([
            later, early, _bout("future", "2022-01-01", winner="Alice")
        ])
        self.assertEqual(list(before), list(changed[:4]))

    def test_export_and_independent_full_audit_detect_corruption(self):
        fights = [_bout("early", "2020-01-01"),
                  _bout("later", "2020-03-01", winner="Bob")]
        with TemporaryDirectory() as directory:
            source = Path(directory) / "fights.jsonl"
            output = Path(directory) / "outcomes.jsonl"
            source.write_text("".join(json.dumps(f.as_record()) + "\n"
                                      for f in fights), encoding="utf-8")
            self.assertEqual(export_prefight_outcomes(source, output), 4)
            first = output.read_bytes()
            self.assertEqual(export_prefight_outcomes(source, output), 4)
            self.assertEqual(first, output.read_bytes())
            rows = read_outcome_history(output)
            self.assertEqual(audit_prefight_outcomes(fights, rows)[
                "all_outcome_rows_checked"], 4)
            altered = dict(rows)
            key = "later", ALICE
            altered[key] = replace(altered[key], prior_365_day_wins=0)
            with self.assertRaisesRegex(ValueError, "prior_365_day_wins"):
                audit_prefight_outcomes(fights, altered)
            raw = [json.loads(line) for line in output.read_text().splitlines()]
            raw[-1]["prior_win_rate"] = 0.5
            output.write_text("".join(json.dumps(r) + "\n" for r in raw),
                              encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "prior win rate"):
                read_outcome_history(output)

    def test_rejects_unresolved_outcomes_and_duplicate_fights(self):
        early = _bout("early", "2020-01-01")
        with self.assertRaisesRegex(ValueError, "duplicate fight"):
            build_outcome_history([early, early])
        wrong = replace(early, fight=replace(early.fight,
                         source_winner_label="Bob"))
        with self.assertRaisesRegex(ValueError, "Unresolved decisive"):
            build_outcome_history([wrong])


if __name__ == "__main__":
    unittest.main()
