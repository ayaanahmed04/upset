"""Cache stats-endpoint evidence for past UFC listings marked hasStats=false."""

import argparse
import json
import os
import time
from collections import Counter
from datetime import UTC, date, datetime
from pathlib import Path

from upset.data.audit_cito_archive import _competition
from upset.data.collect_cito_archive import _atomic_json, _digest
from upset.data.collect_cito_card import BASE_URL


def _summary(saved: dict, event: dict) -> dict:
    response = saved.get("response")
    data = response.get("data") if isinstance(response, dict) else None
    totals = data.get("boutStats") if isinstance(data, dict) else None
    rounds = data.get("roundStats") if isinstance(data, dict) else None
    embedded = data.get("event") if isinstance(data, dict) else None
    identity = isinstance(embedded, dict) and all(
        str(embedded.get(k)) == event[v] for k, v in (
            ("id", "provider_event_id"), ("slug", "slug"), ("eventDate", "event_date")))
    available = (saved.get("http_status") == 200 and isinstance(response, dict)
                 and response.get("success") is not False and identity
                 and isinstance(totals, list) and bool(totals)
                 and isinstance(rounds, list) and bool(rounds))
    return {"status": "stats_returned" if available else "requires_provider_review",
            "http_status": saved.get("http_status"), "event_identity_matches": identity,
            "total_rows": len(totals) if isinstance(totals, list) else None,
            "round_rows": len(rounds) if isinstance(rounds, list) else None,
            "request_error": saved.get("request_error")}


def probe_statless(root: Path, output: Path, api_key: str, get: object, *,
                   through_date: str, max_events: int = 50, delay: float = 7,
                   sleep: object = time.sleep, log: object = print) -> dict:
    if not api_key or max_events < 1 or delay < 0:
        raise ValueError("API key, positive event cap and valid delay required.")
    cutoff = date.fromisoformat(through_date)
    if cutoff.isoformat() != through_date:
        raise ValueError("Noncanonical cutoff date.")
    manifest = root / "inventory/manifest.json"
    inventory = json.loads(manifest.read_text(encoding="utf-8"))
    if inventory.get("status") != "provider inventory captured; UFC coverage unverified":
        raise ValueError("Completed provider inventory required.")
    digest = _digest(manifest)
    events = inventory["events"]
    collisions = Counter(e["slug"] for e in events)
    targets = sorted((e for e in events if e["has_stats"] is False
                      and e["event_date"] <= through_date
                      and _competition(e["slug"]) == "ufc_candidate"),
                     key=lambda e: (e["event_date"], e["slug"]))
    rows = []
    fetched = 0
    for number, event in enumerate(targets, 1):
        slug = event["slug"]
        key = f"{event['event_date']}/{slug}/{event['provider_event_id']}"
        if collisions[slug] > 1:
            rows.append({"event": key, "status": "ambiguous_slug"})
            continue
        path = output / f"{slug}.json"
        url = f"{BASE_URL}/events/{slug}/stats"
        if path.exists():
            saved = json.loads(path.read_text(encoding="utf-8"))
            if (saved.get("inventory_sha256") != digest or saved.get("event") != key
                    or saved.get("source_url") != url):
                raise ValueError(f"Cached probe differs from request: {slug}")
        else:
            if fetched >= max_events:
                break
            if fetched:
                sleep(delay)
            log(f"[{number}/{len(targets)}] Probing {slug}", flush=True)
            saved = {"source": "cito", "source_url": url, "event": key,
                     "inventory_sha256": digest,
                     "observed_at_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z")}
            try:
                response = get(url, headers={"x-api-key": api_key}, timeout=30)
                saved["http_status"] = response.status_code
                try:
                    saved["response"] = response.json()
                except ValueError:
                    saved["request_error"] = "non_json_response"
            except OSError as error:
                saved["request_error"] = type(error).__name__
            if api_key in json.dumps(saved, ensure_ascii=False):
                raise ValueError("Response contains API key; refusing to save.")
            _atomic_json(path, saved)
            fetched += 1
        summary = _summary(saved, event)
        rows.append({"event": key, **summary, "raw_path": str(path),
                     "raw_sha256": _digest(path)})
        log(f"  {summary['status']}; totals={summary['total_rows']}, "
            f"rounds={summary['round_rows']}", flush=True)
        if saved.get("http_status") in (401, 403, 429):
            log("Stopping after an access or rate-limit response; evidence saved.", flush=True)
            break
    report = {"status": "endpoint availability probe; bout completeness unverified",
              "inventory_sha256": digest, "through_date": through_date,
              "target_events": len(targets), "examined_events": len(rows),
              "remaining_events": len(targets) - len(rows),
              "api_calls_this_run": fetched, "statuses": dict(Counter(
                  row["status"] for row in rows)), "events": rows,
              "coverage_verified": False}
    _atomic_json(output / "report.json", report)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("data/raw/cito_archive"))
    parser.add_argument("--output", type=Path,
                        default=Path("data/raw/cito_archive/statless_probes_v1"))
    parser.add_argument("--through-date", required=True)
    parser.add_argument("--max-events", type=int, default=50)
    args = parser.parse_args()
    from dotenv import load_dotenv

    load_dotenv(dotenv_path=Path(".env"))
    key = os.getenv("CITO_API_KEY")
    if not key:
        raise SystemExit("CITO_API_KEY is missing; keep the key out of chat.")
    import requests

    try:
        report = probe_statless(args.root, args.output, key, requests.get,
                                through_date=args.through_date, max_events=args.max_events)
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.error(str(error))
    print(json.dumps({k: v for k, v in report.items() if k != "events"}, indent=2))
    print(f"Report: {args.output / 'report.json'}")


if __name__ == "__main__":
    main()
