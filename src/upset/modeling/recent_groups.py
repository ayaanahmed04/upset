"""Fixed exploratory ablation of existing recent-performance feature groups."""

import json
import platform
from dataclasses import asdict
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np
import sklearn
from threadpoolctl import threadpool_limits

from upset.data.audit_prefight_ratings import audit_prefight_ratings
from upset.data.audit_prefight_recent import audit_prefight_recent, read_recent_sources
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
from upset.modeling.examined_later import EXPECTED_REFERENCE_SHA256, _snapshot
from upset.modeling.paired_context import _references
from upset.modeling.recent_form import NEW_VARIANTS, join_recent
from upset.modeling.symmetric import (
    fit_symmetric,
    swap_features,
    symmetric_probabilities,
)

REFERENCE = "symmetric_recent_elo"
COMMON = DEFENSE_FEATURES + (ELO_COLUMN,) + tuple(
    f"recent_log_{field}_{operation}"
    for field in ("seconds", "appearances") for operation in ("diff", "sum")
)
GROUPS = {
    "strikes": tuple(f"recent_{field}_diff" for field in (
        "sig_landed_per_minute", "sig_absorbed_per_minute", "sig_accuracy",
        "sig_defense",
    )),
    "takedowns": tuple(f"recent_{field}_diff" for field in (
        "td_landed_per_15", "td_conceded_per_15", "td_accuracy", "td_defense",
    )),
    "knockdowns": ("recent_kd_per_15_diff", "recent_kd_conceded_per_15_diff"),
    "submissions": ("recent_sub_attempts_per_15_diff",),
    "control_margin": (
        "recent_control_margin_diff", "recent_log_control_seconds_diff",
        "recent_log_control_seconds_sum",
    ),
}
VARIANTS = {
    "common_base": COMMON,
    **{f"add_{name}": COMMON + fields for name, fields in GROUPS.items()},
    **{f"without_{name}": tuple(
        c for c in NEW_VARIANTS[REFERENCE] if c not in fields
    ) for name, fields in GROUPS.items()},
    REFERENCE: NEW_VARIANTS[REFERENCE],
}
assert set(COMMON) | {c for fields in GROUPS.values() for c in fields} == set(
    VARIANTS[REFERENCE]
)
assert sum(map(len, GROUPS.values())) + len(COMMON) == len(VARIANTS[REFERENCE])


def _records(rows, defense, ratings, recent):
    pairs = join_ratings(rows, ratings)
    defensive = join_defense(rows, defense)
    recent_pairs = join_recent(rows, recent, pairs, defense)
    records = {}
    for row in rows:
        bout = row.source_bout_id
        a, b = pairs[bout]
        records[bout] = {
            **row.feature_differences,
            **defensive[bout],
            ELO_COLUMN: a.rating - b.rating,
            **recent_pairs[bout],
            "prior_fights_a": a.prior_fights,
            "prior_fights_b": b.prior_fights,
        }
    return records


def _matrix(rows, records, columns):
    return np.asarray([
        [np.nan if records[r.source_bout_id][c] is None
         else records[r.source_bout_id][c] for c in columns]
        for r in rows
    ], dtype=float)


def compare_recent_groups(rows, defense, ratings, recent, saved):
    """Fit variants only on earlier decisive fights; leave all saved rows intact."""
    records = _records(rows, defense, ratings, recent)
    predictions = _references(rows, records, saved, candidate="common_base")
    for record in predictions:
        for field in (
            "probabilities_a_win", "swapped_probabilities_b_win",
            "raw_directional_probabilities",
        ):
            record[field].update({name: None for name in VARIANTS
                                  if name not in record[field] and name != REFERENCE})
    by_bout = {r["source_bout_id"]: r for r in predictions}
    ordered = sorted(rows, key=lambda r: (r.event_date, r.source_bout_id))
    folds = []
    with threadpool_limits(limits=1):
        for fold in DEVELOPMENT_FOLDS:
            train = [r for r in ordered if r.event_date <= fold.train_through
                     and r.target_a_win is not None]
            validation = [r for r in ordered if fold.validate_from <= r.event_date
                          <= fold.validate_through]
            selected = [r for r in validation if r.target_a_win is not None]
            if not train or not selected:
                raise ValueError(f"Empty development fold: {fold.name}")
            targets = [r.target_a_win for r in train]
            reference_columns = VARIANTS[REFERENCE]
            signs = np.asarray([1 if c.endswith("_sum") else -1
                                for c in reference_columns])
            old = fit_symmetric(_matrix(train, records, reference_columns),
                                targets, signs)
            old_matrix = _matrix(selected, records, reference_columns)
            p, forward, backward = symmetric_probabilities(old, old_matrix, signs)
            reversed_p = symmetric_probabilities(
                old, swap_features(old_matrix, signs), signs
            )[0]
            error = max(abs(actual - expected) for r, *values in zip(
                selected, p, forward, backward, reversed_p, strict=True
            ) for actual, expected in zip(values, (
                by_bout[r.source_bout_id]["probabilities_a_win"][REFERENCE],
                by_bout[r.source_bout_id]["raw_directional_probabilities"][REFERENCE][
                    "forward_a_win"],
                by_bout[r.source_bout_id]["raw_directional_probabilities"][REFERENCE][
                    "reverse_b_win"],
                by_bout[r.source_bout_id]["swapped_probabilities_b_win"][REFERENCE],
            ), strict=True))
            if error > 1e-12:
                raise ValueError(f"Saved reference refit differs: {fold.name} ({error})")
            for name, columns in VARIANTS.items():
                if name == REFERENCE:
                    continue
                signs = np.asarray([1 if c.endswith("_sum") else -1
                                    for c in columns])
                model = fit_symmetric(_matrix(train, records, columns), targets, signs)
                matrix = _matrix(selected, records, columns)
                probs, front, back = symmetric_probabilities(model, matrix, signs)
                swapped = symmetric_probabilities(
                    model, swap_features(matrix, signs), signs
                )[0]
                if not np.allclose(probs + swapped, 1, rtol=0, atol=1e-12):
                    raise ValueError(f"Fighter-order symmetry failed: {fold.name}/{name}")
                for r, value, reverse, fwd, bwd in zip(
                    selected, probs, swapped, front, back, strict=True
                ):
                    out = by_bout[r.source_bout_id]
                    out["probabilities_a_win"][name] = float(value)
                    out["swapped_probabilities_b_win"][name] = float(reverse)
                    out["raw_directional_probabilities"][name] = {
                        "forward_a_win": float(fwd), "reverse_b_win": float(bwd),
                    }
            folds.append({
                **asdict(fold), "train_decisive": len(train),
                "validation_bouts": len(validation),
                "draw_nc_exclusions": len(validation) - len(selected),
                "matched_reference_refit_maximum_absolute_error": float(error),
                "scores": _scores([r for r in predictions
                                   if r["fold"] == fold.name], VARIANTS),
            })
    comparisons = {}
    for group in GROUPS:
        for candidate, reference in (
            (f"add_{group}", "common_base"),
            (REFERENCE, f"without_{group}"),
        ):
            paired = _paired_summary([{
                "event_date": r["event_date"],
                "target_a_win": r["target_a_win"],
                "baseline_probability_a_win": r["probabilities_a_win"][reference],
                "defense_probability_a_win": r["probabilities_a_win"][candidate],
            } for r in predictions])
            comparisons[f"{candidate}_minus_{reference}"] = {
                "delta": paired["delta_defense_minus_baseline"],
                "date_cluster_bootstrap_95_percent": paired[
                    "date_cluster_bootstrap_95_percent"
                ],
            }
    return predictions, {
        "folds": folds,
        "pooled": _scores(predictions, VARIANTS),
        "paired_comparisons": comparisons,
        "validation_bouts": len(predictions),
        "draw_nc_exclusions": sum(r["target_a_win"] is None for r in predictions),
        **_diagnostics(predictions, VARIANTS),
    }


def export_recent_groups(inputs: dict[str, Path], reference: Path, output: Path,
                         code_commit: str, *, expected_reference_sha256: str = (
                             EXPECTED_REFERENCE_SHA256)) -> dict:
    if not code_commit or not code_commit.strip() or output.exists():
        raise ValueError("Commit required; experiment output must be new.")
    if output.resolve() in {p.resolve() for p in inputs.values()} or (
        reference.resolve() in output.resolve().parents or
        any(output.resolve() in p.resolve().parents for p in inputs.values())
    ):
        raise ValueError("Experiment output overlaps an input.")
    previous = _snapshot(inputs, reference, expected_reference_sha256)
    saved = [json.loads(line) for line in (reference / "predictions.jsonl")
             .read_text(encoding="utf-8").splitlines()]
    rows = read_matchups(inputs["matchups"])
    defense = read_defensive_history(inputs["defensive_history"])
    ratings = read_rating_history(inputs["rating_history"])
    recent = read_recent_history(inputs["recent_history"])
    fights, stats = read_recent_sources(inputs["identified_fights"],
                                        inputs["identified_stats"])
    rating_audit = audit_prefight_ratings(fights, ratings)
    recent_audit = audit_prefight_recent(fights, stats, recent)
    predictions, report = compare_recent_groups(rows, defense, ratings, recent, saved)
    if any(_sha256(path) != previous[name + "_sha256"]
           for name, path in inputs.items()):
        raise ValueError("Experiment input changed while evaluating.")
    manifest = {
        "experiment": "recent_groups_v1",
        "status": "exploratory on repeatedly examined development folds; no promotion",
        "code_commit": code_commit,
        "reference_manifest_sha256": expected_reference_sha256,
        "reference_predictions_sha256": previous["predictions_sha256"],
        "source_sha256": {name: _sha256(path) for name, path in inputs.items()},
        "development_last_date": DEVELOPMENT_LAST_DATE,
        "total_source_bouts": len(rows),
        "rating_audit": rating_audit, "recent_audit": recent_audit,
        "reference": REFERENCE,
        "common_columns": list(COMMON),
        "groups": {name: list(columns) for name, columns in GROUPS.items()},
        "variants": {name: list(columns) for name, columns in VARIANTS.items()},
        "selection_policy": "fixed groups; matched paired deltas and dates; no selection from these folds",
        "environment": {"python": platform.python_version(), "numpy": np.__version__,
                        "scikit_learn": sklearn.__version__},
        **report,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=output.parent, prefix=".upset-recent-groups-") as temp:
        staged = Path(temp) / "study"
        _write_verified_json(staged / "predictions.jsonl", predictions, json_lines=True)
        manifest["predictions_sha256"] = _sha256(staged / "predictions.jsonl")
        _write_verified_json(staged / "manifest.json", manifest, json_lines=False)
        staged.rename(output)
    return manifest
