"""Load verified experimental v2 ratings for dated, lookup-only serving."""

import json
from copy import deepcopy
from math import floor, log
from pathlib import Path

from upset.ratings import serving as v1

VERSION = "upset_rating_experimental_v2"
REFERENCE_BEFORE = "2019-01-01"


def curve_grade(unrounded, percentile):
    """Round half up while reserving 99 for the highest reference tier."""
    if percentile >= .9999 and unrounded >= 99:
        return 99
    return min(98, floor(unrounded + .5))


def display_adjustments(curve_score, bouts, last_outcomes, previous_score, *, hold=True):
    """Compute the badge and its adjustments in the protocol's order."""
    protected = min(curve_score, 88) if bouts < 5 else curve_score
    unheld = protected
    reason = None
    if previous_score is not None:
        unheld = max(previous_score - 5, min(previous_score + 5, protected))
    if hold and previous_score is not None and last_outcomes:
        if unheld < previous_score and all(result == "win" for result in last_outcomes):
            reason = "held_after_win"
        elif unheld > previous_score and all(result == "loss" for result in last_outcomes):
            reason = "held_after_loss"
    return {
        "small_history_adjustment": protected - curve_score,
        "change_adjustment": unheld - protected,
        "unheld_score": unheld,
        "outcome_hold": reason,
        "score": previous_score if reason else unheld,
    }


def _validate_evaluation(evaluation):
    if not isinstance(evaluation, dict) or evaluation.get("version") != VERSION:
        raise ValueError("Rating snapshot evaluation version differs.")
    v1._validate_evaluation({**evaluation, "version": v1.VERSION})
    candidate = evaluation.get("candidate")
    comparison = evaluation.get("comparison_to_v1")
    policy = evaluation.get("policy")
    if not all(isinstance(item, dict) for item in (candidate, comparison, policy)):
        raise ValueError("V2 rating evaluation requires its matched comparison and policy checks.")
    matched = comparison.get("matched_bouts")
    nll = candidate.get("nll")
    delta = comparison.get("nll_difference")
    common = comparison.get("common_display")
    if (type(matched) is not int or matched < 500
            or type(candidate.get("bouts")) is not int or candidate["bouts"] != matched
            or not v1._number(nll, 0) or nll >= log(2)
            or not v1._number(delta, high=.010) or not isinstance(common, dict)):
        raise ValueError("V2 rating evaluation failed the matched log-loss gate.")
    count, display_delta = common.get("bouts"), common.get("accuracy_difference")
    violations = policy.get("wrong_direction_updates")
    if (type(count) is not int or not 500 <= count <= matched
            or not v1._number(display_delta, -.02, 1)
            or type(violations) is not int or violations != 0):
        raise ValueError("V2 rating evaluation failed the display comparison or policy gate.")


def _validate_row(row, metadata, previous):
    v1._validate_row(row, metadata, previous)
    percentile, unrounded, curve_score = (
        row.get(key) for key in ("curve_percentile", "curve_unrounded", "curve_score")
    )
    if (not v1._number(percentile, 0, 1) or not v1._number(unrounded, 60, 99)
            or type(curve_score) is not int or curve_score != curve_grade(unrounded, percentile)):
        raise ValueError("Rating curve grade differs from the declared rounding and 99 threshold.")
    outcomes = row.get("last_outcomes")
    if (not isinstance(outcomes, list) or not outcomes
            or any(result not in ("win", "loss", "other") for result in outcomes)):
        raise ValueError("Rating update needs its recorded outcomes.")
    expected = display_adjustments(
        curve_score, row["bouts"], outcomes, previous["score"] if previous else None,
    )
    for key, value in expected.items():
        if key not in row or type(row[key]) is not type(value) or row[key] != value:
            raise ValueError("Rating cap or outcome hold is inconsistent: " + key)


class RatingSnapshot(v1.RatingSnapshot):
    """Preserve the dated snapshot interface and expose v2 display history."""

    def estimate(self, database, report):
        result = super().estimate(database, report)
        result["version"] = VERSION
        if result["status"] == "available":
            for point, row in zip(result["history"], self._rows[report["id"]]):
                point.update({
                    "unheld_score": row["unheld_score"],
                    "outcome_hold": row["outcome_hold"],
                    "last_outcomes": deepcopy(row["last_outcomes"]),
                })
        return result


def load_snapshot(folder, database):
    """Verify the artifact and its rule-consistent history before serving it."""
    folder, database = Path(folder), Path(database)
    metadata = json.loads((folder / "manifest.json").read_text())
    if not isinstance(metadata, dict):
        raise TypeError("Rating manifest must be an object.")
    if (metadata.get("version") != VERSION or metadata.get("experimental") is not True
            or metadata.get("validated") is not False
            or Path(metadata["input_database"]).resolve() != database.resolve()
            or v1._digest(database) != metadata.get("database_sha256")):
        raise ValueError("Experimental rating snapshot version/database differs.")
    before, latest = v1._day(metadata["before_exclusive"]), v1._day(metadata["latest_event"])
    reference = v1._day(metadata["display_curve"]["reference_before"])
    if latest >= before or reference > before or reference != REFERENCE_BEFORE:
        raise ValueError("Rating snapshot date contract differs.")
    model = metadata["model"]
    if (not isinstance(model, dict) or model.get("resume_weight") != .5
            or model.get("skill_weights") != [.5, .3, .2] or not v1._finite_tree(metadata)):
        raise ValueError("Invalid experimental rating model metadata.")
    v1._verify_hashes(metadata["input_sha256"])
    outputs = metadata.get("output_sha256")
    if not isinstance(outputs, dict) or not {"ratings.jsonl", "evaluation.json"} <= outputs.keys():
        raise ValueError("Rating snapshot is missing bound outputs.")
    for name, expected in outputs.items():
        path = folder / name
        if not path.resolve().is_relative_to(folder.resolve()) or v1._digest(path) != expected:
            raise ValueError("Rating snapshot output hash differs: " + name)
    evaluation = json.loads((folder / "evaluation.json").read_text())
    _validate_evaluation(evaluation)

    rows, previous = [], {}
    with (folder / "ratings.jsonl").open() as observations:
        for line in observations:
            row = json.loads(line)
            if not isinstance(row, dict):
                raise TypeError("Rating observation must be an object.")
            uid = row["fighter_id"]
            _validate_row(row, metadata, previous.get(uid))
            previous[uid] = row
            rows.append(row)
    if not rows:
        raise ValueError("Experimental rating snapshot contains no ratings.")
    return RatingSnapshot(metadata, rows, evaluation)
