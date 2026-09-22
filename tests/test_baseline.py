"""Protect the chronological holdout and train-only preprocessing boundary."""

import json
import subprocess
import sys
from dataclasses import replace
from datetime import date, timedelta

import numpy as np
import pytest

from upset.data.matchups import AMBIGUOUS_OUTCOME, INPUT_FIELDS, MatchupRow
from upset.modeling.baseline import (
    FEATURE_COLUMNS,
    evaluate_baseline,
    fit_baseline,
    read_matchups,
    split_by_event_date,
)

ALICE = "00000000-0000-4000-8000-000000000001"
BOB = "00000000-0000-4000-8000-000000000002"


def _row(day: int, side: int = 0, *, ambiguous: bool = False) -> MatchupRow:
    return MatchupRow(
        source_bout_id=f"bout-{day}-{side}",
        event_date=(date(2020, 1, 1) + timedelta(days=day)).isoformat(),
        fighter_a_id=ALICE,
        fighter_b_id=BOB,
        feature_differences={
            f"{field}_diff": day if index < 2 else float(day) / 10
            for index, field in enumerate(INPUT_FIELDS)
        },
        target_a_win=None if ambiguous else (day + side) % 2,
        training_exclusion_reason=AMBIGUOUS_OUTCOME if ambiguous else None,
        source_winner_label="Draw/NC" if ambiguous else "Alice",
    )


def _history() -> tuple[MatchupRow, ...]:
    rows = [_row(day, side) for day in range(20) for side in range(2)]
    rows[0] = _row(0, ambiguous=True)
    rows[36] = _row(18, ambiguous=True)
    return tuple(reversed(rows))  # The input file need not be date sorted.


def test_date_groups_remain_intact_and_ambiguous_rows_are_counted():
    rows = _history()
    splits = split_by_event_date(rows)

    assert [len(splits[name]) for name in ("train", "validation", "test")] == [
        28,
        6,
        6,
    ]
    dates = [{row.event_date for row in period} for period in splits.values()]
    assert dates[0].isdisjoint(dates[1])
    assert dates[1].isdisjoint(dates[2])
    assert max(dates[0]) < min(dates[1]) < min(dates[2])
    report = evaluate_baseline(rows)
    assert report["total_bouts"] == 40
    assert report["splits"]["train"]["excluded_draw_nc"] == 1
    assert report["splits"]["test"]["excluded_draw_nc"] == 1
    assert report["splits"]["train"]["decisive"] == 27
    assert tuple(report["feature_columns"]) == FEATURE_COLUMNS


def test_holdout_labels_and_values_cannot_affect_fitted_preprocessing_or_model():
    rows = _history()
    original = fit_baseline(split_by_event_date(rows)["train"])
    altered = tuple(
        replace(
            row,
            target_a_win=(1 - row.target_a_win)
            if row.target_a_win is not None
            else None,
            feature_differences={
                **row.feature_differences,
                "prior_fights_diff": 10_000_000,
            },
        )
        if row.event_date >= "2020-01-15"
        else row
        for row in rows
    )
    after = fit_baseline(split_by_event_date(altered)["train"])

    np.testing.assert_array_equal(
        original.named_steps["imputer"].statistics_,
        after.named_steps["imputer"].statistics_,
    )
    np.testing.assert_array_equal(
        original.named_steps["scaler"].mean_,
        after.named_steps["scaler"].mean_,
    )
    np.testing.assert_array_equal(
        original.named_steps["classifier"].coef_,
        after.named_steps["classifier"].coef_,
    )


def test_missing_train_feature_and_single_class_test_still_produce_report():
    rows = _history()
    changed = tuple(
        replace(
            row,
            target_a_win=0
            if row.event_date >= "2020-01-18" and (row.target_a_win is not None)
            else row.target_a_win,
            feature_differences={
                **row.feature_differences,
                "sig_strikes_accuracy_diff": (
                    None if row.event_date < "2020-01-15" else 100.0
                ),
            },
        )
        for row in rows
    )
    report = evaluate_baseline(changed)
    train = report["splits"]["train"]
    assert train["missing_by_feature"]["sig_strikes_accuracy_diff"] == 27
    assert report["splits"]["test"]["model_metrics"]["roc_auc"] is None
    assert report["splits"]["test"]["training_prior_metrics"]["roc_auc"] is None


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"target_a_win": True}, "Invalid decisive target"),
        ({"training_exclusion_reason": "wrong"}, "Invalid decisive target"),
        ({"event_date": "2020-1-1"}, "Invalid event date"),
        ({"fighter_b_id": ALICE}, "Unsorted or identical"),
        ({"feature_differences": {"winner": 1}}, "Unexpected feature columns"),
    ],
)
def test_reader_rejects_broken_contract(tmp_path, change, message):
    row = replace(_row(0), **change)
    path = tmp_path / "matchups.jsonl"
    path.write_text(json.dumps(row.as_record()) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match=message):
        read_matchups(path)


def test_reader_rejects_duplicate_bouts_and_nonfinite_features(tmp_path):
    row = _row(0)
    path = tmp_path / "matchups.jsonl"
    line = json.dumps(row.as_record()) + "\n"
    path.write_text(line * 2, encoding="utf-8")
    with pytest.raises(ValueError, match="Duplicate bout"):
        read_matchups(path)

    bad = replace(
        row,
        feature_differences={
            **row.feature_differences,
            "takedown_accuracy_diff": float("inf"),
        },
    )
    path.write_text(json.dumps(bad.as_record()) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Invalid takedown_accuracy_diff"):
        read_matchups(path)


def test_training_requires_both_targets_and_three_distinct_dates():
    with pytest.raises(ValueError, match="three nonempty periods"):
        split_by_event_date(tuple(_row(day) for day in range(2)))

    rows = tuple(
        replace(row, target_a_win=0)
        for row in _history()
        if row.target_a_win is not None
    )
    with pytest.raises(ValueError, match="both orientations"):
        fit_baseline(split_by_event_date(rows)["train"])


def test_command_reads_export_and_prints_machine_readable_report(tmp_path):
    path = tmp_path / "matchups.jsonl"
    path.write_text(
        "".join(json.dumps(row.as_record()) + "\n" for row in _history()),
        encoding="utf-8",
    )
    result = subprocess.run(
        [sys.executable, "-m", "upset.modeling.run_baseline", "--input", str(path)],
        capture_output=True,
        text=True,
        check=True,
    )
    report = json.loads(result.stdout)
    assert report["total_bouts"] == 40
    assert report["splits"]["test"]["decisive"] == 5
