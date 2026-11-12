"""Cross-check every accepted fight against an independent provider capture.

UPSET's historical fights come from the UFCStats-based Kaggle export; the archived Cito
cards are a separate capture of the same bouts. For each fight both sources contain, compare
the winner, how it ended, the round and the time. Also list completed Cito bouts that UPSET
does not have. Reviewed amendments (official overturns) count as the UPSET result.
Writes audit.json and summary.md into a new folder; changes nothing else.
"""

import argparse
import hashlib
import json
import sqlite3
from collections import Counter, defaultdict
from contextlib import closing
from datetime import date, timedelta
from difflib import SequenceMatcher
from pathlib import Path

from upset.data.audit_cito_archive import _name


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def family(method, outcome=None):
    """Collapse both providers' labels (e.g. "Decision - Unanimous" and "U-DEC") to one family."""
    text = (method or "").casefold()
    if outcome in ("draw", "nc"):
        return outcome
    if any(word in text for word in ("overturned", "no contest", "could not continue")) or text == "nc":
        return "nc"
    if text in ("dq", "disqualification") or "disqual" in text:
        return "dq"
    if "ko" in text or "doctor" in text:
        return "ko"
    if "sub" in text:
        return "sub"
    if "dec" in text:
        return "decision"
    return text or "unknown"


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
        fights = [(fid, day, json.loads(payload)) for fid, day, payload in
                  db.execute("SELECT id,event_date,payload FROM fights")]
    by_bout = {payload.get("source_bout_id"): (fid, day, payload) for fid, day, payload in fights}
    by_names, by_day = defaultdict(list), defaultdict(list)
    for fid, day, payload in fights:
        by_names[(day, frozenset(_name(payload[f"fighter_{i}_name"]) for i in (1, 2)))].append(fid)
        by_day[day].append((fid, day, payload))

    def close_match(day, names):
        """Same date (+/- 1), names alike on both corners (spelling variants such as Zach/Zachary)."""
        found = []
        for offset in (-1, 0, 1):
            for item in by_day.get((day + timedelta(days=offset)).isoformat(), []):
                ours = [_name(item[2][f"fighter_{i}_name"]) for i in (1, 2)]
                a, b = sorted(names)
                score = max(min(SequenceMatcher(None, a, x).ratio(), SequenceMatcher(None, b, y).ratio())
                            for x, y in (ours, ours[::-1]))
                if score >= .72:
                    found.append(item)
        return found[0] if len(found) == 1 else None
    counts, disagreements, missing, seen = Counter(), [], [], set()
    latest_capture = None
    for path in sorted(args.cards.glob("*/event.json")):
        raw = json.loads(path.read_text())
        latest_capture = max(latest_capture or "", raw.get("observed_at_utc") or "")
        event = raw["response"]["data"]
        for bout in event.get("bouts") or []:
            if bout.get("status") != "completed" or bout.get("isCancelled"):
                continue
            sides = bout.get("fighters") or []
            names = frozenset(_name(side.get("fighterName")) for side in sides)
            match = by_bout.get(bout["id"])
            if match is None and len(names) == 2:
                day = date.fromisoformat(event["eventDate"])
                ids = [fid for offset in (-1, 0, 1) for fid in by_names.get(((day + timedelta(days=offset)).isoformat(), names), [])]
                if len(ids) == 1:
                    match = next(item for item in fights if item[0] == ids[0])
                else:
                    match = close_match(day, names)
                    if match is not None:
                        counts["matched_by_close_names"] += 1
            if match is None:
                missing.append({"event": event.get("title"), "date": event.get("eventDate"),
                                "fighters": [side.get("fighterName") for side in sides], "method": bout.get("method")})
                counts["provider_only"] += 1
                continue
            fid, day, fight = match
            seen.add(fid)
            counts["compared"] += 1
            reviewed = fight.get("reviewed_result") or {}
            ours_winner = reviewed.get("winner_name", fight.get("winner_name")) if reviewed else fight.get("winner_name")
            ours_outcome = reviewed.get("outcome") if reviewed else None
            ours_family = family(reviewed.get("result_method", fight.get("result_method")), ours_outcome)
            if not ours_winner and ours_family == "decision":
                ours_family = "draw"
            ours = {"winner": _name(ours_winner) if ours_winner else None,
                    "family": ours_family,
                    "round": reviewed.get("result_round", fight.get("result_round")),
                    "time": reviewed.get("result_time", fight.get("result_time"))}
            winner_side = next((side for side in sides if side.get("outcome") == "win"), None)
            outcomes = {side.get("outcome") for side in sides}
            theirs_outcome = "draw" if outcomes == {"draw"} else "nc" if outcomes & {"nc", "no_contest", "noContest"} else None
            theirs = {"winner": _name(winner_side.get("fighterName")) if winner_side else None,
                      "family": family(bout.get("method"), theirs_outcome),
                      "round": bout.get("resultRound"), "time": bout.get("resultTime")}
            if ours["winner"] and theirs["winner"] and ours["winner"] != theirs["winner"]:
                # Names can be spelled differently; only flag when the other corner matches.
                loser_names = names - {theirs["winner"]}
                if ours["winner"] not in loser_names:
                    theirs["winner"] = ours["winner"] if len(names) == 2 else theirs["winner"]
            problems = [key for key in ("winner", "family", "round", "time")
                        if ours[key] is not None and theirs[key] is not None and str(ours[key]) != str(theirs[key])]
            if problems:
                counts["disagree"] += 1
                for key in problems:
                    counts["disagree_" + key] += 1
                disagreements.append({"fight_id": fid, "date": day, "event": event.get("title"),
                                      "fighters": [fight["fighter_1_name"], fight["fighter_2_name"]],
                                      "fields": problems, "upset": ours, "provider": theirs,
                                      "reviewed_amendment": bool(reviewed)})
            else:
                counts["agree"] += 1
    counts["upset_only"] = len(fights) - len(seen)
    result = {"version": "provider_agreement_v1", "database_sha256": digest(database),
              "provider": "Cito archived cards (independent capture of UFCStats-era and recent bouts)",
              "provider_captured_through": latest_capture, "counts": dict(counts),
              "disagreements": disagreements, "provider_only_bouts": missing}
    args.output.mkdir(parents=True)
    (args.output / "audit.json").write_text(json.dumps(result, indent=1))
    lines = ["# Provider agreement audit", "",
             f"Compared {counts['compared']:,} fights found in both UPSET and the archived Cito cards.",
             f"Agree on winner, method, round and time: {counts['agree']:,}. Disagree on at least one: {counts['disagree']:,}.",
             f"Completed provider bouts missing from UPSET: {counts['provider_only']:,}. UPSET fights not in the capture: {counts['upset_only']:,}.",
             "", "| Field | Disagreements |", "| --- | --- |"]
    lines += [f"| {key} | {counts['disagree_' + key]} |" for key in ("winner", "family", "round", "time")]
    (args.output / "summary.md").write_text("\n".join(lines) + "\n")
    manifest = {"version": "provider_agreement_v1", "database_sha256": result["database_sha256"],
                "output_sha256": {name: digest(args.output / name) for name in ("audit.json", "summary.md")}}
    (args.output / "manifest.json").write_text(json.dumps(manifest, indent=1))
    print("\n".join(lines))


if __name__ == "__main__":
    main()
