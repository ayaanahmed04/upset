"""Betting market prices for the next scheduled card, and how often the market has been right when
it and the UPSET forecast strongly disagree.

Used only to flag big disagreements on fight cards. The forecast itself never uses these prices.
"""

import csv
import io
import statistics
import zipfile
from datetime import date, timedelta

from upset.data.build_market_odds import american, fair, orientation, parse_time

GAP = 0.15  # flag when the two sides of the call differ by 15+ points and pick different favorites


def scheduled_market(archive, event):
    """Median margin-free chance across books from the latest snapshot before the card, per bout."""
    if not event or not event.get("bouts"):
        return {}
    day = date.fromisoformat(event["date"])
    window = {(day + timedelta(days=d)).isoformat() for d in (-1, 0, 1)}
    start = parse_time(event.get("starts_at") or "") or None
    bouts = [b for b in event["bouts"] if all(f.get("id") for f in b["fighters"])]
    found = {}
    with zipfile.ZipFile(archive) as z, z.open("UFC_betting_odds.csv") as stream:
        for row in csv.DictReader(io.TextIOWrapper(stream, encoding="utf-8-sig")):
            if row["event_date"] not in window:
                continue
            moment = parse_time(row["adding_date"])
            if moment is None or (start and moment >= start):
                continue
            for bout in bouts:
                names = [f["name"] for f in bout["fighters"]]
                sign = orientation(row, names)
                if not sign:
                    continue
                try:
                    odds = (float(row["odds_1"]), float(row["odds_2"]))
                except ValueError:
                    continue
                a, b = odds if sign == 1 else odds[::-1]
                p = fair(a, b)
                if p is not None:
                    key = frozenset(f["id"] for f in bout["fighters"])
                    found.setdefault(key, []).append((moment, row["source"] or "unnamed book", p, a, b, bout))
                break
    out = {}
    for key, rows in found.items():
        latest = max(m for m, *_ in rows).date()
        books = {}
        for moment, book, p, a, b, bout in sorted(rows, key=lambda r: r[0]):
            if moment.date() == latest:
                books[book] = (p, a, b)
        bout = rows[0][5]
        ids = [f["id"] for f in bout["fighters"]]
        p = statistics.median(v[0] for v in books.values())
        decimals = [statistics.median(v[1] for v in books.values()), statistics.median(v[2] for v in books.values())]
        out[key] = {"fighter_ids": ids, "probabilities": [round(p, 4), round(1 - p, 4)],
                    "american": [american(x) for x in decimals], "books": len(books), "observed": latest.isoformat()}
    return out


def disagreement_record(forecasts, market_odds, since="2019-01-01"):
    """When UPSET and the market picked different favorites by GAP or more, how often was the market right?"""
    cases = market_right = 0
    for fid, item in forecasts.items():
        entry = market_odds.get(fid)
        if (entry is None or item.get("y") is None or item["event_date"] < since
                or min(item["prior_decisive_bouts"]) < 1 or set(entry["fighter_ids"]) != set(item["fighter_ids"])):
            continue
        m = entry["probability_a"] if entry["fighter_ids"][0] == item["fighter_ids"][0] else 1 - entry["probability_a"]
        u = item["forecast"]
        if abs(u - m) < GAP or (u > .5) == (m > .5) or u == .5 or m == .5:
            continue
        cases += 1
        market_right += (m > .5) == bool(item["y"])
    return {"since": since, "gap": GAP, "cases": cases, "market_right": market_right,
            "market_right_rate": round(market_right / cases, 4) if cases else None}


def attach(forecast, market, record):
    """Add the market view to an available forecast, and flag a strong disagreement."""
    if not forecast or forecast.get("status") != "available" or not market:
        return forecast
    p_market = market["probabilities"][0]
    p = forecast["probabilities"][0]
    out = {**forecast, "market": market}
    if abs(p - p_market) >= GAP and (p > .5) != (p_market > .5) and record.get("cases"):
        out["market_disagreement"] = {"gap": round(abs(p - p_market), 4), **record}
    return out
