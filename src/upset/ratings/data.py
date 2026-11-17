"""Read-only, hash-bound paired bouts for the experimental overall-rating study.

Outcome amendments are the currently reviewed snapshot, not a reconstruction of
when commissions or providers made those amendments available.
"""

import hashlib
import json
import re
import sqlite3
from collections import Counter
from contextlib import closing
from datetime import date
from pathlib import Path

from upset.data.identity import validate_upset_fighter_id

VERSION = "overall_rating_bouts_v1"
COUNTS = ("knockdowns", "sig_strikes_landed", "sig_strikes_attempted",
          "takedowns_landed", "takedowns_attempted", "submission_attempts",
          "head_landed", "body_landed", "leg_landed", "distance_landed",
          "clinch_landed", "ground_landed")
DIVISIONS = {"Strawweight", "Flyweight", "Bantamweight", "Featherweight",
             "Lightweight", "Welterweight", "Middleweight", "Light Heavyweight",
             "Heavyweight"}
HINDSIGHT = ("Uses currently reviewed outcome amendments. Date filtering does not "
             "reconstruct when amendments or profile/name changes became known.")


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _day(value):
    if not isinstance(value, str) or date.fromisoformat(value).isoformat() != value:
        raise ValueError("Use a canonical ISO date.")
    return value


def _division(label):
    value = " ".join(re.sub(r"\b(UFC|Interim|Title|Bout)\b", " ", label or "").split())
    return value if value.removeprefix("Women's ") in DIVISIONS else None


def _method(label):
    text = (label or "").casefold()
    if "ko" in text or "doctor" in text:
        return "ko"
    if "submission" in text:
        return "sub"
    if "decision" in text:
        return "decision"
    return "other"


def _outcome(fight, ids):
    reviewed = fight.get("reviewed_result")
    result = reviewed if reviewed is not None else fight
    if not isinstance(result, dict):
        raise TypeError("Malformed reviewed outcome.")
    winner = result.get("winner_name")
    source_names = [fight["fighter_1_name"], fight["fighter_2_name"]]
    explicit_id = result.get("winner_upset_fighter_id")
    if winner is not None:
        if source_names.count(winner) != 1:
            raise ValueError("Winner does not uniquely identify a participant.")
        winner_id = ids[source_names.index(winner)]
        if explicit_id is not None and explicit_id != winner_id:
            raise ValueError("Reviewed winner name and permanent identity disagree.")
        return winner_id, "decisive", result.get("result_method")
    if explicit_id is not None:
        raise ValueError("Winner identity has no matching named winner.")
    text = (result.get("result_method") or "").casefold()
    stated = result.get("outcome")
    if stated == "draw" or "draw" in text:
        outcome = "draw"
    elif stated in ("no_contest", "nc") or "no contest" in text or "overturned" in text:
        outcome = "nc"
    elif "decision" in text:
        outcome = "draw"
    else:
        # Historical "Draw/NC" and "Could Not Continue" do not resolve type.
        outcome = "other"
    return None, outcome, result.get("result_method")


def _check_stats(row, fight, uid, side):
    if (row.get("upset_fighter_id") != uid or row.get("source") != fight["source"]
            or row.get("source_bout_id") != fight["source_bout_id"]
            or row.get("source_fighter_id") != fight[f"source_fighter_{side}_id"]):
        raise ValueError("Statistics and paired participant identity disagree.")
    seconds = row.get("fight_duration_seconds")
    if type(seconds) is not int or seconds < 0:
        raise ValueError("Invalid fight duration.")
    for field in COUNTS:
        if type(row.get(field)) is not int or row[field] < 0:
            raise ValueError("Invalid count: " + field)
    for landed, attempts in (("sig_strikes_landed", "sig_strikes_attempted"),
                             ("takedowns_landed", "takedowns_attempted")):
        if row[landed] > row[attempts]:
            raise ValueError("Landed count exceeds attempts.")
    for fields in (("head_landed", "body_landed", "leg_landed"),
                   ("distance_landed", "clinch_landed", "ground_landed")):
        if sum(row[field] for field in fields) != row["sig_strikes_landed"]:
            raise ValueError("Significant-strike breakdown differs from total.")
    control = row.get("control_seconds")
    if control is not None and (type(control) is not int or not 0 <= control <= seconds):
        raise ValueError("Invalid control duration.")


def load_bouts(database, before):
    """Return (paired_bouts, metadata), preserving source counts and missingness.

    Bouts are sorted by (event_date, fight_id). Outcomes and all participant
    statistics on one date remain in the same date batch; callers must predict
    the entire batch before updating any history. No filtering for observed
    winners, known divisions, positive durations or control availability occurs.
    """
    database = Path(database).resolve()
    before = _day(before)
    database_hash = digest(database)
    wal = Path(str(database) + "-wal")
    if wal.exists() and wal.stat().st_size:
        raise ValueError("Use a checkpointed, immutable database snapshot without WAL.")
    manifest = database.parent / "manifest.json"
    manifest_hash = digest(manifest) if manifest.exists() else None
    if manifest_hash is not None and json.loads(manifest.read_text()).get("database_sha256") != database_hash:
        raise ValueError("Research database hash differs from its manifest.")
    bouts = []
    counts = Counter()
    with closing(sqlite3.connect(database.as_uri() + "?mode=ro&immutable=1", uri=True)) as db:
        db.row_factory = sqlite3.Row
        labels = {r["id"]: r["name"] for r in db.execute("SELECT id,name FROM fighters ORDER BY id")}
        for uid in labels:
            validate_upset_fighter_id(uid)
        selected = db.execute("SELECT * FROM fights WHERE event_date<? ORDER BY event_date,id", (before,)).fetchall()
        for saved in selected:
            fight = json.loads(saved["payload"])
            day, key = _day(fight["event_date"]), saved["id"]
            ids = [fight["upset_fighter_1_id"], fight["upset_fighter_2_id"]]
            if (day != saved["event_date"] or day >= before or len(set(ids)) != 2
                    or ids != [saved["fighter_1"], saved["fighter_2"]]
                    or any(uid not in labels for uid in ids)
                    or key != fight["source"] + ":" + fight["source_bout_id"]):
                raise ValueError("Paired fight identity/date differs from stored key.")
            paired = {r["fighter_id"]: json.loads(r["payload"]) for r in
                      db.execute("SELECT fighter_id,payload FROM stats WHERE fight_id=?", (key,))}
            if set(paired) != set(ids):
                raise ValueError("Fight needs exactly two matching stat rows.")
            stats = [paired[uid] for uid in ids]
            for side, (uid, row) in enumerate(zip(ids, stats), 1):
                _check_stats(row, fight, uid, side)
            seconds = stats[0]["fight_duration_seconds"]
            if stats[1]["fight_duration_seconds"] != seconds:
                raise ValueError("Paired durations disagree.")
            winner_id, outcome, method = _outcome(fight, ids)
            bouts.append({"fight_id": key, "event_date": day,
                          "division": _division(fight.get("weight_class")),
                          "fighter_ids": ids, "names": [labels[uid] for uid in ids],
                          "winner_id": winner_id, "outcome": outcome,
                          "method_group": _method(method), "result_method": method,
                          "duration_seconds": seconds, "stats": stats,
                          "source": fight["source"], "source_url": fight.get("source_url"),
                          "reviewed_outcome": fight.get("reviewed_result") is not None})
            counts[fight["source"]] += 1
    if digest(database) != database_hash or manifest_hash is not None and digest(manifest) != manifest_hash:
        raise ValueError("Rating inputs changed while reading.")
    metadata = {"adapter_version": VERSION, "database": str(database),
                "database_sha256": database_hash, "manifest_sha256": manifest_hash,
                "before_exclusive": before, "bouts": len(bouts),
                "fighter_stat_rows": 2 * len(bouts), "fighters": len(labels),
                "fighter_labels": labels,
                "first_event": bouts[0]["event_date"] if bouts else None,
                "latest_event": bouts[-1]["event_date"] if bouts else None,
                "source_bouts": dict(sorted(counts.items())),
                "reviewed_outcomes": sum(row["reviewed_outcome"] for row in bouts),
                "outcomes": dict(Counter(row["outcome"] for row in bouts)),
                "unknown_division_bouts": sum(row["division"] is None for row in bouts),
                "zero_duration_bouts": sum(row["duration_seconds"] == 0 for row in bouts),
                "missing_control_sides": sum(stat["control_seconds"] is None for row in bouts for stat in row["stats"]),
                "interpretation": HINDSIGHT,
                "same_date_contract": "Predict every bout on a calendar date before updating any history."}
    return bouts, metadata
