"""Replay the v3 model and compare the predeclared smoother v4 display."""

import argparse
import hashlib
import json
from pathlib import Path

from upset.ratings import build_v2 as v2
from upset.ratings import build_v3 as v3
from upset.ratings import serving_v3, serving_v4
from upset.skill.striking_adapter import digest, encoded, verify_hashes, write_artifact

DISPLAY_FIELDS = {"score", "curve_score", "peak", "change", "change_adjustment",
                  "small_history_adjustment", "unheld_score", "outcome_hold"}
EXAMPLES = {
    "Charles Oliveira", "Francis Ngannou", "Ilia Topuria", "Islam Makhachev",
    "Jon Jones", "Justin Gaethje", "Michel Pereira",
}


def upper_band_changes(old_rows, new_rows):
    prior = {}
    counts = {"updates": 0, "v3_moves_at_least_four": 0, "v4_moves_at_least_four": 0}
    for old, new in zip(old_rows, new_rows, strict=True):
        uid, day = old["fighter_id"], old["event_date"]
        previous = prior.get(uid)
        prior[uid] = old
        outcomes = old["last_outcomes"]
        if (day < v3.START or previous is None or not 89 <= previous["curve_score"] <= 95
                or abs(old["raw_combined"] - previous["raw_combined"]) > 1.25
                or len(set(outcomes)) != 1 or outcomes[0] not in ("win", "loss")):
            continue
        counts["updates"] += 1
        counts["v3_moves_at_least_four"] += abs(old["change"]) >= 4
        counts["v4_moves_at_least_four"] += abs(new["change"]) >= 4
    return counts


def build(database, baseline, parent, protocol, output):
    if output.exists() or output.resolve().is_relative_to(database.parent.resolve()):
        raise ValueError("Use a new output directory outside the serving database folder.")
    parent_path = (parent / "manifest.json").resolve()
    manifest = json.loads(parent_path.read_text())
    hashes = {**manifest["input_sha256"], str(parent_path): digest(parent_path)}
    hashes.update({str((parent / name).resolve()): value for name, value in manifest["output_sha256"].items()})
    for path in (Path(__file__), Path(serving_v4.__file__), protocol):
        hashes[str(path.resolve())] = digest(path)
    verify_hashes(hashes)
    verified_parent = serving_v3.load_snapshot(parent, database)
    original = json.loads((parent / "evaluation.json").read_text())
    v2_paths = (baseline / "ratings.jsonl", baseline / "manifest.json")
    if any(str(path.resolve()) not in manifest["input_sha256"] for path in v2_paths):
        raise ValueError("The v2 rows and fighter labels must be bound by the v3 parent.")
    original_rows = list(v2.read_rows(v2_paths[0]))
    names = json.loads(v2_paths[1].read_text())["source_metadata"]["fighter_labels"]
    old_rows = list(v3.regrade(original_rows, manifest))
    if any(old != saved for old, saved in zip(
            old_rows, v2.read_rows(parent / "ratings.jsonl"), strict=True)):
        raise ValueError("Saved v3 rows did not reproduce.")

    curve = manifest["display_curve"]
    bounds = curve["upper_thresholds"]
    metadata = {**manifest, "version": serving_v4.VERSION, "parent_manifest": str(parent_path),
                "display_curve": {**curve, "first_spread_grade": 90,
                                  "upper_thresholds": serving_v4.smoothed_thresholds(bounds[0], bounds[-1])}}
    new_rows = list(v3.regrade(original_rows, metadata))
    preserved = all(
        old.keys() == new.keys() and all(old[k] == new[k] for k in old.keys() - DISPLAY_FIELDS)
        for old, new in zip(old_rows, new_rows, strict=True)
    )
    prefix = [row for row in original_rows if row["event_date"] < v3.PREFIX]
    prefix_ok = list(v3.regrade(prefix, metadata)) == [row for row in new_rows if row["event_date"] < v3.PREFIX]

    versions = {"v3": old_rows, "v4": new_rows}
    parent_bouts = list(v2.read_rows(parent / "displayed_comparisons.jsonl"))
    displays = list(v2.display_rows(parent_bouts, versions, names))
    if any({k: old[k] for k in new if k != "v4"} != {k: v for k, v in new.items() if k != "v4"}
           for old, new in zip(parent_bouts, displays, strict=True)):
        raise ValueError("Saved v3 pre-fight badge evidence did not reproduce.")
    records = {key: v2.display_result(displays, key) for key in versions}
    if records["v3"] != original["track_record"] or verified_parent.evaluation["track_record"] != records["v3"]:
        raise ValueError("Saved v3 track record did not reproduce.")
    common = [row for row in displays
              if all(None not in row[key]["grades"] and len(set(row[key]["grades"])) == 2 for key in versions)]
    common_scores = {key: v2.display_result(common, key) for key in versions}

    latest = {uid: {row["fighter_id"]: row for row in rows} for uid, rows in versions.items()}
    recent = {
        key: {uid: row for uid, row in snapshot.items() if row["event_date"] >= v3.RECENT}
        for key, snapshot in latest.items()
    }
    if recent["v3"].keys() != recent["v4"].keys() or len(recent["v3"]) != original["recent"]["fighters"]:
        raise ValueError("The recent fighter cohort differs from the saved v3 release.")
    fields = ("event_date", "raw_combined", "curve_score", "score", "peak", "change",
              "change_adjustment", "outcome_hold")
    cases = {names[uid]: {key: {k: rows[uid][k] for k in fields} for key, rows in latest.items()}
             for uid in latest["v4"] if names[uid] in EXAMPLES}
    pereira = [{key: {k: row[k] for k in fields} for key, row in zip(versions, (old, new), strict=True)}
               for old, new in zip(old_rows, new_rows, strict=True)
               if names[old["fighter_id"]] == "Michel Pereira"
               and "2024-03-01" <= old["event_date"] <= "2024-05-04"]
    evaluation = {
        "version": serving_v4.VERSION, "evaluation_label": original["evaluation_label"],
        "engineering_checks_passed": preserved and prefix_ok,
        "engineering": {"v3_reproduced": True, "same_model_fields": preserved, "prefix_reproduced": prefix_ok,
                        "fighter_dates": len(new_rows), "fighters": len(latest["v4"]),
                        "decisive_comparison_bouts": len(displays)},
        "candidate": original["candidate"], "track_record": records["v4"], "display_records": records,
        "common_display": {"bouts": len(common), "accuracy_difference":
                           common_scores["v4"]["accuracy"] - common_scores["v3"]["accuracy"] if common else None,
                           **common_scores},
        "recent": {**original["recent"], "v4": v3.summarize_recent(recent["v4"])},
        "policy": v2.policy(new_rows, names), "v3_policy": v2.policy(old_rows, names),
        "modest_changes_near_upper_bands": upper_band_changes(old_rows, new_rows),
        "all_99_fighters": sorted({names[row["fighter_id"]] for row in new_rows if row["score"] == 99}),
        "cases": cases, "pereira_example": pereira,
    }
    evaluation["serving_eligible"] = serving_v4.passes_gate(evaluation)
    files = {"ratings.jsonl": v3.jsonl(new_rows), "evaluation.json": encoded(evaluation),
             "displayed_comparisons.jsonl": v3.jsonl(displays), "protocol.md": protocol.read_text()}
    metadata.update({"input_sha256": hashes, "output_sha256": {
        name: hashlib.sha256(body.encode()).hexdigest() for name, body in files.items()}})
    verify_hashes(hashes)
    files["manifest.json"] = encoded(metadata)
    write_artifact(output, files)
    return evaluation


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("database", "baseline", "parent", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--protocol", type=Path, default=Path("docs/OVERALL_RATING_PROTOCOL_V4.md"))
    args = parser.parse_args()
    result = build(args.database, args.baseline, args.parent, args.protocol, args.output)
    print(encoded({k: result[k] for k in ("serving_eligible", "common_display", "modest_changes_near_upper_bands")}))


if __name__ == "__main__":
    main()
