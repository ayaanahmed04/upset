"""Forecast, then score the already-examined 2023+ historical period.

This period was used by the original baseline. It is a retrospective stress
test of a frozen recipe, never an unbiased final holdout or a live forecast.
"""

import json
import platform
from collections import Counter
from math import isfinite
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np
import sklearn
from threadpoolctl import threadpool_limits

from upset.data.export_prefight import read_identified
from upset.data.identify_historical import IdentifiedFight
from upset.data.models import Fight
from upset.data.prefight_ratings import read_rating_history
from upset.data.prefight_recent import read_recent_history
from upset.modeling.baseline import read_matchups
from upset.modeling.defense_ablation import (
    _paired_summary,
    join_defense,
    read_defensive_history,
)
from upset.modeling.elo_comparison import (
    DEFENSE_FEATURES,
    _audit_matchup_sources,
    _diagnostics,
    _scores,
    join_ratings,
)
from upset.modeling.evaluation import (
    DEVELOPMENT_LAST_DATE,
    PREDICTION_CUTOFF,
    _sha256,
    _write_verified_json,
)
from upset.modeling.recent_form import NEW_VARIANTS, feature_matrix, join_recent
from upset.modeling.symmetric import (
    fit_symmetric,
    swap_features,
    symmetric_probabilities,
)

# This is the SHA-256 of the completed Mac study's manifest supplied before
# writing this historical follow-up. It fixes the input snapshot and protocol.
EXPECTED_REFERENCE_SHA256 = "9c5f6228ffb3028d010bc70a644e34be47591626443285fc50e5345107f49787"
EXPERIMENT = "examined_later_v1"
MODEL = "symmetric_recent_elo"
COMPARATOR = "symmetric_defense_elo"
VARIANTS = {name: NEW_VARIANTS[name] for name in (COMPARATOR, MODEL)}
FORECAST_FIELDS = {
    "source_bout_id", "event_date", "fighter_a_id", "fighter_b_id",
    "weight_class", "diagnostic_groups", "probabilities_a_win",
    "swapped_probabilities_b_win", "raw_directional_probabilities",
}


def _snapshot(inputs: dict[str, Path], reference: Path, expected_sha: str) -> dict:
    required = {
        "matchups", "defensive_history", "rating_history", "recent_history",
        "identified_fights", "identified_stats", "registry",
    }
    if set(inputs) != required:
        raise ValueError("Historical inputs must contain all seven named paths.")
    manifest_path = reference / "manifest.json"
    predictions_path = reference / "predictions.jsonl"
    if _sha256(manifest_path) != expected_sha:
        raise ValueError("Reference manifest hash differs from the frozen study.")
    previous = json.loads(manifest_path.read_text(encoding="utf-8"))
    if (
        previous.get("experiment") != "recent_form_v1"
        or previous.get("development_last_date") != DEVELOPMENT_LAST_DATE
        or previous.get("predictions_sha256") != _sha256(predictions_path)
        or previous.get("source_bouts_after_development", 0) <= 0
        or previous.get("variants", {}).get(MODEL) != list(VARIANTS[MODEL])
        or previous.get("variants", {}).get(COMPARATOR) != list(VARIANTS[COMPARATOR])
        or previous.get("recent_audit", {}).get("comparison") != "matched"
        or previous.get("rating_audit", {}).get("comparison") != "matched"
    ):
        raise ValueError("Reference study is incomplete or incompatible.")
    for name, path in inputs.items():
        if _sha256(path) != previous.get(name + "_sha256"):
            raise ValueError(f"Frozen source hash differs: {name}")
    return previous


def _forecast_rows(rows, defense, ratings, recent, fights):
    ordered = sorted(rows, key=lambda r: (r.event_date, r.source_bout_id))
    train = [
        r for r in ordered
        if r.event_date <= DEVELOPMENT_LAST_DATE and r.target_a_win is not None
    ]
    later = [r for r in ordered if r.event_date > DEVELOPMENT_LAST_DATE]
    if not train or not later or {r.target_a_win for r in train} != {0, 1}:
        raise ValueError("Empty or single-class training period / empty later period.")
    rating_pairs = join_ratings(rows, ratings)
    defensive = join_defense(rows, defense)
    recent_pairs = join_recent(rows, recent, rating_pairs, defense)
    classes = {f.fight.source_bout_id: f.fight.weight_class or "unknown" for f in fights}
    if set(classes) != {r.source_bout_id for r in rows}:
        raise ValueError("Fight classes do not match the matchup cohort.")
    forecasts = [
        {
            "source_bout_id": r.source_bout_id,
            "event_date": r.event_date,
            "fighter_a_id": r.fighter_a_id,
            "fighter_b_id": r.fighter_b_id,
            "weight_class": classes[r.source_bout_id],
            "diagnostic_groups": {
                "history": (
                    "neither_has_history", "one_has_history", "both_have_history"
                )[
                    int(rating_pairs[r.source_bout_id][0].prior_fights > 0)
                    + int(rating_pairs[r.source_bout_id][1].prior_fights > 0)
                ],
                "experience": (
                    "at_least_one_under_3_bouts"
                    if min(
                        rating_pairs[r.source_bout_id][0].prior_fights,
                        rating_pairs[r.source_bout_id][1].prior_fights,
                    ) < 3
                    else "both_at_least_3_bouts"
                ),
                "missingness": (
                    "any_missing_defense_input"
                    if np.isnan(
                        feature_matrix(
                            (r,), defensive, rating_pairs, recent_pairs,
                            DEFENSE_FEATURES,
                        )
                    ).any()
                    else "complete_defense_inputs"
                ),
            },
            "probabilities_a_win": {},
            "swapped_probabilities_b_win": {},
            "raw_directional_probabilities": {},
        }
        for r in later
    ]
    with threadpool_limits(limits=1):
        for name, columns in VARIANTS.items():
            signs = np.asarray([1 if c.endswith("_sum") else -1 for c in columns])
            model = fit_symmetric(
                feature_matrix(train, defensive, rating_pairs, recent_pairs, columns),
                [r.target_a_win for r in train], signs,
            )
            matrix = feature_matrix(later, defensive, rating_pairs, recent_pairs, columns)
            forward, raw_forward, raw_backward = symmetric_probabilities(
                model, matrix, signs
            )
            backward, _, _ = symmetric_probabilities(
                model, swap_features(matrix, signs), signs
            )
            if not np.allclose(forward + backward, 1, rtol=0, atol=1e-12):
                raise ValueError(f"Swapped probabilities differ: {name}")
            for i, row in enumerate(forecasts):
                row["probabilities_a_win"][name] = float(forward[i])
                row["swapped_probabilities_b_win"][name] = float(backward[i])
                row["raw_directional_probabilities"][name] = {
                    "forward_a_win": float(raw_forward[i]),
                    "reverse_b_win": float(raw_backward[i]),
                }
    return forecasts, len(train)


def export_forecasts(
    inputs: dict[str, Path], reference: Path, output: Path, code_commit: str,
    *, expected_reference_sha256: str = EXPECTED_REFERENCE_SHA256,
) -> dict:
    """Fit on pre-cutoff results and save later-date predictions without labels."""
    if not code_commit or not code_commit.strip():
        raise ValueError("A code commit is required.")
    paths = [*inputs.values(), reference / "manifest.json", reference / "predictions.jsonl"]
    if len({p.resolve() for p in paths}) != len(paths):
        raise ValueError("Experiment inputs must be distinct.")
    if output.exists() or any(
        output.resolve() == p.resolve() or output.resolve() in p.resolve().parents
        for p in paths
    ) or reference.resolve() in output.resolve().parents:
        raise ValueError("Output exists or overlaps an input.")
    previous = _snapshot(inputs, reference, expected_reference_sha256)
    rows = read_matchups(inputs["matchups"])
    defense = read_defensive_history(inputs["defensive_history"])
    ratings = read_rating_history(inputs["rating_history"])
    recent = read_recent_history(inputs["recent_history"])
    fights = read_identified(
        inputs["identified_fights"], Fight, IdentifiedFight,
        ("upset_fighter_1_id", "upset_fighter_2_id"),
    )
    if len(rows) != previous["total_source_bouts"]:
        raise ValueError("Frozen matchup count differs.")
    forecasts, training_bouts = _forecast_rows(rows, defense, ratings, recent, fights)
    if len(forecasts) != previous["source_bouts_after_development"]:
        raise ValueError("Frozen examined-period cohort differs.")
    hashes = {name + "_sha256": _sha256(path) for name, path in inputs.items()}
    if hashes != {
        name + "_sha256": previous[name + "_sha256"] for name in inputs
    } or (
        _sha256(reference / "manifest.json") != expected_reference_sha256
        or _sha256(reference / "predictions.jsonl")
        != previous["predictions_sha256"]
    ):
        raise ValueError("An input changed during forecast generation.")
    manifest = {
        "experiment": EXPERIMENT,
        "status": "examined historical stress test; no promotion",
        "code_commit": code_commit,
        "reference_manifest_sha256": expected_reference_sha256,
        "reference_predictions_sha256": previous["predictions_sha256"],
        **hashes,
        "train_through": DEVELOPMENT_LAST_DATE,
        "examined_first_date": forecasts[0]["event_date"],
        "examined_last_date": forecasts[-1]["event_date"],
        "training_decisive_bouts": training_bouts,
        "forecast_bouts": len(forecasts),
        "variants": {name: list(columns) for name, columns in VARIANTS.items()},
        "model": MODEL,
        "primary_comparator": COMPARATOR,
        "training": "mirrored rows with 0.5 weight each, fit once through cutoff",
        "preprocessing": "training-only median/indicator/scale, C=1, lbfgs",
        "inference": "0.5 + 0.5 * (forward - reverse)",
        "calibration": "identity; no calibrator fitted; ten fixed 0.1 bins for diagnostics",
        "tie_policy": "p >= 0.5 chooses canonical UUID-ordered A; ties reported",
        "prediction_cutoff": PREDICTION_CUTOFF,
        "availability": "earlier-dated historical features; no dated pre-event capture",
        "environment": {
            "python": platform.python_version(),
            "numpy": np.__version__,
            "scikit_learn": sklearn.__version__,
            "fit_thread_limit": 1,
        },
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=output.parent, prefix=".upset-examined-") as temp:
        staged = Path(temp) / "result"
        _write_verified_json(staged / "forecasts.jsonl", forecasts, json_lines=True)
        manifest["forecasts_sha256"] = _sha256(staged / "forecasts.jsonl")
        _write_verified_json(staged / "manifest.json", manifest, json_lines=False)
        staged.rename(output)
    return manifest


def score_forecasts(
    output: Path, matchup_path: Path, fights_path: Path,
    reference: Path, *, expected_reference_sha256: str = EXPECTED_REFERENCE_SHA256,
) -> dict:
    """Join outcomes only after the entire forecast file is saved and hashed."""
    manifest_path = output / "manifest.json"
    forecasts_path = output / "forecasts.jsonl"
    scored_dir = output / "scored"
    if scored_dir.exists():
        raise ValueError("Scored report already exists; do not overwrite evidence.")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if (
        manifest.get("experiment") != EXPERIMENT
        or manifest.get("reference_manifest_sha256") != expected_reference_sha256
        or _sha256(reference / "manifest.json") != expected_reference_sha256
        or _sha256(reference / "predictions.jsonl")
        != manifest.get("reference_predictions_sha256")
        or _sha256(forecasts_path) != manifest.get("forecasts_sha256")
        or _sha256(matchup_path) != manifest.get("matchups_sha256")
        or _sha256(fights_path) != manifest.get("identified_fights_sha256")
        or manifest.get("variants") != {
            name: list(columns) for name, columns in VARIANTS.items()
        }
        or manifest.get("train_through") != DEVELOPMENT_LAST_DATE
        or manifest.get("calibration")
        != "identity; no calibrator fitted; ten fixed 0.1 bins for diagnostics"
    ):
        raise ValueError("Forecast or frozen-source evidence differs.")
    forecasts = [
        json.loads(line) for line in forecasts_path.read_text(encoding="utf-8").splitlines()
    ]
    rows = read_matchups(matchup_path)
    fights = read_identified(
        fights_path, Fight, IdentifiedFight,
        ("upset_fighter_1_id", "upset_fighter_2_id"),
    )
    _audit_matchup_sources(rows, fights)
    later = {r.source_bout_id: r for r in rows if r.event_date > DEVELOPMENT_LAST_DATE}
    if len(forecasts) != manifest["forecast_bouts"] or len(later) != len(forecasts):
        raise ValueError("Examined-period cohort count changed.")
    by_id = {}
    for record in forecasts:
        if not isinstance(record, dict) or set(record) != FORECAST_FIELDS:
            raise ValueError("Forecast row schema differs or contains outcomes.")
        bout = record["source_bout_id"]
        if bout in by_id or bout not in later:
            raise ValueError("Duplicate or unknown forecast bout.")
        source = later[bout]
        if any(
            record[key] != getattr(source, key)
            for key in ("event_date", "fighter_a_id", "fighter_b_id")
        ) or not isinstance(record["weight_class"], str):
            raise ValueError("Forecast date or fighter identity differs.")
        for key in ("probabilities_a_win", "swapped_probabilities_b_win"):
            probs = record[key]
            if not isinstance(probs, dict) or set(probs) != set(VARIANTS):
                raise ValueError("Forecast variants differ.")
            if any(
                type(p) not in (int, float) or not isfinite(p) or not 0 <= p <= 1
                for p in probs.values()
            ):
                raise ValueError("Invalid saved probability.")
        for name in VARIANTS:
            if abs(
                record["probabilities_a_win"][name]
                + record["swapped_probabilities_b_win"][name] - 1
            ) > 1e-12:
                raise ValueError("Saved prediction is not swap symmetric.")
        by_id[bout] = record
    if set(by_id) != set(later):
        raise ValueError("Forecast cohort differs from outcome cohort.")
    scored = [
        {
            **record,
            "target_a_win": later[record["source_bout_id"]].target_a_win,
            "exclusion_reason": later[record["source_bout_id"]].training_exclusion_reason,
        }
        for record in forecasts
    ]
    if not any(r["target_a_win"] is not None for r in scored):
        raise ValueError("No decisive later-date bouts to score.")
    scores = _scores(scored, VARIANTS)
    pair = _paired_summary([
        {
            "event_date": r["event_date"],
            "target_a_win": r["target_a_win"],
            "baseline_probability_a_win": r["probabilities_a_win"][COMPARATOR],
            "defense_probability_a_win": r["probabilities_a_win"][MODEL],
        }
        for r in scored
    ])
    diagnostics = _diagnostics(scored, VARIANTS)
    decisive = [r for r in scored if r["target_a_win"] is not None]
    calibration = {}
    for name, bins in diagnostics["reliability_deciles"].items():
        calibration[name] = {
            "ten_bin_expected_calibration_error": sum(
                row["count"] / len(decisive)
                * abs(row["mean_probability"] - row["observed_a_win_fraction"])
                for row in bins if row["count"]
            ),
            "mean_predicted_winner_confidence": sum(
                max(r["probabilities_a_win"][name],
                    1 - r["probabilities_a_win"][name])
                for r in decisive
            ) / len(decisive),
        }
    score_manifest = {
        "experiment": EXPERIMENT,
        "status": "examined historical stress test; no promotion or live estimate",
        "forecast_manifest_sha256": _sha256(manifest_path),
        "forecasts_sha256": _sha256(forecasts_path),
        "outcome_matchups_sha256": _sha256(matchup_path),
        "outcome_fights_sha256": _sha256(fights_path),
        "training_through": DEVELOPMENT_LAST_DATE,
        "first_date": min(r["event_date"] for r in scored),
        "last_date": max(r["event_date"] for r in scored),
        "validation_bouts": len(scored),
        "decisive_bouts": len(decisive),
        "draw_nc_exclusions": len(scored) - len(decisive),
        "model": MODEL,
        "primary_comparator": COMPARATOR,
        "pooled": scores,
        "paired": {
            "delta_recent_minus_comparator": pair["delta_defense_minus_baseline"],
            "date_cluster_bootstrap_95_percent": pair[
                "date_cluster_bootstrap_95_percent"
            ],
        },
        "year_scores": {
            year: _scores([r for r in scored if r["event_date"][:4] == year], VARIANTS)
            for year in sorted({r["event_date"][:4] for r in scored})
        },
        "weight_class_scores": {
            label: _scores([r for r in scored if r["weight_class"] == label], VARIANTS)
            for label in sorted({r["weight_class"] for r in scored})
        },
        "calibration": calibration,
        "exact_ties": {
            name: sum(r["probabilities_a_win"][name] == 0.5 for r in decisive)
            for name in VARIANTS
        },
        "target_balance": {
            "fighter_a_wins": Counter(r["target_a_win"] for r in decisive)[1],
            "fighter_b_wins": Counter(r["target_a_win"] for r in decisive)[0],
        },
        **diagnostics,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=output, prefix=".upset-scored-") as temp:
        staged = Path(temp) / "result"
        _write_verified_json(staged / "scored_predictions.jsonl", scored, json_lines=True)
        score_manifest["scored_predictions_sha256"] = _sha256(
            staged / "scored_predictions.jsonl"
        )
        _write_verified_json(staged / "manifest.json", score_manifest, json_lines=False)
        staged.rename(scored_dir)
    return score_manifest
