"""Apply the reviewed October maintenance identities offline, preserving prior cohorts.

This script consumes explicit reviewed rules; it never infers identity from names.
Earlier excluded bouts remain withheld even when a participant gains a link.
"""

import json
from dataclasses import asdict
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory

from upset.data.audit_cito_archive import _name
from upset.data.build_research_db import rows
from upset.data.collect_cito_archive import _digest
from upset.data.export_cito_current_archive import _manifest
from upset.data.identity import (
    FighterIdentity, FighterProviderLink, FighterRegistry,
    add_reviewed_cito_link, load_fighter_registry, save_fighter_registry,
)
from upset.data.models import Fighter
from upset.data.reconcile_cito_archive import _write_verified
from upset.data.stage_current import stage_completed_fights


def integrate(current, prior, bundles, historical, rules_path, output):
    if output.exists() or any(output.resolve().is_relative_to(p.resolve())
                              for p in (current, prior, bundles, historical, rules_path)):
        raise ValueError("Use a new output separate from every input.")
    hashes = {}
    manifest = _manifest(current, hashes)
    _manifest(prior, hashes)
    rules = json.loads(rules_path.read_text())["rules"]
    hashes[str(rules_path)] = _digest(rules_path)
    canonical = rows(current / "fights.jsonl")
    stats = rows(current / "fight_stats.jsonl")
    queue = json.loads((current / "review.json").read_text())
    unresolved = {r["cito_fighter_id"]: r for r in queue["unresolved_fighter_identities"]}
    registry = load_fighter_registry(current / "fighter_registry.json")
    historical_profiles = {r["upset_fighter_id"]: r
                           for r in rows(historical.parent / "fighters_identified.jsonl")}
    hashes[str(historical.parent / "fighters_identified.jsonl")] = _digest(historical.parent / "fighters_identified.jsonl")
    old_ids = {f["source_bout_id"] for f in rows(prior / "identified/fights_identified.jsonl")}
    new_ids = {f["source_bout_id"] for f in canonical if "2026-10-04" <= f["event_date"] <= "2026-10-24"}
    if len(new_ids) != 39 or len(rules) != 18 or len({r["cito_fighter_id"] for r in rules}) != len(rules):
        raise ValueError("The bounded October cohort or review rule count differs.")
    profiles, evidence = [], []
    for rule in rules:
        pid, uid, name = rule["cito_fighter_id"], rule["upset_fighter_id"], rule["name"]
        if rule["reviewed"] is not True or rule["reviewed_at"] != "2026-10-25" or not rule["public_sources"]:
            raise ValueError("Every identity requires explicit dated review evidence.")
        if pid not in unresolved or any(l.provider == "cito" and l.provider_fighter_id == pid for l in registry.provider_links):
            raise ValueError("Reviewed provider identity is absent or already linked.")
        folder = bundles / "fighters" / pid
        wrappers = {}
        for kind in ("profile", "fights"):
            p = folder / (kind + ".json")
            if _digest(p) != rule["history_sha256" if kind == "fights" else "profile_sha256"]:
                raise ValueError("Reviewed bundle hash differs.")
            hashes[str(p)] = _digest(p)
            w = json.loads(p.read_text())
            if w["http_status"] != 200 or w["expected_cito_fighter_id"] != pid or w["response"].get("success") is False:
                raise ValueError("Reviewed bundle response identity differs.")
            wrappers[kind] = w["response"]["data"]
        profile = wrappers["profile"].get("fighter", wrappers["profile"])
        if profile["id"] != pid or profile["slug"] != rule["slug"] or _name(profile["name"]) != _name(name):
            raise ValueError("Profile does not identify the reviewed participant.")
        history = wrappers["fights"]
        history = history.get("fights", []) if isinstance(history, dict) else history
        for anchor in rule["supporting_history_matchups"]:
            matches = [h for h in history if str(h["bout"]["id"]) == anchor["source_bout_id"]
                       and h["event"]["eventDate"] == anchor["date"]
                       and _name(h["fighterName"]) == _name(name)
                       and _name(h["opponent"]["name"]) == _name(anchor["opponent"])]
            fights = [f for f in canonical if f["source_bout_id"] == anchor["source_bout_id"]]
            if len(matches) != 1 or len(fights) != 1:
                raise ValueError("Missing or duplicate reviewed history anchor.")
            f = fights[0]
            side = next((s for s in (1, 2) if f[f"source_fighter_{s}_id"] == pid), None)
            if not side or f["event_date"] != anchor["date"] or _name(f[f"fighter_{3-side}_name"]) != _name(anchor["opponent"]):
                raise ValueError("History anchor differs from the canonical matchup.")
        if not rule["supporting_history_matchups"] or not set(rule["maintenance_bout_ids"]) <= new_ids:
            raise ValueError("Rules require a history anchor and bounded maintenance bouts.")
        item = {**rule, "basis": "reviewed_profile_demographics_and_dated_matchups",
                "rules_sha256": hashes[str(rules_path)]}
        if rule["identity_action"] == "link_existing":
            candidates = unresolved[pid]["name_only_candidates"]
            if not any(c["upset_fighter_id"] == uid and rule["ufcstats_fighter_id"] in c["ufcstats_fighter_ids"] for c in candidates):
                raise ValueError("Reviewed historical identity differs from the candidate.")
            old = historical_profiles[uid]
            dob = date.fromisoformat(old["date_of_birth"])
            reviewed = date.fromisoformat(rule["reviewed_at"])
            age = reviewed.year - dob.year - ((reviewed.month, reviewed.day) < (dob.month, dob.day))
            if age != rule["public_profile_facts"]["age"]:
                raise ValueError("Historical DOB does not match reviewed public age.")
            registry = add_reviewed_cito_link(registry, cito_fighter_id=pid,
                ufcstats_fighter_id=rule["ufcstats_fighter_id"], evidence=json.dumps(item, sort_keys=True))
        elif rule["identity_action"] == "new_identity":
            if unresolved[pid]["name_only_candidates"] or any(i.upset_fighter_id == uid or _name(i.display_name) == _name(name) for i in registry.identities):
                raise ValueError("New identity conflicts with an existing identity.")
            registry = FighterRegistry((*registry.identities, FighterIdentity(uid, name)),
                (*registry.provider_links, FighterProviderLink("cito", pid, uid, json.dumps(item, sort_keys=True))))
            # Do not infer demographics, status, or images for newly allocated IDs.
            profiles.append({**asdict(Fighter("cito", pid, rule["slug"], name,
                              source_url=rule["public_sources"][0])), "upset_fighter_id": uid})
        else:
            raise ValueError("Unsupported reviewed identity action.")
        evidence.append(item)
    links = {l.provider_fighter_id: l.upset_fighter_id for l in registry.provider_links if l.provider == "cito"}
    accepted_ids = old_ids | new_ids
    accepted = [f for f in canonical if f["source_bout_id"] in accepted_ids]
    if len(accepted) != len(accepted_ids) or any(f[f"source_fighter_{s}_id"] not in links for f in accepted for s in (1, 2)):
        raise ValueError("Maintenance cohort contains unresolved identities.")
    remaining = [r for pid, r in unresolved.items() if pid not in {e["cito_fighter_id"] for e in evidence}]
    output.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=output.parent, prefix=".upset-october-review-") as temporary:
        folder = Path(temporary) / "export"
        folder.mkdir()
        save_fighter_registry(registry, folder / "fighter_registry.json")
        _write_verified(folder / "fighters_identified.jsonl", rows(current / "fighters_identified.jsonl") + profiles)
        _write_verified(folder / "identity_link_evidence.jsonl", rows(current / "identity_link_evidence.jsonl") + evidence)
        for name in ("fights.jsonl", "fight_stats.jsonl", "bout_provenance.jsonl"):
            (folder / name).write_bytes((current / name).read_bytes())
        _write_verified(folder / "rounds_staged.jsonl", [dict(r, upset_fighter_id=links.get(r["source_fighter_id"])) for r in rows(current / "rounds_staged.jsonl")])
        (folder / "review.json").write_text(json.dumps({**queue, "unresolved_fighter_identities": remaining,
            "prior_exclusions_preserved": sorted({f["source_bout_id"] for f in canonical} - accepted_ids)}, indent=2, sort_keys=True) + "\n")
        subset = Path(temporary) / "subset"
        subset.mkdir()
        _write_verified(subset / "fights.jsonl", accepted)
        _write_verified(subset / "fight_stats.jsonl", [s for s in stats if s["source_bout_id"] in accepted_ids])
        staged = stage_completed_fights(subset / "fights.jsonl", subset / "fight_stats.jsonl", folder / "fighter_registry.json", historical, folder / "identified")
        staged["input_paths"] = {"registry": str(output / "fighter_registry.json"), "historical": str(historical)}
        (folder / "identified/manifest.json").write_text(json.dumps(staged, indent=2, sort_keys=True) + "\n")
        summary = {**{k: v for k, v in manifest.items() if k not in ("input_sha256", "output_sha256", "identified_subset_manifest")},
            "status": "October maintenance identities reviewed; prior accepted cohort preserved",
            "identity_links_added": len(evidence), "new_fighter_identities": len(profiles),
            "identified_current_bouts": len(accepted), "bouts_awaiting_identity_review": len(canonical) - len(accepted),
            "unresolved_provider_fighters": len(remaining), "cohort_policy": "Prior accepted bouts plus 39 October maintenance bouts; prior exclusions remain withheld.",
            "input_sha256": hashes, "identified_subset_manifest": staged, "api_calls": 0,
            "output_sha256": {str(p.relative_to(folder)): _digest(p) for p in folder.rglob("*") if p.is_file()}}
        if any(_digest(Path(p)) != h for p, h in hashes.items()):
            raise ValueError("Identity review inputs changed during integration.")
        (folder / "manifest.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
        folder.rename(output)
    return {k: summary[k] for k in ("status", "identity_links_added", "new_fighter_identities", "identified_current_bouts", "bouts_awaiting_identity_review")}


if __name__ == "__main__":
    print(json.dumps(integrate(
        Path("data/processed/cito_current_2026_10_25_v1"),
        Path("data/processed/cito_current_rahiki_v1"),
        Path("data/raw/cito_identity_review_2026_10_25_v1"),
        Path("data/processed/kaggle_ufc_1994_2026/identified/fights_identified.jsonl"),
        Path("data/mappings/cito_2026_10_25_reviewed_identities.json"),
        Path("data/processed/cito_current_2026_10_25_reviewed_v1")), indent=2))
