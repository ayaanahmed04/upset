"""Frozen development folds and auditable, out-of-time baseline predictions.

The original 70/15/15 baseline remains an unchanged historical reference.
This experiment uses only dates before its previously examined test period.
"""

import hashlib
import json
import platform
from dataclasses import asdict, dataclass
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np
import sklearn
from sklearn.metrics import accuracy_score, brier_score_loss, log_loss, roc_auc_score

from upset.data.matchups import MatchupRow
from upset.modeling.baseline import FEATURE_COLUMNS, fit_baseline, read_matchups

DEVELOPMENT_LAST_DATE = "2023-08-19"
PREDICTION_CUTOFF = "strictly earlier event dates"
MODEL_NAME = "original_nine_feature_logistic"


@dataclass(frozen=True)
class Fold:
    name: str
    train_through: str
    validate_from: str
    validate_through: str


# Boundaries were set by calendar year before evaluating candidate features.
# Validation windows do not overlap. The intervening dates still enter later
# training histories; the already examined 2023-08-26+ test is never used.
DEVELOPMENT_FOLDS = (
    Fold("2019", "2018-12-31", "2019-01-01", "2019-12-31"),
    Fold("2021", "2020-12-31", "2021-01-01", "2021-12-31"),
    Fold("2022", "2021-12-31", "2022-01-01", "2022-12-31"),
    Fold("2023_partial", "2022-12-31", "2023-01-01", DEVELOPMENT_LAST_DATE),
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _matrix(rows: tuple[MatchupRow, ...]) -> np.ndarray:
    return np.asarray(
        [
            [
                np.nan if row.feature_differences[column] is None
                else row.feature_differences[column]
                for column in FEATURE_COLUMNS
            ]
            for row in rows
        ],
        dtype=float,
    )


def development_predictions(
    rows: tuple[MatchupRow, ...],
) -> tuple[list[dict], list[dict]]:
    """Fit anew on each earlier window and predict every later validation bout."""
    if not rows:
        raise ValueError("No matchup rows were supplied.")
    ordered = tuple(sorted(rows, key=lambda r: (r.event_date, r.source_bout_id)))
    predictions: list[dict] = []
    fold_reports: list[dict] = []
    used: set[str] = set()

    for fold in DEVELOPMENT_FOLDS:
        if not (fold.train_through < fold.validate_from <= fold.validate_through):
            raise ValueError(f"Invalid fold dates: {fold.name}")
        train = tuple(r for r in ordered if r.event_date <= fold.train_through)
        validation = tuple(
            r for r in ordered
            if fold.validate_from <= r.event_date <= fold.validate_through
        )
        selected = tuple(r for r in validation if r.target_a_win is not None)
        if not train or not selected:
            raise ValueError(f"Empty training or decisive validation: {fold.name}")
        if any(r.source_bout_id in used for r in validation):
            raise ValueError("Validation folds overlap.")
        used.update(r.source_bout_id for r in validation)

        model = fit_baseline(train)
        probabilities = model.predict_proba(_matrix(selected))[:, 1]
        probability_by_bout = {
            row.source_bout_id: float(probability)
            for row, probability in zip(selected, probabilities, strict=True)
        }
        labels = [r.target_a_win for r in selected]
        fold_reports.append(
            {
                **asdict(fold),
                "train_bouts": len(train),
                "train_decisive": sum(r.target_a_win is not None for r in train),
                "validation_bouts": len(validation),
                "validation_decisive": len(selected),
                "validation_draw_nc": len(validation) - len(selected),
                "accuracy": float(accuracy_score(labels, probabilities >= 0.5)),
                "roc_auc": float(roc_auc_score(labels, probabilities))
                if len(set(labels)) == 2 else None,
                "log_loss": float(log_loss(labels, probabilities, labels=[0, 1])),
                "brier_score": float(brier_score_loss(labels, probabilities)),
            }
        )
        for row in validation:
            predictions.append(
                {
                    "fold": fold.name,
                    "source_bout_id": row.source_bout_id,
                    "event_date": row.event_date,
                    "fighter_a_id": row.fighter_a_id,
                    "fighter_b_id": row.fighter_b_id,
                    "target_a_win": row.target_a_win,
                    "probability_a_win": probability_by_bout.get(row.source_bout_id),
                    "exclusion_reason": row.training_exclusion_reason,
                    "prediction_cutoff": PREDICTION_CUTOFF,
                }
            )
    return predictions, fold_reports


def _write_verified_json(path: Path, value: dict | list[dict], *,
                         json_lines: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=path.parent, prefix=".upset-evaluation-") as tmp:
        staged = Path(tmp) / path.name
        with staged.open("w", encoding="utf-8", newline="\n") as saved:
            if json_lines:
                for record in value:
                    saved.write(
                        json.dumps(record, allow_nan=False, sort_keys=True) + "\n"
                    )
            else:
                saved.write(json.dumps(value, allow_nan=False, indent=2, sort_keys=True)
                            + "\n")
        with staged.open(encoding="utf-8") as check:
            restored = ([json.loads(line) for line in check] if json_lines
                        else json.load(check))
        if restored != value:
            raise ValueError("Evaluation read-back verification failed.")
        staged.replace(path)


def export_development_evaluation(
    matchup_path: Path, registry_path: Path, output_directory: Path,
    code_commit: str,
) -> dict:
    """Save paired prediction rows and provenance; do not touch v1 exports."""
    if not code_commit or not code_commit.strip():
        raise ValueError("A code commit is required for the experiment manifest.")
    if not registry_path.is_file():
        raise ValueError("The committed identity registry is required.")
    rows = read_matchups(matchup_path)
    predictions, reports = development_predictions(rows)
    input_hash = _sha256(matchup_path)
    registry_hash = _sha256(registry_path)
    manifest = {
        "experiment": "frozen_development_baseline_v1",
        "model": MODEL_NAME,
        "code_commit": code_commit,
        "matchups_sha256": input_hash,
        "registry_sha256": registry_hash,
        "total_source_bouts": len(rows),
        "development_last_date": DEVELOPMENT_LAST_DATE,
        "original_examined_test_first_date": "2023-08-26",
        "source_bouts_after_development": sum(
            r.event_date > DEVELOPMENT_LAST_DATE for r in rows
        ),
        "validation_predictions": len(predictions),
        "validation_decisive": sum(
            r["target_a_win"] is not None for r in predictions
        ),
        "validation_draw_nc": sum(
            r["target_a_win"] is None for r in predictions
        ),
        "prediction_cutoff": PREDICTION_CUTOFF,
        "features": list(FEATURE_COLUMNS),
        "fit": {
            "imputation": "train-only median, missing indicators, keep empty",
            "scaling": "train-only standard scaling",
            "classifier": "LogisticRegression(max_iter=1000, solver=lbfgs)",
            "seed": None,
            "retraining": "once per fold on all earlier training dates",
            "threshold": 0.5,
        },
        "environment": {
            "python": platform.python_version(),
            "numpy": np.__version__,
            "scikit_learn": sklearn.__version__,
        },
        "folds": reports,
    }
    if output_directory.resolve() in (matchup_path.resolve(), registry_path.resolve()):
        raise ValueError("Output directory must not replace an input.")
    _write_verified_json(
        output_directory / "predictions.jsonl", predictions, json_lines=True
    )
    _write_verified_json(
        output_directory / "manifest.json", manifest, json_lines=False
    )
    return manifest
