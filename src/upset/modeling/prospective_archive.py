"""Record supplied pre-event forecasts with exact evidence and no outcomes."""

import fcntl
import hashlib
import json
import re
import shutil
from datetime import UTC, date, datetime, timedelta
from math import isfinite
from pathlib import Path
from tempfile import TemporaryDirectory

from upset.data.identity import load_fighter_registry, validate_upset_fighter_id
from upset.modeling.baseline import FEATURE_COLUMNS
from upset.modeling.defense_ablation import DEFENSE_COLUMNS
from upset.modeling.outcome_recency import OUTCOME_COLUMNS
from upset.modeling.recent_form import NEW_VARIANTS

SCHEDULE_FIELDS = {
    "provider", "source_bout_id", "source_fighter_a_id",
    "source_fighter_b_id", "fighter_a_id", "fighter_b_id",
    "scheduled_start_utc", "source_observed_at_utc", "source_url",
}
FORECAST_FIELDS = {
    "source_bout_id", "fighter_a_id", "fighter_b_id",
    "feature_differences", "probability_a_win",
}
MODEL_FIELDS = {
    "model_name", "code_commit", "training_through_date",
    "training_input_sha256", "model_artifact_sha256", "feature_columns",
}
APPROVED_COLUMNS = (
    FEATURE_COLUMNS,
    FEATURE_COLUMNS + DEFENSE_COLUMNS,
    FEATURE_COLUMNS + OUTCOME_COLUMNS,
    FEATURE_COLUMNS + DEFENSE_COLUMNS + OUTCOME_COLUMNS,
    NEW_VARIANTS["symmetric_recent_elo"],
)
COPIES = {
    "schedule.jsonl": "schedule",
    "forecasts.jsonl": "forecasts",
    "model.bin": "model",
    "model_spec.json": "model_spec",
    "fighter_registry.json": "registry",
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _utc(value: str) -> datetime:
    if not isinstance(value, str) or not re.fullmatch(
        r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", value
    ):
        raise ValueError(f"Expected UTC timestamp with second precision: {value!r}")
    return datetime.fromisoformat(value)


def _read_jsonl(path: Path, expected: set[str]) -> list[dict]:
    records = []
    with path.open(encoding="utf-8") as source:
        for number, line in enumerate(source, 1):
            try:
                item = json.loads(line)
            except ValueError as error:
                raise ValueError(f"Invalid JSON at {path.name}:{number}") from error
            if not isinstance(item, dict) or set(item) != expected:
                raise ValueError(f"Unexpected fields at {path.name}:{number}")
            records.append(item)
    if not records:
        raise ValueError(f"Empty prospective input: {path.name}")
    return records


def _validate_model(spec_path: Path, model_path: Path) -> dict:
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    if not isinstance(spec, dict) or set(spec) != MODEL_FIELDS:
        raise ValueError("Unexpected model specification fields.")
    if not isinstance(spec["model_name"], str) or not spec["model_name"].strip():
        raise ValueError("Model name is required.")
    for name, length in (
        ("code_commit", 40), ("training_input_sha256", 64),
        ("model_artifact_sha256", 64),
    ):
        if not isinstance(spec[name], str) or not re.fullmatch(
            rf"[0-9a-f]{{{length}}}", spec[name]
        ):
            raise ValueError(f"Invalid {name} in model specification.")
    try:
        trained = date.fromisoformat(spec["training_through_date"])
        if trained.isoformat() != spec["training_through_date"]:
            raise ValueError("Noncanonical date")
    except (TypeError, ValueError) as error:
        raise ValueError("Invalid model training cutoff date.") from error
    if not isinstance(spec["feature_columns"], list) or tuple(
        spec["feature_columns"]
    ) not in APPROVED_COLUMNS:
        raise ValueError("Model feature columns are not a reviewed variant.")
    if not model_path.is_file() or model_path.stat().st_size == 0:
        raise ValueError("A nonempty model artifact is required.")
    if _sha256(model_path) != spec["model_artifact_sha256"]:
        raise ValueError("Model artifact does not match its specification.")
    from upset.modeling.frozen_replay import MODEL_NAME, parse_artifact

    if tuple(spec["feature_columns"]) == NEW_VARIANTS["symmetric_recent_elo"] and (
        spec["model_name"] != MODEL_NAME
    ):
        raise ValueError("Recent + Elo forecasts require a replayable artifact.")
    if spec["model_name"] == MODEL_NAME:
        parse_artifact(model_path.read_bytes(), spec)
    return spec


def _validate_inputs(
    schedule_path: Path,
    forecasts_path: Path,
    spec_path: Path,
    model_path: Path,
    registry_path: Path,
    recorded_at: datetime,
) -> list[list[str]]:
    spec = _validate_model(spec_path, model_path)
    from upset.modeling.frozen_replay import (
        MODEL_NAME,
        parse_artifact,
    )
    from upset.modeling.frozen_replay import (
        probability as replay_probability,
    )

    replay = (parse_artifact(model_path.read_bytes(), spec)
              if spec["model_name"] == MODEL_NAME else None)
    registry = load_fighter_registry(registry_path)
    known_ids = {item.upset_fighter_id for item in registry.identities}
    provider_links = {
        (item.provider, item.provider_fighter_id): item.upset_fighter_id
        for item in registry.provider_links
    }
    schedule = _read_jsonl(schedule_path, SCHEDULE_FIELDS)
    forecasts = _read_jsonl(forecasts_path, FORECAST_FIELDS)
    by_bout = {}
    for row in schedule:
        provider, bout = row["provider"], row["source_bout_id"]
        if (not isinstance(provider, str) or not provider
                or provider != provider.lower()
                or not isinstance(bout, str) or not bout):
            raise ValueError("Invalid schedule provider or bout ID.")
        key = provider, bout
        if key in by_bout:
            raise ValueError(f"Duplicate scheduled bout: {key}")
        a, b = row["fighter_a_id"], row["fighter_b_id"]
        validate_upset_fighter_id(a)
        validate_upset_fighter_id(b)
        if a >= b or a not in known_ids or b not in known_ids:
            raise ValueError(f"Unknown or unsorted fighter identities: {key}")
        for side, fighter_id in (("a", a), ("b", b)):
            source_id = row[f"source_fighter_{side}_id"]
            if (not isinstance(source_id, str) or not source_id
                    or provider_links.get((provider, source_id)) != fighter_id):
                raise ValueError(f"Unreviewed provider fighter link: {key}")
        start = _utc(row["scheduled_start_utc"])
        observed = _utc(row["source_observed_at_utc"])
        if (start <= recorded_at + timedelta(hours=1)
                or not observed <= recorded_at
                or recorded_at - observed > timedelta(hours=48)):
            raise ValueError(f"Schedule is stale or too close to start: {key}")
        if date.fromisoformat(spec["training_through_date"]) >= start.date():
            raise ValueError(f"Model training overlaps scheduled bout: {key}")
        url = row["source_url"]
        if not isinstance(url, str) or not url.startswith("https://"):
            raise ValueError(f"Schedule source URL is required: {key}")
        by_bout[key] = row

    matched = set()
    for row in forecasts:
        bout = row["source_bout_id"]
        possible = [key for key in by_bout if key[1] == bout]
        if len(possible) != 1:
            raise ValueError(f"Unknown or ambiguous forecast bout: {bout}")
        key = possible[0]
        if key in matched:
            raise ValueError(f"Duplicate forecast bout: {key}")
        matched.add(key)
        source = by_bout[key]
        if (row["fighter_a_id"] != source["fighter_a_id"]
                or row["fighter_b_id"] != source["fighter_b_id"]):
            raise ValueError(f"Forecast fighter identities differ: {key}")
        probability = row["probability_a_win"]
        if (type(probability) not in (int, float) or not isfinite(probability)
                or not 0 <= probability <= 1):
            raise ValueError(f"Invalid win probability: {key}")
        values = row["feature_differences"]
        if not isinstance(values, dict) or set(values) != set(
            spec["feature_columns"]
        ):
            raise ValueError(f"Forecast feature columns differ: {key}")
        if any(value is not None and (
            type(value) not in (int, float) or not isfinite(value)
        ) for value in values.values()):
            raise ValueError(f"Invalid forecast feature value: {key}")
        if replay is not None and abs(replay_probability(replay, values) - probability) > (
            1e-12
        ):
            raise ValueError(f"Forecast differs from frozen model replay: {key}")
    if matched != set(by_bout):
        raise ValueError("One or more scheduled bouts have no forecast.")
    return [list(key) for key in sorted(matched)]


def verify_forecast_batch(batch: Path) -> dict:
    """Check copied bytes and relations; never load/execute the model binary."""
    if not batch.is_dir() or {p.name for p in batch.iterdir()} != (
        set(COPIES) | {"manifest.json"}
    ):
        raise ValueError("Prospective batch has missing or unexpected files.")
    manifest = json.loads((batch / "manifest.json").read_text(encoding="utf-8"))
    if not isinstance(manifest, dict) or set(manifest) != {
        "schema_version", "recorded_at_utc", "bout_keys", "sha256"
    } or manifest["schema_version"] != 1:
        raise ValueError("Invalid prospective manifest schema.")
    if not isinstance(manifest["sha256"], dict) or set(
        manifest["sha256"]
    ) != set(COPIES):
        raise ValueError("Incomplete prospective checksums.")
    for name in COPIES:
        if _sha256(batch / name) != manifest["sha256"][name]:
            raise ValueError(f"Prospective batch was modified: {name}")
    keys = _validate_inputs(
        batch / "schedule.jsonl", batch / "forecasts.jsonl",
        batch / "model_spec.json", batch / "model.bin",
        batch / "fighter_registry.json", _utc(manifest["recorded_at_utc"]),
    )
    if manifest["bout_keys"] != keys:
        raise ValueError("Prospective manifest keys differ from inputs.")
    return manifest


def record_forecast_batch(
    schedule_path: Path,
    forecasts_path: Path,
    spec_path: Path,
    model_path: Path,
    registry_path: Path,
    archive_root: Path,
    *,
    recorded_at: datetime | None = None,
) -> Path:
    """Write one complete new batch; existing bout keys cannot be repeated."""
    moment = datetime.now(UTC) if recorded_at is None else recorded_at
    if moment.tzinfo is None or moment.utcoffset() != timedelta(0):
        raise ValueError("Recording clock must be timezone-aware UTC.")
    moment = moment.replace(microsecond=0)
    inputs = (schedule_path, forecasts_path, spec_path, model_path, registry_path)
    if len({p.resolve() for p in inputs}) != len(inputs):
        raise ValueError("Prospective evidence inputs must be distinct files.")
    if archive_root.resolve() in {p.resolve() for p in inputs}:
        raise ValueError("Archive root must not replace an input.")
    keys = _validate_inputs(*inputs, moment)
    archive_root.mkdir(parents=True, exist_ok=True)
    with (archive_root / ".write.lock").open("a+b") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        for existing in archive_root.iterdir():
            if existing.name == ".write.lock":
                continue
            prior = verify_forecast_batch(existing)
            if set(map(tuple, prior["bout_keys"])) & set(map(tuple, keys)):
                raise ValueError("A bout already has a locked prospective forecast.")
        name = moment.strftime("%Y%m%dT%H%M%SZ") + "-" + _sha256(
            forecasts_path
        )[:12]
        destination = archive_root / name
        if destination.exists():
            raise ValueError("Prospective batch already exists.")
        with TemporaryDirectory(dir=archive_root, prefix=".upset-stage-") as tmp:
            staged = Path(tmp) / name
            staged.mkdir()
            copies = {
                "schedule.jsonl": schedule_path,
                "forecasts.jsonl": forecasts_path,
                "model.bin": model_path,
                "model_spec.json": spec_path,
                "fighter_registry.json": registry_path,
            }
            for filename, source in copies.items():
                shutil.copyfile(source, staged / filename)
            manifest = {
                "schema_version": 1,
                "recorded_at_utc": moment.isoformat().replace("+00:00", "Z"),
                "bout_keys": keys,
                "sha256": {name: _sha256(staged / name) for name in COPIES},
            }
            (staged / "manifest.json").write_text(
                json.dumps(manifest, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            verify_forecast_batch(staged)
            staged.rename(destination)
        return destination
