"""Upset Tracker by the betting market: every UFC fight since 2010 that the market's underdog won.

The market is the usual definition of an upset and covers debuts, which the UPSET rating can't
judge well (a debut fighter has no UFC record yet). Each upset also shows what the UPSET forecast
said going in, and how many of them UPSET saw coming.
"""

import json
from datetime import date, timedelta

from upset.data.viewer_events import reviewed_bout

LIST_LIMIT = 60
UPSET_LINE = 0.45  # a clear underdog: under a 45% market chance, about +120 or longer


def side(estimate, fighter, day):
    grade = estimate(fighter["id"], day) if fighter.get("id") else None
    available = grade is not None and grade.get("status") == "available"
    return {"id": fighter.get("id"), "name": fighter["name"],
            "grade": grade["score"] if available else None,
            "prior_bouts": grade.get("bouts", 0) if available else 0}


def add_market_upsets(index, db, snapshot, market, estimate):
    """Adds index["market"]: lists and counts for the market-based tracker."""
    decided, upsets = 0, []
    ids = list(market)
    payloads = {}
    for start in range(0, len(ids), 500):
        chunk = ids[start:start + 500]
        rows = db.execute("SELECT id,payload FROM fights WHERE id IN (%s)" % ",".join("?" * len(chunk)), chunk)
        payloads.update({row["id"]: json.loads(row["payload"]) for row in rows})
    for fid, entry in market.items():
        if fid not in payloads:
            continue
        bout = reviewed_bout(payloads[fid], fid)
        if bout["outcome"] != "decisive" or bout["winner_id"] is None:
            continue
        decided += 1
        ids_ = [f["id"] for f in bout["fighters"]]
        if ids_ != entry["fighter_ids"]:
            continue
        won = ids_.index(bout["winner_id"])
        chance = entry["probability_a"] if won == 0 else 1 - entry["probability_a"]
        if chance >= UPSET_LINE:
            continue
        forecast = snapshot.forecasts.get(fid)
        upset_chance = None
        if forecast is not None and bout["winner_id"] in forecast["fighter_ids"] and min(forecast["prior_decisive_bouts"]) >= 1:
            p = forecast["forecast"]
            upset_chance = p if forecast["fighter_ids"][0] == bout["winner_id"] else 1 - p
        day = bout["date"]
        winner = side(estimate, bout["fighters"][won], day)
        loser = side(estimate, bout["fighters"][1 - won], day)
        upsets.append({"id": fid, "date": day, "method": bout["method"], "title": bout["title"],
                       "winner": winner, "opponent": loser,
                       "gap": (loser["grade"] - winner["grade"]) if winner["grade"] is not None and loser["grade"] is not None else None,
                       "market_chance": round(chance, 4), "winner_line": entry["american"][won],
                       "favorite_line": entry["american"][1 - won], "market_basis": entry["basis"],
                       "books": entry["books"], "upset_chance": None if upset_chance is None else round(upset_chance, 4),
                       "upset_saw_it": upset_chance is not None and upset_chance > .5})
    upsets.sort(key=lambda u: (u["date"], u["id"]), reverse=True)
    shocks = sorted(upsets, key=lambda u: (u["market_chance"], u["date"]))
    latest = upsets[0]["date"] if upsets else None
    recent_since = (date.fromisoformat(latest) - timedelta(days=364)).isoformat() if latest else None
    wins, chances = {}, {}
    for fid, entry in market.items():
        if recent_since and entry["date"] >= recent_since:
            p_a = entry["probability_a"]
            if min(p_a, 1 - p_a) < UPSET_LINE:
                uid = entry["fighter_ids"][0 if p_a < .5 else 1]
                chances[uid] = chances.get(uid, 0) + 1
    for upset in upsets:
        if recent_since and upset["date"] >= recent_since:
            wins.setdefault(upset["winner"]["id"], []).append(upset)
    repeat = [{"fighter": rows[0]["winner"], "wins": len(rows), "opportunities": chances.get(uid, len(rows)),
               "recent_results": [{"id": r["id"], "date": r["date"], "opponent": r["opponent"], "winner_chance": r["market_chance"]}
                                  for r in rows]}
              for uid, rows in wins.items() if len(rows) > 1]
    repeat.sort(key=lambda row: (-row["wins"], row["opportunities"], row["fighter"]["name"]))
    index["market"] = {
        "first": min((u["date"] for u in upsets), default=None), "latest": latest, "recent_since": recent_since,
        "decided_bouts": decided, "upsets": len(upsets), "upset_line": UPSET_LINE,
        "upset_saw_it": sum(u["upset_saw_it"] for u in upsets),
        "with_upset_forecast": sum(u["upset_chance"] is not None for u in upsets),
        "shocks": shocks[:LIST_LIMIT], "latest_upsets": upsets[:LIST_LIMIT],
        "title_upsets": [u for u in upsets if u["title"]],
        "saw_it": sorted((u for u in upsets if u["upset_saw_it"]), key=lambda u: (u["market_chance"], u["date"]))[:LIST_LIMIT],
        "saw_it_latest": [u for u in upsets if u["upset_saw_it"]][:LIST_LIMIT],
        "repeat_winners": repeat[:8],
        "recent_shock": min((u for u in upsets if recent_since and u["date"] >= recent_since),
                            key=lambda u: u["market_chance"], default=None),
        "source": "UFC Betting Odds Daily (Kaggle, CC0 public domain): one archived pre-fight line per bout for "
                  "2010-2024 and the median of 20+ sportsbooks from the day before the fight for 2025-26, "
                  "with the bookmaker margin removed."}
    return index
