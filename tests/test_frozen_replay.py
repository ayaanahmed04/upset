"""Verify portable model arithmetic and reject altered prospective forecasts."""

import hashlib
import json
import unittest
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np

from upset.modeling.examined_later import EXPECTED_REFERENCE_SHA256
from upset.modeling.frozen_replay import (
    COLUMNS,
    MODEL_NAME,
    TRAINING_LAST_DATE,
    parse_artifact,
    probability,
    record_generated_forecasts,
)
from upset.modeling.prospective_archive import (
    _validate_inputs,
    _validate_model,
    verify_forecast_batch,
)
from upset.modeling.symmetric import fit_symmetric, symmetric_probabilities

A = "00000000-0000-4000-8000-000000000001"
B = "00000000-0000-4000-8000-000000000002"
NOW = datetime(2026, 9, 25, 12, tzinfo=UTC)


def _fixture(root):
    # A fitted estimator is used only to make the fixture; replay uses JSON.
    matrix = np.full((8, len(COLUMNS)), np.nan)
    matrix[:, 0] = [-4, 2, 1, -3, 5, -1, 4, -2]
    matrix[:4, 1] = [1, 2, 3, 4]
    matrix[:, -1] = 1
    signs = np.array([1 if c.endswith("_sum") else -1 for c in COLUMNS])
    model = fit_symmetric(matrix, [0, 1, 1, 0, 1, 0, 1, 0], signs)
    imp, scaler, classifier = (model.named_steps[k] for k in (
        "imputer", "scaler", "classifier"
    ))
    hashes = {name: "a" * 64 for name in (
        "matchups", "defensive_history", "rating_history", "recent_history",
        "identified_fights", "identified_stats", "registry",
    )}
    hashes["reference_manifest"] = EXPECTED_REFERENCE_SHA256
    artifact = {
        "format": MODEL_NAME, "feature_columns": list(COLUMNS),
        "training_through_date": TRAINING_LAST_DATE, "input_hashes": hashes,
        "imputer_statistics": imp.statistics_.tolist(),
        "missing_indicator_columns": imp.indicator_.features_.tolist(),
        "scaler_mean": scaler.mean_.tolist(), "scaler_scale": scaler.scale_.tolist(),
        "coefficients": classifier.coef_[0].tolist(),
        "intercept": float(classifier.intercept_[0]),
    }
    raw = json.dumps(artifact, allow_nan=False, sort_keys=True).encode()
    frozen = root / "frozen"
    frozen.mkdir()
    (frozen / "model.bin").write_bytes(raw)
    spec = {
        "model_name": MODEL_NAME, "code_commit": "a" * 40,
        "training_through_date": TRAINING_LAST_DATE,
        "training_input_sha256": hashlib.sha256(json.dumps(
            hashes, sort_keys=True, separators=(",", ":")
        ).encode()).hexdigest(),
        "model_artifact_sha256": hashlib.sha256(raw).hexdigest(),
        "feature_columns": list(COLUMNS),
    }
    (frozen / "model_spec.json").write_text(json.dumps(spec))
    schedule = root / "schedule.jsonl"
    schedule.write_text(json.dumps({
        "provider": "cito", "source_bout_id": "bout-1",
        "source_fighter_a_id": "a", "source_fighter_b_id": "b",
        "fighter_a_id": A, "fighter_b_id": B,
        "scheduled_start_utc": "2026-09-27T00:00:00Z",
        "source_observed_at_utc": "2026-09-25T11:50:00Z",
        "source_url": "https://example.org/bout-1",
    }) + "\n")
    features = root / "features.jsonl"
    values = {column: None for column in COLUMNS}
    values[COLUMNS[0]] = 3
    values[COLUMNS[-1]] = 1
    features.write_text(json.dumps({
        "source_bout_id": "bout-1", "fighter_a_id": A, "fighter_b_id": B,
        "feature_differences": values,
    }) + "\n")
    registry = root / "registry.json"
    registry.write_text(json.dumps({
        "schema_version": 1,
        "identities": [{"upset_fighter_id": f, "display_name": n} for f, n in (
            (A, "A"), (B, "B")
        )],
        "provider_links": [{"provider": "cito", "provider_fighter_id": source,
                            "upset_fighter_id": f, "evidence": "reviewed fixture"}
                           for f, source in ((A, "a"), (B, "b"))],
    }))
    return model, matrix, signs, frozen, schedule, features, registry


class FrozenReplayTests(unittest.TestCase):
    def test_json_replay_agrees_with_sklearn_in_both_orientations(self):
        with TemporaryDirectory() as directory:
            model, matrix, signs, frozen, *_ = _fixture(Path(directory))
            raw = (frozen / "model.bin").read_bytes()
            spec = json.loads((frozen / "model_spec.json").read_text())
            artifact = parse_artifact(raw, spec)
            expected = symmetric_probabilities(model, matrix, signs)[0]
            for values, p in zip(matrix, expected, strict=True):
                features = {column: None if np.isnan(v) else float(v)
                            for column, v in zip(COLUMNS, values, strict=True)}
                self.assertAlmostEqual(probability(artifact, features), p, places=12)
            broken = dict(artifact)
            broken["scaler_scale"] = [0] * len(artifact["scaler_scale"])
            with self.assertRaisesRegex(ValueError, "scale"):
                parse_artifact(json.dumps(broken).encode())
            spec["model_name"] = "unreplayed-model"
            (frozen / "model_spec.json").write_text(json.dumps(spec))
            with self.assertRaisesRegex(ValueError, "replayable artifact"):
                _validate_model(frozen / "model_spec.json", frozen / "model.bin")

    def test_generated_archive_rejects_probability_edits_even_with_valid_schema(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            _, _, _, frozen, schedule, features, registry = _fixture(root)
            batch = record_generated_forecasts(
                schedule, features, frozen, registry, root / "archive",
                recorded_at=NOW,
            )
            verify_forecast_batch(batch)
            original = json.loads((batch / "forecasts.jsonl").read_text())
            altered = dict(original)
            altered["probability_a_win"] = 1 - original["probability_a_win"]
            tampered = root / "tampered.jsonl"
            tampered.write_text(json.dumps(altered) + "\n")
            with self.assertRaisesRegex(ValueError, "differs from frozen model replay"):
                _validate_inputs(schedule, tampered, frozen / "model_spec.json",
                                 frozen / "model.bin", registry, NOW)
            with self.assertRaisesRegex(ValueError, "invalid feature values"):
                changed = json.loads(features.read_text())
                changed["feature_differences"][COLUMNS[0]] = float("nan")
                # Invalid numeric feature is rejected before a batch can appear.
                probability(parse_artifact((frozen / "model.bin").read_bytes()),
                            changed["feature_differences"])


if __name__ == "__main__":
    unittest.main()
