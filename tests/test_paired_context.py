"""Context retention, identity swaps, temporal isolation and preserved evidence."""

import json
from copy import deepcopy
from dataclasses import replace

import numpy as np
import pytest
import test_recent_form as fixtures

from upset.data.matchups import build_matchup_rows
from upset.data.prefight import build_prefight_snapshots
from upset.data.prefight_defense import build_defensive_history
from upset.data.prefight_features import build_prefight_features
from upset.data.prefight_ratings import build_rating_history
from upset.data.prefight_recent import build_recent_history
from upset.modeling.defense_ablation import export_defense_ablation
from upset.modeling.elo_comparison import export_elo_comparison
from upset.modeling.evaluation import _sha256
from upset.modeling.paired_context import (
    CANDIDATE,
    COLUMNS,
    COMPARATOR,
    DIFFERENCE_COLUMNS,
    FIGHTER_FIELDS,
    REFERENCE_VARIANTS,
    SWAP_INDICES,
    SWAP_SIGNS,
    VARIANTS,
    build_paired_records,
    compare_paired_context,
    export_paired_context,
    feature_matrix,
)
from upset.modeling.recent_form import export_recent_form
from upset.modeling.symmetric import swap_features

history = fixtures.history
comparison = fixtures.comparison
stats = fixtures.stats
recent = fixtures.recent
new_comparison = fixtures.new_comparison


def indexed(rows):
    return {(r.source_bout_id, r.upset_fighter_id): r for r in rows}


@pytest.fixture(scope="module")
def features(history, stats):
    return indexed(
        build_prefight_features(list(build_prefight_snapshots(history[3], stats)))
    )


@pytest.fixture(scope="module")
def paired_comparison(history, features, recent, new_comparison):
    rows, defense, ratings, _ = history
    return compare_paired_context(
        rows, features, defense, ratings, recent, new_comparison[0]
    )


def test_individual_values_retain_absolute_context_and_one_known_side(
    history, features, recent
):
    rows, defense, ratings, _ = history
    records = build_paired_records(rows, features, defense, ratings, recent)
    # Two high-output fighters can have the same difference as two low-output
    # fighters. The extra columns preserve that distinction explicitly.
    row = next(
        r
        for r in rows
        if all(
            features[r.source_bout_id, i].sig_strikes_landed_per_minute is not None
            for i in (r.fighter_a_id, r.fighter_b_id)
        )
    )
    changed = dict(features)
    for fighter_id in (row.fighter_a_id, row.fighter_b_id):
        key = row.source_bout_id, fighter_id
        changed[key] = replace(
            changed[key],
            sig_strikes_landed_per_minute=changed[key].sig_strikes_landed_per_minute
            + 2,
        )
    shifted = build_paired_records(rows, changed, defense, ratings, recent)
    assert np.allclose(
        feature_matrix([row], records, DIFFERENCE_COLUMNS),
        feature_matrix([row], shifted, DIFFERENCE_COLUMNS),
        equal_nan=True,
    )
    assert (
        records[row.source_bout_id]["sig_strikes_landed_per_minute_a"]
        != shifted[row.source_bout_id]["sig_strikes_landed_per_minute_a"]
    )
    one_history = next(
        r
        for r in rows
        if (features[r.source_bout_id, r.fighter_a_id].prior_fights == 0)
        != (features[r.source_bout_id, r.fighter_b_id].prior_fights == 0)
    )
    record = records[one_history.source_bout_id]
    assert record["sig_strikes_landed_per_minute_diff"] is None
    assert (
        sum(
            record[f"sig_strikes_landed_per_minute_{side}"] is not None
            for side in ("a", "b")
        )
        == 1
    )
    assert len(FIGHTER_FIELDS) == 33
    assert len(COLUMNS) == 102
    assert set(record) == set(COLUMNS)


def test_swap_rebuilt_from_opposite_fighter_ids_matches_permutation(
    history, features, recent
):
    rows, defense, ratings, _ = history
    swapped_rows = [
        replace(
            r,
            fighter_a_id=r.fighter_b_id,
            fighter_b_id=r.fighter_a_id,
            feature_differences={
                k: None if v is None else -v for k, v in r.feature_differences.items()
            },
        )
        for r in rows
    ]
    matrix = feature_matrix(
        rows, build_paired_records(rows, features, defense, ratings, recent)
    )
    rebuilt = feature_matrix(
        swapped_rows,
        build_paired_records(swapped_rows, features, defense, ratings, recent),
    )
    swapped = swap_features(matrix, SWAP_SIGNS, swap_indices=SWAP_INDICES)
    assert np.array_equal(swapped, rebuilt, equal_nan=True)
    assert np.array_equal(
        swap_features(swapped, SWAP_SIGNS, swap_indices=SWAP_INDICES),
        matrix,
        equal_nan=True,
    )


def test_bad_feature_join_or_differences_cannot_enter_fit(history, features, recent):
    rows, defense, ratings, _ = history
    key = rows[0].source_bout_id, rows[0].fighter_a_id
    broken = dict(features)
    broken.pop(key)
    with pytest.raises(ValueError, match="feature keys"):
        build_paired_records(rows, broken, defense, ratings, recent)
    broken[key] = replace(features[key], event_date="2010-01-01")
    with pytest.raises(ValueError, match="identity/date/exposure"):
        build_paired_records(rows, broken, defense, ratings, recent)
    bad_rows = list(rows)
    bad_rows[0] = replace(
        rows[0],
        feature_differences={
            **rows[0].feature_differences,
            "prior_fight_seconds_diff": 1,
        },
    )
    with pytest.raises(ValueError, match="do not reproduce"):
        build_paired_records(bad_rows, features, defense, ratings, recent)


def test_current_same_date_and_future_source_changes_leave_prior_context_unchanged(
    history, stats, features, recent
):
    rows, defense, ratings, fights = history
    day = "2023-08-01"
    affected = {f.fight.source_bout_id for f in fights if f.fight.event_date >= day}
    altered_stats = [
        replace(s, stats=replace(s.stats, knockdowns=s.stats.knockdowns + 99))
        if s.stats.source_bout_id in affected
        else s
        for s in stats
    ]
    altered_fights = [
        replace(
            f,
            fight=replace(
                f.fight,
                winner_name=f.fight.fighter_2_name,
                source_winner_label=f.fight.fighter_2_name,
            ),
        )
        if f.fight.source_bout_id in affected
        else f
        for f in fights
    ]
    new_features = build_prefight_features(
        list(build_prefight_snapshots(altered_fights, altered_stats))
    )
    new_rows = build_matchup_rows(altered_fights, list(new_features))
    old_records = build_paired_records(rows, features, defense, ratings, recent)
    new_records = build_paired_records(
        new_rows,
        indexed(new_features),
        indexed(build_defensive_history(altered_fights, altered_stats)),
        indexed(build_rating_history(altered_fights)),
        indexed(build_recent_history(altered_fights, altered_stats)),
    )
    assert all(
        old_records[r.source_bout_id] == new_records[r.source_bout_id]
        for r in rows
        if r.event_date <= day
    )


def test_preserved_references_same_cohort_refit_and_complementarity(
    new_comparison, paired_comparison
):
    previous, _ = new_comparison
    predictions, report = paired_comparison
    assert report["decisive_bouts"] == 95
    assert report["draw_nc_exclusions"] == 1
    assert len(predictions) == 96
    for old, new in zip(previous, predictions, strict=True):
        for field in (
            "probabilities_a_win",
            "swapped_probabilities_b_win",
            "raw_directional_probabilities",
        ):
            assert {k: v for k, v in new[field].items() if k != CANDIDATE} == old[field]
        assert new["event_date"] <= "2023-08-19"
        assert (new["probabilities_a_win"][CANDIDATE] is None) == (
            new["target_a_win"] is None
        )
    assert all(CANDIDATE not in r["probabilities_a_win"] for r in previous)
    assert report["symmetry"][CANDIDATE]["maximum_absolute_error"] <= 1e-12
    assert report["symmetry"][CANDIDATE]["conflicting_winner_picks"] == 0
    for fold in report["folds"]:
        assert fold["matched_tree_refit_maximum_absolute_error"] <= 1e-12
        assert fold["mirrored_train_rows"] == 2 * fold["total_training_weight"]
        assert fold["train_through"] < fold["validate_from"]
    assert set(report["pooled"]) == set(VARIANTS)
    assert set(report["ten_bin_ece"]) == set(VARIANTS)
    assert len(report["paired_comparisons"]) == 2


def test_changed_last_validation_labels_do_not_change_predictions(
    history, features, recent, new_comparison, paired_comparison
):
    rows, defense, ratings, _ = history
    altered = [
        replace(r, target_a_win=1 - r.target_a_win)
        if "2023-01-01" <= r.event_date <= "2023-08-19" and r.target_a_win is not None
        else r
        for r in rows
    ]
    saved = deepcopy(new_comparison[0])
    for row in saved:
        if row["fold"] == "2023_partial" and row["target_a_win"] is not None:
            row["target_a_win"] = 1 - row["target_a_win"]
    predictions, _ = compare_paired_context(
        altered, features, defense, ratings, recent, saved
    )
    assert [r["probabilities_a_win"] for r in predictions] == [
        r["probabilities_a_win"] for r in paired_comparison[0]
    ]


@pytest.mark.parametrize("corruption", ["cohort", "groups", "probability", "refit"])
def test_bad_reference_is_rejected(
    history, features, recent, new_comparison, corruption
):
    rows, defense, ratings, _ = history
    saved = deepcopy(new_comparison[0])
    if corruption == "cohort":
        saved.pop()
    elif corruption == "groups":
        saved[0]["diagnostic_groups"]["history"] = "invented"
    else:
        saved[0]["probabilities_a_win"][COMPARATOR] = (
            float("nan")
            if corruption == "probability"
            else saved[0]["probabilities_a_win"][COMPARATOR] + 0.01
        )
    with pytest.raises(ValueError, match="[Rr]eference|refit"):
        compare_paired_context(rows, features, defense, ratings, recent, saved)


def test_export_checks_full_sources_pinned_manifest_readback_and_no_overwrites(
    tmp_path, history, stats, recent
):
    rows, defense, ratings, fights = history
    paths = [
        tmp_path / n
        for n in (
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
    paths[-1].write_text('{"fixture":true}\n')
    first, elo, reference, output = [
        tmp_path / n for n in ("first", "elo", "reference", "output")
    ]
    export_defense_ablation(paths[0], paths[1], paths[-1], first, "base")
    export_elo_comparison(
        paths[0], paths[1], paths[2], paths[4], paths[-1], first, elo, "elo"
    )
    export_recent_form(*paths, elo, reference, "recent")
    pinned = _sha256(reference / "manifest.json")
    inputs = {
        p: p.read_bytes()
        for p in (*paths, reference / "manifest.json", reference / "predictions.jsonl")
    }
    report = export_paired_context(
        *paths, reference, output, "context", expected_reference_sha256=pinned
    )
    assert report == json.loads((output / "manifest.json").read_text())
    assert report["predictions_sha256"] == _sha256(output / "predictions.jsonl")
    assert report["recent_audit"]["comparison"] == "matched"
    assert report["rating_audit"]["comparison"] == "matched"
    assert report["individual_feature_rows_checked"] == len(recent)
    assert report["source_bouts_after_development_not_scored"] > 0
    assert all(p.read_bytes() == original for p, original in inputs.items())
    with pytest.raises(ValueError, match="already exists"):
        export_paired_context(
            *paths, reference, output, "again", expected_reference_sha256=pinned
        )
    rejected = tmp_path / "rejected"
    with pytest.raises(ValueError, match="manifest hash"):
        export_paired_context(
            *paths, reference, rejected, "wrong-pin", expected_reference_sha256="bad"
        )
    paths[5].write_bytes(inputs[paths[5]] + b"\n")
    with pytest.raises(ValueError, match="source hash"):
        export_paired_context(
            *paths,
            reference,
            rejected,
            "changed-source",
            expected_reference_sha256=pinned,
        )
    paths[5].write_bytes(inputs[paths[5]])
    (reference / "predictions.jsonl").write_bytes(
        inputs[reference / "predictions.jsonl"] + b"\n"
    )
    with pytest.raises(ValueError, match="prediction hash"):
        export_paired_context(
            *paths,
            reference,
            rejected,
            "changed-probabilities",
            expected_reference_sha256=pinned,
        )
    assert not rejected.exists()
    assert set(report["variants"]) == set(REFERENCE_VARIANTS) | {CANDIDATE}
