"""Upset Tracker for UPSET Rating v5: the v4-style rating-gap lists plus each winner's
walk-forward forecast chance, and a "longest shots" list ranked by that chance.

The forecast for a fight was computed only from fights before its date, so a winner's
chance is what UPSET would have said beforehand, not a hindsight score.
"""

import json

from upset.data.viewer_events import reviewed_bout
from upset.data.viewer_upsets import DISPLAY_LIMIT, build_upset_index, rated_side

MIN_PRIOR_DECISIVE = 3


def winner_chance(snapshot, fight_id, winner_id):
    item = snapshot.forecasts.get(fight_id)
    if item is None or winner_id not in item["fighter_ids"]:
        return None
    p = item["forecast"]
    return p if item["fighter_ids"][0] == winner_id else 1 - p


def build_upset_index_v5(db, database, snapshot, scheduled, estimate):
    index = build_upset_index(db, database, snapshot, scheduled)
    entries = index["biggest"] + index["latest_upsets"] + [
        result for row in index["repeat_winners"] for result in row["recent_results"]]
    for upset in entries:
        upset["winner_chance"] = winner_chance(snapshot, upset["id"], upset["winner"]["id"])

    shots, eligible = [], 0
    rows = db.execute("SELECT id,payload FROM fights WHERE event_date BETWEEN ? AND ? ORDER BY event_date DESC,id",
                      (index["first"], index["latest"]))
    for row in rows:
        bout = reviewed_bout(json.loads(row["payload"]), row["id"])
        item = snapshot.forecasts.get(bout["id"])
        if bout["outcome"] != "decisive" or item is None or min(item["prior_decisive_bouts"]) < MIN_PRIOR_DECISIVE:
            continue
        day = bout["date"]
        sides = [rated_side(snapshot, database, fighter, day, day) for fighter in bout["fighters"]]
        if not all(sides):
            continue
        winner = next(side for side in sides if side["id"] == bout["winner_id"])
        loser = next(side for side in sides if side["id"] != bout["winner_id"])
        chance = winner_chance(snapshot, bout["id"], winner["id"])
        if chance is None:
            continue
        eligible += 1
        if chance >= .5:
            continue
        shots.append({"id": bout["id"], "date": day, "method": bout["method"], "title": bout["title"],
                      "winner": winner, "opponent": loser, "gap": loser["grade"] - winner["grade"],
                      "winner_chance": chance})
    index["forecast_upsets"] = len(shots)
    index["forecast_eligible"] = eligible
    index["title_upsets"] = [shot for shot in shots if shot["title"]]
    index["longest_shots"] = sorted(shots, key=lambda u: (u["winner_chance"], u["date"]))[:DISPLAY_LIMIT]
    index["latest_forecast_upsets"] = shots[:DISPLAY_LIMIT]

    upcoming = index.get("upcoming")
    if upcoming:
        for bout in upcoming["bouts"]:
            pair = [estimate(fighter["id"], upcoming["before"]) for fighter in bout["fighters"]]
            bout["forecast"] = snapshot.matchup(*pair)
    record = snapshot.evaluation["metrics"]["v5_forecast"]
    index["forecast_basis"] = {
        "label": "Winner's chance from the UPSET forecast, computed only from earlier fights.",
        "minimum_prior_decisive_bouts": MIN_PRIOR_DECISIVE,
        "record_since_2019": record["test"], "record_since_2025": record["recent"],
        "market_check": snapshot.evaluation.get("market")}
    return index
