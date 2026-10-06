"""Safe, inspectable symmetric logistic artifact and independent probability replay.

No pickle or arbitrary executable model bytes enter prospective verification.
The JSON parameters are fitted on the fixed, audited historical source cohort.
"""

import hashlib
import json
from math import isfinite
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np
from threadpoolctl import threadpool_limits

from upset.data.prefight_ratings import read_rating_history
from upset.data.prefight_recent import read_recent_history
from upset.modeling.baseline import read_matchups
from upset.modeling.defense_ablation import join_defense, read_defensive_history
from upset.modeling.elo_comparison import join_ratings
from upset.modeling.examined_later import EXPECTED_REFERENCE_SHA256, _snapshot
from upset.modeling.recent_form import NEW_VARIANTS, feature_matrix, join_recent
from upset.modeling.symmetric import fit_symmetric, symmetric_probabilities

MODEL_NAME = "symmetric_recent_elo_json_v1"
COLUMNS = NEW_VARIANTS["symmetric_recent_elo"]
TRAINING_LAST_DATE = "2026-03-07"
ARTIFACT_FIELDS = {
    "format", "feature_columns", "training_through_date", "input_hashes",
    "imputer_statistics", "missing_indicator_columns", "scaler_mean",
    "scaler_scale", "coefficients", "intercept",
}


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _vector(value, length: int, name: str) -> np.ndarray:
    if not isinstance(value, list) or len(value) != length or any(
        type(x) not in (float, int) or not isfinite(x) for x in value
    ):
        raise ValueError(f"Invalid frozen model {name}.")
    return np.asarray(value, dtype=float)


def parse_artifact(raw: bytes, spec: dict | None = None) -> dict:
    """Validate the complete numeric model before replay; never deserialize code."""
    try:
        data = json.loads(raw)
    except (UnicodeError, ValueError) as error:
        raise ValueError("Frozen model is not JSON.") from error
    if not isinstance(data, dict) or set(data) != ARTIFACT_FIELDS or (
        data["format"] != MODEL_NAME
        or data["feature_columns"] != list(COLUMNS)
        or data["training_through_date"] != TRAINING_LAST_DATE
    ):
        raise ValueError("Unexpected frozen model schema or training cutoff.")
    hashes = data["input_hashes"]
    if not isinstance(hashes, dict) or set(hashes) != {
        "matchups", "defensive_history", "rating_history", "recent_history",
        "identified_fights", "identified_stats", "registry", "reference_manifest",
    } or any(not isinstance(v, str) or len(v) != 64 or any(
        c not in "0123456789abcdef" for c in v
    ) for v in hashes.values()) or hashes["reference_manifest"] != (
        EXPECTED_REFERENCE_SHA256
    ):
        raise ValueError("Frozen model source hashes differ.")
    n = len(COLUMNS)
    indicators = data["missing_indicator_columns"]
    if (not isinstance(indicators, list) or any(type(i) is not int or i < 0 or i >= n
            for i in indicators) or indicators != sorted(set(indicators))):
        raise ValueError("Invalid missing-indicator columns.")
    _vector(data["imputer_statistics"], n, "imputer statistics")
    width = n + len(indicators)
    _vector(data["scaler_mean"], width, "scaler mean")
    scale = _vector(data["scaler_scale"], width, "scaler scale")
    _vector(data["coefficients"], width, "coefficients")
    if np.any(scale <= 0) or type(data["intercept"]) not in (float, int) or (
        not isfinite(data["intercept"])
    ):
        raise ValueError("Invalid frozen model scale or intercept.")
    if spec is not None and (
        spec["model_name"] != MODEL_NAME
        or spec["feature_columns"] != list(COLUMNS)
        or spec["training_through_date"] != data["training_through_date"]
        or spec["training_input_sha256"] != hashlib.sha256(
            json.dumps(hashes, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
    ):
        raise ValueError("Frozen model does not match its specification.")
    # Constructed arrays above also reject nonfinite and wrong-shape parameters.
    return data


def probability(artifact: dict, features: dict) -> float:
    """Recompute both model directions from supplied pre-fight input values."""
    if not isinstance(features, dict) or set(features) != set(COLUMNS):
        raise ValueError("Frozen forecast feature columns differ.")
    if any(value is not None and (type(value) not in (int, float) or not isfinite(value))
           for value in features.values()):
        raise ValueError("Frozen forecast contains invalid feature values.")
    x = np.asarray([np.nan if features[c] is None else features[c] for c in COLUMNS])
    signs = np.asarray([1 if c.endswith("_sum") else -1 for c in COLUMNS])
    stats = np.asarray(artifact["imputer_statistics"])
    mean = np.asarray(artifact["scaler_mean"])
    scale = np.asarray(artifact["scaler_scale"])
    coef = np.asarray(artifact["coefficients"])
    indices = artifact["missing_indicator_columns"]

    def direction(values):
        missing = np.isnan(values)
        filled = np.where(missing, stats, values)
        expanded = np.concatenate((filled, missing[indices].astype(float)))
        z = float(np.dot((expanded - mean) / scale, coef) + artifact["intercept"])
        # This branch avoids overflow for large finite linear predictors.
        if z >= 0:
            return 1.0 / (1.0 + np.exp(-z))
        exp_z = np.exp(z)
        return float(exp_z / (1.0 + exp_z))

    return float(0.5 + 0.5 * (direction(x) - direction(x * signs)))


def freeze_model(inputs: dict[str, Path], reference: Path, output: Path,
                 code_commit: str) -> dict:
    """Fit once through the historical snapshot; write an immutable JSON model."""
    if output.exists() or not code_commit or len(code_commit) != 40 or any(
        c not in "0123456789abcdef" for c in code_commit
    ):
        raise ValueError("Output already exists or code commit is invalid.")
    if output.resolve() in {p.resolve() for p in inputs.values()}:
        raise ValueError("Model output overlaps a historical source.")
    _snapshot(inputs, reference, EXPECTED_REFERENCE_SHA256)
    rows = read_matchups(inputs["matchups"])
    if max(r.event_date for r in rows) != TRAINING_LAST_DATE:
        raise ValueError("Historical training cutoff differs from the accepted data.")
    defense = read_defensive_history(inputs["defensive_history"])
    ratings = join_ratings(rows, read_rating_history(inputs["rating_history"]))
    joined = join_defense(rows, defense)
    recent = join_recent(
        rows, read_recent_history(inputs["recent_history"]), ratings, defense
    )
    ordered = sorted(
        (r for r in rows if r.target_a_win is not None),
        key=lambda r: (r.event_date, r.source_bout_id),
    )
    matrix = feature_matrix(ordered, joined, ratings, recent, COLUMNS)
    signs = np.asarray([1 if c.endswith("_sum") else -1 for c in COLUMNS])
    with threadpool_limits(limits=1):
        model = fit_symmetric(matrix, [r.target_a_win for r in ordered], signs)
        imputer, scaler, classifier = (
            model.named_steps[key] for key in ("imputer", "scaler", "classifier")
        )
        hashes = {name: _sha(path) for name, path in inputs.items()}
        hashes["reference_manifest"] = EXPECTED_REFERENCE_SHA256
        artifact = {
            "format": MODEL_NAME,
            "feature_columns": list(COLUMNS),
            "training_through_date": TRAINING_LAST_DATE,
            "input_hashes": hashes,
            "imputer_statistics": imputer.statistics_.tolist(),
            "missing_indicator_columns": imputer.indicator_.features_.tolist(),
            "scaler_mean": scaler.mean_.tolist(),
            "scaler_scale": scaler.scale_.tolist(),
            "coefficients": classifier.coef_[0].tolist(),
            "intercept": float(classifier.intercept_[0]),
        }
        raw = (json.dumps(artifact, sort_keys=True, allow_nan=False,
                          separators=(",", ":")) + "\n").encode()
        parse_artifact(raw)
        expected = symmetric_probabilities(model, matrix, signs)[0]
        replayed = np.asarray([
            probability(artifact, dict(zip(
                COLUMNS, (None if np.isnan(v) else float(v) for v in row),
                strict=True,
            ))) for row in matrix
        ])
        if not np.allclose(expected, replayed, rtol=0, atol=1e-12):
            raise ValueError("Frozen parameter replay differs from the fitted model.")
    if any(_sha(path) != hashes[name] for name, path in inputs.items()) or (
        _sha(reference / "manifest.json") != EXPECTED_REFERENCE_SHA256
    ):
        raise ValueError("Historical files changed during model fitting.")
    spec = {
        "model_name": MODEL_NAME,
        "code_commit": code_commit,
        "training_through_date": TRAINING_LAST_DATE,
        "training_input_sha256": hashlib.sha256(
            json.dumps(hashes, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest(),
        "model_artifact_sha256": hashlib.sha256(raw).hexdigest(),
        "feature_columns": list(COLUMNS),
    }
    parse_artifact(raw, spec)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.mkdir()
    (output / "model.bin").write_bytes(raw)
    (output / "model_spec.json").write_text(
        json.dumps(spec, sort_keys=True, indent=2) + "\n", encoding="utf-8"
    )
    return {"training_bouts": len(ordered), "model_sha256": spec["model_artifact_sha256"]}


def record_generated_forecasts(
    schedule_path: Path, features_path: Path, frozen_dir: Path,
    registry_path: Path, archive_root: Path, *, recorded_at=None,
) -> Path:
    """Predict, then archive exactly those probabilities with schedule evidence."""
    from upset.modeling.prospective_archive import (
        SCHEDULE_FIELDS,
        _read_jsonl,
        _validate_model,
        record_forecast_batch,
    )

    spec_path, model_path = (
        frozen_dir / "model_spec.json", frozen_dir / "model.bin"
    )
    spec = _validate_model(spec_path, model_path)
    if spec["model_name"] != MODEL_NAME:
        raise ValueError("Only a frozen symmetric recent + Elo model is supported.")
    artifact = parse_artifact(model_path.read_bytes(), spec)
    schedule = _read_jsonl(schedule_path, SCHEDULE_FIELDS)
    scheduled = {row["source_bout_id"]: row for row in schedule}
    if len(scheduled) != len(schedule):
        raise ValueError("Duplicate schedule bout ID.")
    snapshots = _read_jsonl(features_path, {
        "source_bout_id", "fighter_a_id", "fighter_b_id", "feature_differences"
    })
    if (len(snapshots) != len(scheduled)
            or {r["source_bout_id"] for r in snapshots} != set(scheduled)):
        raise ValueError("Feature snapshots differ from the reviewed schedule.")
    forecasts = []
    for row in snapshots:
        source = scheduled[row["source_bout_id"]]
        if any(row[k] != source[k] for k in ("fighter_a_id", "fighter_b_id")):
            raise ValueError("Feature snapshot fighter identities differ.")
        forecasts.append({**row, "probability_a_win": probability(
            artifact, row["feature_differences"]
        )})
    # The archive replays every saved row before publishing the batch.
    with TemporaryDirectory(prefix="upset-frozen-forecasts-") as directory:
        path = Path(directory) / "forecasts.jsonl"
        with path.open("w", encoding="utf-8") as target:
            for row in forecasts:
                target.write(json.dumps(row, allow_nan=False, sort_keys=True) + "\n")
        return record_forecast_batch(
            schedule_path, path, spec_path, model_path, registry_path,
            archive_root, recorded_at=recorded_at,
        )
