"""Read-only audit of striking counts and accepted cached round coverage."""

import argparse
import json
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path

from upset.skill.takedown_defense import digest

MARGINS = (("head", "body", "leg"), ("distance", "clinch", "ground"))


def valid_pair(landed, attempted):
    return type(landed) is int and type(attempted) is int and 0 <= landed <= attempted


def audit(database, rounds_path, cohort_manifest):
    serving_manifest = database.parent / "manifest.json"
    paths = (database, serving_manifest, rounds_path, cohort_manifest, Path(__file__))
    hashes = {str(p): digest(p) for p in paths}
    if json.loads(serving_manifest.read_text())["database_sha256"] != hashes[str(database)]:
        raise ValueError("Serving snapshot hash mismatch.")
    cohort = json.loads(cohort_manifest.read_text())
    if cohort["output_sha256"][rounds_path.name] != hashes[str(rounds_path)]:
        raise ValueError("Cached rounds hash mismatch.")
    stats, fights = {}, {}
    with sqlite3.connect(database.resolve().as_uri()+"?mode=ro", uri=True) as db:
        if db.execute("PRAGMA quick_check").fetchone()[0] != "ok":
            raise ValueError("Database integrity failed.")
        for key, payload in db.execute("SELECT id,payload FROM fights"):
            fights[key] = json.loads(payload)
        for fid, uid, payload in db.execute("SELECT fight_id,fighter_id,payload FROM stats"):
            row = json.loads(payload)
            if uid != row["upset_fighter_id"] or fid != row["source"]+":"+row["source_bout_id"]:
                raise ValueError("Statistics identity mismatch.")
            stats[fid, uid] = row
    by_fight = defaultdict(dict)
    for (fid, uid), row in stats.items():
        by_fight[fid][uid] = row
    if set(by_fight) != set(fights):
        raise ValueError("Fight/statistics set mismatch.")
    structural = Counter()
    availability = Counter()
    by_source = defaultdict(Counter)
    for fid, fight in fights.items():
        pair = by_fight[fid]
        participants = [fight["upset_fighter_1_id"], fight["upset_fighter_2_id"]]
        if len(pair) != 2 or set(pair) != set(participants):
            raise ValueError("Broken paired permanent identities.")
        durations = [r.get("fight_duration_seconds") for r in pair.values()]
        structural["duration_disagreement_fights"] += durations[0] != durations[1]
        for side, uid in enumerate(participants, 1):
            row = pair[uid]
            if row["source_fighter_id"] != fight[f"source_fighter_{side}_id"]:
                raise ValueError("Provider participant mismatch.")
            landed, attempted = row.get("sig_strikes_landed"), row.get("sig_strikes_attempted")
            valid = valid_pair(landed, attempted)
            seconds = row.get("fight_duration_seconds")
            positive_time = type(seconds) is int and seconds > 0
            flags = {"sides": True, "valid_total_counts": valid,
                     "positive_duration": positive_time,
                     "A1_count_time_available": valid and positive_time,
                     "A2_positive_attempts": valid and attempted > 0,
                     "A2_zero_attempts": valid and attempted == 0,
                     "duration_under_60_seconds": positive_time and seconds < 60,
                     "control_missing": row.get("control_seconds") is None,
                     "all_margin_attempts_present": all(type(row.get(f"{part}_attempted")) is int
                                                         for parts in MARGINS for part in parts)}
            for label, flag in flags.items():
                availability[label] += bool(flag)
                by_source[row["source"]][label] += bool(flag)
            for parts in MARGINS:
                label = "target" if parts[0] == "head" else "position"
                values = [row.get(f"{part}_landed") for part in parts]
                structural[label+"_landed_missing_sides"] += any(type(v) is not int or v < 0 for v in values)
                if all(type(v) is int and v >= 0 for v in values) and valid:
                    structural[label+"_landed_sum_mismatch_sides"] += sum(values) != landed
    rounds = [json.loads(line) for line in rounds_path.read_text().splitlines()]
    grouped = defaultdict(list)
    for row in rounds:
        grouped["cito:"+row["source_bout_id"]].append(row)
    round_report = {"cached_round_rows": len(rounds), "cached_bouts": len(grouped),
                    "accepted_bouts_with_rounds": 0, "accepted_round_rows": 0,
                    "complete_reconciled_bouts": 0, "complete_reconciled_sides": 0,
                    "cached_bouts_outside_serving": len(set(grouped)-set(fights)), "issues": []}
    for fid in sorted(set(grouped) & set(fights)):
        records, fight, issues = grouped[fid], fights[fid], []
        round_report["accepted_bouts_with_rounds"] += 1
        round_report["accepted_round_rows"] += len(records)
        expected_rounds = set(range(1, fight["result_round"]+1))
        for uid, total in by_fight[fid].items():
            own = [r for r in records if r.get("upset_fighter_id") == uid]
            if (len(own) != len(expected_rounds)
                    or {r["round_number"] for r in own} != expected_rounds
                    or any(r.get("source_fighter_id") != total["source_fighter_id"] for r in own)):
                issues.append("participant_or_round_completeness")
                continue
            for row in own:
                for prefix in ("sig_strikes", *(part for parts in MARGINS for part in parts)):
                    if not valid_pair(row.get(prefix+"_landed"), row.get(prefix+"_attempted")):
                        issues.append("invalid_round_count")
                for parts in MARGINS:
                    for suffix in ("landed", "attempted"):
                        if sum(row.get(f"{part}_{suffix}", -1) for part in parts) != row.get("sig_strikes_"+suffix):
                            issues.append("round_margin_reconciliation")
            for field in ("sig_strikes_landed", "sig_strikes_attempted",
                          *(part+"_landed" for parts in MARGINS for part in parts)):
                if sum(row[field] for row in own) != total[field]:
                    issues.append("round_sum_vs_serving_total")
        if len(records) != 2*len(expected_rounds):
            issues.append("unexpected_round_row_count")
        if issues:
            round_report["issues"].append({"fight_id": fid, "reasons": sorted(set(issues))})
        else:
            round_report["complete_reconciled_bouts"] += 1
            round_report["complete_reconciled_sides"] += 2
    if any(digest(Path(p)) != value for p, value in hashes.items()):
        raise ValueError("An audited input changed while reading.")
    return {"audit": "striking_availability_v1", "input_sha256": hashes,
            "fights": len(fights), "side_rows": len(stats),
            "latest_event": max(f["event_date"] for f in fights.values()),
            "availability": dict(availability), "by_source": {key: dict(value) for key, value in by_source.items()},
            "structural_diagnostics": dict(structural), "round_coverage": round_report,
            "coverage_verified": False, "fitted_model": False, "public_release": False,
            "interpretation": "Counts are available for total striking. Component attempts require a separately versioned, reconciled round aggregation; clocks and joint position-by-target counts are not observed."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--rounds", type=Path, required=True)
    parser.add_argument("--cohort-manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError("Use a new audit output; existing artifacts are immutable.")
    report = audit(args.database, args.rounds, args.cohort_manifest)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x") as saved:
        saved.write(json.dumps(report, indent=2, sort_keys=True)+"\n")
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
