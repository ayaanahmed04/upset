"""Save verified Cito round responses locally, one source bout per file."""

import argparse
import json
import os
import re
import time
from pathlib import Path
from tempfile import NamedTemporaryFile

from upset.data.export_prefight import read_identified
from upset.data.identify_historical import IdentifiedFight
from upset.data.models import Fight
from upset.data.probe_cito_rounds import describe_error_payload

SOURCE = "cito"
DEFAULT_OUTPUT = Path("data/raw/cito_rounds")
_BOUT_ID = re.compile(r"[A-Za-z0-9-]{1,64}\Z")


class RoundDownloadError(ValueError):
    """An API request or response failed without exposing response contents."""


def validate_bout_ids(bout_ids: list[str]) -> list[str]:
    """Reject unsafe IDs and duplicates before any request is made."""
    if not bout_ids or len(bout_ids) != len(set(bout_ids)):
        raise ValueError("Bout IDs must be nonempty and unique.")
    if any(
        not isinstance(bout_id, str) or not _BOUT_ID.fullmatch(bout_id)
        for bout_id in bout_ids
    ):
        raise ValueError("Bout IDs must contain only letters, digits, and hyphens.")
    return bout_ids


def read_bout_ids(path: Path) -> list[str]:
    """Read one ID per line; blank lines are ignored."""
    ids = [
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    return validate_bout_ids(ids)


def round_row_count(payload: object) -> int:
    """Reject unknown or empty data rather than caching it as complete."""
    if not isinstance(payload, dict) or payload.get("success") is False:
        raise RoundDownloadError("Cito response is not a successful JSON object.")
    data = payload.get("data")
    if isinstance(data, list):
        rows = data
    elif isinstance(data, dict):
        lists = [
            data[key]
            for key in ("rounds", "rows", "items", "results", "stats")
            if isinstance(data.get(key), list)
        ]
        if len(lists) != 1:
            raise RoundDownloadError("Cito round response has an unknown data shape.")
        rows = lists[0]
    else:
        raise RoundDownloadError("Cito round response has an unknown data shape.")
    if not rows or any(not isinstance(row, dict) for row in rows):
        raise RoundDownloadError("Cito round response has no valid rows.")
    return len(rows)


def validate_row_bout_ids(payload: dict, bout_id: str) -> None:
    """Reject rows with a provider bout ID that contradicts the request."""
    data = payload["data"]
    if isinstance(data, list):
        rows = data
    else:
        rows = next(
            data[key]
            for key in ("rounds", "rows", "items", "results", "stats")
            if isinstance(data.get(key), list)
        )
    if any("boutId" in row and str(row["boutId"]) != bout_id for row in rows):
        raise RoundDownloadError("Cito round row references a different bout ID.")


def _read_saved(path: Path, bout_id: str) -> int:
    try:
        saved = json.loads(path.read_text(encoding="utf-8"))
        if (
            not isinstance(saved, dict)
            or saved.get("source") != SOURCE
            or saved.get("source_bout_id") != bout_id
        ):
            raise RoundDownloadError("Saved source or bout ID does not match.")
        count = round_row_count(saved.get("response"))
        validate_row_bout_ids(saved["response"], bout_id)
        return count
    except (UnicodeError, ValueError) as error:
        raise RoundDownloadError(
            f"Existing round file is invalid: {path.name}"
        ) from error


def collect_one(
    bout_id: str, output_dir: Path, api_key: str, get: object
) -> tuple[int, bool]:
    """Return (round row count, fetched); existing verified files cost no API calls."""
    validate_bout_ids([bout_id])
    if not api_key:
        raise ValueError("Cito API key is required.")
    path = output_dir / f"{bout_id}.json"
    if path.exists():
        return _read_saved(path, bout_id), False

    url = f"https://api.citoapi.com/api/v1/ufc/bouts/{bout_id}/rounds"
    response = get(url, headers={"x-api-key": api_key}, timeout=20)
    try:
        payload = response.json()
    except ValueError as error:
        raise RoundDownloadError(
            f"Cito returned non-JSON HTTP {response.status_code}."
        ) from error
    if response.status_code != 200:
        labels = describe_error_payload(payload, secret=api_key)
        raise RoundDownloadError(
            f"Cito HTTP {response.status_code}; "
            f"error_type={labels['error_type']}; error_code={labels['error_code']}"
        )
    row_count = round_row_count(payload)
    validate_row_bout_ids(payload, bout_id)
    document = {"source": SOURCE, "source_bout_id": bout_id, "response": payload}
    encoded = json.dumps(
        document, ensure_ascii=False, allow_nan=False, sort_keys=True
    )
    if api_key in encoded:
        raise RoundDownloadError(
            "Cito response contains the API key; refusing to save."
        )
    output_dir.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with NamedTemporaryFile(
            mode="w", encoding="utf-8", newline="\n", dir=output_dir,
            prefix=".upset-cito-rounds-", suffix=".json", delete=False,
        ) as saved:
            temporary = Path(saved.name)
            saved.write(encoded + "\n")
        if _read_saved(temporary, bout_id) != row_count:
            raise RoundDownloadError("Round file read-back count differs from source.")
        temporary.replace(path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return row_count, True


def collect_bouts(
    bout_ids: list[str], output_dir: Path, api_key: str, get: object,
    *, limit: int = 1, delay: float = 7.0, sleep: object = time.sleep,
) -> dict:
    """Process in order; stop safely on errors and cap new requests per run."""
    validate_bout_ids(bout_ids)
    if limit < 1 or delay < 0:
        raise ValueError("Request limit must be positive and delay nonnegative.")
    fetched = skipped = rows = 0
    for bout_id in bout_ids:
        path = output_dir / f"{bout_id}.json"
        if path.exists():
            rows += _read_saved(path, bout_id)
            skipped += 1
            continue
        if fetched >= limit:
            break
        if fetched:
            sleep(delay)
        count, _ = collect_one(bout_id, output_dir, api_key, get)
        rows += count
        fetched += 1
    return {"fetched": fetched, "cached": skipped, "round_rows": rows}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    inputs = parser.add_mutually_exclusive_group(required=True)
    inputs.add_argument("--bout-id", action="append", help="Repeat for multiple bouts")
    inputs.add_argument("--bout-ids-file", type=Path, help="One Cito bout ID per line")
    inputs.add_argument("--identified-fights", type=Path, help="Identified fight JSONL")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--limit", type=int, default=1, help="Max new requests (default: 1)"
    )
    parser.add_argument(
        "--delay", type=float, default=7.0, help="Seconds between calls"
    )
    args = parser.parse_args()
    if args.bout_id:
        bout_ids = validate_bout_ids(args.bout_id)
    elif args.bout_ids_file:
        bout_ids = read_bout_ids(args.bout_ids_file)
    else:
        fights = read_identified(
            args.identified_fights, Fight, IdentifiedFight,
            ("upset_fighter_1_id", "upset_fighter_2_id"),
        )
        bout_ids = validate_bout_ids([fight.fight.source_bout_id for fight in fights])

    from dotenv import load_dotenv

    load_dotenv(dotenv_path=Path(".env"))
    api_key = os.getenv("CITO_API_KEY")
    if not api_key:
        raise SystemExit("CITO_API_KEY is missing; keep the key out of chat.")
    import requests

    try:
        report = collect_bouts(
            bout_ids, args.output_dir, api_key, requests.get,
            limit=args.limit, delay=args.delay,
        )
    except RoundDownloadError as error:
        raise SystemExit(str(error)) from None
    print(json.dumps(report, indent=2))
    print(f"Saved under: {args.output_dir}")


if __name__ == "__main__":
    main()
