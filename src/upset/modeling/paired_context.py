"""One fixed tree comparison: retain differences and add each fighter's values.

This is development research on the existing four examined windows. It never
scores dates after August 19, 2023 or claims a live performance gain.
"""

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
from upset.data.matchups import INPUT_FIELDS, build_matchup_rows
from upset.data.prefight import build_prefight_snapshots
from upset.data.prefight_defense import build_defensive_history
from upset.data.prefight_features import build_prefight_features
from upset.data.prefight_ratings import read_rating_history
from upset.data.prefight_recent import RATE_SPECS, read_recent_history
from upset.modeling.baseline import read_matchups
from upset.modeling.defense_ablation import (
    DEFENSE_FIELDS,
    _paired_summary,
    join_defense,
    read_defensive_history,
)
from upset.modeling.elo_comparison import (
    DEFENSE_FEATURES,
    _diagnostics,
    _scores,
    join_ratings,
)
from upset.modeling.evaluation import (
    DEVELOPMENT_FOLDS,
    DEVELOPMENT_LAST_DATE,
    PREDICTION_CUTOFF,
    _sha256,
    _write_verified_json,
)
from upset.modeling.recent_form import EXPOSURES, join_recent
from upset.modeling.recent_form import NEW_VARIANTS as RECENT_NEW_VARIANTS
from upset.modeling.recent_form import VARIANTS as REFERENCE_VARIANTS
from upset.modeling.symmetric import (
    SYMMETRIC_BOOSTED_SETTINGS,
    fit_symmetric,
    swap_features,
    symmetric_probabilities,
)

EXPERIMENT = "paired_context_v1"
CANDIDATE = "paired_boosted_recent_elo"
COMPARATOR = "symmetric_boosted_recent_elo"
LOGISTIC_REFERENCE = "symmetric_recent_elo"
# The accepted Mac recent_form_v1 report, supplied before designing this study.
EXPECTED_REFERENCE_SHA256 = (
    "9c5f6228ffb3028d010bc70a644e34be47591626443285fc50e5345107f49787"
)
DIFFERENCE_COLUMNS = REFERENCE_VARIANTS[COMPARATOR]
FIGHTER_FIELDS = (
    INPUT_FIELDS
    + DEFENSE_FIELDS
    + ("elo_rating",)
    + tuple(f"recent_{name}" for name in RATE_SPECS)
    + tuple(f"recent_log_{field}" for field in EXPOSURES)
)
PAIRED_COLUMNS = tuple(
    f"{field}_{side}" for field in FIGHTER_FIELDS for side in ("a", "b")
)
COLUMNS = DIFFERENCE_COLUMNS + PAIRED_COLUMNS
VARIANTS = {**REFERENCE_VARIANTS, CANDIDATE: COLUMNS}
SWAP_SIGNS = np.asarray(
    [1 if c.endswith("_sum") else -1 for c in DIFFERENCE_COLUMNS]
    + [1] * len(PAIRED_COLUMNS)
)
SWAP_INDICES = np.asarray(
    list(range(len(DIFFERENCE_COLUMNS)))
    + [len(DIFFERENCE_COLUMNS) + (i ^ 1) for i in range(len(PAIRED_COLUMNS))]
)


def build_paired_records(rows, features, defense, ratings, recent):
    """Join whitelisted pre-fight values, preserving a known side if one is missing.

    Reconstruct every old difference/sum from these individual values. This
    catches a join or feature-definition mismatch before either model is fit.
    IDs and targets select rows and labels; they never enter the feature dict.
    """
    rating_pairs = join_ratings(rows, ratings)
    defensive = join_defense(rows, defense)
    recent_pairs = join_recent(rows, recent, rating_pairs, defense)
    expected = {
        (r.source_bout_id, i) for r in rows for i in (r.fighter_a_id, r.fighter_b_id)
    }
    if set(features) != expected:
        raise ValueError("Individual feature keys differ from matchup participants.")
    records = {}
    for row in rows:
        bout = row.source_bout_id
        ra, rb = rating_pairs[bout]
        record = {
            **row.feature_differences,
            **defensive[bout],
            "elo_rating_diff": ra.rating - rb.rating,
            **recent_pairs[bout],
        }
        for side, fighter_id in (("a", row.fighter_a_id), ("b", row.fighter_b_id)):
            key = bout, fighter_id
            own, incoming, rating, form = (
                features[key],
                defense[key],
                ratings[key],
                recent[key],
            )
            if (
                own.source_bout_id != bout
                or own.upset_fighter_id != fighter_id
                or own.event_date != row.event_date
                or own.prior_fights != rating.prior_fights
                or own.prior_fight_seconds != incoming.prior_fight_seconds
            ):
                raise ValueError(
                    f"Individual feature identity/date/exposure differs: {bout}"
                )
            values = {
                **{f: getattr(own, f) for f in INPUT_FIELDS},
                **{f: getattr(incoming, f) for f in DEFENSE_FIELDS},
                "elo_rating": rating.rating,
                **{f"recent_{f}": form.features[f] for f in RATE_SPECS},
                **{
                    f"recent_log_{f}": log1p(form.weighted_totals[f]) for f in EXPOSURES
                },
            }
            record.update(
                {f"{field}_{side}": values[field] for field in FIGHTER_FIELDS}
            )
        for column in DIFFERENCE_COLUMNS:
            field, operation = column.rsplit("_", 1)
            a, b = record[field + "_a"], record[field + "_b"]
            reconstructed = (
                None
                if a is None or b is None
                else a + b
                if operation == "sum"
                else a - b
            )
            old = record[column]
            matches = (
                old is None
                if reconstructed is None
                else old is not None
                and np.isclose(old, reconstructed, rtol=0, atol=1e-12)
            )
            if not matches:
                raise ValueError(f"Individual values do not reproduce {column}: {bout}")
        if set(record) != set(COLUMNS):
            raise ValueError("Paired feature schema differs from the fixed whitelist.")
        if any(v is not None and not isfinite(v) for v in record.values()):
            raise ValueError(f"Nonfinite individual feature: {bout}")
        records[bout] = record
    return records


def feature_matrix(rows, records, columns=COLUMNS):
    return np.asarray(
        [
            [
                np.nan
                if records[r.source_bout_id][c] is None
                else records[r.source_bout_id][c]
                for c in columns
            ]
            for r in rows
        ],
        dtype=float,
    )


def _references(rows, records, saved, *, candidate=CANDIDATE):
    expected = {
        r.source_bout_id: (r, fold)
        for fold in DEVELOPMENT_FOLDS
        for r in rows
        if fold.validate_from <= r.event_date <= fold.validate_through
    }
    if len({r["source_bout_id"] for r in saved}) != len(saved) or set(expected) != {
        r["source_bout_id"] for r in saved
    }:
        raise ValueError("Recent reference cohort differs.")
    predictions = []
    for old in saved:
        row, fold = expected[old["source_bout_id"]]
        record = records[row.source_bout_id]
        a, b = record["prior_fights_a"], record["prior_fights_b"]
        required = {
            "event_date": row.event_date,
            "fighter_a_id": row.fighter_a_id,
            "fighter_b_id": row.fighter_b_id,
            "target_a_win": row.target_a_win,
            "exclusion_reason": row.training_exclusion_reason,
            "fold": fold.name,
            "prediction_cutoff": PREDICTION_CUTOFF,
            "diagnostic_groups": {
                "history": (
                    "neither_has_history",
                    "one_has_history",
                    "both_have_history",
                )[int(a > 0) + int(b > 0)],
                "experience": "at_least_one_under_3_bouts"
                if min(a, b) < 3
                else "both_at_least_3_bouts",
                "missingness": "any_missing_defense_input"
                if any(record[c] is None for c in DEFENSE_FEATURES)
                else "complete_defense_inputs",
            },
        }
        if any(old.get(k) != value for k, value in required.items()):
            raise ValueError(
                f"Recent reference identity/target/groups differ: {row.source_bout_id}"
            )

        def valid(p, excluded=row.target_a_win is None):
            return (
                p is None
                if excluded
                else type(p) in (int, float) and isfinite(p) and 0 <= p <= 1
            )

        for field in ("probabilities_a_win", "swapped_probabilities_b_win"):
            probabilities = old.get(field, {})
            if set(probabilities) != set(REFERENCE_VARIANTS) or not all(
                valid(p) for p in probabilities.values()
            ):
                raise ValueError("Invalid recent reference probabilities.")
        raw = old.get("raw_directional_probabilities", {})
        if set(raw) != set(RECENT_NEW_VARIANTS):
            raise ValueError("Invalid recent reference directional probabilities.")
        for p in raw.values():
            valid_raw = (
                p is None
                if row.target_a_win is None
                else isinstance(p, dict)
                and set(p) == {"forward_a_win", "reverse_b_win"}
                and all(valid(v) for v in p.values())
            )
            if not valid_raw:
                raise ValueError("Invalid recent reference directional probabilities.")
        copy = deepcopy(old)
        for field in (
            "probabilities_a_win",
            "swapped_probabilities_b_win",
            "raw_directional_probabilities",
        ):
            copy[field][candidate] = None
        predictions.append(copy)
    return predictions


def compare_paired_context(rows, features, defense, ratings, recent, saved):
    records = build_paired_records(rows, features, defense, ratings, recent)
    predictions = _references(rows, records, saved)
    by_bout = {r["source_bout_id"]: r for r in predictions}
    ordered = sorted(rows, key=lambda r: (r.event_date, r.source_bout_id))
    signs = SWAP_SIGNS[: len(DIFFERENCE_COLUMNS)]
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
                raise ValueError(f"Empty training/validation fold: {fold.name}")
            labels = [r.target_a_win for r in train]
            # Refit only the directly matched old tree. Reject environment or
            # feature drift instead of calling a changed reference the baseline.
            reference_model = fit_symmetric(
                feature_matrix(train, records, DIFFERENCE_COLUMNS),
                labels,
                signs,
                boosted=True,
            )
            old_matrix = feature_matrix(selected, records, DIFFERENCE_COLUMNS)
            replayed = symmetric_probabilities(reference_model, old_matrix, signs)
            expected = (
                [
                    by_bout[r.source_bout_id]["probabilities_a_win"][COMPARATOR]
                    for r in selected
                ],
                [
                    by_bout[r.source_bout_id]["raw_directional_probabilities"][
                        COMPARATOR
                    ]["forward_a_win"]
                    for r in selected
                ],
                [
                    by_bout[r.source_bout_id]["raw_directional_probabilities"][
                        COMPARATOR
                    ]["reverse_b_win"]
                    for r in selected
                ],
            )
            error = max(
                float(np.max(np.abs(a - b)))
                for a, b in zip(replayed, expected, strict=True)
            )
            reverse = symmetric_probabilities(
                reference_model, swap_features(old_matrix, signs), signs
            )[0]
            error = max(
                error,
                float(
                    np.max(
                        np.abs(
                            reverse
                            - [
                                by_bout[r.source_bout_id][
                                    "swapped_probabilities_b_win"
                                ][COMPARATOR]
                                for r in selected
                            ]
                        )
                    )
                ),
            )
            if error > 1e-12:
                raise ValueError(
                    f"Saved matched tree refit differs: {fold.name} ({error:.3g})"
                )
            model = fit_symmetric(
                feature_matrix(train, records),
                labels,
                SWAP_SIGNS,
                boosted=True,
                swap_indices=SWAP_INDICES,
            )
            matrix = feature_matrix(selected, records)
            forward, raw_forward, raw_backward = symmetric_probabilities(
                model,
                matrix,
                SWAP_SIGNS,
                swap_indices=SWAP_INDICES,
            )
            backward = symmetric_probabilities(
                model,
                swap_features(matrix, SWAP_SIGNS, swap_indices=SWAP_INDICES),
                SWAP_SIGNS,
                swap_indices=SWAP_INDICES,
            )[0]
            if not np.allclose(forward + backward, 1, rtol=0, atol=1e-12):
                raise ValueError(f"Paired context symmetry failed: {fold.name}")
            for i, row in enumerate(selected):
                p = by_bout[row.source_bout_id]
                p["probabilities_a_win"][CANDIDATE] = float(forward[i])
                p["swapped_probabilities_b_win"][CANDIDATE] = float(backward[i])
                p["raw_directional_probabilities"][CANDIDATE] = {
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
                    "matched_tree_refit_maximum_absolute_error": error,
                    "observed_training_columns": [
                        c
                        for c, observed in zip(
                            COLUMNS, model.observed_columns, strict=True
                        )
                        if observed
                    ],
                    "scores": _scores(
                        [r for r in predictions if r["fold"] == fold.name], VARIANTS
                    ),
                }
            )
    paired = {}
    for reference in (COMPARATOR, LOGISTIC_REFERENCE):
        result = _paired_summary(
            [
                {
                    "event_date": r["event_date"],
                    "target_a_win": r["target_a_win"],
                    "baseline_probability_a_win": r["probabilities_a_win"][reference],
                    "defense_probability_a_win": r["probabilities_a_win"][CANDIDATE],
                }
                for r in predictions
            ]
        )
        paired[f"{CANDIDATE}_minus_{reference}"] = {
            "delta": result["delta_defense_minus_baseline"],
            "date_cluster_bootstrap_95_percent": result[
                "date_cluster_bootstrap_95_percent"
            ],
        }
    diagnostics = _diagnostics(predictions, VARIANTS)
    decisive = [r for r in predictions if r["target_a_win"] is not None]
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
    return predictions, {
        "folds": folds,
        "pooled": _scores(predictions, VARIANTS),
        "validation_bouts": len(predictions),
        "decisive_bouts": len(decisive),
        "draw_nc_exclusions": len(predictions) - len(decisive),
        "paired_comparisons": paired,
        **diagnostics,
        "ten_bin_ece": {
            name: sum(
                b["count"] * abs(b["mean_probability"] - b["observed_a_win_fraction"])
                for b in bins
                if b["count"]
            )
            / len(decisive)
            for name, bins in diagnostics["reliability_deciles"].items()
        },
    }


def export_paired_context(
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
    *,
    expected_reference_sha256: str = EXPECTED_REFERENCE_SHA256,
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
    if (
        any(
            output_directory.resolve() == p.resolve()
            or output_directory.resolve() in p.resolve().parents
            for p in inputs.values()
        )
        or reference_directory.resolve() in output_directory.resolve().parents
    ):
        raise ValueError("Output must not contain or replace an input or reference.")
    hashes = {name + "_sha256": _sha256(path) for name, path in inputs.items()}
    if hashes["reference_manifest_sha256"] != expected_reference_sha256:
        raise ValueError("Reference manifest hash differs from the accepted Mac study.")
    previous = json.loads(inputs["reference_manifest"].read_text(encoding="utf-8"))
    if (
        previous.get("experiment") != "recent_form_v1"
        or previous.get("development_last_date") != DEVELOPMENT_LAST_DATE
        or previous.get("variants")
        != {n: list(c) for n, c in REFERENCE_VARIANTS.items()}
        or previous.get("boosted_settings") != SYMMETRIC_BOOSTED_SETTINGS
    ):
        raise ValueError("Reference study schema/settings differ.")
    for name in inputs:
        if (
            not name.startswith("reference_")
            and previous.get(name + "_sha256") != hashes[name + "_sha256"]
        ):
            raise ValueError(f"Reference source hash differs: {name}")
    if previous.get("predictions_sha256") != hashes["reference_predictions_sha256"]:
        raise ValueError("Reference prediction hash differs.")
    saved = [
        json.loads(line)
        for line in inputs["reference_predictions"]
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    rows = read_matchups(matchup_path)
    defense, ratings, recent = (
        read_defensive_history(defensive_path),
        read_rating_history(ratings_path),
        read_recent_history(recent_path),
    )
    fights, stats = read_recent_sources(fights_path, stats_path)
    # Rebuild the individual cumulative rates from the same dated sources that
    # produced the saved differences. Current career profiles are never inputs.
    features = list(
        build_prefight_features(list(build_prefight_snapshots(fights, stats)))
    )
    rebuilt_matchups = build_matchup_rows(fights, features)
    rebuilt_defense = {
        (r.source_bout_id, r.upset_fighter_id): r
        for r in build_defensive_history(fights, stats)
    }
    if rebuilt_defense != defense or {
        r.source_bout_id: r for r in rebuilt_matchups
    } != {r.source_bout_id: r for r in rows}:
        raise ValueError("Reference features differ from identified source statistics.")
    rating_audit = audit_prefight_ratings(fights, ratings)
    recent_audit = audit_prefight_recent(fights, stats, recent)
    classes = {
        f.fight.source_bout_id: f.fight.weight_class or "unknown" for f in fights
    }
    if any(r.get("weight_class") != classes.get(r["source_bout_id"]) for r in saved):
        raise ValueError("Reference weight class differs from source.")
    predictions, report = compare_paired_context(
        rows,
        {(r.source_bout_id, r.upset_fighter_id): r for r in features},
        defense,
        ratings,
        recent,
        saved,
    )
    manifest = {
        "experiment": EXPERIMENT,
        "status": "exploratory; examined development folds; no promotion",
        "code_commit": code_commit,
        **hashes,
        "reference_code_commit": previous["code_commit"],
        "reference_probabilities": "all 12 saved forward/reverse series and six raw series preserved exactly",
        "source_feature_replay": "cumulative individual rates rebuilt; saved matchups/defense match; every difference/sum reconstructed from paired values",
        "individual_feature_rows_checked": len(features),
        "rating_audit": rating_audit,
        "recent_audit": recent_audit,
        "total_source_bouts": len(rows),
        "development_last_date": DEVELOPMENT_LAST_DATE,
        "source_bouts_after_development_not_scored": sum(
            r.event_date > DEVELOPMENT_LAST_DATE for r in rows
        ),
        "prediction_cutoff": PREDICTION_CUTOFF,
        "candidate": CANDIDATE,
        "primary_comparator": COMPARATOR,
        "secondary_reference": LOGISTIC_REFERENCE,
        "variants": {name: list(columns) for name, columns in VARIANTS.items()},
        "fighter_fields": list(FIGHTER_FIELDS),
        "new_paired_columns": list(PAIRED_COLUMNS),
        "boosted_settings": SYMMETRIC_BOOSTED_SETTINGS,
        "symmetry_settings": {
            "swap_signs": SWAP_SIGNS.tolist(),
            "swap_indices": SWAP_INDICES.tolist(),
            "training": "mirror after date split; weight 0.5 per orientation",
            "inference": "0.5 + 0.5 * (forward - reverse)",
        },
        "selection_policy": "one fixed added-context tree; same settings, cohorts and source history; primary paired log loss; report accuracy/calibration; no tuning, constraints or promotion",
        "tie_policy": "p >= 0.5 picks canonical UUID-ordered A; exact ties reported",
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
            for label in sorted({r["weight_class"] for r in predictions})
        },
        **report,
    }
    if hashes != {name + "_sha256": _sha256(path) for name, path in inputs.items()}:
        raise ValueError("An experiment input changed during evaluation.")
    output_directory.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(
        dir=output_directory.parent, prefix=".upset-paired-context-"
    ) as tmp:
        staged = Path(tmp) / "results"
        _write_verified_json(staged / "predictions.jsonl", predictions, json_lines=True)
        manifest["predictions_sha256"] = _sha256(staged / "predictions.jsonl")
        _write_verified_json(staged / "manifest.json", manifest, json_lines=False)
        staged.rename(output_directory)
    return manifest
