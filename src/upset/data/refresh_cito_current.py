"""Capture a new dated inventory and later UFC cards without changing the archive."""

import argparse
import json
import os
import time
from collections import Counter
from datetime import UTC, date, datetime
from pathlib import Path

from upset.data.audit_cito_archive import _competition
from upset.data.collect_cito_archive import (
    _atomic_json,
    _digest,
    _entry,
    _event_rows,
    collect_inventory,
)
from upset.data.collect_cito_card import collect_card
from upset.data.export_cito_card import _read_card


def inventory_evidence(root):
    """Verify cached pages and their entries against the completed inventory."""
    path = root / "inventory/manifest.json"
    inventory = json.loads(path.read_text())
    hashes = {str(path): _digest(path)}
    entries = []
    for name, digest in inventory["page_sha256"].items():
        page = root / "inventory/pages" / name
        if not page.resolve().is_relative_to((root / "inventory/pages").resolve()) or _digest(page) != digest:
            raise ValueError("Fresh inventory page hash differs.")
        hashes[str(page)] = digest
        wrapper = json.loads(page.read_text())
        items, _ = _event_rows(wrapper["response"])
        entries.extend(_entry(item) for item in items)
    if (not entries or sorted(entries, key=lambda r: (r["event_date"], r["slug"])) != inventory["events"]
            or len(inventory["page_sha256"]) != inventory["pages"]
            or inventory["coverage_verified"] is not False):
        raise ValueError("Fresh inventory entries differ from saved pages.")
    return inventory, hashes


def refresh(root, api_key, get, *, from_date, through_date, max_pages=50,
            max_cards=20, retry_failed=False, delay=7.0, sleep=time.sleep,
            log=print, today=None):
    """Resume only this snapshot; false hasStats flags never suppress a UFC card."""
    start, end = date.fromisoformat(from_date), date.fromisoformat(through_date)
    if (not api_key or max_pages < 1 or max_cards < 1 or delay < 0
            or start > end or end > (today or datetime.now(UTC).date())
            or start.isoformat() != from_date or end.isoformat() != through_date):
        raise ValueError("Require a valid past date range, key and positive limits.")
    calls_this_run = 0
    original_get = get

    def get(url, **kwargs):
        nonlocal calls_this_run
        calls_this_run += 1
        return original_get(url, **kwargs)
    request_path = root / "refresh_request.json"
    request = {"schema_version": 1, "from_date": from_date, "through_date": through_date,
               "rule": "New inventory; inspect every UFC candidate regardless of hasStats."}
    if request_path.exists():
        if json.loads(request_path.read_text()) != request:
            raise ValueError("Refresh range differs; use a new snapshot root.")
    else:
        if root.exists() and any(root.iterdir()):
            raise ValueError("Refresh root is occupied; keep the existing archive immutable.")
        _atomic_json(request_path, request)
    inventory_path = root / "inventory/manifest.json"
    inventory_calls = 0
    if not inventory_path.exists():
        log("Capturing fresh inventory; saved pages will be reused on resume.")

        def logged_get(url, **kwargs):
            log(f"Inventory request: {url.rsplit('?', 1)[-1]}")
            return get(url, **kwargs)

        result = collect_inventory(root, api_key, logged_get, max_pages=max_pages, delay=delay, sleep=sleep)
        inventory_calls = result["api_calls"]
        if not inventory_path.exists():
            raise ValueError("Fresh inventory is partial; resume with a higher --max-pages.")
    inventory, hashes = inventory_evidence(root)
    hashes[str(request_path)] = _digest(request_path)
    events = [r for r in inventory["events"] if from_date <= r["event_date"] <= through_date]
    targets = [r for r in events if _competition(r["slug"]) == "ufc_candidate"]
    progress_path = root / "refresh_progress.json"
    if progress_path.exists():
        progress = json.loads(progress_path.read_text())
        if progress["input_sha256"] != hashes:
            raise ValueError("Refresh acquisition inputs changed.")
    else:
        progress = {"input_sha256": hashes, "cards": {}}
    slugs = Counter(r["slug"] for r in inventory["events"])
    attempted = calls = 0
    for number, event in enumerate(targets, 1):
        slug = event["slug"]
        key = f"{event['event_date']}/{slug}/{event['provider_event_id']}"
        previous = progress["cards"].get(key)
        if previous and previous["status"] == "captured":
            _, _, digest = _read_card(root / "cards" / slug)
            if digest != previous["card_manifest_sha256"]:
                raise ValueError("Previously captured refresh card changed.")
            continue
        if previous and not retry_failed:
            continue
        if attempted >= max_cards:
            break
        if slugs[slug] != 1:
            progress["cards"][key] = {"status": "ambiguous_slug"}
            _atomic_json(progress_path, progress)
            continue
        if attempted or inventory_calls:
            sleep(delay)
        log(f"[{number}/{len(targets)}] Capturing {slug}; listed hasStats={event['has_stats']}")
        folder = root / "cards" / slug
        try:
            if not (folder / "manifest.json").exists():
                captured = collect_card(slug, folder, api_key, get, delay=delay, sleep=sleep)
                calls += captured["api_calls"]
            payloads, _, digest = _read_card(folder)
            if any(str(payloads["event"].get(k)) != v for k, v in (
                    ("slug", slug), ("eventDate", event["event_date"]), ("id", event["provider_event_id"]))):
                raise ValueError("Fresh card event ID, date or slug differs from inventory.")
            result = {"status": "captured", "card_manifest_sha256": digest}
        except (OSError, ValueError, KeyError, TypeError) as error:
            result = {"status": "failed", "error": str(error).replace(api_key, "[redacted]")}
        progress["cards"][key] = result
        _atomic_json(progress_path, progress)
        attempted += 1
        log(f"  {result['status']}")
    _atomic_json(progress_path, progress)
    target_keys = {f"{r['event_date']}/{r['slug']}/{r['provider_event_id']}" for r in targets}
    if set(progress["cards"]) - target_keys:
        raise ValueError("Refresh progress contains an event outside the bound range.")
    report = {"schema_version": 1, "status": "fresh source snapshot; normalization required",
              "from_date": from_date, "through_date": through_date,
              "target_cards": len(targets), "attempted_this_run": attempted,
              "remaining_cards": len(target_keys - set(progress["cards"])),
              "statuses": dict(Counter(r["status"] for r in progress["cards"].values())),
              "excluded_listing_events": [dict(r, competition=_competition(r["slug"])) for r in events
                                          if _competition(r["slug"]) != "ufc_candidate"],
              "successful_requests_this_run": inventory_calls + calls,
              "api_calls_this_run": calls_this_run,
              "input_sha256": {**hashes, str(progress_path): _digest(progress_path)},
              "coverage_verified": False, "training_ready": False}
    report_path = root / "refresh_report.json"
    # Preserve the acquisition binding after an unchanged resume. Per-run
    # counters are returned/printed, but must not invalidate an existing export.
    previous = json.loads(report_path.read_text()) if report_path.exists() else None
    if previous is None or any(previous.get(key) != report[key] for key in (
            "input_sha256", "from_date", "through_date", "target_cards",
            "remaining_cards", "statuses", "excluded_listing_events")):
        _atomic_json(report_path, report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--from-date", required=True)
    parser.add_argument("--through-date", required=True)
    parser.add_argument("--max-pages", type=int, default=50)
    parser.add_argument("--max-cards", type=int, default=20)
    parser.add_argument("--retry-failed", action="store_true")
    args = parser.parse_args()
    import requests
    from dotenv import load_dotenv
    load_dotenv()
    calls = 0

    def get(url, **kwargs):
        nonlocal calls
        calls += 1
        return requests.get(url, **kwargs)

    try:
        result = refresh(args.root, os.environ.get("CITO_API_KEY", ""), get,
                         from_date=args.from_date, through_date=args.through_date,
                         max_pages=args.max_pages, max_cards=args.max_cards, retry_failed=args.retry_failed,
                         log=lambda message: print(message, flush=True))
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.error(str(error))
    print(json.dumps({k: v for k, v in result.items() if k != "input_sha256"} | {"api_calls_this_run": calls}, indent=2))


if __name__ == "__main__":
    main()
