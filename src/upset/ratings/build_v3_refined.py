"""Run the separately declared v3 revision over verified archived evidence."""

import argparse
import hashlib
import json
from bisect import bisect_left, bisect_right
from datetime import date
from math import inf, nextafter
from pathlib import Path

import numpy as np

from upset.ratings import build_v2 as v2
from upset.ratings import build_v3 as first
from upset.ratings import serving_v2, serving_v3
from upset.skill.striking_adapter import digest, encoded, verify_hashes, write_artifact


def refined_scale(reference, old_curve):
    def legacy_grade(x):
        p = (bisect_left(reference, x) + bisect_right(reference, x)) / (2 * len(reference))
        curve = float(np.interp(p, serving_v3.LEGACY_PERCENTILES, serving_v3.LEGACY_GRADES))
        return serving_v2.curve_grade(curve, p)

    thresholds = []
    for grade in range(90, 96):
        index = bisect_left(reference, grade, key=legacy_grade)
        between = nextafter(reference[index - 1], inf)
        thresholds.append(between if legacy_grade(between) >= grade else reference[index])
    spread = np.linspace(thresholds[-1], old_curve["upper_thresholds"][-1], 5).tolist()
    return {**old_curve, "first_spread_grade": 95, "upper_thresholds": thresholds[:-1] + spread}


def build(database, before, baseline, first_candidate, protocol, output):
    if output.exists() or output.resolve().is_relative_to(database.parent.resolve()):
        raise ValueError("Use a new output outside the serving database folder.")
    original_manifest = first_candidate / "manifest.json"
    manifest = json.loads(original_manifest.read_text())
    if (manifest["version"] != serving_v3.VERSION or digest(database) != manifest["database_sha256"]
            or database.resolve() != Path(manifest["input_database"]).resolve()
            or before < manifest["before_exclusive"]):
        raise ValueError("Use the first v3 candidate with the same frozen database and compatible cutoff.")
    hashes = dict(manifest["input_sha256"])
    for name, expected in manifest["output_sha256"].items():
        hashes[str((first_candidate / name).resolve())] = expected
    for name in ("manifest.json", "ratings.jsonl", "model.json", "displayed_comparisons.jsonl"):
        if str((baseline / name).resolve()) not in hashes:
            raise ValueError("Use the same v2 input as the first candidate.")
    for path in (Path(__file__), original_manifest, protocol):
        hashes[str(path.resolve())] = digest(path)
    verify_hashes(hashes)
    original = json.loads((first_candidate / "evaluation.json").read_text())
    if original["serving_eligible"] or not original["engineering_checks_passed"]:
        raise ValueError("Expected the archived first candidate to miss the declared grade distribution.")
    reference = json.loads((baseline / "model.json").read_text())["reference_values"]
    curve = refined_scale(reference, manifest["display_curve"])
    metadata = {**manifest, "before_exclusive": before, "display_curve": curve}
    old_rows = list(v2.read_rows(baseline / "ratings.jsonl"))
    new_rows = list(first.regrade(old_rows, metadata))
    if any(min(old["curve_score"], 95) != min(new["curve_score"], 95)
           for old, new in zip(old_rows, new_rows, strict=True)):
        raise ValueError("The refined scale moved a v2 boundary at or below grade 95.")
    prefix = [row for row in old_rows if row["event_date"] < first.PREFIX]
    names = json.loads((baseline / "manifest.json").read_text())["source_metadata"]["fighter_labels"]
    prefix_reference = sorted(row["raw_combined"] for row in prefix if row["event_date"] < first.START)
    prefix_ok = (refined_scale(prefix_reference, first.upper_scale(prefix, prefix_reference, names)) == curve
                 and list(first.regrade(prefix, metadata)) == [row for row in new_rows if row["event_date"] < first.PREFIX])
    versions = {"v2": old_rows, "v3": new_rows}
    # The original archive contains the verified decisive identities and dates.
    fights = v2.read_rows(first_candidate / "displayed_comparisons.jsonl")
    displays = list(v2.display_rows(fights, versions, names))
    records = {key: v2.display_result(displays, key) for key in versions}
    if records["v2"] != original["display_records"]["v2"]:
        raise ValueError("The v2 display evidence did not reproduce.")
    common = [row for row in displays
              if all(None not in row[key]["grades"] and len(set(row[key]["grades"])) == 2 for key in versions)]
    common_scores = {key: v2.display_result(common, key) for key in versions}
    difference = common_scores["v3"]["accuracy"] - common_scores["v2"]["accuracy"] if common else None
    latest = {row["fighter_id"]: row for row in new_rows}
    recent = {uid: row for uid, row in latest.items() if row["event_date"] >= first.RECENT}
    top = sorted(names[uid] for uid in {row["fighter_id"] for row in new_rows if row["score"] == 99})
    fields = ("event_date", "raw_combined", "curve_score", "score", "change", "change_adjustment",
              "small_history_adjustment", "outcome_hold")
    cases = {names[uid]: {**original["cases"][names[uid]], "v3": {key: row[key] for key in fields}}
             for uid, row in latest.items() if names[uid] in original["cases"]}
    evaluation = {
        **original, "engineering_checks_passed": prefix_ok, "track_record": records["v3"],
        "display_records": records,
        "common_display": {"bouts": len(common), "accuracy_difference": difference, **common_scores},
        "recent": {**original["recent"], "v3": first.summarize_recent(recent)},
        "policy": v2.policy(new_rows, names), "all_99_fighters": top, "cases": cases,
    }
    evaluation["serving_eligible"] = serving_v3.passes_gate(evaluation)
    files = {"ratings.jsonl": first.jsonl(new_rows), "evaluation.json": encoded(evaluation),
             "displayed_comparisons.jsonl": first.jsonl(displays), "protocol.md": protocol.read_text()}
    metadata.update({"input_sha256": hashes, "output_sha256": {
        name: hashlib.sha256(body.encode()).hexdigest() for name, body in files.items()}})
    verify_hashes(hashes)
    files["manifest.json"] = encoded(metadata)
    write_artifact(output, files)
    return evaluation


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("database", "baseline", "first-candidate", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--before", type=date.fromisoformat, required=True)
    parser.add_argument("--protocol", type=Path, default=Path("docs/OVERALL_RATING_PROTOCOL_V3_REFINED.md"))
    args = parser.parse_args()
    result = build(args.database, args.before.isoformat(), args.baseline, args.first_candidate,
                   args.protocol, args.output)
    print(encoded({key: result[key] for key in ("serving_eligible", "common_display", "recent", "cases")}))


if __name__ == "__main__":
    main()
