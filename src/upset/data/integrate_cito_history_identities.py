"""Attach three reviewed history-backed identities and restage cached bouts."""

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory

from upset.data.audit_cito_archive import _name
from upset.data.build_research_db import rows
from upset.data.collect_cito_archive import _digest
from upset.data.export_cito_current_archive import METHODS, _manifest
from upset.data.identity import (
    add_reviewed_cito_link,
    load_fighter_registry,
    save_fighter_registry,
)
from upset.data.reconcile_cito_archive import _write_verified
from upset.data.stage_current import (
    ACCEPTED_HISTORICAL_FIGHTS_SHA256,
    stage_completed_fights,
)

# Individually reviewed against the saved fighter histories and frozen bout
# records. This is an allowlist, not a general names-only matching algorithm.
REVIEWED = (
    {"name": "Harry Hardwick", "cito_fighter_id": "12837274-f2e0-441d-b278-1ef8f7d66c8d",
     "ufcstats_fighter_id": "2dbc60c52de126d8", "historical_bout_id": "5cd2dd6075fadcce",
     "cito_bout_id": "5cd2dd6075fadcce", "event_date": "2025-09-06",
     "opponent_cito_id": "fced3984-5dde-4729-a657-f3d611bb0f58"},
    {"name": "Shem Rock", "cito_fighter_id": "b9b9c4ee-b76a-41f8-808d-16b027c3ac96",
     "ufcstats_fighter_id": "52b6bf4528130e86", "historical_bout_id": "46f81d5ecd974c1c",
     "cito_bout_id": "12514", "event_date": "2025-11-22",
     "opponent_cito_id": "df1b3d64-16d7-44c6-b38d-cbb7c379b660"},
    {"name": "Abdul Rakhman Yakhyaev", "cito_fighter_id": "9c434328-43aa-4bcc-aef7-46ed5a1c198a",
     "ufcstats_fighter_id": "95aff2fd8d09a5f0", "historical_bout_id": "f5564a9eeebd4ea0",
     "cito_bout_id": "12465", "event_date": "2025-11-22",
     "opponent_cito_id": "0bc898cb-df18-44a4-aae0-a46345abe82d"},
)


def history_evidence(rule, history, historical, registry):
    """Require known opponent, exact date/result/clock and one reviewed ID."""
    bid = rule["historical_bout_id"]
    frozen = [r for r in historical if r["source_bout_id"] == bid]
    saved = [r for r in history if str(r.get("bout", {}).get("id")) == rule["cito_bout_id"]]
    if len(frozen) != 1 or len(saved) != 1:
        raise ValueError(f"Missing or duplicate reviewed historical evidence: {rule['name']}")
    fight, response = frozen[0], saved[0]
    links = {(r.provider, r.provider_fighter_id): r.upset_fighter_id for r in registry.provider_links}
    slots = [i for i in (1, 2) if fight[f"source_fighter_{i}_id"] == rule["ufcstats_fighter_id"]]
    if len(slots) != 1:
        raise ValueError(f"Reviewed fighter absent from historical bout: {bid}")
    own = slots[0]
    other = 3 - own
    uid = fight[f"upset_fighter_{own}_id"]
    opponent = fight[f"upset_fighter_{other}_id"]
    if (uid == opponent or links.get(("ufcstats", rule["ufcstats_fighter_id"])) != uid
            or links.get(("ufcstats", fight[f"source_fighter_{other}_id"])) != opponent
            or links.get(("cito", rule["opponent_cito_id"])) != opponent):
        raise ValueError(f"Reviewed opponent or historical identity differs: {bid}")
    bout = response["bout"]
    expected_outcome = "win" if fight["winner_name"] == fight[f"fighter_{own}_name"] else "loss"
    if (fight["source_winner_label"] != fight["winner_name"]
            or fight["winner_name"] not in (fight["fighter_1_name"], fight["fighter_2_name"])
            or _name(response["fighterName"]) != _name(rule["name"])
            or _name(fight[f"fighter_{own}_name"]) != _name(rule["name"])
            or _name(response["opponent"]["name"]) != _name(fight[f"fighter_{other}_name"])
            or fight["event_date"] != rule["event_date"]
            or response["event"]["eventDate"] != rule["event_date"]
            or response.get("isCompleted") is not True or bout.get("status") != "completed"
            or bout.get("isCancelled") is True or response.get("outcome") != expected_outcome
            or METHODS.get(bout.get("method")) != fight["result_method"]
            or bout.get("resultRound") != fight["result_round"]
            or bout.get("resultTime") != fight["result_time"]):
        raise ValueError(f"Reviewed historical date, matchup or result differs: {bid}")
    return {**rule, "upset_fighter_id": uid, "opponent_upset_fighter_id": opponent,
            "historical_source_url": fight["source_url"],
            "result_method": fight["result_method"], "result_round": fight["result_round"],
            "result_time": fight["result_time"], "outcome": expected_outcome,
            "basis": "reviewed dated bout, linked opponent, result and clock; no round-stat requirement"}


def integrate(current, review, bundles, historical_path, registry_path, output, *,
              expected_history=ACCEPTED_HISTORICAL_FIGHTS_SHA256, rules=REVIEWED):
    """Publish an immutable registry overlay and expanded identified subset."""
    if any(output.resolve() == p.resolve() or output.resolve().is_relative_to(p.resolve())
           for p in (current, review, bundles, historical_path, registry_path)):
        raise ValueError("Identity integration output overlaps inputs.")
    hashes = {}
    if len({r["cito_fighter_id"] for r in rules}) != len(rules):
        raise ValueError("Duplicate reviewed identity rule.")
    cm = _manifest(current, hashes)
    rm = _manifest(review, hashes)
    for path, digest in rm["input_sha256"].items():
        if _digest(Path(path)) != digest:
            raise ValueError(f"Profile review input hash differs: {path}")
        hashes[path] = digest
    if (rm["identity_links_added"] != 0
            or rm["input_sha256"].get(str(current / "manifest.json")) != _digest(current / "manifest.json")
            or rm["input_sha256"].get(str(registry_path)) != _digest(registry_path)
            or cm["identified_subset_manifest"]["input_sha256"]["registry"] != _digest(registry_path)):
        raise ValueError("Identity integration differs from the reviewed current cohort.")
    if _digest(historical_path) != expected_history:
        raise ValueError("Historical identity evidence differs from accepted snapshot.")
    hashes[str(historical_path)] = expected_history
    if output.exists():
        old = _manifest(output, {})
        if old["input_sha256"] != hashes or old["reviewed_history_rules"] != list(rules):
            raise ValueError("Existing identity integration differs; use a new output.")
        return old
    historical = rows(historical_path)
    registry = load_fighter_registry(registry_path)
    original = registry
    queue = json.loads((current / "review.json").read_text())
    unresolved = {r["cito_fighter_id"]: r for r in queue["unresolved_fighter_identities"]}
    evidence = []
    for rule in rules:
        pid = rule["cito_fighter_id"]
        if pid not in unresolved:
            raise ValueError(f"Reviewed fighter is absent from unresolved queue: {pid}")
        history_path = bundles / "fighters" / pid / "fights.json"
        if rm["input_sha256"].get(str(history_path)) != _digest(history_path):
            raise ValueError(f"Fighter history is absent from validated review: {pid}")
        wrapper = json.loads(history_path.read_text())
        if wrapper["http_status"] != 200 or wrapper["expected_cito_fighter_id"] != pid:
            raise ValueError(f"Fighter history wrapper identity differs: {pid}")
        item = history_evidence(rule, wrapper["response"]["data"], historical, original)
        if item["upset_fighter_id"] not in {c["upset_fighter_id"] for c in unresolved[pid]["name_only_candidates"]}:
            raise ValueError(f"Reviewed historical candidate differs: {pid}")
        item.update(history_sha256=_digest(history_path), historical_sha256=expected_history,
                    observed_at_utc=wrapper["observed_at_utc"], source_url=wrapper["source_url"])
        registry = add_reviewed_cito_link(registry, cito_fighter_id=pid,
            ufcstats_fighter_id=rule["ufcstats_fighter_id"], evidence=json.dumps(item, sort_keys=True))
        evidence.append(item)
    links = {r.provider_fighter_id: r.upset_fighter_id for r in registry.provider_links if r.provider == "cito"}
    fights, stats = rows(current / "fights.jsonl"), rows(current / "fight_stats.jsonl")
    linked = {r["source_bout_id"] for r in fights if all(r[f"source_fighter_{i}_id"] in links for i in (1, 2))}
    previous = {r["source_bout_id"] for r in rows(current / "identified/fights_identified.jsonl")}
    if not previous <= linked:
        raise ValueError("Identity integration lost previously accepted bouts.")
    remaining = [r for pid, r in unresolved.items() if pid not in {e["cito_fighter_id"] for e in evidence}]
    if any(_digest(Path(p)) != h for p, h in hashes.items()):
        raise ValueError("Identity evidence changed during integration.")
    output.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=output.parent, prefix=".upset-history-links-") as temporary:
        folder = Path(temporary) / "export"
        folder.mkdir()
        save_fighter_registry(registry, folder / "fighter_registry.json")
        _write_verified(folder / "identity_link_evidence.jsonl", evidence)
        for name in ("fights.jsonl", "fight_stats.jsonl", "bout_provenance.jsonl"):
            (folder / name).write_bytes((current / name).read_bytes())
        rounds = rows(current / "rounds_staged.jsonl")
        _write_verified(folder / "rounds_staged.jsonl", [dict(r, upset_fighter_id=links.get(r["source_fighter_id"])) for r in rounds])
        (folder / "review.json").write_text(json.dumps({**queue, "unresolved_fighter_identities": remaining}, indent=2, sort_keys=True) + "\n")
        subset = Path(temporary) / "subset"
        subset.mkdir()
        _write_verified(subset / "fights.jsonl", [r for r in fights if r["source_bout_id"] in linked])
        _write_verified(subset / "fight_stats.jsonl", [r for r in stats if r["source_bout_id"] in linked])
        identified = stage_completed_fights(subset / "fights.jsonl", subset / "fight_stats.jsonl",
            folder / "fighter_registry.json", historical_path, folder / "identified",
            expected_historical_sha256=expected_history)
        # Bind durable paths, rather than temporary build directories.
        identified["input_paths"] = {"registry": str(output / "fighter_registry.json"), "historical": str(historical_path)}
        (folder / "identified/manifest.json").write_text(json.dumps(identified, indent=2, sort_keys=True) + "\n")
        summary = {**{k: v for k, v in cm.items() if k not in ("input_sha256", "output_sha256", "identified_subset_manifest")},
                   "status": "reviewed history identities integrated; current bouts restaged",
                   "identity_integrated_at_utc": datetime.now(UTC).isoformat(),
                   "identity_links_added": len(evidence), "newly_identified_bouts": len(linked - previous),
                   "identified_current_bouts": len(linked), "bouts_awaiting_identity_review": len(fights) - len(linked),
                   "unresolved_provider_fighters": len(remaining), "reviewed_history_rules": list(rules),
                   "input_sha256": hashes, "identified_subset_manifest": identified,
                   "api_calls": 0, "coverage_verified": False, "training_ready": False,
                   "output_sha256": {str(p.relative_to(folder)): _digest(p) for p in folder.rglob("*") if p.is_file()}}
        if any(_digest(Path(p)) != h for p, h in hashes.items()):
            raise ValueError("Identity inputs changed during export.")
        (folder / "manifest.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
        folder.rename(output)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--current", type=Path, default=Path("data/processed/cito_current_archive_v1"))
    parser.add_argument("--review", type=Path, default=Path("data/processed/cito_fighter_review_v1"))
    parser.add_argument("--bundles", type=Path, default=Path("data/raw/cito_fighter_bundles_v1"))
    parser.add_argument("--historical", type=Path, default=Path("data/processed/kaggle_ufc_1994_2026/identified/fights_identified.jsonl"))
    parser.add_argument("--registry", type=Path, default=Path("data/processed/cito_gap_reconciliation_v1/fighter_registry.json"))
    parser.add_argument("--output", type=Path, default=Path("data/processed/cito_current_identity_v2"))
    args = parser.parse_args()
    try:
        result = integrate(args.current, args.review, args.bundles, args.historical, args.registry, args.output)
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.error(str(error))
    print(json.dumps({k: result[k] for k in ("status", "identity_links_added", "newly_identified_bouts",
        "identified_current_bouts", "bouts_awaiting_identity_review", "unresolved_provider_fighters", "api_calls", "training_ready")}, indent=2))
    print(f"Saved to: {args.output}")


if __name__ == "__main__":
    main()
