"""A fixed chronological win-prediction baseline and its input audit."""

import json
from collections import Counter
from dataclasses import fields
from datetime import date
from itertools import groupby
from math import ceil, isfinite
from pathlib import Path

import numpy as np
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
from upset.data.matchups import AMBIGUOUS_OUTCOME, INPUT_FIELDS, MatchupRow

FEATURE_COLUMNS = tuple(f"{field}_diff" for field in INPUT_FIELDS)
SPLIT_NAMES = ("train", "validation", "test")


def _validate_row(row: MatchupRow) -> None:
    if not isinstance(row.source_bout_id, str) or not row.source_bout_id:
        raise ValueError("Matchup has an invalid bout ID.")
    try:
        if date.fromisoformat(row.event_date).isoformat() != row.event_date:
            raise ValueError("Noncanonical event date")
    except (TypeError, ValueError) as error:
        raise ValueError(f"Invalid event date: {row.source_bout_id}") from error
    validate_upset_fighter_id(row.fighter_a_id)
    validate_upset_fighter_id(row.fighter_b_id)
    if row.fighter_a_id >= row.fighter_b_id:
        raise ValueError(f"Unsorted or identical fighter IDs: {row.source_bout_id}")
    if not isinstance(row.feature_differences, dict) or set(
        row.feature_differences
    ) != set(FEATURE_COLUMNS):
        raise ValueError(f"Unexpected feature columns: {row.source_bout_id}")
    for column, value in row.feature_differences.items():
        if value is None:
            continue
        if column in ("prior_fights_diff", "prior_fight_seconds_diff"):
            valid = type(value) is int
        else:
            valid = type(value) in (int, float) and isfinite(value)
        if not valid:
            raise ValueError(f"Invalid {column}: {row.source_bout_id}")
    if row.source_winner_label == "Draw/NC":
        if row.target_a_win is not None or row.training_exclusion_reason != (
            AMBIGUOUS_OUTCOME
        ):
            raise ValueError(f"Invalid ambiguous target: {row.source_bout_id}")
    elif (
        not isinstance(row.source_winner_label, str)
        or not row.source_winner_label
        or type(row.target_a_win) is not int
        or row.target_a_win not in (0, 1)
        or row.training_exclusion_reason is not None
    ):
        raise ValueError(f"Invalid decisive target: {row.source_bout_id}")


def read_matchups(path: Path) -> tuple[MatchupRow, ...]:
    """Require the exact export schema and one unique, valid row per bout."""
    expected = {field.name for field in fields(MatchupRow)}
    rows = []
    seen = set()
    with path.open(encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, start=1):
            try:
                record = json.loads(line)
                if not isinstance(record, dict) or set(record) != expected:
                    raise ValueError("fields do not match the matchup schema")
                row = MatchupRow(**record)
                _validate_row(row)
                if row.source_bout_id in seen:
                    raise ValueError(f"Duplicate bout: {row.source_bout_id}")
            except (TypeError, ValueError) as error:
                raise ValueError(
                    f"Invalid matchup at line {line_number}: {error}"
                ) from error
            rows.append(row)
            seen.add(row.source_bout_id)
    if not rows:
        raise ValueError("Matchup export is empty.")
    return tuple(rows)


def split_by_event_date(
    rows: tuple[MatchupRow, ...],
) -> dict[str, tuple[MatchupRow, ...]]:
    """Approximate 70/15/15 by bout count without splitting any calendar date."""
    if not rows:
        raise ValueError("Matchup export is empty.")
    ordered = sorted(rows, key=lambda row: (row.event_date, row.source_bout_id))
    buckets: dict[str, list[MatchupRow]] = {name: [] for name in SPLIT_NAMES}
    train_cutoff, validation_cutoff = ceil(0.70 * len(rows)), ceil(0.85 * len(rows))
    count = 0
    for _, dated_rows in groupby(ordered, key=lambda row: row.event_date):
        group = tuple(dated_rows)
        if count < train_cutoff:
            name = "train"
        elif count < validation_cutoff:
            name = "validation"
        else:
            name = "test"
        buckets[name].extend(group)
        count += len(group)
    if any(not buckets[name] for name in SPLIT_NAMES):
        raise ValueError("Need three nonempty periods with distinct event dates.")
    splits = {name: tuple(buckets[name]) for name in SPLIT_NAMES}
    if any(not decisive_rows(splits[name]) for name in SPLIT_NAMES):
        raise ValueError("Each time period needs at least one decisive bout.")
    return splits


def decisive_rows(rows: tuple[MatchupRow, ...]) -> tuple[MatchupRow, ...]:
    return tuple(row for row in rows if row.target_a_win is not None)


def _inputs(rows: tuple[MatchupRow, ...]) -> np.ndarray:
    # No metadata or target is admitted to this matrix. NaNs are imputed later.
    return np.asarray(
        [
            [
                np.nan
                if row.feature_differences[column] is None
                else row.feature_differences[column]
                for column in FEATURE_COLUMNS
            ]
            for row in rows
        ],
        dtype=float,
    )


def fit_baseline(train: tuple[MatchupRow, ...]) -> Pipeline:
    """Fit medians, missing indicators, scaling, and logistic regression on train."""
    selected = decisive_rows(train)
    y = [row.target_a_win for row in selected]
    if set(y) != {0, 1}:
        raise ValueError("Training period needs wins for both orientations.")
    model = Pipeline(
        [
            (
                "imputer",
                SimpleImputer(
                    strategy="median", add_indicator=True, keep_empty_features=True
                ),
            ),
            ("scaler", StandardScaler()),
            ("classifier", LogisticRegression(max_iter=1000, solver="lbfgs")),
        ]
    )
    model.fit(_inputs(selected), y)
    return model


def _metrics(y: list[int], probabilities: np.ndarray) -> dict:
    return {
        "accuracy": float(accuracy_score(y, probabilities >= 0.5)),
        "roc_auc": float(roc_auc_score(y, probabilities)) if len(set(y)) == 2 else None,
        "log_loss": float(log_loss(y, probabilities, labels=[0, 1])),
        "brier_score": float(brier_score_loss(y, probabilities)),
    }


def evaluate_baseline(rows: tuple[MatchupRow, ...]) -> dict:
    """Return a deterministic report; no holdout row participates in fitting."""
    splits = split_by_event_date(rows)
    train = decisive_rows(splits["train"])
    model = fit_baseline(splits["train"])
    training_prevalence = sum(row.target_a_win for row in train) / len(train)
    report = {
        "total_bouts": len(rows),
        "split_policy": "70/15/15 approximate bout counts, full event dates",
        "model": "train-only median + missing indicators + scaling + logistic regression",
        "feature_columns": FEATURE_COLUMNS,
        "splits": {},
    }
    for name, period in splits.items():
        selected = decisive_rows(period)
        labels = [row.target_a_win for row in selected]
        probabilities = model.predict_proba(_inputs(selected))[:, 1]
        report["splits"][name] = {
            "first_date": period[0].event_date,
            "last_date": period[-1].event_date,
            "bouts": len(period),
            "decisive": len(selected),
            "excluded_draw_nc": len(period) - len(selected),
            "fighter_a_wins": Counter(labels)[1],
            "fighter_b_wins": Counter(labels)[0],
            "missing_by_feature": {
                column: sum(row.feature_differences[column] is None for row in selected)
                for column in FEATURE_COLUMNS
            },
            "model_metrics": _metrics(labels, probabilities),
            "training_prior_metrics": _metrics(
                labels, np.full(len(labels), training_prevalence)
            ),
        }
    return report
