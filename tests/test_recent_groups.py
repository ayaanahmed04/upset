"""The ablation replays the old model and isolates predefined recent groups."""

from copy import deepcopy

import pytest
import test_recent_form as fixtures

from upset.modeling.recent_form import VARIANTS as SAVED_VARIANTS
from upset.modeling.recent_groups import (
    COMMON,
    GROUPS,
    REFERENCE,
    VARIANTS,
    compare_recent_groups,
)

history = fixtures.history
stats = fixtures.stats
recent = fixtures.recent
comparison = fixtures.comparison
new_comparison = fixtures.new_comparison


def test_groups_partition_exact_full_model_and_control_evidence():
    columns = VARIANTS[REFERENCE]
    assert len(columns) == 36
    assert set(COMMON).isdisjoint({c for group in GROUPS.values() for c in group})
    assert sum(len(group) for group in GROUPS.values()) + len(COMMON) == 36
    assert GROUPS["control_margin"] == (
        "recent_control_margin_diff", "recent_log_control_seconds_diff",
        "recent_log_control_seconds_sum",
    )
    assert "recent_control_margin_diff" not in VARIANTS["without_control_margin"]
    assert "recent_log_control_seconds_sum" not in VARIANTS[
        "without_control_margin"
    ]


@pytest.fixture(scope="module")
def group_comparison(history, recent, new_comparison):
    rows, defense, ratings, _ = history
    return compare_recent_groups(rows, defense, ratings, recent, new_comparison[0])


def test_same_cohort_all_reference_values_unchanged_and_date_paired(
    group_comparison, new_comparison
):
    predictions, report = group_comparison
    saved = new_comparison[0]
    assert len(predictions) == len(saved) == 96
    assert len(report["paired_comparisons"]) == 2 * len(GROUPS)
    assert all(score["decisive_bouts"] == 95 for score in report["pooled"].values())
    for current, previous in zip(predictions, saved, strict=True):
        for field in ("probabilities_a_win", "swapped_probabilities_b_win"):
            assert {k: current[field][k] for k in SAVED_VARIANTS} == previous[field]
        assert {k: current["raw_directional_probabilities"][k]
                for k in previous["raw_directional_probabilities"]} == previous[
                    "raw_directional_probabilities"
                ]
        assert set(VARIANTS).issubset(current["probabilities_a_win"])
    assert report["pooled"][REFERENCE]["log_loss"] == pytest.approx(
        new_comparison[1]["pooled"][REFERENCE]["log_loss"]
    )
    assert all(f["matched_reference_refit_maximum_absolute_error"] < 1e-12
               for f in report["folds"])
    assert all(report["symmetry"][name]["maximum_absolute_error"] < 1e-12
               for name in VARIANTS)


def test_2023_validation_labels_do_not_change_predictions_in_that_fold(
    history, recent, new_comparison, group_comparison
):
    from dataclasses import replace

    rows, defense, ratings, _ = history
    changed_rows = tuple(replace(r, target_a_win=1 - r.target_a_win)
                         if r.event_date.startswith("2023") and r.target_a_win is not None
                         else r for r in rows)
    changed_saved = deepcopy(new_comparison[0])
    for row in changed_saved:
        if row["fold"] == "2023_partial" and row["target_a_win"] is not None:
            row["target_a_win"] = 1 - row["target_a_win"]
    changed, _ = compare_recent_groups(
        changed_rows, defense, ratings, recent, changed_saved
    )
    original = {r["source_bout_id"]: r for r in group_comparison[0]}
    for row in changed:
        if row["fold"] == "2023_partial":
            assert row["probabilities_a_win"] == original[row["source_bout_id"]][
                "probabilities_a_win"
            ]
            assert all(row["probabilities_a_win"][name] is not None
                       for name in VARIANTS)
