"""Create an immutable research snapshot with explicitly reviewed profile fields."""

import argparse
import hashlib
import json
import sqlite3
from contextlib import closing
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory


FIELDS = {"height_inches", "reach_inches", "weight_lbs", "date_of_birth", "stance"}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_only(path):
    return sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)


def apply_profiles(database, review_path, output):
    database, review_path, output = map(Path, (database, review_path, output))
    if output.resolve() == database.parent.resolve():
        raise ValueError("Use a new output folder; the baseline is immutable.")
    review = json.loads(review_path.read_text())
    if review.get("schema_version") != 1 or not review.get("fighters"):
        raise ValueError("Invalid profile review.")
    input_hashes = {"baseline_database": digest(database), "profile_review": digest(review_path)}
    if output.exists():
        manifest = json.loads((output / "manifest.json").read_text())
        if (manifest.get("profile_update_inputs") != input_hashes
                or digest(output / "upset.sqlite") != manifest["database_sha256"]):
            raise ValueError("Existing profile snapshot differs; use a new output folder.")
        return manifest
    with closing(read_only(database)) as source:
        if source.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ValueError("Invalid baseline database.")
        metadata = {k: json.loads(v) for k, v in source.execute("SELECT key,value FROM metadata")}
        revised = {}
        for uid, entry in review["fighters"].items():
            row = source.execute("SELECT name,profile FROM fighters WHERE id=?", (uid,)).fetchone()
            if row is None:
                raise ValueError("Reviewed fighter is absent; install the newcomer identity update first.")
            profile = json.loads(row[1])
            if (profile.get("upset_fighter_id") != uid
                    or profile.get("source") != entry["provider"]
                    or profile.get("source_fighter_id") != entry["provider_fighter_id"]):
                raise ValueError("Reviewed permanent/provider identity mismatch.")
            fields = entry["fields"]
            if set(fields) != FIELDS or set(entry["evidence"]) != FIELDS:
                raise ValueError("Missing field-level review evidence.")
            original = {field: profile.get(field) for field in fields}
            for field, value in fields.items():
                if not entry["evidence"][field].get("sources"):
                    raise ValueError("Missing profile source.")
                if field == "date_of_birth":
                    if date.fromisoformat(value).isoformat() != value:
                        raise ValueError("Invalid birth date.")
                elif field == "stance":
                    if value not in {"Orthodox", "Southpaw", "Switch", "Open Stance"}:
                        raise ValueError("Invalid stance.")
                elif (isinstance(value, bool) or not isinstance(value, (int, float))
                      or not 0 < value < 1000):
                    raise ValueError("Invalid measurement.")
                if original[field] is not None and original[field] != value:
                    raise ValueError("Existing profile conflicts with review; explicit re-review required.")
            profile.update(fields)
            profile["reviewed_profile"] = {"reviewed_on": review["reviewed_on"],
                                           "original_fields": original,
                                           "field_evidence": entry["evidence"]}
            revised[uid] = json.dumps(profile, sort_keys=True)
        output.parent.mkdir(parents=True, exist_ok=True)
        with TemporaryDirectory(dir=output.parent, prefix=".reviewed-profiles-") as tmp:
            folder = Path(tmp) / "snapshot"
            folder.mkdir()
            target = folder / "upset.sqlite"
            with closing(sqlite3.connect(target)) as db:
                source.backup(db)
                with db:
                    db.executemany("UPDATE fighters SET profile=? WHERE id=?",
                                   [(profile, uid) for uid, profile in revised.items()])
                    db.execute("INSERT INTO metadata VALUES (?,?)",
                               ("reviewed_profile_fighters", json.dumps(sorted(revised))))
                if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                    raise ValueError("Updated database integrity check failed.")
                if db.execute("PRAGMA foreign_key_check").fetchall():
                    raise ValueError("Updated database foreign-key check failed.")
                for table in ("fights", "stats"):
                    if set(source.execute("SELECT * FROM " + table)) != set(db.execute("SELECT * FROM " + table)):
                        raise ValueError("Fight or stat rows changed during profile update.")
                old = {row[0]: row for row in source.execute("SELECT * FROM fighters")}
                new = {row[0]: row for row in db.execute("SELECT * FROM fighters")}
                if old.keys() != new.keys() or any(
                    old[uid] != new[uid] for uid in old if uid not in revised
                ) or any(old[uid][:-1] != new[uid][:-1] for uid in revised):
                    raise ValueError("Unreviewed fighter records changed.")
            if digest(database) != input_hashes["baseline_database"] or digest(review_path) != input_hashes["profile_review"]:
                raise ValueError("Inputs changed during profile update.")
            previous_manifest = database.parent / "manifest.json"
            manifest = json.loads(previous_manifest.read_text()) if previous_manifest.exists() else metadata
            manifest = {**manifest, "profile_update_inputs": input_hashes,
                        "reviewed_profile_fighters": sorted(revised),
                        "database_sha256": digest(target)}
            (folder / "profile_review.json").write_text(review_path.read_text())
            (folder / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
            folder.rename(output)
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--review", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    manifest = apply_profiles(args.database, args.review, args.output)
    print("Reviewed profile snapshot:", args.output / "upset.sqlite")
    print("Fighters:", manifest["fighters"], "Fights:", manifest["total_bouts"])


if __name__ == "__main__":
    main()
