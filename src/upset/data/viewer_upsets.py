"""Summarize reviewed results using each fighter's saved pre-bout grade."""

import json
from collections import defaultdict
from datetime import date, timedelta

from upset.data.viewer_events import reviewed_bout

MIN_PRIOR_BOUTS = 5
CLOSE_GAP = 3
DISPLAY_LIMIT = 12


def rated_side(snapshot, database, fighter, cutoff, bout_date):
    grade = snapshot.estimate(database, {"id": fighter["id"], "before": cutoff, "window": 0})
    if grade["status"] != "available" or grade["bouts"] < MIN_PRIOR_BOUTS:
        return None
    graded_on = date.fromisoformat(grade["event_date"])
    age = (date.fromisoformat(bout_date) - graded_on).days
    if not grade["event_date"] < cutoff or not 0 < age <= 730:
        return None
    return {**fighter, "grade": grade["score"], "graded_on": grade["event_date"],
            "prior_bouts": grade["bouts"]}


def close_matchups(snapshot, database, scheduled, latest):
    if scheduled is None or scheduled["date"] <= latest:
        return None
    cutoff = (date.fromisoformat(latest) + timedelta(days=1)).isoformat()
    matches = []
    for bout in scheduled["bouts"]:
        if not all(fighter["id"] for fighter in bout["fighters"]):
            continue
        sides = [rated_side(snapshot, database, fighter, cutoff, scheduled["date"]) for fighter in bout["fighters"]]
        if all(sides):
            gap = abs(sides[0]["grade"] - sides[1]["grade"])
            if gap <= CLOSE_GAP:
                matches.append({"fighters": sides, "gap": gap})
    return {"slug": scheduled["slug"], "name": scheduled["name"], "date": scheduled["date"],
            "before": cutoff, "bouts": matches}


def build_upset_index(db, database, snapshot, scheduled):
    first = snapshot.metadata["display_curve"]["reference_before"]
    latest = snapshot.metadata["latest_event"]
    recent_since = (date.fromisoformat(latest) - timedelta(days=364)).isoformat()
    lower_graded_bouts = defaultdict(int)
    recent_wins = defaultdict(list)
    upsets = []
    eligible_bouts = 0

    rows = db.execute("SELECT id,payload FROM fights WHERE event_date BETWEEN ? AND ? "
                      "ORDER BY event_date DESC,id", (first, latest))
    for row in rows:
        bout = reviewed_bout(json.loads(row["payload"]), row["id"])
        if bout["outcome"] != "decisive":
            continue
        day = bout["date"]
        sides = [rated_side(snapshot, database, fighter, day, day) for fighter in bout["fighters"]]
        if not all(sides):
            continue
        eligible_bouts += 1
        low, high = sorted(sides, key=lambda fighter: fighter["grade"])
        gap = high["grade"] - low["grade"]
        if not gap:
            continue
        if day >= recent_since:
            lower_graded_bouts[low["id"]] += 1
        if bout["winner_id"] == low["id"]:
            upset = {"id": bout["id"], "date": day, "method": bout["method"], "title": bout["title"],
                     "winner": low, "opponent": high, "gap": gap}
            upsets.append(upset)
            if day >= recent_since:
                recent_wins[low["id"]].append(upset)

    repeat_winners = []
    for uid, wins in recent_wins.items():
        if len(wins) >= 2:
            repeat_winners.append({"fighter": wins[0]["winner"], "wins": len(wins),
                                   "opportunities": lower_graded_bouts[uid], "recent_results": wins})
    repeat_winners.sort(key=lambda row: (-row["wins"], row["opportunities"], row["fighter"]["name"]))
    biggest = sorted(upsets, key=lambda bout: (bout["gap"], bout["date"], bout["id"]), reverse=True)
    return {"first": first, "latest": latest, "recent_since": recent_since, "minimum_prior_bouts": MIN_PRIOR_BOUTS,
            "eligible_bouts": eligible_bouts, "upset_count": len(upsets), "close_gap": CLOSE_GAP,
            "biggest": biggest[:DISPLAY_LIMIT], "latest_upsets": upsets[:DISPLAY_LIMIT],
            "repeat_winners": repeat_winners[:DISPLAY_LIMIT],
            "upcoming": close_matchups(snapshot, database, scheduled, latest)}
