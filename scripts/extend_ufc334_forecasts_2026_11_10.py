"""Freeze forecasts for the two UFC 334 pairings made eligible by the backfill."""

import hashlib
import json
from collections import defaultdict
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

from scipy.special import expit

from upset.data.audit_cito_archive import _name
from upset.ratings.data import load_bouts
from upset.ratings.results_benchmark import elo_at, load_histories, prior_state, replay_elo
from upset.ratings.serving_v4 import load_snapshot
from upset.ratings.settle_forecasts import event_identity, validate_predictions
from upset.research_app import connect
from upset.skill.striking_adapter import digest, encoded, verify_hashes, write_artifact

DATA = Path("data/processed")
ORIGINAL = DATA / "rating_prospective_ufc334_2026_11_10_v1"
CALIBRATION = DATA / "rating_results_benchmark_2026_11_10_v2"
DATABASE = DATA / "research_2026_11_10_reviewed_v2/upset.sqlite"
SNAPSHOT = DATA / "overall_rating_v4_2026_11_10_reviewed_v2"
OUTPUT = DATA / "rating_prospective_ufc334_2026_11_10_v2"
NEW_PAIRINGS = {("Bilal Hasan", "Luis Gurule"), ("Alatengheili", "Juan Diaz")}


def main():
    frozen_file, summary_file = ORIGINAL / "forecast.json", CALIBRATION / "summary.json"
    paths = (frozen_file, ORIGINAL / "manifest.json", summary_file, CALIBRATION / "manifest.json",
             DATABASE, SNAPSHOT / "manifest.json", Path(__file__))
    hashes = {str(path.resolve()): digest(path) for path in paths}
    for folder, path in ((ORIGINAL, frozen_file), (CALIBRATION, summary_file)):
        manifest = json.loads((folder / "manifest.json").read_text())
        if manifest["output_sha256"][path.name] != hashes[str(path.resolve())]:
            raise ValueError(f"Saved {path.name} differs from its manifest.")
    forecast = json.loads(frozen_file.read_text())
    _, day = event_identity(forecast)
    starts = datetime.fromisoformat(forecast["scheduled_start_utc"])
    if datetime.now(UTC) >= starts:
        raise ValueError("The scheduled card start has passed.")
    validate_predictions(forecast["matchups"])
    reference = load_snapshot(SNAPSHOT, DATABASE)
    cutoff = reference.metadata["before_exclusive"]
    if cutoff > day.isoformat() or reference.metadata["latest_event"] != forecast["data_through"]:
        raise ValueError("The new release must cover the same pre-event dates.")
    fold = next(row for row in json.loads(summary_file.read_text())["folds"] if row["year"] == str(day.year))
    histories = load_histories(SNAPSHOT)
    bouts, _ = load_bouts(DATABASE, cutoff)
    elo32 = replay_elo(bouts, 32)[2]
    elo64 = replay_elo(bouts, 64, 730)[2]
    by_name = defaultdict(list)
    with closing(connect(DATABASE)) as db:
        for row in db.execute("SELECT id,name FROM fighters"):
            by_name[_name(row["name"])].append(row["id"])

    added = set()
    for row in forecast["matchups"]:
        row["frozen_at_utc"] = forecast["frozen_at_utc"]
        names = tuple(row["fighters"])
        if names not in NEW_PAIRINGS:
            continue
        matches = [by_name[_name(name)] for name in names]
        if row["probabilities_a"] is not None or any(len(side) != 1 for side in matches):
            raise ValueError(f"Unexpected fighter coverage for {names}.")
        ids = [side[0] for side in matches]
        if any(old is not None and old != uid for old, uid in zip(row["fighter_ids"], ids, strict=True)):
            raise ValueError("A previously resolved scheduled identity changed.")
        a, b = [prior_state(histories, uid, cutoff) for uid in ids]
        if a is None or b is None:
            raise ValueError("Backfilled matchup still lacks a prior v4 rating.")
        v4_delta = (a[2] - b[2]) / 10
        deltas = {"v4_rolling": v4_delta}
        for model, state, half_life in (("elo32", elo32, None), ("elo64_decay", elo64, 730)):
            x, y = [elo_at(state, uid, day.isoformat(), half_life) for uid in ids]
            deltas[model] = (x - y) / 100
        probabilities = {model: float(expit(fold["slopes"][model] * value)) for model, value in deltas.items()}
        probabilities["v4_fixed"] = float(expit(reference.metadata["model"]["probability_fit"]["slope"] * 10 * v4_delta))
        row.update(fighter_ids=ids, v4_badges=[a[1], b[1]], v4_state_dates=[a[0], b[0]],
                   probabilities_a=probabilities, status="matched")
        added.add(names)
    if added != NEW_PAIRINGS:
        raise ValueError("The updated ledger must include both reviewed pairings.")
    validate_predictions(forecast["matchups"])
    frozen_at = datetime.now(UTC)
    if frozen_at >= starts:
        raise ValueError("The event began before the additional forecasts could be saved.")
    forecast.update(frozen_at_utc=frozen_at.isoformat(), prior_forecast_sha256=hashes[str(frozen_file.resolve())])
    for row in forecast["matchups"]:
        if tuple(row["fighters"]) in added:
            row["frozen_at_utc"] = frozen_at.isoformat()
    verify_hashes(hashes)
    body = encoded(forecast)
    write_artifact(OUTPUT, {"forecast.json": body, "manifest.json": encoded({
        "input_sha256": hashes, "output_sha256": {"forecast.json": hashlib.sha256(body.encode()).hexdigest()},
    })})
    print(f"Saved {len(added)} additional forecasts. The updated ledger covers 12 of 13 scheduled bouts.")


if __name__ == "__main__":
    main()
