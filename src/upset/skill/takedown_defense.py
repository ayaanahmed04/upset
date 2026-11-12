"""Export paired takedown-defense observations from a verified serving snapshot."""

import argparse
import hashlib
import json
import sqlite3
from collections import Counter
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory

from upset.data.identity import validate_upset_fighter_id

ADAPTER_VERSION = "takedown_defense_sides_v1"
DIVISIONS = {
    "Strawweight", "Flyweight", "Bantamweight", "Featherweight", "Lightweight",
    "Welterweight", "Middleweight", "Light Heavyweight", "Heavyweight",
}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def division(label):
    import re
    text = " ".join(re.sub(r"\b(UFC|Interim|Title|Bout)\b", " ", label or "").split())
    base = text.removeprefix("Women's ")
    return text if base in DIVISIONS else None


def paired_sides(fight_id, fight, stats, database_sha256):
    """Reject structural identity errors; retain measurement exclusion reasons."""
    own = [fight[f"upset_fighter_{side}_id"] for side in (1, 2)]
    if len(set(own)) != 2 or set(stats) != set(own):
        raise ValueError("A fight requires exactly two matching permanent identities.")
    for uid in own:
        validate_upset_fighter_id(uid)
    if fight_id != fight["source"] + ":" + fight["source_bout_id"]:
        raise ValueError("Fight key differs from its source identity.")
    day = fight["event_date"]
    if date.fromisoformat(day).isoformat() != day:
        raise ValueError("Invalid event date.")
    durations = [stats[uid].get("fight_duration_seconds") for uid in own]
    if any(type(x) is not int or x < 0 for x in durations) or durations[0] != durations[1]:
        raise ValueError("Paired fight durations are invalid or inconsistent.")
    for side, uid in enumerate(own, 1):
        row = stats[uid]
        if (row["upset_fighter_id"] != uid or row["source"] != fight["source"]
                or row["source_bout_id"] != fight["source_bout_id"]
                or row["source_fighter_id"] != fight[f"source_fighter_{side}_id"]):
            raise ValueError("Statistics differ from the participant's provider identity.")
    result = []
    for index, uid in enumerate(own):
        opponent = own[1-index]
        row = stats[opponent]
        landed, attempts = row.get("takedowns_landed"), row.get("takedowns_attempted")
        status = "observed"
        if landed is None or attempts is None:
            status = "missing_opponent_counts"
        elif (type(landed) is not int or type(attempts) is not int
              or landed < 0 or attempts < 0 or landed > attempts):
            status = "invalid_opponent_counts"
        elif durations[0] == 0 and attempts > 0:
            status = "positive_attempts_zero_duration"
        elif attempts == 0:
            status = "zero_attempts"
        available = status in ("observed", "zero_attempts")
        source_event = fight.get("source_event_id")
        result.append({
            "adapter_version": ADAPTER_VERSION, "fight_id": fight_id,
            "fighter_id": uid, "opponent_id": opponent, "event_date": day,
            "event_id": fight["source"] + ":" + str(source_event or day),
            "event_id_basis": "provider_event_id" if source_event else "source_date_fallback",
            "division": division(fight.get("weight_class")),
            "opponent_takedowns_landed": landed if available else None,
            "opponent_takedown_attempts": attempts if available else None,
            "takedowns_stopped": attempts-landed if available else None,
            "observed_defense": (attempts-landed)/attempts if available and attempts else None,
            "status": status, "source": fight["source"],
            "source_bout_id": fight["source_bout_id"],
            "source_fighter_id": fight[f"source_fighter_{index+1}_id"],
            "opponent_source_fighter_id": row["source_fighter_id"],
            "source_url": fight.get("source_url"),
            "database_sha256": database_sha256,
            "source_rows_sha256": hashlib.sha256(json.dumps(
                {"fight": fight, "stats": stats}, sort_keys=True).encode()).hexdigest(),
        })
    return result


def read_sides(database, before):
    if date.fromisoformat(before).isoformat() != before:
        raise ValueError("Use an exclusive ISO cutoff.")
    manifest_path = database.parent / "manifest.json"
    database_hash = digest(database)
    if json.loads(manifest_path.read_text())["database_sha256"] != database_hash:
        raise ValueError("Serving database hash differs from its manifest.")
    observations = []
    with sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True) as db:
        if db.execute("PRAGMA quick_check").fetchone()[0] != "ok" or db.execute("PRAGMA foreign_key_check").fetchall():
            raise ValueError("Serving database integrity check failed.")
        for fid, payload, a, b, stored_day in db.execute(
                "SELECT id,payload,fighter_1,fighter_2,event_date FROM fights WHERE event_date<? ORDER BY event_date,id", (before,)):
            fight = json.loads(payload)
            if (a, b) != (fight["upset_fighter_1_id"], fight["upset_fighter_2_id"]):
                raise ValueError("Database participant columns differ from the payload.")
            if fight["event_date"] != stored_day or fight["event_date"] >= before:
                raise ValueError("Payload cutoff differs from database event date.")
            saved = db.execute("SELECT fighter_id,payload FROM stats WHERE fight_id=?", (fid,)).fetchall()
            if len(saved) != 2:
                raise ValueError("Missing or duplicate paired statistics.")
            observations.extend(paired_sides(fid, fight, {uid: json.loads(p) for uid, p in saved}, database_hash))
    if digest(database) != database_hash:
        raise ValueError("Database changed while reading.")
    return observations, {"database_sha256": database_hash,
                          "serving_manifest_sha256": digest(manifest_path)}


def export(database, before, output):
    if output.exists() or output.resolve().is_relative_to(database.parent.resolve()):
        raise ValueError("Use a new output separate from the serving snapshot.")
    observations, hashes = read_sides(database, before)
    summary = {"adapter_version": ADAPTER_VERSION, "before_exclusive": before,
               "input_database": str(database), "input_sha256": hashes,
               "side_rows": len(observations), "fights": len(observations)//2,
               "statuses": dict(Counter(r["status"] for r in observations)),
               "by_source": dict(Counter(r["source"] for r in observations)),
               "by_year_status": {year: dict(Counter(r["status"] for r in observations if r["event_date"].startswith(year)))
                                  for year in sorted({r["event_date"][:4] for r in observations})},
               "unknown_division_side_rows": sum(r["division"] is None for r in observations),
               "event_date_clusters": len({r["event_date"] for r in observations}),
               "public_release": False, "opponent_adjusted": False}
    output.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=output.parent, prefix=".upset-defense-") as temporary:
        folder = Path(temporary) / "export"
        folder.mkdir()
        path = folder / "sides.jsonl"
        path.write_text("".join(json.dumps(r, sort_keys=True) + "\n" for r in observations))
        summary["output_sha256"] = {"sides.jsonl": digest(path)}
        (folder / "manifest.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
        folder.rename(output)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--before", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(export(args.database, args.before, args.output), indent=2))


if __name__ == "__main__":
    main()
