"""Dated, evidence-backed championship ledger; ordinary wins never transfer titles.

The packaged seed is a current observation, not reconstructed title history.
Future title results are proposed for review, then replayed by fighter ID.
Run ``python -m upset.championships --help`` for maintenance commands.
"""

import argparse
import json
import os
import sqlite3
import tempfile
from datetime import date, datetime, timedelta
from importlib.resources import files
from pathlib import Path
from urllib.parse import urlsplit
from uuid import UUID

from upset.data.reviewed_bout_metadata import reviewed_title_evidence

DIVISIONS = ("Flyweight", "Bantamweight", "Featherweight", "Lightweight",
             "Welterweight", "Middleweight", "Light Heavyweight", "Heavyweight",
             "Women's Strawweight", "Women's Flyweight", "Women's Bantamweight")
KINDS = ("undisputed", "interim")
LEDGER_PATH = Path("data/champions/champions.json")


def iso(value):
    if not isinstance(value, str) or date.fromisoformat(value).isoformat() != value:
        raise ValueError("Championship dates must be ISO dates.")
    return value


def identity(value):
    if str(UUID(value)) != value:
        raise ValueError("Championship holders must use permanent UPSET UUIDs.")


def sources(value):
    if not isinstance(value, list) or not value:
        raise ValueError("Every championship observation needs source URLs.")
    if any(not isinstance(v, str) or urlsplit(v).scheme != "https"
           or not urlsplit(v).netloc for v in value):
        raise ValueError("Championship sources must be HTTPS URLs.")


def key(row):
    if row.get("division") not in DIVISIONS or row.get("kind") not in KINDS:
        raise ValueError("Unsupported championship division or title kind.")
    return row["division"], row["kind"]


def replay(data, before):
    """Validate the complete ledger, returning only facts effective at cutoff.

    A fight on D becomes effective on D+1, matching the viewer's strict Before
    filter. Administrative decisions have an explicit effective_date.
    """
    iso(before)
    if data.get("schema_version") != 1:
        raise ValueError("Unsupported championship ledger version.")
    snapshot, verified = iso(data["snapshot_date"]), iso(data["verified_at"])
    if verified < snapshot:
        raise ValueError("Verification cannot precede the snapshot.")
    slots, selected, seen = {}, {}, set()
    for row in data["champions"]:
        slot = key(row)
        identity(row["fighter_id"])
        sources(row["sources"])
        if slot in slots:
            raise ValueError("Two holders occupy the same championship slot.")
        slots[slot] = {**row, "verified_at": verified, "effective_date": snapshot,
                       "basis": "verified_snapshot"}
    if before >= snapshot:
        selected = {k: dict(v) for k, v in slots.items()}
    previous = snapshot
    for event in data["events"]:
        slot = key(event)
        effective = iso(event["effective_date"])
        reviewed = iso(event["reviewed_at"])
        sources(event["sources"])
        if effective < previous or reviewed < effective or event.get("reviewed") is not True:
            raise ValueError("Events must be dated, reviewed and in chronological order.")
        previous = effective
        identifier = event["event_id"]
        if not isinstance(identifier, str) or not identifier or identifier in seen:
            raise ValueError("Championship event IDs must be unique.")
        seen.add(identifier)
        current = slots.get(slot)
        expected = current["fighter_id"] if current else None
        if event.get("previous_fighter_id") != expected:
            raise ValueError("Championship event does not match the prior holder.")
        action = event["action"]
        if action in ("award", "retain", "unify", "non_title"):
            identity(event["fighter_id"])
            identity(event["opponent_id"])
            if event["fighter_id"] == event["opponent_id"]:
                raise ValueError("A fighter cannot meet themselves.")
            if not event.get("fight_id") or (action != "non_title" and event.get("title_confirmed") is not True):
                raise ValueError("Fight-based changes require confirmed title and fight ID.")
            if action == "non_title" and event.get("title_confirmed") is not False:
                raise ValueError("Non-title review must explicitly confirm no title was at stake.")
            if iso(event["fight_date"]) != (date.fromisoformat(effective) - timedelta(days=1)).isoformat():
                raise ValueError("Fight events take effect the day after the fight.")
            if expected and expected not in (event["fighter_id"], event["opponent_id"]):
                raise ValueError("Title fight does not include its reigning holder.")
            if action == "retain":
                if not current or event["fighter_id"] != expected:
                    raise ValueError("Retention requires the existing holder.")
            elif action != "non_title" and event.get("winner_eligible") is not True:
                raise ValueError("Awarding a belt requires verified winner eligibility.")
            if action == "unify":
                interim = slots.get((event["division"], "interim"))
                if slot[1] != "undisputed" or not interim or interim["fighter_id"] not in (event["fighter_id"], event["opponent_id"]):
                    raise ValueError("Unification requires the interim holder in the fight.")
                del slots[(event["division"], "interim")]
            elif action == "award" and slot[1] == "undisputed" and (event["division"], "interim") in slots:
                raise ValueError("Use unification when an interim title exists.")
            if action != "non_title":
                slots[slot] = {**event, "basis": "reviewed_title_result", "verified_at": reviewed}
        elif action == "vacate":
            if not current:
                raise ValueError("Cannot vacate an empty title slot.")
            del slots[slot]
        elif action == "promote":
            identity(event["fighter_id"])
            interim = slots.get((event["division"], "interim"))
            if slot[1] != "undisputed" or current or not interim or interim["fighter_id"] != event["fighter_id"]:
                raise ValueError("Promotion requires a vacant main title and its interim holder.")
            del slots[(event["division"], "interim")]
            slots[slot] = {**event, "basis": "reviewed_promotion", "verified_at": reviewed}
        else:
            raise ValueError("Unknown championship action.")
        if before >= snapshot and effective <= before:
            selected = {k: dict(v) for k, v in slots.items()}
    return selected


def load(path=None):
    payload = (path.read_bytes() if path is not None else
               files("upset").joinpath("web/champions_seed.json").read_bytes())
    data = json.loads(payload)
    replay(data, date.today().isoformat())
    return data


def title_division(fight):
    label = fight.get("weight_class") or ""
    if "BMF" in label.upper():
        return None
    evidence = reviewed_title_evidence(fight)
    if "Title" not in label and evidence is None:
        return None
    for token in ("UFC ", "Interim ", " Title Bout", " Title", " Bout"):
        label = label.replace(token, "")
    return label if label in DIVISIONS else None


def result(fight):
    amended = fight.get("reviewed_result")
    winner = amended["winner_name"] if amended else fight.get("winner_name")
    found = next((fight[f"upset_fighter_{side}_id"] for side in (1, 2)
                  if winner and winner == fight[f"fighter_{side}_name"]), None)
    if winner is not None and found is None:
        raise ValueError("Stored championship winner is not one of the participants.")
    return found


def verify_fight(db, event):
    record = db.execute("SELECT payload FROM fights WHERE id=?", (event["fight_id"],)).fetchone()
    if record is None:
        raise ValueError("Reviewed championship fight is missing from the database.")
    fight = json.loads(record[0])
    ids = {fight["upset_fighter_1_id"], fight["upset_fighter_2_id"]}
    if fight["event_date"] != event["fight_date"] or ids != {event["fighter_id"], event["opponent_id"]}:
        raise ValueError("Reviewed title result differs from the dated matchup.")
    # An explicit official review can recover absent source title labels, but
    # cannot reassign a known different division or turn BMF into divisional gold.
    label = fight.get("weight_class") or ""
    clean = label
    for token in ("UFC ", "Interim ", " Title Bout", " Title", " Bout"):
        clean = clean.replace(token, "")
    if "BMF" in label.upper() or clean != event["division"]:
        raise ValueError("Reviewed title result differs from the fight division.")
    winner = result(fight)
    expected = event.get("winner_id")
    if winner != expected:
        raise ValueError("Stored winner differs from the reviewed championship result.")
    if event["action"] in ("award", "unify") and winner != event["fighter_id"]:
        raise ValueError("A belt can only be awarded to the recorded winner.")
    if event["action"] == "retain" and winner not in (None, event["fighter_id"]):
        raise ValueError("A defeated champion cannot retain through a normal title result.")
    return fight


def scan(db, ledger, before):
    """Find newer title results; proposals cannot silently become approved facts."""
    iso(before)
    handled = {e.get("fight_id") for e in ledger["events"] if e.get("fight_id")}
    proposals = []
    for row in db.execute("SELECT id,payload FROM fights WHERE event_date>=? AND event_date<? ORDER BY event_date,id",
                          (ledger["snapshot_date"], before)):
        fight = json.loads(row[1])
        division = title_division(fight)
        if row[0] in handled or "BMF" in (fight.get("weight_class") or "").upper():
            continue
        confirmed_label = division is not None
        prior_slots = replay(ledger, fight["event_date"])
        ids = (fight["upset_fighter_1_id"], fight["upset_fighter_2_id"])
        if not division:
            # Cito sometimes drops title labels. A new incumbent bout is a
            # review candidate even when its label provides no title evidence.
            label = fight.get("weight_class") or ""
            for token in ("UFC ", "Interim ", " Title Bout", " Title", " Bout"):
                label = label.replace(token, "")
            matches = [slot for slot, holder in prior_slots.items()
                       if slot[0] == label and holder["fighter_id"] in ids]
            if not matches:
                continue
            division = matches[0][0]
        kind = "interim" if "Interim" in (fight.get("weight_class") or "") else "undisputed"
        if not confirmed_label:
            kind = next(slot[1] for slot, holder in prior_slots.items()
                        if slot[0] == division and holder["fighter_id"] in ids)
        effective = (date.fromisoformat(fight["event_date"]) + timedelta(days=1)).isoformat()
        prior = prior_slots.get((division, kind))
        holder = prior["fighter_id"] if prior else None
        winner = result(fight)
        fighter = winner or holder
        opponent = next((uid for uid in ids if uid != fighter), None)
        action = ("award" if winner else "retain") if confirmed_label else "review"
        proposals.append({"event_id": "fight:" + row[0], "action": action,
                          "division": division, "kind": kind, "fight_id": row[0],
                          "fight_date": fight["event_date"], "effective_date": effective,
                          "fighter_id": fighter, "opponent_id": opponent, "winner_id": winner,
                          "previous_fighter_id": holder, "reviewed": False,
                          "reviewed_at": None, "title_confirmed": False, "winner_eligible": None,
                          "sources": [fight["source_url"]] if fight.get("source_url") else [],
                          "note": "Verify official title type, result and eligibility before applying. Use non_title for a confirmed ordinary bout. Review in date order."})
    return proposals


def status(db, ledger, uid, before):
    slots = replay(ledger, before)
    problems = []
    for event in ledger["events"]:
        if event.get("fight_id") and event["effective_date"] <= before:
            try:
                verify_fight(db, event)
            except ValueError as error:
                problems.append({"division": event["division"], "reason": str(error)})
    pending = scan(db, ledger, before)
    blocked = {p["division"] for p in problems + pending}
    titles = []
    for (division, kind), row in slots.items():
        if row["fighter_id"] == uid and division not in blocked:
            slug = division.removeprefix("Women's ").lower().replace(" ", "-")
            titles.append({"division": division, "kind": kind,
                           "label": "Interim champion" if kind == "interim" else "Champion",
                           "belt_url": f"/assets/belt-{slug}.png",
                           "verified_at": row["verified_at"], "sources": row["sources"],
                           "basis": row["basis"]})
    return {"titles": titles, "snapshot_date": ledger["snapshot_date"],
            "historical_coverage": before >= ledger["snapshot_date"],
            "pending_review": bool(blocked), "pending_divisions": sorted(blocked)}


def default_path():
    return Path("data/champions/champions.json")


def report(database, fighter):
    """Read the latest approved ledger on each request; no server restart needed."""
    ledger = load(LEDGER_PATH if LEDGER_PATH.is_file() else None)
    with sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True) as db:
        return status(db, ledger, fighter["id"], fighter["before"])


def append_review(path, database, event):
    original = path.read_bytes()
    ledger = json.loads(original)
    candidate = {**ledger, "events": ledger["events"] + [event]}
    replay(candidate, date.today().isoformat())
    with sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True) as db:
        if event.get("fight_id"):
            verify_fight(db, event)
        for row in candidate["champions"] + [e for e in candidate["events"] if e.get("fighter_id")]:
            if db.execute("SELECT 1 FROM fighters WHERE id=?", (row["fighter_id"],)).fetchone() is None:
                raise ValueError("Championship holder is not in this database.")
    backup = path.with_name(path.name + "." + datetime.now().strftime("%Y%m%d-%H%M%S-%f") + ".bak")
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix="champions-")
    try:
        with os.fdopen(fd, "w") as stream:
            json.dump(candidate, stream, indent=2)
            stream.write("\n")
        if path.read_bytes() != original:
            raise ValueError("Championship ledger changed while reviewing; retry from the new version.")
        backup.write_bytes(original)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return backup


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for command in ("scan", "apply"):
        child = sub.add_parser(command)
        child.add_argument("--database", type=Path, required=True)
        child.add_argument("--ledger", type=Path, default=default_path())
        if command == "scan":
            child.add_argument("--before", default=(date.today() + timedelta(days=1)).isoformat())
        else:
            child.add_argument("--event", type=Path, required=True,
                               help="One reviewed event JSON, not an unreviewed scan output.")
    args = parser.parse_args()
    try:
        if args.command == "scan":
            with sqlite3.connect(args.database.resolve().as_uri() + "?mode=ro", uri=True) as db:
                print(json.dumps(scan(db, load(args.ledger), args.before), indent=2))
        else:
            backup = append_review(args.ledger, args.database, json.loads(args.event.read_bytes()))
            print("Applied reviewed championship event. Backup: " + str(backup))
    except (OSError, ValueError, KeyError, TypeError, sqlite3.Error) as error:
        parser.exit(1, str(error) + "\n")


if __name__ == "__main__":
    main()
