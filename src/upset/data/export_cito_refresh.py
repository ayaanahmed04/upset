"""Append validated refreshed cards to the existing current cohort offline."""

import argparse
import json
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory

from upset.data.audit_cito_archive import _name, _rows
from upset.data.build_research_db import rows
from upset.data.collect_cito_archive import _digest
from upset.data.export_cito_card import _bout_signature, _read_card
from upset.data.export_cito_current_archive import _manifest, normalize_completed_bout
from upset.data.identity import load_fighter_registry
from upset.data.reconcile_cito_archive import _write_verified
from upset.data.refresh_cito_current import inventory_evidence
from upset.data.stage_current import (
    ACCEPTED_HISTORICAL_FIGHTS_SHA256,
    stage_completed_fights,
)


def export_refresh(current, refresh_root, historical_path, output, *,
                   expected_history=ACCEPTED_HISTORICAL_FIGHTS_SHA256, observed_at=None):
    """Preserve old records and registry; unmatched names remain in the queue."""
    if any(output.resolve() == p.resolve() or output.resolve().is_relative_to(p.resolve())
           for p in (current, refresh_root, historical_path)):
        raise ValueError("Refresh output overlaps inputs.")
    hashes = {}
    cm = _manifest(current, hashes)
    inventory, inventory_hashes = inventory_evidence(refresh_root)
    hashes.update(inventory_hashes)
    report_path = refresh_root / "refresh_report.json"
    report = json.loads(report_path.read_text())
    hashes[str(report_path)] = _digest(report_path)
    for name, digest in report["input_sha256"].items():
        if _digest(Path(name)) != digest:
            raise ValueError("Fresh acquisition input hash differs.")
        hashes[name] = digest
    if report["remaining_cards"] != 0 or report["coverage_verified"] is not False:
        raise ValueError("Refresh collection is partial; resume it before normalization.")
    registry_path = current / "fighter_registry.json"
    if (cm["identified_subset_manifest"]["input_sha256"]["registry"] != _digest(registry_path)
            or cm["identified_subset_manifest"]["input_sha256"]["historical"] != expected_history
            or _digest(historical_path) != expected_history):
        raise ValueError("Current registry or historical snapshot differs.")
    hashes[str(historical_path)] = expected_history
    old_fights, old_stats = rows(current / "fights.jsonl"), rows(current / "fight_stats.jsonl")
    if not old_fights or report["from_date"] <= max(r["event_date"] for r in old_fights):
        raise ValueError("Refresh must start after the current cohort; corrections need separate review.")
    progress_path = refresh_root / "refresh_progress.json"
    progress = json.loads(progress_path.read_text()) if progress_path.exists() else {"cards": {}}
    events = {f"{r['event_date']}/{r['slug']}/{r['provider_event_id']}": r for r in inventory["events"]}
    from upset.data.audit_cito_archive import _competition
    targets = {key for key, r in events.items() if report["from_date"] <= r["event_date"] <= report["through_date"]
               and _competition(r["slug"]) == "ufc_candidate"}
    if set(progress["cards"]) != targets or report["target_cards"] != len(targets):
        raise ValueError("Fresh progress does not account for every targeted UFC card.")
    cards = []
    refresh_findings = []
    for key, result in progress["cards"].items():
        event = events[key]
        if not report["from_date"] <= event["event_date"] <= report["through_date"]:
            raise ValueError("Refresh card is outside the configured date range.")
        if result["status"] != "captured":
            refresh_findings.append({"event": key, **result})
            continue
        folder = refresh_root / "cards" / event["slug"]
        payloads, components, digest = _read_card(folder)
        if digest != result["card_manifest_sha256"] or any(str(payloads["event"].get(k)) != v for k, v in (
                ("slug", event["slug"]), ("eventDate", event["event_date"]), ("id", event["provider_event_id"]))):
            raise ValueError("Refresh card identity or hash differs.")
        hashes[str(folder / "manifest.json")] = digest
        hashes.update({str(folder / f"{kind}.json"): value for kind, value in components.items()})
        cards.append((key, payloads, json.loads((folder / "manifest.json").read_text())))
    if output.exists():
        previous = _manifest(output, {})
        if previous["input_sha256"] != hashes:
            raise ValueError("Existing refresh export differs; use a new immutable output.")
        return previous
    registry = load_fighter_registry(registry_path)
    links = {r.provider_fighter_id: r.upset_fighter_id for r in registry.provider_links if r.provider == "cito"}
    names, ufc_ids = defaultdict(list), defaultdict(list)
    for identity in registry.identities:
        names[_name(identity.display_name)].append(identity.upset_fighter_id)
    for link in registry.provider_links:
        if link.provider == "ufcstats":
            ufc_ids[link.upset_fighter_id].append(link.provider_fighter_id)
    queue = json.loads((current / "review.json").read_text())
    unresolved = {r["cito_fighter_id"]: r for r in queue["unresolved_fighter_identities"]}
    fights, stats = list(old_fights), list(old_stats)
    rounds = rows(current / "rounds_staged.jsonl")
    provenance = rows(current / "bout_provenance.jsonl")
    seen = {r["source_bout_id"] for r in fights}
    occupied = {(r["event_date"], *sorted((r["source_fighter_1_id"], r["source_fighter_2_id"]))) for r in fights}
    added = examined = 0
    for key, payloads, manifest in cards:
        listing = _rows(payloads["bouts"], "bouts", "fights", "items", "results")
        if listing is None or len({str(b["id"]) for b in listing}) != len(listing):
            raise ValueError("Invalid refreshed bout listing.")
        # Reject orphan measurements and inconsistent endpoint bout lists.
        bids = {str(b["id"]) for b in listing}
        raw_stats = payloads["stats"]
        if any(str(r["boutId"]) not in bids for kind in ("boutStats", "roundStats") for r in raw_stats[kind]):
            raise ValueError("Refreshed stats contain an unlisted bout.")
        for endpoint in ("event", "stats"):
            embedded = payloads[endpoint]["bouts"]
            if len(embedded) != len(listing) or {str(b["id"]) for b in embedded} != bids:
                raise ValueError("Refreshed endpoint bout coverage differs.")
        for bout in listing:
            bid = str(bout["id"])
            examined += 1
            try:
                if bid in seen:
                    raise ValueError("Refresh repeats a prior bout ID.")
                seen.add(bid)
                for endpoint in ("event", "stats"):
                    embedded = [b for b in payloads[endpoint]["bouts"] if str(b["id"]) == bid]
                    if len(embedded) != 1 or _bout_signature(embedded[0]) != _bout_signature(bout):
                        raise ValueError("Refreshed participants or result differ between endpoints.")
                if bout.get("isCancelled") is True or bout.get("status") != "completed":
                    raise ValueError("Bout is cancelled or not completed; no history contribution.")
                totals = [r for r in raw_stats["boutStats"] if str(r["boutId"]) == bid]
                observed_rounds = [r for r in raw_stats["roundStats"] if str(r["boutId"]) == bid]
                fight, paired, normalized_rounds = normalize_completed_bout(bout, payloads["event"], totals, observed_rounds)
                pair = (fight["event_date"], *sorted((fight["source_fighter_1_id"], fight["source_fighter_2_id"])))
                if pair in occupied:
                    raise ValueError("Refresh duplicates a dated provider matchup.")
                occupied.add(pair)
            except (ValueError, KeyError, TypeError) as error:
                refresh_findings.append({"event": key, "cito_bout_id": bid, "status": "bout_requires_review", "reason": str(error)})
                continue
            fights.append(fight)
            stats.extend(paired)
            added += 1
            evidence = {"source_bout_id": bid, "event": key,
                        "card_manifest_sha256": _digest(refresh_root / "cards" / manifest["event_slug"] / "manifest.json"),
                        "raw_stats_sha256": manifest["sha256"]["stats"], "observed_at_utc": manifest["observed_at_utc"]["stats"],
                        "totals_basis": "provider_totals_reconciled_with_rounds", "provider_fight_totals_present": True}
            provenance.append(evidence)
            rounds.extend({**r, **evidence, "upset_fighter_id": links.get(r["source_fighter_id"])} for r in normalized_rounds)
            for fighter in bout["fighters"]:
                pid = fighter["fighterId"]
                if pid in links:
                    continue
                item = unresolved.setdefault(pid, {"cito_fighter_id": pid, "source_names": [], "source_slugs": [],
                    "supporting_bouts": [], "name_only_candidates": [], "profile_observations": []})
                item["source_names"] = sorted(set(item["source_names"]) | {fighter["fighterName"]})
                item["source_slugs"] = sorted(set(item["source_slugs"]) | {fighter["fighterSlug"]})
                item["supporting_bouts"].append({"source_bout_id": bid, "event_date": fight["event_date"]})
                candidates = {r["upset_fighter_id"]: r for r in item["name_only_candidates"]}
                for uid in names[_name(fighter["fighterName"])]:
                    candidates.setdefault(uid, {"upset_fighter_id": uid, "ufcstats_fighter_ids": sorted(ufc_ids[uid]), "basis": "name_only_not_accepted"})
                item["name_only_candidates"] = list(candidates.values())
                if isinstance(fighter.get("profile"), dict):
                    item["profile_observations"].append({"profile": fighter["profile"], "observed_at_utc": manifest["observed_at_utc"]["bouts"],
                                                        "card_manifest_sha256": evidence["card_manifest_sha256"]})
    linked = {r["source_bout_id"] for r in fights if all(r[f"source_fighter_{i}_id"] in links for i in (1, 2))}
    previous_linked = {r["source_bout_id"] for r in rows(current / "identified/fights_identified.jsonl")}
    if not previous_linked <= linked:
        raise ValueError("Refresh lost previously accepted identity links.")
    output.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=output.parent, prefix=".upset-refresh-") as temporary:
        folder = Path(temporary) / "export"
        folder.mkdir()
        for name, batch in (("fights.jsonl", fights), ("fight_stats.jsonl", stats),
                            ("rounds_staged.jsonl", rounds), ("bout_provenance.jsonl", provenance)):
            _write_verified(folder / name, batch)
        (folder / "fighter_registry.json").write_bytes(registry_path.read_bytes())
        if (current / "identity_link_evidence.jsonl").exists():
            (folder / "identity_link_evidence.jsonl").write_bytes((current / "identity_link_evidence.jsonl").read_bytes())
        if (current / "fighters_identified.jsonl").exists():
            (folder / "fighters_identified.jsonl").write_bytes((current / "fighters_identified.jsonl").read_bytes())
        review = {**queue, "unresolved_fighter_identities": list(unresolved.values()), "refresh_findings": refresh_findings,
                  "refresh_excluded_listing_events": report["excluded_listing_events"]}
        (folder / "review.json").write_text(json.dumps(review, sort_keys=True, indent=2) + "\n")
        subset = Path(temporary) / "subset"
        subset.mkdir()
        _write_verified(subset / "fights.jsonl", [r for r in fights if r["source_bout_id"] in linked])
        _write_verified(subset / "fight_stats.jsonl", [r for r in stats if r["source_bout_id"] in linked])
        identified = stage_completed_fights(subset / "fights.jsonl", subset / "fight_stats.jsonl", folder / "fighter_registry.json",
            historical_path, folder / "identified", expected_historical_sha256=expected_history, observed_at=observed_at)
        identified["input_paths"] = {"registry": str(output / "fighter_registry.json"), "historical": str(historical_path)}
        (folder / "identified/manifest.json").write_text(json.dumps(identified, indent=2, sort_keys=True) + "\n")
        summary = {"schema_version": 1, "status": "later current cards normalized; coverage review remains open",
                   "processed_at_utc": (observed_at or datetime.now(UTC)).isoformat(), "refreshed_bouts_examined": examined,
                   "canonical_bouts_added": added, "identified_bouts_added": len(linked - previous_linked),
                   "canonical_current_bouts": len(fights), "canonical_fighter_stats": len(stats), "current_round_rows": len(rounds),
                   "identified_current_bouts": len(linked), "bouts_awaiting_identity_review": len(fights) - len(linked),
                   "unresolved_provider_fighters": len(unresolved), "refresh_findings": len(refresh_findings),
                   "latest_bout": max(r["event_date"] for r in fights), "acquisition_through_date": report["through_date"],
                   "totals_basis": dict(Counter(r["totals_basis"] for r in provenance)),
                   "api_calls": 0, "coverage_verified": False, "training_ready": False,
                   "input_sha256": hashes, "identified_subset_manifest": identified,
                   "output_sha256": {str(p.relative_to(folder)): _digest(p) for p in folder.rglob("*") if p.is_file()}}
        if any(_digest(Path(p)) != h for p, h in hashes.items()):
            raise ValueError("Refresh inputs changed during normalization.")
        (folder / "manifest.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
        folder.rename(output)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--current", type=Path, default=Path("data/processed/cito_current_identity_v3"))
    parser.add_argument("--refresh", type=Path, required=True)
    parser.add_argument("--historical", type=Path, default=Path("data/processed/kaggle_ufc_1994_2026/identified/fights_identified.jsonl"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = export_refresh(args.current, args.refresh, args.historical, args.output)
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.error(str(error))
    print(json.dumps({k: v for k, v in result.items() if k not in ("input_sha256", "output_sha256", "identified_subset_manifest")}, indent=2))
    print(f"Saved to: {args.output}")


if __name__ == "__main__":
    main()
