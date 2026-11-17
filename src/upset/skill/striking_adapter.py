"""Immutable, paired significant-striking observations from reviewed serving data."""

import argparse
import hashlib
import json
import re
import sqlite3
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory

from upset.data.identity import load_fighter_registry, validate_upset_fighter_id

VERSION = "significant_striking_sides_v1"
PROVIDERS = {"kaggle_ufc_1994_2026": "ufcstats", "kaggle": "ufcstats", "cito": "cito"}
DIVISIONS = {"Strawweight", "Flyweight", "Bantamweight", "Featherweight",
             "Lightweight", "Welterweight", "Middleweight", "Light Heavyweight",
             "Heavyweight"}


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def encoded(value):
    return json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n"


def iso_date(value):
    if not isinstance(value, str) or date.fromisoformat(value).isoformat() != value:
        raise ValueError("Use an ISO calendar date.")
    return value


def division(label):
    text = " ".join(re.sub(r"\b(UFC|Interim|Title|Bout)\b", " ", label or "").split())
    return text if text.removeprefix("Women's ") in DIVISIONS else None


def measurement(landed, attempts, seconds):
    """Retain true zero exposure, with independent count and duration eligibility."""
    if landed is None or attempts is None:
        status = "missing_counts"
    elif type(landed) is not int or type(attempts) is not int or not 0 <= landed <= attempts:
        status = "invalid_counts"
    elif seconds == 0 and attempts > 0:
        status = "positive_attempts_zero_duration"
    else:
        status = "observed" if attempts else "zero_attempts"
    usable = status in ("observed", "zero_attempts")
    return {"status": status, "landed": landed if usable else None,
            "attempts": attempts if usable else None,
            "observed_accuracy": landed / attempts if usable and attempts else None,
            "landed_per_minute": 60 * landed / seconds
            if usable and seconds is not None and seconds > 0 else None}


def paired_sides(fight_id, fight, stats, database_hash):
    participants = [fight[f"upset_fighter_{i}_id"] for i in (1, 2)]
    if len(set(participants)) != 2 or set(stats) != set(participants):
        raise ValueError("Exactly two matching permanent participants are required.")
    for uid in participants:
        validate_upset_fighter_id(uid)
    if fight_id != fight["source"] + ":" + fight["source_bout_id"]:
        raise ValueError("Fight key and provider identity disagree.")
    day = iso_date(fight["event_date"])
    durations = [stats[uid].get("fight_duration_seconds") for uid in participants]
    if (any(s is not None and (type(s) is not int or s < 0) for s in durations)
            or durations[0] != durations[1]):
        raise ValueError("Paired durations must be nonnegative integers or matching nulls.")
    for i, uid in enumerate(participants, 1):
        row = stats[uid]
        if (row["upset_fighter_id"] != uid or row["source"] != fight["source"]
                or row["source_bout_id"] != fight["source_bout_id"]
                or row["source_fighter_id"] != fight[f"source_fighter_{i}_id"]):
            raise ValueError("Statistics and provider participant identities disagree.")
    provenance = hashlib.sha256(json.dumps(
        {"fight": fight, "stats": stats}, sort_keys=True, allow_nan=False).encode()).hexdigest()
    result = []
    for i, uid in enumerate(participants):
        opponent = participants[1-i]
        raw = {label: {"landed": stats[key].get("sig_strikes_landed"),
                       "attempts": stats[key].get("sig_strikes_attempted")}
               for label, key in (("own", uid), ("opponent", opponent))}
        own = measurement(**raw["own"], seconds=durations[0])
        opposing = measurement(**raw["opponent"], seconds=durations[0])
        event = fight.get("source_event_id")
        result.append({
            "adapter_version": VERSION, "fight_id": fight_id, "fighter_id": uid,
            "opponent_id": opponent, "event_date": day,
            "event_id": fight["source"] + ":" + str(event or day),
            "event_id_basis": "provider_event_id" if event else "source_date_fallback",
            "division": division(fight.get("weight_class")),
            "duration_seconds": durations[0],
            "duration_status": "missing" if durations[0] is None else
            "zero" if durations[0] == 0 else "positive",
            "short_fight": durations[0] is not None and 0 < durations[0] < 60,
            "raw_counts": raw, **own,
            "opponent_landed": opposing["landed"],
            "opponent_attempts": opposing["attempts"],
            "opponent_status": opposing["status"],
            "source": fight["source"], "source_bout_id": fight["source_bout_id"],
            "source_fighter_id": stats[uid]["source_fighter_id"],
            "opponent_source_fighter_id": stats[opponent]["source_fighter_id"],
            "source_url": fight.get("source_url"), "database_sha256": database_hash,
            "source_rows_sha256": provenance,
        })
    return result


def audit_rows(rows, before, database_hash):
    iso_date(before)
    by_fight = defaultdict(list)
    seen = set()
    for row in rows:
        key = row["fight_id"], row["fighter_id"]
        if key in seen:
            raise ValueError("Duplicate side observation.")
        seen.add(key)
        for uid in (row["fighter_id"], row["opponent_id"]):
            validate_upset_fighter_id(uid)
        if (row["adapter_version"] != VERSION or row["database_sha256"] != database_hash
                or iso_date(row["event_date"]) >= before
                or row["fighter_id"] == row["opponent_id"]
                or row["fight_id"] != row["source"] + ":" + row["source_bout_id"]):
            raise ValueError("Adapter identity, cutoff or provenance mismatch.")
        seconds = row["duration_seconds"]
        if seconds is not None and (type(seconds) is not int or seconds < 0):
            raise ValueError("Invalid duration.")
        expected_duration = "missing" if seconds is None else "zero" if seconds == 0 else "positive"
        if (row["duration_status"] != expected_duration
                or row["short_fight"] != (seconds is not None and 0 < seconds < 60)):
            raise ValueError("Duration flags disagree.")
        own = measurement(**row["raw_counts"]["own"], seconds=seconds)
        opposing = measurement(**row["raw_counts"]["opponent"], seconds=seconds)
        if (any(row[k] != value for k, value in own.items())
                or row["opponent_status"] != opposing["status"]
                or row["opponent_landed"] != opposing["landed"]
                or row["opponent_attempts"] != opposing["attempts"]):
            raise ValueError("Raw counts and derived measurements disagree.")
        by_fight[row["fight_id"]].append(row)
    for pair in by_fight.values():
        if len(pair) != 2:
            raise ValueError("Missing paired side.")
        a, b = pair
        if (a["fighter_id"] != b["opponent_id"] or b["fighter_id"] != a["opponent_id"]
                or a["source_fighter_id"] != b["opponent_source_fighter_id"]
                or b["source_fighter_id"] != a["opponent_source_fighter_id"]
                or a["raw_counts"]["own"] != b["raw_counts"]["opponent"]
                or b["raw_counts"]["own"] != a["raw_counts"]["opponent"]
                or any(a[k] != b[k] for k in (
                    "event_date", "event_id", "event_id_basis", "division",
                    "duration_seconds", "source_rows_sha256", "source_url"))):
            raise ValueError("Paired side identities, counts or metadata disagree.")


def verify_hashes(hashes):
    if any(digest(path) != expected for path, expected in hashes.items()):
        raise ValueError("An input changed or its hash differs.")


def read_sides(database, registry_path, before):
    iso_date(before)
    paths = [database, database.parent / "manifest.json", registry_path,
             Path(__file__), Path(__file__).parents[1] / "data/identity.py"]
    hashes = {str(p.resolve()): digest(p) for p in paths}
    database_hash = hashes[str(database.resolve())]
    manifest = json.loads((database.parent / "manifest.json").read_text())
    if manifest["database_sha256"] != database_hash:
        raise ValueError("Serving database hash differs from its manifest.")
    bound_registry = {str(Path(p).resolve()): h for p, h in manifest["input_sha256"].items()}
    if bound_registry.get(str(registry_path.resolve())) != digest(registry_path):
        raise ValueError("Registry is not bound to the serving manifest.")
    registry = load_fighter_registry(registry_path)
    links = {(link.provider, link.provider_fighter_id): link.upset_fighter_id
             for link in registry.provider_links}
    observations = []
    with sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True) as db:
        if (db.execute("PRAGMA quick_check").fetchone()[0] != "ok"
                or db.execute("PRAGMA foreign_key_check").fetchall()):
            raise ValueError("Database integrity check failed.")
        excluded = db.execute("SELECT count(*) FROM fights WHERE event_date>=?", (before,)).fetchone()[0]
        for fid, a, b, day, payload in db.execute(
                "SELECT id,fighter_1,fighter_2,event_date,payload FROM fights "
                "WHERE event_date<? ORDER BY event_date,id", (before,)):
            fight = json.loads(payload)
            if ((a, b) != (fight["upset_fighter_1_id"], fight["upset_fighter_2_id"])
                    or day != fight["event_date"]):
                raise ValueError("Stored fight columns differ from payload.")
            saved = db.execute("SELECT fighter_id,payload FROM stats WHERE fight_id=?", (fid,)).fetchall()
            if len(saved) != 2 or len({uid for uid, _ in saved}) != 2:
                raise ValueError("Missing or duplicate paired statistics.")
            stats = {uid: json.loads(p) for uid, p in saved}
            provider = PROVIDERS.get(fight["source"])
            if provider is None or any(
                    links.get((provider, row["source_fighter_id"])) != uid
                    for uid, row in stats.items()):
                raise ValueError("Provider link disagrees with reviewed registry.")
            observations.extend(paired_sides(fid, fight, stats, database_hash))
    audit_rows(observations, before, database_hash)
    verify_hashes(hashes)
    return observations, hashes, excluded


def write_artifact(output, files):
    if output.exists():
        raise ValueError("Use a new immutable output directory.")
    output.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=output.parent, prefix=".upset-striking-") as temporary:
        folder = Path(temporary) / "artifact"
        folder.mkdir()
        for name, contents in files.items():
            (folder / name).write_text(contents)
            if (folder / name).read_text() != contents:
                raise ValueError("Artifact read-back verification failed.")
        if output.exists():
            raise ValueError("Use a new immutable output directory.")
        folder.rename(output)


def export(database, registry, before, output):
    if output.exists() or output.resolve().is_relative_to(database.parent.resolve()):
        raise ValueError("Use a new output separate from the serving snapshot.")
    rows, hashes, excluded = read_sides(database, registry, before)
    body = "".join(json.dumps(r, sort_keys=True, allow_nan=False) + "\n" for r in rows)
    summary = {"adapter_version": VERSION, "before_exclusive": before,
               "input_database": str(database.resolve()), "registry": str(registry.resolve()),
               "database_sha256": digest(database), "input_sha256": hashes,
               "side_rows": len(rows), "fights": len(rows) // 2,
               "latest_event": max((r["event_date"] for r in rows), default=None),
               "excluded_fights_on_or_after_cutoff": excluded,
               "statuses": dict(Counter(r["status"] for r in rows)),
               "duration_statuses": dict(Counter(r["duration_status"] for r in rows)),
               "short_fight_sides": sum(r["short_fight"] for r in rows),
               "total_observed_landed": sum(r["landed"] or 0 for r in rows),
               "total_observed_attempts": sum(r["attempts"] or 0 for r in rows),
               "by_source_status": {source: dict(Counter(r["status"] for r in rows
                                                         if r["source"] == source))
                                    for source in sorted({r["source"] for r in rows})},
               "unknown_division_sides": sum(r["division"] is None for r in rows),
               "date_clusters": len({r["event_date"] for r in rows}),
               "coverage_verified": False, "public_release": False,
               "opponent_adjusted": False,
               "output_sha256": {"sides.jsonl": hashlib.sha256(body.encode()).hexdigest()}}
    verify_hashes(hashes)
    write_artifact(output, {"sides.jsonl": body, "manifest.json": encoded(summary)})
    return summary


def load_adapter(folder):
    manifest_path, sides_path = folder / "manifest.json", folder / "sides.jsonl"
    manifest = json.loads(manifest_path.read_text())
    body = sides_path.read_bytes()
    if (manifest["adapter_version"] != VERSION
            or hashlib.sha256(body).hexdigest() != manifest["output_sha256"]["sides.jsonl"]):
        raise ValueError("Adapter version or output hash differs.")
    verify_hashes(manifest["input_sha256"])
    if digest(manifest["input_database"]) != manifest["database_sha256"]:
        raise ValueError("Adapter database provenance differs.")
    rows = [json.loads(line) for line in body.splitlines()]
    if len(rows) != manifest["side_rows"] or len(rows) != 2 * manifest["fights"]:
        raise ValueError("Adapter row count differs.")
    audit_rows(rows, manifest["before_exclusive"], manifest["database_sha256"])
    hashes = {str(p.resolve()): digest(p) for p in (manifest_path, sides_path)}
    return rows, manifest, {**manifest["input_sha256"], **hashes}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--registry", type=Path, required=True)
    parser.add_argument("--before", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(encoded(export(args.database, args.registry, args.before, args.output)))


if __name__ == "__main__":
    main()
