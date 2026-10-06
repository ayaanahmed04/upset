"""Finish raw card captures using verified stats responses from statless probes."""

import argparse
import json
import os
import time
from pathlib import Path

from upset.data.audit_cito_archive import _competition
from upset.data.collect_cito_archive import _atomic_json, _digest
from upset.data.collect_cito_card import BASE_URL, _read_saved, _save, collect_card
from upset.data.export_cito_card import _read_card
from upset.data.probe_cito_recent import _EVENT_SLUG
from upset.data.probe_cito_statless import _summary


def recover_cards(root: Path, probes: Path, api_key: str, get: object, *,
                  max_cards: int = 50, delay: float = 7,
                  sleep: object = time.sleep, log: object = print) -> dict:
    if not api_key or max_cards < 1 or delay < 0:
        raise ValueError("API key, positive card cap and valid delay required.")
    manifest = root / "inventory/manifest.json"
    inventory = json.loads(manifest.read_text(encoding="utf-8"))
    progress_path = root / "collection_progress.json"
    progress = json.loads(progress_path.read_text(encoding="utf-8"))
    report = json.loads((probes / "report.json").read_text(encoding="utf-8"))
    digest = _digest(manifest)
    if (inventory.get("status") != "provider inventory captured; UFC coverage unverified"
            or progress.get("inventory_sha256") != digest
            or report.get("inventory_sha256") != digest):
        raise ValueError("Inventory, collection progress and probe evidence differ.")
    events = {f"{e['event_date']}/{e['slug']}/{e['provider_event_id']}": e
              for e in inventory["events"]}
    targets = []
    seen = set()
    # Validate all selected evidence before making requests or editing progress.
    for row in report["events"]:
        if row["status"] != "stats_returned":
            continue
        key = row["event"]
        event = events.get(key)
        if (event is None or key in seen or event["has_stats"] is not False
                or _competition(event["slug"]) != "ufc_candidate"
                or not _EVENT_SLUG.fullmatch(event["slug"])):
            raise ValueError("Probe does not identify a unique statless UFC listing.")
        seen.add(key)
        path = probes / f"{event['slug']}.json"
        if _digest(path) != row["raw_sha256"]:
            raise ValueError(f"Probe changed: {event['slug']}")
        saved = json.loads(path.read_text(encoding="utf-8"))
        if (saved.get("inventory_sha256") != digest or saved.get("event") != key
                or saved.get("source_url") != f"{BASE_URL}/events/{event['slug']}/stats"
                or not isinstance(saved.get("observed_at_utc"), str)
                or _summary(saved, event)["status"] != "stats_returned"):
            raise ValueError(f"Invalid stats probe evidence: {event['slug']}")
        targets.append((key, event, row, saved))
    attempted = recovered = api_calls = 0
    failures = []

    def tracked_get(*args, **kwargs):
        nonlocal api_calls
        api_calls += 1
        return get(*args, **kwargs)

    for number, (key, event, row, saved) in enumerate(targets, 1):
        slug = event["slug"]
        existing = progress["cards"].get(key, {})
        if existing.get("status") == "captured":
            continue
        if attempted >= max_cards:
            break
        directory = root / "cards" / slug
        log(f"[{number}/{len(targets)}] Recovering {slug}; reusing saved stats", flush=True)
        before = api_calls
        try:
            wrapped = {"source": "cito", "event_slug": slug,
                       "source_url": saved["source_url"],
                       "observed_at_utc": saved["observed_at_utc"],
                       "response": saved["response"]}
            stat_path = directory / "stats.json"
            if stat_path.exists():
                if _read_saved(stat_path, "stats", slug)[0] != wrapped:
                    raise ValueError("Existing stats differ from the verified probe.")
            else:
                _save(stat_path, wrapped, "stats", slug, api_key)
            if not (directory / "manifest.json").exists():
                if api_calls:
                    sleep(delay)
                collect_card(slug, directory, api_key, tracked_get, delay=delay, sleep=sleep)
            payloads, _, card_digest = _read_card(directory)
            details = payloads["event"]
            if not isinstance(details, dict) or any(
                str(details.get(k)) != event[v] for k, v in (
                    ("id", "provider_event_id"), ("slug", "slug"), ("eventDate", "event_date"))
            ):
                raise ValueError("Captured event detail differs from inventory.")
            result = {"status": "captured", "card_manifest_sha256": card_digest,
                      "api_calls": api_calls - before,
                      "stats_probe_sha256": row["raw_sha256"],
                      "provider_inventory_has_stats": False}
            recovered += 1
        except (OSError, ValueError, KeyError, TypeError) as error:
            result = {"status": "failed", "error": str(error).replace(api_key, "[redacted]"),
                      "stats_probe_sha256": row["raw_sha256"], "api_calls": api_calls - before}
            failures.append({"event": key, "error": result["error"]})
        progress["cards"][key] = result
        _atomic_json(progress_path, progress)
        attempted += 1
        log(f"  {result['status']}; new requests={api_calls - before}", flush=True)
    return {"status": "raw card recovery; coverage remains unverified",
            "target_cards": len(targets), "attempted_this_run": attempted,
            "recovered_this_run": recovered, "api_calls_this_run": api_calls,
            "captured_archive_cards": sum(r["status"] == "captured"
                                          for r in progress["cards"].values()),
            "remaining_target_cards": sum(progress["cards"].get(key, {}).get("status")
                                          != "captured" for key, *_ in targets),
            "failures_this_run": failures, "coverage_verified": False}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("data/raw/cito_archive"))
    parser.add_argument("--probes", type=Path,
                        default=Path("data/raw/cito_archive/statless_probes_v1"))
    parser.add_argument("--max-cards", type=int, default=50)
    args = parser.parse_args()
    from dotenv import load_dotenv

    load_dotenv(dotenv_path=Path(".env"))
    key = os.getenv("CITO_API_KEY")
    if not key:
        raise SystemExit("CITO_API_KEY is missing; keep the key out of chat.")
    import requests

    try:
        report = recover_cards(args.root, args.probes, key, requests.get, max_cards=args.max_cards)
        _atomic_json(args.root / "statless_recovery_report.json", report)
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.error(str(error))
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
