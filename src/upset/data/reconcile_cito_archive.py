"""Stage archive rounds and propose historical bout/identity links offline.

Proposals require a unique two-fighter/date match and agreement with both
accepted fighter totals. These files are a review layer, not training input.
"""

import argparse
import json
from collections import Counter, defaultdict
from datetime import date, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

from upset.data.audit_cito_archive import (
    REVIEWED_NAMES,
    _check_card,
    _competition,
    _name,
    _participant,
    _rows,
    _stat_values,
)
from upset.data.collect_cito_archive import _digest
from upset.data.export_cito_card import _read_card
from upset.data.export_prefight import read_identified
from upset.data.identify_historical import IdentifiedFight, IdentifiedFightStats
from upset.data.identity import load_fighter_registry
from upset.data.models import Fight, FightStats
from upset.data.stage_current import ACCEPTED_HISTORICAL_FIGHTS_SHA256

PAIR_NAMES = {
    "significantStrikes": "sig_strikes", "totalStrikes": "total_strikes",
    "takedowns": "takedowns", "head": "head", "body": "body", "leg": "leg",
    "distance": "distance", "clinch": "clinch", "ground": "ground",
}
COMMON_STATS = ("knockdowns", "sig_strikes_landed", "sig_strikes_attempted",
                "takedowns_landed", "takedowns_attempted", "submission_attempts",
                "head_landed", "body_landed", "leg_landed", "distance_landed",
                "clinch_landed", "ground_landed", "control_seconds")


def _numbers(raw: dict) -> dict:
    values = _stat_values(raw)
    result = {}
    for source, target in PAIR_NAMES.items():
        landed, attempted = values[source]
        result[f"{target}_landed"] = landed
        result[f"{target}_attempted"] = attempted
    for source, target in (("knockdowns", "knockdowns"),
                           ("submissionAttempts", "submission_attempts"),
                           ("reversals", "reversals")):
        result[target] = values[source][0]
    control = values["controlTime"]
    result["control_seconds"] = None if control is None else control[0]
    if any(result[f"sig_strikes_{kind}"] > result[f"total_strikes_{kind}"]
           for kind in ("landed", "attempted")):
        raise ValueError("Significant strikes exceed total strikes.")
    for parts in (("head", "body", "leg"), ("distance", "clinch", "ground")):
        for kind in ("landed", "attempted"):
            if sum(result[f"{part}_{kind}"] for part in parts) != result[f"sig_strikes_{kind}"]:
                raise ValueError("Significant-strike breakdown does not reconcile.")
    return result


def _aliases(fighter: dict, person: int, fighters: list, totals: list) -> set[str]:
    profile = fighter.get("profile")
    names = {fighter.get("fighterName"), fighter.get("fighterSlug")}
    if isinstance(profile, dict):
        names.update((profile.get("name"), profile.get("slug")))
    reviewed = REVIEWED_NAMES.get(fighter.get("fighterId"))
    if reviewed and fighter.get("fighterName") == reviewed[0]:
        names.update(reviewed)
    for row in totals:
        if _participant(row, fighters) == person:
            names.update((row.get("fighterName"), row.get("fighterSlug")))
    return {_name(n) for n in names if isinstance(n, str) and _name(n)}


def _method(value):
    return {"U-DEC": "Decision - Unanimous", "S-DEC": "Decision - Split",
            "M-DEC": "Decision - Majority", "SUB": "Submission"}.get(value, value)


def match_bout(event_date: str, bout: dict, totals: list, by_date: dict,
               historical_stats: dict, reviewed_links: dict) -> dict:
    """Return evidence; never accept a names-only link or break candidate ties."""
    fighters = bout.get("fighters")
    if (not isinstance(fighters, list) or len(fighters) != 2
            or any(not isinstance(f, dict) or not isinstance(f.get("fighterId"), str)
                   or not f["fighterId"] for f in fighters)
            or fighters[0]["fighterId"] == fighters[1]["fighterId"]):
        return {"status": "invalid_participants", "candidates": []}
    aliases = [_aliases(f, i, fighters, totals) for i, f in enumerate(fighters)]
    day = date.fromisoformat(event_date)
    candidates = []
    for offset in (-1, 0, 1):
        for history in by_date.get((day + timedelta(days=offset)).isoformat(), []):
            possibilities = []
            for order in ((1, 2), (2, 1)):
                if all(_name(history[f"fighter_{side}_name"]) in aliases[i]
                       for i, side in enumerate(order)):
                    possibilities.append(order)
            if len(possibilities) != 1:
                continue
            order = possibilities[0]
            differences = []
            comparisons = 0
            people = [_participant(row, fighters) for row in totals]
            if len(totals) != 2 or Counter(people) != Counter((0, 1)):
                differences.append({"field": "fighter_totals", "reason": "not_two_unique_fighters"})
            else:
                for i, side in enumerate(order):
                    uid = history[f"upset_fighter_{side}_id"]
                    known = reviewed_links.get(fighters[i]["fighterId"])
                    if known is not None and known != uid:
                        differences.append({"field": "reviewed_identity", "cito_fighter_index": i,
                                            "historical": uid, "reviewed": known})
                    try:
                        numbers = _numbers(totals[people.index(i)])
                        accepted = historical_stats[(history["source_bout_id"], uid)]
                        for field in COMMON_STATS:
                            if numbers[field] is None or accepted[field] is None:
                                continue
                            comparisons += 1
                            if numbers[field] != accepted[field]:
                                differences.append({"field": field, "cito_fighter_index": i,
                                                    "cito": numbers[field],
                                                    "historical": accepted[field]})
                    except (KeyError, TypeError, ValueError) as error:
                        differences.append({"field": "numerical_stats", "reason": str(error)})
            candidates.append({"historical_bout_id": history["source_bout_id"],
                               "historical_event_date": history["event_date"],
                               "date_offset_days": offset,
                               "upset_fighter_ids_in_cito_order": [
                                   history[f"upset_fighter_{side}_id"] for side in order],
                               "ufcstats_fighter_ids_in_cito_order": [
                                   history[f"source_fighter_{side}_id"] for side in order],
                               "compared_stat_fields": comparisons,
                               "stat_differences": differences})
    verified_candidates = [c for c in candidates if not c["stat_differences"]
                           and c["compared_stat_fields"] >= 24]
    alternatives = []
    if len(verified_candidates) == 1:
        alternatives = [c for c in candidates if c is not verified_candidates[0]]
        candidates = verified_candidates
    elif len(candidates) != 1:
        status = "ambiguous_historical_candidates" if candidates else "no_historical_candidate"
        if not candidates and by_date and event_date > (
            date.fromisoformat(max(by_date)) + timedelta(days=1)).isoformat():
            status = "post_snapshot"
        elif not candidates and by_date and event_date < (
            date.fromisoformat(min(by_date)) - timedelta(days=1)).isoformat():
            status = "before_snapshot"
        return {"status": status, "candidates": candidates}
    candidate = candidates[0]
    verified = not candidate["stat_differences"] and candidate["compared_stat_fields"] >= 24
    result = {"status": "totals_verified_proposal" if verified else "candidate_requires_review",
              "candidates": candidates}
    if alternatives:
        result["other_name_date_candidates"] = alternatives
    if verified:
        history = next(h for h in by_date[candidate["historical_event_date"]]
                       if h["source_bout_id"] == candidate["historical_bout_id"])
        winner = history.get("winner_name")
        winner_ids = [history[f"upset_fighter_{side}_id"] for side in (1, 2)
                      if history[f"fighter_{side}_name"] == winner]
        result["accepted_historical_result"] = {key: history.get(key) for key in (
            "winner_name", "source_winner_label", "result_method", "result_round", "result_time")}
        result["accepted_historical_result"]["winner_upset_fighter_id"] = (
            winner_ids[0] if len(winner_ids) == 1 else None)
        result["metadata_differences"] = []
        for raw_key, accepted_key in (("method", "result_method"), ("resultRound", "result_round"),
                                      ("resultTime", "result_time")):
            left, right = bout.get(raw_key), history.get(accepted_key)
            if (_method(left) if raw_key == "method" else left) != (
                _method(right) if raw_key == "method" else right):
                result["metadata_differences"].append({"field": raw_key, "cito": left,
                                                       "historical": right})
        raw_winners = [i for i, f in enumerate(fighters) if f.get("outcome") == "win"]
        raw_winner_uid = (candidate["upset_fighter_ids_in_cito_order"][raw_winners[0]]
                          if len(raw_winners) == 1 else None)
        if raw_winner_uid != result["accepted_historical_result"]["winner_upset_fighter_id"]:
            result["metadata_differences"].append({"field": "winner", "cito": raw_winner_uid,
                                                   "historical": result["accepted_historical_result"][
                                                       "winner_upset_fighter_id"]})
        if bout.get("status") != "completed":
            result["metadata_differences"].append({"field": "status", "cito": bout.get("status"),
                                                   "historical": "completed"})
    return result


def _history(fights_path: Path, stats_path: Path, registry):
    fights = [row.as_record() for row in read_identified(
        fights_path, Fight, IdentifiedFight, ("upset_fighter_1_id", "upset_fighter_2_id"))]
    stats = [row.as_record() for row in read_identified(
        stats_path, FightStats, IdentifiedFightStats, ("upset_fighter_id",))]
    links = {(r.provider, r.provider_fighter_id): r.upset_fighter_id for r in registry.provider_links}
    by_date = defaultdict(list)
    expected = {}
    seen = set()
    for row in fights:
        bid = row["source_bout_id"]
        day = row["event_date"]
        if (row["source"] != "kaggle_ufc_1994_2026" or not bid or bid in seen
                or date.fromisoformat(day).isoformat() != day):
            raise ValueError("Invalid or duplicate historical bout.")
        seen.add(bid)
        if row["upset_fighter_1_id"] == row["upset_fighter_2_id"]:
            raise ValueError("Historical bout repeats one fighter identity.")
        for side in (1, 2):
            uid = row[f"upset_fighter_{side}_id"]
            source_id = row[f"source_fighter_{side}_id"]
            if links.get(("ufcstats", source_id)) != uid:
                raise ValueError("Historical identities differ from registry.")
            expected[(bid, uid)] = source_id
        by_date[day].append(row)
    indexed_stats = {}
    for row in stats:
        key = (row["source_bout_id"], row["upset_fighter_id"])
        if (row["source"] != "kaggle_ufc_1994_2026" or key in indexed_stats
                or row["source_fighter_id"] != expected.get(key)):
            raise ValueError("Historical totals do not identify a unique bout participant.")
        indexed_stats[key] = row
    if not fights or set(indexed_stats) != set(expected):
        raise ValueError("Historical paired totals are incomplete.")
    return fights, by_date, indexed_stats


def _write_verified(path: Path, rows) -> None:
    with path.open("w", encoding="utf-8") as stream:
        for row in rows:
            stream.write(json.dumps(row, sort_keys=True, ensure_ascii=False, allow_nan=False) + "\n")
    restored = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    if restored != rows:
        raise ValueError(f"Export read-back differs: {path.name}")


def reconcile_archive(root: Path, historical: Path, registry_path: Path, output: Path, *,
                      expected_history_sha256: str | None = ACCEPTED_HISTORICAL_FIGHTS_SHA256,
                      log: object = print) -> dict:
    """Stage source rows and evidence with immutable inputs and explicit unresolved cases."""
    if (output.exists() or output.resolve().is_relative_to(root.resolve())
            or output.resolve().is_relative_to(historical.resolve())):
        raise ValueError("Output exists or overlaps an input directory.")
    fights_path = historical / "fights_identified.jsonl"
    stats_path = historical / "fight_stats_identified.jsonl"
    inventory_path = root / "inventory/manifest.json"
    progress_path = root / "collection_progress.json"
    paths = {"historical_fights": fights_path, "historical_stats": stats_path,
             "fighter_registry": registry_path, "inventory": inventory_path,
             "collection_progress": progress_path}
    hashes = {key: _digest(path) for key, path in paths.items()}
    if expected_history_sha256 is not None and hashes["historical_fights"] != expected_history_sha256:
        raise ValueError("Historical fights differ from the accepted snapshot.")
    registry = load_fighter_registry(registry_path)
    history, by_date, accepted_stats = _history(fights_path, stats_path, registry)
    reviewed_links = {r.provider_fighter_id: r.upset_fighter_id for r in registry.provider_links
                      if r.provider == "cito"}
    inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    progress = json.loads(progress_path.read_text(encoding="utf-8"))
    if (inventory.get("status") != "provider inventory captured; UFC coverage unverified"
            or progress.get("inventory_sha256") != hashes["inventory"]):
        raise ValueError("Archive inventory and collection progress differ.")
    bouts, round_rows, review = [], [], []
    proposals = defaultdict(lambda: defaultdict(list))
    source_names = defaultdict(set)
    source_checks = {}
    card_hashes = {}
    parsed_cards = 0
    for event in inventory["events"]:
        if _competition(event["slug"]) != "ufc_candidate":
            continue
        key = f"{event['event_date']}/{event['slug']}/{event['provider_event_id']}"
        saved = progress["cards"].get(key, {})
        if saved.get("status") != "captured":
            continue
        folder = root / "cards" / event["slug"]
        payloads, component_hashes, card_hash = _read_card(folder)
        if card_hash != saved["card_manifest_sha256"]:
            raise ValueError(f"Card differs from acquisition progress: {event['slug']}")
        validation = _check_card(payloads, event)
        card_findings = [finding for finding in validation["findings"] if ":" not in finding]
        if card_findings:
            raise ValueError(f"Card endpoints disagree on {event['slug']}: {card_findings}")
        bout_findings = defaultdict(list)
        for finding in validation["findings"]:
            label, bid = finding.split(":", 1)
            bout_findings[bid].append(label)
        card_hashes[key] = card_hash
        source_checks.update({folder / f"{name}.json": value
                              for name, value in component_hashes.items()})
        source_checks[folder / "manifest.json"] = card_hash
        stats = payloads["stats"]
        listed = _rows(payloads["bouts"], "bouts", "fights", "items", "results")
        if not isinstance(stats, dict) or listed is None:
            raise TypeError(f"Unsupported archive shape: {event['slug']}")
        totals = defaultdict(list)
        rounds = defaultdict(list)
        for target, rows in ((totals, stats.get("boutStats")), (rounds, stats.get("roundStats"))):
            if not isinstance(rows, list):
                raise TypeError("Card has no list of totals or rounds.")
            for row in rows:
                if not isinstance(row, dict):
                    raise TypeError("Invalid source stat row.")
                target[str(row.get("boutId"))].append(row)
        seen_bids = set()
        manifest = json.loads((folder / "manifest.json").read_text())
        for bout in listed:
            if not isinstance(bout, dict) or not isinstance(bout.get("id"), (str, int)):
                raise TypeError("Invalid source bout.")
            bid = str(bout["id"])
            if bid in seen_bids:
                raise ValueError("Duplicate bout on one card.")
            seen_bids.add(bid)
            match = match_bout(event["event_date"], bout, totals[bid], by_date,
                               accepted_stats, reviewed_links)
            record = {"event": key, "cito_bout_id": bid,
                      "cito_fighters": [{k: f.get(k) for k in ("fighterId", "fighterName", "fighterSlug", "outcome")}
                                        for f in bout.get("fighters", []) if isinstance(f, dict)],
                      "cito_status": bout.get("status"), "cito_has_stats": bout.get("hasStats"),
                      "cito_result": {k: bout.get(k) for k in ("method", "resultRound", "resultTime")},
                      "card_manifest_sha256": card_hash,
                      "total_rows": len(totals[bid]), "round_rows": len(rounds[bid]),
                      "source_bout_findings": bout_findings[bid], **match}
            bouts.append(record)
            if match["status"] == "totals_verified_proposal":
                candidate = match["candidates"][0]
                for i, f in enumerate(bout["fighters"]):
                    uid = candidate["upset_fighter_ids_in_cito_order"][i]
                    proposals[f["fighterId"]][uid].append({"event": key, "cito_bout_id": bid,
                        "historical_bout_id": candidate["historical_bout_id"],
                        "ufcstats_fighter_id": candidate["ufcstats_fighter_ids_in_cito_order"][i],
                        "card_manifest_sha256": card_hash})
            if (match["status"] != "totals_verified_proposal" or match.get("metadata_differences")
                    or bout_findings[bid]):
                review.append(record)
            for f in bout.get("fighters", []):
                if isinstance(f, dict) and isinstance(f.get("fighterId"), str):
                    source_names[f["fighterId"]].add(f.get("fighterName"))
            seen_rounds = set()
            seen_round_ids = set()
            for raw in rounds[bid]:
                try:
                    person = _participant(raw, bout.get("fighters", []))
                    number = raw.get("round")
                    if (person is None or type(number) is not int or number < 1
                            or (person, number) in seen_rounds
                            or not isinstance(raw.get("id"), str) or not raw["id"]
                            or raw["id"] in seen_round_ids):
                        raise ValueError("Round has an ambiguous identity, duplicate or invalid number/ID.")
                    seen_rounds.add((person, number))
                    seen_round_ids.add(raw["id"])
                    fighter = bout["fighters"][person]
                    if not isinstance(fighter.get("fighterId"), str) or not fighter["fighterId"]:
                        raise ValueError("Round participant lacks a provider fighter ID.")
                    numbers = _numbers(raw)
                    candidate = match["candidates"][0] if match["status"] == "totals_verified_proposal" else None
                    round_rows.append({"source": "cito", "source_bout_id": bid,
                        "source_event_id": event["provider_event_id"], "provider_event_date": event["event_date"],
                        "source_fighter_id": fighter["fighterId"], "source_fighter_slug": raw.get("fighterSlug"),
                        "source_round_stat_id": raw["id"], "fighter_name": raw.get("fighterName"),
                        "round_number": number, **numbers,
                        "candidate_historical_bout_id": candidate["historical_bout_id"] if candidate else None,
                        "source_bout_findings": bout_findings[bid],
                        "observed_at_utc": manifest["observed_at_utc"]["stats"],
                        "card_manifest_sha256": card_hash})
                except (TypeError, ValueError, KeyError) as error:
                    review.append({"event": key, "cito_bout_id": bid, "status": "round_requires_review",
                                   "source_round_stat_id": raw.get("id"), "reason": str(error)})
        extras = (set(totals) | set(rounds)) - seen_bids
        if extras:
            raise ValueError(f"Stats reference unlisted bouts on {event['slug']}: {sorted(extras)}")
        parsed_cards += 1
        if parsed_cards % 50 == 0:
            log(f"Processed {parsed_cards} cards; staged {len(round_rows)} round rows", flush=True)
    fighter_proposals = []
    for provider_id, names in sorted(source_names.items()):
        candidates = proposals[provider_id]
        fighter_proposals.append({"cito_fighter_id": provider_id, "source_names": sorted(n for n in names if n),
                                 "reviewed_upset_fighter_id": reviewed_links.get(provider_id),
                                 "status": "unique_evidence_proposal" if len(candidates) == 1 else (
                                     "conflicting_evidence" if candidates else "no_historical_evidence"),
                                 "candidates": [{"upset_fighter_id": uid, "supporting_bouts": evidence}
                                                for uid, evidence in sorted(candidates.items())]})
    unique_links = {row["cito_fighter_id"]: row["candidates"][0]["upset_fighter_id"]
                    for row in fighter_proposals if row["status"] == "unique_evidence_proposal"}
    coverage = defaultdict(list)
    for row in bouts:
        if row["status"] == "totals_verified_proposal":
            coverage[row["candidates"][0]["historical_bout_id"]].append(
                {"event": row["event"], "cito_bout_id": row["cito_bout_id"]})
    duplicate_history = {bid for bid, rows in coverage.items() if len(rows) > 1}
    for row in round_rows:
        row["proposed_upset_fighter_id"] = unique_links.get(row["source_fighter_id"])
        row["reviewed_upset_fighter_id"] = reviewed_links.get(row["source_fighter_id"])
        row["duplicate_historical_match"] = row["candidate_historical_bout_id"] in duplicate_history
    unmatched = [row for row in history if row["source_bout_id"] not in coverage]
    summary = {"status": "offline bridge staged; bout and identity proposals require review",
               "schema_version": 1, "captured_cards_processed": parsed_cards,
               "cito_bouts": len(bouts), "staged_round_rows": len(round_rows),
               "bout_match_statuses": dict(Counter(row["status"] for row in bouts)),
               "fighter_proposal_statuses": dict(Counter(row["status"] for row in fighter_proposals)),
               "accepted_historical_bouts": len(history), "historical_bouts_with_verified_totals": len(coverage),
               "historical_bouts_without_verified_totals": len(unmatched),
               "historical_bouts_with_multiple_cito_matches": len(duplicate_history),
               "review_records": len(review), "api_calls": 0,
               "input_sha256": hashes, "card_manifest_sha256": card_hashes,
               "coverage_verified": False, "training_ready": False}
    for path, digest in {**source_checks, **{path: hashes[key] for key, path in paths.items()}}.items():
        if _digest(path) != digest:
            raise ValueError(f"Input changed during reconciliation: {path.name}")
    output.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=output.parent, prefix=".upset-archive-bridge-") as temporary:
        folder = Path(temporary) / "export"
        folder.mkdir()
        batches = {"bout_matches.jsonl": bouts, "bout_review.jsonl": review,
                   "fighter_link_proposals.jsonl": fighter_proposals, "round_stats_staged.jsonl": round_rows,
                   "historical_without_verified_totals.jsonl": unmatched,
                   "duplicate_historical_matches.jsonl": [{"historical_bout_id": bid, "cito_matches": coverage[bid]}
                                                           for bid in sorted(duplicate_history)]}
        for name, rows in batches.items():
            _write_verified(folder / name, rows)
        summary["output_sha256"] = {name: _digest(folder / name) for name in batches}
        (folder / "manifest.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
        if json.loads((folder / "manifest.json").read_text()) != summary:
            raise ValueError("Bridge manifest read-back differs.")
        folder.rename(output)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("data/raw/cito_archive"))
    parser.add_argument("--historical", type=Path,
                        default=Path("data/processed/kaggle_ufc_1994_2026/identified"))
    parser.add_argument("--registry", type=Path, default=Path("data/mappings/fighter_registry.json"))
    parser.add_argument("--output", type=Path, default=Path("data/processed/cito_archive_bridge_v1"))
    args = parser.parse_args()
    try:
        summary = reconcile_archive(args.root, args.historical, args.registry, args.output)
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.error(str(error))
    print(json.dumps({k: v for k, v in summary.items() if not k.endswith("sha256")}, indent=2))
    print(f"Saved to: {args.output}")


if __name__ == "__main__":
    main()
