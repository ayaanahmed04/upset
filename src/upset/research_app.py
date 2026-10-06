"""Local fighter research viewer. Run with python -m upset.research_app."""

import argparse
import json
import re
import sqlite3
from bisect import bisect_left, bisect_right
from contextlib import closing
from datetime import UTC, date, datetime
from functools import lru_cache
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.resources import files
from pathlib import Path
from statistics import median
from urllib.parse import parse_qs, urlsplit

from upset.data.audit_cito_archive import _name
from upset.data.collect_cito_archive import _digest
from upset.data.reviewed_bout_metadata import reviewed_title_evidence


def connect(database):
    db = sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    return db


def metadata(db):
    return {r["key"]: json.loads(r["value"]) for r in db.execute("SELECT * FROM metadata")}


def search(db, query):
    if len(query) > 100:
        raise ValueError("Search is limited to 100 characters.")
    # Normalize name tokens; all user values still use SQL parameters.
    terms = [_name(part) for part in query.split()]
    terms = [t for t in terms if t]
    if not terms:
        return []
    where = " AND ".join("search_name LIKE ?" for _ in terms)
    matches = db.execute("SELECT id,name,profile,(SELECT COUNT(*) FROM stats WHERE fighter_id=fighters.id) AS bouts "
                         "FROM fighters WHERE " + where + " ORDER BY bouts DESC,name,id LIMIT 25",
                         tuple("%" + term + "%" for term in terms)).fetchall()
    results = []
    for r in matches:
        latest = db.execute("""SELECT event_date,payload FROM fights WHERE fighter_1=? OR fighter_2=?
                               ORDER BY event_date DESC,id DESC LIMIT 1""", (r["id"], r["id"])).fetchone()
        results.append({"id": r["id"], "name": r["name"], "source_fighter_id": json.loads(r["profile"])["source_fighter_id"],
                        "recorded_bouts": r["bouts"], "last_bout": latest["event_date"] if latest else None,
                        "division": division(json.loads(latest["payload"])["weight_class"]) if latest else None})
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
        title_evidence = reviewed_title_evidence(fight)
        history.append({"fight_id": record["id"], "date": fight["event_date"],
                        "opponent_id": opponent, "opponent": fight[f"fighter_{other}_name"],
                        "outcome": reviewed_outcome, "frozen_outcome": frozen_outcome,
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
             "sig_landed_per_minute": ratio(own("sig_strikes_landed"), minutes),
             "sig_absorbed_per_minute": ratio(opposing("sig_strikes_landed"), minutes),
             "sig_differential_per_minute": ratio(own("sig_strikes_landed") - opposing("sig_strikes_landed"), minutes),
             "striking_accuracy": ratio(own("sig_strikes_landed"), own("sig_strikes_attempted")),
             "striking_defense": None if not strike_attempts else 1 - opposing("sig_strikes_landed") / strike_attempts,
             "takedowns_per_15_minutes": ratio(own("takedowns_landed") * 15, minutes),
             "takedown_accuracy": ratio(own("takedowns_landed"), own("takedowns_attempted")),
             "takedown_defense": None if not td_attempts else 1 - opposing("takedowns_landed") / td_attempts,
             "opponent_takedown_attempts": td_attempts, "opponent_strike_attempts": strike_attempts,
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
    streak_kind, streak = (history[0]["outcome"], 0) if history else (None, 0)
    for r in history:
        if r["outcome"] != streak_kind:
            break
        streak += 1
    # Most common division over the last five classified bouts; ties go to the most recent.
    divisions = [r["division"] for r in history if r["division"]][:5]
    divisions = sorted(divisions, key=divisions.count, reverse=True)
    summary = {"career": {k: sum(r["outcome"] == k for r in history) for k in ("win", "loss", "other")},
               "streak": {"outcome": streak_kind, "count": streak},
               "last_bout": history[0]["date"] if history else None, "first_bout": history[-1]["date"] if history else None,
               "division": divisions[0] if divisions else None,
               "title_bouts": sum(r["title_bout"] for r in history),
               "age": age_on(profile.get("date_of_birth"), cutoff)}
    for r in history:
        r["sig_differential_per_minute"] = ratio(r["own"]["sig_strikes_landed"] - r["opponent_stats"]["sig_strikes_landed"], r["own"]["fight_duration_seconds"] / 60)
    return {"id": uid, "name": row["name"], "profile": profile, "before": before,
            "window": window, "available_bouts": len(history), "metrics": stats, "history": history,
            "summary": summary,
            "interpretation": "Fight-date filter with currently reviewed outcomes and title metadata; not a reconstruction of when amendments became available. Profile measurements are from the frozen profile snapshot."}


PERCENTILE_KEYS = ("sig_landed_per_minute", "sig_absorbed_per_minute", "sig_differential_per_minute",
                   "striking_accuracy", "striking_defense", "takedowns_per_15_minutes", "takedown_accuracy",
                   "takedown_defense", "knockdowns_per_15_minutes", "control_margin_seconds_per_minute",
                   "submission_attempts_per_15_minutes")
POOL_MIN_BOUTS = 3
POOL_MIN_MINUTES = 15


@lru_cache(maxsize=16)
def distributions(database, before, window):
    """Sorted metric values for every fighter with enough timed evidence under the same cutoff and window."""
    pools = {}
    with closing(connect(database)) as db:
        for (uid,) in db.execute("SELECT DISTINCT fighter_id FROM stats").fetchall():
            report = fighter_report(db, uid, before, window)
            m = report["metrics"]
            if m["timed_bouts"] < POOL_MIN_BOUTS or m["minutes"] < POOL_MIN_MINUTES:
                continue
            for scope in ("All divisions", report["summary"]["division"]):
                if scope is None:
                    continue
                pool = pools.setdefault(scope, {"fighters": 0, "values": {k: [] for k in PERCENTILE_KEYS}})
                pool["fighters"] += 1
                for key in PERCENTILE_KEYS:
                    if m[key] is not None:
                        pool["values"][key].append(m[key])
    for pool in pools.values():
        for values in pool["values"].values():
            values.sort()
    return pools


def percentiles(database, report):
    """Mid-rank percentile of each window metric against fighters in the same division (or all, if the pool is thin)."""
    m = report["metrics"]
    if m["timed_bouts"] < POOL_MIN_BOUTS or m["minutes"] < POOL_MIN_MINUTES:
        return {"eligible": False, "reason": f"Needs {POOL_MIN_BOUTS}+ timed bouts and {POOL_MIN_MINUTES}+ minutes in the window."}
    pools = distributions(database, report["before"], report["window"])
    scope = report["summary"]["division"]
    if scope not in pools or pools[scope]["fighters"] < 25:
        scope = "All divisions"
    pool = pools[scope]
    out = {"eligible": True, "scope": scope, "pool_fighters": pool["fighters"], "values": {}}
    for key in PERCENTILE_KEYS:
        values, value = pool["values"][key], m[key]
        if value is None or not values:
            out["values"][key] = None
            continue
        below, through = bisect_left(values, value), bisect_right(values, value)
        out["values"][key] = {"percentile": 100 * (below + through) / 2 / len(values),
                              "median": median(values), "pool": len(values)}
    return out


ROSTER = {}
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


def enrich(database, report):
    report["percentiles"] = percentiles(database, report)
    report["roster"] = roster_entry(report)
    return report


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
                                      "result_amended": bool(row["reviewed_result"])})
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
        if parts.path == "/api/meta":
            return metadata(db)
        if parts.path == "/api/fighters":
            return search(db, params.get("q", [""])[0])
        before = params.get("before", [datetime.now(UTC).date().isoformat()])[0]
        window = int(params.get("window", ["5"])[0])
        if parts.path == "/api/fighter":
            return enrich(database, fighter_report(db, params.get("id", [""])[0], before, window))
        if parts.path == "/api/compare":
            a, b = params.get("a", [""])[0], params.get("b", [""])[0]
            if a == b:
                raise ValueError("Choose two different fighters.")
            reports = [enrich(database, fighter_report(db, uid, before, window)) for uid in (a, b)]
            return {"fighters": reports, "common_opponents": common_opponents(reports)}
    raise KeyError("Page not found.")


DESIGNS = {"broadcast": "research.html", "editorial": "research_editorial.html"}
WEB_FILES = {
    "research_about.css": "text/css; charset=utf-8",
    "research_about.js": "text/javascript; charset=utf-8",
    "research_base.css": "text/css; charset=utf-8",
    "research_editorial.css": "text/css; charset=utf-8",
    "research_editorial.js": "text/javascript; charset=utf-8",
}


def handler(database, design="broadcast"):
    page = DESIGNS[design]

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            try:
                path = urlsplit(self.path).path
                if path == "/":
                    body = files("upset").joinpath("web/" + page).read_bytes()
                    content_type = "text/html; charset=utf-8"
                elif path.startswith("/web/"):
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
                else:
                    body = json.dumps(route(database, self.path), allow_nan=False).encode()
                    content_type = "application/json; charset=utf-8"
                status = 200
            except (KeyError, FileNotFoundError):
                body, status, content_type = b'{"error":"Not found"}', 404, "application/json"
            except (ValueError, TypeError):
                body, status, content_type = b'{"error":"Invalid date, window or query"}', 400, "application/json"
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(body)

    return Handler


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, default=Path("data/processed/research_v1/upset.sqlite"))
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--design", choices=DESIGNS, default="broadcast",
                        help="Choose the original broadcast site or the editorial experiment.")
    parser.add_argument("--roster", type=Path, default=None,
                        help="Optional roster JSON with contract status and image references (see web/ROSTER.md).")
    args = parser.parse_args()
    try:
        manifest = json.loads((args.database.parent / "manifest.json").read_text())
        if _digest(args.database) != manifest["database_sha256"]:
            raise ValueError("Research database hash differs.")
        ROSTER.update(load_roster(args.roster))
        server = ThreadingHTTPServer(("127.0.0.1", args.port), handler(args.database, args.design))
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.error(str(error))
    print(f"UPSET local research: http://127.0.0.1:{args.port}", flush=True)
    print("Read-only local viewer. Leave this terminal running; Ctrl+C stops it.", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
