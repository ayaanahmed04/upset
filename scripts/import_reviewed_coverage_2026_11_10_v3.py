"""Complete the November 10 recent coverage review in a new archive version.

The previous importer is preserved because the v2 archive manifest binds its
source hash. This version also handles an explicit multi-candidate identity
decision and retains the reviewed reason for a source discrepancy.
"""

import json
from collections import defaultdict
from contextlib import closing
from dataclasses import asdict
from pathlib import Path
from shutil import copyfile
from tempfile import TemporaryDirectory

from import_recent_card import verify_preservation

from upset.data.audit_cito_archive import _name, _rows
from upset.data.build_research_db import build_database, rows
from upset.data.collect_cito_archive import _digest
from upset.data.export_cito_card import _bout_signature, _read_card
from upset.data.export_cito_current_archive import _manifest, normalize_completed_bout
from upset.data.identity import FighterIdentity, FighterProviderLink, FighterRegistry, load_fighter_registry, save_fighter_registry
from upset.data.models import Fighter
from upset.data.reconcile_cito_archive import _write_verified
from upset.data.stage_current import stage_completed_fights
from upset.research_app import connect

DATA = Path("data/processed")
PRIOR = DATA / "cito_current_2026_11_10_reviewed_v2"
OLD_DB = DATA / "research_2026_11_10_reviewed_v2/upset.sqlite"
ARCHIVE = DATA / "cito_current_2026_11_10_reviewed_v3"
DATABASE = DATA / "research_2026_11_10_reviewed_v3"
HISTORY = DATA / "kaggle_ufc_1994_2026/identified"
RULES = Path("data/mappings/cito_2026_11_10_coverage_completion.json")


def index_rows(path):
    indexed = defaultdict(list)
    for row in rows(path):
        indexed[row["source_bout_id"]].append(row)
    return indexed


def read_reviewed_bouts(rules, hashes):
    normalized = {}
    provenance = {row["source_bout_id"]: row for row in rows(PRIOR / "bout_provenance.jsonl")}
    canonical = {row["source_bout_id"]: row for row in rows(PRIOR / "fights.jsonl")}
    totals = index_rows(PRIOR / "fight_stats.jsonl")
    rounds = index_rows(PRIOR / "rounds_staged.jsonl")
    identities = defaultdict(list)
    for card in rules["cards"]:
        folder = Path(card["card"])
        payload, source_hashes, manifest_hash = _read_card(folder)
        hashes.update({str(folder / f"{name}.json"): sha for name, sha in source_hashes.items()})
        hashes[str(folder / "manifest.json")] = manifest_hash
        event, stats = payload["event"], payload["stats"]
        if event["eventDate"] != card["date"]:
            raise ValueError("Reviewed event date differs from the capture.")
        listing = _rows(payload["bouts"], "bouts", "fights", "items", "results")
        for rule in card["bouts"]:
            bid = rule["source_bout_id"]
            evidence = provenance[bid]
            if bid in normalized or evidence["card_manifest_sha256"] != manifest_hash or evidence["raw_stats_sha256"] != source_hashes["stats"]:
                raise ValueError(f"Repeated bout or different archived evidence: {bid}.")
            listed = [bout for bout in listing if str(bout["id"]) == bid]
            if len(listed) != 1:
                raise ValueError(f"Expected one listed bout: {bid}.")
            for endpoint in (event, stats):
                embedded = [bout for bout in endpoint["bouts"] if str(bout["id"]) == bid]
                if len(embedded) != 1 or _bout_signature(embedded[0]) != _bout_signature(listed[0]):
                    raise ValueError(f"Saved UFC endpoints disagree: {bid}.")
            raw_totals, raw_rounds = ([row for row in stats[key] if str(row["boutId"]) == bid]
                                      for key in ("boutStats", "roundStats"))
            fight, paired, observed = normalize_completed_bout(listed[0], event, raw_totals, raw_rounds)
            expected = (rule["winner"], rule["method"], rule["round"], rule["time"])
            if (fight["winner_name"], fight["result_method"], fight["result_round"], fight["result_time"]) != expected or {
                    fight["fighter_1_name"], fight["fighter_2_name"]} != {rule["winner"], rule["opponent"]}:
                raise ValueError(f"The source result differs from the official result: {bid}.")
            if (fight != canonical[bid] or paired != totals[bid]
                    or len(observed) != 2 * rule["round"]
                    or observed != [{key: row[key] for key in observed[0]} for row in rounds[bid]]):
                raise ValueError(f"Saved normalized fight or both sets of stats differ from the capture: {bid}.")
            normalized[bid] = fight, paired, {**rule, "date": card["date"], "source_url": card["source_url"]}
            for person in listed[0]["fighters"]:
                identities[person["fighterId"]].append(
                    (person["fighterName"], person["fighterSlug"], bid, card["source_url"]))
    return normalized, identities


def resolve_identities(rules, prior, queue, observed, db):
    existing = {row.upset_fighter_id: row.display_name for row in prior.identities}
    names = defaultdict(set)
    for uid, name in existing.items():
        names[_name(name)].add(uid)
    provider_ids = {row.provider_fighter_id for row in prior.provider_links if row.provider == "cito"}
    unresolved = {row["cito_fighter_id"]: row for row in queue["unresolved_fighter_identities"]}
    decisions = {row["cito_fighter_id"]: row for row in rules["identities"]}
    if len(decisions) != len(rules["identities"]) or set(observed) - provider_ids != decisions.keys():
        raise ValueError("Each unlinked participant needs exactly one reviewed decision.")

    profiles, evidence, links, identities = [], [], list(prior.provider_links), list(prior.identities)
    for pid, rule in decisions.items():
        name, slug, uid = (rule[key] for key in ("name", "slug", "upset_fighter_id"))
        if {(n, s) for n, s, _, _ in observed[pid]} != {(name, slug)}:
            raise ValueError(f"Dated provider observations disagree for {name}.")
        candidates = {row["upset_fighter_id"] for row in unresolved[pid]["name_only_candidates"]}
        if names[_name(name)] != candidates:
            raise ValueError(f"Current same-name identities differ from the review for {name}.")
        if rule["action"] == "link":
            if (uid not in candidates or candidates != set(rule["existing_candidates"])
                    or _name(existing[uid]) != _name(name) or not rule.get("source_url")):
                raise ValueError(f"Existing identity does not match the reviewed link for {name}.")
            if len(candidates) > 1:
                profile = json.loads(db.execute("SELECT profile FROM fighters WHERE id=?", (uid,)).fetchone()[0])
                expected = rule["expected_profile"]
                if (not expected or not rule.get("distinct_from_url")
                        or any(profile[key] != value for key, value in expected.items())):
                    raise ValueError(f"Ambiguous identity needs a matching archived profile for {name}.")
        elif rule["action"] == "new":
            if uid in existing or candidates:
                raise ValueError(f"New identity must have no current candidate for {name}.")
            identities.append(FighterIdentity(uid, name))
            existing[uid] = name
            names[_name(name)].add(uid)
            profile = Fighter("cito", pid, slug, name,
                **{field: rule[field] for field in ("height_inches", "weight_lbs", "reach_inches") if field in rule},
                source_url=rule.get("source_url") or observed[pid][0][3])
            profiles.append({**asdict(profile), "upset_fighter_id": uid})
        else:
            raise ValueError("Unsupported reviewed identity action.")
        note = {**rule, "reviewed_at": rules["reviewed_at"],
                "dated_bout_sources": {bid: url for _, _, bid, url in observed[pid]}}
        links.append(FighterProviderLink("cito", pid, uid, json.dumps(note, sort_keys=True)))
        evidence.append(note)
    return FighterRegistry(tuple(identities), tuple(links)), profiles, evidence


def main():
    if ARCHIVE.exists() or DATABASE.exists():
        raise ValueError("Use fresh release directories.")
    hashes = {str(path): _digest(path) for path in (RULES, OLD_DB, Path(__file__))}
    previous = _manifest(PRIOR, hashes)
    rules = json.loads(RULES.read_text())
    normalized, observed = read_reviewed_bouts(rules, hashes)
    queue = json.loads((PRIOR / "review.json").read_text())
    pending = set(queue["withheld_prior_bout_ids"])
    held = rules["pending_results"]
    if not normalized or pending != normalized.keys() | held.keys() or normalized.keys() & held.keys():
        raise ValueError("Every pending bout needs exactly one reviewed disposition.")
    with closing(connect(OLD_DB)) as db:
        registry, profiles, evidence = resolve_identities(
            rules, load_fighter_registry(PRIOR / "fighter_registry.json"), queue, observed, db)
    links = {row.provider_fighter_id: row.upset_fighter_id for row in registry.provider_links if row.provider == "cito"}
    added_ids = {row["cito_fighter_id"] for row in evidence}
    queue["withheld_prior_bout_ids"] = sorted(pending - normalized.keys())
    queue["unresolved_fighter_identities"] = [row for row in queue["unresolved_fighter_identities"]
                                             if row["cito_fighter_id"] not in added_ids]
    queue["november_10_coverage_backfill"].extend(review for _, _, review in normalized.values())
    queue["pending_result_discrepancies"] = held

    with TemporaryDirectory(dir=DATA, prefix=".upset-reviewed-coverage-") as temporary:
        folder = Path(temporary) / "current"
        folder.mkdir()
        for name in ("fights.jsonl", "fight_stats.jsonl", "bout_provenance.jsonl"):
            copyfile(PRIOR / name, folder / name)
        save_fighter_registry(registry, folder / "fighter_registry.json")
        all_rounds = rows(PRIOR / "rounds_staged.jsonl")
        for row in all_rounds:
            if row["source_bout_id"] in normalized:
                row["upset_fighter_id"] = links[row["source_fighter_id"]]
        for name, batch in (
            ("accepted_fights.jsonl", rows(PRIOR / "accepted_fights.jsonl") +
             [fight for fight, _, _ in normalized.values()]),
            ("accepted_fight_stats.jsonl", rows(PRIOR / "accepted_fight_stats.jsonl") +
             [row for _, paired, _ in normalized.values() for row in paired]),
            ("fighters_identified.jsonl", rows(PRIOR / "fighters_identified.jsonl") + profiles),
            ("identity_link_evidence.jsonl", rows(PRIOR / "identity_link_evidence.jsonl") + evidence),
            ("rounds_staged.jsonl", all_rounds),
        ):
            _write_verified(folder / name, batch)
        (folder / "review.json").write_text(json.dumps(queue, indent=2, ensure_ascii=False) + "\n")
        staged = stage_completed_fights(folder / "accepted_fights.jsonl", folder / "accepted_fight_stats.jsonl",
            folder / "fighter_registry.json", HISTORY / "fights_identified.jsonl", folder / "identified")
        staged["input_paths"] = {"registry": str(ARCHIVE / "fighter_registry.json"),
                                 "historical": str(HISTORY / "fights_identified.jsonl")}
        (folder / "identified/manifest.json").write_text(json.dumps(staged, indent=2) + "\n")
        manifest = {**previous, "status": "Dated November 10 coverage completion review",
                    "identified_current_bouts": previous["identified_current_bouts"] + len(normalized),
                    "backfilled_bouts": len(normalized), "new_bouts": 0, "new_identities": len(profiles),
                    "identity_links_added": len(evidence), "bouts_awaiting_identity_review": len(queue["withheld_prior_bout_ids"]),
                    "unresolved_provider_fighters": len(queue["unresolved_fighter_identities"]),
                    "identified_subset_manifest": staged, "input_sha256": hashes,
                    "output_sha256": {str(path.relative_to(folder)): _digest(path)
                                      for path in folder.rglob("*") if path.is_file()}}
        if any(_digest(Path(path)) != sha for path, sha in hashes.items()):
            raise ValueError("A verified review input changed during the build.")
        (folder / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
        folder.rename(ARCHIVE)
    build_database(HISTORY, ARCHIVE, ARCHIVE / "fighter_registry.json", DATA / "cito_historical_rounds_v1", DATABASE)
    preservation = verify_preservation(OLD_DB, DATABASE / "upset.sqlite")
    if [preservation[key]["added"] for key in ("fighters", "fights", "stats")] != [
            len(profiles), len(normalized), 2 * len(normalized)]:
        raise ValueError("The new database added unexpected rows.")
    print(json.dumps(preservation, indent=2))


if __name__ == "__main__":
    main()
