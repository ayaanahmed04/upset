"""List safe Cito event or bout identifiers for a recent-round smoke test."""

import argparse
import json
import os
import re
from pathlib import Path

from upset.data.probe_cito_rounds import describe_error_payload

_EVENT_SLUG = re.compile(r"[A-Za-z0-9-]{1,100}\Z")


def summarize_listing(payload: object, *, kind: str) -> list[dict]:
    """Expose IDs and dates only; reject unknown provider response layouts."""
    if not isinstance(payload, dict) or payload.get("success") is False:
        raise ValueError("Cito listing is not a successful JSON object.")
    data = payload.get("data")
    if isinstance(data, list):
        items = data
    elif isinstance(data, dict):
        keys = ("events", "items", "results") if kind == "event" else (
            "bouts", "fights", "items", "results"
        )
        candidates = [data[key] for key in keys if isinstance(data.get(key), list)]
        if len(candidates) != 1:
            raise ValueError("Unknown Cito listing data shape.")
        items = candidates[0]
    else:
        raise ValueError("Unknown Cito listing data shape.")

    summary = []
    for item in items[:10]:
        if not isinstance(item, dict):
            raise ValueError("Cito listing contains a non-object item.")
        record = item.get(kind) if isinstance(item.get(kind), dict) else item
        identifier = record.get("id") or record.get(f"{kind}Id")
        entry = {
            "id": str(identifier) if isinstance(identifier, (str, int)) else None,
        }
        if kind == "event":
            entry["slug"] = record.get("slug")
            entry["event_date"] = record.get("eventDate")
            entry["has_stats"] = record.get("hasStats")
        else:
            entry["status"] = record.get("status")
            entry["has_stats"] = record.get("hasStats")
        summary.append(entry)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--event", help="Recent event slug; omit to list events")
    args = parser.parse_args()
    if args.event and not _EVENT_SLUG.fullmatch(args.event):
        parser.error("Event slug may contain only letters, digits, and hyphens.")

    from dotenv import load_dotenv

    load_dotenv(dotenv_path=Path(".env"))
    api_key = os.getenv("CITO_API_KEY")
    if not api_key:
        raise SystemExit("CITO_API_KEY is missing; keep the key out of chat.")
    import requests

    endpoint = (
        f"events/{args.event}/bouts" if args.event else "events/recent"
    )
    url = f"https://api.citoapi.com/api/v1/ufc/{endpoint}"
    response = requests.get(url, headers={"x-api-key": api_key}, timeout=20)
    print(f"HTTP status: {response.status_code}")
    try:
        payload = response.json()
    except ValueError:
        payload = None
    if response.status_code != 200:
        labels = describe_error_payload(payload, secret=api_key)
        print(json.dumps(labels, indent=2))
        raise SystemExit("Cito listing failed; see safe status and error labels.")
    try:
        summary = summarize_listing(payload, kind="bout" if args.event else "event")
    except ValueError as error:
        raise SystemExit(str(error)) from None
    output = json.dumps(summary, indent=2)
    if api_key in output:
        raise SystemExit("Cito listing contains the API key; refusing to print.")
    print(output)


if __name__ == "__main__":
    main()
