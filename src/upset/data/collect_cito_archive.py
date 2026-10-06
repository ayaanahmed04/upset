"""Cache a paginated Cito event inventory and resumably collect card responses.

This is raw acquisition, not proof of a complete UFC archive. The provider
inventory and every unavailable or failed card remain visible for review.
"""

import argparse
import hashlib
import json
import os
import time
from collections import Counter
from datetime import UTC, date, datetime
from pathlib import Path
from tempfile import NamedTemporaryFile

from upset.data.collect_cito_card import BASE_URL, collect_card
from upset.data.collect_cito_rounds import RoundDownloadError
from upset.data.probe_cito_recent import _EVENT_SLUG
from upset.data.probe_cito_rounds import describe_error_payload

DEFAULT_ROOT = Path("data/raw/cito_archive")
PAGE_LIMIT = 50
LIST_URL = f"{BASE_URL}/events"


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _atomic_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with NamedTemporaryFile(
            "w", encoding="utf-8", newline="\n", dir=path.parent,
            prefix=".upset-archive-", suffix=".json", delete=False,
        ) as stream:
            temporary = Path(stream.name)
            json.dump(value, stream, sort_keys=True, indent=2, allow_nan=False)
            stream.write("\n")
        if json.loads(temporary.read_text(encoding="utf-8")) != value:
            raise ValueError("Archive JSON read-back differs.")
        temporary.replace(path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _event_rows(payload: object) -> tuple[list[dict], dict]:
    if not isinstance(payload, dict) or payload.get("success") is False:
        raise ValueError("Event listing is not a successful object.")
    data = payload.get("data")
    if isinstance(data, list):
        rows, container = data, payload
    elif isinstance(data, dict):
        found = [data[key] for key in ("events", "items", "results")
                 if isinstance(data.get(key), list)]
        if len(found) != 1:
            raise ValueError("Unknown paginated event-list shape.")
        rows, container = found[0], data
    else:
        raise TypeError("Unknown paginated event-list shape.")
    page = container.get("pagination", payload.get("pagination", {}))
    if not isinstance(page, dict):
        raise TypeError("Unknown pagination metadata.")
    return rows, page


def _pagination_end(rows: list, page: dict, number: int) -> bool:
    """Use explicit pagination when present; otherwise stop on a short page."""
    for key in ("hasNextPage", "hasMore"):
        if key in page:
            if type(page[key]) is not bool:
                raise ValueError("Invalid event pagination flag.")
            return not page[key]
    for key in ("totalPages", "total_pages"):
        if key in page:
            if type(page[key]) is not int or page[key] < number:
                raise ValueError("Invalid event pagination page count.")
            return number == page[key]
    return len(rows) < PAGE_LIMIT


def _entry(item: object) -> dict:
    row = item.get("event", item) if isinstance(item, dict) else None
    if not isinstance(row, dict):
        raise TypeError("Event-list row is not an object.")
    slug, event_day, stats = (row.get("slug"), row.get("eventDate"),
                              row.get("hasStats"))
    if not isinstance(slug, str) or not _EVENT_SLUG.fullmatch(slug):
        raise ValueError("Event-list row has an unsafe or missing slug.")
    try:
        if date.fromisoformat(event_day).isoformat() != event_day:
            raise ValueError("Noncanonical date")
    except (TypeError, ValueError) as error:
        raise ValueError(f"Invalid date for event {slug}.") from error
    if type(stats) is not bool:
        raise ValueError(f"Missing hasStats for event {slug}.")
    provider_id = row.get("id")
    if type(provider_id) not in (str, int) or not str(provider_id):
        raise ValueError(f"Missing ID for event {slug}.")
    return {"slug": slug, "event_date": event_day, "has_stats": stats,
            "provider_event_id": str(provider_id), "status": row.get("status")}


def collect_inventory(root: Path, api_key: str, get: object, *,
                      max_pages: int = 1, delay: float = 7.0,
                      sleep: object = time.sleep) -> dict:
    """Save full raw pages; only mark inventory complete at the final page."""
    if not api_key or max_pages < 1 or delay < 0:
        raise ValueError("API key, positive page cap and valid delay required.")
    completed = root / "inventory" / "manifest.json"
    if completed.exists():
        raise ValueError("Inventory already complete; keep its snapshot immutable.")
    events, seen, hashes = [], set(), {}
    fetched = 0
    for number in range(1, max_pages + 1):
        url = f"{LIST_URL}?page={number}&limit={PAGE_LIMIT}"
        path = root / "inventory" / "pages" / f"page-{number:04d}.json"
        if path.exists():
            saved = json.loads(path.read_text(encoding="utf-8"))
            if (not isinstance(saved, dict) or set(saved) != {
                "source_url", "observed_at_utc", "response"
            } or saved["source_url"] != url):
                raise ValueError(f"Invalid cached inventory page {number}.")
        else:
            if fetched:
                sleep(delay)
            try:
                response = get(url, headers={"x-api-key": api_key}, timeout=30)
                payload = response.json()
            except (OSError, ValueError, TypeError) as error:
                raise RoundDownloadError(
                    f"Event inventory request failed: {type(error).__name__}"
                ) from None
            if response.status_code != 200:
                labels = describe_error_payload(payload, secret=api_key)
                raise RoundDownloadError(
                    f"Inventory HTTP {response.status_code}; "
                    f"error_code={labels['error_code']}"
                )
            rows, _ = _event_rows(payload)
            if len(rows) > PAGE_LIMIT:
                raise ValueError("Event-list page exceeds requested limit.")
            saved = {"source_url": url,
                     "observed_at_utc": datetime.now(UTC).isoformat().replace(
                         "+00:00", "Z"), "response": payload}
            if api_key in json.dumps(saved):
                raise ValueError("Event response contains the API key.")
            _atomic_json(path, saved)
            fetched += 1
        rows, page = _event_rows(saved["response"])
        if len(rows) > PAGE_LIMIT:
            raise ValueError("Cached event-list page exceeds requested limit.")
        for item in rows:
            event = _entry(item)
            key = (event["provider_event_id"], event["slug"], event["event_date"])
            if key in seen:
                raise ValueError(f"Repeated event listing row: {event['slug']}")
            seen.add(key)
            events.append(event)
        hashes[path.name] = _digest(path)
        if _pagination_end(rows, page, number):
            if not events:
                raise ValueError("Completed event inventory is empty.")
            slug_counts = Counter(event["slug"] for event in events)
            report = {
                "status": "provider inventory captured; UFC coverage unverified",
                "source": "cito", "pages": number, "events": sorted(
                    events, key=lambda e: (e["event_date"], e["slug"])),
                "slug_collisions": sorted(slug for slug, count in slug_counts.items()
                                          if count > 1),
                "page_sha256": hashes, "coverage_verified": False,
            }
            _atomic_json(completed, report)
            return {"status": report["status"], "pages": number,
                    "events": len(events), "api_calls": fetched,
                    "inventory_sha256": _digest(completed)}
    return {"status": "partial inventory; resume with a higher --max-pages",
            "pages": max_pages, "events_seen": len(events), "api_calls": fetched}


def collect_archive_cards(root: Path, api_key: str, get: object, *,
                          from_date: str, through_date: str, max_cards: int = 1,
                          retry_failed: bool = False, delay: float = 7.0,
                          sleep: object = time.sleep) -> dict:
    """Collect a bounded batch; persist every skip/failure for later review."""
    if not api_key or max_cards < 1 or delay < 0:
        raise ValueError("API key, positive card cap and valid delay required.")
    start, end = date.fromisoformat(from_date), date.fromisoformat(through_date)
    if start.isoformat() != from_date or end.isoformat() != through_date or start > end:
        raise ValueError("Invalid archive date range.")
    manifest = root / "inventory" / "manifest.json"
    inventory = json.loads(manifest.read_text(encoding="utf-8"))
    if (inventory.get("coverage_verified") is not False
            or inventory.get("status") != "provider inventory captured; UFC coverage unverified"):
        raise ValueError("Incomplete or unexpected inventory manifest.")
    progress_path = root / "collection_progress.json"
    if progress_path.exists():
        progress = json.loads(progress_path.read_text(encoding="utf-8"))
        if progress.get("inventory_sha256") != _digest(manifest):
            raise ValueError("Inventory changed since archive collection began.")
    else:
        progress = {"inventory_sha256": _digest(manifest), "cards": {}}
    attempted = 0
    stats_slug_counts = Counter(row["slug"] for row in inventory["events"]
                                if row["has_stats"] is True)
    for event in sorted(inventory["events"],
                        key=lambda row: (row["event_date"], row["slug"]),
                        reverse=True):
        slug = event["slug"]
        event_key = (f"{event['event_date']}/{slug}/"
                     f"{event['provider_event_id']}")
        if not from_date <= event["event_date"] <= through_date:
            continue
        existing = progress["cards"].get(event_key)
        if existing and (existing["status"] != "failed" or not retry_failed):
            continue
        if event["has_stats"] is False:
            progress["cards"][event_key] = {"status": "provider_has_no_stats"}
            _atomic_json(progress_path, progress)
            continue
        if stats_slug_counts[slug] > 1:
            progress["cards"][event_key] = {"status": "ambiguous_slug"}
            _atomic_json(progress_path, progress)
            continue
        if attempted >= max_cards:
            break
        card_path = root / "cards" / slug
        if (card_path / "manifest.json").exists():
            result = {"status": "captured", "card_manifest_sha256": _digest(
                card_path / "manifest.json")}
        else:
            try:
                report = collect_card(slug, card_path, api_key, get,
                                      delay=delay, sleep=sleep)
                result = {"status": "captured", "card_manifest_sha256": _digest(
                    card_path / "manifest.json"), "api_calls": report["api_calls"]}
            except (OSError, ValueError) as error:
                message = str(error).replace(api_key, "[redacted]")
                result = {"status": "failed", "error": message}
        progress["cards"][event_key] = result
        _atomic_json(progress_path, progress)
        attempted += 1
        if attempted < max_cards:
            sleep(delay)
    return {"attempted_this_run": attempted,
            "captured": sum(row["status"] == "captured"
                            for row in progress["cards"].values()),
            "provider_has_no_stats": sum(row["status"] == "provider_has_no_stats"
                                         for row in progress["cards"].values()),
            "failed": sum(row["status"] == "failed"
                          for row in progress["cards"].values()),
            "ambiguous_slug": sum(row["status"] == "ambiguous_slug"
                                  for row in progress["cards"].values()),
            "progress_path": str(progress_path), "coverage_verified": False}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    inventory = sub.add_parser("inventory", help="List and cache all event pages")
    inventory.add_argument("--max-pages", type=int, default=1)
    cards = sub.add_parser("cards", help="Collect a bounded set of cards")
    cards.add_argument("--from-date", required=True)
    cards.add_argument("--through-date", required=True)
    cards.add_argument("--max-cards", type=int, default=1)
    cards.add_argument("--retry-failed", action="store_true")
    for command in (inventory, cards):
        command.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    args = parser.parse_args()
    from dotenv import load_dotenv

    load_dotenv(dotenv_path=Path(".env"))
    key = os.getenv("CITO_API_KEY")
    if not key:
        parser.error("CITO_API_KEY missing; keep the key out of chat.")
    import requests

    try:
        if args.action == "inventory":
            result = collect_inventory(args.root, key, requests.get,
                                       max_pages=args.max_pages)
        else:
            result = collect_archive_cards(
                args.root, key, requests.get, from_date=args.from_date,
                through_date=args.through_date, max_cards=args.max_cards,
                retry_failed=args.retry_failed,
            )
    except (OSError, ValueError, TypeError) as error:
        parser.error(str(error).replace(key, "[redacted]"))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
