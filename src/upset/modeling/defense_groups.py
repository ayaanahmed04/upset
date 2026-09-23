"""Exploratory feature-group comparisons on the frozen development cohort."""

import platform
from pathlib import Path

import numpy as np
import sklearn
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from upset.data.matchups import MatchupRow
from upset.data.prefight_defense import DefensiveHistory
from upset.modeling.baseline import FEATURE_COLUMNS, read_matchups
from upset.modeling.defense_ablation import (
    DEFENSE_COLUMNS,
    _metrics,
    compare_defense,
    join_defense,
    read_defensive_history,
)
from upset.modeling.evaluation import (
    DEVELOPMENT_FOLDS,
    DEVELOPMENT_LAST_DATE,
    PREDICTION_CUTOFF,
    _sha256,
    _write_verified_json,
)

# Fixed before reading the results. These are descriptions of overlapping
# histories, not independent or causal components of predictive performance.
GROUPS = {
    "striking": DEFENSE_COLUMNS[:2],
    "grappling": DEFENSE_COLUMNS[2:4],
    "knockdowns": DEFENSE_COLUMNS[4:6],
    "finish_losses": DEFENSE_COLUMNS[6:8],
}
VARIANTS = {
    "baseline": (),
    **{f"add_{name}": columns for name, columns in GROUPS.items()},
    "all_defense": DEFENSE_COLUMNS,
    **{
        f"without_{name}": tuple(c for c in DEFENSE_COLUMNS if c not in columns)
        for name, columns in GROUPS.items()
    },
}


def _matrix(
    rows: tuple[MatchupRow, ...],
    joined: dict[str, dict[str, float | int | None]],
    columns: tuple[str, ...],
) -> np.ndarray:
    return np.asarray([
        [
            np.nan if value is None else value
            for value in (
                *(row.feature_differences[name] for name in FEATURE_COLUMNS),
                *(joined[row.source_bout_id][name] for name in columns),
            )
        ]
        for row in rows
    ], dtype=float)


def _score(predictions: list[dict], name: str) -> dict:
    selected = [row for row in predictions if row["target_a_win"] is not None]
    labels = [row["target_a_win"] for row in selected]
    probabilities = np.asarray([
        row["probabilities_a_win"][name] for row in selected
    ])
    return {"decisive_bouts": len(selected), "correct_bouts": int(sum(
        (probabilities >= 0.5) == labels
    )), **_metrics(labels, probabilities)}


def _delta(score: dict, reference: dict) -> dict:
    return {
        name: score[name] - reference[name]
        if score[name] is not None and reference[name] is not None else None
        for name in ("accuracy", "roc_auc", "log_loss", "brier_score")
    }


def compare_groups(
    rows: tuple[MatchupRow, ...],
    defense: dict[tuple[str, str], DefensiveHistory],
) -> tuple[list[dict], dict]:
    """Reuse baseline/full forecasts and fit eight exploratory variants."""
    paired, reference = compare_defense(rows, defense)
    joined = join_defense(rows, defense)
    predictions = [{
        **{key: value for key, value in row.items()
           if key not in ("baseline_probability_a_win", "defense_probability_a_win")},
        "probabilities_a_win": {
            "baseline": row["baseline_probability_a_win"],
            "all_defense": row["defense_probability_a_win"],
        },
    } for row in paired]
    by_bout = {row["source_bout_id"]: row for row in predictions}
    if len(by_bout) != len(predictions):
        raise ValueError("Duplicate group validation bout.")
    ordered = tuple(sorted(rows, key=lambda r: (r.event_date, r.source_bout_id)))
    fold_reports = []
    for fold, original_fold in zip(
        DEVELOPMENT_FOLDS, reference["folds"], strict=True
    ):
        train = tuple(r for r in ordered if r.event_date <= fold.train_through
                      and r.target_a_win is not None)
        validation = tuple(r for r in ordered if fold.validate_from <= r.event_date
                           <= fold.validate_through)
        selected = tuple(r for r in validation if r.target_a_win is not None)
        if len(validation) != original_fold["validation_bouts"]:
            raise ValueError(f"Validation cohort changed: {fold.name}")
        for name, columns in VARIANTS.items():
            if name in ("baseline", "all_defense"):
                continue
            model = Pipeline([
                ("imputer", SimpleImputer(
                    strategy="median", add_indicator=True, keep_empty_features=True
                )),
                ("scaler", StandardScaler()),
                ("classifier", LogisticRegression(max_iter=1000, solver="lbfgs")),
            ])
            model.fit(_matrix(train, joined, columns),
                      [r.target_a_win for r in train])
            probabilities = model.predict_proba(
                _matrix(selected, joined, columns)
            )[:, 1]
            for row, probability in zip(selected, probabilities, strict=True):
                by_bout[row.source_bout_id]["probabilities_a_win"][name] = float(
                    probability
                )
        for row in validation:
            saved = by_bout[row.source_bout_id]
            if saved["fold"] != fold.name:
                raise ValueError(f"Validation fold changed: {row.source_bout_id}")
            if row.target_a_win is None:
                saved["probabilities_a_win"].update({
                    name: None for name in VARIANTS
                })
            elif set(saved["probabilities_a_win"]) != set(VARIANTS):
                raise ValueError(f"Missing variant: {row.source_bout_id}")
        in_fold = [row for row in predictions if row["fold"] == fold.name]
        fold_reports.append({
            "name": fold.name,
            "train_bouts": original_fold["train_bouts"],
            "validation_bouts": len(validation),
            "draw_nc_exclusions": len(validation) - len(selected),
            "scores": {name: _score(in_fold, name) for name in VARIANTS},
        })
    pooled = {name: _score(predictions, name) for name in VARIANTS}
    if pooled["baseline"]["accuracy"] != (
        reference["paired_all_validation"]["baseline"]["accuracy"]
    ) or pooled["all_defense"]["accuracy"] != (
        reference["paired_all_validation"]["with_defense"]["accuracy"]
    ):
        raise ValueError("Reference scores changed.")
    return predictions, {
        "folds": fold_reports,
        "pooled": pooled,
        "delta_from_baseline": {
            name: _delta(score, pooled["baseline"])
            for name, score in pooled.items() if name.startswith("add_")
        },
        "delta_from_all_defense": {
            name: _delta(score, pooled["all_defense"])
            for name, score in pooled.items() if name.startswith("without_")
        },
        "validation_bouts": len(predictions),
        "decisive_bouts": pooled["baseline"]["decisive_bouts"],
        "draw_nc_exclusions": sum(
            row["target_a_win"] is None for row in predictions
        ),
    }


def export_defense_groups(
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
    predictions, report = compare_groups(rows, defense)
    manifest = {
        "experiment": "defense_groups_v1",
        "status": "exploratory; folds already used to select defensive features",
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
        "groups": {name: list(columns) for name, columns in GROUPS.items()},
        "variants": {name: list(columns) for name, columns in VARIANTS.items()},
        "fit": "per-fold train-only median + missing indicators + scaling "
               "+ logistic regression (max_iter=1000, lbfgs); threshold 0.5",
        "environment": {
            "python": platform.python_version(),
            "numpy": np.__version__,
            "scikit_learn": sklearn.__version__,
        },
        **report,
    }
    _write_verified_json(
        output_directory / "predictions.jsonl", predictions, json_lines=True
    )
    _write_verified_json(
        output_directory / "manifest.json", manifest, json_lines=False
    )
    return manifest
