"""Bounded opponent-strength study on the frozen development cohorts."""

import json
import platform
from dataclasses import asdict
from math import isclose
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np
import sklearn
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from threadpoolctl import threadpool_limits

from upset.data.audit_prefight_ratings import audit_prefight_ratings
from upset.data.export_prefight import read_identified
from upset.data.identify_historical import IdentifiedFight
from upset.data.matchups import AMBIGUOUS_OUTCOME, MatchupRow
from upset.data.models import Fight
from upset.data.prefight_defense import DefensiveHistory
from upset.data.prefight_ratings import (
    INITIAL_RATING,
    K_FACTOR,
    RATING_SCALE,
    RatingHistory,
    read_rating_history,
)
from upset.modeling.baseline import FEATURE_COLUMNS, read_matchups
from upset.modeling.defense_ablation import (
    DEFENSE_COLUMNS,
    _metrics,
    _paired_summary,
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

DEFENSE_FEATURES = FEATURE_COLUMNS + DEFENSE_COLUMNS
ELO_COLUMN = "elo_rating_diff"
VARIANTS = {
    "baseline": FEATURE_COLUMNS,
    "all_defense": DEFENSE_FEATURES,
    "elo_only": (ELO_COLUMN,),
    "defense_plus_elo": DEFENSE_FEATURES + (ELO_COLUMN,),
    "boosted_defense": DEFENSE_FEATURES,
    "boosted_defense_plus_elo": DEFENSE_FEATURES + (ELO_COLUMN,),
}
# Fixed before seeing any full-data scores; no random early-stopping holdout.
BOOSTED_SETTINGS = {
    "loss": "log_loss",
    "learning_rate": 0.05,
    "max_iter": 150,
    "max_leaf_nodes": 7,
    "max_depth": 3,
    "min_samples_leaf": 30,
    "l2_regularization": 5.0,
    "max_bins": 255,
    "categorical_features": None,
    "early_stopping": False,
    "random_state": 20260924,
}
PAIRS = (
    ("elo_only", "all_defense"),
    ("defense_plus_elo", "all_defense"),
    ("boosted_defense", "all_defense"),
    ("boosted_defense_plus_elo", "all_defense"),
    ("boosted_defense_plus_elo", "boosted_defense"),
)


def join_ratings(
    rows: tuple[MatchupRow, ...],
    ratings: dict[tuple[str, str], RatingHistory],
) -> dict[str, tuple[RatingHistory, RatingHistory]]:
    expected = {
        (r.source_bout_id, i) for r in rows for i in (r.fighter_a_id, r.fighter_b_id)
    }
    if len({r.source_bout_id for r in rows}) != len(rows):
        raise ValueError("Duplicate matchup bout.")
    if set(ratings) != expected:
        raise ValueError("Rating join keys differ from matchup participants.")
    joined = {}
    for row in rows:
        a, b = (
            ratings[row.source_bout_id, i] for i in (row.fighter_a_id, row.fighter_b_id)
        )
        if a.event_date != row.event_date or b.event_date != row.event_date:
            raise ValueError(f"Rating and matchup dates differ: {row.source_bout_id}")
        if (
            a.upset_fighter_id != row.fighter_a_id
            or b.upset_fighter_id != row.fighter_b_id
            or a.opponent_id != row.fighter_b_id
            or b.opponent_id != row.fighter_a_id
            or a.rating != b.opponent_rating
            or b.rating != a.opponent_rating
            or not isclose(
                a.elo_probability + b.elo_probability, 1, rel_tol=0, abs_tol=1e-12
            )
        ):
            raise ValueError(f"Rating opponent mismatch: {row.source_bout_id}")
        joined[row.source_bout_id] = a, b
    return joined


def _logistic() -> Pipeline:
    return Pipeline(
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


def _matrix(rows, defense, ratings, columns) -> np.ndarray:
    values = []
    for row in rows:
        a, b = ratings[row.source_bout_id]
        record = {
            **row.feature_differences,
            **defense[row.source_bout_id],
            ELO_COLUMN: a.rating - b.rating,
        }
        values.append([np.nan if record[c] is None else record[c] for c in columns])
    return np.asarray(values, dtype=float)


def _scores(predictions: list[dict]) -> dict:
    decisive = [r for r in predictions if r["target_a_win"] is not None]
    if not decisive:
        return {
            name: {
                "decisive_bouts": 0,
                "correct_bouts": 0,
                "accuracy": None,
                "roc_auc": None,
                "log_loss": None,
                "brier_score": None,
            }
            for name in VARIANTS
        }
    y = np.asarray([r["target_a_win"] for r in decisive])
    scores = {}
    for name in VARIANTS:
        p = np.asarray([r["probabilities_a_win"][name] for r in decisive])
        scores[name] = {
            "decisive_bouts": len(y),
            "correct_bouts": int(np.sum((p >= 0.5) == y)),
            **_metrics(y.tolist(), p),
        }
    return scores


def _diagnostics(predictions: list[dict]) -> dict:
    decisive = [r for r in predictions if r["target_a_win"] is not None]
    groups = {
        "history": ("neither_has_history", "one_has_history", "both_have_history"),
        "experience": ("at_least_one_under_3_bouts", "both_at_least_3_bouts"),
        "missingness": ("any_missing_defense_input", "complete_defense_inputs"),
    }
    slices = {}
    for field, labels in groups.items():
        slices[field] = {}
        for label in labels:
            selected = [r for r in decisive if r["diagnostic_groups"][field] == label]
            slices[field][label] = {
                "coverage": len(selected) / len(decisive),
                "scores": _scores(selected),
            }
    reliability, symmetry = {}, {}
    for name in VARIANTS:
        p = np.asarray([r["probabilities_a_win"][name] for r in decisive])
        swapped = np.asarray([r["swapped_probabilities_b_win"][name] for r in decisive])
        errors = np.abs(p + swapped - 1)
        symmetry[name] = {
            "mean_absolute_error": float(errors.mean()),
            "maximum_absolute_error": float(errors.max()),
            "bouts_error_over_0_01": int(np.sum(errors > 0.01)),
        }
        targets = np.asarray([r["target_a_win"] for r in decisive])
        bin_ids = np.minimum((p * 10).astype(int), 9)
        reliability[name] = []
        for bin_id in range(10):
            mask = bin_ids == bin_id
            reliability[name].append(
                {
                    "lower": bin_id / 10,
                    "upper": (bin_id + 1) / 10,
                    "count": int(mask.sum()),
                    "mean_probability": float(p[mask].mean()) if mask.any() else None,
                    "observed_a_win_fraction": (
                        float(targets[mask].mean()) if mask.any() else None
                    ),
                }
            )
    return {
        "subgroups": slices,
        "symmetry": symmetry,
        "reliability_deciles": reliability,
    }


def _preserve_references(generated: list[dict], saved: list[dict] | None) -> list[dict]:
    if saved is None:
        return generated
    by_bout = {row["source_bout_id"]: row for row in saved}
    if len(by_bout) != len(saved) or set(by_bout) != {
        row["source_bout_id"] for row in generated
    }:
        raise ValueError("Saved reference cohort differs.")
    result = []
    for row in generated:
        old = by_bout[row["source_bout_id"]]
        if set(old) != set(row):
            raise ValueError("Saved reference schema differs.")
        for field, value in row.items():
            if field in ("baseline_probability_a_win", "defense_probability_a_win"):
                previous = old[field]
                if value is None:
                    valid = previous is None
                else:
                    valid = (
                        type(previous) in (int, float)
                        and 0 <= previous <= 1
                        and isclose(previous, value, rel_tol=0, abs_tol=1e-12)
                    )
            else:
                valid = old[field] == value
            if not valid:
                raise ValueError(
                    f"Saved reference differs: {row['source_bout_id']}/{field}"
                )
        # Carry the original stored probabilities, including their exact floats.
        result.append(dict(old))
    return result


def compare_elo(
    rows: tuple[MatchupRow, ...],
    defense: dict[tuple[str, str], DefensiveHistory],
    ratings: dict[tuple[str, str], RatingHistory],
    saved_references: list[dict] | None = None,
) -> tuple[list[dict], dict]:
    joined = join_ratings(rows, ratings)
    defensive = join_defense(rows, defense)
    for row in rows:
        a, b = joined[row.source_bout_id]
        if (
            row.feature_differences["prior_fights_diff"]
            != a.prior_fights - b.prior_fights
            or defense[row.source_bout_id, row.fighter_a_id].prior_fights
            != a.prior_fights
            or defense[row.source_bout_id, row.fighter_b_id].prior_fights
            != b.prior_fights
        ):
            raise ValueError(f"Prior appearance counts differ: {row.source_bout_id}")
    original, _ = compare_defense(rows, defense)
    references = _preserve_references(original, saved_references)
    predictions = [
        {
            **{
                k: v
                for k, v in row.items()
                if k not in ("baseline_probability_a_win", "defense_probability_a_win")
            },
            "probabilities_a_win": {
                "baseline": row["baseline_probability_a_win"],
                "all_defense": row["defense_probability_a_win"],
            },
            "swapped_probabilities_b_win": {},
        }
        for row in references
    ]
    by_bout = {r["source_bout_id"]: r for r in predictions}
    ordered = sorted(rows, key=lambda r: (r.event_date, r.source_bout_id))
    folds = []
    # Limiting numerical threads avoids oversubscription on small datasets.
    with threadpool_limits(limits=1):
        for fold in DEVELOPMENT_FOLDS:
            train = tuple(
                r
                for r in ordered
                if r.event_date <= fold.train_through and r.target_a_win is not None
            )
            validation = tuple(
                r
                for r in ordered
                if fold.validate_from <= r.event_date <= fold.validate_through
            )
            selected = tuple(r for r in validation if r.target_a_win is not None)
            for name, columns in VARIANTS.items():
                if name == "elo_only":
                    forward = [
                        joined[r.source_bout_id][0].elo_probability for r in selected
                    ]
                    backward = [
                        joined[r.source_bout_id][1].elo_probability for r in selected
                    ]
                else:
                    model = (
                        HistGradientBoostingClassifier(**BOOSTED_SETTINGS)
                        if name.startswith("boosted_")
                        else _logistic()
                    )
                    model.fit(
                        _matrix(train, defensive, joined, columns),
                        [r.target_a_win for r in train],
                    )
                    matrix = _matrix(selected, defensive, joined, columns)
                    forward = model.predict_proba(matrix)[:, 1]
                    # Every input is an A-minus-B difference; NaN stays NaN.
                    backward = model.predict_proba(-matrix)[:, 1]
                for row, probability, swapped in zip(
                    selected, forward, backward, strict=True
                ):
                    record = by_bout[row.source_bout_id]
                    if name in ("baseline", "all_defense"):
                        if not isclose(
                            record["probabilities_a_win"][name],
                            probability,
                            rel_tol=0,
                            abs_tol=1e-12,
                        ):
                            raise ValueError(f"Reference refit changed: {name}")
                    else:
                        record["probabilities_a_win"][name] = float(probability)
                    record["swapped_probabilities_b_win"][name] = float(swapped)
            for row in validation:
                record = by_bout[row.source_bout_id]
                a, b = joined[row.source_bout_id]
                history_count = int(a.prior_fights > 0) + int(b.prior_fights > 0)
                record["diagnostic_groups"] = {
                    "history": (
                        "neither_has_history",
                        "one_has_history",
                        "both_have_history",
                    )[history_count],
                    "experience": (
                        "at_least_one_under_3_bouts"
                        if min(a.prior_fights, b.prior_fights) < 3
                        else "both_at_least_3_bouts"
                    ),
                    "missingness": (
                        "any_missing_defense_input"
                        if np.isnan(
                            _matrix((row,), defensive, joined, DEFENSE_FEATURES)
                        ).any()
                        else "complete_defense_inputs"
                    ),
                }
                if row.target_a_win is None:
                    record["probabilities_a_win"] = dict.fromkeys(VARIANTS)
                    record["swapped_probabilities_b_win"] = dict.fromkeys(VARIANTS)
            in_fold = [r for r in predictions if r["fold"] == fold.name]
            folds.append(
                {
                    **asdict(fold),
                    "train_decisive": len(train),
                    "validation_bouts": len(validation),
                    "draw_nc_exclusions": len(validation) - len(selected),
                    "scores": _scores(in_fold),
                }
            )
    paired = {}
    for candidate, reference in PAIRS:
        result = _paired_summary(
            [
                {
                    "event_date": r["event_date"],
                    "target_a_win": r["target_a_win"],
                    "baseline_probability_a_win": r["probabilities_a_win"][reference],
                    "defense_probability_a_win": r["probabilities_a_win"][candidate],
                }
                for r in predictions
            ]
        )
        paired[f"{candidate}_minus_{reference}"] = {
            "delta": result["delta_defense_minus_baseline"],
            "date_cluster_bootstrap_95_percent": result[
                "date_cluster_bootstrap_95_percent"
            ],
        }
    scores = _scores(predictions)
    return predictions, {
        "folds": folds,
        "pooled": scores,
        "validation_bouts": len(predictions),
        "decisive_bouts": scores["baseline"]["decisive_bouts"],
        "draw_nc_exclusions": sum(r["target_a_win"] is None for r in predictions),
        "paired_comparisons": paired,
        **_diagnostics(predictions),
    }


def _audit_matchup_sources(rows, fights) -> None:
    sources = {f.fight.source_bout_id: f for f in fights}
    if set(sources) != {r.source_bout_id for r in rows} or len(sources) != len(fights):
        raise ValueError("Source and matchup coverage differ.")
    for row in rows:
        source = sources[row.source_bout_id]
        fight = source.fight
        ids = source.upset_fighter_1_id, source.upset_fighter_2_id
        target = None
        if fight.source_winner_label != "Draw/NC":
            winner = ids[0] if fight.winner_name == fight.fighter_1_name else ids[1]
            target = int(winner == row.fighter_a_id)
        if (
            tuple(sorted(ids)) != (row.fighter_a_id, row.fighter_b_id)
            or row.event_date != fight.event_date
            or row.target_a_win != target
            or row.source_winner_label != fight.source_winner_label
            or row.training_exclusion_reason
            != (AMBIGUOUS_OUTCOME if target is None else None)
        ):
            raise ValueError(
                f"Source and matchup identity/date/target differ: {row.source_bout_id}"
            )


def export_elo_comparison(
    matchup_path: Path,
    defensive_path: Path,
    ratings_path: Path,
    fights_path: Path,
    registry_path: Path,
    reference_directory: Path,
    output_directory: Path,
    code_commit: str,
) -> dict:
    if not code_commit or not code_commit.strip():
        raise ValueError("A code commit is required.")
    inputs = {
        "matchups": matchup_path,
        "defensive_history": defensive_path,
        "rating_history": ratings_path,
        "identified_fights": fights_path,
        "registry": registry_path,
        "reference_predictions": reference_directory / "predictions.jsonl",
        "reference_manifest": reference_directory / "manifest.json",
    }
    if len({p.resolve() for p in inputs.values()}) != len(inputs):
        raise ValueError("Experiment inputs must be distinct.")
    if output_directory.exists():
        raise ValueError(
            "Experiment output already exists; use a new --output directory."
        )
    if any(
        output_directory.resolve() == p.resolve()
        or output_directory.resolve() in p.resolve().parents
        for p in inputs.values()
    ):
        raise ValueError("Output must not contain or replace an input.")
    hashes = {name + "_sha256": _sha256(path) for name, path in inputs.items()}
    previous = json.loads(inputs["reference_manifest"].read_text(encoding="utf-8"))
    if previous.get("experiment") != "defense_ablation_v1":
        raise ValueError("Expected the preserved defense_ablation_v1 reference.")
    for name in ("matchups_sha256", "defensive_history_sha256", "registry_sha256"):
        if previous.get(name) != hashes[name]:
            raise ValueError(f"Reference input hash differs: {name}")
    saved = [
        json.loads(line)
        for line in inputs["reference_predictions"]
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    rows = read_matchups(matchup_path)
    defense, ratings = (
        read_defensive_history(defensive_path),
        read_rating_history(ratings_path),
    )
    fights = read_identified(
        fights_path,
        Fight,
        IdentifiedFight,
        ("upset_fighter_1_id", "upset_fighter_2_id"),
    )
    audit = audit_prefight_ratings(fights, ratings)
    _audit_matchup_sources(rows, fights)
    predictions, report = compare_elo(rows, defense, ratings, saved)
    classes = {
        f.fight.source_bout_id: f.fight.weight_class or "unknown" for f in fights
    }
    for row in predictions:
        row["weight_class"] = classes[row["source_bout_id"]]
    report["weight_class_scores"] = {
        name: _scores([r for r in predictions if r["weight_class"] == name])
        for name in sorted({r["weight_class"] for r in predictions})
    }
    manifest = {
        "experiment": "elo_comparison_v1",
        "status": "exploratory; previously examined development folds; no promotion",
        "code_commit": code_commit,
        **hashes,
        "rating_audit": audit,
        "reference_probabilities": "exact saved values; refit agreement within 1e-12",
        "reference_code_commit": previous.get("code_commit"),
        "total_source_bouts": len(rows),
        "source_bouts_after_development": sum(
            r.event_date > DEVELOPMENT_LAST_DATE for r in rows
        ),
        "development_last_date": DEVELOPMENT_LAST_DATE,
        "original_examined_test_first_date": "2023-08-26",
        "prediction_cutoff": PREDICTION_CUTOFF,
        "variants": {name: list(columns) for name, columns in VARIANTS.items()},
        "elo_settings": {
            "initial_rating": INITIAL_RATING,
            "scale": RATING_SCALE,
            "k": K_FACTOR,
            "draw_nc_update": "none",
            "period": "calendar date; simultaneous updates",
        },
        "boosted_settings": HistGradientBoostingClassifier(
            **BOOSTED_SETTINGS
        ).get_params(),
        "logistic_fit": "train-only median with indicators, scaling, lbfgs/max_iter=1000",
        "selection_policy": "No tuning or automatic promotion. Primary log loss; "
        "also report accuracy and fold consistency. A lower "
        "accuracy is not an accuracy gain.",
        "symmetry_policy": "diagnostic only; no symmetrization or mirrored training",
        "reliability_bins": "fixed deciles; left closed, last bin includes 1",
        "tie_policy": "p >= 0.5 chooses UUID-ordered fighter A",
        "environment": {
            "python": platform.python_version(),
            "numpy": np.__version__,
            "scikit_learn": sklearn.__version__,
            "fit_thread_limit": 1,
        },
        **report,
    }
    # Detect accidental concurrent source edits before publishing the report.
    if hashes != {name + "_sha256": _sha256(path) for name, path in inputs.items()}:
        raise ValueError("An experiment input changed during evaluation.")
    output_directory.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=output_directory.parent, prefix=".upset-elo-") as tmp:
        staged = Path(tmp) / "results"
        _write_verified_json(staged / "predictions.jsonl", predictions, json_lines=True)
        manifest["predictions_sha256"] = _sha256(staged / "predictions.jsonl")
        _write_verified_json(staged / "manifest.json", manifest, json_lines=False)
        staged.rename(output_directory)
    return manifest
