"""Local fighter research viewer. Run with python -m upset.research_app."""

import argparse
import json
import sqlite3
from contextlib import closing
from datetime import UTC, date, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.resources import files
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from upset.data.audit_cito_archive import _name
from upset.data.collect_cito_archive import _digest


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
    matches = db.execute("SELECT id,name,profile FROM fighters WHERE " + where + " ORDER BY name,id LIMIT 25",
                         tuple("%" + term + "%" for term in terms)).fetchall()
    return [{"id": r["id"], "name": r["name"], "source_fighter_id": json.loads(r["profile"])["source_fighter_id"],
             "recorded_bouts": db.execute("SELECT COUNT(*) FROM stats WHERE fighter_id=?", (r["id"],)).fetchone()[0]} for r in matches]


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
        history.append({"fight_id": record["id"], "date": fight["event_date"],
                        "opponent_id": opponent, "opponent": fight[f"fighter_{other}_name"],
                        "outcome": reviewed_outcome, "frozen_outcome": frozen_outcome,
                        "method": amendment["result_method"] if amendment else fight["result_method"],
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
             "control_observed_bouts": len(controlled), "control_observed_minutes": control_seconds / 60}
    for r in history:
        r["sig_differential_per_minute"] = ratio(r["own"]["sig_strikes_landed"] - r["opponent_stats"]["sig_strikes_landed"], r["own"]["fight_duration_seconds"] / 60)
    return {"id": uid, "name": row["name"], "profile": profile, "before": before,
            "window": window, "available_bouts": len(history), "metrics": stats, "history": history,
            "interpretation": "Fight-date filter with currently reviewed outcomes; not a reconstruction of when each result amendment became available. Profile measurements are from the frozen profile snapshot."}


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
            return fighter_report(db, params.get("id", [""])[0], before, window)
        if parts.path == "/api/compare":
            a, b = params.get("a", [""])[0], params.get("b", [""])[0]
            if a == b:
                raise ValueError("Choose two different fighters.")
            return {"fighters": [fighter_report(db, uid, before, window) for uid in (a, b)]}
    raise KeyError("Page not found.")


def handler(database):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            try:
                if urlsplit(self.path).path == "/":
                    body = files("upset").joinpath("web/research.html").read_bytes()
                    content_type = "text/html; charset=utf-8"
                else:
                    body = json.dumps(route(database, self.path), allow_nan=False).encode()
                    content_type = "application/json; charset=utf-8"
                status = 200
            except KeyError:
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
    args = parser.parse_args()
    try:
        manifest = json.loads((args.database.parent / "manifest.json").read_text())
        if _digest(args.database) != manifest["database_sha256"]:
            raise ValueError("Research database hash differs.")
        server = ThreadingHTTPServer(("127.0.0.1", args.port), handler(args.database))
    except (OSError, ValueError, KeyError) as error:
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
