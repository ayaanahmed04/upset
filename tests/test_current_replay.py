"""Exercise retrospective replay timing, omissions and source integrity."""

import hashlib
import json
import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from test_asof_features import A, B, C, _history
from test_frozen_replay import _fixture

from upset.data.identity import load_fighter_registry
from upset.data.reconcile_cito_archive import _write_verified
from upset.data.stage_current import stage_completed_fights
from upset.modeling.run_current_replay import export_replay, history_gaps, replay_rows


def fixture(root):
    _, _, _, frozen, _, _, registry_path = _fixture(root)
    registry_data = json.loads(registry_path.read_text())
    registry_data["identities"].append({"upset_fighter_id": C, "display_name": "C"})
    registry_data["provider_links"] = [
        {"provider": "cito", "provider_fighter_id": "cito-" + uid[-1],
         "upset_fighter_id": uid, "evidence": "Reviewed test link"}
        for uid in (A, B, C)]
    registry_path.write_text(json.dumps(registry_data))
    fights, stats = _history()
    historical = [replace(fights[0], fight=replace(fights[0].fight, event_date="2026-03-07"))]
    historical_stats = stats[:2]
    first = replace(fights[3], fight=replace(fights[3].fight, event_date="2026-04-01",
                                           source_url="https://example.org/four"))
    later = replace(first, fight=replace(first.fight, source_bout_id="five", event_date="2026-05-01"))
    current_fights = [first, later]
    current_stats = stats[6:8] + [replace(r, stats=replace(r.stats, source_bout_id="five")) for r in stats[6:8]]
    raw = json.loads((frozen / "model.bin").read_text())
    registry = load_fighter_registry(registry_path)
    return frozen, registry_path, registry, historical, historical_stats, current_fights, current_stats, raw


def excluded(day="2026-03-20", bout="excluded", participants=("cito-1", "unknown")):
    original = _history()[0][3].fight
    return replace(original, source_bout_id=bout, event_date=day,
                   source_fighter_1_id=participants[0], source_fighter_2_id=participants[1]).__dict__


class CurrentReplayTests(unittest.TestCase):
    def test_target_result_and_own_stats_do_not_enter_own_features(self):
        with TemporaryDirectory() as directory:
            _, _, registry, history, hs, current, cs, artifact = fixture(Path(directory))
            canonical = [r.fight.__dict__ for r in current]
            original = replay_rows(history, hs, current, cs, canonical, registry, artifact)
            first = current[0]
            flipped = replace(first, fight=replace(first.fight,
                winner_name=first.fight.fighter_1_name, source_winner_label=first.fight.fighter_1_name))
            changed = [flipped, current[1]]
            altered_stats = [replace(r, stats=replace(r.stats, sig_strikes_landed=500,
                sig_strikes_attempted=1000)) if r.stats.source_bout_id == "four" else r for r in cs]
            again = replay_rows(history, hs, changed, altered_stats,
                                [r.fight.__dict__ for r in changed], registry, artifact)
            self.assertEqual(original[0][0], again[0][0])
            self.assertEqual(original[1][0]["probability_a_win"], again[1][0]["probability_a_win"])
            self.assertNotEqual(original[1][0]["target_a_win"], again[1][0]["target_a_win"])
            self.assertNotEqual(original[0][1], again[0][1])

    def test_gap_priority_counts_only_strictly_prior_bouts(self):
        with TemporaryDirectory() as directory:
            _, _, registry, _, _, current, _, _ = fixture(Path(directory))
            raw = [r.fight.__dict__ for r in current] + [excluded(), excluded("2026-04-01", "same-day"),
                                                       excluded("2026-06-01", "later")]
            gaps, priority, omitted = history_gaps(raw, current, registry)
            self.assertEqual(len(omitted), 3)
            self.assertEqual(gaps[("cito", "four")]["direct_missing_prior_bouts"][A], ["excluded"])
            self.assertEqual(gaps[("cito", "five")]["omitted_cohort_bouts_before_date"], 2)
            self.assertEqual(priority[0]["directly_affected_replay_bouts"], ["five", "four"])
            self.assertEqual(len(priority[0]["blocked_bouts"]), 3)

    def test_unrelated_omission_still_flags_population_dependency(self):
        with TemporaryDirectory() as directory:
            _, _, registry, _, _, current, _, _ = fixture(Path(directory))
            raw = [r.fight.__dict__ for r in current] + [excluded(participants=("unknown-a", "unknown-b"))]
            gaps, priority, _ = history_gaps(raw, current, registry)
            self.assertFalse(gaps[("cito", "four")]["has_direct_history_gap"])
            self.assertTrue(gaps[("cito", "four")]["population_prior_has_omitted_bouts"])
            self.assertFalse(gaps[("cito", "four")]["coverage_verified"])
            self.assertTrue(all(not r["directly_affected_replay_bouts"] for r in priority))

    def test_unknown_identified_links_and_duplicate_canonical_fail(self):
        with TemporaryDirectory() as directory:
            _, _, registry, _, _, current, _, _ = fixture(Path(directory))
            raw = [r.fight.__dict__ for r in current]
            with self.assertRaisesRegex(ValueError, "Duplicate canonical"):
                history_gaps(raw + [raw[0]], current, registry)
            with self.assertRaisesRegex(ValueError, "registry differs"):
                history_gaps(raw, [replace(current[0], upset_fighter_1_id=C)], registry)
            with self.assertRaisesRegex(ValueError, "linked bout is missing"):
                history_gaps(raw, current[:1], registry)

    def test_draw_is_replayed_but_excluded_from_binary_metrics(self):
        with TemporaryDirectory() as directory:
            _, _, registry, history, hs, current, cs, artifact = fixture(Path(directory))
            current[0] = replace(current[0], fight=replace(current[0].fight,
                winner_name=None, source_winner_label="Draw/NC"))
            _, predictions, _, report = replay_rows(history, hs, current, cs,
                [r.fight.__dict__ for r in current], registry, artifact)
            self.assertIsNone(predictions[0]["target_a_win"])
            self.assertEqual(report["retrospective_diagnostic_metrics"]["decisive_bouts"], 1)

    def test_export_binds_real_stage_hashes_and_reuses_only_identical_inputs(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            frozen, registry_path, _, history, hs, current, cs, artifact = fixture(root)
            base = root / "historical"
            base.mkdir()
            historical_path = base / "fights.jsonl"
            _write_verified(historical_path, [r.as_record() for r in history])
            inputs = {"identified_fights": historical_path}
            for key in ("matchups", "defensive_history", "rating_history", "recent_history", "identified_stats", "registry"):
                p = base / key
                p.write_text(key)
                inputs[key] = p
            artifact["input_hashes"].update({key: hashlib.sha256(p.read_bytes()).hexdigest() for key, p in inputs.items()})
            (frozen / "model.bin").write_text(json.dumps(artifact))
            spec_path = frozen / "model_spec.json"
            spec = json.loads(spec_path.read_text())
            spec["model_artifact_sha256"] = hashlib.sha256((frozen / "model.bin").read_bytes()).hexdigest()
            spec["training_input_sha256"] = hashlib.sha256(json.dumps(artifact["input_hashes"], sort_keys=True, separators=(",", ":")).encode()).hexdigest()
            spec_path.write_text(json.dumps(spec))
            cohort = root / "current"
            cohort.mkdir()
            _write_verified(cohort / "fights.jsonl", [r.fight.__dict__ for r in current] + [excluded()])
            _write_verified(cohort / "fight_stats.jsonl", [r.stats.__dict__ for r in cs])
            subset = root / "subset"
            subset.mkdir()
            _write_verified(subset / "fights.jsonl", [r.fight.__dict__ for r in current])
            _write_verified(subset / "stats.jsonl", [r.stats.__dict__ for r in cs])
            stage_completed_fights(subset / "fights.jsonl", subset / "stats.jsonl", registry_path,
                historical_path, cohort / "identified", expected_historical_sha256=artifact["input_hashes"]["identified_fights"])
            cm = {"canonical_current_bouts": 3, "identified_current_bouts": 2,
                  "output_sha256": {str(p.relative_to(cohort)): hashlib.sha256(p.read_bytes()).hexdigest()
                                    for p in cohort.rglob("*") if p.is_file()}}
            (cohort / "manifest.json").write_text(json.dumps(cm))
            reference = root / "reference"
            reference.mkdir()
            (reference / "manifest.json").write_text("{}")
            output = root / "replay"
            with patch("upset.modeling.run_current_replay.audit_asof_history", return_value={"comparison": "fixture"}), \
                 patch("upset.modeling.run_current_replay._historical", return_value=(history, hs, [], {})):
                report = export_replay(inputs, reference, cohort, registry_path, frozen, output, "a" * 40,
                                       expected_model_sha256=spec["model_artifact_sha256"])
                self.assertEqual(report["replayed_bouts"], 2)
                self.assertFalse(report["prospective_evidence"])
                self.assertFalse(report["model_retrained"])
                self.assertEqual(report["api_calls"], 0)
                self.assertEqual(export_replay(inputs, reference, cohort, registry_path, frozen, output, "a" * 40,
                    expected_model_sha256=spec["model_artifact_sha256"]), report)
                with self.assertRaisesRegex(ValueError, "accepted Mac model"):
                    export_replay(inputs, reference, cohort, registry_path, frozen, root / "bad", "a" * 40)
                (output / "predictions.jsonl").write_text("{}\n")
                with self.assertRaisesRegex(ValueError, "Export hash differs"):
                    export_replay(inputs, reference, cohort, registry_path, frozen, output, "a" * 40,
                                  expected_model_sha256=spec["model_artifact_sha256"])
