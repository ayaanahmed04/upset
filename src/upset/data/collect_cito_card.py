"""Cache one recent Cito event card without claiming its statistics are complete."""

import argparse
import hashlib
import json
import os
import time
from datetime import UTC, datetime
from pathlib import Path
from tempfile import NamedTemporaryFile

from upset.data.collect_cito_rounds import RoundDownloadError
from upset.data.probe_cito_recent import _EVENT_SLUG
from upset.data.probe_cito_rounds import describe_error_payload

BASE_URL = "https://api.citoapi.com/api/v1/ufc"
DEFAULT_ROOT = Path("data/raw/cito_current")
COMPONENTS = ("event", "bouts", "stats")


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _bouts(payload: dict, slug: str) -> int:
    data = payload["data"]
    if isinstance(data, list):
        rows = data
    elif isinstance(data, dict):
        candidates = [data[key] for key in ("bouts", "fights", "items", "results")
                      if isinstance(data.get(key), list)]
        if len(candidates) != 1:
            raise RoundDownloadError("Unknown card bout-list shape.")
        rows = candidates[0]
        page = data.get("pagination")
        if isinstance(page, dict) and any(page.get(key) for key in (
            "hasNextPage", "hasMore", "nextCursor", "nextPage", "next",
        )):
            raise RoundDownloadError("Bout listing is paginated; full card not captured.")
    else:
        raise RoundDownloadError("Unknown card bout-list shape.")
    ids = set()
    if not rows:
        raise RoundDownloadError("Card bout listing is empty.")
    for item in rows:
        if not isinstance(item, dict):
            raise RoundDownloadError("Invalid card bout-list item.")
        bout = item.get("bout", item)
        if not isinstance(bout, dict) or type(bout.get("id")) not in (str, int):
            raise RoundDownloadError("Card bout is missing its provider ID.")
        bout_id = str(bout["id"])
        if not bout_id or bout_id in ids or (
            bout.get("eventSlug") is not None and bout["eventSlug"] != slug
        ):
            raise RoundDownloadError("Duplicate, empty or mismatched card bout ID.")
        ids.add(bout_id)
    return len(ids)


def _check_payload(payload: object, kind: str, slug: str) -> int | None:
    if not isinstance(payload, dict) or payload.get("success") is False:
        raise RoundDownloadError("Cito card response is not a successful JSON object.")
    data = payload.get("data")
    if not isinstance(data, (dict, list)) or not data:
        raise RoundDownloadError("Cito card response has no data.")
    if kind == "bouts":
        return _bouts(payload, slug)
    if kind == "event":
        event = data.get("event", data) if isinstance(data, dict) else None
        if not isinstance(event, dict) or (
            event.get("slug") is not None and event["slug"] != slug
        ):
            raise RoundDownloadError("Unexpected event-detail shape or slug.")
    return None


def _read_saved(path: Path, kind: str, slug: str) -> tuple[dict, int | None]:
    try:
        saved = json.loads(path.read_text(encoding="utf-8"))
        expected_url = f"{BASE_URL}/events/{slug}"
        if kind != "event":
            expected_url += f"/{kind}"
        if not isinstance(saved, dict) or set(saved) != {
            "source", "event_slug", "source_url", "observed_at_utc", "response",
        } or saved["source"] != "cito" or saved["event_slug"] != slug or (
            saved["source_url"] != expected_url
        ) or not isinstance(saved["observed_at_utc"], str):
            raise RoundDownloadError("Cached card metadata differs from request.")
        return saved, _check_payload(saved["response"], kind, slug)
    except (OSError, UnicodeError, ValueError) as error:
        raise RoundDownloadError(f"Invalid cached Cito card file: {path.name}") from error


def _save(path: Path, saved: dict, kind: str, slug: str, api_key: str) -> None:
    encoded = json.dumps(saved, allow_nan=False, ensure_ascii=False, sort_keys=True)
    if api_key in encoded:
        raise RoundDownloadError("Cito response contains the API key; refusing to save.")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with NamedTemporaryFile(
            mode="w", encoding="utf-8", newline="\n", dir=path.parent,
            prefix=".upset-cito-card-", suffix=".json", delete=False,
        ) as stream:
            temporary = Path(stream.name)
            stream.write(encoded + "\n")
        if _read_saved(temporary, kind, slug)[0] != saved:
            raise RoundDownloadError("Cito card cache read-back differs.")
        temporary.replace(path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def collect_card(
    slug: str, output: Path, api_key: str, get: object, *,
    delay: float = 7.0, sleep: object = time.sleep,
) -> dict:
    """Fetch up to three endpoints and resume safely from verified cached files."""
    if not isinstance(slug, str) or not _EVENT_SLUG.fullmatch(slug):
        raise ValueError("Event slug may contain only letters, digits, and hyphens.")
    if not api_key or delay < 0:
        raise ValueError("API key required and delay must be nonnegative.")
    if output.exists() and not output.is_dir():
        raise ValueError("Card output path is not a directory.")
    if (output / "manifest.json").exists():
        raise ValueError("Card already captured; use another directory for a new snapshot.")
    fetched = 0
    hashes = {}
    observed = {}
    bout_count = None
    for kind in COMPONENTS:
        url = f"{BASE_URL}/events/{slug}"
        if kind != "event":
            url += f"/{kind}"
        path = output / f"{kind}.json"
        if path.exists():
            saved, count = _read_saved(path, kind, slug)
        else:
            if fetched:
                sleep(delay)
            try:
                response = get(url, headers={"x-api-key": api_key}, timeout=20)
            except OSError as error:
                raise RoundDownloadError(
                    f"Cito card request failed: {type(error).__name__}"
                ) from None
            try:
                payload = response.json()
            except ValueError as error:
                raise RoundDownloadError(
                    f"Cito card returned non-JSON HTTP {response.status_code}."
                ) from error
            if response.status_code != 200:
                labels = describe_error_payload(payload, secret=api_key)
                raise RoundDownloadError(
                    f"Cito card HTTP {response.status_code}; "
                    f"error_type={labels['error_type']}; error_code={labels['error_code']}"
                )
            count = _check_payload(payload, kind, slug)
            saved = {
                "source": "cito", "event_slug": slug, "source_url": url,
                "observed_at_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
                "response": payload,
            }
            _save(path, saved, kind, slug, api_key)
            fetched += 1
        hashes[kind] = _hash(path)
        observed[kind] = saved["observed_at_utc"]
        if kind == "bouts":
            bout_count = count
    report = {
        "status": "raw card captured; stats and bout coverage unverified",
        "event_slug": slug, "listed_bouts": bout_count,
        "api_calls": fetched, "observed_at_utc": observed,
        "sha256": hashes, "coverage_verified": False,
    }
    manifest = output / "manifest.json"
    manifest.write_text(json.dumps(report, sort_keys=True, indent=2) + "\n",
                        encoding="utf-8")
    if json.loads(manifest.read_text(encoding="utf-8")) != report:
        raise RoundDownloadError("Card manifest read-back differs.")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--event", required=True, help="Cito event ID or slug")
    parser.add_argument("--output", type=Path,
                        help="Snapshot directory (default: data/raw/cito_current/<event>)")
    args = parser.parse_args()
    from dotenv import load_dotenv

    load_dotenv(dotenv_path=Path(".env"))
    api_key = os.getenv("CITO_API_KEY")
    if not api_key:
        raise SystemExit("CITO_API_KEY is missing; keep the key out of chat.")
    import requests

    output = args.output or DEFAULT_ROOT / args.event
    try:
        report = collect_card(args.event, output, api_key, requests.get)
    except (OSError, ValueError) as error:
        parser.error(str(error))
    print(json.dumps(report, indent=2))
    print(f"Saved raw card under: {output}")


if __name__ == "__main__":
    main()
