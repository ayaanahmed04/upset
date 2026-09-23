"""Compare the original baseline with added pre-fight defensive histories."""

import json
import platform
from collections import defaultdict
from dataclasses import fields
from datetime import date
from math import isclose, isfinite
from pathlib import Path

import numpy as np
import sklearn
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    brier_score_loss,
    log_loss,
    roc_auc_score,
)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from upset.data.identity import validate_upset_fighter_id
from upset.data.matchups import MatchupRow
from upset.data.prefight_defense import DefensiveHistory
from upset.modeling.baseline import FEATURE_COLUMNS, read_matchups
from upset.modeling.evaluation import (
    DEVELOPMENT_FOLDS,
    DEVELOPMENT_LAST_DATE,
    PREDICTION_CUTOFF,
    _sha256,
    _write_verified_json,
    development_predictions,
)

# Explicit extra inputs keep outcome labels, IDs and the target bout's stats
# outside the model matrix. Exposure counts remain visible for small samples.
DEFENSE_FIELDS = (
    "sig_strikes_absorbed_per_minute",
    "sig_strike_defense",
    "takedowns_conceded_per_15_minutes",
    "takedown_defense",
    "knockdowns_conceded_per_15_minutes",
    "prior_bouts_with_knockdown_conceded",
    "prior_ko_tko_losses",
    "prior_submission_losses",
)
DEFENSE_COLUMNS = tuple(f"{name}_diff" for name in DEFENSE_FIELDS)
ALL_COLUMNS = FEATURE_COLUMNS + DEFENSE_COLUMNS


def _validate_defense(row: DefensiveHistory) -> None:
    if not isinstance(row.source_bout_id, str) or not row.source_bout_id:
        raise ValueError("Defensive row has no bout ID.")
    validate_upset_fighter_id(row.upset_fighter_id)
    if not isinstance(row.event_date, str):
        raise TypeError(f"Invalid defensive date type: {row.source_bout_id}")
    if len(row.event_date) != 10:
        raise ValueError(f"Invalid defensive date: {row.source_bout_id}")
    try:
        if date.fromisoformat(row.event_date).isoformat() != row.event_date:
            raise ValueError("Noncanonical date")
    except ValueError as error:
        raise ValueError(f"Invalid defensive date: {row.source_bout_id}") from error
    counts = (
        "prior_fights", "prior_fight_seconds",
        "prior_sig_strikes_absorbed", "prior_opponent_sig_strikes_attempted",
        "prior_takedowns_conceded", "prior_opponent_takedowns_attempted",
        "prior_knockdowns_conceded", "prior_bouts_with_knockdown_conceded",
        "prior_ko_tko_losses", "prior_submission_losses",
    )
    for name in counts:
        value = getattr(row, name)
        if type(value) is not int or value < 0:
            raise ValueError(f"Invalid {name}: {row.source_bout_id}")
    if (
        row.prior_sig_strikes_absorbed
        > row.prior_opponent_sig_strikes_attempted
        or row.prior_takedowns_conceded
        > row.prior_opponent_takedowns_attempted
        or row.prior_bouts_with_knockdown_conceded > row.prior_fights
        or row.prior_ko_tko_losses + row.prior_submission_losses > row.prior_fights
    ):
        raise ValueError(f"Inconsistent defensive totals: {row.source_bout_id}")
    if row.prior_fights == 0 and any(getattr(row, name) for name in counts[1:]):
        raise ValueError(f"First-fight defensive totals: {row.source_bout_id}")

    def check(name: str, expected: float | None) -> None:
        actual = getattr(row, name)
        if expected is None:
            if actual is not None:
                raise ValueError(f"Undefined {name}: {row.source_bout_id}")
        elif (
            type(actual) not in (int, float)
            or not isfinite(actual)
            or not isclose(actual, expected, abs_tol=1e-12, rel_tol=1e-12)
        ):
            raise ValueError(f"Inconsistent {name}: {row.source_bout_id}")

    seconds = row.prior_fight_seconds
    sig_attempts = row.prior_opponent_sig_strikes_attempted
    td_attempts = row.prior_opponent_takedowns_attempted
    check(
        "sig_strikes_absorbed_per_minute",
        row.prior_sig_strikes_absorbed * 60 / seconds if seconds else None,
    )
    check(
        "sig_strike_defense",
        1 - row.prior_sig_strikes_absorbed / sig_attempts
        if sig_attempts else None,
    )
    check(
        "takedowns_conceded_per_15_minutes",
        row.prior_takedowns_conceded * 900 / seconds if seconds else None,
    )
    check(
        "takedown_defense",
        1 - row.prior_takedowns_conceded / td_attempts if td_attempts else None,
    )
    check(
        "knockdowns_conceded_per_15_minutes",
        row.prior_knockdowns_conceded * 900 / seconds if seconds else None,
    )


def read_defensive_history(path: Path) -> dict[tuple[str, str], DefensiveHistory]:
    """Require exact schema and a unique row for each bout and fighter."""
    expected = {field.name for field in fields(DefensiveHistory)}
    by_key: dict[tuple[str, str], DefensiveHistory] = {}
    with path.open(encoding="utf-8") as source:
        for line_number, line in enumerate(source, 1):
            try:
                record = json.loads(line)
                if not isinstance(record, dict) or set(record) != expected:
                    raise ValueError("fields do not match defensive schema")
                row = DefensiveHistory(**record)
                _validate_defense(row)
                key = row.source_bout_id, row.upset_fighter_id
                if key in by_key:
                    raise ValueError(f"Duplicate defensive row: {key}")
                by_key[key] = row
            except (TypeError, ValueError) as error:
                raise ValueError(
                    f"Invalid defensive history at line {line_number}: {error}"
                ) from error
    if not by_key:
        raise ValueError("Defensive history is empty.")
    return by_key


def join_defense(
    rows: tuple[MatchupRow, ...],
    defense: dict[tuple[str, str], DefensiveHistory],
) -> dict[str, dict[str, float | int | None]]:
    """Match permanent IDs and dates before forming fighter A minus B."""
    expected = {
        (r.source_bout_id, fighter_id)
        for r in rows
        for fighter_id in (r.fighter_a_id, r.fighter_b_id)
    }
    if set(defense) != expected:
        missing = sorted(expected - set(defense))
        extra = sorted(set(defense) - expected)
        raise ValueError(f"Defensive join mismatch: missing={missing[:2]}, "
                         f"extra={extra[:2]}")
    joined = {}
    for row in rows:
        a = defense[(row.source_bout_id, row.fighter_a_id)]
        b = defense[(row.source_bout_id, row.fighter_b_id)]
        if a.event_date != row.event_date or b.event_date != row.event_date:
            raise ValueError(f"Fight and defensive dates differ: {row.source_bout_id}")
        joined[row.source_bout_id] = {
            f"{name}_diff": (
                getattr(a, name) - getattr(b, name)
                if getattr(a, name) is not None
                and getattr(b, name) is not None else None
            )
            for name in DEFENSE_FIELDS
        }
    return joined


def _matrix(
    rows: tuple[MatchupRow, ...],
    joined: dict[str, dict[str, float | int | None]],
) -> np.ndarray:
    return np.asarray(
        [
            [
                np.nan if value is None else value
                for value in (
                    *(row.feature_differences[name] for name in FEATURE_COLUMNS),
                    *(joined[row.source_bout_id][name] for name in DEFENSE_COLUMNS),
                )
            ]
            for row in rows
        ],
        dtype=float,
    )


def _metrics(labels: list[int], probabilities: np.ndarray) -> dict:
    return {
        "accuracy": float(accuracy_score(labels, probabilities >= 0.5)),
        "roc_auc": float(roc_auc_score(labels, probabilities))
        if len(set(labels)) == 2 else None,
        "log_loss": float(log_loss(labels, probabilities, labels=[0, 1])),
        "brier_score": float(brier_score_loss(labels, probabilities)),
    }


def _paired_summary(predictions: list[dict]) -> dict:
    decisive = [p for p in predictions if p["target_a_win"] is not None]
    labels = [p["target_a_win"] for p in decisive]
    baseline = np.asarray([p["baseline_probability_a_win"] for p in decisive])
    augmented = np.asarray([p["defense_probability_a_win"] for p in decisive])
    before, after = _metrics(labels, baseline), _metrics(labels, augmented)

    # Resample dates, retaining all bouts on a drawn date. This captures
    # within-event clustering, though repeated fighters still create dependence.
    by_day: dict[str, list[int]] = defaultdict(list)
    for index, row in enumerate(decisive):
        by_day[row["event_date"]].append(index)
    days = sorted(by_day)
    rng = np.random.default_rng(20260923)
    accuracy_deltas, loss_deltas = [], []
    for _ in range(1000):
        drawn = rng.integers(0, len(days), len(days))
        indices = [index for day_index in drawn
                   for index in by_day[days[day_index]]]
        y = np.asarray(labels)[indices]
        a, b = baseline[indices], augmented[indices]
        accuracy_deltas.append(float(
            np.mean((b >= 0.5) == y) - np.mean((a >= 0.5) == y)
        ))
        eps = np.finfo(float).eps
        a, b = np.clip(a, eps, 1 - eps), np.clip(b, eps, 1 - eps)
        a_loss = -np.mean(y * np.log(a) + (1 - y) * np.log1p(-a))
        b_loss = -np.mean(y * np.log(b) + (1 - y) * np.log1p(-b))
        loss_deltas.append(float(b_loss - a_loss))
    return {
        "decisive_bouts": len(decisive),
        "draw_nc_exclusions": len(predictions) - len(decisive),
        "baseline": before,
        "with_defense": after,
        "delta_defense_minus_baseline": {
            name: (after[name] - before[name])
            if before[name] is not None and after[name] is not None else None
            for name in before
        },
        "date_cluster_bootstrap_95_percent": {
            "accuracy_delta": np.quantile(
                accuracy_deltas, [0.025, 0.975]
            ).tolist(),
            "log_loss_delta": np.quantile(
                loss_deltas, [0.025, 0.975]
            ).tolist(),
            "replicates": 1000,
            "seed": 20260923,
            "note": "Resamples calendar dates; repeated fighters may remain dependent.",
        },
    }


def compare_defense(
    rows: tuple[MatchupRow, ...],
    defense: dict[tuple[str, str], DefensiveHistory],
) -> tuple[list[dict], dict]:
    joined = join_defense(rows, defense)
    baseline_predictions, baseline_folds = development_predictions(rows)
    base_by_bout = {
        p["source_bout_id"]: p for p in baseline_predictions
    }
    if len(base_by_bout) != len(baseline_predictions):
        raise ValueError("Duplicate baseline validation bout.")

    predictions = []
    fold_reports = []
    ordered = tuple(sorted(rows, key=lambda r: (r.event_date, r.source_bout_id)))
    for fold, base_report in zip(DEVELOPMENT_FOLDS, baseline_folds, strict=True):
        train = tuple(r for r in ordered if r.event_date <= fold.train_through
                      and r.target_a_win is not None)
        validation = tuple(
            r for r in ordered
            if fold.validate_from <= r.event_date <= fold.validate_through
        )
        selected = tuple(r for r in validation if r.target_a_win is not None)
        model = Pipeline(
            [
                ("imputer", SimpleImputer(
                    strategy="median", add_indicator=True, keep_empty_features=True
                )),
                ("scaler", StandardScaler()),
                ("classifier", LogisticRegression(max_iter=1000, solver="lbfgs")),
            ]
        )
        model.fit(_matrix(train, joined), [r.target_a_win for r in train])
        probabilities = model.predict_proba(_matrix(selected, joined))[:, 1]
        augmented = {
            row.source_bout_id: float(probability)
            for row, probability in zip(selected, probabilities, strict=True)
        }
        fold_reports.append({
            "name": fold.name,
            "train_bouts": base_report["train_bouts"],
            "validation_bouts": base_report["validation_bouts"],
            "validation_decisive": len(selected),
            "baseline": {
                name: base_report[name] for name in (
                    "accuracy", "roc_auc", "log_loss", "brier_score"
                )
            },
            "with_defense": _metrics(
                [r.target_a_win for r in selected], probabilities
            ),
            "defense_missing_by_feature": {
                name: sum(joined[r.source_bout_id][name] is None for r in selected)
                for name in DEFENSE_COLUMNS
            },
        })
        for row in validation:
            original = base_by_bout[row.source_bout_id]
            if original["fold"] != fold.name:
                raise ValueError(f"Baseline fold mismatch: {row.source_bout_id}")
            predictions.append({
                **original,
                "baseline_probability_a_win": original["probability_a_win"],
                "defense_probability_a_win": augmented.get(row.source_bout_id),
            })
            del predictions[-1]["probability_a_win"]
    if len(predictions) != len(baseline_predictions):
        raise ValueError("A validation bout was lost in the comparison.")
    return predictions, {
        "folds": fold_reports,
        "paired_all_validation": _paired_summary(predictions),
    }


def export_defense_ablation(
    matchup_path: Path,
    defensive_path: Path,
    registry_path: Path,
    output_directory: Path,
    code_commit: str,
) -> dict:
    if not code_commit or not code_commit.strip():
        raise ValueError("A code commit is required.")
    if len({path.resolve() for path in (
        matchup_path, defensive_path, registry_path, output_directory
    )}) != 4:
        raise ValueError("Experiment output must not replace an input.")
    rows = read_matchups(matchup_path)
    defense = read_defensive_history(defensive_path)
    if not registry_path.is_file():
        raise ValueError("The committed fighter registry is required.")
    predictions, results = compare_defense(rows, defense)
    manifest = {
        "experiment": "defense_ablation_v1",
        "code_commit": code_commit,
        "matchups_sha256": _sha256(matchup_path),
        "defensive_history_sha256": _sha256(defensive_path),
        "registry_sha256": _sha256(registry_path),
        "total_source_bouts": len(rows),
        "source_bouts_after_development": sum(
            row.event_date > DEVELOPMENT_LAST_DATE for row in rows
        ),
        "development_last_date": DEVELOPMENT_LAST_DATE,
        "original_examined_test_first_date": "2023-08-26",
        "prediction_cutoff": PREDICTION_CUTOFF,
        "baseline_features": list(FEATURE_COLUMNS),
        "added_defense_features": list(DEFENSE_COLUMNS),
        "fit": "per-fold train-only median + missing indicators + scaling "
               "+ logistic regression (max_iter=1000, lbfgs); threshold 0.5",
        "environment": {
            "python": platform.python_version(),
            "numpy": np.__version__,
            "scikit_learn": sklearn.__version__,
        },
        **results,
    }
    _write_verified_json(
        output_directory / "predictions.jsonl", predictions, json_lines=True
    )
    _write_verified_json(
        output_directory / "manifest.json", manifest, json_lines=False
    )
    return manifest
