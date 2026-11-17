"""Published UPSET picks: freeze a scheduled card's forecasts before the fights, grade them after.

Each frozen card lives in its own folder under data/published/picks/<event slug>/:

    picks.json     what UPSET said before the card. Written once, never edited.
    manifest.json  the SHA-256 fingerprint of picks.json and when it was frozen.
    graded.json    the results, written after the card. picks.json is not touched.

Anyone can check a pick was not changed afterwards: hash picks.json and compare it with the
fingerprint shown on the site (and, once the folder is committed, with the Git history).

Usage:
    python -m upset.predictions.published_picks freeze --api http://127.0.0.1:8768 --slug ufc-334 \
        --market data/raw/ufc_market_odds_2026_11_10_v1/kaggle-odds.zip \
        --rating-snapshot data/processed/overall_rating_v5_1_2026_11_10_reviewed_v3
    python -m upset.predictions.published_picks grade --slug ufc-334 \
        --database data/processed/research_<next release>/upset.sqlite
"""

import argparse
import csv
import hashlib
import io
import itertools
import json
import math
import re
import sqlite3
import unicodedata
import zipfile
from contextlib import closing
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote
from urllib.request import urlopen

VERSION = "upset_published_picks_v1"
GRADE_VERSION = "upset_published_grades_v1"
DEFAULT_ROOT = Path("data/published/picks")
SLUG = re.compile(r"[a-z0-9][a-z0-9-]{0,80}")
MARKET_BOOKS = ("BetOnline.ag", "Pinnacle")  # BetOnline.ag first: the same book as the v5 market check.
RULES = ("A pick is the fighter UPSET gave the higher chance. It is graded right when that fighter wins. "
         "Draws, no contests and bouts that were cancelled or changed are not graded. Log loss scores the "
         "probability itself: lower is better, and always picking 50% scores 0.693.")


def digest(data):
    return hashlib.sha256(data).hexdigest()


def utc_now():
    return datetime.now(timezone.utc).replace(microsecond=0)


def iso(moment):
    return moment.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def parse_time(text):
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


def fetch_json(url):
    with urlopen(url, timeout=60) as response:
        return json.loads(response.read())


def dump(value):
    return (json.dumps(value, indent=1, ensure_ascii=False) + "\n").encode()


# ---------------------------------------------------------------- market reference

def normal(name):
    text = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()
    return " ".join("".join(c if c.isalnum() else " " for c in text).split())


def same_person(a, b):
    """Exact token match, allowing reordered or joined name parts (Heili Alateng = Alatengheili)."""
    ta, tb = normal(a).split(), normal(b).split()
    if not ta or not tb:
        return False
    if sorted(ta) == sorted(tb):
        return True
    joined_a, joined_b = "".join(ta), "".join(tb)
    return any("".join(p) == joined_a for p in itertools.permutations(tb) if len(tb) <= 3) or \
        any("".join(p) == joined_b for p in itertools.permutations(ta) if len(ta) <= 3)


def no_vig(odds_a, odds_b):
    inverse = [1 / odds_a, 1 / odds_b]
    total = sum(inverse)
    if not 1.0 <= total <= 1.15:
        return None
    return [inverse[0] / total, inverse[1] / total]


def market_rows(path, first_day, last_day):
    with zipfile.ZipFile(path) as archive:
        name = next(n for n in archive.namelist() if n.endswith(".csv"))
        with archive.open(name) as stream:
            for row in csv.DictReader(io.TextIOWrapper(stream, encoding="utf-8")):
                if first_day <= row["event_date"] <= last_day and row["source"] in MARKET_BOOKS:
                    yield row


def market_reference(path, card_date, bouts, frozen_at):
    """Latest pre-freeze no-vig moneyline per bout from the CC0 daily odds archive."""
    first, last = card_date.isoformat(), (card_date + timedelta(days=1)).isoformat()
    rows = [row for row in market_rows(path, first, last) if parse_time(row["adding_date"]) <= frozen_at]
    captured = max((row["adding_date"] for row in rows), key=parse_time, default=None)
    found = {}
    for index, fighters in bouts.items():
        best = None
        for row in rows:
            straight = same_person(row["fighter_1"], fighters[0]) and same_person(row["fighter_2"], fighters[1])
            swapped = same_person(row["fighter_1"], fighters[1]) and same_person(row["fighter_2"], fighters[0])
            if not (straight or swapped):
                continue
            try:
                odds = [float(row["odds_1"]), float(row["odds_2"])]
            except ValueError:
                continue
            if min(odds) <= 1.01:
                continue
            fair = no_vig(*odds)
            if fair is None:
                continue
            if swapped:
                odds, fair = odds[::-1], fair[::-1]
            rank = (-MARKET_BOOKS.index(row["source"]), parse_time(row["adding_date"]))
            if best is None or rank > best[0]:
                best = (rank, {"probabilities": [round(fair[0], 4), round(fair[1], 4)],
                               "decimal_odds": odds, "book": row["source"],
                               "observed_at": row["adding_date"]})
        if best:
            found[index] = best[1]
    source = {"name": "UFC Betting Odds Daily (Kaggle, CC0 public domain)",
              "url": "https://www.kaggle.com/datasets/jerzyszocik/ufc-betting-odds-daily-dataset",
              "file_sha256": digest(Path(path).read_bytes()), "captured_through": captured,
              "method": "Latest " + " or ".join(MARKET_BOOKS) + " moneyline seen before the freeze; "
                        "bookmaker margin removed proportionally. Shown for comparison, not advice."}
    return found, source


# ---------------------------------------------------------------- freeze

def freeze(api, slug, root=DEFAULT_ROOT, market=None, rating_snapshot=None, now=None,
           forecast_adjustment=None, folder_name=None, supersedes=None):
    """Freeze a scheduled card. To re-lock a card before it starts, write a new folder (folder_name) that
    names the earlier lock in `supersedes`; the earlier lock is kept untouched and listed as replaced."""
    if not SLUG.fullmatch(slug) or (folder_name is not None and not SLUG.fullmatch(folder_name)):
        raise SystemExit("Use the event slug from the site, for example ufc-334.")
    folder = Path(root) / (folder_name or slug)
    replaced = None
    if supersedes is not None:
        old_manifest, old = load_frozen(Path(root) / supersedes)
        if old["event"]["slug"] != slug:
            raise SystemExit(f"{supersedes} is a lock for {old['event']['slug']}, not {slug}.")
        if (Path(root) / supersedes / "graded.json").exists():
            raise SystemExit(f"{supersedes} is already graded; a graded lock cannot be replaced.")
        replaced = {"folder": supersedes, "frozen_at": old["frozen_at"], "picks_sha256": old_manifest["picks_sha256"],
                    "forecast_revision": (old.get("model") or {}).get("forecast_revision")}
    elif folder_name is not None and folder_name != slug:
        raise SystemExit("A folder name other than the event slug is only for a re-lock (pass supersedes).")
    if folder.exists():
        raise SystemExit(f"{folder} already exists. Published picks are never overwritten.")
    now = now or utc_now()
    meta = fetch_json(api.rstrip("/") + "/api/meta")
    event = fetch_json(api.rstrip("/") + "/api/event?slug=" + quote(slug))
    if event.get("status") != "scheduled":
        raise SystemExit("Only a scheduled card can be frozen.")
    if event.get("starts_at") and parse_time(event["starts_at"]) <= now:
        raise SystemExit("This card has already started; picks must be frozen before the first fight.")

    picks, skipped, label, record, forecast_revision = [], [], None, None, None
    for order, bout in enumerate(event["bouts"]):
        fighters = [{"id": fighter.get("id"), "name": fighter["name"]} for fighter in bout["fighters"]]
        forecast = bout.get("forecast") or {}
        if forecast.get("status") != "available" or not all(f["id"] for f in fighters):
            skipped.append({"order": order, "fighters": fighters,
                            "reason": "Not enough UFC fights to forecast" if forecast else "No forecast"})
            continue
        label, record = forecast.get("label", label), forecast.get("record", record)
        forecast_revision = forecast.get("revision") or forecast_revision
        p = [round(float(x), 4) for x in forecast["probabilities"]]
        favorite = 0 if p[0] >= p[1] else 1
        picks.append({"order": order, "group": bout.get("group"), "division": bout.get("division"),
                      "title": bool(bout.get("title")), "rounds": bout.get("rounds"), "fighters": fighters,
                      "probabilities": p, "pick": fighters[favorite]["id"], "pick_name": fighters[favorite]["name"],
                      "rating_gap": forecast.get("rating_gap"), "provisional": bool(forecast.get("provisional")),
                      "inactive": bool(forecast.get("stale"))})
    if not picks:
        raise SystemExit("No bout on this card has a forecast to publish.")

    market_source = None
    if market:
        found, market_source = market_reference(market, date.fromisoformat(event["date"]),
                                                {i: [f["name"] for f in pick["fighters"]] for i, pick in enumerate(picks)}, now)
        for i, quote_ in found.items():
            picks[i]["market"] = quote_

    model = {"name": "UPSET forecast", "label": label, "record_before_publishing": record,
             "data_through": meta.get("latest_bout"), "forecast_revision": forecast_revision}
    if rating_snapshot:
        manifest_path = Path(rating_snapshot) / "manifest.json"
        snapshot_manifest = json.loads(manifest_path.read_text())
        model.update({"snapshot": Path(rating_snapshot).name, "revision": snapshot_manifest.get("revision"),
                      "snapshot_manifest_sha256": digest(manifest_path.read_bytes())})
    if forecast_adjustment:
        manifest_path = Path(forecast_adjustment) / "manifest.json"
        model["forecast_adjustment"] = {"folder": Path(forecast_adjustment).name,
                                       "revision": json.loads(manifest_path.read_text()).get("revision"),
                                       "manifest_sha256": digest(manifest_path.read_bytes())}

    payload = {"version": VERSION, "frozen_at": iso(now),
               "event": {key: event.get(key) for key in ("slug", "name", "headline", "date", "venue", "starts_at",
                                                        "source_url", "schedule_reviewed_on")},
               "model": model, "rules": RULES, "picks": picks, "not_picked": skipped,
               "market_source": market_source}
    if replaced:
        payload["supersedes"] = replaced
    body = dump(payload)
    folder.mkdir(parents=True)
    (folder / "picks.json").write_bytes(body)
    manifest = {"version": VERSION, "slug": folder.name, "event_slug": slug, "frozen_at": iso(now), "picks_sha256": digest(body),
                "picks_bytes": len(body), "tool": "src/upset/predictions/published_picks.py"}
    if replaced:
        manifest["supersedes"] = replaced
    (folder / "manifest.json").write_bytes(dump(manifest))
    return folder, payload, manifest


# ---------------------------------------------------------------- grade

def load_frozen(folder):
    folder = Path(folder)
    manifest = json.loads((folder / "manifest.json").read_text())
    body = (folder / "picks.json").read_bytes()
    if manifest.get("version") != VERSION or digest(body) != manifest.get("picks_sha256"):
        raise ValueError(f"{folder}/picks.json does not match its fingerprint.")
    return manifest, json.loads(body)


def score(p_winner):
    p = min(max(p_winner, 1e-6), 1 - 1e-6)
    return -math.log(p), (1 - p) ** 2


def grade(folder, database, now=None, regrade=False):
    from upset.data.viewer_events import reviewed_bout

    folder = Path(folder)
    manifest, picks = load_frozen(folder)
    target = folder / "graded.json"
    if target.exists():
        if not regrade:
            raise SystemExit(f"{target} exists. Pass --regrade to grade again; the old file is kept.")
        target.rename(folder / ("graded-" + utc_now().strftime("%Y%m%dT%H%M%SZ") + ".json"))
    card = date.fromisoformat(picks["event"]["date"])
    with closing(sqlite3.connect(database)) as db:
        db.row_factory = sqlite3.Row
        rows = db.execute("SELECT id,payload FROM fights WHERE event_date BETWEEN ? AND ?",
                          ((card - timedelta(days=1)).isoformat(), (card + timedelta(days=1)).isoformat())).fetchall()
    bouts = [reviewed_bout(json.loads(row["payload"]), row["id"]) for row in rows]
    by_pair = {frozenset(f["id"] for f in bout["fighters"]): bout for bout in bouts}
    results = []
    for pick in picks["picks"]:
        ids = [f["id"] for f in pick["fighters"]]
        bout = by_pair.get(frozenset(ids))
        row = {"order": pick["order"], "fighters": ids}
        if bout is None:
            row["status"] = "pending" if not bouts else "not_held"
        elif bout["outcome"] != "decisive":
            row.update(status="void", outcome=bout["outcome"], fight_id=bout["id"])
        else:
            won = ids.index(bout["winner_id"])
            log_loss, brier = score(pick["probabilities"][won])
            row.update(status="graded", fight_id=bout["id"], winner_id=bout["winner_id"], method=bout["method"],
                       round=bout["round"], time=bout["time"], correct=bout["winner_id"] == pick["pick"],
                       log_loss=round(log_loss, 5), brier=round(brier, 5),
                       upset=pick["probabilities"][won] < .5)
            if pick.get("market"):
                m_loss, m_brier = score(pick["market"]["probabilities"][won])
                row["market"] = {"correct": pick["market"]["probabilities"][won] > .5,
                                 "log_loss": round(m_loss, 5), "brier": round(m_brier, 5)}
        results.append(row)
    payload = {"version": GRADE_VERSION, "slug": picks["event"]["slug"], "picks_sha256": manifest["picks_sha256"],
               "graded_at": iso(now or utc_now()), "database": Path(database).parent.name,
               "database_sha256": digest(Path(database).read_bytes()), "results": results,
               "summary": summarize([(p, r) for p, r in zip(picks["picks"], results)])}
    target.write_bytes(dump(payload))
    return payload


def summarize(pairs):
    graded = [r for _, r in pairs if r.get("status") == "graded"]
    priced = [r for r in graded if r.get("market")]
    out = {"picks": len(pairs), "graded": len(graded),
           "pending": sum(r.get("status") == "pending" for _, r in pairs),
           "void": sum(r.get("status") in ("void", "not_held") for _, r in pairs),
           "correct": sum(r["correct"] for r in graded),
           "log_loss": round(sum(r["log_loss"] for r in graded) / len(graded), 4) if graded else None,
           "market_bouts": len(priced)}
    if priced:
        out.update(upset_correct_on_market_bouts=sum(r["correct"] for r in priced),
                   market_correct=sum(r["market"]["correct"] for r in priced),
                   upset_log_loss_on_market_bouts=round(sum(r["log_loss"] for r in priced) / len(priced), 4),
                   market_log_loss=round(sum(r["market"]["log_loss"] for r in priced) / len(priced), 4))
    return out


# ---------------------------------------------------------------- record for the site

def load_record(root=DEFAULT_ROOT):
    """Every published card, newest first, with grades when they exist. Bad fingerprints are reported, not hidden."""
    root = Path(root)
    events, pairs = [], []
    for folder in sorted(p for p in root.glob("*") if p.is_dir() and SLUG.fullmatch(p.name)) if root.exists() else []:
        try:
            manifest, picks = load_frozen(folder)
        except (ValueError, OSError, json.JSONDecodeError) as error:
            events.append({"slug": folder.name, "error": str(error)})
            continue
        graded = None
        if (folder / "graded.json").exists():
            graded = json.loads((folder / "graded.json").read_text())
            if graded.get("picks_sha256") != manifest["picks_sha256"]:
                graded = None
        results = {r["order"]: r for r in graded["results"]} if graded else {}
        rows = [{**pick, "result": results.get(pick["order"], {"status": "pending"})} for pick in picks["picks"]]
        events.append({"slug": folder.name, "event": picks["event"], "frozen_at": picks["frozen_at"],
                       "sha256": manifest["picks_sha256"], "model": picks["model"], "rules": picks["rules"],
                       "market_source": picks.get("market_source"), "picks": rows,
                       "not_picked": picks["not_picked"], "graded_at": graded and graded["graded_at"],
                       "summary": summarize([(p, r["result"]) for p, r in zip(picks["picks"], rows)]),
                       "supersedes": picks.get("supersedes"), "_picks": picks["picks"]})
    # A re-locked card counts once: the replaced lock stays on file and is listed under the lock that replaced it.
    replaced = {e["supersedes"]["folder"]: e for e in events if e.get("supersedes")}
    kept = []
    for e in events:
        if e["slug"] in replaced:
            replaced[e["slug"]].setdefault("replaces", []).append(
                {"slug": e["slug"], "frozen_at": e.get("frozen_at"), "sha256": e.get("sha256"),
                 "forecast_revision": (e.get("model") or {}).get("forecast_revision") or (e.get("model") or {}).get("revision"),
                 "error": e.get("error")})
        else:
            kept.append(e)
    pairs = [(pick, row["result"]) for e in kept if not e.get("error") for pick, row in zip(e["_picks"], e["picks"])]
    for e in kept:
        e.pop("_picks", None)
    kept.sort(key=lambda e: (e.get("event") or {}).get("date", ""), reverse=True)
    return {"events": kept, "summary": summarize(pairs)}


def picks_file(root, slug):
    if not SLUG.fullmatch(slug):
        raise KeyError(slug)
    path = Path(root) / slug / "picks.json"
    if not path.is_file():
        raise KeyError(slug)
    return path.read_bytes()


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    f = sub.add_parser("freeze", help="Freeze a scheduled card's forecasts.")
    f.add_argument("--api", default="http://127.0.0.1:8768")
    f.add_argument("--slug", required=True)
    f.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    f.add_argument("--market", type=Path, help="CC0 daily odds archive (zip) for a market reference.")
    f.add_argument("--rating-snapshot", type=Path)
    f.add_argument("--forecast-adjustment", type=Path, help="Forecast adjustment folder the server used (recorded in the lock).")
    f.add_argument("--folder", help="Re-lock only: new folder name, e.g. ufc-334-r2.")
    f.add_argument("--supersedes", help="Re-lock only: the earlier lock's folder. It is kept and listed as replaced.")
    g = sub.add_parser("grade", help="Grade a frozen card against a newer database.")
    g.add_argument("--slug", required=True)
    g.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    g.add_argument("--database", type=Path, required=True)
    g.add_argument("--regrade", action="store_true")
    args = parser.parse_args()
    if args.command == "freeze":
        folder, payload, manifest = freeze(args.api, args.slug, args.root, args.market, args.rating_snapshot,
                                           forecast_adjustment=args.forecast_adjustment, folder_name=args.folder,
                                           supersedes=args.supersedes)
        print(f"Froze {len(payload['picks'])} picks for {payload['event']['name']} at {manifest['frozen_at']}")
        print(f"Fingerprint (SHA-256 of {folder}/picks.json): {manifest['picks_sha256']}")
        for pick in payload["picks"]:
            side = [f["id"] for f in pick["fighters"]].index(pick["pick"])
            m = pick.get("market")
            names = " vs ".join(f["name"] for f in pick["fighters"])
            print(f"  {names:<40} pick {pick['pick_name']:<22} {pick['probabilities'][side]:.0%}"
                  + (f"   market {m['probabilities'][side]:.0%} ({m['book']}, {m['observed_at'][:16]})" if m else "   no market match"))
    else:
        payload = grade(args.root / args.slug, args.database, regrade=args.regrade)
        print(json.dumps(payload["summary"], indent=1))


if __name__ == "__main__":
    main()
