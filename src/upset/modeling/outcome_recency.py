"""Compare frozen baseline and defense with dated UFC outcome histories."""

import platform
from pathlib import Path

import numpy as np
import sklearn
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from upset.data.audit_prefight_outcomes import audit_prefight_outcomes
from upset.data.export_prefight import read_identified
from upset.data.identify_historical import IdentifiedFight
from upset.data.matchups import MatchupRow
from upset.data.models import Fight
from upset.data.prefight_defense import DefensiveHistory
from upset.data.prefight_outcomes import OutcomeHistory, read_outcome_history
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

OUTCOME_FIELDS = (
    "prior_win_rate",
    "prior_365_day_wins",
    "prior_365_day_losses",
    "days_since_last_bout",
)
OUTCOME_COLUMNS = tuple(f"{name}_diff" for name in OUTCOME_FIELDS)
VARIANTS = {
    "baseline": FEATURE_COLUMNS,
    "all_defense": FEATURE_COLUMNS + DEFENSE_COLUMNS,
    "baseline_plus_outcomes": FEATURE_COLUMNS + OUTCOME_COLUMNS,
    "defense_plus_outcomes": FEATURE_COLUMNS + DEFENSE_COLUMNS + OUTCOME_COLUMNS,
}


def join_outcomes(
    rows: tuple[MatchupRow, ...],
    outcomes: dict[tuple[str, str], OutcomeHistory],
) -> dict[str, dict[str, float | int | None]]:
    expected = {(row.source_bout_id, fighter_id)
                for row in rows
                for fighter_id in (row.fighter_a_id, row.fighter_b_id)}
    if set(outcomes) != expected:
        raise ValueError("Outcome join keys differ from matchup participants.")
    result = {}
    for row in rows:
        a = outcomes[row.source_bout_id, row.fighter_a_id]
        b = outcomes[row.source_bout_id, row.fighter_b_id]
        if a.event_date != row.event_date or b.event_date != row.event_date:
            raise ValueError(f"Outcome and matchup dates differ: {row.source_bout_id}")
        result[row.source_bout_id] = {
            f"{field}_diff": (
                getattr(a, field) - getattr(b, field)
                if getattr(a, field) is not None
                and getattr(b, field) is not None else None
            )
            for field in OUTCOME_FIELDS
        }
    return result


def _matrix(
    rows: tuple[MatchupRow, ...],
    defense: dict[str, dict[str, float | int | None]],
    outcomes: dict[str, dict[str, float | int | None]],
    columns: tuple[str, ...],
) -> np.ndarray:
    return np.asarray([
        [np.nan if value is None else value for value in (
            *(row.feature_differences[name] for name in FEATURE_COLUMNS),
            *(defense[row.source_bout_id][name] for name in columns
              if name in DEFENSE_COLUMNS),
            *(outcomes[row.source_bout_id][name] for name in columns
              if name in OUTCOME_COLUMNS),
        )]
        for row in rows
    ], dtype=float)


def _score(predictions: list[dict], variant: str) -> dict:
    chosen = [row for row in predictions if row["target_a_win"] is not None]
    y = [row["target_a_win"] for row in chosen]
    probabilities = np.asarray([
        row["probabilities_a_win"][variant] for row in chosen
    ])
    return {"decisive_bouts": len(chosen),
            "correct_bouts": int(sum((probabilities >= 0.5) == y)),
            **_metrics(y, probabilities)}


def compare_outcome_recency(
    rows: tuple[MatchupRow, ...],
    defense: dict[tuple[str, str], DefensiveHistory],
    outcomes: dict[tuple[str, str], OutcomeHistory],
) -> tuple[list[dict], dict]:
    """Retain exact fixed references; fit two further variants per fold."""
    prior, reference = compare_defense(rows, defense)
    defensive = join_defense(rows, defense)
    outcome = join_outcomes(rows, outcomes)
    predictions = [{
        **{key: value for key, value in item.items()
           if key not in ("baseline_probability_a_win", "defense_probability_a_win")},
        "probabilities_a_win": {
            "baseline": item["baseline_probability_a_win"],
            "all_defense": item["defense_probability_a_win"],
        },
    } for item in prior]
    by_bout = {item["source_bout_id"]: item for item in predictions}
    if len(by_bout) != len(predictions):
        raise ValueError("Duplicate validation bout.")
    ordered = tuple(sorted(rows, key=lambda r: (r.event_date, r.source_bout_id)))
    folds = []
    for fold, original in zip(DEVELOPMENT_FOLDS, reference["folds"], strict=True):
        train = tuple(r for r in ordered if r.event_date <= fold.train_through
                      and r.target_a_win is not None)
        validation = tuple(r for r in ordered if fold.validate_from <= r.event_date
                           <= fold.validate_through)
        selected = tuple(r for r in validation if r.target_a_win is not None)
        if (original["name"] != fold.name
                or original["validation_bouts"] != len(validation)):
            raise ValueError(f"Validation cohort changed: {fold.name}")
        for name in ("baseline_plus_outcomes", "defense_plus_outcomes"):
            model = Pipeline([
                ("imputer", SimpleImputer(
                    strategy="median", add_indicator=True, keep_empty_features=True
                )),
                ("scaler", StandardScaler()),
                ("classifier", LogisticRegression(max_iter=1000, solver="lbfgs")),
            ])
            model.fit(_matrix(train, defensive, outcome, VARIANTS[name]),
                      [r.target_a_win for r in train])
            probabilities = model.predict_proba(
                _matrix(selected, defensive, outcome, VARIANTS[name])
            )[:, 1]
            for row, probability in zip(selected, probabilities, strict=True):
                by_bout[row.source_bout_id]["probabilities_a_win"][name] = float(
                    probability
                )
        for row in validation:
            record = by_bout[row.source_bout_id]
            if record["fold"] != fold.name:
                raise ValueError(f"Baseline fold differs: {row.source_bout_id}")
            if row.target_a_win is None:
                record["probabilities_a_win"].update({
                    name: None for name in VARIANTS
                })
            elif set(record["probabilities_a_win"]) != set(VARIANTS):
                raise ValueError(f"Missing outcome variant: {row.source_bout_id}")
        in_fold = [item for item in predictions if item["fold"] == fold.name]
        folds.append({
            "name": fold.name,
            "train_bouts": original["train_bouts"],
            "validation_bouts": len(validation),
            "draw_nc_exclusions": len(validation) - len(selected),
            "outcome_missing_by_feature": {
                column: sum(outcome[row.source_bout_id][column] is None
                            for row in selected)
                for column in OUTCOME_COLUMNS
            },
            "scores": {name: _score(in_fold, name) for name in VARIANTS},
        })
    scores = {name: _score(predictions, name) for name in VARIANTS}
    for name, ref in (
        ("baseline", "baseline"), ("all_defense", "with_defense")
    ):
        for metric, value in reference["paired_all_validation"][ref].items():
            if scores[name][metric] != value:
                raise ValueError(f"Reference metric changed: {name}/{metric}")
    return predictions, {
        "folds": folds,
        "pooled": scores,
        "validation_bouts": len(predictions),
        "decisive_bouts": scores["baseline"]["decisive_bouts"],
        "draw_nc_exclusions": sum(item["target_a_win"] is None
                                  for item in predictions),
        "deltas": {
            name: {
                metric: scores[name][metric] - scores[reference_name][metric]
                if (scores[name][metric] is not None
                    and scores[reference_name][metric] is not None) else None
                for metric in ("accuracy", "roc_auc", "log_loss", "brier_score")
            }
            for name, reference_name in (
                ("baseline_plus_outcomes", "baseline"),
                ("defense_plus_outcomes", "all_defense"),
            )
        },
    }


def export_outcome_comparison(
    matchup_path: Path,
    defensive_path: Path,
    outcome_path: Path,
    identified_fights_path: Path,
    registry_path: Path,
    output_directory: Path,
    code_commit: str,
) -> dict:
    if not code_commit or not code_commit.strip():
        raise ValueError("A code commit is required.")
    paths = (matchup_path, defensive_path, outcome_path,
             identified_fights_path, registry_path, output_directory)
    if len({path.resolve() for path in paths}) != len(paths):
        raise ValueError("Experiment output must not replace an input.")
    if not registry_path.is_file():
        raise ValueError("The committed fighter registry is required.")
    rows = read_matchups(matchup_path)
    defense = read_defensive_history(defensive_path)
    outcomes = read_outcome_history(outcome_path)
    fights = read_identified(
        identified_fights_path, Fight, IdentifiedFight,
        ("upset_fighter_1_id", "upset_fighter_2_id"),
    )
    audit = audit_prefight_outcomes(fights, outcomes)
    predictions, report = compare_outcome_recency(rows, defense, outcomes)
    manifest = {
        "experiment": "outcome_recency_v1",
        "status": "exploratory; development folds previously examined",
        "code_commit": code_commit,
        "matchups_sha256": _sha256(matchup_path),
        "defensive_history_sha256": _sha256(defensive_path),
        "outcome_history_sha256": _sha256(outcome_path),
        "identified_fights_sha256": _sha256(identified_fights_path),
        "registry_sha256": _sha256(registry_path),
        "outcome_audit": audit,
        "total_source_bouts": len(rows),
        "source_bouts_after_development": sum(
            row.event_date > DEVELOPMENT_LAST_DATE for row in rows
        ),
        "development_last_date": DEVELOPMENT_LAST_DATE,
        "original_examined_test_first_date": "2023-08-26",
        "prediction_cutoff": PREDICTION_CUTOFF,
        "outcome_features": list(OUTCOME_COLUMNS),
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
