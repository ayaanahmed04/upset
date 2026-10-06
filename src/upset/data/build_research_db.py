"""Build a local read-only research database from accepted identified exports."""

import argparse
import json
import sqlite3
from collections import Counter
from pathlib import Path
from tempfile import TemporaryDirectory

from upset.data.audit_cito_archive import _name
from upset.data.collect_cito_archive import _digest
from upset.data.export_cito_current_archive import _manifest
from upset.data.identity import load_fighter_registry
from upset.data.stage_current import (
    ACCEPTED_HISTORICAL_FIGHTS_SHA256,
    LAST_HISTORICAL_DATE,
)

HISTORICAL_STATS_SHA256 = "2ab95df885ddd53fee7199e51bbd8afeef5cdb0ae38e9252821c0f8f55f1e17e"


def rows(path):
    return [json.loads(line) for line in path.read_text().splitlines()]


def build_database(historical, current, registry_path, accepted, output, *,
                   expected_fights=ACCEPTED_HISTORICAL_FIGHTS_SHA256,
                   expected_stats=HISTORICAL_STATS_SHA256):
    """Keep frozen and reviewed labels separate; exclude unreviewed identities."""
    if any(output.resolve() == p.resolve() or output.resolve().is_relative_to(p.resolve())
           for p in (historical, current, registry_path, accepted)):
        raise ValueError("Research output overlaps source data.")
    hashes = {}
    cm = _manifest(current, hashes)
    am = _manifest(accepted, hashes)
    history_paths = {name: historical / name for name in (
        "fighters_identified.jsonl", "fights_identified.jsonl", "fight_stats_identified.jsonl")}
    hashes.update({str(p): _digest(p) for p in history_paths.values()})
    if (_digest(history_paths["fights_identified.jsonl"]) != expected_fights
            or _digest(history_paths["fight_stats_identified.jsonl"]) != expected_stats):
        raise ValueError("Historical research snapshot differs from accepted hashes.")
    hashes[str(registry_path)] = _digest(registry_path)
    identified = cm["identified_subset_manifest"]
    if (identified["input_sha256"]["registry"] != hashes[str(registry_path)]
            or identified["input_sha256"]["historical"] != expected_fights
            or am["input_sha256"]["historical_fights"] != expected_fights):
        raise ValueError("Research identities or historical result overlay differ.")
    if output.exists():
        old = json.loads((output / "manifest.json").read_text())
        if old["input_sha256"] != hashes or _digest(output / "upset.sqlite") != old["database_sha256"]:
            raise ValueError("Existing research database differs; use a new output.")
        return old
    registry = load_fighter_registry(registry_path)
    names = {r.upset_fighter_id: r.display_name for r in registry.identities}
    provider_links = {(r.provider, r.provider_fighter_id): r.upset_fighter_id for r in registry.provider_links}
    profiles = rows(history_paths["fighters_identified.jsonl"])
    fighters = {}
    for profile in profiles:
        uid = profile["upset_fighter_id"]
        if uid in fighters or provider_links.get(("ufcstats", profile["source_fighter_id"])) != uid:
            raise ValueError("Historical profile identity differs from registry.")
        fighters[uid] = profile
    bouts = rows(history_paths["fights_identified.jsonl"])
    history_count = len(bouts)
    if max(r["event_date"] for r in bouts) != LAST_HISTORICAL_DATE:
        raise ValueError("Historical research cutoff differs.")
    current_bouts = rows(current / "identified/fights_identified.jsonl")
    if len(current_bouts) != cm["identified_current_bouts"]:
        raise ValueError("Current research cohort differs from manifest.")
    if any(r["event_date"] <= LAST_HISTORICAL_DATE for r in current_bouts):
        raise ValueError("Current research cohort overlaps historical dates.")
    bouts += current_bouts
    stats = rows(history_paths["fight_stats_identified.jsonl"]) + rows(current / "identified/fight_stats_identified.jsonl")
    amendments = {r["historical_bout_id"]: r for r in rows(accepted / "bout_results.jsonl")
                  if r["resolution"] == "reviewed_amendment"}
    bout_map, expected, occupied = {}, set(), {}
    for bout in bouts:
        key = bout["source"] + ":" + bout["source_bout_id"]
        uids = bout["upset_fighter_1_id"], bout["upset_fighter_2_id"]
        pair = (bout["event_date"], *sorted(uids))
        if key in bout_map:
            raise ValueError(f"Duplicate research bout ID: {key}")
        if len(set(uids)) != 2 or any(u not in names for u in uids):
            raise ValueError(f"Invalid or unknown research fighter identity: {key}; {uids}")
        previous = occupied.get(pair)
        if previous is not None and bout_map[previous]["source"] != bout["source"]:
            raise ValueError(f"Cross-provider same-date duplicate research bout: {previous}, {key}")
        # Distinct same-source bouts can share a date and both participants
        # (Silveira/Sakuraba, 1997-12-21). Match the accepted replay policy.
        for i, uid in enumerate(uids, 1):
            provider = "ufcstats" if bout["event_date"] <= LAST_HISTORICAL_DATE else "cito"
            if provider_links.get((provider, bout[f"source_fighter_{i}_id"])) != uid:
                raise ValueError(f"Research fight provider link differs: {key}; fighter {i}")
            if uid not in fighters:
                raise ValueError(f"Reviewed fighter lacks a historical profile: {key}; {uid}")
        occupied.setdefault(pair, key)
        bout_map[key] = bout
        expected.update((key, uid) for uid in uids)
    stat_map = {}
    for stat in stats:
        key = stat["source"] + ":" + stat["source_bout_id"]
        uid = stat["upset_fighter_id"]
        if (key, uid) not in expected or (key, uid) in stat_map:
            raise ValueError("Duplicate or unmatched research statistics.")
        duration = stat["fight_duration_seconds"]
        if type(duration) is not int or duration < 0:
            raise ValueError("Invalid research fight duration.")
        for field in ("knockdowns", "sig_strikes_landed", "sig_strikes_attempted",
                      "takedowns_landed", "takedowns_attempted", "submission_attempts"):
            if type(stat[field]) is not int or stat[field] < 0:
                raise ValueError("Invalid research counts.")
        if (stat["sig_strikes_landed"] > stat["sig_strikes_attempted"]
                or stat["takedowns_landed"] > stat["takedowns_attempted"]
                or stat["control_seconds"] is not None and not 0 <= stat["control_seconds"] <= duration):
            raise ValueError("Invalid research attempts or control duration.")
        stat_map[key, uid] = stat
    if set(stat_map) != expected:
        raise ValueError("Missing paired research statistics.")
    for key, bout in bout_map.items():
        if stat_map[key, bout["upset_fighter_1_id"]]["fight_duration_seconds"] != stat_map[key, bout["upset_fighter_2_id"]]["fight_duration_seconds"]:
            raise ValueError("Research opponents have different durations.")
        amendment = amendments.get(bout["source_bout_id"]) if bout["event_date"] <= LAST_HISTORICAL_DATE else None
        if amendment:
            frozen = amendment["frozen_result"]
            for field in ("winner_name", "source_winner_label", "result_method", "result_round", "result_time"):
                if frozen[field] != bout[field]:
                    raise ValueError("Reviewed amendment differs from frozen result.")
            bout["reviewed_result"] = amendment["current_result"]
    if any(_digest(Path(k)) != v for k, v in hashes.items()):
        raise ValueError("Research inputs changed during build.")
    output.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=output.parent, prefix=".upset-research-") as temporary:
        folder = Path(temporary) / "research"
        folder.mkdir()
        with sqlite3.connect(folder / "upset.sqlite") as db:
            db.execute("PRAGMA foreign_keys=ON")
            db.executescript("""
                CREATE TABLE fighters (id TEXT PRIMARY KEY, name TEXT NOT NULL, search_name TEXT NOT NULL, profile TEXT NOT NULL);
                CREATE INDEX fighter_search ON fighters(search_name);
                CREATE TABLE fights (id TEXT PRIMARY KEY, event_date TEXT NOT NULL, fighter_1 TEXT REFERENCES fighters(id), fighter_2 TEXT REFERENCES fighters(id), payload TEXT NOT NULL);
                CREATE INDEX fight_date ON fights(event_date);
                CREATE INDEX fight_first ON fights(fighter_1,event_date);
                CREATE INDEX fight_second ON fights(fighter_2,event_date);
                CREATE TABLE stats (fight_id TEXT REFERENCES fights(id), fighter_id TEXT REFERENCES fighters(id), payload TEXT NOT NULL, PRIMARY KEY(fight_id,fighter_id));
                CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            """)
            db.executemany("INSERT INTO fighters VALUES (?,?,?,?)", [(uid, names[uid], _name(names[uid]), json.dumps(p)) for uid, p in fighters.items()])
            db.executemany("INSERT INTO fights VALUES (?,?,?,?,?)", [(key, b["event_date"], b["upset_fighter_1_id"], b["upset_fighter_2_id"], json.dumps(b)) for key, b in bout_map.items()])
            db.executemany("INSERT INTO stats VALUES (?,?,?)", [(key, uid, json.dumps(s)) for (key, uid), s in stat_map.items()])
            metadata = {"schema_version": 1, "fighters": len(fighters), "historical_bouts": history_count,
                        "verified_current_bouts": len(current_bouts), "total_bouts": len(bouts),
                        "fighter_stat_rows": len(stats), "earliest_bout": min(r["event_date"] for r in bouts),
                        "latest_bout": max(r["event_date"] for r in bouts),
                        "excluded_current_bouts": cm["bouts_awaiting_identity_review"],
                        "unresolved_current_fighters": cm["unresolved_provider_fighters"],
                        "reviewed_result_amendments": len(amendments), "api_calls": 0,
                        "coverage_verified": False, "mode": "local research; no prediction or model changes"}
            db.executemany("INSERT INTO metadata VALUES (?,?)", [(k, json.dumps(v)) for k, v in metadata.items()])
            if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok" or db.execute("PRAGMA foreign_key_check").fetchall():
                raise ValueError("Research database verification failed.")
        if any(_digest(Path(k)) != v for k, v in hashes.items()):
            raise ValueError("Research inputs changed during database write.")
        manifest = {**metadata, "input_sha256": hashes, "database_sha256": _digest(folder / "upset.sqlite"),
                    "bout_sources": dict(Counter(r["source"] for r in bouts))}
        (folder / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
        folder.rename(output)
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--historical", type=Path, default=Path("data/processed/kaggle_ufc_1994_2026/identified"))
    parser.add_argument("--current", type=Path, default=Path("data/processed/cito_current_archive_v1"))
    parser.add_argument("--registry", type=Path, default=Path("data/processed/cito_gap_reconciliation_v1/fighter_registry.json"))
    parser.add_argument("--accepted", type=Path, default=Path("data/processed/cito_historical_rounds_v1"))
    parser.add_argument("--output", type=Path, default=Path("data/processed/research_v1"))
    args = parser.parse_args()
    try:
        result = build_database(args.historical, args.current, args.registry, args.accepted, args.output)
    except (OSError, ValueError, KeyError, TypeError, sqlite3.Error) as error:
        parser.error(str(error))
    print(json.dumps({k: v for k, v in result.items() if k != "input_sha256"}, indent=2))
    print(f"Saved to: {args.output}")


if __name__ == "__main__":
    main()
