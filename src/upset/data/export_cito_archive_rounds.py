"""Export a verified historical round subset and evidence-backed Cito registry.

Current bouts stay staged. Labels are separate from round measurements, and
the accepted historical snapshot and original registry are never overwritten.
"""

import argparse
import json
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory

from upset.data.collect_cito_archive import _digest
from upset.data.collect_cito_card import BASE_URL
from upset.data.identity import (
    FighterProviderLink,
    FighterRegistry,
    load_fighter_registry,
    save_fighter_registry,
)
from upset.data.reconcile_cito_archive import (
    COMMON_STATS,
    _history,
    _method,
    _reviewed_result,
    _write_verified,
    reconcile_archive,
)
from upset.data.stage_current import ACCEPTED_HISTORICAL_FIGHTS_SHA256

BRIDGE_FILES = {
    "bout_matches.jsonl", "bout_review.jsonl", "fighter_link_proposals.jsonl",
    "round_stats_staged.jsonl", "historical_without_verified_totals.jsonl",
    "duplicate_historical_matches.jsonl",
}


def read_bridge(bridge: Path) -> tuple[dict, dict]:
    """Verify all immutable bridge files before using any recorded proposal."""
    manifest = json.loads((bridge / "manifest.json").read_text())
    if manifest.get("schema_version") != 1 or set(manifest["output_sha256"]) != BRIDGE_FILES:
        raise ValueError("Unsupported bridge manifest.")
    rows = {}
    for name, digest in manifest["output_sha256"].items():
        path = bridge / name
        if _digest(path) != digest:
            raise ValueError(f"Bridge hash differs: {name}")
        rows[name] = [json.loads(line) for line in path.read_text().splitlines()]
        if any(not isinstance(row, dict) for row in rows[name]):
            raise ValueError(f"Invalid bridge row: {name}")
    return manifest, rows


def select_verified_rounds(rows: dict, registry) -> tuple[list, list, list, dict]:
    """Require unique paired evidence, consistent identities and complete rounds."""
    known = {i.upset_fighter_id for i in registry.identities}
    existing = {(link.provider, link.provider_fighter_id): link.upset_fighter_id
                for link in registry.provider_links}
    matches = {}
    historical_counts = Counter()
    links = {}
    evidence = defaultdict(list)
    for record in rows["bout_matches.jsonl"]:
        if record["status"] != "totals_verified_proposal":
            continue
        candidates = record["candidates"]
        if len(candidates) != 1:
            raise ValueError("Verified bout must have one candidate.")
        candidate = candidates[0]
        uids = candidate["upset_fighter_ids_in_cito_order"]
        fighters = record["cito_fighters"]
        if (candidate["stat_differences"] or candidate["compared_stat_fields"] < 24
                or len(fighters) != 2 or len(uids) != 2 or len(set(uids)) != 2
                or any(uid not in known for uid in uids)):
            raise ValueError("Incomplete verified-bout evidence.")
        key = (record["card_manifest_sha256"], record["cito_bout_id"])
        if key in matches:
            raise ValueError("Duplicate provider bout in bridge.")
        matches[key] = record
        historical_counts[candidate["historical_bout_id"]] += 1
        for i, fighter in enumerate(fighters):
            pid, uid = fighter["fighterId"], uids[i]
            if (existing.get(("cito", pid), uid) != uid
                    or existing.get(("ufcstats", candidate["ufcstats_fighter_ids_in_cito_order"][i])) != uid
                    or links.get(pid, uid) != uid):
                raise ValueError("Provider identity conflicts with historical or saved evidence.")
            links[pid] = uid
            evidence[pid].append({"historical_bout_id": candidate["historical_bout_id"],
                "cito_bout_id": record["cito_bout_id"], "event": record["event"],
                "card_manifest_sha256": record["card_manifest_sha256"],
                "ufcstats_fighter_id": candidate["ufcstats_fighter_ids_in_cito_order"][i]})
    proposal_links = {}
    for proposal in rows["fighter_link_proposals.jsonl"]:
        if proposal["status"] == "conflicting_evidence":
            raise ValueError("Conflicting fighter proposals need review.")
        if proposal["status"] == "unique_evidence_proposal":
            if len(proposal["candidates"]) != 1:
                raise ValueError("Invalid unique fighter proposal.")
            pid = proposal["cito_fighter_id"]
            if pid in proposal_links:
                raise ValueError("Duplicate fighter proposal.")
            proposal_links[pid] = proposal["candidates"][0]["upset_fighter_id"]
    if links != proposal_links:
        raise ValueError("Fighter proposals differ from paired bout evidence.")
    if any(count != 1 for count in historical_counts.values()):
        raise ValueError("Multiple provider bouts match one historical bout.")
    groups = defaultdict(list)
    selected = []
    skipped = Counter()
    seen = set()
    for row in rows["round_stats_staged.jsonl"]:
        key = (row["card_manifest_sha256"], row["source_bout_id"])
        match = matches.get(key)
        if match is None:
            skipped["bout_without_verified_historical_totals"] += 1
            continue
        candidate = match["candidates"][0]
        uid = links.get(row["source_fighter_id"])
        pair = {f["fighterId"]: candidate["upset_fighter_ids_in_cito_order"][i]
                for i, f in enumerate(match["cito_fighters"])}
        bid = candidate["historical_bout_id"]
        number = row["round_number"]
        row_key = (bid, uid, number)
        if (row.get("duplicate_historical_match") or type(number) is not int or number < 1
                or uid is None or pair.get(row["source_fighter_id"]) != uid
                or row["proposed_upset_fighter_id"] != uid
                or row["candidate_historical_bout_id"] != bid or row_key in seen):
            raise ValueError("Round identity, duplicate or bout evidence differs.")
        seen.add(row_key)
        identified = {**row, "historical_bout_id": bid, "upset_fighter_id": uid,
                      "event_date": candidate["historical_event_date"]}
        selected.append(identified)
        groups[key].append(identified)
    for key, match in matches.items():
        number = match["accepted_historical_result"]["result_round"]
        if type(number) is not int or number < 1:
            raise ValueError("Historical result has no valid round count.")
        actual = groups[key]
        expected = {(uid, n) for uid in match["candidates"][0]["upset_fighter_ids_in_cito_order"]
                    for n in range(1, number + 1)}
        if (len(actual) != match["round_rows"]
                or {(row["upset_fighter_id"], row["round_number"]) for row in actual} != expected):
            raise ValueError(f"Historical round coverage differs: {match['cito_bout_id']}")
    accepted_links = [{"cito_fighter_id": pid, "upset_fighter_id": uid,
                       "acceptance_basis": "unique paired historical totals and registry source IDs",
                       "supporting_bouts": evidence[pid]} for pid, uid in sorted(links.items())]
    return selected, accepted_links, list(matches.values()), dict(skipped)


def result_record(match: dict) -> dict:
    """Keep amendments and unresolved result classifications visible to callers."""
    frozen = match["accepted_historical_result"]
    revision = match.get("reviewed_current_result")
    differences = match.get("metadata_differences", [])
    unresolved = []
    for diff in differences:
        if revision or diff["cito"] is None or diff["field"] == "status":
            continue
        if diff["field"] == "method":
            left, right = _method(diff["cito"]), _method(diff["historical"])
            if ((left, right) in (("KO/TKO", "TKO - Doctor's Stoppage"),
                                 ("CNC", "Could Not Continue"))):
                continue
        unresolved.append(diff)
    return {"historical_bout_id": match["candidates"][0]["historical_bout_id"],
            "cito_bout_id": match["cito_bout_id"], "frozen_result": frozen,
            "current_result": revision if revision else (None if unresolved else frozen),
            "resolution": "reviewed_amendment" if revision else (
                "requires_result_review" if unresolved else "historical_result_verified"),
            "provider_result": match["cito_result"], "provider_fighters": match["cito_fighters"],
            "metadata_differences": differences, "unresolved_differences": unresolved,
            "card_manifest_sha256": match["card_manifest_sha256"]}


def gap_plan(rows: dict, inventory: dict, progress: dict) -> dict:
    """Request only absent historical rows and flagged current totals."""
    requests = {}

    def add(scope, identifier, endpoint, reason, *, fallback_id=None):
        url = f"{BASE_URL}/{scope}/{identifier}/{endpoint}"
        item = {"scope": scope, "identifier": identifier, "endpoint": endpoint,
                "source_url": url, "reason": reason}
        if fallback_id and fallback_id != identifier:
            item["fallback_identifier"] = fallback_id
        requests[url] = item

    by_history = defaultdict(list)
    by_source = defaultdict(list)
    for bout in rows["bout_matches.jsonl"]:
        by_source[bout["cito_bout_id"]].append(bout)
        for candidate in bout["candidates"]:
            by_history[candidate["historical_bout_id"]].append(bout)
        if (bout["status"] == "post_snapshot" and bout["cito_has_stats"] is True
                and bout["total_rows"] != 2):
            add("bouts", bout["cito_bout_id"], "stats", "current_bout_missing_paired_totals")
    unresolved = []
    missing_dates = set()
    for historical in rows["historical_without_verified_totals.jsonl"]:
        bid = historical["source_bout_id"]
        matches = by_history.get(bid) or by_source.get(bid) or []
        if len(matches) == 1 and matches[0]["total_rows"] == 2 and matches[0]["round_rows"]:
            unresolved.append({"historical_bout_id": bid, "reason": "existing_stats_need_match_review"})
            continue
        identifier = matches[0]["cito_bout_id"] if len(matches) == 1 else bid
        for endpoint in ("stats", "rounds"):
            add("bouts", identifier, endpoint, f"historical_bout_missing_stats:{bid}", fallback_id=bid)
        if not matches:
            missing_dates.add(historical["event_date"])
    for event in inventory["events"]:
        key = f"{event['event_date']}/{event['slug']}/{event['provider_event_id']}"
        if progress["cards"].get(key, {}).get("status") != "failed":
            continue
        if any(abs((date.fromisoformat(event["event_date"]) - date.fromisoformat(day)).days) <= 1
               for day in missing_dates):
            for endpoint in ("stats", "bouts"):
                add("events", event["slug"], endpoint, "failed_event_near_missing_historical_bouts")
    targets = sorted(requests.values(), key=lambda row: row["source_url"])
    return {"schema_version": 1, "requests": targets, "manual_match_review": unresolved,
            "primary_requests": len(targets), "maximum_requests_including_fallbacks":
            len(targets) + sum("fallback_identifier" in row for row in targets),
            "status": "targeted availability probe plan; responses require reconciliation"}


def export_rounds(bridge: Path, historical: Path, registry_path: Path, root: Path, output: Path,
                  *, expected_history_sha256=ACCEPTED_HISTORICAL_FIGHTS_SHA256) -> dict:
    if (output.exists() or any(output.resolve().is_relative_to(path.resolve())
                               for path in (bridge, historical, root))):
        raise ValueError("Output exists or overlaps an input.")
    manifest, rows = read_bridge(bridge)
    paths = {"historical_fights": historical / "fights_identified.jsonl",
             "historical_stats": historical / "fight_stats_identified.jsonl",
             "fighter_registry": registry_path, "inventory": root / "inventory/manifest.json",
             "collection_progress": root / "collection_progress.json"}
    hashes = {key: _digest(path) for key, path in paths.items()}
    if hashes != manifest["input_sha256"] or hashes["historical_fights"] != expected_history_sha256:
        raise ValueError("Export inputs differ from the accepted bridge or historical snapshot.")
    if manifest.get("matcher_revision") != 2:
        raise ValueError("Rebuild the bridge with reviewed names and the result amendment.")
    registry = load_fighter_registry(registry_path)
    history, _by_date, stats = _history(paths["historical_fights"], paths["historical_stats"], registry)
    rounds, links, matches, skipped = select_verified_rounds(rows, registry)
    if not rounds or not matches:
        raise ValueError("No verified historical rounds to export.")
    indexed_history = {row["source_bout_id"]: row for row in history}
    if len(matches) != manifest["historical_bouts_with_verified_totals"]:
        raise ValueError("Verified bout count differs from bridge manifest.")
    groups = defaultdict(list)
    for row in rounds:
        groups[(row["historical_bout_id"], row["upset_fighter_id"])].append(row)
    for match in matches:
        candidate = match["candidates"][0]
        bid = candidate["historical_bout_id"]
        accepted = indexed_history[bid]
        if (candidate["historical_event_date"] != accepted["event_date"]
                or set(candidate["upset_fighter_ids_in_cito_order"])
                != {accepted["upset_fighter_1_id"], accepted["upset_fighter_2_id"]}):
            raise ValueError("Historical participant or date evidence differs.")
        frozen = match["accepted_historical_result"]
        expected_result = {key: accepted.get(key) for key in (
            "winner_name", "source_winner_label", "result_method", "result_round", "result_time")}
        expected_result["winner_upset_fighter_id"] = next((accepted[f"upset_fighter_{side}_id"]
            for side in (1, 2) if accepted[f"fighter_{side}_name"] == accepted.get("winner_name")), None)
        if frozen != expected_result:
            raise ValueError("Frozen result differs from accepted historical snapshot.")
        reviewed = _reviewed_result(accepted, {**match["cito_result"], "fighters": match["cito_fighters"]}, candidate)
        if reviewed != match.get("reviewed_current_result"):
            raise ValueError("Current amendment differs from reviewed evidence.")
        for uid in candidate["upset_fighter_ids_in_cito_order"]:
            comparisons = 0
            for field in COMMON_STATS:
                values = [row[field] for row in groups[(bid, uid)]]
                actual = None if any(value is None for value in values) else sum(values)
                expected = stats[(bid, uid)][field]
                if actual is None or expected is None:
                    continue
                comparisons += 1
                if actual != expected:
                    raise ValueError(f"Historical round sums differ: {bid}/{uid}/{field}")
            if comparisons < 12:
                raise ValueError("Insufficient observed round sums to verify a fighter.")
    digest = _digest(bridge / "manifest.json")
    existing = {(link.provider, link.provider_fighter_id): link for link in registry.provider_links}
    added = []
    for link in links:
        if ("cito", link["cito_fighter_id"]) not in existing:
            added.append(FighterProviderLink("cito", link["cito_fighter_id"], link["upset_fighter_id"],
                f"Paired historical totals and complete round sums; bridge SHA256 {digest}; "
                f"witness UFCStats bout {link['supporting_bouts'][0]['historical_bout_id']}"))
    extended = FighterRegistry(registry.identities, (*registry.provider_links, *added))
    results = [result_record(match) for match in matches]
    plan = gap_plan(rows, json.loads(paths["inventory"].read_text()),
                    json.loads(paths["collection_progress"].read_text()))
    summary = {"schema_version": 1, "status": "verified historical round subset exported",
               "historical_bouts": len(matches), "historical_round_rows": len(rounds),
               "historical_bouts_without_verified_totals": manifest["historical_bouts_without_verified_totals"],
               "cito_identity_links": len(links), "new_registry_links": len(added),
               "round_rows_with_unavailable_control": sum(r["control_seconds"] is None for r in rounds),
               "result_resolutions": dict(Counter(r["resolution"] for r in results)),
               "result_clocks_requiring_review": sum(
                   bool(r["current_result"] and r["current_result"].get("result_time_requires_review"))
                   for r in results),
               "excluded_staged_round_rows": skipped, "probe_primary_requests": plan["primary_requests"],
               "probe_maximum_requests": plan["maximum_requests_including_fallbacks"],
               "api_calls": 0, "coverage_verified": False, "training_ready": False,
               "input_sha256": hashes, "bridge_manifest_sha256": digest}
    if any(_digest(path) != hashes[key] for key, path in paths.items()) or _digest(bridge / "manifest.json") != digest:
        raise ValueError("Input changed during export.")
    read_bridge(bridge)
    current = [row for row in rows["bout_matches.jsonl"] if row["status"] == "post_snapshot"]
    current_ids = {fighter["fighterId"] for row in current for fighter in row["cito_fighters"]}
    review = {"historical_bouts_without_verified_totals": rows["historical_without_verified_totals.jsonl"],
              "reviewed_or_unresolved_results": [row for row in results if row["resolution"] != "historical_result_verified"],
              "reviewed_alias_matches": [match for match in matches if any(
                  f["fighterId"] in {"5ac923a0-f9b1-4611-b3dc-14fc2d230899", "6fe35b97-d7c3-4ac7-b19a-cceaa43eeb02"}
                  for f in match["cito_fighters"])],
              "current_bouts": current,
              "current_fighters_without_historical_evidence": [proposal for proposal in rows["fighter_link_proposals.jsonl"]
                  if proposal["status"] == "no_historical_evidence" and proposal["cito_fighter_id"] in current_ids]}
    output.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=output.parent, prefix=".upset-historical-rounds-") as temporary:
        folder = Path(temporary) / "export"
        folder.mkdir()
        for name, batch in (("round_stats_identified.jsonl", rounds), ("fighter_link_evidence.jsonl", links),
                            ("bout_results.jsonl", results)):
            _write_verified(folder / name, batch)
        save_fighter_registry(extended, folder / "fighter_registry.json")
        (folder / "gap_probe_plan.json").write_text(json.dumps(plan, indent=2, sort_keys=True) + "\n")
        (folder / "review.json").write_text(json.dumps(review, indent=2, sort_keys=True) + "\n")
        summary["output_sha256"] = {path.name: _digest(path) for path in folder.iterdir()}
        (folder / "manifest.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
        if json.loads((folder / "manifest.json").read_text()) != summary:
            raise ValueError("Manifest read-back differs.")
        folder.rename(output)
    return summary


def reuse_export(output: Path, bridge: Path, historical: Path, registry: Path, root: Path) -> dict:
    """A repeated CLI run reuses an intact export only while every input agrees."""
    manifest = json.loads((output / "manifest.json").read_text())
    expected_files = {"round_stats_identified.jsonl", "fighter_link_evidence.jsonl", "bout_results.jsonl",
                      "fighter_registry.json", "gap_probe_plan.json", "review.json"}
    if manifest.get("schema_version") != 1 or set(manifest["output_sha256"]) != expected_files:
        raise ValueError("Unsupported existing historical-round export.")
    bridge_manifest, _rows = read_bridge(bridge)
    paths = {"historical_fights": historical / "fights_identified.jsonl",
             "historical_stats": historical / "fight_stats_identified.jsonl",
             "fighter_registry": registry, "inventory": root / "inventory/manifest.json",
             "collection_progress": root / "collection_progress.json"}
    hashes = {key: _digest(path) for key, path in paths.items()}
    if (hashes != manifest["input_sha256"] or hashes != bridge_manifest["input_sha256"]
            or bridge_manifest.get("matcher_revision") != 2
            or _digest(bridge / "manifest.json") != manifest["bridge_manifest_sha256"]):
        raise ValueError("Existing export inputs differ; use a new immutable output.")
    if any(_digest(output / name) != digest for name, digest in manifest["output_sha256"].items()):
        raise ValueError("Existing export hash differs.")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("data/raw/cito_archive"))
    parser.add_argument("--historical", type=Path, default=Path("data/processed/kaggle_ufc_1994_2026/identified"))
    parser.add_argument("--registry", type=Path, default=Path("data/mappings/fighter_registry.json"))
    parser.add_argument("--bridge", type=Path, default=Path("data/processed/cito_archive_bridge_v2"))
    parser.add_argument("--output", type=Path, default=Path("data/processed/cito_historical_rounds_v1"))
    args = parser.parse_args()
    try:
        if not args.bridge.exists():
            reconcile_archive(args.root, args.historical, args.registry, args.bridge)
        if args.output.exists():
            result = reuse_export(args.output, args.bridge, args.historical, args.registry, args.root)
            print("Existing export verified; reusing saved files.")
        else:
            result = export_rounds(args.bridge, args.historical, args.registry, args.root, args.output)
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.error(str(error))
    print(json.dumps({k: v for k, v in result.items() if not k.endswith("sha256")}, indent=2))
    print(f"Saved to: {args.output}")


if __name__ == "__main__":
    main()
