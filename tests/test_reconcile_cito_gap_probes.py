"""Offline supplements preserve snapshots and reject inconsistent source evidence."""

import hashlib
import json
from copy import deepcopy

import pytest
from test_reconcile_cito_archive import _bout, _history_rows, _prepare, _raw, _run

from upset.data.collect_cito_archive import _digest
from upset.data.collect_cito_card import BASE_URL
from upset.data.export_cito_archive_rounds import export_rounds
from upset.data.reconcile_cito_gap_probes import (
    CURRENT_MISSING_TOTALS,
    ROAD_ALIASES,
    ROAD_CANONICAL_SLUG,
    ROAD_SLUG,
    _bout_witnesses,
    read_probes,
    reconcile_gaps,
    reconcile_rounds,
)


def _json(path, value):
    path.write_text(json.dumps(value, sort_keys=True))


def _fixture(tmp_path):
    root, historical, registry = _prepare(tmp_path)
    road_bouts, road_totals, road_rounds = [], [], []
    fight, stats = _history_rows()
    for i, (hid, pid) in enumerate(ROAD_ALIASES.items()):
        h = {**fight, "source_bout_id": hid, "event_date": "2025-08-22"}
        with (historical / "fights_identified.jsonl").open("a") as f:
            f.write(json.dumps(h) + "\n")
        with (historical / "fight_stats_identified.jsonl").open("a") as f:
            for s in stats.values():
                f.write(json.dumps({**s, "source_bout_id": hid, "knockdowns": i}) + "\n")
        bout = _bout(pid)
        bout["eventSlug"] = ROAD_CANONICAL_SLUG
        for fighter in bout["fighters"]:
            fighter["fighterId"] = fighter["fighterId"].replace("cito-", "road-")
        road_bouts.append(bout)
        for name, slug in (("Alex", "alex"), ("Sam", "sam")):
            road_totals.append({**_raw(name, slug, bout_id=pid, control="--"), "knockdowns": i})
            road_rounds.append({**_raw(name, slug, bout_id=pid, round_number=1, control="--"), "knockdowns": i})
    bridge = tmp_path / "bridge"
    _run((root, historical, registry), bridge)
    # Include synthetic post-snapshot gaps in the staged bridge.
    current_payloads = {}
    for bid in CURRENT_MISSING_TOTALS:
        bout = _bout(bid)
        raw = [_raw(name, slug, bout_id=bid, round_number=1, control="--")
               for name, slug in (("Alex", "alex"), ("Sam", "sam"))]
        rows, _ = reconcile_rounds(bout, raw, expected_rounds=1)
        with (bridge / "bout_matches.jsonl").open("a") as f:
            f.write(json.dumps({"cito_bout_id": bid, "status": "post_snapshot", "total_rows": 0,
                "round_rows": 2, "cito_status": "completed", "cito_has_stats": True, "candidates": [],
                "cito_fighters": bout["fighters"], "cito_result": {"resultRound": 1},
                "event": "2026-09-12/ufc-test/event-current", "card_manifest_sha256": "current-card"}) + "\n")
        with (bridge / "round_stats_staged.jsonl").open("a") as f:
            for r in rows:
                f.write(json.dumps({**r, "card_manifest_sha256": "current-card"}) + "\n")
        current_payloads[f"{BASE_URL}/bouts/{bid}/stats"] = {"boutStats": [], "roundStats": raw}
    bm = json.loads((bridge / "manifest.json").read_text())
    bm["output_sha256"] = {n: _digest(bridge / n) for n in bm["output_sha256"]}
    _json(bridge / "manifest.json", bm)
    accepted = tmp_path / "accepted"
    expected = _digest(historical / "fights_identified.jsonl")
    export_rounds(bridge, historical, registry, root, accepted, expected_history_sha256=expected)
    plan_path = accepted / "gap_probe_plan.json"
    plan = json.loads(plan_path.read_text())
    for endpoint in ("bouts", "stats"):
        plan["requests"].append({"scope": "events", "identifier": ROAD_SLUG, "endpoint": endpoint,
            "reason": "failed_event_near_missing_historical_bouts", "source_url": f"{BASE_URL}/events/{ROAD_SLUG}/{endpoint}"})
    _json(plan_path, plan)
    base = json.loads((accepted / "manifest.json").read_text())
    base["output_sha256"]["gap_probe_plan.json"] = _digest(plan_path)
    _json(accepted / "manifest.json", base)
    data = {"event": {"id": "road-event", "slug": ROAD_CANONICAL_SLUG, "eventDate": "2025-08-22"},
            "bouts": road_bouts, "boutStats": road_totals, "roundStats": road_rounds}
    payloads = {**current_payloads, f"{BASE_URL}/events/{ROAD_SLUG}/bouts": road_bouts,
                f"{BASE_URL}/events/{ROAD_SLUG}/stats": data}
    for hid, pid in ROAD_ALIASES.items():
        totals = [r for r in road_totals if r["boutId"] == pid]
        rounds = [r for r in road_rounds if r["boutId"] == pid]
        payloads[f"{BASE_URL}/bouts/{hid}/stats"] = {"boutStats": totals, "roundStats": rounds}
        payloads[f"{BASE_URL}/bouts/{hid}/rounds"] = rounds
    probes = tmp_path / "probes"
    (probes / "requests").mkdir(parents=True)
    requests = []
    for target in plan["requests"]:
        url = target["source_url"]
        path = probes / "requests" / f"{hashlib.sha256(url.encode()).hexdigest()}.json"
        _json(path, {"source": "cito", "source_url": url, "plan_sha256": _digest(plan_path),
                    "observed_at_utc": "2026-10-01T02:30:00Z", "http_status": 200,
                    "response": {"data": payloads[url]}})
        requests.append({"source_url": url, "raw_sha256": _digest(path), "http_status": 200,
                         "reason": target["reason"]})
    _json(probes / "report.json", {"schema_version": 1, "plan_sha256": _digest(plan_path), "requests": requests})
    return accepted, bridge, historical, probes, expected


def _run_export(paths, output):
    return reconcile_gaps(*paths[:4], output, expected_history_sha256=paths[4])


def _rewrite_response(paths, url, change):
    probes = paths[3]
    p = probes / "requests" / f"{hashlib.sha256(url.encode()).hexdigest()}.json"
    wrapper = json.loads(p.read_text())
    change(wrapper["response"]["data"])
    _json(p, wrapper)
    report = json.loads((probes / "report.json").read_text())
    next(r for r in report["requests"] if r["source_url"] == url)["raw_sha256"] = _digest(p)
    _json(probes / "report.json", report)


def test_offline_supplement_checks_historical_sums_and_preserves_derived_missingness(tmp_path):
    paths = _fixture(tmp_path)
    before = {p: p.read_bytes() for p in tmp_path.rglob("*.json*")}
    output = tmp_path / "supplement"
    result = _run_export(paths, output)
    assert result["historical_bouts_added"] == 2
    assert result["historical_round_rows_added"] == 4
    assert result["combined_historical_bouts"] == 3
    assert result["historical_bouts_without_verified_rounds"] == 0
    assert result["new_registry_links"] == 2
    assert result["derived_current_total_rows"] == 4
    assert result["api_calls"] == 0 and result["training_ready"] is False
    totals = [json.loads(line) for line in (output / "current_totals_derived.jsonl").read_text().splitlines()]
    assert all(r["provider_fight_totals_present"] is False and r["control_seconds"] is None for r in totals)
    assert all(p.read_bytes() == b for p, b in before.items())
    assert _run_export(paths, output) == result
    (output / "current_totals_derived.jsonl").write_text("changed")
    with pytest.raises(ValueError, match="Existing reconciliation differs"):
        _run_export(paths, output)


@pytest.mark.parametrize("change", [
    lambda d: d["roundStats"].pop(),
    lambda d: d["roundStats"].append(deepcopy(d["roundStats"][0])),
    lambda d: d["roundStats"][0].update(boutId="wrong-bout"),
    lambda d: d["roundStats"][0].update(knockdowns=1),
])
def test_changed_current_rounds_and_incomplete_coverage_are_rejected(tmp_path, change):
    paths = _fixture(tmp_path)
    _rewrite_response(paths, f"{BASE_URL}/bouts/12979/stats", change)
    with pytest.raises(ValueError, match="coverage|duplicate|differ"):
        _run_export(paths, tmp_path / "out")
    assert not (tmp_path / "out").exists()


def test_hash_tampering_wrong_alias_and_changed_historical_sums_are_rejected(tmp_path):
    paths = _fixture(tmp_path)
    p = next((paths[3] / "requests").glob("*.json"))
    original = p.read_bytes()
    p.write_bytes(original + b" ")
    with pytest.raises(ValueError, match="hash differs"):
        read_probes(paths[3], paths[0] / "gap_probe_plan.json")
    p.write_bytes(original)
    _rewrite_response(paths, f"{BASE_URL}/events/{ROAD_SLUG}/stats", lambda d: d["event"].update(slug="wrong"))
    with pytest.raises(ValueError, match="event alias"):
        _run_export(paths, tmp_path / "out")


def test_round_sum_validation_checks_fields_absent_from_historical_totals():
    bout = _bout()
    totals = [_raw("Alex", "alex"), _raw("Sam", "sam")]
    rounds = [_raw("Alex", "alex", round_number=1), _raw("Sam", "sam", round_number=1)]
    totals[0]["reversals"] = 1
    with pytest.raises(ValueError, match="round sums: reversals"):
        reconcile_rounds(bout, rounds, expected_rounds=1, expected_totals=totals)


def test_nested_round_order_is_irrelevant_but_values_and_result_fields_are_checked():
    left = _bout()
    left["roundStats"] = [_raw("Alex", "alex", round_number=1), _raw("Sam", "sam", round_number=1)]
    right = deepcopy(left)
    right["roundStats"].reverse()
    assert _bout_witnesses([left]) == _bout_witnesses([right])
    right["roundStats"][0]["knockdowns"] = 1
    assert _bout_witnesses([left]) != _bout_witnesses([right])
    right = deepcopy(left)
    right["resultTime"] = "4:59"
    assert _bout_witnesses([left]) != _bout_witnesses([right])


def test_paired_historical_totals_recheck_is_independent_of_report_hashes(tmp_path):
    paths = _fixture(tmp_path)
    # Change all agreeing provider endpoints; the historical snapshot still catches it.
    pid = next(iter(ROAD_ALIASES.values()))
    hid = next(iter(ROAD_ALIASES))
    for endpoint in ("stats", "rounds"):
        def change(d, endpoint=endpoint):
            if endpoint == "rounds":
                for row in d:
                    row["knockdowns"] = 4
            else:
                for key in ("boutStats", "roundStats"):
                    for row in d[key]:
                        row["knockdowns"] = 4
        _rewrite_response(paths, f"{BASE_URL}/bouts/{hid}/{endpoint}", change)
    def change_event(d):
        for key in ("boutStats", "roundStats"):
            for row in d[key]:
                if row["boutId"] == pid:
                    row["knockdowns"] = 4
    _rewrite_response(paths, f"{BASE_URL}/events/{ROAD_SLUG}/stats", change_event)
    with pytest.raises(ValueError, match="paired totals or identity not verified"):
        _run_export(paths, tmp_path / "out")
