"""Round-by-round profiles for fighter pages.

Built from the audited Cito round rows (see upset.ratings.round_research): every round used adds
up to the fight totals in the database. For each fighter this keeps rounds won on a judges-style
score, strikes thrown per minute by round, output in rounds where the fighter is wrestled, and the
last few fights round by round. Percentiles compare with UFC fighters active since 2023 who have
at least 15 rounds. Descriptive only: none of this feeds the forecast (it did not help it).

    python -m upset.data.round_profiles --database ... --bridge ... --current ... --output DIR
"""

import argparse
import hashlib
import json
import sqlite3
from collections import Counter, defaultdict
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from upset.ratings import round_research as RR

VERSION = "round_profiles_v1"
RECENT = 6
COMPARE_MIN_ROUNDS = 15
COMPARE_ACTIVE_FROM = "2023-01-01"
MIN_ROUNDS_FOR_AVERAGES = 10
MIN_MINUTES = 10.0
MIN_WRESTLED_MINUTES = 5.0


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def finish_code(method):
    text = (method or "").upper()
    if text.startswith(("KO", "TKO")):
        return "KO"
    if text.startswith("SUB"):
        return "SUB"
    if "DQ" in text or "DISQUAL" in text:
        return "DQ"
    return None


def load_results(database):
    results, names = {}, {}
    with closing(sqlite3.connect(database)) as db:
        names = {uid: name for uid, name in db.execute("SELECT id,name FROM fighters")}
        for fid, payload in db.execute("SELECT id,payload FROM fights"):
            p = json.loads(payload)
            result = p.get("reviewed_result") or p
            corner = [p.get("fighter_1_name"), p.get("fighter_2_name")]
            winner = result.get("winner_name")
            method = result.get("result_method") or p.get("result_method") or ""
            results[fid] = {"winner": corner.index(winner) if winner in corner else None, "method": method}
    return results, names


def outcome(result, side):
    if result["winner"] is not None:
        return "W" if result["winner"] == side else "L"
    method = result["method"].lower()
    return "D" if method.startswith("decision") else "NC"   # no contest, overturned, could not continue


def strip(fid, fight, lines, side, result, names):
    """One past fight, round by round, from this fighter's side."""
    won = outcome(result, side)
    rounds = []
    for line in lines:
        own, opp = line["rows"][side], line["rows"][1 - side]
        g = lambda r, k: r.get(k) or 0
        detail = [g(own, "sig_strikes_landed"), g(opp, "sig_strikes_landed"), g(own, "takedowns_landed"),
                  g(opp, "takedowns_landed"), g(own, "control_seconds"), g(opp, "control_seconds"),
                  g(own, "knockdowns"), g(opp, "knockdowns")]
        if line["full"]:
            score = RR.judge(own, opp)
            code = "W" if score > 0 else "L" if score < 0 else "E"
        else:
            code = "F" if won == "W" else "X" if won == "L" else "-"
        rounds.append({"code": code, "d": detail})
    opponent = fight["ids"][1 - side]
    return {"fight_id": fid, "date": fight["day"], "opponent_id": opponent,
            "opponent": names.get(opponent) or fight["names"][1 - side], "result": won,
            "finish": finish_code(result["method"]), "rounds": rounds}


def percentile(values, value):
    if value is None or not values:
        return None
    below = sum(v < value for v in values)
    equal = sum(v == value for v in values)
    return round(100 * (below + equal / 2) / len(values))


def build(database, bridge, current):
    fights, stats = RR.load_fights(database)
    rounds, dropped, conflicts = RR.load_rounds(bridge, current, fights)
    good, audit = RR.audit(rounds, stats, fights, conflicts)
    lines = {fid: RR.round_lines(fights[fid], by) for fid, by in good.items() if fights[fid]["day"] >= RR.ROUND_RULES_FROM}
    lines = {fid: v for fid, v in lines.items() if v}
    results, names = load_results(database)
    league = RR.league([ln for fid, v in lines.items() if RR.TRAIN[0] <= fights[fid]["day"] <= RR.TRAIN[1] for ln in v])
    winners = {fid: r["winner"] for fid, r in results.items()
               if r["winner"] is not None and r["method"].lower().startswith("decision")}
    judging = RR.decision_check(fights, lines, winners)

    history = defaultdict(Counter)
    by_round = defaultdict(lambda: defaultdict(lambda: [0.0, 0, 0]))
    recent, last = defaultdict(list), {}
    for fid in sorted(lines, key=lambda f: (fights[f]["day"], f)):
        fight = fights[fid]
        for side, uid in enumerate(fight["ids"]):
            for line in lines[fid]:
                RR.update(history[uid], line, side)
                cell = by_round[uid][line["n"]]
                cell[0] += line["minutes"]
                cell[1] += line["rows"][side].get("sig_strikes_attempted") or 0
                cell[2] += line["rows"][side].get("sig_strikes_landed") or 0
            recent[uid].append(strip(fid, fight, lines[fid], side, results[fid], names))
            last[uid] = fight["day"]

    def measures(h):
        pace = lambda part: h[part + "_att"] / h[part + "_min"]
        out = {"won": h["won"] / h["rounds"] if h["rounds"] else None, "late": None, "keep": None}
        if h["r1_min"] >= MIN_MINUTES and h["late_min"] >= MIN_MINUTES and h["r1_att"] > 0:
            out["late"] = pace("late") / pace("r1") - 1
        if h["wr_min"] >= MIN_WRESTLED_MINUTES and h["clean_min"] >= MIN_MINUTES and h["clean_att"] > 0:
            out["keep"] = pace("wr") / pace("clean") - 1
        return out

    group = [uid for uid, h in history.items() if h["all_rounds"] >= COMPARE_MIN_ROUNDS and last[uid] >= COMPARE_ACTIVE_FROM]
    values = {key: [m[key] for m in (measures(history[u]) for u in group) if m[key] is not None]
              for key in ("won", "late", "keep")}

    fighters = {}
    for uid, h in history.items():
        m = measures(h)
        enough = h["all_rounds"] >= MIN_ROUNDS_FOR_AVERAGES
        pace_rows = [{"round": n, "minutes": round(c[0], 1), "thrown": round(c[1] / c[0], 1), "landed": round(c[2] / c[0], 1)}
                     for n, c in sorted(by_round[uid].items()) if c[0] >= 1]
        fighters[uid] = {
            "rounds": h["all_rounds"], "scored": h["rounds"], "won": h["won"],
            "won_pct": round(100 * m["won"]) if m["won"] is not None else None,
            "pace": pace_rows,
            "r1": round(h["r1_att"] / h["r1_min"], 1) if m["late"] is not None else None,
            "later": round(h["late_att"] / h["late_min"], 1) if m["late"] is not None else None,
            "late_change": round(100 * m["late"]) if m["late"] is not None else None,
            "wrestled": ({"minutes": round(h["wr_min"], 1), "thrown": round(h["wr_att"] / h["wr_min"], 1),
                          "clean": round(h["clean_att"] / h["clean_min"], 1), "change": round(100 * m["keep"])}
                         if m["keep"] is not None else None),
            "wrestles_pct": round(100 * h["wrestling_rounds"] / h["all_rounds"]) if h["all_rounds"] else None,
            "percentiles": ({key: percentile(values[key], m[key]) for key in ("won", "late", "keep") if m[key] is not None}
                            if enough else {}),
            "recent": recent[uid][::-1][:RECENT],
            "fights_with_rounds": len(recent[uid]),
            "last_fight": last[uid],
        }
    summary = {"league": {"late_change": round(100 * (league["late_pace"] / league["r1_pace"] - 1)),
                          "keep_change": round(100 * (league["wr_pace"] / league["clean_pace"] - 1)),
                          "compared_with": len(group), "judging_agrees": round(100 * judging["round_score_agrees"]),
                          "decisions_checked": judging["decisions"]},
               "audit": dict(audit), "rows_left_out": dict(dropped), "bouts_used": len(lines)}
    return fighters, summary


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--bridge", type=Path, required=True)
    parser.add_argument("--current", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit(f"{args.output} exists; write a new version instead.")
    fighters, summary = build(args.database, args.bridge, args.current)
    args.output.mkdir(parents=True)
    out = args.output / "rounds.json"
    out.write_text(json.dumps({"version": VERSION, **summary, "fighters": fighters}, separators=(",", ":"), sort_keys=True) + "\n")
    inputs = [args.bridge / "round_stats_staged.jsonl", args.bridge / "bout_matches.jsonl", args.current / "rounds_staged.jsonl"]
    manifest = {"version": VERSION, "database_sha256": digest(args.database),
                "inputs_sha256": {str(p): digest(p) for p in inputs},
                "output_sha256": {"rounds.json": digest(out)}, "fighters": len(fighters),
                "built_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "tool": "src/upset/data/round_profiles.py"}
    (args.output / "manifest.json").write_text(json.dumps(manifest, indent=1) + "\n")
    print(json.dumps({k: v for k, v in summary.items()}, indent=1), len(fighters), "fighters")


def profile(data, uid):
    """API view of one fighter, or an 'unavailable' status."""
    item = data["fighters"].get(uid)
    if not item or not item["recent"]:
        return {"status": "unavailable"}
    return {"status": "available", **item, "league": data["league"]}


if __name__ == "__main__":
    main()
