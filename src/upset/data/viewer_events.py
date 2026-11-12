"""Archived cards and paired fight stats for the local research viewer."""

import json
import re
from collections import defaultdict
from datetime import date
from importlib.resources import files
from pathlib import Path

from upset.data.audit_cito_archive import _name
from upset.data.collect_cito_archive import _digest
from upset.data.reviewed_bout_metadata import result_type, reviewed_title_evidence

CITO_EVENT = re.compile(r"https://api\.citoapi\.com/api/v1/ufc/events/([a-z0-9-]+)/bouts")
ROUND_FIELDS = ("sig_strikes_landed", "sig_strikes_attempted", "takedowns_landed", "takedowns_attempted",
                "knockdowns", "submission_attempts", "control_seconds")
EVENT_NOTES = json.loads(files("upset").joinpath("web/research_events.json").read_text())
SCHEDULE = EVENT_NOTES["scheduled"]


def verified_file(archive, filename, manifest):
    path = archive / filename
    matches = [sha for key, sha in manifest["input_sha256"].items()
               if Path(key).resolve() == path.resolve()]
    if len(matches) != 1 or _digest(path) != matches[0]:
        raise ValueError(f"Event data differs from the reviewed release: {filename}")
    return path


def verified_rows(archive, filename, manifest):
    with verified_file(archive, filename, manifest).open() as stream:
        return [json.loads(line) for line in stream]


def event_name(slug):
    if "ufc-fight-night-" in slug:
        return "UFC Fight Night"
    if slug == "ufc-freedom-250":
        return "UFC Freedom 250"
    numbered = re.search(r"(?:^|-)ufc-(\d+)$", slug)
    return "UFC " + numbered[1] if numbered else slug.replace("-", " ").title()


def source_event_slug(fight):
    match = CITO_EVENT.fullmatch(fight.get("source_url") or "")
    return match[1] if match else None


def title_bout(fight):
    return "Title" in (fight.get("weight_class") or "") or reviewed_title_evidence(fight) is not None


def reviewed_bout(fight, fight_id):
    ids = [fight[f"upset_fighter_{i}_id"] for i in (1, 2)]
    names = [fight[f"fighter_{i}_name"] for i in (1, 2)]
    result = fight.get("reviewed_result") or fight
    winner = result["winner_name"]
    outcome = result_type(fight)[0] if winner is None else "decisive"
    return {"id": fight_id, "date": fight["event_date"],
            "fighters": [{"id": uid, "name": name} for uid, name in zip(ids, names, strict=True)],
            "winner_id": ids[names.index(winner)] if winner is not None else None,
            "outcome": outcome, "method": result.get("result_method"),
            "round": result.get("result_round"), "time": result.get("result_time"),
            "division": fight.get("weight_class"),
            "title": title_bout(fight),
            "amended": fight.get("reviewed_result") is not None, "status": "reviewed"}


def load_event_archive(db, archive, manifest):
    raw = verified_rows(archive, "fights.jsonl", manifest)
    review = json.loads(verified_file(archive, "review.json", manifest).read_text())
    sources = {row["source_bout_id"]: row["source_url"] for row in review.get("november_10_coverage_backfill", [])}
    discrepancies = review.get("pending_result_discrepancies", {})
    accepted = {row["id"]: json.loads(row["payload"])
                for row in db.execute("SELECT id,payload FROM fights WHERE id LIKE 'cito:%'")}
    events, round_index = {}, defaultdict(list)
    for row in raw:
        slug = source_event_slug(row)
        if slug is None:
            raise ValueError("Expected a source event slug for each archived card.")
        key = "cito:" + row["source_bout_id"]
        notes = EVENT_NOTES["archived"].get(slug, {})
        event = events.setdefault(slug, {"slug": slug, "name": event_name(slug), "date": row["event_date"],
            "status": "archived", "bouts": [], "source_url": notes.get("source_url"), **notes})
        if event["date"] != row["event_date"]:
            raise ValueError("An archived event slug identifies multiple dates.")
        if key in accepted:
            bout = reviewed_bout(accepted[key], key)
            source = sources.get(row["source_bout_id"])
            if source:
                bout["source_url"] = source
                if not event["source_url"]:
                    event["source_url"] = source
            event["bouts"].append(bout)
        else:
            event["bouts"].append({"status": "pending", "division": row.get("weight_class"),
                                  "discrepancy": discrepancies.get(row["source_bout_id"]),
                                  "fighters": [{"id": None, "name": row[f"fighter_{i}_name"]} for i in (1, 2)]})
    for event in events.values():
        main = set(event.pop("main_event", []))
        event["bouts"].sort(key=lambda row: (
            {fighter["name"] for fighter in row["fighters"]} != main,
            row["status"] != "reviewed", not row.get("title"),
        ))
        event["reviewed_bouts"] = sum(row["status"] == "reviewed" for row in event["bouts"])
        event["pending_bouts"] = len(event["bouts"]) - event["reviewed_bouts"]
    for row in verified_rows(archive, "rounds_staged.jsonl", manifest):
        key = "cito:" + row["source_bout_id"]
        if key in accepted:
            round_index[key].append(row)
    return events, dict(round_index)


def events_index(events):
    archived = [{key: value for key, value in event.items() if key != "bouts"} for event in events.values()]
    upcoming = None if SCHEDULE["slug"] in events else {
        key: value for key, value in SCHEDULE.items() if key != "bouts"}
    return {"scheduled": upcoming, "archived": sorted(archived, key=lambda event: event["date"], reverse=True)}


def event_detail(db, events, slug):
    if slug in events:
        return events[slug]
    if slug != SCHEDULE["slug"]:
        raise KeyError("Event not found.")
    bouts = []
    for row in SCHEDULE["bouts"]:
        fighters = []
        for name in row["fighters"]:
            matches = db.execute("SELECT id FROM fighters WHERE search_name=?", (_name(name),)).fetchall()
            fighters.append({"name": name, "id": matches[0]["id"] if len(matches) == 1 else None})
        bouts.append({**row, "fighters": fighters, "status": "scheduled"})
    return {**SCHEDULE, "status": "scheduled", "bouts": bouts}


def paired_rounds(fight, rows, totals):
    """Publish rounds only when both sides and their observed counts reconcile."""
    if not rows:
        return []
    sides = {fight[f"source_fighter_{i}_id"]: i - 1 for i in (1, 2)}
    indexed = {}
    for row in rows:
        side = sides.get(row["source_fighter_id"])
        if side is None or row.get("upset_fighter_id") not in (None, fight[f"upset_fighter_{side + 1}_id"]):
            return []
        key = row["round_number"], side
        if key in indexed:
            return []
        indexed[key] = {field: row.get(field) for field in ROUND_FIELDS}
    expected = range(1, (fight["result_round"] or 0) + 1)
    if set(indexed) != {(number, side) for number in expected for side in (0, 1)}:
        return []
    for side, total in enumerate(totals):
        for field in ROUND_FIELDS:
            values = [indexed[number, side][field] for number in expected]
            if total.get(field) is not None and (None in values or sum(values) != total[field]):
                return []
    return [{"round": number, "stats": [indexed[number, 0], indexed[number, 1]]} for number in expected]


def fight_detail(db, key, events, round_index):
    record = db.execute("SELECT payload FROM fights WHERE id=?", (key,)).fetchone()
    if record is None:
        raise KeyError("Fight not found.")
    fight = json.loads(record["payload"])
    report = reviewed_bout(fight, key)
    totals = {row["fighter_id"]: json.loads(row["payload"]) for row in db.execute(
        "SELECT fighter_id,payload FROM stats WHERE fight_id=?", (key,))}
    paired = [totals[side["id"]] for side in report["fighters"]]
    slug = source_event_slug(fight)
    event = events.get(slug)
    source = next((bout.get("source_url") for bout in event["bouts"] if bout.get("id") == key), None) if event else None
    return {**report, "event": {field: event.get(field) for field in ("slug", "name", "headline")} if event else None,
            "source_url": source or (event.get("source_url") if event else None) or fight.get("source_url"),
            "totals": [{field: side.get(field) for field in ROUND_FIELDS + ("fight_duration_seconds",)}
                       for side in paired],
            "rounds": paired_rounds(fight, round_index.get(key, []), paired)}


def draw_time_machine_fight(db, exclude=""):
    candidates = db.execute("""
        SELECT id, event_date, fighter_1, fighter_2, payload FROM fights
        WHERE id != ? AND event_date <= ?
          AND (id LIKE 'cito:%' OR instr(json_extract(payload, '$.weight_class'), 'Title') > 0)
        ORDER BY random()
    """, (exclude, date.today().isoformat()))
    for row in candidates:
        fight = json.loads(row["payload"])
        sides = [{"id": row[f"fighter_{side}"], "name": fight[f"fighter_{side}_name"]} for side in (1, 2)]
        slug = source_event_slug(fight)
        main = EVENT_NOTES["archived"].get(slug, {}).get("main_event")
        is_main = main and {_name(name) for name in main} == {_name(side["name"]) for side in sides}
        is_title = title_bout(fight)
        if not (is_title or is_main):
            continue
        if all(db.execute("""
            SELECT 1 FROM fights WHERE fighter_1 = ?1 AND event_date < ?2
            UNION ALL
            SELECT 1 FROM fights WHERE fighter_2 = ?1 AND event_date < ?2
            LIMIT 1 OFFSET 2
        """, (side["id"], row["event_date"])).fetchone() is not None for side in sides):
            division = fight.get("weight_class") or "UFC"
            label = (division if "Title" in division else f"{division} title bout") if is_title else "UFC main event"
            return {"id": row["id"], "date": row["event_date"], "fighters": sides,
                    "label": label}
    return None
