"""Verify and serve the v3 display scale over frozen v2 model values."""

import json
from bisect import bisect_right
from datetime import date
from itertools import pairwise
from pathlib import Path

import numpy as np

from upset.ratings import serving, serving_v2
from upset.ratings.build import ANCHORS

VERSION = "upset_rating_experimental_v3"
REFERENCE_BEFORE = "2019-01-01"
LEGACY_PERCENTILES, LEGACY_GRADES = zip(*ANCHORS)


def grade_for(combined, percentile, thresholds):
    """Thresholds are the inclusive lower bounds for grades 90 through 99."""
    if combined >= thresholds[0]:
        return 89 + bisect_right(thresholds, combined)
    old_curve = float(np.interp(percentile, LEGACY_PERCENTILES, LEGACY_GRADES))
    return min(89, serving_v2.curve_grade(old_curve, percentile))


def validate_row(row, metadata, previous):
    serving._validate_row(row, metadata, previous)
    thresholds = metadata["display_curve"]["upper_thresholds"]
    percentile = row.get("curve_percentile")
    outcomes = row.get("last_outcomes")
    if (not serving._number(percentile, 0, 1) or type(row.get("curve_score")) is not int
            or row["curve_score"] != grade_for(row["raw_combined"], percentile, thresholds)
            or not isinstance(outcomes, list) or not outcomes
            or any(outcome not in ("win", "loss", "other") for outcome in outcomes)):
        raise ValueError("Invalid v3 model grade or recorded outcomes.")
    expected = serving_v2.display_adjustments(
        row["curve_score"], row["bouts"], outcomes, previous["score"] if previous else None,
    )
    if any(key not in row or type(row[key]) is not type(value) or row[key] != value
           for key, value in expected.items()):
        raise ValueError("Invalid v3 display adjustments.")


def passes_gate(evaluation):
    common = evaluation["common_display"]
    recent = evaluation["recent"]
    v2, v3 = recent["v2"], recent["v3"]
    return (evaluation.get("engineering_checks_passed") is True
            and evaluation["policy"]["wrong_direction_updates"] == 0
            and len(evaluation["all_99_fighters"]) <= 10
            and common["bouts"] >= 500 and common["accuracy_difference"] >= -.02
            and 2 * v3["at_98"] <= v2["at_98"] and v3["at_least_90"] <= v2["at_least_90"]
            and recent["fighters"] > 0
            and .01 <= v3["at_least_95"] / recent["fighters"] <= .05)


class RatingSnapshot(serving_v2.RatingSnapshot):
    def estimate(self, database, report):
        result = super().estimate(database, report)
        result["version"] = VERSION
        if result["status"] == "available":
            age = date.fromisoformat(result["before"]) - date.fromisoformat(result["event_date"])
            result["rating_is_stale"] = age.days > 730
        return result


def load_snapshot(folder, database):
    folder, database = Path(folder), Path(database)
    metadata = json.loads((folder / "manifest.json").read_text())
    if (not isinstance(metadata, dict) or metadata.get("version") != VERSION
            or metadata.get("experimental") is not True or metadata.get("validated") is not False
            or not serving._finite_tree(metadata)
            or Path(metadata["input_database"]).resolve() != database.resolve()
            or serving._digest(database) != metadata.get("database_sha256")):
        raise ValueError("Experimental v3 rating snapshot version/database differs.")
    curve = metadata["display_curve"]
    thresholds = curve["upper_thresholds"]
    if (curve["reference_before"] != REFERENCE_BEFORE
            or not REFERENCE_BEFORE < serving._day(metadata["latest_event"])
            < serving._day(metadata["before_exclusive"])
            or metadata["model"]["resume_weight"] != .5
            or metadata["model"]["skill_weights"] != [.5, .3, .2]
            or not isinstance(thresholds, list) or len(thresholds) != 10
            or not all(serving._number(x, 60, 99) for x in thresholds)
            or not all(a < b for a, b in pairwise(thresholds))):
        raise ValueError("Invalid v3 date or grade thresholds.")
    serving._verify_hashes(metadata["input_sha256"])
    outputs = metadata["output_sha256"]
    if not {"ratings.jsonl", "evaluation.json"} <= outputs.keys():
        raise ValueError("Missing required v3 outputs.")
    for name, expected in outputs.items():
        path = folder / name
        if not path.resolve().is_relative_to(folder.resolve()) or serving._digest(path) != expected:
            raise ValueError("V3 snapshot output hash differs: " + name)
    evaluation = json.loads((folder / "evaluation.json").read_text())
    if evaluation.get("version") != VERSION or not passes_gate(evaluation):
        raise ValueError("V3 snapshot failed its serving gate.")
    serving._validate_evaluation({**evaluation, "version": serving.VERSION})

    rows, previous = [], {}
    with (folder / "ratings.jsonl").open() as stream:
        for line in stream:
            row = json.loads(line)
            uid = row["fighter_id"]
            validate_row(row, metadata, previous.get(uid))
            previous[uid] = row
            rows.append(row)
    if not rows:
        raise ValueError("V3 snapshot contains no ratings.")
    return RatingSnapshot(metadata, rows, evaluation)
