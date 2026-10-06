"""Review cached fighter records without inferring identities or birth dates."""

import argparse
import json
import math
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory

from upset.data.collect_cito_archive import _digest
from upset.data.collect_cito_fighter_bundles import bundle_targets
from upset.data.identity import load_fighter_registry
from upset.data.reconcile_cito_archive import _write_verified


def measurement(value, field, issues):
    """Source zeroes/placeholders are missing, never real body measurements."""
    if value is None or value in ("", "--"):
        return None
    try:
        number = float(value)
    except (ValueError, TypeError):
        issues.append({"field": field, "reason": "invalid measurement", "value": value})
        return None
    bounds = {"height_inches": (40, 90), "reach_inches": (40, 100), "weight_lbs": (80, 400)}
    if not math.isfinite(number) or not bounds[field][0] <= number <= bounds[field][1]:
        issues.append({"field": field, "reason": "unavailable or implausible measurement", "value": value})
        return None
    return number


def normalize_profile(profile, observed, source_url):
    issues = []
    dob = profile.get("birthDate")
    if dob is not None:
        try:
            # Only accept a source DOB, never reverse-engineer it from age.
            dob = date.fromisoformat(dob[:10]).isoformat()
        except (ValueError, TypeError):
            issues.append({"field": "date_of_birth", "reason": "invalid source date"})
            dob = None
    result = {"source": "cito", "source_fighter_id": profile["id"],
              "source_fighter_slug": profile["slug"], "name": profile["name"],
              "nickname": profile.get("nickname"), "stance": profile.get("stance"),
              "division": profile.get("division"), "date_of_birth": dob,
              "reported_age": profile.get("age"), "observed_at_utc": observed,
              "source_url": source_url, "identity_verified": False}
    for raw, field in (("heightInches", "height_inches"), ("reachInches", "reach_inches"),
                       ("weightLbs", "weight_lbs")):
        result[field] = measurement(profile.get(raw), field, issues)
    return result, issues


def compare_candidate(observation, historical):
    evidence, conflicts = [], []
    for field in ("height_inches", "reach_inches", "stance"):
        current, previous = observation.get(field), historical.get(field)
        if current is None or previous is None:
            continue
        same = str(current).casefold() == str(previous).casefold() if field == "stance" else current == previous
        (evidence if same else conflicts).append({"field": field, "cito": current, "historical": previous})
    dob = historical.get("date_of_birth")
    age = observation.get("reported_age")
    if dob and type(age) is int:
        born = date.fromisoformat(dob)
        observed = date.fromisoformat(observation["observed_at_utc"][:10])
        expected = observed.year - born.year - ((observed.month, observed.day) < (born.month, born.day))
        # Stale provider ages remain evidence for review, not a date-of-birth claim.
        (evidence if age == expected else conflicts).append(
            {"field": "reported_age", "cito": age, "age_from_historical_dob": expected})
    return {"matching_fields": evidence, "conflicting_fields": conflicts,
            "status": "conflicting_profile_evidence" if conflicts else "profile_candidate_requires_review"}


def review_bundles(current, bundles, historical_profiles, registry_path, output):
    inputs = (current, bundles, historical_profiles, registry_path)
    if any(output.resolve() == p.resolve() or output.resolve().is_relative_to(p.resolve()) for p in inputs):
        raise ValueError("Review output overlaps an input.")
    targets, hashes = bundle_targets(current)
    report_path, plan_path = bundles / "report.json", bundles / "plan.json"
    report, plan = json.loads(report_path.read_text()), json.loads(plan_path.read_text())
    # Bind by complete relative export contents, so a downloaded archive can
    # be inspected elsewhere without trusting its original machine's paths.
    roots = [Path(k).parent for k, v in plan["input_sha256"].items()
             if Path(k).name == "manifest.json" and v == hashes[str(current / "manifest.json")]]
    if len(roots) != 1:
        raise ValueError("Fighter bundle current-export manifest differs.")
    plan_hashes = {str(Path(k).relative_to(roots[0])): v for k, v in plan["input_sha256"].items()}
    current_hashes = {str(Path(k).relative_to(current)): v for k, v in hashes.items()}
    hashes[str(report_path)], hashes[str(plan_path)] = _digest(report_path), _digest(plan_path)
    if (report["plan_sha256"] != hashes[str(plan_path)] or plan["requests"] != targets
            or plan_hashes != current_hashes
            or report["remaining_targets"] or len(report["requests"]) != len(targets)):
        raise ValueError("Fighter bundle is incomplete or differs from the current export.")
    responses = {}
    for target, record in zip(targets, report["requests"], strict=True):
        pid, kind = target["cito_fighter_id"], target["kind"]
        path = bundles / "fighters" / pid / f"{kind}.json"
        if any(record[k] != target[k] for k in target) or _digest(path) != record["raw_sha256"]:
            raise ValueError("Fighter bundle request or hash differs.")
        hashes[str(path)] = _digest(path)
        wrapper = json.loads(path.read_text())
        if (wrapper.get("http_status") != 200 or wrapper.get("expected_cito_fighter_id") != pid
                or wrapper.get("plan_sha256") != report["plan_sha256"]
                or wrapper.get("source_url") != target["source_url"]):
            raise ValueError("Unreviewed fighter response status or identity.")
        responses[pid, kind] = wrapper
    hashes[str(historical_profiles)], hashes[str(registry_path)] = _digest(historical_profiles), _digest(registry_path)
    registry = load_fighter_registry(registry_path)
    links = {(r.provider, r.provider_fighter_id): r.upset_fighter_id for r in registry.provider_links}
    historical = {}
    for line in historical_profiles.read_text().splitlines():
        row = json.loads(line)
        uid = row["upset_fighter_id"]
        if uid in historical or links.get(("ufcstats", row["source_fighter_id"])) != uid:
            raise ValueError("Duplicate historical profile identity.")
        historical[uid] = row
    known = {r.upset_fighter_id for r in registry.identities}
    if set(historical) - known:
        raise ValueError("Historical profile is absent from the registry.")
    if output.exists():
        old = json.loads((output / "manifest.json").read_text())
        if old["input_sha256"] != hashes or any(_digest(output / k) != v for k, v in old["output_sha256"].items()):
            raise ValueError("Existing profile review differs; use a new output.")
        return old
    queue = json.loads((current / "review.json").read_text())["unresolved_fighter_identities"]
    cohort_totals = defaultdict(Counter)
    totals_path = current / "fight_stats.jsonl"
    if totals_path.exists():
        for line in totals_path.read_text().splitlines():
            row = json.loads(line)
            for field in ("sig_strikes_landed", "sig_strikes_attempted", "takedowns_landed", "takedowns_attempted"):
                cohort_totals[row["source_fighter_id"]][field] += row[field]
    profiles, findings = [], []
    for item in queue:
        pid = item["cito_fighter_id"]
        wrapper = responses[pid, "profile"]
        profile = wrapper["response"]["data"]
        if profile.get("id") != pid:
            raise ValueError("Profile ID differs from the requested identity.")
        observation, issues = normalize_profile(profile, wrapper["observed_at_utc"], wrapper["source_url"])
        observation["raw_sha256"] = hashes[str(bundles / "fighters" / pid / "profile.json")]
        history = responses[pid, "fights"]["response"]["data"]
        if not isinstance(history, list):
            raise TypeError("Unsupported fighter history shape.")
        aggregate = responses[pid, "stats"]["response"]["data"]
        if not isinstance(aggregate, dict):
            raise TypeError("Unsupported fighter stats shape.")
        for source, field in (("significantStrikesLanded", "sig_strikes_landed"),
                              ("significantStrikesAttempted", "sig_strikes_attempted"),
                              ("takedownsLanded", "takedowns_landed"),
                              ("takedownsAttempted", "takedowns_attempted")):
            value = aggregate.get(source)
            if value is not None and float(value) < cohort_totals[pid][field]:
                issues.append({"field": field, "reason": "career aggregate below captured current-cohort counts; scope, freshness or identity requires review",
                               "provider_aggregate": value, "captured_current_cohort": cohort_totals[pid][field],
                               "provider_last_synced_at": aggregate.get("lastSyncedAt")})
        # This named collision was independently reviewed on UFC's two athlete pages.
        if (pid == "accf0e18-9e9b-4e82-b74a-26afc7aafa5b" and profile.get("nickname") == "Joe Boxer"
                and any(r.get("bout", {}).get("id") == "2e7f8d0ad385876d" for r in history)):
            issues.append({"field": "profile_identity", "reason": "mixed namesake profile: Joe Boxer bio with current Psicosis bout history",
                           "source_urls": ["https://www.ufc.com/athlete/victor-valenzuela",
                                           "https://www.ufc.com/athlete/victor-valenzuela-0"]})
            observation["profile_requires_identity_review"] = True
        candidates = []
        for candidate in item["name_only_candidates"]:
            uid = candidate["upset_fighter_id"]
            if uid not in historical:
                raise ValueError("Candidate historical profile is unavailable.")
            candidates.append({**candidate, **compare_candidate(observation, historical[uid])})
        profiles.append(observation)
        findings.append({"cito_fighter_id": pid, "name": observation["name"], "issues": issues,
                         "candidates": candidates, "supporting_bouts": item["supporting_bouts"],
                         "source_history_rows": len(history), "identity_links_added": 0})
    if any(_digest(Path(k)) != v for k, v in hashes.items()):
        raise ValueError("Inputs changed during profile review.")
    output.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=output.parent, prefix=".upset-profile-review-") as temporary:
        folder = Path(temporary) / "review"
        folder.mkdir()
        _write_verified(folder / "profile_observations.jsonl", profiles)
        _write_verified(folder / "identity_review.jsonl", findings)
        summary = {"schema_version": 1, "status": "offline profile observations and identity evidence reviewed",
                   "provider_profiles": len(profiles), "profiles_with_source_dob": sum(r["date_of_birth"] is not None for r in profiles),
                   "profiles_with_findings": sum(bool(r["issues"]) for r in findings),
                   "profiles_with_aggregate_findings": sum(any("career aggregate below" in i["reason"] for i in r["issues"]) for r in findings),
                   "candidate_statuses": dict(Counter(c["status"] for r in findings for c in r["candidates"])),
                   "identity_links_added": 0, "api_calls": 0, "training_ready": False,
                   "input_sha256": hashes,
                   "output_sha256": {p.name: _digest(p) for p in folder.iterdir()}}
        (folder / "manifest.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
        folder.rename(output)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--current", type=Path, default=Path("data/processed/cito_current_archive_v1"))
    parser.add_argument("--bundles", type=Path, default=Path("data/raw/cito_fighter_bundles_v1"))
    parser.add_argument("--profiles", type=Path, default=Path("data/processed/kaggle_ufc_1994_2026/identified/fighters_identified.jsonl"))
    parser.add_argument("--registry", type=Path, default=Path("data/processed/cito_gap_reconciliation_v1/fighter_registry.json"))
    parser.add_argument("--output", type=Path, default=Path("data/processed/cito_fighter_review_v1"))
    args = parser.parse_args()
    try:
        result = review_bundles(args.current, args.bundles, args.profiles, args.registry, args.output)
    except (ValueError, KeyError, TypeError, OSError) as error:
        parser.error(str(error))
    print(json.dumps({k: v for k, v in result.items() if k not in {"input_sha256", "output_sha256"}}, indent=2))
    print(f"Saved to: {args.output}")


if __name__ == "__main__":
    main()
