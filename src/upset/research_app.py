"""Local fighter research viewer. Run with python -m upset.research_app."""

import argparse
import json
import re
import sqlite3
from contextlib import closing
from datetime import UTC, date, datetime
from difflib import get_close_matches
from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.resources import files
from ipaddress import IPv4Address
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlencode, urlsplit

from upset import championships
from upset.data.audit_cito_archive import _name
from upset.data.collect_cito_archive import _digest
from upset.data.historical_results import load_historical_results
from upset.data.reviewed_bout_metadata import result_type, reviewed_title_evidence
from upset.data.viewer_coverage import load_coverage, pending_search
from upset.data.viewer_events import SCHEDULE, draw_time_machine_fight, event_detail, events_index, fight_detail, load_event_archive
from upset.data.viewer_upsets import build_upset_index
from upset.data.viewer_upsets_v5 import build_upset_index_v5
from upset.data.viewer_upsets_market import add_market_upsets
from upset.data.upcoming_market import attach, disagreement_record, scheduled_market
from upset.predictions.published_picks import load_record, picks_file
from upset.ratings.forecast_adjust import ForecastAdjustment, weight_class_check
from upset.data.skills_view import SkillProfiles


def connect(database):
    db = sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    return db


def metadata(db):
    return {r["key"]: json.loads(r["value"]) for r in db.execute("SELECT * FROM metadata")}


def historical_history(uid, before=None):
    history = HISTORICAL_RESULTS.get("by_fighter", {}).get(uid, ())
    return [row for row in history if before is None or row["date"] < before]


def search(db, query, before=None):
    if len(query) > 100:
        raise ValueError("Search is limited to 100 characters.")
    if before is not None and date.fromisoformat(before).isoformat() != before:
        raise ValueError("Use an ISO date for the search cutoff.")
    # Normalize name tokens; all user values still use SQL parameters.
    terms = [_name(part) for part in query.split()]
    terms = [t for t in terms if t]
    aliases = {("bobby", "green"): ("king", "green"),
               ("bones",): ("jon", "jones"),
               ("gsp",): ("georges", "st", "pierre"),
               ("do", "bronx"): ("charles", "oliveira"),
               ("valesca", "machado"): ("tina", "black"),
               ("gable", "stevenson"): ("gable", "steveson"),
               ("lesone", "keita"): ("losene", "keita"),
               ("kai", "kamaka", "iii"): ("kai", "kamaka")}
    terms = aliases.get(tuple(terms), terms)
    if not terms:
        return []
    count_cutoff = " AND fights.event_date<?" if before is not None else ""
    count_args = (before,) if before is not None else ()

    def lookup(needles):
        where = " AND ".join("search_name LIKE ?" for _ in needles)
        return db.execute("SELECT id,name,profile,(SELECT COUNT(*) FROM stats JOIN fights ON fights.id=stats.fight_id "
                          "WHERE stats.fighter_id=fighters.id" + count_cutoff + ") AS bouts "
                          "FROM fighters WHERE " + where + " ORDER BY bouts DESC,name,id LIMIT 25",
                          count_args + tuple("%" + term + "%" for term in needles)).fetchall()

    matches = lookup(terms)
    # Nicknames, alternate spellings and reviewed former names, only after the name search misses.
    alias_ids = FIGHTER_ALIASES.get("".join(terms)) if not matches else None
    if alias_ids:
        marks = ",".join("?" for _ in alias_ids[:25])
        matches = db.execute("SELECT id,name,profile,(SELECT COUNT(*) FROM stats JOIN fights ON fights.id=stats.fight_id "
                             "WHERE stats.fighter_id=fighters.id" + count_cutoff + ") AS bouts "
                             "FROM fighters WHERE id IN (" + marks + ") ORDER BY bouts DESC,name,id",
                             count_args + tuple(alias_ids[:25])).fetchall()
    # Fall back to a close first name only after an exact full-name search misses.
    if not matches and len(terms) == 2 and len(terms[0]) >= 4:
        candidates = [r for r in lookup(terms[1:]) if _name(r["name"].split()[-1]) == terms[1]]
        close = set(get_close_matches(terms[0], [_name(r["name"].split()[0]) for r in candidates],
                                      n=3, cutoff=.8))
        matches = [r for r in candidates if _name(r["name"].split()[0]) in close]
    results = []
    for r in matches:
        cutoff_clause = " AND event_date<?" if before is not None else ""
        dated = db.execute("SELECT event_date,payload FROM fights WHERE (fighter_1=? OR fighter_2=?)"
                           + cutoff_clause + " ORDER BY event_date DESC,id DESC",
                           (r["id"], r["id"]) + count_args).fetchall()
        history = [{"date": row["event_date"], "division": division(json.loads(row["payload"])["weight_class"])}
                   for row in dated]
        last_division, division_date, _ = latest_classified_division(history)
        profile = json.loads(r["profile"])
        portrait = roster_entry({"id": r["id"], "profile": profile, "before": before or date.today().isoformat()})
        earlier = historical_history(r["id"], before)
        results.append({"id": r["id"], "name": r["name"], "source_fighter_id": profile["source_fighter_id"],
                        "roster": portrait,
                        "recorded_bouts": r["bouts"], "historical_results": len(earlier),
                        "last_bout": dated[0]["event_date"] if dated else earlier[0]["date"] if earlier else None,
                        "division": last_division, "division_date": division_date})
    return results


DIVISIONS = ("Strawweight", "Flyweight", "Bantamweight", "Featherweight", "Lightweight", "Welterweight",
             "Middleweight", "Light Heavyweight", "Heavyweight")


def division(weight_class):
    """Map a source weight-class label to a canonical division, or None for open/catch/tournament bouts."""
    text = re.sub(r"\b(UFC|Interim|Title|Bout)\b", " ", weight_class or "")
    text = " ".join(text.split())
    women = text.startswith("Women's ")
    base = text.removeprefix("Women's ")
    if base not in DIVISIONS:
        return None
    return ("Women's " if women else "") + base


def method_group(method):
    text = (method or "").casefold()
    if "ko" in text or "doctor" in text:
        return "ko"
    if "submission" in text:
        return "sub"
    if "decision" in text:
        return "dec"
    return "other"


def latest_classified_division(history):
    """Latest classified bout in descending date order, never a majority vote.

    Unknown/catchweight bouts provide no new division evidence. Contradictory
    same-day divisions remain unresolved because intra-day order is unknown.
    """
    for row in history:
        if row["division"] is None:
            continue
        day = row["date"]
        divisions = {r["division"] for r in history if r["date"] == day and r["division"] is not None}
        if len(divisions) > 1:
            return None, day, "ambiguous_same_day_divisions"
        return row["division"], day, "latest_classified_bout"
    return None, None, "no_classified_bout"


def age_on(date_of_birth, cutoff):
    if not date_of_birth:
        return None
    born = date.fromisoformat(date_of_birth)
    return cutoff.year - born.year - ((cutoff.month, cutoff.day) < (born.month, born.day))


def ratio(numerator, denominator):
    return numerator / denominator if denominator else None


def fighter_report(db, uid, before, window):
    cutoff = date.fromisoformat(before)
    if cutoff.isoformat() != before or window not in (0, 3, 5, 10):
        raise ValueError("Use an ISO date and a window of 0, 3, 5 or 10 fights.")
    row = db.execute("SELECT * FROM fighters WHERE id=?", (uid,)).fetchone()
    if row is None:
        raise KeyError("Fighter not found.")
    profile = json.loads(row["profile"])
    history = []
    for record in db.execute("""SELECT id,payload FROM fights WHERE (fighter_1=? OR fighter_2=?) AND event_date<?
                                ORDER BY event_date DESC,id DESC""", (uid, uid, before)):
        fight = json.loads(record["payload"])
        side = 1 if fight["upset_fighter_1_id"] == uid else 2
        other = 3 - side
        opponent = fight[f"upset_fighter_{other}_id"]
        stat = json.loads(db.execute("SELECT payload FROM stats WHERE fight_id=? AND fighter_id=?", (record["id"], uid)).fetchone()[0])
        opposing = json.loads(db.execute("SELECT payload FROM stats WHERE fight_id=? AND fighter_id=?", (record["id"], opponent)).fetchone()[0])
        winner = fight["winner_name"]
        frozen_outcome = "other" if winner is None else ("win" if winner == fight[f"fighter_{side}_name"] else "loss")
        amendment = fight.get("reviewed_result")
        reviewed_outcome = ("other" if amendment["winner_name"] is None else
                            "win" if amendment["winner_name"] == fight[f"fighter_{side}_name"] else "loss") if amendment else frozen_outcome
        method = amendment["result_method"] if amendment else fight["result_method"]
        detail, result_source = result_type(fight) if reviewed_outcome == "other" else (reviewed_outcome, None)
        title_evidence = reviewed_title_evidence(fight)
        history.append({"fight_id": record["id"], "date": fight["event_date"],
                        "opponent_id": opponent, "opponent": fight[f"fighter_{other}_name"],
                        "outcome": reviewed_outcome, "result_type": detail, "result_source_url": result_source,
                        "frozen_outcome": frozen_outcome,
                        "method": method, "method_group": method_group(method),
                        "result_round": amendment.get("result_round") if amendment else fight.get("result_round"),
                        "result_time": amendment.get("result_time") if amendment else fight.get("result_time"),
                        "weight_class": fight.get("weight_class"), "division": division(fight.get("weight_class")),
                        "title_bout": "Title" in (fight.get("weight_class") or "") or title_evidence is not None,
                        "title_bout_evidence": title_evidence,
                        "source": fight["source"], "source_url": fight.get("source_url"),
                        "reviewed_result": amendment, "frozen_result": {k: fight[k] for k in ("winner_name", "source_winner_label", "result_method", "result_time")},
                        "own": stat, "opponent_stats": opposing})
    selected = history[:window] if window else history
    timed = [r for r in selected if r["own"]["fight_duration_seconds"] > 0]
    seconds = sum(r["own"]["fight_duration_seconds"] for r in timed)
    minutes = seconds / 60
    def own(field):
        return sum(r["own"][field] for r in timed)

    def opposing(field):
        return sum(r["opponent_stats"][field] for r in timed)
    controlled = [r for r in timed if r["own"]["control_seconds"] is not None
                  and r["opponent_stats"]["control_seconds"] is not None]
    control_seconds = sum(r["own"]["fight_duration_seconds"] for r in controlled)
    control_margin = sum(r["own"]["control_seconds"] - r["opponent_stats"]["control_seconds"] for r in controlled)
    td_attempts = opposing("takedowns_attempted")
    strike_attempts = opposing("sig_strikes_attempted")
    stats = {"bouts": len(selected), "timed_bouts": len(timed), "minutes": minutes,
             "wins": sum(r["outcome"] == "win" for r in selected), "losses": sum(r["outcome"] == "loss" for r in selected),
             "other_results": sum(r["outcome"] == "other" for r in selected),
             "draws": sum(r["result_type"] == "draw" for r in selected),
             "no_contests": sum(r["result_type"] == "nc" for r in selected),
             "sig_landed_per_minute": ratio(own("sig_strikes_landed"), minutes),
             "sig_absorbed_per_minute": ratio(opposing("sig_strikes_landed"), minutes),
             "sig_differential_per_minute": ratio(own("sig_strikes_landed") - opposing("sig_strikes_landed"), minutes),
             "striking_accuracy": ratio(own("sig_strikes_landed"), own("sig_strikes_attempted")),
             "striking_defense": None if not strike_attempts else 1 - opposing("sig_strikes_landed") / strike_attempts,
             "takedowns_per_15_minutes": ratio(own("takedowns_landed") * 15, minutes),
             "takedown_accuracy": ratio(own("takedowns_landed"), own("takedowns_attempted")),
             "takedown_defense": None if not td_attempts else 1 - opposing("takedowns_landed") / td_attempts,
             "opponent_takedown_attempts": td_attempts, "opponent_strike_attempts": strike_attempts,
             "takedown_attempts": own("takedowns_attempted"), "strike_attempts": own("sig_strikes_attempted"),
             "knockdowns_per_15_minutes": ratio(own("knockdowns") * 15, minutes),
             "control_margin_seconds_per_minute": ratio(control_margin, control_seconds / 60),
             "control_observed_bouts": len(controlled), "control_observed_minutes": control_seconds / 60,
             "submission_attempts_per_15_minutes": ratio(own("submission_attempts") * 15, minutes)}
    # Where landed significant strikes went (target and position), summed over the window.
    stats["sig_targets"] = {k: own(k + "_landed") for k in ("head", "body", "leg")}
    stats["sig_positions"] = {k: own(k + "_landed") for k in ("distance", "clinch", "ground")}
    stats["results_by_method"] = {outcome: {g: sum(r["outcome"] == outcome and r["method_group"] == g for r in selected)
                                            for g in ("ko", "sub", "dec", "other")} for outcome in ("win", "loss")}
    # Count-based measures include selected bouts even when the clock is zero.
    # Their denominator is landed significant strikes, never bout duration.
    knockdowns = sum(r["own"]["knockdowns"] for r in selected)
    sig_landed = sum(r["own"]["sig_strikes_landed"] for r in selected)
    stats["power_durability"] = {
        "bouts": len(selected),
        "knockdowns_scored": knockdowns,
        "sig_strikes_landed": sig_landed,
        "knockdowns_per_100_sig_landed": ratio(100 * knockdowns, sig_landed),
        "knockdowns_received": sum(r["opponent_stats"]["knockdowns"] for r in selected),
        "ko_tko_losses": stats["results_by_method"]["loss"]["ko"],
        "losses": stats["losses"],
    }
    results_only = historical_history(uid, before)
    results = history + results_only
    streak_kind, streak = (results[0]["outcome"], 0) if results else (None, 0)
    streak_detail = results[0]["result_type"] if results else None
    for r in results:
        if r["result_type"] != streak_detail:
            break
        streak += 1
    last_division, division_date, division_basis = latest_classified_division(history)
    all_historical = historical_history(uid)
    if all_historical:
        first_recorded = all_historical[-1]["date"]
    elif history:
        first_recorded = history[-1]["date"]
    else:
        first_recorded = db.execute("SELECT MIN(event_date) FROM fights WHERE fighter_1=? OR fighter_2=?",
                                    (uid, uid)).fetchone()[0]
    summary = {"career": {k: sum(r["outcome"] == k for r in results) for k in ("win", "loss", "other")},
               "draws": sum(r["result_type"] == "draw" for r in results),
               "no_contests": sum(r["result_type"] == "nc" for r in results),
               "reviewed_results": len(results),
               "streak": {"outcome": streak_kind, "count": streak,
                          "result_type": streak_detail},
               "first_recorded_bout": first_recorded,
               "last_bout": results[0]["date"] if results else None,
               "first_bout": results[-1]["date"] if results else None,
               "division": last_division, "division_date": division_date, "division_basis": division_basis,
               "title_bouts": sum(r["title_bout"] for r in history),
               "age": age_on(profile.get("date_of_birth"), cutoff)}
    for r in history:
        r["sig_differential_per_minute"] = ratio(r["own"]["sig_strikes_landed"] - r["opponent_stats"]["sig_strikes_landed"], r["own"]["fight_duration_seconds"] / 60)
    return {"id": uid, "name": row["name"], "profile": profile, "before": before,
            "window": window, "available_bouts": len(history), "metrics": stats, "history": history,
            "summary": summary, "results_only_history": results_only,
            "interpretation": "Fight-date filter with currently reviewed outcomes and title metadata; not a reconstruction of when amendments became available. Profile measurements are from the frozen profile snapshot."}


def load_professional_records(db, path, database_sha256):
    data = json.loads(path.read_text())
    if data["schema_version"] != 1 or data["database_sha256"] != database_sha256:
        raise ValueError("Professional records differ from the selected database release.")
    as_of = data["as_of"]
    if date.fromisoformat(as_of).isoformat() != as_of:
        raise ValueError("Use an ISO observation date for professional records.")
    for uid, record in data["records"].items():
        report = fighter_report(db, uid, as_of, 0)
        if report["name"] != record["name"]:
            raise ValueError(f"Professional record identity does not match {uid}.")
        minimums = {"wins": report["summary"]["career"]["win"],
                    "losses": report["summary"]["career"]["loss"],
                    "draws": report["summary"]["draws"],
                    "no_contests": report["summary"]["no_contests"]}
        for field, minimum in minimums.items():
            count = record[field]
            if field == "no_contests" and count is None and minimum == 0:
                continue
            if type(count) is not int or count < minimum:
                raise ValueError(f"Professional {field} for {record['name']} conflict with reviewed UFC results.")
        urls = record["source_urls"]
        if not isinstance(urls, list) or not urls or any(
                not isinstance(url, str) or urlsplit(url).scheme != "https" or not urlsplit(url).netloc for url in urls):
            raise ValueError(f"Professional record source is missing for {record['name']}.")
    return {uid: {**record, "as_of": as_of} for uid, record in data["records"].items()}


ROSTER = {}
PROFESSIONAL_RECORDS = {}
UPSET_INDEX = None
STRIKING_PREVIEW = None
RATING_SNAPSHOT = None
COVERAGE = ()
EVENTS = {}
FIGHT_ROUNDS = {}
HISTORICAL_RESULTS = {}
EVENT_NAMES = {}
FIGHTER_ALIASES = {}
PROVIDER_AUDIT = None
MARKET_ODDS = None
SKILL_PROFILES = None
FIGHTERS_WITH_FIGHTS = None
UPCOMING_MARKET = {}
DISAGREEMENT = {}
PUBLISHED_PICKS = Path("data/published/picks")
BREAKDOWN_FIELDS = ("head_landed", "body_landed", "leg_landed", "distance_landed", "clinch_landed", "ground_landed")
IMAGE_NAME = re.compile(r"^[A-Za-z0-9_-]{1,80}\.(jpg|jpeg|png|webp)$")
ASSET_NAME = re.compile(r"^[A-Za-z0-9_-]{1,80}\.(jpg|jpeg|png|webp|woff2|ttf)$")
ASSET_TYPES = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png", "webp": "image/webp",
               "woff2": "font/woff2", "ttf": "font/ttf"}


def load_roster(path):
    """Optional hand-maintained roster: {"as_of": "YYYY-MM-DD", "fighters": {<upset id or source id>: {...}}}."""
    if path is None:
        return {}
    data = json.loads(path.read_text())
    if not isinstance(data, dict) or not isinstance(data.get("fighters"), dict):
        raise TypeError("Roster must contain an as_of date and fighter dictionary.")
    snapshot = date.fromisoformat(data["as_of"])
    if snapshot.isoformat() != data["as_of"] or any(not isinstance(row, dict) for row in data["fighters"].values()):
        raise ValueError("Invalid roster date or fighter entry.")
    return {"as_of": data.get("as_of"), "source": data.get("source"), "fighters": data.get("fighters", {}),
            "media_dir": path.parent / "media"}


def roster_entry(report):
    if not ROSTER:
        return None
    fighters = ROSTER["fighters"]
    entry = fighters.get(report["id"]) or fighters.get(report["profile"].get("source_fighter_id"))
    if not entry:
        return {"status": None, "as_of": ROSTER["as_of"]}
    image = entry.get("image")
    # A later roster observation cannot establish status at an earlier cutoff.
    elapsed = (date.fromisoformat(report["before"]) - date.fromisoformat(ROSTER["as_of"])).days
    current = 0 <= elapsed <= 62
    return {"status": entry.get("status") if current else None, "status_current": current,
            "as_of": ROSTER["as_of"], "source": ROSTER.get("source"),
            "image_url": "/media/" + image if isinstance(image, str) and IMAGE_NAME.fullmatch(image) else entry.get("image_url"),
            "image_credit": entry.get("image_credit"), "image_kind": entry.get("image_kind", "photo")}


def rating_availability(report):
    """Expose rating readiness without converting existing statistics into a score.

    History already obeys the report's exclusive date cutoff. Read its full
    length, rather than the selected measurement window, for provisional status.
    """
    bouts = len(report["history"])
    message = "The four-part UPSET overall rating is still in development. No score has been assigned."
    if not bouts:
        message = "Rated after first recorded UFC fight. " + message
    return {"status": "not_available", "score": None, "version": None,
            "before": report["before"], "reason": "rating_model_not_ready",
            "provisional": 0 < bouts < 4, "recorded_bouts": bouts,
            "message": message}


def rating_fight_summary(row):
    """Describe the recorded result and counts for the latest rated bout."""
    method = row.get("method")
    verb = {"win": "Won", "loss": "Lost"}.get(row["outcome"])
    non_decisive = {"draw": "Draw", "nc": "No contest"}.get(row.get("result_type"))
    result = (f"{verb} by {method}" if method else verb) if verb else (non_decisive or method or "Recorded result")
    own, opponent = row.get("own", {}), row.get("opponent_stats", {})
    landed, absorbed = own.get("sig_strikes_landed"), opponent.get("sig_strikes_landed")
    made, attempted = own.get("takedowns_landed"), own.get("takedowns_attempted")
    counts = []
    if type(landed) is int and type(absorbed) is int:
        counts.append(f"significant strikes landed: {landed}–{absorbed}")
    if type(made) is int and type(attempted) is int and attempted > 0:
        counts.append(f"takedowns: {made} of {attempted}")
    return f"{result}." + (" Recorded " + "; ".join(counts) + "." if counts else "")


def rating_explanations(database, report):
    """Decorate a served rating using only dated snapshot lookups, never fits.

    Part changes compare against the snapshot strictly before the latest
    post-date batch. Best wins use each opponent's pre-fight rating, not their
    current rating. Reviewed outcomes retain the viewer's existing hindsight.
    """
    rating = report["rating"]
    if RATING_SNAPSHOT is None or rating["status"] != "available":
        return
    history = [row for row in report["history"] if row["date"] < report["before"]]
    prior = RATING_SNAPSHOT.estimate(database, {"id": report["id"],
                                             "before": rating["event_date"], "window": 0})
    rating["previous_score"] = prior.get("score") if prior["status"] == "available" else None
    rating["part_changes"] = []
    if prior["status"] == "available":
        earlier_parts = {part["key"]: part for part in prior["parts"]}
        for part in rating["parts"]:
            previous = earlier_parts.get(part["key"], {}).get("score")
            current = part["score"]
            rating["part_changes"].append({"key": part["key"], "label": part["label"],
                                           "previous": previous, "current": current,
                                           "change": None if previous is None else current-previous})
    result_fields = ("fight_id", "date", "opponent_id", "opponent", "method", "outcome")
    latest = [row for row in history if row["date"] == rating["event_date"]]
    rating["last_results"] = [
        {**{key: row[key] for key in result_fields},
         **({"result_type": row["result_type"]} if row["outcome"] == "other" else {})}
        for row in latest
    ]
    if len(latest) == 1:
        rating["last_fight_summary"] = rating_fight_summary(latest[0])
    wins = []
    for row in history:
        if row["outcome"] != "win":
            continue
        opponent = RATING_SNAPSHOT.estimate(database, {"id": row["opponent_id"],
                                                     "before": row["date"], "window": 0})
        wins.append({**{key: row[key] for key in ("fight_id", "date", "opponent_id", "opponent", "method")},
                     "opponent_rating": opponent.get("score") if opponent["status"] == "available" else None})
    wins.sort(key=lambda row: (row["opponent_rating"] is not None, row["opponent_rating"] or 0,
                              row["date"], row["fight_id"]), reverse=True)
    rating["best_wins"] = wins[:5]
    rating["best_wins_basis"] = "opponent pre-fight rating under this version"


def estimate_on_saved_data(snapshot, database, report):
    result = _estimate_on_saved_data(snapshot, database, report)
    if isinstance(result, dict):
        result["fighter_id"] = report["id"]
    return result


def _estimate_on_saved_data(snapshot, database, report):
    result = snapshot.estimate(database, report)
    if result["status"] != "unsupported_cutoff":
        return result
    cutoff = snapshot.metadata["before_exclusive"]
    if report["before"] <= cutoff:
        return result
    # The snapshot was verified against this exact database at startup. Only
    # reuse the saved estimate if its cutoff includes the entire fight archive.
    with closing(connect(database)) as db:
        if db.execute("SELECT 1 FROM fights WHERE event_date>=? LIMIT 1", (cutoff,)).fetchone():
            return result
    saved = snapshot.estimate(database, {**report, "before": cutoff})
    if saved["status"] == "available":
        saved.update(before=report["before"], snapshot_before=cutoff)
        if "rating_is_stale" in saved:
            age = date.fromisoformat(report["before"]) - date.fromisoformat(saved["event_date"])
            saved["rating_is_stale"] = age.days > 730
    return saved


def enrich(database, report):
    report["roster"] = roster_entry(report)
    record = PROFESSIONAL_RECORDS.get(report["id"])
    if record and report["before"] >= record["as_of"]:
        report["professional_record"] = record
    report["championships"] = championships.report(database, report)
    report["rating"] = (estimate_on_saved_data(RATING_SNAPSHOT, database, report) if RATING_SNAPSHOT is not None
                        else rating_availability(report))
    if report["results_only_history"] and not report["history"]:
        report["rating"]["message"] = "Official results are available. A rating uses linked fight statistics."
    if report["rating"]["status"] == "available":
        rating_explanations(database, report)
        updates = {row["date"]: row for row in report["rating"]["history"]}
        seen = set()
        for row in report["history"]:
            day = row["date"]
            if day in seen or day not in updates:
                continue
            seen.add(day)
            update = updates[day]
            row["rating_update"] = {"date": day, "score": update["score"],
                                    "change": update["change"], "version": report["rating"]["version"],
                                    "scope": "post-date batch", "experimental": True}
            if update.get("outcome_hold"):
                row["rating_update"]["outcome_hold"] = update["outcome_hold"]
    if STRIKING_PREVIEW is not None:
        report["experimental_striking"] = estimate_on_saved_data(STRIKING_PREVIEW, database, report)
    return report


def attach_locked_picks(event):
    """Show the frozen pick next to today's forecast, so a card never shows one without the other."""
    try:
        record = load_record(PUBLISHED_PICKS)
    except (OSError, ValueError):
        return event
    item = next((e for e in record["events"] if not e.get("error") and e["slug"] == event.get("slug")), None)
    if item is None:
        return event
    picks = {frozenset(f["id"] for f in pick["fighters"]): pick for pick in item["picks"]}
    bouts = []
    for bout in event["bouts"]:
        ids = [fighter.get("id") for fighter in bout["fighters"]]
        pick = picks.get(frozenset(ids))
        if pick:
            order = [f["id"] for f in pick["fighters"]]
            p = pick["probabilities"] if order == ids else pick["probabilities"][::-1]
            bout = {**bout, "locked_pick": {"probabilities": p, "frozen_at": item["frozen_at"],
                                            "revision": (item.get("model") or {}).get("forecast_revision")
                                            or (item.get("model") or {}).get("revision")}}
        bouts.append(bout)
    return {**event, "bouts": bouts, "locked_picks": {"frozen_at": item["frozen_at"], "sha256": item["sha256"]}}


def rating_forecast(database, a_id, b_id, before, division=None):
    """Matchup forecast from a snapshot that offers one (UPSET Rating v5); otherwise None."""
    if RATING_SNAPSHOT is None or not hasattr(RATING_SNAPSHOT, "matchup") or not a_id or not b_id:
        return None
    pair = [estimate_on_saved_data(RATING_SNAPSHOT, database, {"id": uid, "before": before, "window": 0})
            for uid in (a_id, b_id)]
    if getattr(RATING_SNAPSHOT, "forecast_adjustment", None) is None:
        return RATING_SNAPSHOT.matchup(*pair)
    forecast = RATING_SNAPSHOT.matchup(*pair, division=division)
    market = UPCOMING_MARKET.get(frozenset((a_id, b_id)))
    # Only for the upcoming fight itself, never for a past cutoff.
    if market and DISAGREEMENT and before > RATING_SNAPSHOT.metadata["latest_event"]:
        if market["fighter_ids"][0] != a_id:
            market = {**market, "fighter_ids": market["fighter_ids"][::-1],
                      "probabilities": market["probabilities"][::-1], "american": market["american"][::-1]}
        forecast = attach(forecast, market, DISAGREEMENT)
    return forecast


def load_event_names(folder, database_sha256):
    """Display-only event titles for archived fights, bound to this exact database."""
    manifest = json.loads((folder / "manifest.json").read_text())
    if (manifest.get("version") != "event_names_v1" or manifest.get("database_sha256") != database_sha256
            or _digest(folder / "event_names.json") != manifest.get("output_sha256")):
        raise ValueError("Event-name index does not match this database.")
    return json.loads((folder / "event_names.json").read_text())


def load_verified_json(folder, name, database_sha256, version):
    """Read one JSON output of a small derived index after checking its manifest and database."""
    manifest = json.loads((folder / "manifest.json").read_text())
    expected = manifest.get("output_sha256")
    expected = expected.get(name) if isinstance(expected, dict) else expected
    if (manifest.get("version") != version or manifest.get("database_sha256") != database_sha256
            or _digest(folder / name) != expected):
        raise ValueError(f"{folder} does not match this database.")
    return json.loads((folder / name).read_text()), manifest


def corrections(db):
    """Everything UPSET changed or checked, with sources, for the public corrections log."""
    amended = []
    for fight_id, day, payload in db.execute(
            "SELECT id,event_date,payload FROM fights WHERE json_extract(payload,'$.reviewed_result') IS NOT NULL "
            "ORDER BY event_date DESC"):
        fight = json.loads(payload)
        review = fight["reviewed_result"]
        amended.append({"fight_id": fight_id, "date": day,
                        "fighters": [fight["fighter_1_name"], fight["fighter_2_name"]],
                        "original": {"winner": fight.get("winner_name"), "method": fight.get("result_method")},
                        "reviewed": {"outcome": review.get("outcome"), "winner": review.get("winner_name"),
                                     "method": review.get("result_method")},
                        "authority": review.get("authority"), "reason": review.get("reason"),
                        "sources": review.get("source_urls", [])})
    audit = PROVIDER_AUDIT or {}
    return {"amended_results": amended,
            "provider_audit": {key: audit.get(key) for key in
                               ("provider", "provider_captured_through", "counts", "disagreements")} if audit else None,
            "provider_only_recent": [row for row in audit.get("provider_only_bouts", []) if row["date"] >= "2001-01-01"],
            "provider_only_early": sum(row["date"] < "2001-01-01" for row in audit.get("provider_only_bouts", [])),
            "aliases": len(FIGHTER_ALIASES), "pending_bouts": len(COVERAGE) if COVERAGE else 0}


def fight_event_info(fight_id, event=None):
    info = EVENT_NAMES.get(fight_id)
    if info:
        return {key: info.get(key) for key in ("title", "location", "slug", "section", "method_detail")}
    if event:
        title = event.get("name") + (": " + event["headline"] if event.get("headline") else "")
        return {"title": title, "slug": event.get("slug")}
    return None


def decorate_fight(db, database, report):
    """Add the event title, strike breakdown and what UPSET said before the fight."""
    report["event_info"] = fight_event_info(report["id"], report.get("event"))
    rows = {row["fighter_id"]: json.loads(row["payload"]) for row in db.execute(
        "SELECT fighter_id,payload FROM stats WHERE fight_id=?", (report["id"],))}
    sides = [rows.get(fighter["id"], {}) for fighter in report["fighters"]]
    if all(type(side.get(field)) is int for side in sides for field in BREAKDOWN_FIELDS):
        report["breakdown"] = [{field: side[field] for field in BREAKDOWN_FIELDS} for side in sides]
    if RATING_SNAPSHOT is not None and all(fighter.get("id") for fighter in report["fighters"]):
        ratings = []
        for fighter in report["fighters"]:
            grade = RATING_SNAPSHOT.estimate(database, {"id": fighter["id"], "before": report["date"], "window": 0})
            ratings.append({key: grade.get(key) for key in ("score", "stars", "tier", "bouts", "provisional")}
                           if grade["status"] == "available" else None)
        report["pre_fight"] = {"ratings": ratings, "version": RATING_SNAPSHOT.evaluation.get("version")}
        item = getattr(RATING_SNAPSHOT, "forecasts", {}).get(report["id"])
        if item and min(item["prior_decisive_bouts"]) >= 1 and item["fighter_ids"][0] in (
                report["fighters"][0]["id"], report["fighters"][1]["id"]):
            p = item["forecast"] if item["fighter_ids"][0] == report["fighters"][0]["id"] else 1 - item["forecast"]
            report["pre_fight"]["forecast"] = [p, 1 - p]
    return report


def opponent_grade_summary(database, report):
    window = report["window"]
    fights = report["history"][:window] if window else report["history"]
    scores = []
    for fight in fights:
        grade = RATING_SNAPSHOT.estimate(database, {"id": fight["opponent_id"], "before": fight["date"], "window": 0})
        if grade["status"] == "available":
            scores.append(grade["score"])
    return {"average": sum(scores) / len(scores) if scores else None,
            "rated_fights": len(scores), "fights": len(fights)}


def common_opponents(reports):
    """Intersect accepted opponent IDs within each report's selected window.

    Keep every meeting, including rematches and reviewed draw/NC outcomes.
    Identical display names never establish an identity match.
    """
    grouped = []
    fields = ("fight_id", "date", "outcome", "method", "result_round", "result_time")
    for report in reports:
        history = report["history"]
        selected = history[:report["window"]] if report["window"] else history
        opponents = {}
        for row in selected:
            entry = opponents.setdefault(row["opponent_id"], {
                "name": row["opponent"], "meetings": []})
            entry["meetings"].append({**{key: row[key] for key in fields},
                                      "result_amended": bool(row["reviewed_result"]),
                                      **({"result_type": row.get("result_type", "other")}
                                         if row["outcome"] == "other" else {})})
        grouped.append(opponents)
    a, b = grouped
    shared = [{"opponent_id": uid, "opponent": a[uid]["name"],
               "fighters": [{"fighter_id": report["id"],
                             "meetings": group[uid]["meetings"]}
                            for report, group in zip(reports, grouped)]}
              for uid in a.keys() & b.keys()]
    shared.sort(key=lambda item: (
        max(meeting["date"] for side in item["fighters"] for meeting in side["meetings"]),
        item["opponent_id"]), reverse=True)
    return shared


def route(database, target):
    parts = urlsplit(target)
    params = parse_qs(parts.query)
    with closing(connect(database)) as db:
        historic = HISTORICAL_RESULTS.get("events", {})
        if parts.path == "/api/meta":
            meta = metadata(db)
            meta["share_routes"] = True
            global FIGHTERS_WITH_FIGHTS
            if FIGHTERS_WITH_FIGHTS is None:
                FIGHTERS_WITH_FIGHTS = db.execute("SELECT COUNT(DISTINCT fighter_id) FROM stats").fetchone()[0]
            meta["fighters_with_fights"] = FIGHTERS_WITH_FIGHTS
            meta["upset_tracker"] = UPSET_INDEX is not None
            if PROFESSIONAL_RECORDS:
                meta["professional_records"] = len(PROFESSIONAL_RECORDS)
            if historic:
                meta["first_reviewed_result"] = min(event["date"] for event in historic.values())
                meta["results_only_bouts"] = len(HISTORICAL_RESULTS["bouts"])
            return meta
        if parts.path == "/api/corrections":
            return corrections(db)
        if parts.path == "/api/skills":
            if SKILL_PROFILES is None:
                raise KeyError("Skill profiles are not loaded.")
            return SKILL_PROFILES.profile(params.get("id", [""])[0])
        if parts.path == "/api/record":
            return load_record(PUBLISHED_PICKS)
        if parts.path == "/api/time-machine":
            fight = draw_time_machine_fight(db, params.get("exclude", [""])[0])
            if fight is not None:
                fight["event_info"] = fight_event_info(fight["id"]) or fight_event_info(
                    fight["id"], fight_detail(db, fight["id"], EVENTS, FIGHT_ROUNDS).get("event"))
            return fight
        if parts.path == "/api/upsets" and UPSET_INDEX is not None:
            return UPSET_INDEX
        if parts.path == "/api/events":
            return {**events_index(EVENTS),
                    "historical": [{key: value for key, value in event.items() if key != "bouts"}
                                   for event in historic.values()]}
        if parts.path == "/api/event":
            slug = params.get("slug", [""])[0]
            event = historic[slug] if slug in historic else event_detail(db, EVENTS, slug)
            upcoming = UPSET_INDEX.get("upcoming") if UPSET_INDEX else None
            if upcoming and event["status"] == "scheduled" and upcoming["slug"] == slug:
                gaps = {frozenset(fighter["id"] for fighter in bout["fighters"]): bout["gap"]
                        for bout in upcoming["bouts"]}
                event = {**event, "bouts": [{**bout, "grade_gap": gaps.get(
                    frozenset(fighter["id"] for fighter in bout["fighters"]))} for bout in event["bouts"]]}
            forecasts = getattr(RATING_SNAPSHOT, "forecasts", None)
            if forecasts and event.get("status") != "scheduled":
                bouts = []
                for bout in event["bouts"]:
                    item = forecasts.get(bout.get("id"))
                    ids = [fighter.get("id") for fighter in bout["fighters"]]
                    if item and min(item["prior_decisive_bouts"]) >= 1 and item["fighter_ids"][0] in ids:
                        p = item["forecast"] if item["fighter_ids"][0] == ids[0] else 1 - item["forecast"]
                        bout = {**bout, "forecast_going_in": [p, 1 - p]}
                    bouts.append(bout)
                event = {**event, "bouts": bouts}
            if event.get("status") == "scheduled" and hasattr(RATING_SNAPSHOT, "matchup"):
                event = {**event, "bouts": [{**bout, "forecast": rating_forecast(
                    database, *[fighter.get("id") for fighter in bout["fighters"]], event["date"], bout.get("division"))}
                    for bout in event["bouts"]]}
                event = attach_locked_picks(event)
            return event
        if parts.path == "/api/fight":
            key = params.get("id", [""])[0]
            historical = HISTORICAL_RESULTS.get("bouts", {})
            return historical[key] if key in historical else decorate_fight(
                db, database, fight_detail(db, key, EVENTS, FIGHT_ROUNDS))
        if parts.path == "/api/fighters":
            return search(db, params.get("q", [""])[0], params.get("before", [None])[0])
        before = params.get("before", [datetime.now(UTC).date().isoformat()])[0]
        if parts.path == "/api/coverage":
            return pending_search(COVERAGE, params.get("q", [""])[0], before)
        window = int(params.get("window", ["5"])[0])
        if parts.path == "/api/fighter":
            return enrich(database, fighter_report(db, params.get("id", [""])[0], before, window))
        if parts.path == "/api/compare":
            a, b = params.get("a", [""])[0], params.get("b", [""])[0]
            if a == b:
                raise ValueError("Choose two different fighters.")
            reports = [enrich(database, fighter_report(db, uid, before, window)) for uid in (a, b)]
            if RATING_SNAPSHOT is not None:
                for report in reports:
                    report["opposition"] = opponent_grade_summary(database, report)
            result = {"fighters": reports, "common_opponents": common_opponents(reports)}
            forecast = rating_forecast(database, a, b, before)
            if forecast is not None:
                result["forecast"] = weight_class_check(forecast, [r["name"] for r in reports],
                                                        [r["summary"].get("division") for r in reports])
            return result
    raise KeyError("Page not found.")


DESIGNS = {"broadcast": "research.html", "editorial": "research_editorial.html"}
WEB_FILES = {
    "research_rating.js": "text/javascript; charset=utf-8",
    "research_rating_examples.js": "text/javascript; charset=utf-8",
    "research_rating.css": "text/css; charset=utf-8",
    "research_champions.js": "text/javascript; charset=utf-8",
    "research_champions.css": "text/css; charset=utf-8",
    "research_comparison_fights.js": "text/javascript; charset=utf-8",
    "research_comparison_fights.css": "text/css; charset=utf-8",
    "research_events.js": "text/javascript; charset=utf-8",
    "research_events.css": "text/css; charset=utf-8",
    "research_about.css": "text/css; charset=utf-8",
    "research_about.js": "text/javascript; charset=utf-8",
    "research_base.css": "text/css; charset=utf-8",
    "research_editorial.css": "text/css; charset=utf-8",
    "research_editorial.js": "text/javascript; charset=utf-8",
}


STATIC_PAGE_LABELS = {
    "/": ("UPSET · UFC Fighter Research", "Search UFC fighters, review fight stats, and compare two fighters at a date you choose."),
    "/events": ("UFC Events · UPSET", "Browse scheduled UFC cards, reviewed results, and paired round-by-round stats."),
    "/time-machine": ("Time Machine · UPSET", "Draw a UFC title fight or main event and see how it looked before fight night."),
    "/upsets": ("Upset Tracker · UPSET", "Explore UFC results where the winner entered with a lower experimental UPSET grade."),
    "/methodology": ("Methodology · UPSET", "How UPSET records UFC bouts, computes fight stats, and presents experimental ratings."),
    "/compare": ("Compare fighters · UPSET", "Pick any two UFC fighters and compare records, ratings and fight stats side by side."),
    "/record": ("Track record · UPSET", "Every pick UPSET publishes before a UFC card, fingerprinted and graded after the fights."),
    "/corrections": ("Data checks & corrections · UPSET", "How UPSET checks UFC results against a second provider, and every correction it has made."),
    "/rating-preview": ("UPSET Rating · Design Preview", "Explore the experimental UPSET fighter rating design."),
    "/about": ("About UPSET", "About Ayaan Ahmed and the UPSET UFC research project."),
}


def share_parameters(query):
    params = parse_qs(query)
    today = date.today().isoformat()
    day = params.get("before", [today])[0]
    window = int(params.get("window", ["0"])[0])
    if date.fromisoformat(day).isoformat() != day or not "1993-01-01" <= day <= today or window not in (0, 3, 5, 10):
        raise ValueError("Use an ISO date and a window of 0, 3, 5 or 10 fights.")
    return day, window


def portrait_path(report):
    url = (report.get("roster") or {}).get("image_url")
    if ROSTER and isinstance(url, str) and url.startswith("/media/"):
        filename = url.removeprefix("/media/")
        if IMAGE_NAME.fullmatch(filename):
            return ROSTER["media_dir"] / filename
    return None


def broadcast_metadata(database, path, query):
    if path in STATIC_PAGE_LABELS:
        return (*STATIC_PAGE_LABELS[path], "/assets/favicon.png")
    resource, *keys = path.removeprefix("/").split("/")
    keys = [unquote(key) for key in keys]
    profile = resource == "fighter" and len(keys) == 1
    comparison = resource == "compare" and len(keys) == 2 and keys[0] != keys[1]
    if profile or comparison:
        with closing(connect(database)) as db:
            fighters = [db.execute("SELECT name FROM fighters WHERE id=?", (key,)).fetchone() for key in keys]
        if any(row is None for row in fighters):
            raise KeyError("Fighter not found.")
        name = " vs ".join(row["name"] for row in fighters)
        if profile:
            return (name + " · UPSET", f"Review {name}’s UFC fight history, recorded stats and experimental UPSET rating.",
                    "/assets/favicon.png")
        before, window = share_parameters(query)
        image = "/share/" + "/".join(quote(key, safe="") for key in keys) + ".png"
        return (name + " · UPSET", f"Compare {name} using UFC fight history before {before}.",
                image + "?" + urlencode({"before": before, "window": window}))
    if resource == "event" and len(keys) == 1:
        event = route(database, "/api/event?" + urlencode({"slug": keys[0]}))
        name = event["name"] + (" · " + event["headline"] if event.get("headline") else "")
        return name + " · UPSET", f"Review the {event['date']} UFC card, matchups and available results.", "/assets/favicon.png"
    if resource == "fight" and len(keys) == 1:
        fight = route(database, "/api/fight?" + urlencode({"id": keys[0]}))
        name = " vs ".join(side["name"] for side in fight["fighters"])
        return (name + " · Fight Detail · UPSET",
                f"Review the official result and available fight statistics for {name} on {fight['date']}.",
                "/assets/favicon.png")
    raise KeyError("Page not found.")


def broadcast_html(template, title, description, image, address, target):
    host, port = address
    origin = f"http://{host}:{port}"
    canonical = escape(origin + target)
    tags = [f"<title>{escape(title)}</title>",
            f'<meta name="description" content="{escape(description)}">',
            f'<link rel="canonical" href="{canonical}">',
            '<meta property="og:type" content="website">',
            f'<meta property="og:title" content="{escape(title)}">',
            f'<meta property="og:description" content="{escape(description)}">',
            f'<meta property="og:image" content="{escape(origin + image)}">',
            f'<meta property="og:url" content="{canonical}">',
            '<meta name="twitter:card" content="summary_large_image">']
    template = template.replace('href="#/', 'href="/')
    return re.sub(r"<title>[^<]*</title>", lambda _: "\n".join(tags), template, count=1).encode()


def handler(database, design="broadcast"):
    page = DESIGNS[design]

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            try:
                target = urlsplit(self.path)
                path = target.path
                status = 200
                if path.startswith("/web/"):
                    name = path.removeprefix("/web/")
                    if name not in WEB_FILES:
                        raise KeyError(name)
                    body = files("upset").joinpath("web/" + name).read_bytes()
                    content_type = WEB_FILES[name]
                elif path.startswith("/assets/"):
                    name = path.removeprefix("/assets/")
                    if not ASSET_NAME.match(name):
                        raise KeyError(name)
                    body = files("upset").joinpath("web/assets/" + name).read_bytes()
                    content_type = ASSET_TYPES[name.rsplit(".", 1)[1].lower()]
                elif path.startswith("/media/"):
                    name = path.removeprefix("/media/")
                    if not ROSTER or not IMAGE_NAME.match(name):
                        raise KeyError(name)
                    body = (ROSTER["media_dir"] / name).read_bytes()
                    content_type = {"png": "image/png", "webp": "image/webp"}.get(name.rsplit(".", 1)[1].lower(), "image/jpeg")
                elif path == "/published/picks.json":
                    body = picks_file(PUBLISHED_PICKS, parse_qs(target.query).get("slug", [""])[0])
                    content_type = "application/json; charset=utf-8"
                elif path.startswith("/api/"):
                    body = json.dumps(route(database, self.path), allow_nan=False).encode()
                    content_type = "application/json; charset=utf-8"
                elif design == "broadcast" and path.startswith("/share/"):
                    keys = [unquote(key) for key in path.removeprefix("/share/").removesuffix(".png").split("/")]
                    if len(keys) != 2 or keys[0] == keys[1] or not path.endswith(".png"):
                        raise KeyError("Matchup preview not found.")
                    before, window = share_parameters(target.query)
                    with closing(connect(database)) as db:
                        reports = [enrich(database, fighter_report(db, key, before, window)) for key in keys]
                    from upset.research_share import matchup_png
                    body = matchup_png(reports, [portrait_path(report) for report in reports], before, window)
                    content_type = "image/png"
                elif design == "broadcast":
                    title, description, image = broadcast_metadata(database, path, target.query)
                    template = files("upset").joinpath("web/" + page).read_text()
                    body = broadcast_html(template, title, description, image, self.server.server_address,
                                          path + ("?" + target.query if target.query else ""))
                    content_type = "text/html; charset=utf-8"
                elif path == "/":
                    body = files("upset").joinpath("web/" + page).read_bytes()
                    content_type = "text/html; charset=utf-8"
                else:
                    raise KeyError("Page not found.")
            except (KeyError, FileNotFoundError):
                status = 404
                if path.startswith(("/api/", "/web/", "/assets/", "/media/", "/share/")):
                    body, content_type = b'{"error":"Not found"}', "application/json"
                else:
                    body = (b'<!doctype html><html lang="en"><meta charset="utf-8">'
                            b'<meta name="viewport" content="width=device-width, initial-scale=1">'
                            b'<title>Page not found | UPSET</title><h1>Page not found</h1>'
                            b'<p><a href="/">Return to UPSET</a></p></html>')
                    content_type = "text/html; charset=utf-8"
            except (ValueError, TypeError):
                body, status, content_type = b'{"error":"Invalid date, window or query"}', 400, "application/json"
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                # A new cutoff or route can cancel the browser's previous request.
                return

    return Handler


def main():
    global COVERAGE, EVENTS, FIGHT_ROUNDS, HISTORICAL_RESULTS, SKILL_PROFILES, MARKET_ODDS, PROVIDER_AUDIT, PUBLISHED_PICKS, RATING_SNAPSHOT, STRIKING_PREVIEW, UPSET_INDEX
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, default=Path("data/processed/research_v1/upset.sqlite"))
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--host", type=IPv4Address, default="127.0.0.1",
                        help="IPv4 address to listen on. Defaults to this Mac only.")
    parser.add_argument("--design", choices=DESIGNS, default="broadcast",
                        help="Choose the original broadcast site or the editorial experiment.")
    parser.add_argument("--roster", type=Path, default=None,
                        help="Optional roster JSON with contract status and image references (see web/ROSTER.md).")
    parser.add_argument("--striking-preview", type=Path, default=None,
                        help="Optional gate-passed experimental striking snapshot; raw statistics stay separate.")
    parser.add_argument("--rating-snapshot", type=Path, default=None,
                        help="Optional verified experimental overall-rating snapshot; career rating is independent of the stats window.")
    parser.add_argument("--coverage-review", type=Path, help="Reviewed current archive for startup reconciliation and pending-bout search.")
    parser.add_argument("--historical-results", type=Path, help="Verified official results without paired stats.")
    parser.add_argument("--professional-records", type=Path, help="Reviewed professional MMA record snapshots.")
    parser.add_argument("--event-names", type=Path, help="Event-title index built for this database (display only).")
    parser.add_argument("--fighter-aliases", type=Path, help="Nickname and former-name search index for this database.")
    parser.add_argument("--provider-audit", type=Path, help="Cross-provider result audit for this database.")
    parser.add_argument("--forecast-adjustment", type=Path,
                        help="Forecast revision 5.2 (age and debut-odds starting point) built for this snapshot.")
    parser.add_argument("--skill-profiles", type=Path, help="Multi-skill model output (skills JSON) for fighter skill profiles.")
    parser.add_argument("--market-archive", type=Path,
                        help="Daily odds archive (zip): flags big UPSET-vs-market disagreements on the next card.")
    parser.add_argument("--market-odds", type=Path,
                        help="Pre-fight betting market chances matched to this database (Upset Tracker).")
    parser.add_argument("--published-picks", type=Path, default=PUBLISHED_PICKS,
                        help="Folder of fingerprinted picks published before each card.")
    args = parser.parse_args()
    PUBLISHED_PICKS = args.published_picks
    try:
        manifest = json.loads((args.database.parent / "manifest.json").read_text())
        if _digest(args.database) != manifest["database_sha256"]:
            raise ValueError("Research database hash differs.")
        if args.coverage_review is not None:
            with closing(connect(args.database)) as db:
                COVERAGE = load_coverage(db, args.coverage_review, manifest)
                EVENTS, FIGHT_ROUNDS = load_event_archive(db, args.coverage_review, manifest)
        if args.historical_results is not None:
            with closing(connect(args.database)) as db:
                HISTORICAL_RESULTS = load_historical_results(db, args.historical_results, manifest["database_sha256"])
        if args.professional_records is not None:
            with closing(connect(args.database)) as db:
                PROFESSIONAL_RECORDS.update(load_professional_records(db, args.professional_records,
                                                                      manifest["database_sha256"]))
        if args.fighter_aliases is not None:
            FIGHTER_ALIASES.update(load_verified_json(args.fighter_aliases, "aliases.json",
                                                      manifest["database_sha256"], "fighter_aliases_v1")[0])
        if args.provider_audit is not None:
            PROVIDER_AUDIT = load_verified_json(args.provider_audit, "audit.json",
                                                manifest["database_sha256"], "provider_agreement_v1")[0]
        if args.skill_profiles is not None:
            with closing(connect(args.database)) as db:
                women = frozenset(uid for row in db.execute("SELECT payload FROM fights") for uid in (
                    json.loads(row["payload"]).get("upset_fighter_1_id"), json.loads(row["payload"]).get("upset_fighter_2_id"))
                    if "women" in (json.loads(row["payload"]).get("weight_class") or "").lower())
                last_division = {}
                for row in db.execute("SELECT payload FROM fights ORDER BY event_date"):
                    bout = json.loads(row["payload"])
                    label = " ".join(w for w in (bout.get("weight_class") or "").replace("UFC", "").split()
                                     if w.lower() not in ("bout", "title", "interim"))
                    if label and "catch" not in label.lower() and "open" not in label.lower():
                        last_division[bout.get("upset_fighter_1_id")] = last_division[bout.get("upset_fighter_2_id")] = label
            SKILL_PROFILES = SkillProfiles(args.skill_profiles, women, last_division)
        if args.market_odds is not None:
            MARKET_ODDS = load_verified_json(args.market_odds, "odds.json", manifest["database_sha256"], "market_odds_v1")[0]
        if args.event_names is not None:
            EVENT_NAMES.update(load_event_names(args.event_names, manifest["database_sha256"]))
        if args.striking_preview is not None:
            from upset.skill.striking_preview import load_preview
            STRIKING_PREVIEW = load_preview(args.striking_preview, args.database)
        if args.rating_snapshot is not None:
            from upset.ratings import serving, serving_v2, serving_v3, serving_v4, serving_v5

            rating_manifest = json.loads((args.rating_snapshot / "manifest.json").read_text())
            loaders = {module.VERSION: module.load_snapshot
                       for module in (serving, serving_v2, serving_v3, serving_v4, serving_v5)}
            if not isinstance(rating_manifest, dict) or rating_manifest.get("version") not in loaders:
                raise ValueError("Unknown experimental rating snapshot version.")
            RATING_SNAPSHOT = loaders[rating_manifest["version"]](args.rating_snapshot, args.database)
            if args.forecast_adjustment is not None:
                if rating_manifest["version"] != serving_v5.VERSION:
                    raise ValueError("The forecast adjustment needs the v5 rating snapshot.")
                ForecastAdjustment(args.forecast_adjustment, args.database, args.rating_snapshot).apply(RATING_SNAPSHOT)
            if rating_manifest["version"] in (serving_v4.VERSION, serving_v5.VERSION):
                with closing(connect(args.database)) as db:
                    upcoming = None if SCHEDULE["slug"] in EVENTS else event_detail(db, EVENTS, SCHEDULE["slug"])
                    if rating_manifest["version"] == serving_v5.VERSION:
                        def estimate(uid, before):
                            return estimate_on_saved_data(RATING_SNAPSHOT, args.database,
                                                          {"id": uid, "before": before, "window": 0})
                        UPSET_INDEX = build_upset_index_v5(db, args.database, RATING_SNAPSHOT, upcoming, estimate)
                        if MARKET_ODDS:
                            add_market_upsets(UPSET_INDEX, db, RATING_SNAPSHOT, MARKET_ODDS, estimate)
                    else:
                        UPSET_INDEX = build_upset_index(db, args.database, RATING_SNAPSHOT, upcoming)
        if args.market_archive is not None and MARKET_ODDS and getattr(RATING_SNAPSHOT, "forecast_adjustment", None):
            with closing(connect(args.database)) as db:
                next_card = None if SCHEDULE["slug"] in EVENTS else event_detail(db, EVENTS, SCHEDULE["slug"])
            UPCOMING_MARKET.update(scheduled_market(args.market_archive, next_card))
            DISAGREEMENT.update(disagreement_record(RATING_SNAPSHOT.forecasts, MARKET_ODDS))
        ROSTER.update(load_roster(args.roster))
        server = ThreadingHTTPServer((str(args.host), args.port), handler(args.database, args.design))
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.error(str(error))
    print(f"UPSET local research: http://{args.host}:{args.port}", flush=True)
    print("Read-only local viewer. Leave this terminal running; Ctrl+C stops it.", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
