"""Reconcile the viewer with its reviewed recent fight archive."""

import json
from collections import defaultdict
from datetime import date
from pathlib import Path

from upset.data.audit_cito_archive import _name
from upset.data.collect_cito_archive import _digest


def load_coverage(db, source, database_manifest):
    paths = ("review.json", "fights.jsonl", "identified/fights_identified.jsonl")
    for name in paths:
        path = source / name
        matches = [value for key, value in database_manifest["input_sha256"].items()
                   if path.resolve() == Path(key).resolve()]
        if len(matches) != 1 or _digest(path) != matches[0]:
            raise ValueError(f"Coverage source differs from the verified database input: {name}")

    def rows(name):
        with (source / name).open() as stream:
            return [json.loads(line) for line in stream]

    archive = rows("fights.jsonl")
    identified = rows("identified/fights_identified.jsonl")
    accepted = {f"cito:{row['source_bout_id']}": (row["upset_fighter_1_id"], row["upset_fighter_2_id"])
                for row in identified}
    actual = {row["id"]: (row["fighter_1"], row["fighter_2"])
              for row in db.execute("SELECT id,fighter_1,fighter_2 FROM fights WHERE id LIKE 'cito:%'")}
    if not accepted or accepted != actual or len(accepted) != len(identified):
        raise ValueError("Recent bout coverage differs from the reviewed source.")

    available = defaultdict(set)
    for row in db.execute(
        "SELECT stats.fight_id,fighters.id,fighters.name,fighters.search_name FROM stats "
        "JOIN fighters ON fighters.id=stats.fighter_id WHERE stats.fight_id LIKE 'cito:%'"
    ):
        if row["search_name"] != _name(row["name"]) or not row["search_name"]:
            raise ValueError(f"Reviewed participant cannot be found by name: {row['id']}")
        available[row["fight_id"]].add(row["id"])
    if any(available[key] != set(pair) for key, pair in accepted.items()):
        raise ValueError("A reviewed bout is missing a participant's fight history.")

    review = json.loads((source / "review.json").read_text())
    pending = set(review["withheld_prior_bout_ids"])
    discrepancies = review.get("pending_result_discrepancies", {})
    pending_rows = [row for row in archive if row["source_bout_id"] in pending]
    if (len(pending_rows) != len(pending) or len(pending) != database_manifest["excluded_current_bouts"]
            or {row["source_bout_id"] for row in archive} != pending | {key[5:] for key in accepted}
            or not discrepancies.keys() <= pending or any(f"cito:{key}" in accepted for key in pending)):
        raise ValueError("Recent archive is missing a reviewed or pending bout.")
    by_provider = {}
    for row in pending_rows:
        for side, other in ((1, 2), (2, 1)):
            uid = row[f"source_fighter_{side}_id"]
            person = by_provider.setdefault(uid, {"names": set(), "bouts": []})
            person["names"].add(row[f"fighter_{side}_name"])
            bout = {"date": row["event_date"], "opponent": row[f"fighter_{other}_name"]}
            if row["source_bout_id"] in discrepancies:
                bout["discrepancy"] = discrepancies[row["source_bout_id"]]
            person["bouts"].append(bout)
    print(f"Coverage checked: {len(accepted)} reviewed recent bouts and {len(pending)} awaiting review.", flush=True)
    return tuple({"names": sorted(person["names"]), "bouts": sorted(person["bouts"],
                 key=lambda bout: (bout["date"], bout["opponent"]), reverse=True)}
                 for person in by_provider.values())


def pending_search(index, query, before):
    if len(query) > 100 or date.fromisoformat(before).isoformat() != before:
        raise ValueError("Use a short query and an ISO date.")
    terms = [_name(part) for part in query.split() if _name(part)]
    if not terms:
        return []
    matches = []
    for person in index:
        names = [name for name in person["names"] if all(term in _name(name) for term in terms)]
        bouts = [bout for bout in person["bouts"] if bout["date"] < before]
        if names and bouts:
            matches.append({"name": names[0], "bouts": bouts})
    return sorted(matches, key=lambda item: item["name"])[:25]
