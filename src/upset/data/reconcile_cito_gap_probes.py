"""Reconcile saved gap responses offline without changing the archive or snapshot.

Historical additions require paired totals AND complete round sums. Current
totals computed from rounds remain explicitly derived staging data.
"""

import argparse
import hashlib
import json
from collections import Counter
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory

from upset.data.audit_cito_archive import _participant
from upset.data.collect_cito_archive import _digest
from upset.data.collect_cito_card import BASE_URL
from upset.data.export_cito_archive_rounds import read_bridge, result_record
from upset.data.identity import (
    FighterProviderLink,
    FighterRegistry,
    load_fighter_registry,
    save_fighter_registry,
)
from upset.data.probe_cito_archive_gaps import _url
from upset.data.reconcile_cito_archive import (
    COMMON_STATS,
    _history,
    _numbers,
    _write_verified,
    match_bout,
)
from upset.data.stage_current import ACCEPTED_HISTORICAL_FIGHTS_SHA256

# Scoped aliases observed in the saved September 30 responses. An alias is not
# acceptance: date, both identities, paired totals and round sums must agree.
ROAD_ALIASES = {
    "16523b1bec3cd7b0": "road-ufc-season-4-semifinals-nyamjargal-tumendemberel-terrance-saeteurn",
    "abf5f4d6f777cf7b": "1273",
}
ROAD_SLUG = "ufc-road-to-ufc-4-6"
ROAD_CANONICAL_SLUG = "road-ufc-season-4-semifinals"
CURRENT_MISSING_TOTALS = {"12979", "fight-night-september-12-2026-rafa-garcia-zhu-rong"}


def read_probes(probes: Path, plan_path: Path) -> tuple[dict, dict, dict]:
    """Verify every response against the plan, report hash and URL-derived file."""
    plan_hash = _digest(plan_path)
    plan = json.loads(plan_path.read_text())
    allowed = {}
    for target in plan["requests"]:
        if _url(target) != target["source_url"]:
            raise ValueError("Probe plan URL differs.")
        for identifier in (target["identifier"], target.get("fallback_identifier")):
            if identifier is not None:
                url = _url(target, identifier)
                if url in allowed:
                    raise ValueError("Duplicate URL in probe plan.")
                allowed[url] = target
    report_path = probes / "report.json"
    report = json.loads(report_path.read_text())
    if report.get("schema_version") != 1 or report.get("plan_sha256") != plan_hash:
        raise ValueError("Probe report differs from accepted export plan.")
    saved, hashes = {}, {str(plan_path): plan_hash, str(report_path): _digest(report_path)}
    for item in report["requests"]:
        url = item["source_url"]
        if url not in allowed or url in saved or item["reason"] != allowed[url]["reason"]:
            raise ValueError("Unexpected or duplicate probe response.")
        path = probes / "requests" / f"{hashlib.sha256(url.encode()).hexdigest()}.json"
        if _digest(path) != item["raw_sha256"]:
            raise ValueError("Probe response hash differs.")
        wrapper = json.loads(path.read_text())
        if (wrapper.get("source") != "cito" or wrapper.get("source_url") != url
                or wrapper.get("plan_sha256") != plan_hash
                or wrapper.get("http_status") != item["http_status"]):
            raise ValueError("Probe source, plan or HTTP evidence differs.")
        observed = datetime.fromisoformat(wrapper["observed_at_utc"])
        if observed.utcoffset() is None:
            raise ValueError("Probe observation must include a timezone.")
        hashes[str(path)] = _digest(path)
        saved[url] = wrapper
    return saved, report, hashes


def _data(saved: dict, url: str):
    wrapper = saved[url]
    response = wrapper.get("response")
    if (wrapper.get("http_status") != 200 or not isinstance(response, dict)
            or response.get("success") is False):
        raise ValueError(f"No successful source response: {url}")
    return response.get("data")


def _bout_witnesses(bouts: list) -> list:
    """Stat-array ordering is not evidence of a different bout response."""
    result = []
    for bout in bouts:
        copy = dict(bout)
        for key in ("boutStats", "roundStats"):
            if key in copy:
                copy[key] = sorted(copy[key], key=lambda r: json.dumps(r, sort_keys=True))
        result.append(copy)
    return sorted(result, key=lambda b: str(b["id"]))


def reconcile_rounds(bout: dict, raw_rounds: list, *, expected_rounds: int,
                     expected_totals: list | None = None) -> tuple[list, list]:
    """Require two participants in every round and reconcile every observed field."""
    fighters = bout["fighters"]
    if (len(fighters) != 2 or not all(f.get("fighterId") for f in fighters)
            or fighters[0]["fighterId"] == fighters[1]["fighterId"]
            or type(expected_rounds) is not int or expected_rounds < 1):
        raise ValueError("Invalid paired round participants or round count.")
    seen, source_ids, rows = set(), set(), []
    for raw in raw_rounds:
        person, number = _participant(raw, fighters), raw.get("round")
        sid = raw.get("id")
        if (str(raw.get("boutId")) != str(bout["id"]) or person is None
                or type(number) is not int or not 1 <= number <= expected_rounds
                or (person, number) in seen or not isinstance(sid, str) or not sid
                or sid in source_ids):
            raise ValueError("Round has invalid bout/participant/number or duplicate source ID.")
        seen.add((person, number))
        source_ids.add(sid)
        rows.append({"source": "cito", "source_bout_id": str(bout["id"]),
                     "source_fighter_id": fighters[person]["fighterId"],
                     "source_round_stat_id": sid, "fighter_name": raw.get("fighterName"),
                     "round_number": number, **_numbers(raw)})
    if seen != {(p, n) for p in (0, 1) for n in range(1, expected_rounds + 1)}:
        raise ValueError("Incomplete paired round coverage.")
    derived = []
    fields = list(_numbers(raw_rounds[0]))
    for person in (0, 1):
        pid = fighters[person]["fighterId"]
        group = [row for row in rows if row["source_fighter_id"] == pid]
        totals = {field: None if any(r[field] is None for r in group)
                  else sum(r[field] for r in group) for field in fields}
        derived.append({"source": "cito", "source_bout_id": str(bout["id"]),
                        "source_fighter_id": pid, "fighter_name": fighters[person]["fighterName"],
                        "totals_basis": "sum_of_complete_observed_rounds",
                        "provider_fight_totals_present": expected_totals is not None, **totals})
    if expected_totals is not None:
        people = [_participant(row, fighters) for row in expected_totals]
        if len(expected_totals) != 2 or Counter(people) != Counter((0, 1)):
            raise ValueError("Provider totals must identify two unique participants.")
        for person, total in zip(people, expected_totals, strict=True):
            if str(total.get("boutId")) != str(bout["id"]):
                raise ValueError("Provider total bout ID differs.")
            for field, value in _numbers(total).items():
                actual = derived[person][field]
                if value is not None and actual is not None and actual != value:
                    raise ValueError(f"Provider totals differ from round sums: {field}")
    return rows, derived


def reconcile_gaps(accepted: Path, bridge: Path, historical: Path, probes: Path,
                   output: Path, *, expected_history_sha256=ACCEPTED_HISTORICAL_FIGHTS_SHA256) -> dict:
    if any(output.resolve().is_relative_to(p.resolve()) for p in (accepted, bridge, historical, probes)):
        raise ValueError("Output overlaps an input directory.")
    base_path = accepted / "manifest.json"
    base = json.loads(base_path.read_text())
    hashes = {str(base_path): _digest(base_path), str(bridge / "manifest.json"): _digest(bridge / "manifest.json")}
    if hashes[str(bridge / "manifest.json")] != base["bridge_manifest_sha256"]:
        raise ValueError("Accepted export bridge differs.")
    for name, digest in base["output_sha256"].items():
        path = accepted / name
        if path.parent != accepted or _digest(path) != digest:
            raise ValueError("Accepted export hash differs.")
        hashes[str(path)] = digest
    bmanifest, brows = read_bridge(bridge)
    for name, digest in bmanifest["output_sha256"].items():
        hashes[str(bridge / name)] = digest
    if bmanifest["input_sha256"] != base["input_sha256"]:
        raise ValueError("Accepted bridge inputs differ.")
    for key, name in (("historical_fights", "fights_identified.jsonl"),
                      ("historical_stats", "fight_stats_identified.jsonl")):
        path = historical / name
        if _digest(path) != base["input_sha256"][key]:
            raise ValueError("Historical snapshot differs from accepted export.")
        hashes[str(path)] = _digest(path)
    if base["input_sha256"]["historical_fights"] != expected_history_sha256:
        raise ValueError("Historical fights differ from accepted snapshot.")
    saved, report, probe_hashes = read_probes(probes, accepted / "gap_probe_plan.json")
    hashes.update(probe_hashes)
    if output.exists():
        previous = json.loads((output / "manifest.json").read_text())
        if previous["input_sha256"] != hashes or any(
                _digest(output / name) != digest for name, digest in previous["output_sha256"].items()):
            raise ValueError("Existing reconciliation differs; use a new immutable output.")
        return previous
    registry = load_fighter_registry(accepted / "fighter_registry.json")
    history, by_date, stats = _history(historical / "fights_identified.jsonl",
                                      historical / "fight_stats_identified.jsonl", registry)
    indexed = {row["source_bout_id"]: row for row in history}
    links = {r.provider_fighter_id: r.upset_fighter_id for r in registry.provider_links if r.provider == "cito"}
    existing_bids = {json.loads(line)["historical_bout_id"] for line in
                     (accepted / "bout_results.jsonl").read_text().splitlines()}
    if len(existing_bids) != base["historical_bouts"]:
        raise ValueError("Accepted historical bout count differs.")
    stats_url = f"{BASE_URL}/events/{ROAD_SLUG}/stats"
    bouts_url = f"{BASE_URL}/events/{ROAD_SLUG}/bouts"
    data, bouts = _data(saved, stats_url), _data(saved, bouts_url)
    event = data["event"]
    if (event["slug"] != ROAD_CANONICAL_SLUG or event["eventDate"] != "2025-08-22"
            or _bout_witnesses(data["bouts"]) != _bout_witnesses(bouts)
            or len(bouts) != len(ROAD_ALIASES)
            or {str(b["id"]) for b in bouts} != set(ROAD_ALIASES.values())):
        raise ValueError("Reviewed Road to UFC event alias or paired endpoints differ.")
    new_rounds, matches, additions, review = [], [], [], []
    for hid, pid in ROAD_ALIASES.items():
        if hid in existing_bids:
            raise ValueError("Supplement repeats an already accepted historical bout.")
        bout = next(b for b in bouts if str(b["id"]) == pid)
        totals = [r for r in data["boutStats"] if str(r["boutId"]) == pid]
        rounds = [r for r in data["roundStats"] if str(r["boutId"]) == pid]
        # Require the alternate-ID bout endpoints to witness the same numeric rows.
        alias_stats = _data(saved, f"{BASE_URL}/bouts/{hid}/stats")
        alias_rounds = _data(saved, f"{BASE_URL}/bouts/{hid}/rounds")
        signature = lambda rows: sorted((str(r["id"]), str(r["boutId"]), r.get("round"),
                                         json.dumps(_numbers(r), sort_keys=True)) for r in rows)
        if (signature(alias_stats["boutStats"]) != signature(totals)
                or signature(alias_stats["roundStats"]) != signature(rounds)
                or signature(alias_rounds) != signature(rounds)):
            raise ValueError("Alternate-ID source endpoints disagree.")
        match = match_bout(event["eventDate"], bout, totals, by_date, stats, links)
        if (match["status"] != "totals_verified_proposal"
                or match["candidates"][0]["historical_bout_id"] != hid):
            raise ValueError(f"Historical paired totals or identity not verified: {hid}")
        candidate = match["candidates"][0]
        normalized, _derived = reconcile_rounds(bout, rounds, expected_rounds=indexed[hid]["result_round"],
                                                expected_totals=totals)
        for i, fighter in enumerate(bout["fighters"]):
            uid = candidate["upset_fighter_ids_in_cito_order"][i]
            fid = fighter["fighterId"]
            if fid not in links:
                additions.append(FighterProviderLink("cito", fid, uid,
                    f"Paired historical totals and complete round sums; probe report SHA256 {_digest(probes / 'report.json')}; UFCStats bout {hid}"))
            links[fid] = uid
            group = [r for r in normalized if r["source_fighter_id"] == fid]
            compared = 0
            for field in COMMON_STATS:
                expected = stats[(hid, uid)][field]
                values = [r[field] for r in group]
                actual = None if any(v is None for v in values) else sum(values)
                if actual is not None and expected is not None:
                    compared += 1
                    if actual != expected:
                        raise ValueError(f"Historical round sums differ: {hid}/{field}")
            if compared < 12:
                raise ValueError("Insufficient observed historical round sums.")
            for row in group:
                new_rounds.append({**row, "historical_bout_id": hid, "upset_fighter_id": uid,
                    "event_date": indexed[hid]["event_date"], "source_event_id": event["id"],
                    "source_url": stats_url, "source_response_sha256": hashes[str(probes / 'requests' / f'{hashlib.sha256(stats_url.encode()).hexdigest()}.json')],
                    "observed_at_utc": saved[stats_url]["observed_at_utc"]})
        record = {**match, "cito_bout_id": pid, "cito_fighters": bout["fighters"],
                  "cito_result": {k: bout.get(k) for k in ("method", "resultRound", "resultTime")},
                  "card_manifest_sha256": None}
        result = result_record(record)
        # These scoped source responses use uppercase labels. Preserve the raw
        # differences, but case alone is not a change in result classification.
        unresolved = [d for d in result["unresolved_differences"] if not (
            d["field"] == "method" and isinstance(d["cito"], str)
            and isinstance(d["historical"], str) and d["cito"].casefold() == d["historical"].casefold())]
        result["unresolved_differences"] = unresolved
        result["resolution"] = "requires_result_review" if unresolved else "historical_result_verified"
        result["current_result"] = None if unresolved else result["frozen_result"]
        result.update(source_url=stats_url, observed_at_utc=saved[stats_url]["observed_at_utc"],
                      source_response_sha256=new_rounds[-1]["source_response_sha256"])
        matches.append(result)
        if result["unresolved_differences"]:
            review.append(result)
    current_rounds, current_totals = [], []
    current = {r["cito_bout_id"]: r for r in brows["bout_matches.jsonl"] if r["status"] == "post_snapshot"}
    for bid in sorted(CURRENT_MISSING_TOTALS):
        record = current[bid]
        url = f"{BASE_URL}/bouts/{bid}/stats"
        payload = _data(saved, url)
        if payload["boutStats"]:
            raise ValueError("Provider now has current totals; review them rather than silently deriving.")
        if record["total_rows"] != 0 or record["cito_status"] != "completed":
            raise ValueError("Current derived-total target is not the reviewed completed gap.")
        normalized, derived = reconcile_rounds({"id": bid, "fighters": record["cito_fighters"]},
            payload["roundStats"], expected_rounds=record["cito_result"]["resultRound"])
        staged = [r for r in brows["round_stats_staged.jsonl"]
                  if r["source_bout_id"] == bid and r["card_manifest_sha256"] == record["card_manifest_sha256"]]
        fields = list(_numbers(payload["roundStats"][0]))
        signature = lambda rows, fields=fields: sorted((r["source_fighter_id"], r["round_number"], r["source_round_stat_id"],
                                         tuple(r[f] for f in fields)) for r in rows)
        if signature(staged) != signature(normalized):
            raise ValueError("Current probe rounds differ from archived card rounds.")
        evidence = {"source_url": url, "observed_at_utc": saved[url]["observed_at_utc"],
                    "source_response_sha256": hashes[str(probes / 'requests' / f'{hashlib.sha256(url.encode()).hexdigest()}.json')],
                    "card_manifest_sha256": record["card_manifest_sha256"],
                    "event_date": record["event"].split("/")[0], "training_ready": False}
        for batch, target in ((normalized, current_rounds), (derived, current_totals)):
            target.extend({**row, **evidence, "upset_fighter_id": links.get(row["source_fighter_id"])} for row in batch)
    remaining = [r for r in history if r["source_bout_id"] not in existing_bids | set(ROAD_ALIASES)]
    issues = {"historical_bouts_without_verified_rounds": remaining,
              "historical_missing_endpoint_evidence": [r for r in report["requests"] if
                  r["reason"] in {f"historical_bout_missing_stats:{h['source_bout_id']}" for h in remaining}],
              "current_bouts_without_provider_totals": sorted(CURRENT_MISSING_TOTALS),
              "result_metadata_requires_review": review,
              "probe_http_statuses": dict(Counter(str(r["http_status"]) for r in report["requests"])),
              "note": "Returned row count includes rounds; it does not establish fight-total availability."}
    summary = {"schema_version": 1, "status": "offline gap supplement exported",
               "historical_bouts_added": len(matches), "historical_round_rows_added": len(new_rounds),
               "combined_historical_bouts": base["historical_bouts"] + len(matches),
               "combined_historical_round_rows": base["historical_round_rows"] + len(new_rounds),
               "historical_bouts_without_verified_rounds": len(remaining),
               "new_registry_links": len(additions), "derived_current_total_rows": len(current_totals),
               "current_round_rows": len(current_rounds), "result_metadata_requires_review": len(review),
               "api_calls": 0, "coverage_verified": False, "training_ready": False,
               "input_sha256": hashes}
    if any(_digest(Path(path)) != digest for path, digest in hashes.items()):
        raise ValueError("Input changed during gap reconciliation.")
    output.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=output.parent, prefix=".upset-gap-reconciliation-") as temporary:
        folder = Path(temporary) / "export"
        folder.mkdir()
        for name, rows in (("historical_rounds_additional.jsonl", new_rounds), ("historical_bout_results.jsonl", matches),
                           ("current_rounds_staged.jsonl", current_rounds), ("current_totals_derived.jsonl", current_totals)):
            _write_verified(folder / name, rows)
        save_fighter_registry(FighterRegistry(registry.identities, (*registry.provider_links, *additions)),
                              folder / "fighter_registry.json")
        (folder / "provider_issues.json").write_text(json.dumps(issues, indent=2, sort_keys=True) + "\n")
        summary["output_sha256"] = {p.name: _digest(p) for p in folder.iterdir()}
        (folder / "manifest.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
        folder.rename(output)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--accepted", type=Path, default=Path("data/processed/cito_historical_rounds_v1"))
    parser.add_argument("--bridge", type=Path, default=Path("data/processed/cito_archive_bridge_v2"))
    parser.add_argument("--historical", type=Path, default=Path("data/processed/kaggle_ufc_1994_2026/identified"))
    parser.add_argument("--probes", type=Path, default=Path("data/raw/cito_archive/gap_probes_v1"))
    parser.add_argument("--output", type=Path, default=Path("data/processed/cito_gap_reconciliation_v1"))
    args = parser.parse_args()
    try:
        result = reconcile_gaps(args.accepted, args.bridge, args.historical, args.probes, args.output)
    except (OSError, ValueError, KeyError, TypeError, StopIteration) as error:
        parser.error(str(error))
    print(json.dumps({k: v for k, v in result.items() if not k.endswith("sha256")}, indent=2))
    print(f"Saved to: {args.output}")


if __name__ == "__main__":
    main()
