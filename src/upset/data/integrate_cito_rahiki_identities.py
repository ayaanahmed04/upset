"""Restore reviewed Rahiki cohort identities from already saved evidence."""

import argparse
import json
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory

from upset.data.audit_cito_archive import _name
from upset.data.build_research_db import rows
from upset.data.collect_cito_archive import _digest
from upset.data.export_cito_current_archive import _manifest
from upset.data.identity import (
    FighterIdentity, FighterProviderLink, FighterRegistry,
    add_reviewed_cito_link,
    load_fighter_registry,
    save_fighter_registry,
)
from upset.data.models import Fighter
from upset.data.reconcile_cito_archive import _write_verified
from upset.data.stage_current import (
    ACCEPTED_HISTORICAL_FIGHTS_SHA256,
    stage_completed_fights,
)

# Individually reviewed Oct 6 UTC against UFC athlete histories and saved Cito
# histories. Existing permanent IDs are retained; Ollie receives one fixed UUID4.
# Public page observations are identity anchors, not validation of every statistic.
REVIEWED = (
    {"name": "Marwan Rahiki", "cito_fighter_id": "9833306c-3365-486b-b8d5-0451a08b32de",
     "ufcstats_fighter_id": "6eedb757f13b9978", "bout_id": "e0acd0cf4930671b",
     "event_date": "2026-03-14", "opponent_name": "Harry Hardwick",
     "opponent_cito_id": "12837274-f2e0-441d-b278-1ef8f7d66c8d",
     "opponent_ufcstats_id": "2dbc60c52de126d8",
     "public_profile_url": "https://www.ufc.com/athlete/marwan-rahiki",
     "public_bout_url": "https://www.ufc.com/athlete/harry-hardwick",
     "history_sha256": "3cbebf4df06db7b25d535faf2aab86dbc17571a1eb5617521a5f8968d38b9cf3"},
    {"name": "Tommy McMillen", "cito_fighter_id": "1c2f5bca-f74d-49fe-a2e1-873c3f215d16",
     "ufcstats_fighter_id": "6b0a6def604de298",
     "bout_id": "fight-night-september-12-2026-marwan-rahiki-tommy-mcmillen",
     "event_date": "2026-09-12", "opponent_name": "Marwan Rahiki",
     "opponent_cito_id": "9833306c-3365-486b-b8d5-0451a08b32de",
     "opponent_ufcstats_id": "6eedb757f13b9978",
     "public_profile_url": "https://www.ufc.com/athlete/tommy-mcmillen",
     "public_bout_url": "https://www.ufc.com/athlete/tommy-mcmillen",
     "history_sha256": "ae9e1eacf9a4c8e948a34c1c2e55db0ce51f950c17a91ae98b80db0fa1d76fec"},
    {"name": "Ollie Schmid", "cito_fighter_id": "c8f1e9d1-1ab8-434f-b882-7a32f437adfa",
     "new_upset_fighter_id": "8921a07e-aed7-4854-ae5b-1d2bf6882af3",
     "bout_id": "cfc884a249141cba", "event_date": "2026-05-02",
     "opponent_name": "Marwan Rahiki", "opponent_cito_id": "9833306c-3365-486b-b8d5-0451a08b32de",
     "opponent_ufcstats_id": "6eedb757f13b9978",
     "public_profile_url": "https://www.ufc.com/athlete/ollie-schmid",
     "public_bout_url": "https://www.ufc.com/athlete/marwan-rahiki",
     "history_sha256": "fc7732fd131b5ecaac0ff2aab7c0137dd5df48d27816a50a3564a2a736665f67"},
)


def matchup_evidence(rule, canonical, queue, history, registry):
    links = {(r.provider, r.provider_fighter_id): r.upset_fighter_id for r in registry.provider_links}
    own = rule.get("new_upset_fighter_id") or links.get(("ufcstats", rule["ufcstats_fighter_id"]))
    opponent = links.get(("ufcstats", rule["opponent_ufcstats_id"]))
    if (own is None or opponent is None or own == opponent
            or links.get(("cito", rule["opponent_cito_id"])) != opponent
            or ("cito", rule["cito_fighter_id"]) in links):
        raise ValueError("Reviewed matchup identity or known opponent differs.")
    candidates = queue["name_only_candidates"]
    if "new_upset_fighter_id" in rule:
        if candidates or any(r.upset_fighter_id == own or _name(r.display_name) == _name(rule["name"])
                             for r in registry.identities):
            raise ValueError("New fighter conflicts with an existing identity or candidate.")
    elif sum(c["upset_fighter_id"] == own and rule["ufcstats_fighter_id"] in c["ufcstats_fighter_ids"]
             for c in candidates) != 1:
        raise ValueError("Reviewed matchup candidate differs from the unresolved queue.")
    fights = [r for r in canonical if r["source"] == "cito" and r["source_bout_id"] == rule["bout_id"]]
    saved = [r for r in history if str(r.get("bout", {}).get("id")) == rule["bout_id"]]
    if len(fights) != 1 or len(saved) != 1:
        raise ValueError("Missing or duplicate reviewed current matchup evidence.")
    fight, response = fights[0], saved[0]
    sides = [s for s in (1, 2) if fight[f"source_fighter_{s}_id"] == rule["cito_fighter_id"]]
    if len(sides) != 1:
        raise ValueError("Reviewed participant absent from the dated bout.")
    side = sides[0]
    other = 3 - side
    if (fight["event_date"] != rule["event_date"]
            or fight[f"source_fighter_{other}_id"] != rule["opponent_cito_id"]
            or _name(fight[f"fighter_{side}_name"]) != _name(rule["name"])
            or _name(fight[f"fighter_{other}_name"]) != _name(rule["opponent_name"])
            or _name(response["fighterName"]) != _name(rule["name"])
            or _name(response["opponent"]["name"]) != _name(rule["opponent_name"])
            or response["event"]["eventDate"] != rule["event_date"]
            or response.get("isCompleted") is not True
            or response["bout"].get("status") != "completed"
            or response["bout"].get("isCancelled") is True):
        raise ValueError("Reviewed dated matchup, participant or saved history differs.")
    outcome = "win" if fight["winner_name"] == rule["name"] else "loss"
    if (response.get("outcome") != outcome or fight["source_winner_label"] != fight["winner_name"]
            or fight["winner_name"] not in (rule["name"], rule["opponent_name"])
            or response["bout"].get("method") != fight["result_method"]
            or response["bout"].get("resultRound") != fight["result_round"]
            or response["bout"].get("resultTime") != fight["result_time"]):
        raise ValueError("Reviewed current result, method or clock differs.")
    return {**rule, "upset_fighter_id": own, "opponent_upset_fighter_id": opponent,
            "basis": "reviewed public profile ID and dated matchup with existing linked opponent",
            "public_evidence_reviewed_date": "2026-10-06",
            "public_evidence_is_result_verification": False,
            "public_source_state": "search-indexed UFC athlete fight histories; direct fetch unavailable",
            "source_url": fight["source_url"]}


def integrate(current, bundles, historical, output, *, rules=REVIEWED,
              expected_history=ACCEPTED_HISTORICAL_FIGHTS_SHA256):
    if any(output.resolve() == p.resolve() or output.resolve().is_relative_to(p.resolve())
           for p in (current, bundles, historical)):
        raise ValueError("Matchup integration output overlaps sources.")
    hashes = {}
    cm = _manifest(current, hashes)
    registry_path = current / "fighter_registry.json"
    if (_digest(historical) != expected_history
            or cm["identified_subset_manifest"]["input_sha256"]["historical"] != expected_history
            or cm["identified_subset_manifest"]["input_sha256"]["registry"] != _digest(registry_path)):
        raise ValueError("Current identity registry or historical snapshot differs.")
    hashes[str(historical)] = expected_history
    if len({r["cito_fighter_id"] for r in rules}) != len(rules):
        raise ValueError("Duplicate reviewed matchup rule.")
    for rule in rules:
        path = bundles / "fighters" / rule["cito_fighter_id"] / "fights.json"
        if rule["history_sha256"] != _digest(path):
            raise ValueError("Reviewed fighter history hash differs.")
        hashes[str(path)] = _digest(path)
    if output.exists():
        existing = _manifest(output, {})
        if existing["input_sha256"] != hashes or existing["reviewed_matchup_rules"] != list(rules):
            raise ValueError("Existing matchup integration differs; use a new output.")
        return existing
    canonical, stats = rows(current / "fights.jsonl"), rows(current / "fight_stats.jsonl")
    queue = json.loads((current / "review.json").read_text())
    unresolved = {r["cito_fighter_id"]: r for r in queue["unresolved_fighter_identities"]}
    registry = load_fighter_registry(registry_path)
    evidence, profiles = [], []
    for rule in rules:
        pid = rule["cito_fighter_id"]
        if pid not in unresolved:
            raise ValueError("Reviewed matchup fighter absent from unresolved queue.")
        path = bundles / "fighters" / pid / "fights.json"
        wrapper = json.loads(path.read_text())
        if wrapper["http_status"] != 200 or wrapper["expected_cito_fighter_id"] != pid:
            raise ValueError("Saved history wrapper identity differs.")
        item = matchup_evidence(rule, canonical, unresolved[pid], wrapper["response"]["data"], registry)
        item.update(history_sha256=_digest(path), observed_at_utc=wrapper["observed_at_utc"])
        if "new_upset_fighter_id" in rule:
            uid = rule["new_upset_fighter_id"]
            registry = FighterRegistry((*registry.identities, FighterIdentity(uid, rule["name"])),
                (*registry.provider_links, FighterProviderLink("cito", pid, uid, json.dumps(item, sort_keys=True))))
            # No DOB, measurements, status or other profile values are inferred.
            profiles.append({**asdict(Fighter("cito", pid, None, rule["name"],
                              source_url=rule["public_profile_url"])), "upset_fighter_id": uid})
        else:
            registry = add_reviewed_cito_link(registry, cito_fighter_id=pid,
                ufcstats_fighter_id=rule["ufcstats_fighter_id"], evidence=json.dumps(item, sort_keys=True))
        evidence.append(item)
    links = {r.provider_fighter_id: r.upset_fighter_id for r in registry.provider_links if r.provider == "cito"}
    linked = {r["source_bout_id"] for r in canonical if all(r[f"source_fighter_{s}_id"] in links for s in (1, 2))}
    previous = {r["source_bout_id"] for r in rows(current / "identified/fights_identified.jsonl")}
    if not previous <= linked:
        raise ValueError("Matchup integration lost accepted bouts.")
    remaining = [r for pid, r in unresolved.items() if pid not in {e["cito_fighter_id"] for e in evidence}]
    output.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=output.parent, prefix=".upset-matchup-links-") as temporary:
        folder = Path(temporary) / "export"
        folder.mkdir()
        save_fighter_registry(registry, folder / "fighter_registry.json")
        prior_profiles = current / "fighters_identified.jsonl"
        _write_verified(folder / "fighters_identified.jsonl",
                        (rows(prior_profiles) if prior_profiles.exists() else []) + profiles)
        _write_verified(folder / "identity_link_evidence.jsonl", rows(current / "identity_link_evidence.jsonl") + evidence)
        for name in ("fights.jsonl", "fight_stats.jsonl", "bout_provenance.jsonl"):
            (folder / name).write_bytes((current / name).read_bytes())
        _write_verified(folder / "rounds_staged.jsonl", [dict(r, upset_fighter_id=links.get(r["source_fighter_id"]))
                                                       for r in rows(current / "rounds_staged.jsonl")])
        (folder / "review.json").write_text(json.dumps({**queue, "unresolved_fighter_identities": remaining}, indent=2, sort_keys=True) + "\n")
        subset = Path(temporary) / "subset"
        subset.mkdir()
        _write_verified(subset / "fights.jsonl", [r for r in canonical if r["source_bout_id"] in linked])
        _write_verified(subset / "fight_stats.jsonl", [r for r in stats if r["source_bout_id"] in linked])
        identified = stage_completed_fights(subset / "fights.jsonl", subset / "fight_stats.jsonl", folder / "fighter_registry.json",
            historical, folder / "identified", expected_historical_sha256=expected_history)
        identified["input_paths"] = {"registry": str(output / "fighter_registry.json"), "historical": str(historical)}
        (folder / "identified/manifest.json").write_text(json.dumps(identified, indent=2, sort_keys=True) + "\n")
        summary = {**{k: v for k, v in cm.items() if k not in ("input_sha256", "output_sha256", "identified_subset_manifest")},
            "status": "reviewed public matchup identities integrated; current bouts restaged",
            "identity_integrated_at_utc": datetime.now(UTC).isoformat(), "identity_links_added": len(evidence),
            "newly_identified_bouts": len(linked - previous), "identified_current_bouts": len(linked),
            "bouts_awaiting_identity_review": len(canonical) - len(linked), "unresolved_provider_fighters": len(remaining),
            "reviewed_matchup_rules": list(rules), "input_sha256": hashes, "identified_subset_manifest": identified,
            "api_calls": 0, "coverage_verified": False, "training_ready": False,
            "output_sha256": {str(p.relative_to(folder)): _digest(p) for p in folder.rglob("*") if p.is_file()}}
        if any(_digest(Path(p)) != h for p, h in hashes.items()):
            raise ValueError("Matchup identity sources changed during integration.")
        (folder / "manifest.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
        folder.rename(output)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--current", type=Path, default=Path("data/processed/cito_current_refresh_v1"))
    parser.add_argument("--bundles", type=Path, default=Path("data/raw/cito_fighter_bundles_v1"))
    parser.add_argument("--historical", type=Path, default=Path("data/processed/kaggle_ufc_1994_2026/identified/fights_identified.jsonl"))
    parser.add_argument("--output", type=Path, default=Path("data/processed/cito_current_rahiki_v1"))
    args = parser.parse_args()
    try:
        report = integrate(args.current, args.bundles, args.historical, args.output)
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.error(str(error))
    print(json.dumps({k: report[k] for k in ("status", "identity_links_added", "newly_identified_bouts",
        "identified_current_bouts", "bouts_awaiting_identity_review", "unresolved_provider_fighters", "api_calls")}, indent=2))
    print(f"Saved to: {args.output}")


if __name__ == "__main__":
    main()
