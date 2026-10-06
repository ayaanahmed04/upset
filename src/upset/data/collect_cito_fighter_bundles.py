"""Cache profile, career stats and fight history for unresolved current fighters.

This preserves source evidence. It neither resolves identities nor uses current
career aggregates as historical model features.
"""

import argparse
import json
import os
import re
import time
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

from upset.data.collect_cito_archive import _atomic_json, _digest
from upset.data.collect_cito_card import BASE_URL

ENDPOINTS = {"profile": "", "stats": "/stats", "fights": "/fights"}
SAFE_SLUG = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*\Z")


def bundle_targets(current: Path) -> tuple[list, dict]:
    manifest_path = current / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    hashes = {str(manifest_path): _digest(manifest_path)}
    for name, digest in manifest["output_sha256"].items():
        path = current / name
        if not path.resolve().is_relative_to(current.resolve()) or _digest(path) != digest:
            raise ValueError("Current export hash differs.")
        hashes[str(path)] = digest
    review = json.loads((current / "review.json").read_text())
    targets = []
    seen = set()
    for fighter in review["unresolved_fighter_identities"]:
        pid = fighter["cito_fighter_id"]
        if not re.fullmatch(r"[a-zA-Z0-9-]+", pid) or pid in seen:
            raise ValueError("Invalid or duplicate unresolved provider ID.")
        seen.add(pid)
        profile_slugs = {p["profile"].get("slug") for p in fighter["profile_observations"]
                         if p["profile"].get("id") == pid}
        candidates = sorted(s for s in profile_slugs if isinstance(s, str) and SAFE_SLUG.fullmatch(s))
        if len(candidates) != 1:
            candidates = sorted({s for s in fighter["source_slugs"] if SAFE_SLUG.fullmatch(s)})
        if len(candidates) != 1:
            raise ValueError(f"Ambiguous or unsafe fighter slug requires review: {pid}")
        slug = candidates[0]
        for kind, suffix in ENDPOINTS.items():
            targets.append({"cito_fighter_id": pid, "fighter_names": fighter["source_names"],
                            "slug": slug, "kind": kind,
                            "source_url": f"{BASE_URL}/fighters/{slug}{suffix}"})
    return targets, hashes


def _summarize(wrapper: dict, target: dict) -> dict:
    response = wrapper.get("response")
    data = response.get("data") if isinstance(response, dict) else None
    okay = wrapper.get("http_status") == 200 and isinstance(response, dict) and response.get("success") is not False
    okay = okay and isinstance(data, (dict, list))
    pid = None
    if target["kind"] == "profile" and isinstance(data, dict):
        profile = data.get("fighter") if isinstance(data.get("fighter"), dict) else data
        pid = profile.get("id") or profile.get("fighterId")
        if pid is not None and str(pid) != target["cito_fighter_id"]:
            return {"status": "different_provider_identity", "returned_provider_id": str(pid),
                    "data_keys": sorted(data), "identity_verified": False}
    return {"status": "source_response_captured" if okay else "requires_source_review",
            "returned_provider_id": pid, "data_keys": sorted(data) if isinstance(data, dict) else None,
            "list_rows": len(data) if isinstance(data, list) else None,
            "identity_verified": False}


def collect_bundles(current: Path, output: Path, api_key: str, get: object, *,
                    max_requests: int = 303, delay: float = 2.2, sleep: object = time.sleep,
                    log: object = print) -> dict:
    if not api_key or max_requests < 1 or delay < 0 or output.resolve().is_relative_to(current.resolve()):
        raise ValueError("Key, positive request cap and a separate output are required.")
    targets, hashes = bundle_targets(current)
    plan = {"schema_version": 1, "input_sha256": hashes, "requests": targets}
    plan_path = output / "plan.json"
    if plan_path.exists():
        if json.loads(plan_path.read_text()) != plan:
            raise ValueError("Existing fighter-bundle plan differs; use a new output.")
    else:
        _atomic_json(plan_path, plan)
    plan_hash = _digest(plan_path)
    examined, fetched = [], 0
    blocked_identities = set()
    paused = None
    effective_delay = delay
    for index, target in enumerate(targets):
        pid, kind = target["cito_fighter_id"], target["kind"]
        if pid in blocked_identities:
            examined.append({**target, "status": "skipped_after_identity_conflict", "identity_verified": False})
            continue
        path = output / "fighters" / pid / f"{kind}.json"
        if path.exists():
            wrapper = json.loads(path.read_text())
            if (wrapper.get("source") != "cito" or wrapper.get("source_url") != target["source_url"]
                    or wrapper.get("expected_cito_fighter_id") != pid or wrapper.get("plan_sha256") != plan_hash):
                raise ValueError("Cached fighter response differs from the immutable plan.")
            cached = True
        else:
            if fetched >= max_requests:
                paused = "request_cap"
                break
            if fetched:
                sleep(effective_delay)
            log(f"[{index + 1}/{len(targets)}] {target['slug']}: {kind}", flush=True)
            wrapper = {"source": "cito", "source_url": target["source_url"],
                       "expected_cito_fighter_id": pid, "plan_sha256": plan_hash,
                       "observed_at_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z")}
            try:
                response = get(target["source_url"], headers={"x-api-key": api_key}, timeout=30,
                               allow_redirects=False)
                wrapper["http_status"] = response.status_code
                header_values = getattr(response, "headers", {})
                wrapper["rate_limit"] = {k: header_values.get(k) for k in (
                    "X-RateLimit-Limit", "X-RateLimit-Remaining", "X-RateLimit-Reset", "Retry-After")}
                try:
                    wrapper["response"] = response.json()
                except ValueError:
                    wrapper["request_error"] = "non_json_response"
            except OSError as error:
                wrapper["request_error"] = type(error).__name__
            if api_key in json.dumps(wrapper, ensure_ascii=False):
                raise ValueError("Response includes API key; refusing to save.")
            _atomic_json(path, wrapper)
            fetched += 1
            cached = False
            try:
                limit = int(wrapper.get("rate_limit", {}).get("X-RateLimit-Limit"))
                if limit > 0:
                    effective_delay = max(delay, 60 / limit + 0.2)
            except (TypeError, ValueError):
                pass
        summary = _summarize(wrapper, target)
        examined.append({**target, **summary, "http_status": wrapper.get("http_status"),
                         "raw_path": str(path), "raw_sha256": _digest(path), "cached": cached,
                         "observed_at_utc": wrapper["observed_at_utc"]})
        log(f"  {summary['status']}; HTTP {wrapper.get('http_status')}", flush=True)
        if summary["status"] == "different_provider_identity":
            blocked_identities.add(pid)
        if wrapper.get("http_status") in (401, 403, 429):
            paused = "access_or_rate_limit_response"
            break
    if any(_digest(Path(path)) != digest for path, digest in hashes.items()) or _digest(plan_path) != plan_hash:
        raise ValueError("Input changed during fighter collection.")
    report = {"schema_version": 1, "status": "fighter source evidence captured; identity review pending",
              "target_fighters": len({t["cito_fighter_id"] for t in targets}), "target_requests": len(targets),
              "examined_targets": len(examined), "remaining_targets": len(targets) - len(examined),
              "api_calls_this_run": fetched, "request_cap": max_requests, "paused_reason": paused,
              "statuses": dict(Counter(r["status"] for r in examined)), "requests": examined,
              "plan_sha256": plan_hash, "identity_links_added": 0, "training_ready": False}
    _atomic_json(output / "report.json", report)
    return report


def main() -> None:
    import requests
    from dotenv import load_dotenv

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--current", type=Path, default=Path("data/processed/cito_current_archive_v1"))
    parser.add_argument("--output", type=Path, default=Path("data/raw/cito_fighter_bundles_v1"))
    parser.add_argument("--max-requests", type=int, default=303)
    parser.add_argument("--delay", type=float, default=2.2)
    args = parser.parse_args()
    load_dotenv()
    key = os.getenv("CITO_API_KEY", "")
    if not key:
        parser.error("Set CITO_API_KEY in the local environment.")
    try:
        report = collect_bundles(args.current, args.output, key, requests.get,
                                 max_requests=args.max_requests, delay=args.delay)
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.error(str(error))
    print(json.dumps({k: v for k, v in report.items() if k != "requests"}, indent=2))
    print(f"Report: {args.output / 'report.json'}")


if __name__ == "__main__":
    main()
