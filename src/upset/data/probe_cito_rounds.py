"""Inspect one Cito bout's round-record shape using the local API key."""

import argparse
import json
import os
import re
from pathlib import Path


def describe_round_payload(payload: dict) -> dict:
    """Show data shapes and field names without printing every round record."""
    if not isinstance(payload, dict):
        raise ValueError("Expected a JSON object from Cito.")
    data = payload.get("data")
    report = {
        "response_keys": sorted(payload),
        "data_type": type(data).__name__,
    }
    if isinstance(data, list):
        report["row_count"] = len(data)
        report["first_row_keys"] = (
            sorted(data[0]) if data and isinstance(data[0], dict) else []
        )
    elif isinstance(data, dict):
        report["data_keys"] = sorted(data)
        report["list_fields"] = {
            key: {
                "rows": len(value),
                "first_row_keys": (
                    sorted(value[0]) if value and isinstance(value[0], dict) else []
                ),
            }
            for key, value in data.items()
            if isinstance(value, list)
        }
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--bout-id", default="daef1691c7d6b1e4", help="One known UFC bout ID"
    )
    args = parser.parse_args()
    if not re.fullmatch(r"[0-9a-f]{16}", args.bout_id):
        parser.error("bout ID must be a 16-character lowercase UFCStats ID")

    from dotenv import load_dotenv

    load_dotenv(dotenv_path=Path(".env"))
    key = os.getenv("CITO_API_KEY")
    if not key:
        raise SystemExit("CITO_API_KEY is missing; keep the key out of chat.")

    import requests

    url = f"https://api.citoapi.com/api/v1/ufc/bouts/{args.bout_id}/rounds"
    response = requests.get(url, headers={"x-api-key": key}, timeout=20)
    print(f"HTTP status: {response.status_code}")
    response.raise_for_status()
    print(json.dumps(describe_round_payload(response.json()), indent=2))


if __name__ == "__main__":
    main()
