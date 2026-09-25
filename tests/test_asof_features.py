"""Cross-check as-of features against the existing historical builders."""

import unittest
from dataclasses import replace
from math import isclose

import numpy as np

from upset.data.asof_features import ScheduledMatchup, build_asof_features
from upset.data.export_identity_registry import HISTORICAL_SOURCE
from upset.data.identify_historical import IdentifiedFight, IdentifiedFightStats
from upset.data.matchups import build_matchup_rows
from upset.data.models import Fight, FightStats
from upset.data.prefight import build_prefight_snapshots
from upset.data.prefight_defense import build_defensive_history
from upset.data.prefight_features import build_prefight_features
from upset.data.prefight_ratings import build_rating_history
from upset.data.prefight_recent import build_recent_history
from upset.modeling.defense_ablation import join_defense
from upset.modeling.elo_comparison import join_ratings
from upset.modeling.frozen_replay import COLUMNS
from upset.modeling.recent_form import feature_matrix, join_recent

A = "00000000-0000-4000-8000-000000000001"
B = "00000000-0000-4000-8000-000000000002"
C = "00000000-0000-4000-8000-000000000003"


def _history():
    fights, stats = [], []
    for provider, bout, day, ids, winner, method, landed in (
        (HISTORICAL_SOURCE, "one", "2026-03-01", (A, B), 0, "KO/TKO", (6, 4)),
        (HISTORICAL_SOURCE, "two", "2026-03-02", (A, C), 1, "Submission", (3, 8)),
        (HISTORICAL_SOURCE, "three", "2026-03-03", (B, C), None, None, (8, 5)),
        ("cito", "four", "2026-03-04", (A, B), 1, "Decision", (12, 20)),
    ):
        names = tuple("Fighter " + x[-1] for x in ids)
        source_ids = tuple(provider + "-" + x[-1] for x in ids)
        fights.append(IdentifiedFight(Fight(
            source=provider, source_bout_id=bout, fighter_1_name=names[0],
            fighter_2_name=names[1], source_fighter_1_id=source_ids[0],
            source_fighter_2_id=source_ids[1], event_date=day,
            source_winner_label=names[winner] if winner is not None else "Draw/NC",
            winner_name=names[winner] if winner is not None else None,
            result_method=method,
        ), *ids))
        for uid, sid, sig in zip(ids, source_ids, landed, strict=True):
            stats.append(IdentifiedFightStats(FightStats(
                source=provider, source_bout_id=bout, source_fighter_id=sid,
                fight_duration_seconds=600, source_time_format="3x5",
                knockdowns=int(sig == 6), sig_strikes_landed=sig,
                sig_strikes_attempted=2 * sig,
                takedowns_landed=1, takedowns_attempted=3,
                submission_attempts=1, control_seconds=80,
                head_landed=sig, body_landed=0, leg_landed=0,
                distance_landed=sig, clinch_landed=0, ground_landed=0,
            ), uid))
    return fights, stats


def _schedule(fights):
    return [ScheduledMatchup(f.fight.source_bout_id, f.fight.event_date,
                             *sorted((f.upset_fighter_1_id, f.upset_fighter_2_id)))
            for f in fights]


class AsOfFeaturesTests(unittest.TestCase):
    def _assert_historical_matrix_matches(self, fights, stats):
        ours = build_asof_features(fights, stats, _schedule(fights))
        features = build_prefight_features(build_prefight_snapshots(fights, stats))
        matchups = build_matchup_rows(fights, features)
        defense = build_defensive_history(fights, stats)
        ratings = build_rating_history(fights)
        recent = build_recent_history(fights, stats)
        by_def = {(r.source_bout_id, r.upset_fighter_id): r for r in defense}
        by_ratings = {(r.source_bout_id, r.upset_fighter_id): r for r in ratings}
        by_recent = {(r.source_bout_id, r.upset_fighter_id): r for r in recent}
        rated = join_ratings(matchups, by_ratings)
        defensive = join_defense(matchups, by_def)
        joined = join_recent(matchups, by_recent, rated, by_def)
        expected = feature_matrix(matchups, defensive, rated, joined, COLUMNS)
        for matchup, values in zip(matchups, expected, strict=True):
            computed = ours[matchup.source_bout_id]
            for name, old in zip(COLUMNS, values, strict=True):
                new = computed[name]
                self.assertTrue(
                    (new is None and np.isnan(old)) or
                    (new is not None and isclose(new, old, abs_tol=1e-10,
                                               rel_tol=1e-10)),
                    (matchup.source_bout_id, name, new, old),
                )
        return ours

    def test_matches_existing_model_matrix_for_all_historical_fights(self):
        fights, stats = _history()
        self._assert_historical_matrix_matches(fights[:3], stats[:6])

    def test_distinct_same_provider_same_day_bouts_match_historical_replay(self):
        fights, stats = _history()
        repeated = replace(fights[0], fight=replace(fights[0].fight,
                                                    source_bout_id="one-again"))
        repeated_stats = [replace(row, stats=replace(row.stats,
                                                     source_bout_id="one-again"))
                          for row in stats[:2]]
        ours = self._assert_historical_matrix_matches(
            [fights[0], repeated, *fights[1:3]],
            [*stats[:2], *repeated_stats, *stats[2:6]],
        )
        original = self._assert_historical_matrix_matches(fights[:3], stats[:6])
        self.assertEqual(ours["one"], ours["one-again"])
        self.assertGreater(ours["two"]["elo_rating_diff"],
                           original["two"]["elo_rating_diff"])
        self.assertGreater(ours["two"]["recent_log_appearances_sum"],
                           original["two"]["recent_log_appearances_sum"])
        with self.assertRaisesRegex(ValueError, "Duplicate or invalid completed fight"):
            build_asof_features([fights[0], fights[0]], stats[:2],
                                _schedule(fights[:1]))

    def test_staged_provider_updates_later_only_and_result_isolation(self):
        fights, stats = _history()
        requests = [ScheduledMatchup("same-day", "2026-03-04", A, B),
                    ScheduledMatchup("next-day", "2026-03-05", A, B)]
        before = build_asof_features(fights[:3], stats[:6], requests)
        after = build_asof_features(fights, stats, requests)
        self.assertEqual(after["same-day"], before["same-day"])
        self.assertNotEqual(after["next-day"], before["next-day"])
        edited = fights[:-1] + [replace(
            fights[-1], fight=replace(fights[-1].fight,
                                      winner_name=fights[-1].fight.fighter_1_name,
                                      source_winner_label=fights[-1].fight.fighter_1_name)
        )]
        changed = build_asof_features(edited, stats, requests)
        self.assertEqual(changed["same-day"], after["same-day"])
        self.assertNotEqual(changed["next-day"]["elo_rating_diff"],
                            after["next-day"]["elo_rating_diff"])

    def test_rejects_cross_source_same_date_duplicate_and_swapped_request(self):
        fights, stats = _history()
        bad = replace(fights[-1], fight=replace(
            fights[-1].fight, event_date="2026-03-01"
        ))
        with self.assertRaisesRegex(ValueError, "duplicate bout"):
            build_asof_features(fights[:-1] + [bad], stats,
                                [ScheduledMatchup("request", "2026-03-05", A, B)])
        with self.assertRaisesRegex(ValueError, "canonical UUID order"):
            build_asof_features(fights, stats,
                                [ScheduledMatchup("request", "2026-03-05", B, A)])


if __name__ == "__main__":
    unittest.main()
