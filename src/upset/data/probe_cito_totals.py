"""Fetch one Cito fight-total response and print only its data shape."""

import argparse
import json
import os
from pathlib import Path
from tempfile import NamedTemporaryFile

from upset.data.collect_cito_rounds import (
    RoundDownloadError,
    validate_bout_ids,
)
from upset.data.probe_cito_rounds import (
    describe_error_payload,
    describe_round_payload,
)

DEFAULT_OUTPUT = Path("data/raw/cito_totals")


def _check_payload(payload: object, bout_id: str) -> dict:
    """Check the envelope without guessing how the provider encodes totals."""
    if not isinstance(payload, dict) or payload.get("success") is False:
        raise RoundDownloadError("Cito totals response is not a successful object.")
    data = payload.get("data")
    if not isinstance(data, (dict, list)) or not data:
        raise RoundDownloadError("Cito totals response has no data.")
    if isinstance(data, dict):
        if "boutId" in data and str(data["boutId"]) != bout_id:
            raise RoundDownloadError("Cito totals response references another bout.")
        lists = [value for value in data.values() if isinstance(value, list)]
    else:
        lists = [data]
    for rows in lists:
        for row in rows:
            if not isinstance(row, dict):
                raise RoundDownloadError(
                    "Cito totals response contains a non-object row."
                )
            if "boutId" in row and str(row["boutId"]) != bout_id:
                raise RoundDownloadError("Cito totals row references another bout.")
    return payload


def _read_cache(path: Path, bout_id: str) -> dict:
    try:
        saved = json.loads(path.read_text(encoding="utf-8"))
        if (
            not isinstance(saved, dict)
            or saved.get("source") != "cito"
            or saved.get("source_bout_id") != bout_id
        ):
            raise RoundDownloadError("Cached totals metadata does not match.")
        return _check_payload(saved.get("response"), bout_id)
    except (OSError, UnicodeError, ValueError) as error:
        raise RoundDownloadError(
            f"Invalid cached totals file: {path.name}"
        ) from error


def probe_one(bout_id: str, output_dir: Path, api_key: str, get: object) -> dict:
    """Save a nonempty response once and show a safe structural summary."""
    validate_bout_ids([bout_id])
    if not api_key:
        raise ValueError("Cito API key is required.")
    path = output_dir / f"{bout_id}.json"
    if path.exists():
        payload = _read_cache(path, bout_id)
        fetched = False
    else:
        url = f"https://api.citoapi.com/api/v1/ufc/bouts/{bout_id}/stats"
        response = get(url, headers={"x-api-key": api_key}, timeout=20)
        try:
            payload = response.json()
        except ValueError as error:
            raise RoundDownloadError(
                f"Cito totals returned non-JSON HTTP {response.status_code}."
            ) from error
        if response.status_code != 200:
            labels = describe_error_payload(payload, secret=api_key)
            raise RoundDownloadError(
                f"Cito totals HTTP {response.status_code}; "
                f"error_type={labels['error_type']}; error_code={labels['error_code']}"
            )
        _check_payload(payload, bout_id)
        encoded = json.dumps({
            "source": "cito", "source_bout_id": bout_id, "response": payload,
        }, ensure_ascii=False, allow_nan=False, sort_keys=True)
        if api_key in encoded:
            raise RoundDownloadError("Cito response contains the API key.")
        output_dir.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            with NamedTemporaryFile(
                mode="w", encoding="utf-8", newline="\n", dir=output_dir,
                prefix=".upset-cito-totals-", suffix=".json", delete=False,
            ) as saved:
                temporary = Path(saved.name)
                saved.write(encoded + "\n")
            if _read_cache(temporary, bout_id) != payload:
                raise RoundDownloadError("Cito totals read-back verification failed.")
            temporary.replace(path)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
        fetched = True
    return {"bout_id": bout_id, "fetched": fetched,
            "shape": describe_round_payload(payload)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bout-id", required=True)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    from dotenv import load_dotenv

    load_dotenv(dotenv_path=Path(".env"))
    api_key = os.getenv("CITO_API_KEY")
    if not api_key:
        raise SystemExit("CITO_API_KEY is missing; keep the key out of chat.")
    import requests

    try:
        result = probe_one(args.bout_id, args.output_dir, api_key, requests.get)
    except RoundDownloadError as error:
        raise SystemExit(str(error)) from None
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print(f"Saved under: {args.output_dir}")


if __name__ == "__main__":
    main()
