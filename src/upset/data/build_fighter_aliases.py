"""Search aliases: nicknames and alternate spellings from archived Cito profiles, plus a
short reviewed list of former names. Display/search metadata only.

A provider fighter is tied to an UPSET fighter only through a fight both sources agree on
(same UFCStats bout id) and a name match on at least one corner. Nothing is guessed from a
name alone.
"""

import argparse
import hashlib
import json
import sqlite3
from collections import defaultdict
from contextlib import closing
from pathlib import Path

from upset.data.audit_cito_archive import _name

# Reviewed former names and spellings: (search text, current UPSET name, source).
REVIEWED = (
    ("Sergey Spivak", "Serghei Spivac", "UFC changed the listed spelling; same athlete page"),
    ("Alexey Oleynik", "Aleksei Oleinik", "Alternate transliteration used by UFC broadcasts"),
    ("Mizuki Inoue", "Mizuki", "UFC lists her by first name"),
    ("Joanne Calderwood", "Joanne Wood", "Fought as Joanne Calderwood before the UFC record name change"),
)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def keys(text):
    key = _name(text or "")
    out = {key} if len(key) >= 3 else set()
    if key.startswith("the") and len(key) > 6:
        out.add(key[3:])
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cards", type=Path, default=Path("data/raw/cito_archive/cards"))
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists() and any(args.output.iterdir()):
        raise SystemExit("Output folder already has files; use a new folder.")
    database = args.database.resolve()
    with closing(sqlite3.connect(database.as_uri() + "?mode=ro&immutable=1", uri=True)) as db:
        names = {uid: name for uid, name in db.execute("SELECT id,name FROM fighters")}
        by_bout = defaultdict(list)
        for payload, in db.execute("SELECT payload FROM fights"):
            fight = json.loads(payload)
            by_bout[fight.get("source_bout_id")].append(fight)
    found = defaultdict(lambda: defaultdict(set))  # key -> uid -> kinds
    for path in sorted(args.cards.glob("*/event.json")):
        event = json.loads(path.read_text())["response"]["data"]
        for bout in event.get("bouts") or []:
            for fight in by_bout.get(bout["id"], []):
                ours = {_name(fight[f"fighter_{i}_name"]): fight[f"upset_fighter_{i}_id"] for i in (1, 2)}
                sides = bout.get("fighters") or []
                tied = {}
                for side in sides:
                    profile = side.get("profile") or {}
                    uid = ours.get(_name(side.get("fighterName"))) or ours.get(_name(profile.get("name")))
                    if uid:
                        tied[side["id"]] = uid
                if len(sides) == 2 and len(tied) == 1 and len(set(ours.values())) == 2:
                    other = next(uid for uid in ours.values() if uid not in tied.values())
                    tied[next(side["id"] for side in sides if side["id"] not in tied)] = other
                for side in sides:
                    uid = tied.get(side["id"])
                    if not uid:
                        continue
                    profile = side.get("profile") or {}
                    for kind, text in (("nickname", profile.get("nickname")), ("profile name", profile.get("name")),
                                       ("listed name", side.get("fighterName"))):
                        for key in keys(text):
                            if key != _name(names.get(uid, "")):
                                found[key][uid].add(kind)
    by_name = defaultdict(list)
    for uid, name in names.items():
        by_name[name].append(uid)
    reviewed = []
    for alias, current, note in REVIEWED:
        ids = by_name.get(current, [])
        if len(ids) == 1:
            for key in keys(alias):
                found[key][ids[0]].add("reviewed former name")
            reviewed.append({"alias": alias, "name": current, "note": note})
    index = {key: sorted(uids) for key, uids in found.items()}
    kinds = defaultdict(int)
    for uids in found.values():
        for kind_set in uids.values():
            for kind in kind_set:
                kinds[kind] += 1
    args.output.mkdir(parents=True)
    (args.output / "aliases.json").write_text(json.dumps(index, sort_keys=True, separators=(",", ":")))
    manifest = {"version": "fighter_aliases_v1", "database_sha256": digest(database), "keys": len(index),
                "by_kind": dict(kinds), "reviewed": reviewed,
                "output_sha256": digest(args.output / "aliases.json")}
    (args.output / "manifest.json").write_text(json.dumps(manifest, indent=1))
    print(json.dumps({k: v for k, v in manifest.items() if k != "reviewed"}, indent=1), len(reviewed))


if __name__ == "__main__":
    main()
