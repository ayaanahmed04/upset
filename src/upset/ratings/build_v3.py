"""Regrade verified v2 histories and measure the v3 display candidate."""

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from copy import deepcopy
from datetime import date, timedelta
from itertools import groupby
from pathlib import Path
from statistics import mean

import numpy as np

from upset.ratings import build as v1
from upset.ratings import build_v2 as v2
from upset.ratings import serving_v2, serving_v3
from upset.ratings.engine import normal_score
from upset.skill.striking_adapter import digest, encoded, verify_hashes, write_artifact

START, END = v2.START, v2.END
RECENT = "2025-01-01"
PREFIX = "2024-01-01"


def upper_scale(rows, reference, names):
    peaks = {}
    for row in rows:
        if row["event_date"] < START and row["bouts"] >= 5:
            uid = row["fighter_id"]
            peaks[uid] = max(peaks.get(uid, 0), row["raw_combined"])
    top = sorted(peaks, key=lambda uid: (-peaks[uid], uid))[:3]
    if len(top) < 3:
        raise ValueError("Insufficient historical careers for the upper scale.")
    low = float(np.quantile(reference, .952, method="linear"))
    high = mean(peaks[uid] for uid in top)
    if not low < high:
        raise ValueError("The upper scale requires increasing grade thresholds.")
    return {
        "reference_before": START,
        "reference_moments": len(reference),
        "qualifying_career_peaks": len(peaks),
        "benchmark_peaks": [{"name": names[uid], "score": peaks[uid]} for uid in top],
        "upper_thresholds": np.linspace(low, high, 10).tolist(),
    }


def regrade(rows, metadata):
    previous = {}
    thresholds = metadata["display_curve"]["upper_thresholds"]
    for row in rows:
        uid = row["fighter_id"]
        prior = previous.get(uid)
        grade = serving_v3.grade_for(row["raw_combined"], row["curve_percentile"], thresholds)
        adjustments = serving_v2.display_adjustments(
            grade, row["bouts"], row["last_outcomes"], prior["score"] if prior else None,
        )
        shown = adjustments["score"]
        result = {**row, **adjustments, "curve_score": grade,
                  "peak": max(shown, prior["peak"]) if prior else shown,
                  "change": shown - prior["score"] if prior else None}
        result.pop("curve_unrounded")
        serving_v3.validate_row(result, metadata, prior)
        previous[uid] = result
        yield result


def summarize_recent(latest):
    grades = Counter(row["score"] for row in latest.values())
    return {"at_98": grades[98], "at_least_90": sum(n for g, n in grades.items() if g >= 90),
            "at_least_95": sum(n for g, n in grades.items() if g >= 95),
            "counts": dict(sorted(grades.items()))}


def centered_values(rows):
    latest, states, combined = {}, {}, []
    for day, batch in groupby(rows, key=lambda row: row["event_date"]):
        since = (date.fromisoformat(day) - timedelta(days=730)).isoformat()
        peers = [row["elo"] for row in latest.values() if row["event_date"] >= since]
        center = mean(peers) if len(peers) >= 30 else 1500
        for row in batch:
            uid = row["fighter_id"]
            resume = normal_score((row["elo"] - center) / 200)
            states[uid, day] = resume
            combined.append(.5 * (60 + .39 * resume) + .5 * row["skills_combined"])
            latest[uid] = row
    return states, combined


def era_diagnostic(rows, prefights, v2_evaluation):
    centered, combined = centered_values(rows)
    matched = v1.eligible(prefights)
    adjusted = []
    for original in matched:
        row = deepcopy(original)
        for side, uid in enumerate(row["fighter_ids"]):
            row["parts"][side]["resume"] = centered[uid, row["prior_snapshot_dates"][side]]
        adjusted.append(row)
    fit = v1.fit_slope([row for row in adjusted if "2012-01-01" <= row["event_date"] < START], .5)
    development = [row for row in adjusted if START <= row["event_date"] < END]
    scores, _, _ = v1.score(development, .5, fit["slope"])
    if scores["bouts"] != v2_evaluation["candidate"]["bouts"]:
        raise ValueError("Era experiment changed the matched development support.")
    original_values = [row["raw_combined"] for row in rows]
    dates = [row["event_date"] for row in rows]
    result = {}
    for label, values, metrics in (("v2", original_values, v2_evaluation["candidate"]),
                                    ("centered", combined, scores)):
        threshold = float(np.quantile([x for day, x in zip(dates, values) if day < START], .952))
        periods = defaultdict(list)
        for day, value in zip(dates, values):
            periods["before_2019" if day < START else "2019_onward"].append(value >= threshold)
            periods[day[:4]].append(value >= threshold)
        result[label] = {"threshold": threshold, "candidate": metrics,
                         "shares_above_90_boundary": {key: {"states": len(values), "share": mean(values)}
                                                      for key, values in periods.items()}}
    return result


def jsonl(values):
    return "".join(json.dumps(row, sort_keys=True, allow_nan=False) + "\n" for row in values)


def build(database, before, baseline, protocol, output):
    if output.exists() or output.resolve().is_relative_to(database.parent.resolve()):
        raise ValueError("Use a new output outside the serving database folder.")
    manifest = json.loads((baseline / "manifest.json").read_text())
    if (manifest["version"] != serving_v2.VERSION or digest(database) != manifest["database_sha256"]
            or database.resolve() != Path(manifest["input_database"]).resolve()
            or before < manifest["before_exclusive"]):
        raise ValueError("V3 requires the same frozen v2 database and a compatible cutoff.")
    hashes = dict(manifest["input_sha256"])
    for name, expected in manifest["output_sha256"].items():
        hashes[str((baseline / name).resolve())] = expected
    for path in (Path(__file__), Path(serving_v3.__file__), Path(v2.__file__), protocol, baseline / "manifest.json"):
        hashes[str(path.resolve())] = digest(path)
    verify_hashes(hashes)
    old_evaluation = json.loads((baseline / "evaluation.json").read_text())
    serving_v2._validate_evaluation(old_evaluation)
    rows = list(v2.read_rows(baseline / "ratings.jsonl"))
    prefights = list(v2.read_rows(baseline / "prefights.jsonl"))
    reference = json.loads((baseline / "model.json").read_text())["reference_values"]
    names = manifest["source_metadata"]["fighter_labels"]
    metadata = {key: manifest[key] for key in ("latest_event", "model", "database_sha256")}
    metadata.update({"before_exclusive": before, "display_curve": upper_scale(rows, reference, names)})
    print("Regrading v2 histories with the declared v3 scale.", flush=True)
    new_rows = list(regrade(rows, metadata))
    prefix = [row for row in rows if row["event_date"] < PREFIX]
    prefix_reference = sorted(row["raw_combined"] for row in prefix if row["event_date"] < START)
    prefix_ok = (prefix_reference == reference
                 and upper_scale(prefix, prefix_reference, names) == metadata["display_curve"]
                 and list(regrade(prefix, metadata)) == [row for row in new_rows if row["event_date"] < PREFIX])
    versions = {"v2": rows, "v3": new_rows}
    displays = list(v2.display_rows(prefights, versions, names))
    records = {key: v2.display_result(displays, key) for key in versions}
    if records["v2"] != old_evaluation["track_record"]:
        raise ValueError("The v2 display evidence did not reproduce.")
    common = [row for row in displays
              if all(None not in row[key]["grades"] and len(set(row[key]["grades"])) == 2 for key in versions)]
    common_scores = {key: v2.display_result(common, key) for key in versions}
    difference = common_scores["v3"]["accuracy"] - common_scores["v2"]["accuracy"] if common else None
    latest = {key: {row["fighter_id"]: row for row in values if row["event_date"] >= RECENT}
              for key, values in versions.items()}
    top = sorted(names[uid] for uid in {row["fighter_id"] for row in new_rows if row["score"] == 99})
    cases = {}
    for name in ("Islam Makhachev", "Charles Oliveira", "Francis Ngannou", "Justin Gaethje", "Miguel Baeza", "Grant Dawson"):
        cases[name] = {}
        for key, values in versions.items():
            row = next(row for row in reversed(values) if names[row["fighter_id"]] == name)
            fields = ("event_date", "raw_combined", "curve_score", "score", "change",
                      "change_adjustment", "small_history_adjustment", "outcome_hold")
            cases[name][key] = {field: row[field] for field in fields}
    print("Testing the separate era adjustment on the same matched fights.", flush=True)
    evaluation = {
        "version": serving_v3.VERSION, "engineering_checks_passed": prefix_ok,
        "evaluation_label": old_evaluation["evaluation_label"], "track_record": records["v3"],
        "display_records": records, "candidate": old_evaluation["candidate"],
        "common_display": {"bouts": len(common), "accuracy_difference": difference, **common_scores},
        "recent": {"fighters": len(latest["v3"]), "since": RECENT,
                   **{key: summarize_recent(value) for key, value in latest.items()}},
        "policy": v2.policy(new_rows, names), "all_99_fighters": top, "cases": cases,
        "era_diagnostic": era_diagnostic(rows, prefights, old_evaluation),
    }
    evaluation["serving_eligible"] = serving_v3.passes_gate(evaluation)
    files = {"ratings.jsonl": jsonl(new_rows), "evaluation.json": encoded(evaluation),
             "displayed_comparisons.jsonl": jsonl(displays), "protocol.md": protocol.read_text()}
    metadata.update({"version": serving_v3.VERSION, "experimental": True, "validated": False,
                     "input_database": str(database.resolve()), "input_sha256": hashes,
                     "output_sha256": {name: hashlib.sha256(body.encode()).hexdigest()
                                       for name, body in files.items()}})
    verify_hashes(hashes)
    files["manifest.json"] = encoded(metadata)
    write_artifact(output, files)
    return evaluation


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("database", "baseline", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--before", type=date.fromisoformat, required=True)
    parser.add_argument("--protocol", type=Path, default=Path("docs/OVERALL_RATING_PROTOCOL_V3.md"))
    args = parser.parse_args()
    result = build(args.database, args.before.isoformat(), args.baseline, args.protocol, args.output)
    print(encoded({key: result[key] for key in ("serving_eligible", "common_display", "recent", "cases")}))


if __name__ == "__main__":
    main()
