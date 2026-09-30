"""Read-only structural audit of a locally captured Cito archive.

The report names missing or inconsistent rows; it does not certify provider
calendar coverage or turn historical round rows into model features.
"""

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

from upset.data.collect_cito_archive import _digest, _event_rows
from upset.data.export_cito_card import _read_card


def _competition(slug: str) -> str:
    if "dwcs" in slug or "road-to-ufc" in slug or "road-ufc" in slug:
        return "other_competition"
    if "ufc" in slug:
        return "ufc_candidate"
    return "unclassified"


def _rows(data: object, *keys: str) -> list | None:
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        values = [data[key] for key in keys if isinstance(data.get(key), list)]
        if len(values) == 1:
            return values[0]
    return None


def _check_card(payloads: dict, event: dict) -> dict:
    """Check coverage by bout ID and fighter name, preserving source exceptions."""
    details, listing_data, stats = (payloads[k] for k in ("event", "bouts", "stats"))
    findings = []
    slug = event["slug"]
    if not isinstance(details, dict) or not isinstance(stats, dict):
        return {"listed_bouts": 0, "eligible_bouts": 0,
                "structurally_complete_bouts": 0,
                "findings": ["unknown_event_or_stats_shape"], "review_bouts": []}
    if any(details.get(k) != event[v] for k, v in (
        ("id", "provider_event_id"), ("slug", "slug"),
        ("eventDate", "event_date"),
    )):
        findings.append("event_detail_differs_from_inventory")
    embedded_event = stats.get("event")
    if not isinstance(embedded_event, dict) or any(
        embedded_event.get(k) != details.get(k)
        for k in ("id", "slug", "eventDate")
    ):
        findings.append("stats_event_differs_from_detail")
    bouts = _rows(listing_data, "bouts", "fights", "items", "results")
    totals, rounds = stats.get("boutStats"), stats.get("roundStats")
    if (bouts is None or not isinstance(totals, list)
            or not isinstance(rounds, list)):
        return {"listed_bouts": len(bouts) if bouts is not None else 0,
                "eligible_bouts": 0,
                "structurally_complete_bouts": 0,
                "findings": findings + ["unknown_bout_or_stat_shape"],
                "review_bouts": []}
    ids = [str(b.get("id")) for b in bouts if isinstance(b, dict)]
    if len(ids) != len(bouts) or len(set(ids)) != len(ids):
        findings.append("duplicate_or_invalid_listed_bout_id")
    listed = set(ids)
    for label, value in (("event", details.get("bouts")),
                         ("stats", stats.get("bouts"))):
        embedded_ids = ([str(b.get("id")) for b in value if isinstance(b, dict)]
                        if isinstance(value, list) else [])
        if (not isinstance(value, list) or len(embedded_ids) != len(value)
                or Counter(embedded_ids) != Counter(ids)):
            findings.append(f"{label}_embedded_bouts_differ_from_listing")
    total_by_bout = defaultdict(list)
    round_by_bout = defaultdict(list)
    for row in totals:
        if isinstance(row, dict):
            total_by_bout[str(row.get("boutId"))].append(row)
        else:
            findings.append("invalid_fighter_total_row")
    for row in rounds:
        if isinstance(row, dict):
            round_by_bout[str(row.get("boutId"))].append(row)
        else:
            findings.append("invalid_round_row")
    for label, index in (("total", total_by_bout), ("round", round_by_bout)):
        for extra in sorted(set(index) - listed):
            findings.append(f"{label}_references_unlisted_bout:{extra}")
    eligible = complete = 0
    for bout in bouts:
        if not isinstance(bout, dict) or not isinstance(bout.get("id"), (str, int)):
            continue
        bid = str(bout["id"])
        if bout.get("eventSlug") not in (None, slug):
            findings.append(f"bout_event_slug_differs:{bid}")
        # Only completed, stat-bearing bouts should have a full round history.
        if (bout.get("status") != "completed" or bout.get("isCancelled") is True
                or bout.get("hasStats") is not True):
            continue
        eligible += 1
        expected_rounds = bout.get("resultRound")
        names = [f.get("fighterName") for f in bout.get("fighters", [])
                 if isinstance(f, dict)]
        observed_totals = total_by_bout[bid]
        observed_rounds = round_by_bout[bid]
        if (len(names) != 2 or len(set(names)) != 2
                or not all(isinstance(name, str) and name for name in names)):
            findings.append(f"invalid_participants:{bid}")
            continue
        if len(observed_totals) != 2:
            findings.append(f"fighter_total_row_count_differs:{bid}")
            continue
        if Counter(row.get("fighterName") for row in observed_totals) != Counter(names):
            findings.append(f"fighter_names_differ:{bid}")
            continue
        if type(expected_rounds) is not int or expected_rounds < 1:
            findings.append(f"invalid_result_round:{bid}")
            continue
        expected = Counter((name, number) for name in names
                           for number in range(1, expected_rounds + 1))
        actual = Counter((row.get("fighterName"), row.get("round"))
                         for row in observed_rounds)
        if actual != expected:
            findings.append(f"missing_or_duplicate_round_rows:{bid}")
            continue
        complete += 1
    suspect_ids = sorted({finding.split(":", 1)[1] for finding in findings
                          if ":" in finding})
    by_id = {str(b["id"]): b for b in bouts
             if isinstance(b, dict) and "id" in b}
    review_bouts = [{"bout_id": bid, "bout": by_id.get(bid),
                     "fighter_totals": total_by_bout.get(bid, []),
                     "round_rows": round_by_bout.get(bid, [])}
                    for bid in suspect_ids]
    return {"listed_bouts": len(bouts),
            "eligible_bouts": eligible,
            "structurally_complete_bouts": complete, "findings": findings,
            "review_bouts": review_bouts}


def audit_archive(root: Path) -> dict:
    inventory_path = root / "inventory" / "manifest.json"
    inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    progress = json.loads((root / "collection_progress.json").read_text(
        encoding="utf-8"))
    if (inventory.get("status") != "provider inventory captured; UFC coverage unverified"
            or progress.get("inventory_sha256") != _digest(inventory_path)):
        raise ValueError("Archive inventory and progress do not match.")
    labels = {}
    for filename, digest in inventory["page_sha256"].items():
        page_path = root / "inventory" / "pages" / filename
        if _digest(page_path) != digest:
            raise ValueError(f"Inventory page changed: {filename}")
        raw_rows, _ = _event_rows(json.loads(page_path.read_text())["response"])
        for item in raw_rows:
            row = item.get("event", item)
            labels[(str(row["id"]), row["slug"], row["eventDate"])] = {
                "title": row.get("title"), "short_title": row.get("shortTitle"),
            }
    events = inventory["events"]
    statuses = Counter()
    competition_statuses = defaultdict(Counter)
    findings = []
    statless = []
    failed = []
    review_bouts = []
    inventory_events = []
    total_bouts = eligible_bouts = complete_bouts = 0
    support_spot_checks = {}
    for event in events:
        slug = event["slug"]
        key = f"{event['event_date']}/{slug}/{event['provider_event_id']}"
        progress_row = progress["cards"].get(key, {"status": "unvisited"})
        status = progress_row["status"]
        kind = _competition(slug)
        inventory_events.append({**event, **labels.get((event["provider_event_id"],
                                 slug, event["event_date"]), {}),
                                 "competition": kind, "collection_status": status})
        statuses[status] += 1
        competition_statuses[kind][status] += 1
        if status == "provider_has_no_stats":
            statless.append({"event": key, "competition": kind})
        elif status == "failed":
            failed.append({"event": key, "competition": kind,
                           "error": progress_row.get("error")})
        elif status == "captured":
            directory = root / "cards" / slug
            try:
                if (_digest(directory / "manifest.json")
                        != progress_row["card_manifest_sha256"]):
                    raise ValueError("Card manifest hash differs from progress.")
                payloads, _, _ = _read_card(directory)
                result = _check_card(payloads, event)
            except (OSError, ValueError, KeyError, TypeError) as error:
                findings.append({"event": key, "finding": "invalid_raw_card",
                                 "detail": str(error)})
                continue
            total_bouts += result["listed_bouts"]
            eligible_bouts += result["eligible_bouts"]
            complete_bouts += result["structurally_complete_bouts"]
            review_bouts.extend({"event": key,
                                 "card_manifest_sha256": progress_row[
                                     "card_manifest_sha256"], **row}
                                for row in result["review_bouts"])
            if slug in ("ufc-fight-night-march-14-2026",
                        "ufc-fight-night-june-06-2026"):
                expected = 14 if "march-14" in slug else 12
                support_spot_checks[slug] = {
                    "expected_bouts": expected,
                    "listed_bouts": result["listed_bouts"],
                    "structurally_complete_bouts": result[
                        "structurally_complete_bouts"],
                    "structure_matches_support_claim": (
                        result["listed_bouts"] == expected
                        and result["structurally_complete_bouts"] == expected
                    ),
                }
            findings.extend({"event": key, "finding": finding}
                            for finding in result["findings"])
    return {
        "status": "structural audit only; UFC calendar and numerical stats unverified",
        "inventory_sha256": _digest(inventory_path),
        "events_in_provider_inventory": len(events),
        "progress_statuses": dict(sorted(statuses.items())),
        "competition_statuses": {k: dict(sorted(v.items()))
                                 for k, v in sorted(competition_statuses.items())},
        "listed_bouts_in_readable_cards": total_bouts,
        "eligible_completed_stat_bearing_bouts": eligible_bouts,
        "structurally_complete_bouts": complete_bouts,
        "support_spot_checks": support_spot_checks,
        "inventory_events": inventory_events,
        "review_bouts": review_bouts,
        "findings": findings, "provider_statless_events": statless,
        "failed_events": failed, "coverage_verified": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("data/raw/cito_archive"))
    parser.add_argument("--output", type=Path,
                        default=Path("data/processed/cito_archive_audit_v1.json"))
    args = parser.parse_args()
    try:
        report = audit_archive(args.root)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, sort_keys=True, indent=2) + "\n",
                               encoding="utf-8")
        if json.loads(args.output.read_text(encoding="utf-8")) != report:
            raise ValueError("Audit report read-back differs.")
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.error(str(error))
    print(json.dumps({k: report[k] for k in (
        "status", "events_in_provider_inventory", "progress_statuses",
        "competition_statuses", "listed_bouts_in_readable_cards",
        "eligible_completed_stat_bearing_bouts", "structurally_complete_bouts",
        "support_spot_checks", "coverage_verified",
    )}, indent=2))
    print(f"Findings: {len(report['findings'])}; report: {args.output}")


if __name__ == "__main__":
    main()
