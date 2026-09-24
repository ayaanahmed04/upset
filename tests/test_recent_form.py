"""Chronological integration with preserved references and source audits."""

import json
from copy import deepcopy
from dataclasses import replace

import numpy as np
import pytest
import test_elo_comparison as elo_fixtures
from test_prefight_defense import _pair

from upset.data.prefight_recent import build_recent_history
from upset.modeling.defense_ablation import export_defense_ablation, join_defense
from upset.modeling.elo_comparison import VARIANTS as ORIGINAL_VARIANTS
from upset.modeling.elo_comparison import export_elo_comparison, join_ratings
from upset.modeling.evaluation import _sha256
from upset.modeling.recent_form import (
    NEW_VARIANTS,
    RECENT_COLUMNS,
    VARIANTS,
    compare_recent_form,
    export_recent_form,
    feature_matrix,
    join_recent,
)
from upset.modeling.symmetric import swap_features

# Reuse the existing source fixture and its preserved experiment predictions.
history = elo_fixtures.history
comparison = elo_fixtures.comparison


@pytest.fixture(scope="module")
def stats(history):
    # Recreate the exact synthetic raw statistics used by the existing fixture.
    rows = []
    for identified in history[3]:
        bout = identified.fight.source_bout_id
        _, month, index = map(int, bout.split("-"))
        pair = _pair(
            bout, a_sig=month + index, b_sig=month, a_kd=index % 2, b_kd=month % 2
        )
        for side, record in enumerate(pair):
            source_id = (
                identified.fight.source_fighter_1_id,
                identified.fight.source_fighter_2_id,
            )[side]
            fighter_id = (identified.upset_fighter_1_id, identified.upset_fighter_2_id)[
                side
            ]
            rows.append(
                replace(
                    record,
                    upset_fighter_id=fighter_id,
                    stats=replace(record.stats, source_fighter_id=source_id),
                )
            )
    return rows


@pytest.fixture(scope="module")
def recent(history, stats):
    return {
        (r.source_bout_id, r.upset_fighter_id): r
        for r in build_recent_history(history[3], stats)
    }


@pytest.fixture(scope="module")
def new_comparison(history, recent, comparison):
    return compare_recent_form(*history[:3], recent, comparison[0])


def test_same_cohort_exact_original_values_full_diagnostics_and_no_double_scoring(
    comparison, new_comparison
):
    old, _ = comparison
    predictions, report = new_comparison
    assert report["decisive_bouts"] == 95
    assert report["draw_nc_exclusions"] == 1
    assert len(predictions) == len(old)
    assert len(VARIANTS) == 12
    for row, previous in zip(predictions, old, strict=True):
        assert row["source_bout_id"] == previous["source_bout_id"]
        for field in ("probabilities_a_win", "swapped_probabilities_b_win"):
            assert {name: row[field][name] for name in ORIGINAL_VARIANTS} == previous[
                field
            ]
            assert set(row[field]) == set(VARIANTS)
            assert all(p is None for p in row[field].values()) == (
                row["target_a_win"] is None
            )
    # Mutation of the preserved prediction dictionaries is forbidden.
    assert all(set(row["probabilities_a_win"]) == set(ORIGINAL_VARIANTS) for row in old)
    for name in NEW_VARIANTS:
        assert report["symmetry"][name]["maximum_absolute_error"] <= 1e-12
        assert report["symmetry"][name]["conflicting_winner_picks"] == 0
    assert all(score["decisive_bouts"] == 95 for score in report["pooled"].values())
    assert all(
        sum(b["count"] for b in bins) == 95
        for bins in report["reliability_deciles"].values()
    )
    assert all(
        f["mirrored_train_rows"]
        == 2 * f["train_decisive"]
        == 2 * f["total_training_weight"]
        for f in report["folds"]
    )
    assert (
        "symmetric_recent_elo_minus_symmetric_defense_elo"
        in report["paired_comparisons"]
    )


def test_recent_feature_swap_rebuilds_signed_differences_and_preserves_exposure_sums(
    history, recent
):
    rows, defense, ratings, _ = history
    pairs = join_ratings(rows, ratings)
    joined = join_recent(rows, recent, pairs, defense)
    flipped_rows = tuple(
        replace(
            r,
            fighter_a_id=r.fighter_b_id,
            fighter_b_id=r.fighter_a_id,
            feature_differences={
                k: -v if v is not None else None
                for k, v in r.feature_differences.items()
            },
            target_a_win=1 - r.target_a_win if r.target_a_win is not None else None,
        )
        for r in rows
    )
    flipped_pairs = join_ratings(flipped_rows, ratings)
    flipped_joined = join_recent(flipped_rows, recent, flipped_pairs, defense)
    columns = NEW_VARIANTS["symmetric_recent_elo"]
    matrix = feature_matrix(rows, join_defense(rows, defense), pairs, joined, columns)
    swapped = feature_matrix(
        flipped_rows,
        join_defense(flipped_rows, defense),
        flipped_pairs,
        flipped_joined,
        columns,
    )
    signs = np.asarray([1 if c.endswith("_sum") else -1 for c in columns])
    assert np.array_equal(swap_features(matrix, signs), swapped, equal_nan=True)
    assert len(RECENT_COLUMNS) == 18


def test_future_features_do_not_change_development_predictions(
    history, recent, comparison, new_comparison
):
    rows, defense, ratings, _ = history
    changed = deepcopy(recent)
    for row in changed.values():
        if row.event_date > "2023-08-19":
            row.features["sig_landed_per_minute"] = 1e9
    assert (
        compare_recent_form(rows, defense, ratings, changed, comparison[0])
        == new_comparison
    )


def test_validation_labels_cannot_change_that_folds_fitted_predictions(
    history, recent, comparison, new_comparison
):
    rows, defense, ratings, _ = history
    changed_rows = tuple(
        replace(r, target_a_win=1 - r.target_a_win)
        if r.event_date.startswith("2019") and r.target_a_win is not None
        else r
        for r in rows
    )
    changed_references = deepcopy(comparison[0])
    for row in changed_references:
        if row["fold"] == "2019" and row["target_a_win"] is not None:
            row["target_a_win"] = 1 - row["target_a_win"]
    predictions, _ = compare_recent_form(
        changed_rows, defense, ratings, recent, changed_references
    )
    original = {r["source_bout_id"]: r for r in new_comparison[0]}
    for row in predictions:
        if row["fold"] == "2019":
            assert (
                row["probabilities_a_win"]
                == original[row["source_bout_id"]]["probabilities_a_win"]
            )


def test_missing_extra_or_mismatched_recent_join_rows_fail(history, recent):
    rows, defense, ratings, _ = history
    key = rows[0].source_bout_id, rows[0].fighter_a_id
    changed = dict(recent)
    changed.pop(key)
    with pytest.raises(ValueError, match="join keys"):
        join_recent(rows, changed, join_ratings(rows, ratings), defense)
    changed[key] = replace(recent[key], prior_fights=100)
    with pytest.raises(ValueError, match="prior counts"):
        join_recent(rows, changed, join_ratings(rows, ratings), defense)


@pytest.mark.parametrize("corruption", ["cohort", "target", "probability", "excluded"])
def test_bad_reference_data_is_rejected(history, recent, comparison, corruption):
    saved = deepcopy(comparison[0])
    if corruption == "cohort":
        saved.pop()
    elif corruption == "target":
        saved[0]["target_a_win"] = 1 - saved[0]["target_a_win"]
    elif corruption == "probability":
        saved[0]["probabilities_a_win"]["elo_only"] = float("nan")
    else:
        next(r for r in saved if r["target_a_win"] is None)["probabilities_a_win"][
            "elo_only"
        ] = 0.5
    with pytest.raises(ValueError, match="[Rr]eference"):
        compare_recent_form(*history[:3], recent, saved)


def test_export_validates_sources_replays_all_fields_and_preserves_prior_experiments(
    tmp_path, history, stats, recent
):
    rows, defense, ratings, fights = history
    paths = [
        tmp_path / name
        for name in (
            "matchups",
            "defense",
            "ratings",
            "recent",
            "fights",
            "stats",
            "registry",
        )
    ]
    for path, records in zip(
        paths[:-1],
        (rows, defense.values(), ratings.values(), recent.values(), fights, stats),
        strict=True,
    ):
        path.write_text("".join(json.dumps(r.as_record()) + "\n" for r in records))
    paths[-1].write_text('{"fixture": true}\n')
    first, reference, output = [tmp_path / d for d in ("first", "reference", "new")]
    export_defense_ablation(paths[0], paths[1], paths[-1], first, "first-fixture")
    export_elo_comparison(
        paths[0],
        paths[1],
        paths[2],
        paths[4],
        paths[-1],
        first,
        reference,
        "elo-fixture",
    )
    inputs = {
        p: p.read_bytes()
        for p in (*paths, reference / "manifest.json", reference / "predictions.jsonl")
    }
    manifest = export_recent_form(*paths, reference, output, "recent-fixture")
    assert manifest == json.loads((output / "manifest.json").read_text())
    assert manifest["recent_audit"]["all_recent_rows_checked"] == len(recent)
    assert manifest["recent_audit"]["all_numeric_fields_recomputed"]
    assert manifest["reference_code_commit"] == "elo-fixture"
    assert manifest["predictions_sha256"] == _sha256(output / "predictions.jsonl")
    assert all(p.read_bytes() == contents for p, contents in inputs.items())
    with pytest.raises(ValueError, match="already exists"):
        export_recent_form(*paths, reference, output, "again")
    # Hash tampering fails before publication.
    reference_json = reference / "manifest.json"
    prior = json.loads(reference_json.read_text())
    prior["predictions_sha256"] = "wrong"
    reference_json.write_text(json.dumps(prior))
    rejected = tmp_path / "rejected"
    with pytest.raises(ValueError, match="prediction hash"):
        export_recent_form(*paths, reference, rejected, "bad-reference")
    assert not rejected.exists()
    reference_json.write_bytes(inputs[reference_json])
    # Even a valid recent export cannot hide drift from the older source stats.
    changed_stats = deepcopy(stats)
    changed_stats[0].stats.knockdowns += 1
    paths[5].write_text(
        "".join(json.dumps(r.as_record()) + "\n" for r in changed_stats)
    )
    with pytest.raises(ValueError, match="Reference features differ"):
        export_recent_form(*paths, reference, rejected, "different-source")
    assert not rejected.exists()
