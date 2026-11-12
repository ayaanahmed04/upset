"""Pre-fight betting market chances for every UFC bout in the research database, 2010 onward.

Source: UFC Betting Odds Daily (Kaggle, CC0), the copy downloaded on 2026-11-10.

* 2010-2024: the archive holds one pre-fight moneyline per bout, linked by UFCStats fight ID.
  Those rows were added to the archive later, so they carry no capture time; they are prices
  quoted before the fight, used here as the market's view going in.
* 2025 on: daily snapshots from many sportsbooks. For each bout this takes the last snapshot
  captured before fight day (UTC), removes each book's margin, and keeps the median chance.

Every match is checked against both fighters' names. Ambiguous matches are dropped and counted.

The script also tests, walk-forward, whether mixing the market with the UPSET forecast beats
the market alone: the mix is fit on 2010-2018 and scored on 2019 onward.
"""

import argparse
import csv
import hashlib
import io
import json
import math
import sqlite3
import statistics
import unicodedata
import zipfile
from collections import defaultdict
from contextlib import closing
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit

VERSION = "market_odds_v1"
START = "2010-01-01"
TRAIN_END = "2018-12-31"


def digest(path):
    h = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def normal(name):
    text = unicodedata.normalize("NFKD", name or "").encode("ascii", "ignore").decode().lower()
    return " ".join("".join(c if c.isalnum() else " " for c in text).split())


def same_person(a, b):
    ta, tb = normal(a).split(), normal(b).split()
    if not ta or not tb:
        return False
    if sorted(ta) == sorted(tb):
        return True
    ja, jb = "".join(ta), "".join(tb)
    return ja == jb or (len(tb) == 2 and ja in (tb[0] + tb[1], tb[1] + tb[0])) or \
        (len(ta) == 2 and jb in (ta[0] + ta[1], ta[1] + ta[0]))


def orientation(row, names):
    """+1 if row fighter_1 is our fighter A, -1 if swapped, 0 if the names don't both match."""
    if same_person(row["fighter_1"], names[0]) and same_person(row["fighter_2"], names[1]):
        return 1
    if same_person(row["fighter_1"], names[1]) and same_person(row["fighter_2"], names[0]):
        return -1
    return 0


def loose_orientation(row, names):
    """For rows already tied to the fight by UFCStats ID: one name or both last names is enough
    to tell the corners apart (Zachary/Zach Reese, Sergey/Sergei Pavlovich)."""
    last = lambda n: (normal(n).split() or [""])[-1]
    straight = same_person(row["fighter_1"], names[0]) or same_person(row["fighter_2"], names[1]) or \
        (last(row["fighter_1"]) == last(names[0]) or last(row["fighter_2"]) == last(names[1]))
    swapped = same_person(row["fighter_1"], names[1]) or same_person(row["fighter_2"], names[0]) or \
        (last(row["fighter_1"]) == last(names[1]) or last(row["fighter_2"]) == last(names[0]))
    return 1 if straight and not swapped else -1 if swapped and not straight else 0


def fair(odds_a, odds_b):
    if min(odds_a, odds_b) <= 1.01 or not all(map(math.isfinite, (odds_a, odds_b))):
        return None
    inverse = (1 / odds_a, 1 / odds_b)
    total = sum(inverse)
    if not 1.0 <= total <= 1.15:
        return None
    return inverse[0] / total


def american(decimal):
    if decimal >= 2:
        return "+" + str(round((decimal - 1) * 100))
    return "-" + str(round(100 / (decimal - 1)))


def parse_time(text):
    try:
        moment = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return moment if moment.utcoffset() is not None else None


def stats_id(url):
    parts = urlsplit(url or "")
    if parts.hostname in {"ufcstats.com", "www.ufcstats.com"} and parts.path.startswith("/fight-details/"):
        return parts.path.removeprefix("/fight-details/")
    return None


def load_fights(database):
    with closing(sqlite3.connect(database)) as db:
        rows = db.execute("SELECT id,event_date,payload FROM fights WHERE event_date>=?", (START,)).fetchall()
    fights = {}
    for fid, day, payload in rows:
        p = json.loads(payload)
        result = p.get("reviewed_result") or p
        names = [p["fighter_1_name"], p["fighter_2_name"]]
        winner = result.get("winner_name")
        fights[fid] = {"id": fid, "date": day, "names": names,
                       "ids": [p.get("upset_fighter_1_id"), p.get("upset_fighter_2_id")],
                       "winner": None if winner is None else (0 if winner == names[0] else 1 if winner == names[1] else None)}
    return fights


def build(database, archive):
    fights = load_fights(database)
    by_stats = {fid.split(":", 1)[1]: fid for fid in fights if fid.startswith("kaggle_ufc_1994_2026:")}
    by_day = defaultdict(list)
    for fight in fights.values():
        by_day[fight["date"]].append(fight["id"])

    archived = defaultdict(list)       # fight id -> [(p_a, odds_a, odds_b)]
    snapshots = defaultdict(list)      # fight id -> [(time, book, p_a, odds_a, odds_b)]
    late = defaultdict(list)           # fight id -> [(p_a, odds_a, odds_b, book)] added after the fight
    dropped = defaultdict(int)
    with zipfile.ZipFile(archive) as z, z.open("UFC_betting_odds.csv") as stream:
        for row in csv.DictReader(io.TextIOWrapper(stream, encoding="utf-8-sig")):
            if row["event_date"] < START:
                continue
            try:
                odds = (float(row["odds_1"]), float(row["odds_2"]))
            except ValueError:
                dropped["no price"] += 1
                continue
            key = by_stats.get(stats_id(row["fight_url"]))
            candidates = [key] if key else [fid for offset in (0, -1, 1) for fid in by_day.get(
                (date.fromisoformat(row["event_date"]) + timedelta(days=offset)).isoformat(), [])]
            matched = [(fid, orientation(row, fights[fid]["names"]) or (loose_orientation(row, fights[fid]["names"]) if key else 0))
                       for fid in candidates]
            matched = [(fid, sign) for fid, sign in matched if sign]
            if len(matched) != 1:
                if key:
                    dropped["UFCStats-linked row whose names don't match"] += 1
                elif matched:
                    dropped["ambiguous name match"] += 1
                else:
                    dropped["unmatched rows (mostly other promotions or cancelled bouts)"] += 1
                continue
            fid, sign = matched[0]
            a, b = odds if sign == 1 else odds[::-1]
            p = fair(a, b)
            if p is None:
                dropped["broken price"] += 1
                continue
            if row["source"] == "zewnetrzne":
                archived[fid].append((p, a, b))
                continue
            moment = parse_time(row["adding_date"])
            fight_day = datetime.fromisoformat(fights[fid]["date"]).replace(tzinfo=timezone.utc)
            # Day-before snapshots first; a fight-day snapshot only if taken before 16:00 UTC,
            # which is before any US card starts.
            if moment is None:
                dropped["no capture time"] += 1
                continue
            if moment >= fight_day + timedelta(days=1):
                # Added to the archive after the fight: a historical pre-fight price, like the 2010-2024 lines.
                late[fid].append((p, a, b, row["source"] or "unnamed book"))
                continue
            if moment >= fight_day + timedelta(hours=16):
                dropped["captured on fight day after 16:00 UTC (could be live)"] += 1
                continue
            snapshots[fid].append((moment, row["source"] or "unnamed book", p, a, b))

    odds = {}
    for fid in set(archived) | set(snapshots) | set(late):
        fight = fights[fid]
        if fid in snapshots:
            fight_day = date.fromisoformat(fight["date"])
            earlier = [m for m, *_ in snapshots[fid] if m.date() < fight_day]
            latest_day = max(earlier).date() if earlier else fight_day
            books = {}
            for moment, book, p, a, b in sorted(snapshots[fid]):
                if moment.date() == latest_day:
                    books[book] = (p, a, b)
            ps = [v[0] for v in books.values()]
            entry = {"basis": "consensus" if earlier else "fight-day consensus", "books": len(books), "observed": latest_day.isoformat(),
                     "probability_a": statistics.median(ps),
                     "decimal_odds": [statistics.median(v[1] for v in books.values()),
                                      statistics.median(v[2] for v in books.values())]}
        elif fid not in archived:
            books = {}
            for p, a, b, book in late[fid]:
                books.setdefault(book, (p, a, b))
            entry = {"basis": "archived line", "books": len(books), "observed": None,
                     "probability_a": statistics.median(v[0] for v in books.values()),
                     "decimal_odds": [statistics.median(v[1] for v in books.values()),
                                      statistics.median(v[2] for v in books.values())]}
        else:
            rows = archived[fid]
            if len({round(r[0], 3) for r in rows}) > 1:
                dropped["conflicting archived lines"] += 1
                continue
            p, a, b = rows[0]
            entry = {"basis": "archived line", "books": 1, "observed": None, "probability_a": p, "decimal_odds": [a, b]}
        entry["probability_a"] = round(entry["probability_a"], 4)
        entry["american"] = [american(x) for x in entry["decimal_odds"]]
        entry["decimal_odds"] = [round(x, 3) for x in entry["decimal_odds"]]
        entry.update(date=fight["date"], fighter_ids=fight["ids"], names=fight["names"])
        odds[fid] = entry
    return fights, odds, dict(dropped)


# ---------------------------------------------------------------- does the mix beat the market?

def logit(p):
    p = min(max(p, 1e-6), 1 - 1e-6)
    return math.log(p / (1 - p))


def sigmoid(x):
    return 1 / (1 + math.exp(-x))


def fit(rows):
    """Fit p = sigmoid(a*logit(market) + b*logit(forecast)) by Newton's method on log loss."""
    a, b = 1.0, 0.0
    for _ in range(50):
        ga = gb = haa = hab = hbb = 0.0
        for xm, xf, y in rows:
            p = sigmoid(a * xm + b * xf)
            r, w = p - y, p * (1 - p)
            ga += r * xm; gb += r * xf
            haa += w * xm * xm; hab += w * xm * xf; hbb += w * xf * xf
        det = haa * hbb - hab * hab
        da, db = (hbb * ga - hab * gb) / det, (haa * gb - hab * ga) / det
        a, b = a - da, b - db
        if abs(da) + abs(db) < 1e-10:
            break
    return a, b


def score(probabilities):
    if not probabilities:
        return None
    loss = sum(-math.log(min(max(p, 1e-6), 1 - 1e-6)) for p in probabilities) / len(probabilities)
    return {"bouts": len(probabilities), "log_loss": round(loss, 4),
            "accuracy": round(sum(p > .5 for p in probabilities) / len(probabilities) + .5 * sum(p == .5 for p in probabilities) / len(probabilities), 4)}


def research(fights, odds, forecasts_path):
    forecasts = {}
    with open(forecasts_path) as stream:
        for line in stream:
            item = json.loads(line)
            forecasts[item["fight_id"]] = item
    rows = []
    for fid, entry in odds.items():
        fight, item = fights[fid], forecasts.get(fid)
        if fight["winner"] is None or item is None or set(item["fighter_ids"]) != set(fight["ids"]) or entry["basis"] == "fight-day consensus":
            continue
        f_a = item["forecast"] if item["fighter_ids"][0] == fight["ids"][0] else 1 - item["forecast"]
        new = min(item["prior_decisive_bouts"]) < 3
        rows.append((fight["date"], entry["probability_a"], f_a, 1 if fight["winner"] == 0 else 0, new))
    train = [(logit(m), logit(f), y) for d, m, f, y, _ in rows if d <= TRAIN_END]
    a, b = fit(train)
    report = {"fit_on": f"{START}..{TRAIN_END}", "weights": {"market": round(a, 4), "forecast": round(b, 4)}, "test": {}}
    for label, keep in (("all", lambda new: True), ("newer fighters (<3 decided UFC fights)", lambda new: new),
                        ("established fighters", lambda new: not new)):
        test = [(m, f, y) for d, m, f, y, new in rows if d > TRAIN_END and keep(new)]
        won = lambda p, y: p if y else 1 - p
        report["test"][label] = {
            "market": score([won(m, y) for m, f, y in test]),
            "upset_forecast": score([won(f, y) for m, f, y in test]),
            "market_plus_upset": score([won(sigmoid(a * logit(m) + b * logit(f)), y) for m, f, y in test])}
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--forecasts", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit(f"{args.output} exists; write a new version instead.")
    fights, odds, dropped = build(args.database, args.archive)
    decided = [fid for fid in odds if fights[fid]["winner"] is not None]
    underdog_won = [fid for fid in decided if (odds[fid]["probability_a"] < .5) == (fights[fid]["winner"] == 0)
                    and odds[fid]["probability_a"] != .5]
    report = {"fights_since_2010": len(fights), "priced": len(odds), "decided_and_priced": len(decided),
              "underdog_won": len(underdog_won), "dropped_rows": dropped,
              "by_basis": {basis: sum(e["basis"] == basis for e in odds.values()) for basis in ("archived line", "consensus", "fight-day consensus")},
              "unpriced_by_year": {}, "mix": research(fights, odds, args.forecasts)}
    for fid, fight in fights.items():
        if fid not in odds:
            year = fight["date"][:4]
            report["unpriced_by_year"][year] = report["unpriced_by_year"].get(year, 0) + 1
    args.output.mkdir(parents=True)
    body = json.dumps(odds, separators=(",", ":"), ensure_ascii=False, sort_keys=True).encode()
    (args.output / "odds.json").write_bytes(body)
    (args.output / "report.json").write_text(json.dumps(report, indent=1) + "\n")
    manifest = {"version": VERSION, "database_sha256": json.loads((args.database.parent / "manifest.json").read_text())["database_sha256"],
                "archive": "UFC Betting Odds Daily (Kaggle, CC0) · https://www.kaggle.com/datasets/jerzyszocik/ufc-betting-odds-daily-dataset",
                "archive_sha256": digest(args.archive), "output_sha256": {"odds.json": hashlib.sha256(body).hexdigest()},
                "tool": "src/upset/data/build_market_odds.py"}
    (args.output / "manifest.json").write_text(json.dumps(manifest, indent=1) + "\n")
    print(json.dumps(report, indent=1))


if __name__ == "__main__":
    main()
