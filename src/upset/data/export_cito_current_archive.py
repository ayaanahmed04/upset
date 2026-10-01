"""Normalize cached post-snapshot bouts and stage the verified-identity subset.

No requests, historical rewrites, names-only links or model changes. Every
excluded bout and unknown provider identity remains in the review output.
"""

import argparse
import json
from collections import Counter, defaultdict
from dataclasses import asdict, fields
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory

from upset.data.audit_cito_archive import _name, _rows
from upset.data.collect_cito_archive import _digest
from upset.data.collect_cito_card import BASE_URL
from upset.data.export_cito_archive_rounds import read_bridge
from upset.data.export_cito_card import _bout_signature, _duration, _read_card
from upset.data.identity import load_fighter_registry
from upset.data.models import Fight, FightStats
from upset.data.reconcile_cito_archive import _write_verified
from upset.data.reconcile_cito_gap_probes import reconcile_rounds
from upset.data.stage_current import (
    ACCEPTED_HISTORICAL_FIGHTS_SHA256,
    stage_completed_fights,
)

METHODS = {
    "KO/TKO": "KO/TKO", "SUB": "Submission", "Submission": "Submission",
    "U-DEC": "Decision - Unanimous", "Decision - Unanimous": "Decision - Unanimous",
    "S-DEC": "Decision - Split", "Decision - Split": "Decision - Split",
    "M-DEC": "Decision - Majority", "Decision - Majority": "Decision - Majority",
    "DQ": "Disqualification", "Disqualification": "Disqualification",
    "CNC": "Could Not Continue", "No Contest": "No Contest", "Overturned": "Overturned",
}


def _manifest(folder: Path, hashes: dict) -> dict:
    path = folder / "manifest.json"
    value = json.loads(path.read_text())
    hashes[str(path)] = _digest(path)
    for name, digest in value["output_sha256"].items():
        target = folder / name
        if not target.resolve().is_relative_to(folder.resolve()) or _digest(target) != digest:
            raise ValueError(f"Export hash differs: {folder.name}/{name}")
        hashes[str(target)] = digest
    return value


def normalize_completed_bout(bout: dict, event: dict, totals: list, rounds: list,
                             *, derived_evidence: list | None = None) -> tuple[dict, list, list]:
    """Validate paired measurements and preserve decisive/draw/NC labels."""
    bid = str(bout["id"])
    fighters = bout["fighters"]
    if (bout.get("status") != "completed" or bout.get("isCancelled") is True
            or bout.get("eventSlug") != event["slug"] or bout.get("method") not in METHODS
            or len(fighters) != 2 or len({f.get("fighterName") for f in fighters}) != 2
            or any(not f.get("fighterName") or not f.get("fighterSlug") for f in fighters)):
        raise ValueError("Unreviewed completed-bout participants, event or method.")
    method = METHODS[bout["method"]]
    outcomes = [f.get("outcome") for f in fighters]
    if Counter(outcomes) == Counter(("win", "loss")):
        winner = fighters[outcomes.index("win")]
        if (method in {"No Contest", "Overturned", "Could Not Continue"}
                or bout.get("winnerFighterSlug") not in (None, winner["fighterSlug"])):
            raise ValueError("Decisive winner contradicts source result.")
        winner_name, label = winner["fighterName"], winner["fighterName"]
    elif (outcomes == ["draw", "draw"] and method.startswith("Decision")
          or outcomes == ["no_contest", "no_contest"]
          and method in {"No Contest", "Overturned", "Could Not Continue"}):
        if bout.get("winnerFighterSlug"):
            raise ValueError("Nondecisive result has a source winner.")
        winner_name, label = None, "Draw/NC"
    else:
        raise ValueError("Unresolved or contradictory fighter outcomes.")
    duration = _duration(bout)
    if not totals and not derived_evidence:
        raise ValueError("Missing provider totals without verified derived evidence.")
    normalized_rounds, summed = reconcile_rounds(bout, rounds, expected_rounds=bout["resultRound"],
                                                expected_totals=totals if totals else None)
    if not totals:
        comparison_fields = [k for k in summed[0] if k not in {"fighter_name"}]
        observed = {r["source_fighter_id"]: r for r in derived_evidence}
        if len(observed) != 2 or any(
                any(row[k] != observed.get(row["source_fighter_id"], {}).get(k) for k in comparison_fields)
                for row in summed):
            raise ValueError("Derived totals differ from the verified gap supplement.")
    canonical = asdict(Fight("cito", bid, fighters[0]["fighterName"], fighters[1]["fighterName"],
        source_event_id=event["id"], source_fighter_1_id=fighters[0]["fighterId"],
        source_fighter_2_id=fighters[1]["fighterId"], winner_name=winner_name,
        source_winner_label=label, result_method=method, result_round=bout["resultRound"],
        result_time=bout["resultTime"], weight_class=bout.get("weightClass"), event_date=event["eventDate"],
        source_url=f"{BASE_URL}/events/{event['slug']}/bouts"))
    stat_fields = {f.name for f in fields(FightStats)} - {
        "source", "source_bout_id", "source_fighter_id", "fight_duration_seconds", "source_time_format"}
    stats = []
    for row in summed:
        if row["control_seconds"] is not None and row["control_seconds"] > duration:
            raise ValueError("Control exceeds the observed fight duration.")
        stats.append(asdict(FightStats("cito", bid, row["source_fighter_id"], duration, "5 min rounds",
                                       **{k: row[k] for k in stat_fields})))
    return canonical, stats, normalized_rounds


def export_current(root: Path, bridge: Path, accepted: Path, supplement: Path,
                   historical: Path, output: Path, *, expected_history_sha256=ACCEPTED_HISTORICAL_FIGHTS_SHA256,
                   observed_at: datetime | None = None) -> dict:
    if any(output.resolve().is_relative_to(p.resolve()) for p in (root, bridge, accepted, supplement, historical)):
        raise ValueError("Current output overlaps an input.")
    hashes = {}
    base, gap = _manifest(accepted, hashes), _manifest(supplement, hashes)
    # The supplement links its entire accepted export, historical and probe evidence.
    for path, digest in gap["input_sha256"].items():
        if _digest(Path(path)) != digest:
            raise ValueError("Gap supplement input evidence differs.")
        hashes[path] = digest
    bm, rows = read_bridge(bridge)
    if (_digest(bridge / "manifest.json") != base["bridge_manifest_sha256"]
            or bm["input_sha256"] != base["input_sha256"]):
        raise ValueError("Current bridge differs from accepted export.")
    for name, digest in bm["output_sha256"].items():
        hashes[str(bridge / name)] = digest
    for key, path in (("historical_fights", historical / "fights_identified.jsonl"),
                      ("historical_stats", historical / "fight_stats_identified.jsonl"),
                      ("inventory", root / "inventory/manifest.json"),
                      ("collection_progress", root / "collection_progress.json")):
        if _digest(path) != base["input_sha256"][key]:
            raise ValueError("Current acquisition or historical snapshot differs.")
        hashes[str(path)] = _digest(path)
    if base["input_sha256"]["historical_fights"] != expected_history_sha256:
        raise ValueError("Historical fights differ from accepted snapshot.")
    registry = load_fighter_registry(supplement / "fighter_registry.json")
    links = {r.provider_fighter_id: r.upset_fighter_id for r in registry.provider_links if r.provider == "cito"}
    names = defaultdict(list)
    for identity in registry.identities:
        names[_name(identity.display_name)].append(identity.upset_fighter_id)
    historical_links = defaultdict(list)
    for link in registry.provider_links:
        if link.provider == "ufcstats":
            historical_links[link.upset_fighter_id].append(link.provider_fighter_id)
    derived = defaultdict(list)
    for line in (supplement / "current_totals_derived.jsonl").read_text().splitlines():
        row = json.loads(line)
        if row["provider_fight_totals_present"] is not False:
            raise ValueError("Derived supplement is mislabeled as provider totals.")
        derived[row["source_bout_id"]].append(row)
    current = [r for r in rows["bout_matches.jsonl"] if r["status"] == "post_snapshot"]
    cards = {}
    for event_key in sorted({r["event"] for r in current}):
        day, slug, eid = event_key.split("/")
        folder = root / "cards" / slug
        payloads, component_hashes, card_hash = _read_card(folder)
        if (bm["card_manifest_sha256"].get(event_key) != card_hash
                or any(payloads["event"].get(k) != v for k, v in (("id", eid), ("slug", slug), ("eventDate", day)))):
            raise ValueError("Current raw card differs from bridge.")
        hashes[str(folder / "manifest.json")] = card_hash
        for kind, digest in component_hashes.items():
            hashes[str(folder / f"{kind}.json")] = digest
        listing = _rows(payloads["bouts"], "bouts", "fights", "items", "results")
        if listing is None or len({str(b["id"]) for b in listing}) != len(listing):
            raise ValueError("Invalid current raw card listing.")
        cards[event_key] = (payloads, {str(b["id"]): b for b in listing},
                            json.loads((folder / "manifest.json").read_text()))
    if output.exists():
        previous = json.loads((output / "manifest.json").read_text())
        if previous["input_sha256"] != hashes or any(
                _digest(output / name) != digest for name, digest in previous["output_sha256"].items()):
            raise ValueError("Existing current export differs; use a new immutable output.")
        return previous
    fights, stats, rounds, provenance, review = [], [], [], [], []
    unresolved = {}
    occupied, seen_bids = set(), set()
    linked_bids = set()
    for record in current:
        bid = record["cito_bout_id"]
        payloads, listed, manifest = cards[record["event"]]
        bout = listed[bid]
        if (bid in seen_bids or record["card_manifest_sha256"] != hashes[str(root / "cards" / record["event"].split("/")[1] / "manifest.json")]
                or [{k: f.get(k) for k in ("fighterId", "fighterName", "fighterSlug", "outcome")}
                    for f in bout["fighters"]] != record["cito_fighters"]
                or {k: bout.get(k) for k in ("method", "resultRound", "resultTime")} != record["cito_result"]):
            raise ValueError("Current bout identity or result differs from bridge.")
        seen_bids.add(bid)
        for endpoint in ("event", "stats"):
            embedded = [b for b in payloads[endpoint]["bouts"] if str(b["id"]) == bid]
            if len(embedded) != 1 or _bout_signature(embedded[0]) != _bout_signature(bout):
                raise ValueError("Current result or participants differ between endpoints.")
        total_rows = [r for r in payloads["stats"]["boutStats"] if str(r["boutId"]) == bid]
        round_rows = [r for r in payloads["stats"]["roundStats"] if str(r["boutId"]) == bid]
        if len(total_rows) != record["total_rows"] or len(round_rows) != record["round_rows"]:
            raise ValueError("Current raw stat counts differ from bridge.")
        try:
            fight, paired, observed_rounds = normalize_completed_bout(bout, payloads["event"], total_rows,
                                                                      round_rows, derived_evidence=derived.get(bid))
            pair = (fight["event_date"], *sorted(f["fighterId"] for f in bout["fighters"]))
            if pair in occupied:
                raise ValueError("Duplicate dated provider matchup.")
            occupied.add(pair)
        except (ValueError, KeyError, TypeError) as error:
            review.append({"cito_bout_id": bid, "event": record["event"], "reason": str(error),
                           "card_manifest_sha256": record["card_manifest_sha256"]})
            continue
        fights.append(fight)
        stats.extend(paired)
        evidence = {"source_bout_id": bid, "event": record["event"],
                    "card_manifest_sha256": record["card_manifest_sha256"],
                    "raw_stats_sha256": manifest["sha256"]["stats"],
                    "observed_at_utc": manifest["observed_at_utc"]["stats"],
                    "totals_basis": "provider_totals_reconciled_with_rounds" if total_rows else "derived_from_complete_rounds",
                    "provider_fight_totals_present": bool(total_rows)}
        provenance.append(evidence)
        rounds.extend({**r, **evidence, "upset_fighter_id": links.get(r["source_fighter_id"])} for r in observed_rounds)
        unknown = [f for f in bout["fighters"] if f["fighterId"] not in links]
        if not unknown:
            linked_bids.add(bid)
        for fighter in unknown:
            pid = fighter["fighterId"]
            item = unresolved.setdefault(pid, {"cito_fighter_id": pid, "source_names": set(),
                "source_slugs": set(), "supporting_bouts": [], "name_only_candidates": {}, "profile_observations": []})
            item["source_names"].add(fighter["fighterName"])
            item["source_slugs"].add(fighter["fighterSlug"])
            item["supporting_bouts"].append({"source_bout_id": bid, "event_date": fight["event_date"]})
            for uid in names[_name(fighter["fighterName"])]:
                item["name_only_candidates"][uid] = {"upset_fighter_id": uid,
                    "ufcstats_fighter_ids": sorted(historical_links[uid]), "basis": "name_only_not_accepted"}
            if isinstance(fighter.get("profile"), dict):
                item["profile_observations"].append({"profile": fighter["profile"],
                    "observed_at_utc": manifest["observed_at_utc"]["bouts"], "card_manifest_sha256": record["card_manifest_sha256"]})
    identities = []
    for item in unresolved.values():
        identities.append({**item, "source_names": sorted(item["source_names"]), "source_slugs": sorted(item["source_slugs"]),
                           "name_only_candidates": list(item["name_only_candidates"].values())})
    if not fights:
        raise ValueError("No current bouts normalized; inspect the source records.")
    if any(_digest(Path(path)) != digest for path, digest in hashes.items()):
        raise ValueError("Input changed during current normalization.")
    output.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=output.parent, prefix=".upset-current-archive-") as temporary:
        folder = Path(temporary) / "export"
        folder.mkdir()
        for name, batch in (("fights.jsonl", fights), ("fight_stats.jsonl", stats), ("rounds_staged.jsonl", rounds),
                            ("bout_provenance.jsonl", provenance)):
            _write_verified(folder / name, batch)
        linked = {"fights.jsonl": [r for r in fights if r["source_bout_id"] in linked_bids],
                  "fight_stats.jsonl": [r for r in stats if r["source_bout_id"] in linked_bids]}
        identified = None
        if linked_bids:
            subset = Path(temporary) / "linked"
            subset.mkdir()
            for name, batch in linked.items():
                _write_verified(subset / name, batch)
            identified = stage_completed_fights(subset / "fights.jsonl", subset / "fight_stats.jsonl",
                supplement / "fighter_registry.json", historical / "fights_identified.jsonl", folder / "identified",
                expected_historical_sha256=expected_history_sha256, observed_at=observed_at)
        (folder / "review.json").write_text(json.dumps({"bout_validation_issues": review,
            "unresolved_fighter_identities": identities, "rule": "Name candidates are not accepted identity links."},
            indent=2, sort_keys=True) + "\n")
        summary = {"schema_version": 1, "status": "current archive normalized; verified identities staged",
            "processed_at_utc": (observed_at or datetime.now(UTC)).isoformat(), "current_bouts_examined": len(current),
            "canonical_current_bouts": len(fights), "canonical_fighter_stats": len(stats), "current_round_rows": len(rounds),
            "bout_validation_issues": len(review), "identified_current_bouts": len(linked_bids),
            "bouts_awaiting_identity_review": len(fights) - len(linked_bids), "unresolved_provider_fighters": len(identities),
            "totals_basis": dict(Counter(r["totals_basis"] for r in provenance)),
            "draw_or_no_contest_bouts": sum(r["source_winner_label"] == "Draw/NC" for r in fights),
            "api_calls": 0, "coverage_verified": False, "training_ready": False, "input_sha256": hashes,
            "identified_subset_manifest": identified,
            "output_sha256": {str(p.relative_to(folder)): _digest(p) for p in folder.rglob("*") if p.is_file()}}
        (folder / "manifest.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
        folder.rename(output)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("data/raw/cito_archive"))
    parser.add_argument("--bridge", type=Path, default=Path("data/processed/cito_archive_bridge_v2"))
    parser.add_argument("--accepted", type=Path, default=Path("data/processed/cito_historical_rounds_v1"))
    parser.add_argument("--supplement", type=Path, default=Path("data/processed/cito_gap_reconciliation_v1"))
    parser.add_argument("--historical", type=Path, default=Path("data/processed/kaggle_ufc_1994_2026/identified"))
    parser.add_argument("--output", type=Path, default=Path("data/processed/cito_current_archive_v1"))
    args = parser.parse_args()
    try:
        result = export_current(args.root, args.bridge, args.accepted, args.supplement, args.historical, args.output)
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.error(str(error))
    print(json.dumps({k: v for k, v in result.items() if k not in {"input_sha256", "output_sha256", "identified_subset_manifest"}}, indent=2))
    print(f"Saved to: {args.output}")


if __name__ == "__main__":
    main()
