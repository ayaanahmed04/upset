"""Bind reviewed results without statistics to existing permanent fighter IDs."""

import argparse
import hashlib
import json
import re
import sqlite3
from collections import defaultdict
from contextlib import closing
from datetime import date
from pathlib import Path

from upset.data.audit_cito_archive import _name
from upset.data.identity import validate_upset_fighter_id
from upset.skill.striking_adapter import digest, encoded, verify_hashes, write_artifact

EVENT = re.compile(r"https://www\.ufc\.com/event/([a-z0-9-]+)")
CLOCK = re.compile(r"\d{1,2}:[0-5][0-9]")


def official_indexes(db, source):
    if source["schema_version"] != 1:
        raise ValueError("Unsupported historical-results format.")
    earliest = db.execute("SELECT MIN(event_date) FROM fights").fetchone()[0]
    names = {uid: (name, json.loads(profile)["source_fighter_id"])
             for uid, name, profile in db.execute("SELECT id,name,profile FROM fighters")}
    events, bouts, by_fighter = {}, {}, defaultdict(list)
    for original in source["events"]:
        slug, day = original["slug"], original["date"]
        url = EVENT.fullmatch(original["source_url"])
        if (slug in events or url is None or url[1] != slug or date.fromisoformat(day).isoformat() != day
                or earliest is None or day >= earliest):
            raise ValueError("A historical card must predate the paired statistics archive and match its source.")
        rows = []
        for order, item in enumerate(original["bouts"], 1):
            key = item["id"]
            if (key != f"ufc:{slug}:{order}" or key in bouts or item["order"] != order
                    or item["round"] < 1 or not CLOCK.fullmatch(item["time"])):
                raise ValueError("Invalid historical bout key, clock or tournament order.")
            fighters = item["fighters"]
            ids = {side["id"] for side in fighters}
            if len(fighters) != 2 or len(ids) != 2 or item["winner_id"] not in ids:
                raise ValueError("Official results require two fighters and a recorded winner.")
            for side in fighters:
                uid = side["id"]
                validate_upset_fighter_id(uid)
                if uid not in names or (_name(side["name"]), side["source_fighter_id"]) != (
                        _name(names[uid][0]), names[uid][1]):
                    raise ValueError("Official result participant differs from the serving registry.")
            row = {**item, "fighters": [{"name": side["name"], "id": side["id"]} for side in fighters],
                   "date": day, "status": "results_only", "outcome": "decisive",
                   "source_url": original["source_url"], "totals": None, "rounds": [],
                   "event": {field: original[field] for field in ("slug", "name", "headline")}}
            for side, other in (fighters, fighters[::-1]):
                outcome = "win" if side["id"] == item["winner_id"] else "loss"
                by_fighter[side["id"]].append({"fight_id": key, "date": day, "order": order,
                    "opponent_id": other["id"], "opponent": other["name"], "outcome": outcome,
                    "result_type": outcome, "method": item["method"], "result_round": item["round"],
                    "result_time": item["time"], "results_only": True, "source_url": original["source_url"]})
            bouts[key] = row
            rows.append(row)
        events[slug] = {**original, "status": "results_only", "bouts": list(reversed(rows)),
                        "reviewed_bouts": len(rows), "pending_bouts": 0}
    for history in by_fighter.values():
        history.sort(key=lambda row: (row["date"], row["order"]), reverse=True)
    return {"events": events, "bouts": bouts, "by_fighter": dict(by_fighter)}


def load_historical_results(db, folder, database_hash):
    manifest = json.loads((folder / "manifest.json").read_text())
    path = folder / "results.json"
    if manifest["database_sha256"] != database_hash or manifest["results_sha256"] != digest(path):
        raise ValueError("Historical results are bound to another database or differ from their manifest.")
    return official_indexes(db, json.loads(path.read_text()))


def build(source, database, output):
    if output.exists() or output.resolve().is_relative_to(database.parent.resolve()):
        raise ValueError("Use a fresh output outside the serving database folder.")
    hashes = {str(path.resolve()): digest(path) for path in (source, database, Path(__file__))}
    database_hash = hashes[str(database.resolve())]
    if json.loads((database.parent / "manifest.json").read_text())["database_sha256"] != database_hash:
        raise ValueError("Historical results require a verified serving database.")
    body = encoded(json.loads(source.read_text()))
    with closing(sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True)) as db:
        checked = official_indexes(db, json.loads(body))
    verify_hashes(hashes)
    write_artifact(output, {"results.json": body, "manifest.json": encoded({
        "database_sha256": database_hash, "input_sha256": hashes,
        "results_sha256": hashlib.sha256(body.encode()).hexdigest(),
    })})
    print(f"Verified {len(checked['bouts'])} historical results and {len(checked['by_fighter'])} identities.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("source", "database", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    build(args.source, args.database, args.output)


if __name__ == "__main__":
    main()
