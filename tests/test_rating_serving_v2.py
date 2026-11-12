"""V2 serving enforces its declared gates and preserves dated history."""

from math import log, nextafter

import pytest
from test_rating_serving import A, artifact, query, row, write

from upset.ratings.serving_v2 import (
    VERSION,
    curve_grade,
    display_adjustments,
    load_snapshot,
)


@pytest.fixture
def v2_artifact(tmp_path):
    folder, database, source, _, evaluation, metadata = artifact(tmp_path)
    rows = []
    for day, bouts, score, peak, change, grade, unheld, reason, outcomes in (
        ("2019-01-01", 1, 76, 76, None, 76, 76, None, ["win"]),
        ("2019-01-04", 2, 80, 80, 4, 80, 80, None, ["win"]),
        ("2019-02-01", 4, 80, 80, 0, 78, 78, "held_after_win", ["win", "win"]),
        ("2020-01-01", 5, 80, 80, 0, 91, 85, "held_after_loss", ["loss"]),
        ("2021-01-01", 7, 77, 80, -3, 77, 77, None, ["win", "loss"]),
    ):
        rows.append({
            **row(A, day, bouts, score, peak, change),
            "curve_score": grade, "curve_unrounded": float(grade), "curve_percentile": .5,
            "unheld_score": unheld, "outcome_hold": reason, "last_outcomes": outcomes,
            "small_history_adjustment": 0, "change_adjustment": unheld - grade,
        })
    evaluation.update({
        "version": VERSION,
        "candidate": {"bouts": 700, "nll": .63},
        "comparison_to_v1": {
            "matched_bouts": 700, "nll_difference": .005,
            "common_display": {"bouts": 600, "accuracy_difference": -.005},
        },
        "policy": {"wrong_direction_updates": 0},
    })
    metadata["version"] = VERSION
    write(folder, rows, evaluation, metadata)
    return folder, database, source, rows, evaluation, metadata


def test_dated_history_exposes_holds_and_keeps_results_detached(v2_artifact):
    folder, database, *_ = v2_artifact
    snapshot = load_snapshot(folder, database)
    assert query(snapshot, database, "2019-01-01")["status"] == "no_history"
    assert query(snapshot, database, "2019-02-01")["outcome_hold"] is None
    held = query(snapshot, database, "2019-02-02")
    assert (held["score"], held["unheld_score"], held["outcome_hold"]) == (80, 78, "held_after_win")
    assert held["version"] == VERSION and held["experimental"] and not held["validated"]
    assert held["history"][-1]["last_outcomes"] == ["win", "win"]
    held["history"][-1]["last_outcomes"].clear()
    assert query(snapshot, database, "2019-02-03")["history"][-1]["last_outcomes"] == ["win", "win"]
    loss = query(snapshot, database, "2020-01-02")
    assert (loss["score"], loss["unheld_score"], loss["outcome_hold"]) == (80, 85, "held_after_loss")
    latest = query(snapshot, database, "2026-11-04")
    assert latest["score"] == 77 and latest["peak"] == 80
    assert query(snapshot, database, "2026-11-04", window=3) == latest
    assert query(snapshot, database, "2026-11-05")["status"] == "unsupported_cutoff"


def test_strict_99_and_optional_counterfactual_hold():
    assert curve_grade(98.5, .999) == 98
    assert curve_grade(99, nextafter(.9999, 0)) == 98
    assert curve_grade(nextafter(99, 0), .9999) == 98
    assert curve_grade(99, .9999) == 99
    assert curve_grade(76.5, .5) == 77
    assert display_adjustments(99, 1, ["loss"], None)["score"] == 88
    assert display_adjustments(98, 9, ["win"], 99)["score"] == 99
    assert display_adjustments(98, 9, ["win"], 99, hold=False)["score"] == 98
    assert display_adjustments(94, 9, ["win", "other"], 99)["score"] == 94


@pytest.mark.parametrize("name", ["database", "source", "ratings.jsonl", "evaluation.json"])
def test_changed_bound_artifacts_are_rejected(v2_artifact, name):
    folder, database, source, *_ = v2_artifact
    path = {"database": database, "source": source}.get(name, folder / name)
    with path.open("ab") as stream:
        stream.write(b" ")
    with pytest.raises(ValueError, match="hash|database"):
        load_snapshot(folder, database)


@pytest.mark.parametrize(("index", "update", "error"), [
    (0, {"outcome_hold": "held_after_loss"}, "outcome hold"),
    (2, {"outcome_hold": None}, "outcome hold"),
    (3, {"unheld_score": 91}, "outcome hold"),
    (4, {"last_outcomes": ["win", "win"]}, "outcome hold"),
    (4, {"last_outcomes": []}, "recorded outcomes"),
    (4, {"curve_score": 99, "curve_unrounded": 99, "curve_percentile": .99989}, "99 threshold"),
    (4, {"event_date": "2026-11-04"}, "cutoff"),
])
def test_rehashed_inconsistent_rows_are_rejected(v2_artifact, index, update, error):
    folder, database, _, rows, evaluation, metadata = v2_artifact
    rows[index].update(update)
    write(folder, rows, evaluation, metadata)
    with pytest.raises(ValueError, match=error):
        load_snapshot(folder, database)


@pytest.mark.parametrize(("path", "value"), [
    (("version",), "upset_rating_experimental_v1"),
    (("engineering_checks_passed",), False),
    (("serving_eligible",), False),
    (("candidate", "nll"), log(2)),
    (("comparison_to_v1", "matched_bouts"), 499),
    (("comparison_to_v1", "nll_difference"), .011),
    (("comparison_to_v1", "common_display", "bouts"), 499),
    (("comparison_to_v1", "common_display", "accuracy_difference"), -.021),
    (("policy", "wrong_direction_updates"), 1),
])
def test_evidence_must_pass_gates(v2_artifact, path, value):
    folder, database, _, rows, evaluation, metadata = v2_artifact
    target = evaluation
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    write(folder, rows, evaluation, metadata)
    with pytest.raises(ValueError, match="serving checks|gate|version"):
        load_snapshot(folder, database)
