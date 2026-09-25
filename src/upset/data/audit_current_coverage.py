"""Compare an independent UFC event calendar with source inventory and stages."""

import argparse
import json
from datetime import date
from pathlib import Path

from upset.data.stage_current import (
    ACCEPTED_HISTORICAL_FIGHTS_SHA256,
    LAST_HISTORICAL_DATE,
)
from upset.modeling.evaluation import _sha256, _write_verified_json

CALENDAR_FIELDS = {"event_key", "event_date", "source_url", "observed_at_utc"}
INVENTORY_FIELDS = {
    "event_key", "event_date", "provider", "source_event_id",
    "completed_bout_ids", "source_url", "observed_at_utc",
}


def _date(value):
    try:
        parsed = date.fromisoformat(value)
        if parsed.isoformat() != value:
            raise ValueError("Noncanonical date")
    except (TypeError, ValueError) as error:
        raise ValueError(f"Invalid coverage date: {value!r}") from error
    return parsed


def _read(path, fields):
    values = []
    with path.open(encoding="utf-8") as source:
        for number, line in enumerate(source, 1):
            try:
                row = json.loads(line)
            except ValueError as error:
                raise ValueError(f"Invalid JSON in {path}:{number}") from error
            if not isinstance(row, dict) or set(row) != fields:
                raise ValueError(f"Unexpected coverage fields in {path}:{number}")
            values.append(row)
    if not values:
        raise ValueError(f"Empty coverage input: {path}")
    return values


def _provenance(row, through):
    if not isinstance(row["event_key"], str) or not row["event_key"]:
        raise ValueError("Event key must identify one calendar event.")
    day = _date(row["event_date"])
    if not _date(LAST_HISTORICAL_DATE) < day <= through:
        raise ValueError(f"Calendar event outside coverage window: {row['event_key']}")
    if not isinstance(row["source_url"], str) or not row["source_url"].startswith(
        "https://"
    ):
        raise ValueError(f"Event source URL is required: {row['event_key']}")
    from upset.modeling.prospective_archive import _utc

    observed = _utc(row["observed_at_utc"])
    if observed.date() < day or observed.date() > through:
        raise ValueError(f"Event inventory must be observed after event: {row['event_key']}")


def audit_current_coverage(calendar_path: Path, inventory_path: Path,
                           stages: list[Path], through_date: str, *,
                           expected_historical_sha256: str = (
                               ACCEPTED_HISTORICAL_FIGHTS_SHA256)) -> dict:
    """List omissions without claiming the supplied calendar itself is complete.

    Calendars and provider inventories are separately captured, immutable inputs.
    The audit checks their agreement, not the truth of either external source.
    """
    through = _date(through_date)
    if through <= _date(LAST_HISTORICAL_DATE) or not stages:
        raise ValueError("Need a post-cutoff date and at least one staged batch.")
    calendar_rows = _read(calendar_path, CALENDAR_FIELDS)
    inventory_rows = _read(inventory_path, INVENTORY_FIELDS)
    calendar, inventory, expected_bouts = {}, {}, {}
    for row in calendar_rows:
        _provenance(row, through)
        key = row["event_key"]
        if key in calendar:
            raise ValueError(f"Duplicate calendar event: {key}")
        calendar[key] = row
    for row in inventory_rows:
        _provenance(row, through)
        key, provider, event_id = (
            row["event_key"], row["provider"], row["source_event_id"]
        )
        if key in inventory or (not isinstance(provider, str) or not provider
                                or provider != provider.lower()
                                or not isinstance(event_id, str) or not event_id):
            raise ValueError(f"Duplicate or invalid provider event: {key}")
        bouts = row["completed_bout_ids"]
        if not isinstance(bouts, list) or not bouts or any(
            not isinstance(b, str) or not b for b in bouts
        ) or len(bouts) != len(set(bouts)):
            raise ValueError(f"Invalid completed-bout inventory: {key}")
        for bout in bouts:
            provider_key = provider, bout
            if provider_key in expected_bouts:
                raise ValueError(f"Provider bout repeated across events: {provider_key}")
            expected_bouts[provider_key] = key
        inventory[key] = row
    used_event_ids = [(r["provider"], r["source_event_id"])
                      for r in inventory.values()]
    if len(set(used_event_ids)) != len(used_event_ids):
        raise ValueError("Provider event ID repeated across calendar events.")

    imported, stats = {}, {}
    stage_hashes = {}
    registry_hashes = set()
    stage_observed = []
    for stage in stages:
        if stage.resolve() in stage_hashes:
            raise ValueError(f"Repeated staged batch: {stage}")
        manifest_path = stage / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if (manifest.get("status") != "partial reviewed completed-fight stage; not model input"
                or manifest.get("historical_cutoff") != LAST_HISTORICAL_DATE
                or manifest.get("input_sha256", {}).get("historical")
                != expected_historical_sha256):
            raise ValueError(f"Unrecognized stage or historical snapshot: {stage}")
        expected = manifest.get("output_sha256", {})
        for filename in ("fights_identified.jsonl", "fight_stats_identified.jsonl"):
            if expected.get(filename) != _sha256(stage / filename):
                raise ValueError(f"Changed stage file: {stage / filename}")
        registry_hashes.add(manifest["input_sha256"]["registry"])
        from upset.modeling.prospective_archive import _utc

        observed = _utc(manifest["observed_at_utc"])
        if observed.date() > through:
            raise ValueError(f"Stage acquired after coverage cutoff: {stage}")
        stage_observed.append(manifest["observed_at_utc"])
        stage_hashes[stage.resolve()] = _sha256(manifest_path)
        fight_rows = [json.loads(line) for line in (stage / "fights_identified.jsonl")
                      .read_text(encoding="utf-8").splitlines()]
        stat_rows = [json.loads(line) for line in (stage / "fight_stats_identified.jsonl")
                     .read_text(encoding="utf-8").splitlines()]
        if len(fight_rows) != manifest["fights"] or len(stat_rows) != manifest[
            "fighter_stats"
        ]:
            raise ValueError(f"Stage counts differ: {stage}")
        for row in fight_rows:
            key = row["source"], row["source_bout_id"]
            if key in imported or row["source"] != manifest["provider"] or (
                _date(row["event_date"]) > through
            ):
                raise ValueError(f"Repeated or misdated stage bout: {key}")
            imported[key] = row
        for row in stat_rows:
            key = row["source"], row["source_bout_id"], row["source_fighter_id"]
            if key in stats:
                raise ValueError(f"Repeated staged fighter stats: {key}")
            stats[key] = row
    if len(registry_hashes) != 1:
        raise ValueError("Stage batches use different fighter registry versions.")

    missing_events = sorted(set(calendar) - set(inventory))
    extra_events = sorted(set(inventory) - set(calendar))
    date_mismatches = sorted(k for k in set(calendar) & set(inventory)
                             if calendar[k]["event_date"] != inventory[k]["event_date"])
    missing_bouts = sorted(set(expected_bouts) - set(imported))
    extra_bouts = sorted(set(imported) - set(expected_bouts))
    wrong_events = []
    incomplete_stats = []
    for key, row in imported.items():
        event = inventory.get(expected_bouts.get(key))
        if event and (row["event_date"] != event["event_date"] or
                      row["source_event_id"] != event["source_event_id"]):
            wrong_events.append(key)
        ids = (row["source_fighter_1_id"], row["source_fighter_2_id"])
        if any((key[0], key[1], i) not in stats for i in ids):
            incomplete_stats.append(key)
    unexpected_stats = sorted((provider, bout, fighter) for provider, bout, fighter
                              in stats if (provider, bout) not in imported or
                              fighter not in (imported[provider, bout][
                                  "source_fighter_1_id"], imported[provider, bout][
                                      "source_fighter_2_id"]))
    issues = {
        "calendar_events_missing_from_provider_inventory": missing_events,
        "provider_events_missing_from_calendar": extra_events,
        "event_date_mismatches": date_mismatches,
        "listed_bouts_missing_from_stages": [list(key) for key in missing_bouts],
        "staged_bouts_missing_from_inventory": [list(key) for key in extra_bouts],
        "staged_bouts_with_wrong_event": [list(key) for key in sorted(wrong_events)],
        "staged_bouts_missing_stats": [list(key) for key in sorted(incomplete_stats)],
        "unexpected_staged_stats": [list(key) for key in unexpected_stats],
    }
    return {
        "status": "matched supplied inventories; external completeness still requires review"
        if not any(issues.values()) else "incomplete supplied current data",
        "historical_cutoff": LAST_HISTORICAL_DATE,
        "through_date": through_date,
        "calendar_events": len(calendar),
        "provider_events": len(inventory),
        "provider_completed_bouts": len(expected_bouts),
        "staged_bouts": len(imported),
        "staged_fighter_stats": len(stats),
        "registry_sha256": next(iter(registry_hashes)),
        "stage_observed_at_utc": stage_observed,
        "input_sha256": {
            "independent_calendar": _sha256(calendar_path),
            "provider_inventory": _sha256(inventory_path),
            "stage_manifests": {str(path): value for path, value in stage_hashes.items()},
        },
        "issues": issues,
        "prospective_ready": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--calendar", type=Path, required=True)
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--stage", type=Path, action="append", required=True)
    parser.add_argument("--through-date", required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        report = audit_current_coverage(args.calendar, args.inventory,
                                        args.stage, args.through_date)
        if args.output:
            if args.output.exists():
                raise ValueError("Coverage report already exists.")
            _write_verified_json(args.output, report, json_lines=False)
    except (ValueError, OSError, KeyError) as error:
        parser.error(str(error))
    print(json.dumps(report, indent=2, sort_keys=True))
    if any(report["issues"].values()):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
