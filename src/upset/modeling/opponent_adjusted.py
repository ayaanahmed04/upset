"""One frozen logistic study of past performance against prior opponent defense."""

import json
import platform
from dataclasses import asdict
from math import isfinite, log1p
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np
import sklearn
from threadpoolctl import threadpool_limits

from upset.data.audit_prefight_adjusted import audit_prefight_adjusted
from upset.data.audit_prefight_ratings import audit_prefight_ratings
from upset.data.audit_prefight_recent import audit_prefight_recent, read_recent_sources
from upset.data.matchups import build_matchup_rows
from upset.data.prefight import build_prefight_snapshots
from upset.data.prefight_adjusted import (
    SPECS,
    build_adjusted_history,
    read_adjusted_history,
)
from upset.data.prefight_defense import build_defensive_history
from upset.data.prefight_features import build_prefight_features
from upset.data.prefight_ratings import read_rating_history
from upset.data.prefight_recent import read_recent_history
from upset.modeling.baseline import read_matchups
from upset.modeling.defense_ablation import (
    _paired_summary,
    join_defense,
    read_defensive_history,
)
from upset.modeling.elo_comparison import (
    ELO_COLUMN,
    _diagnostics,
    _scores,
    join_ratings,
)
from upset.modeling.evaluation import (
    DEVELOPMENT_FOLDS,
    DEVELOPMENT_LAST_DATE,
    _sha256,
    _write_verified_json,
)
from upset.modeling.paired_context import (
    EXPECTED_REFERENCE_SHA256,
    _references,
)
from upset.modeling.recent_form import (
    VARIANTS as REFERENCE_VARIANTS,
)
from upset.modeling.recent_form import join_recent
from upset.modeling.symmetric import (
    fit_symmetric,
    swap_features,
    symmetric_probabilities,
)

EXPERIMENT = "opponent_adjusted_v1"
CANDIDATE = "symmetric_opponent_adjusted_recent_elo"
REFERENCE = "symmetric_recent_elo"
ADJUSTED_COLUMNS = tuple(f"adjusted_{name}_diff" for name in SPECS) + tuple(
    f"adjusted_log_{name}_seconds_{operation}"
    for name in SPECS
    for operation in ("diff", "sum")
)
COLUMNS = REFERENCE_VARIANTS[REFERENCE] + ADJUSTED_COLUMNS
VARIANTS = {**REFERENCE_VARIANTS, CANDIDATE: COLUMNS}
REFERENCE_SIGNS = np.asarray(
    [1 if c.endswith("_sum") else -1 for c in REFERENCE_VARIANTS[REFERENCE]]
)
SIGNS = np.asarray([1 if c.endswith("_sum") else -1 for c in COLUMNS])


def join_adjusted(rows, defense, ratings, recent, adjusted):
    expected = {
        (row.source_bout_id, fighter_id)
        for row in rows
        for fighter_id in (row.fighter_a_id, row.fighter_b_id)
    }
    if set(adjusted) != expected:
        raise ValueError("Adjusted history keys differ from matchup participants.")
    rating_pairs = join_ratings(rows, ratings)
    defensive = join_defense(rows, defense)
    recent_pairs = join_recent(rows, recent, rating_pairs, defense)
    records = {}
    for row in rows:
        bout = row.source_bout_id
        a, b = [adjusted[bout, i] for i in (row.fighter_a_id, row.fighter_b_id)]
        ra, rb = rating_pairs[bout]
        if any(
            r.source_bout_id != bout
            or r.event_date != row.event_date
            or r.upset_fighter_id != i
            or r.prior_fights != recent[bout, i].prior_fights
            for r, i in zip((a, b), (row.fighter_a_id, row.fighter_b_id), strict=True)
        ):
            raise ValueError(f"Adjusted identity/date/history differs: {bout}")
        record = {
            **row.feature_differences,
            **defensive[bout],
            ELO_COLUMN: ra.rating - rb.rating,
            **recent_pairs[bout],
            "prior_fights_a": a.prior_fights,
            "prior_fights_b": b.prior_fights,
        }
        for name in SPECS:
            record[f"adjusted_{name}_diff"] = a.features[name] - b.features[name]
            left, right = (
                log1p(a.weighted_seconds[name]),
                log1p(b.weighted_seconds[name]),
            )
            record[f"adjusted_log_{name}_seconds_diff"] = left - right
            record[f"adjusted_log_{name}_seconds_sum"] = left + right
        if any(not isfinite(record[c]) for c in ADJUSTED_COLUMNS):
            raise ValueError(f"Nonfinite adjusted feature: {bout}")
        records[bout] = record
    return records


def feature_matrix(rows, records, columns=COLUMNS):
    return np.asarray(
        [
            [
                np.nan
                if records[row.source_bout_id][name] is None
                else records[row.source_bout_id][name]
                for name in columns
            ]
            for row in rows
        ],
        dtype=float,
    )


def compare_opponent_adjusted(rows, defense, ratings, recent, adjusted, saved):
    records = join_adjusted(rows, defense, ratings, recent, adjusted)
    predictions = _references(rows, records, saved, candidate=CANDIDATE)
    by_bout = {row["source_bout_id"]: row for row in predictions}
    ordered = sorted(rows, key=lambda row: (row.event_date, row.source_bout_id))
    folds = []
    with threadpool_limits(limits=1):
        for fold in DEVELOPMENT_FOLDS:
            train = [
                row
                for row in ordered
                if row.event_date <= fold.train_through and row.target_a_win is not None
            ]
            validation = [
                row
                for row in ordered
                if fold.validate_from <= row.event_date <= fold.validate_through
            ]
            selected = [row for row in validation if row.target_a_win is not None]
            if not train or not selected:
                raise ValueError(f"Empty development fold: {fold.name}")
            labels = [row.target_a_win for row in train]
            # The older model is fitted only for an exact replay check; saved
            # reference probabilities stay untouched in the output.
            reference_model = fit_symmetric(
                feature_matrix(train, records, REFERENCE_VARIANTS[REFERENCE]),
                labels,
                REFERENCE_SIGNS,
            )
            old_matrix = feature_matrix(
                selected, records, REFERENCE_VARIANTS[REFERENCE]
            )
            final, raw_forward, raw_reverse = symmetric_probabilities(
                reference_model, old_matrix, REFERENCE_SIGNS
            )
            swapped = symmetric_probabilities(
                reference_model,
                swap_features(old_matrix, REFERENCE_SIGNS),
                REFERENCE_SIGNS,
            )[0]
            expected = (
                [
                    by_bout[r.source_bout_id]["probabilities_a_win"][REFERENCE]
                    for r in selected
                ],
                [
                    by_bout[r.source_bout_id]["raw_directional_probabilities"][
                        REFERENCE
                    ]["forward_a_win"]
                    for r in selected
                ],
                [
                    by_bout[r.source_bout_id]["raw_directional_probabilities"][
                        REFERENCE
                    ]["reverse_b_win"]
                    for r in selected
                ],
                [
                    by_bout[r.source_bout_id]["swapped_probabilities_b_win"][REFERENCE]
                    for r in selected
                ],
            )
            error = max(
                float(np.max(np.abs(actual - wanted)))
                for actual, wanted in zip(
                    (final, raw_forward, raw_reverse, swapped), expected, strict=True
                )
            )
            if error > 1e-12:
                raise ValueError(
                    f"Saved logistic reference refit differs: {fold.name} ({error:.3g})"
                )
            model = fit_symmetric(feature_matrix(train, records), labels, SIGNS)
            matrix = feature_matrix(selected, records)
            forecast, forward, reverse = symmetric_probabilities(model, matrix, SIGNS)
            swapped_new = symmetric_probabilities(
                model, swap_features(matrix, SIGNS), SIGNS
            )[0]
            if not np.allclose(forecast + swapped_new, 1, rtol=0, atol=1e-12):
                raise ValueError(f"Adjusted swap symmetry failed: {fold.name}")
            for i, row in enumerate(selected):
                out = by_bout[row.source_bout_id]
                out["probabilities_a_win"][CANDIDATE] = float(forecast[i])
                out["swapped_probabilities_b_win"][CANDIDATE] = float(swapped_new[i])
                out["raw_directional_probabilities"][CANDIDATE] = {
                    "forward_a_win": float(forward[i]),
                    "reverse_b_win": float(reverse[i]),
                }
            folds.append(
                {
                    **asdict(fold),
                    "train_decisive": len(train),
                    "mirrored_train_rows": 2 * len(train),
                    "total_training_weight": len(train),
                    "validation_bouts": len(validation),
                    "draw_nc_exclusions": len(validation) - len(selected),
                    "matched_logistic_refit_maximum_absolute_error": error,
                    "scores": _scores(
                        [r for r in predictions if r["fold"] == fold.name], VARIANTS
                    ),
                }
            )
    paired = _paired_summary(
        [
            {
                "event_date": r["event_date"],
                "target_a_win": r["target_a_win"],
                "baseline_probability_a_win": r["probabilities_a_win"][REFERENCE],
                "defense_probability_a_win": r["probabilities_a_win"][CANDIDATE],
            }
            for r in predictions
        ]
    )
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
        "paired_comparison": {
            f"{CANDIDATE}_minus_{REFERENCE}": {
                "delta": paired["delta_defense_minus_baseline"],
                "date_cluster_bootstrap_95_percent": paired[
                    "date_cluster_bootstrap_95_percent"
                ],
            }
        },
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


def export_opponent_adjusted(
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
    if len({path.resolve() for path in inputs.values()}) != len(inputs):
        raise ValueError("Experiment inputs must be distinct.")
    if output_directory.exists():
        raise ValueError(
            "Experiment output already exists; use a new --output directory."
        )
    if (
        any(
            output_directory.resolve() == path.resolve()
            or output_directory.resolve() in path.resolve().parents
            for path in inputs.values()
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
    ):
        raise ValueError("Reference study schema differs.")
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
    rebuilt_defense = {
        (row.source_bout_id, row.upset_fighter_id): row
        for row in build_defensive_history(fights, stats)
    }
    rebuilt_matchups = build_matchup_rows(
        fights,
        list(build_prefight_features(list(build_prefight_snapshots(fights, stats)))),
    )
    if rebuilt_defense != defense or {
        row.source_bout_id: row for row in rebuilt_matchups
    } != {row.source_bout_id: row for row in rows}:
        raise ValueError("Reference features differ from identified source statistics.")
    rating_audit = audit_prefight_ratings(fights, ratings)
    recent_audit = audit_prefight_recent(fights, stats, recent)
    adjusted = build_adjusted_history(fights, stats, recent)
    indexed = {(row.source_bout_id, row.upset_fighter_id): row for row in adjusted}
    adjusted_audit = audit_prefight_adjusted(fights, stats, recent, indexed)
    classes = {
        identified.fight.source_bout_id: identified.fight.weight_class or "unknown"
        for identified in fights
    }
    if any(
        row.get("weight_class") != classes.get(row["source_bout_id"]) for row in saved
    ):
        raise ValueError("Reference weight class differs from source.")
    predictions, report = compare_opponent_adjusted(
        rows, defense, ratings, recent, indexed, saved
    )
    manifest = {
        "experiment": EXPERIMENT,
        "status": "exploratory; examined development folds; no promotion",
        "code_commit": code_commit,
        **hashes,
        "reference_code_commit": previous["code_commit"],
        "reference_probabilities": "all 12 saved forward/reverse series and six raw series preserved exactly",
        "source_feature_replay": "saved matchups/defense match rebuilt identified sources; Elo/recent replay independently audited",
        "rating_audit": rating_audit,
        "recent_audit": recent_audit,
        "adjusted_audit": adjusted_audit,
        "total_source_bouts": len(rows),
        "adjusted_history_rows": len(adjusted),
        "development_last_date": DEVELOPMENT_LAST_DATE,
        "source_bouts_after_development_not_scored": sum(
            row.event_date > DEVELOPMENT_LAST_DATE for row in rows
        ),
        "candidate": CANDIDATE,
        "primary_comparator": REFERENCE,
        "variants": {name: list(columns) for name, columns in VARIANTS.items()},
        "new_columns": list(ADJUSTED_COLUMNS),
        "history_specification": {
            "opponent_rates": {name: field for name, (_, field, _) in SPECS.items()},
            "decay_half_life_days": 365,
            "prior_seconds": 900,
            "missing_opponent_rate": "exclude that bout's observation for the affected family",
            "no_eligible_history": "zero adjusted excess and zero exposure",
            "expectation": "opponent's pre-bout shrunk conceded rate times current bout duration",
        },
        "selection_policy": "one fixed added-feature symmetric logistic; matched paired log loss; report accuracy and calibration; no tuning or promotion",
        "symmetry_settings": {
            "swap_signs": SIGNS.tolist(),
            "training": "mirror after date split; weight 0.5 per orientation",
            "inference": "0.5 + 0.5 * (forward - reverse)",
        },
        "tie_policy": "p >= 0.5 picks canonical UUID-ordered A; exact ties reported",
        "environment": {
            "python": platform.python_version(),
            "numpy": np.__version__,
            "scikit_learn": sklearn.__version__,
            "fit_thread_limit": 1,
        },
        "weight_class_scores": {
            label: _scores(
                [row for row in predictions if row["weight_class"] == label], VARIANTS
            )
            for label in sorted({row["weight_class"] for row in predictions})
        },
        **report,
    }
    if hashes != {name + "_sha256": _sha256(path) for name, path in inputs.items()}:
        raise ValueError("An experiment input changed during evaluation.")
    output_directory.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(
        dir=output_directory.parent, prefix=".upset-opponent-adjusted-"
    ) as tmp:
        staged = Path(tmp) / "results"
        history_path = staged / "adjusted_history.jsonl"
        _write_verified_json(
            history_path, [row.as_record() for row in adjusted], json_lines=True
        )
        if read_adjusted_history(history_path) != indexed:
            raise ValueError("Adjusted history read-back differs.")
        manifest["adjusted_history_sha256"] = _sha256(history_path)
        _write_verified_json(staged / "predictions.jsonl", predictions, json_lines=True)
        manifest["predictions_sha256"] = _sha256(staged / "predictions.jsonl")
        _write_verified_json(staged / "manifest.json", manifest, json_lines=False)
        staged.rename(output_directory)
    return manifest
