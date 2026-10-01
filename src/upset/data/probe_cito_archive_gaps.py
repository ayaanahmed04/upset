"""Cache a bounded endpoint probe for gaps in the verified archive export.

Success means source rows were returned for review, not that they have been
accepted into UPSET. Saved requests are reused; each new call is capped.
"""

import argparse
import hashlib
import json
import os
import re
import time
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

from upset.data.collect_cito_archive import _atomic_json, _digest
from upset.data.collect_cito_card import BASE_URL


def _url(target: dict, identifier: str | None = None) -> str:
    scope, endpoint = target["scope"], target["endpoint"]
    value = target["identifier"] if identifier is None else identifier
    if ((scope, endpoint) not in {("bouts", "stats"), ("bouts", "rounds"),
                                  ("events", "stats"), ("events", "bouts")}
            or not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9-]{1,200}", value)):
        raise ValueError("Unsupported endpoint or unsafe identifier in gap plan.")
    return f"{BASE_URL}/{scope}/{value}/{endpoint}"


def _summary(saved: dict, target: dict) -> dict:
    response = saved.get("response")
    data = response.get("data") if isinstance(response, dict) else None
    rows = []
    if isinstance(data, list):
        rows = data
    elif isinstance(data, dict):
        for key in ("boutStats", "roundStats", "stats", "rounds", "rows", "items", "results", "bouts"):
            if isinstance(data.get(key), list):
                rows.extend(data[key])
    allowed = {target["identifier"], target.get("fallback_identifier")}
    contradicts = target["scope"] == "bouts" and (
        (isinstance(data, dict) and "boutId" in data and str(data["boutId"]) not in allowed)
        or any(isinstance(row, dict) and "boutId" in row and str(row["boutId"]) not in allowed for row in rows))
    available = (saved.get("http_status") == 200 and isinstance(response, dict)
                 and response.get("success") is not False and bool(rows)
                 and all(isinstance(row, dict) for row in rows) and not contradicts)
    return {"status": "rows_returned_for_review" if available else "requires_provider_review",
            "http_status": saved.get("http_status"), "row_count": len(rows),
            "contradictory_bout_id": contradicts, "request_error": saved.get("request_error")}


def probe_gaps(plan_path: Path, output: Path, api_key: str, get: object, *,
               max_requests: int = 50, delay: float = 7, sleep: object = time.sleep,
               log: object = print) -> dict:
    if not api_key or max_requests < 1 or delay < 0:
        raise ValueError("API key, positive request cap and nonnegative delay required.")
    plan_hash = _digest(plan_path)
    plan = json.loads(plan_path.read_text())
    if plan.get("schema_version") != 1 or not isinstance(plan.get("requests"), list):
        raise ValueError("Unsupported gap plan.")
    targets = plan["requests"]
    urls = []
    for target in targets:
        url = _url(target)
        if url != target["source_url"]:
            raise ValueError("Gap plan URL differs from its endpoint.")
        urls.append(url)
        if "fallback_identifier" in target:
            urls.append(_url(target, target["fallback_identifier"]))
    if len(urls) != len(set(urls)):
        raise ValueError("Duplicate request URLs in gap plan.")
    if output.resolve().is_relative_to(plan_path.parent.resolve()):
        raise ValueError("Probe output must be separate from the immutable export.")
    examined = []
    fetched = primaries = 0
    pending_fallbacks = []
    stopped = False
    for target in targets:
        for fallback in (False, True):
            if fallback and "fallback_identifier" not in target:
                break
            url = _url(target, target["fallback_identifier"] if fallback else None)
            path = output / "requests" / f"{hashlib.sha256(url.encode()).hexdigest()}.json"
            if path.exists():
                saved = json.loads(path.read_text())
                if (saved.get("plan_sha256") != plan_hash or saved.get("source_url") != url
                        or saved.get("source") != "cito"):
                    raise ValueError("Cached probe does not match this immutable plan.")
                cached = True
            else:
                if fetched >= max_requests:
                    if fallback:
                        pending_fallbacks.append(url)
                    stopped = True
                    break
                if fetched:
                    sleep(delay)
                log(f"[{fetched + 1}/{max_requests}] {target['scope']}/{url.split('/')[-2]}/{target['endpoint']}", flush=True)
                saved = {"source": "cito", "source_url": url, "plan_sha256": plan_hash,
                         "observed_at_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z")}
                try:
                    response = get(url, headers={"x-api-key": api_key}, timeout=30,
                                   allow_redirects=False)
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
                cached = False
            summary = _summary(saved, target)
            examined.append({"source_url": url, "fallback": fallback, "cached": cached,
                             "reason": target["reason"], **summary,
                             "raw_path": str(path), "raw_sha256": _digest(path)})
            if not fallback:
                primaries += 1
            log(f"  {summary['status']}; rows={summary['row_count']}", flush=True)
            if saved.get("http_status") in (401, 403, 429):
                stopped = True
                break
            if summary["status"] == "rows_returned_for_review":
                break
        if stopped:
            break
    if _digest(plan_path) != plan_hash:
        raise ValueError("Gap plan changed during probe.")
    report = {"schema_version": 1, "status": "targeted source responses captured; reconciliation required",
              "plan_sha256": plan_hash, "primary_targets": len(targets), "primary_targets_examined": primaries,
              "remaining_primary_targets": len(targets) - primaries,
              "pending_fallback_requests": pending_fallbacks,
              "api_calls_this_run": fetched, "request_cap": max_requests,
              "statuses": dict(Counter(row["status"] for row in examined)),
              "requests": examined, "coverage_verified": False, "training_ready": False}
    _atomic_json(output / "report.json", report)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path,
                        default=Path("data/processed/cito_historical_rounds_v1/gap_probe_plan.json"))
    parser.add_argument("--output", type=Path, default=Path("data/raw/cito_archive/gap_probes_v1"))
    parser.add_argument("--max-requests", type=int, default=50)
    args = parser.parse_args()
    from dotenv import load_dotenv

    load_dotenv(dotenv_path=Path(".env"))
    key = os.getenv("CITO_API_KEY")
    if not key:
        raise SystemExit("CITO_API_KEY is missing; keep the key out of chat.")
    import requests

    try:
        report = probe_gaps(args.plan, args.output, key, requests.get, max_requests=args.max_requests)
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.error(str(error))
    print(json.dumps({k: v for k, v in report.items() if k != "requests"}, indent=2))
    print(f"Report: {args.output / 'report.json'}")


if __name__ == "__main__":
    main()
