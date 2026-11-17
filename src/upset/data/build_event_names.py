"""Index each accepted fight to its official event title from the archived Cito cards.

Display metadata only (event title, location, card section, finishing detail). Fights are
matched by their UFCStats bout id first, then by date (within a day, for time zones) and the
exact pair of normalized fighter names. Ambiguous matches are left out rather than guessed.
"""

import argparse
import hashlib
import json
import sqlite3
from collections import defaultdict
from contextlib import closing
from datetime import date, timedelta
from pathlib import Path

from upset.data.audit_cito_archive import _name


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cards", type=Path, default=Path("data/raw/cito_archive/cards"))
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists() and any(args.output.iterdir()):
        raise SystemExit("Output folder already has files; use a new folder.")
    by_id, by_names, cards = {}, defaultdict(list), {}
    for path in sorted(args.cards.glob("*/event.json")):
        cards[path.as_posix()] = digest(path)
        event = json.loads(path.read_text())["response"]["data"]
        for bout in event.get("bouts") or []:
            info = {"title": event.get("title"), "date": event.get("eventDate"), "location": event.get("locationText"),
                    "slug": event.get("slug"), "section": bout.get("cardSection"),
                    "method_detail": bout.get("methodDetails")}
            by_id[bout["id"]] = info
            names = frozenset(_name(f["fighterName"]) for f in bout.get("fighters") or [])
            if len(names) == 2:
                by_names[(event.get("eventDate"), names)].append(info)
    index, counts = {}, defaultdict(int)
    database = args.database.resolve()
    with closing(sqlite3.connect(database.as_uri() + "?mode=ro&immutable=1", uri=True)) as db:
        for fight_id, payload in db.execute("SELECT id,payload FROM fights"):
            fight = json.loads(payload)
            info = by_id.get(fight.get("source_bout_id"))
            if info:
                counts["by_bout_id"] += 1
            else:
                names = frozenset(_name(fight[f"fighter_{i}_name"]) for i in (1, 2))
                day = date.fromisoformat(fight["event_date"])
                found = [item for offset in (-1, 0, 1)
                         for item in by_names.get(((day + timedelta(days=offset)).isoformat(), names), [])]
                if len({item["slug"] for item in found}) == 1:
                    info = found[0]
                    counts["by_date_and_names"] += 1
                else:
                    counts["ambiguous" if found else "unmatched"] += 1
            if info:
                index[fight_id] = info
    args.output.mkdir(parents=True)
    (args.output / "event_names.json").write_text(json.dumps(index, sort_keys=True, separators=(",", ":")))
    manifest = {"version": "event_names_v1", "database_sha256": digest(database), "cards": len(cards),
                "cards_sha256": hashlib.sha256(json.dumps(cards, sort_keys=True).encode()).hexdigest(),
                "counts": dict(counts), "output_sha256": digest(args.output / "event_names.json")}
    (args.output / "manifest.json").write_text(json.dumps(manifest, indent=1))
    print(json.dumps(manifest, indent=1))


if __name__ == "__main__":
    main()
