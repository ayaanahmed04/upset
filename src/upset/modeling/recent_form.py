"""Fixed symmetry and recent-performance comparison against preserved Elo v1."""

import json
import platform
from copy import deepcopy
from dataclasses import asdict
from math import isfinite, log1p
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np
import sklearn
from threadpoolctl import threadpool_limits

from upset.data.audit_prefight_ratings import audit_prefight_ratings
from upset.data.audit_prefight_recent import audit_prefight_recent, read_recent_sources
from upset.data.matchups import build_matchup_rows
from upset.data.prefight import build_prefight_snapshots
from upset.data.prefight_defense import build_defensive_history
from upset.data.prefight_features import build_prefight_features
from upset.data.prefight_ratings import read_rating_history
from upset.data.prefight_recent import HALF_LIFE_DAYS, RATE_SPECS, read_recent_history
from upset.modeling.baseline import read_matchups
from upset.modeling.defense_ablation import (
    _paired_summary,
    join_defense,
    read_defensive_history,
)
from upset.modeling.elo_comparison import (
    DEFENSE_FEATURES,
    ELO_COLUMN,
    _audit_matchup_sources,
    _diagnostics,
    _scores,
    join_ratings,
)
from upset.modeling.elo_comparison import (
    VARIANTS as ORIGINAL_VARIANTS,
)
from upset.modeling.evaluation import (
    DEVELOPMENT_FOLDS,
    DEVELOPMENT_LAST_DATE,
    PREDICTION_CUTOFF,
    _sha256,
    _write_verified_json,
)
from upset.modeling.symmetric import (
    SYMMETRIC_BOOSTED_SETTINGS,
    fit_symmetric,
    swap_features,
    symmetric_probabilities,
)

EXPOSURES = ("seconds", "appearances", "control_seconds")
RECENT_COLUMNS = tuple(f"recent_{name}_diff" for name in RATE_SPECS) + tuple(
    f"recent_log_{field}_{operation}"
    for field in EXPOSURES
    for operation in ("diff", "sum")
)
NEW_VARIANTS = {
    f"symmetric_{prefix}{suffix}": features
    for prefix in ("", "boosted_")
    for suffix, features in (
        ("defense", DEFENSE_FEATURES),
        ("defense_elo", DEFENSE_FEATURES + (ELO_COLUMN,)),
        ("recent_elo", DEFENSE_FEATURES + (ELO_COLUMN,) + RECENT_COLUMNS),
    )
}
VARIANTS = {**ORIGINAL_VARIANTS, **NEW_VARIANTS}
PAIRS = tuple(
    dict.fromkeys(
        [
            *((name, "all_defense") for name in NEW_VARIANTS),
            ("symmetric_defense_elo", "defense_plus_elo"),
            ("symmetric_boosted_defense", "boosted_defense"),
            ("symmetric_boosted_defense_elo", "boosted_defense_plus_elo"),
            ("symmetric_defense_elo", "symmetric_defense"),
            ("symmetric_boosted_defense_elo", "symmetric_boosted_defense"),
            ("symmetric_recent_elo", "symmetric_defense_elo"),
            ("symmetric_boosted_recent_elo", "symmetric_boosted_defense_elo"),
        ]
    )
)


def join_recent(rows, recent, ratings, defense):
    expected = {
        (r.source_bout_id, i) for r in rows for i in (r.fighter_a_id, r.fighter_b_id)
    }
    if set(recent) != expected:
        raise ValueError("Recent join keys differ from matchup participants.")
    joined = {}
    for row in rows:
        a, b = [
            recent[row.source_bout_id, i] for i in (row.fighter_a_id, row.fighter_b_id)
        ]
        for side, history in enumerate((a, b)):
            fighter_id = (row.fighter_a_id, row.fighter_b_id)[side]
            if (
                history.event_date != row.event_date
                or history.upset_fighter_id != fighter_id
                or history.source_bout_id != row.source_bout_id
                or history.prior_fights
                != ratings[row.source_bout_id][side].prior_fights
                or history.prior_fights
                != defense[row.source_bout_id, fighter_id].prior_fights
            ):
                raise ValueError(
                    f"Recent identity/date/prior counts differ: {row.source_bout_id}"
                )
        if (
            a.prior_fights - b.prior_fights
            != row.feature_differences["prior_fights_diff"]
        ):
            raise ValueError(f"Matchup prior counts differ: {row.source_bout_id}")
        record = {
            f"recent_{name}_diff": a.features[name] - b.features[name]
            if a.features[name] is not None and b.features[name] is not None
            else None
            for name in RATE_SPECS
        }
        for field in EXPOSURES:
            left, right = (
                log1p(a.weighted_totals[field]),
                log1p(b.weighted_totals[field]),
            )
            record[f"recent_log_{field}_diff"] = left - right
            record[f"recent_log_{field}_sum"] = left + right
        joined[row.source_bout_id] = record
    return joined


def feature_matrix(rows, defensive, ratings, recent, columns):
    values = []
    for row in rows:
        a, b = ratings[row.source_bout_id]
        record = {
            **row.feature_differences,
            **defensive[row.source_bout_id],
            ELO_COLUMN: a.rating - b.rating,
            **recent[row.source_bout_id],
        }
        values.append([np.nan if record[c] is None else record[c] for c in columns])
    return np.asarray(values, dtype=float)


def _references(rows, saved):
    expected = {
        r.source_bout_id: (r, fold)
        for fold in DEVELOPMENT_FOLDS
        for r in rows
        if fold.validate_from <= r.event_date <= fold.validate_through
    }
    if len({r["source_bout_id"] for r in saved}) != len(saved) or set(expected) != {
        r["source_bout_id"] for r in saved
    }:
        raise ValueError("Saved Elo reference cohort differs.")
    result = []
    for old in saved:
        row, fold = expected[old["source_bout_id"]]
        required = {
            "event_date": row.event_date,
            "fighter_a_id": row.fighter_a_id,
            "fighter_b_id": row.fighter_b_id,
            "target_a_win": row.target_a_win,
            "exclusion_reason": row.training_exclusion_reason,
            "fold": fold.name,
            "prediction_cutoff": PREDICTION_CUTOFF,
        }
        if any(old.get(k) != v for k, v in required.items()):
            raise ValueError(
                f"Saved Elo reference identity/date/target differs: {row.source_bout_id}"
            )
        for field in ("probabilities_a_win", "swapped_probabilities_b_win"):
            probabilities = old.get(field, {})
            if set(probabilities) != set(ORIGINAL_VARIANTS):
                raise ValueError("Saved Elo reference variants differ.")
            for p in probabilities.values():
                valid = (
                    p is None
                    if row.target_a_win is None
                    else (type(p) in (int, float) and isfinite(p) and 0 <= p <= 1)
                )
                if not valid:
                    raise ValueError("Invalid saved Elo reference probability.")
        record = deepcopy(old)
        for field in ("probabilities_a_win", "swapped_probabilities_b_win"):
            record[field].update(dict.fromkeys(NEW_VARIANTS))
        record["raw_directional_probabilities"] = dict.fromkeys(NEW_VARIANTS)
        result.append(record)
    return result


def compare_recent_form(rows, defense, ratings, recent, saved):
    rating_pairs = join_ratings(rows, ratings)
    defensive = join_defense(rows, defense)
    recent_pairs = join_recent(rows, recent, rating_pairs, defense)
    predictions = _references(rows, saved)
    by_bout = {r["source_bout_id"]: r for r in predictions}
    ordered = sorted(rows, key=lambda r: (r.event_date, r.source_bout_id))
    folds = []
    with threadpool_limits(limits=1):
        for fold in DEVELOPMENT_FOLDS:
            train = [
                r
                for r in ordered
                if r.event_date <= fold.train_through and r.target_a_win is not None
            ]
            validation = [
                r
                for r in ordered
                if fold.validate_from <= r.event_date <= fold.validate_through
            ]
            selected = [r for r in validation if r.target_a_win is not None]
            if not train or not selected:
                raise ValueError(
                    f"Empty training/decisive validation fold: {fold.name}"
                )
            for name, columns in NEW_VARIANTS.items():
                signs = np.asarray([1 if c.endswith("_sum") else -1 for c in columns])
                train_matrix = feature_matrix(
                    train, defensive, rating_pairs, recent_pairs, columns
                )
                model = fit_symmetric(
                    train_matrix,
                    [r.target_a_win for r in train],
                    signs,
                    boosted="boosted" in name,
                )
                matrix = feature_matrix(
                    selected, defensive, rating_pairs, recent_pairs, columns
                )
                forward, raw_forward, raw_backward = symmetric_probabilities(
                    model, matrix, signs
                )
                # Invoke the public procedure again on swapped input; don't just
                # write 1-p and call that an independent symmetry check.
                backward, _, _ = symmetric_probabilities(
                    model, swap_features(matrix, signs), signs
                )
                if not np.allclose(forward + backward, 1, rtol=0, atol=1e-12):
                    raise ValueError(f"Symmetry failed: {fold.name}/{name}")
                for i, row in enumerate(selected):
                    record = by_bout[row.source_bout_id]
                    record["probabilities_a_win"][name] = float(forward[i])
                    record["swapped_probabilities_b_win"][name] = float(backward[i])
                    record["raw_directional_probabilities"][name] = {
                        "forward_a_win": float(raw_forward[i]),
                        "reverse_b_win": float(raw_backward[i]),
                    }
            folds.append(
                {
                    **asdict(fold),
                    "train_decisive": len(train),
                    "mirrored_train_rows": 2 * len(train),
                    "total_training_weight": len(train),
                    "validation_bouts": len(validation),
                    "draw_nc_exclusions": len(validation) - len(selected),
                    "scores": _scores(
                        [r for r in predictions if r["fold"] == fold.name], VARIANTS
                    ),
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
    diagnostics = _diagnostics(predictions, VARIANTS)
    decisive = [r for r in predictions if r["target_a_win"] is not None]
    raw_symmetry = {}
    for name in VARIANTS:
        p = np.asarray([r["probabilities_a_win"][name] for r in decisive])
        q = np.asarray([r["swapped_probabilities_b_win"][name] for r in decisive])
        diagnostics["symmetry"][name].update(
            {
                "conflicting_winner_picks": int(
                    np.sum(((p > 0.5) & (q > 0.5)) | ((p < 0.5) & (q < 0.5)))
                ),
                "exact_forward_ties": int(np.sum(p == 0.5)),
            }
        )
        if name in NEW_VARIANTS:
            errors = [
                abs(
                    r["raw_directional_probabilities"][name]["forward_a_win"]
                    + r["raw_directional_probabilities"][name]["reverse_b_win"]
                    - 1
                )
                for r in decisive
            ]
            raw_symmetry[name] = {
                "mean_absolute_error": float(np.mean(errors)),
                "maximum_absolute_error": float(np.max(errors)),
            }
    return predictions, {
        "folds": folds,
        "pooled": _scores(predictions, VARIANTS),
        "validation_bouts": len(predictions),
        "decisive_bouts": len(decisive),
        "draw_nc_exclusions": len(predictions) - len(decisive),
        "paired_comparisons": paired,
        "raw_symmetry": raw_symmetry,
        **diagnostics,
    }


def export_recent_form(
    matchup_path: Path,
    defensive_path: Path,
    ratings_path: Path,
    recent_path: Path,
    fights_path: Path,
    stats_path: Path,
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
        "recent_history": recent_path,
        "identified_fights": fights_path,
        "identified_stats": stats_path,
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
    if previous.get("experiment") != "elo_comparison_v1":
        raise ValueError("Expected preserved elo_comparison_v1 reference.")
    for name in (
        "matchups",
        "defensive_history",
        "rating_history",
        "identified_fights",
        "registry",
    ):
        if previous.get(name + "_sha256") != hashes[name + "_sha256"]:
            raise ValueError(f"Reference input hash differs: {name}")
    if previous.get("predictions_sha256") != hashes["reference_predictions_sha256"]:
        raise ValueError("Reference prediction hash differs.")
    saved = [
        json.loads(line)
        for line in inputs["reference_predictions"]
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    rows, defense = read_matchups(matchup_path), read_defensive_history(defensive_path)
    ratings, recent = (
        read_rating_history(ratings_path),
        read_recent_history(recent_path),
    )
    fights, stats = read_recent_sources(fights_path, stats_path)
    # Link the newly supplied statistics to the preserved reference features,
    # not just to the newly exported recent rates.
    replayed_defense = {
        (r.source_bout_id, r.upset_fighter_id): r
        for r in build_defensive_history(fights, stats)
    }
    replayed_matchups = build_matchup_rows(
        fights,
        list(build_prefight_features(list(build_prefight_snapshots(fights, stats)))),
    )
    if replayed_defense != defense or {
        r.source_bout_id: r for r in replayed_matchups
    } != {r.source_bout_id: r for r in rows}:
        raise ValueError("Reference features differ from identified source statistics.")
    rating_audit = audit_prefight_ratings(fights, ratings)
    recent_audit = audit_prefight_recent(fights, stats, recent)
    _audit_matchup_sources(rows, fights)
    predictions, report = compare_recent_form(rows, defense, ratings, recent, saved)
    classes = {
        f.fight.source_bout_id: f.fight.weight_class or "unknown" for f in fights
    }
    for row in predictions:
        if (
            row.get("weight_class", classes[row["source_bout_id"]])
            != classes[row["source_bout_id"]]
        ):
            raise ValueError("Reference weight class differs from source.")
        row["weight_class"] = classes[row["source_bout_id"]]
    manifest = {
        "experiment": "recent_form_v1",
        "status": "exploratory; examined folds; no promotion",
        "code_commit": code_commit,
        **hashes,
        "reference_code_commit": previous.get("code_commit"),
        "reference_probabilities": "all six saved forward/reverse values retained exactly; hash checked; no refit",
        "rating_audit": rating_audit,
        "recent_audit": recent_audit,
        "reference_feature_source_replay": "matchups and defense matched source rebuild",
        "total_source_bouts": len(rows),
        "source_bouts_after_development": sum(
            r.event_date > DEVELOPMENT_LAST_DATE for r in rows
        ),
        "development_last_date": DEVELOPMENT_LAST_DATE,
        "prediction_cutoff": PREDICTION_CUTOFF,
        "variants": {name: list(columns) for name, columns in VARIANTS.items()},
        "recent_settings": {
            "half_life_days": HALF_LIFE_DAYS,
            "rate_specs": {k: list(v) for k, v in RATE_SPECS.items()},
            "population_prior": "all fighter-bout totals on strictly earlier dates",
        },
        "symmetry_settings": {
            "training": "mirrored rows, each weight 0.5; split before mirroring",
            "inference": "0.5 + 0.5 * (forward - reverse)",
            "swap_even_columns": [c for c in RECENT_COLUMNS if c.endswith("_sum")],
        },
        "boosted_settings": SYMMETRIC_BOOSTED_SETTINGS,
        "logistic_settings": {
            "C": 1.0,
            "max_iter": 1000,
            "solver": "lbfgs",
            "preprocessing": "train-only median/indicators/scaling",
        },
        "selection_policy": "fixed six candidates; primary log loss, explicit accuracy/folds; no tuning or promotion",
        "tie_policy": "metrics retain p >= 0.5 choosing canonical UUID-ordered A; exact ties reported separately",
        "environment": {
            "python": platform.python_version(),
            "numpy": np.__version__,
            "scikit_learn": sklearn.__version__,
            "fit_thread_limit": 1,
        },
        "weight_class_scores": {
            label: _scores(
                [r for r in predictions if r["weight_class"] == label], VARIANTS
            )
            for label in sorted(set(classes.values()))
            if any(r["weight_class"] == label for r in predictions)
        },
        **report,
    }
    if hashes != {name + "_sha256": _sha256(path) for name, path in inputs.items()}:
        raise ValueError("An experiment input changed during evaluation.")
    output_directory.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(
        dir=output_directory.parent, prefix=".upset-recent-model-"
    ) as tmp:
        staged = Path(tmp) / "results"
        _write_verified_json(staged / "predictions.jsonl", predictions, json_lines=True)
        manifest["predictions_sha256"] = _sha256(staged / "predictions.jsonl")
        _write_verified_json(staged / "manifest.json", manifest, json_lines=False)
        staged.rename(output_directory)
    return manifest
