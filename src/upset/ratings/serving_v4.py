"""Verify and serve the smoother v4 display over frozen v3 model values."""

import json
from pathlib import Path

from upset.ratings import serving, serving_v3

VERSION = "upset_rating_experimental_v4"


def smoothed_thresholds(low, high):
    """Inclusive lower bounds for 90–99, with progressively wider bands."""
    if not 60 <= low < high <= 99:
        raise ValueError("Invalid v4 scale anchors.")
    width = (high - low) / 9
    # Sum of the first i widths in the progression from 0.5 to 1.5.
    return [low + width * (i / 2 + i * (i - 1) / 16) for i in range(9)] + [high]


def passes_gate(evaluation):
    common = evaluation["common_display"]
    recent = evaluation["recent"]
    jumps = evaluation["modest_changes_near_upper_bands"]
    return (
        evaluation["engineering_checks_passed"] is True
        and evaluation["policy"]["wrong_direction_updates"] == 0
        and len(evaluation["all_99_fighters"]) <= 10
        and common["bouts"] >= 500
        and common["accuracy_difference"] >= -.02
        and recent["fighters"] > 0
        and .01 <= recent["v4"]["at_least_95"] / recent["fighters"] <= .05
        and recent["v4"]["at_least_90"] <= recent["v3"]["at_least_90"]
        and 2 * recent["v4"]["at_98"] <= recent["v2"]["at_98"]
        and jumps["updates"] >= 50
        and jumps["v3_moves_at_least_four"] > 0
        and 5 * jumps["v4_moves_at_least_four"] <= 4 * jumps["v3_moves_at_least_four"]
    )


class RatingSnapshot(serving_v3.RatingSnapshot):
    def estimate(self, database, report):
        result = super().estimate(database, report)
        result["version"] = VERSION
        return result


def load_snapshot(folder, database):
    folder, database = Path(folder), Path(database)
    metadata = json.loads((folder / "manifest.json").read_text())
    if (metadata.get("version") != VERSION or metadata.get("experimental") is not True
            or metadata.get("validated") is not False or not serving._finite_tree(metadata)
            or Path(metadata["input_database"]).resolve() != database.resolve()
            or serving._digest(database) != metadata["database_sha256"]):
        raise ValueError("Experimental v4 rating snapshot version/database differs.")
    serving._verify_hashes(metadata["input_sha256"])
    parent_path = Path(metadata["parent_manifest"])
    if str(parent_path) not in metadata["input_sha256"]:
        raise ValueError("V4 requires a verified v3 parent.")
    parent = json.loads(parent_path.read_text())
    parent_curve = parent["display_curve"]
    curve = metadata["display_curve"]
    anchors = parent_curve["upper_thresholds"]
    if (parent["version"] != serving_v3.VERSION
            or any(metadata[key] != parent[key] for key in
                   ("before_exclusive", "latest_event", "model", "database_sha256"))
            or curve != {**parent_curve, "first_spread_grade": 90,
                         "upper_thresholds": smoothed_thresholds(anchors[0], anchors[-1])}):
        raise ValueError("V4 scale or scope differs from the declared v3 anchors.")
    outputs = metadata["output_sha256"]
    if not {"ratings.jsonl", "evaluation.json"} <= outputs.keys():
        raise ValueError("Missing required v4 outputs.")
    for name, expected in outputs.items():
        path = folder / name
        if not path.resolve().is_relative_to(folder.resolve()) or serving._digest(path) != expected:
            raise ValueError("V4 snapshot output hash differs: " + name)
    evaluation = json.loads((folder / "evaluation.json").read_text())
    if evaluation["version"] != VERSION or not passes_gate(evaluation):
        raise ValueError("V4 snapshot failed its serving gate.")
    serving._validate_evaluation({**evaluation, "version": serving.VERSION})
    rows, previous = [], {}
    with (folder / "ratings.jsonl").open() as stream:
        for line in stream:
            row = json.loads(line)
            uid = row["fighter_id"]
            serving_v3.validate_row(row, metadata, previous.get(uid))
            rows.append(row)
            previous[uid] = row
    if not rows:
        raise ValueError("V4 snapshot contains no ratings.")
    return RatingSnapshot(metadata, rows, evaluation)
