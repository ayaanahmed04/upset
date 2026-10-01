"""Round acceptance independently checks joins, coverage, sums and immutable inputs."""

import json
from copy import deepcopy

import pytest
from test_reconcile_cito_archive import A, B, _prepare, _run

from upset.data.collect_cito_archive import _digest
from upset.data.export_cito_archive_rounds import (
    export_rounds,
    gap_plan,
    read_bridge,
    result_record,
    reuse_export,
    select_verified_rounds,
)
from upset.data.identity import load_fighter_registry


def _bridge(tmp_path):
    root, historical, registry = _prepare(tmp_path)
    bridge = tmp_path / "bridge"
    _run((root, historical, registry), bridge)
    return bridge, historical, registry, root


def _export(paths, output):
    return export_rounds(*paths, output,
                        expected_history_sha256=_digest(paths[1] / "fights_identified.jsonl"))


def test_exports_complete_linked_rounds_and_separate_registry_without_changing_inputs(tmp_path):
    paths = _bridge(tmp_path)
    before = {p: p.read_bytes() for p in tmp_path.rglob("*.json*")}
    output = tmp_path / "accepted"
    summary = _export(paths, output)
    assert summary["historical_bouts"] == 1
    assert summary["historical_round_rows"] == 2
    assert summary["new_registry_links"] == 2
    assert summary["round_rows_with_unavailable_control"] == 2
    assert summary["api_calls"] == 0
    assert summary["training_ready"] is False
    rows = [json.loads(line) for line in (output / "round_stats_identified.jsonl").read_text().splitlines()]
    assert {r["upset_fighter_id"] for r in rows} == {A, B}
    assert all(r["historical_bout_id"] == "history-bout" for r in rows)
    assert all(r["event_date"] == "2024-04-27" and r["control_seconds"] is None for r in rows)
    extended = load_fighter_registry(output / "fighter_registry.json")
    assert {(link.provider_fighter_id, link.upset_fighter_id) for link in extended.provider_links
            if link.provider == "cito"} == {("cito-a", A), ("cito-b", B)}
    assert all(p.read_bytes() == content for p, content in before.items())
    assert all(_digest(output / name) == digest for name, digest in summary["output_sha256"].items())
    assert reuse_export(output, *paths) == summary
    with pytest.raises(ValueError, match="Output exists"):
        _export(paths, output)


def test_bridge_tampering_and_changed_source_inputs_are_rejected(tmp_path):
    paths = _bridge(tmp_path)
    paths[2].write_text(paths[2].read_text() + " ")
    with pytest.raises(ValueError, match="inputs differ"):
        _export(paths, tmp_path / "out")
    raw = paths[0] / "round_stats_staged.jsonl"
    raw.write_text(raw.read_text() + " ")
    with pytest.raises(ValueError, match="Bridge hash differs"):
        read_bridge(paths[0])


def test_round_sum_recheck_rejects_self_consistent_but_incorrect_bridge_hash(tmp_path):
    paths = _bridge(tmp_path)
    raw = paths[0] / "round_stats_staged.jsonl"
    rows = [json.loads(line) for line in raw.read_text().splitlines()]
    rows[0]["knockdowns"] = 1
    raw.write_text("".join(json.dumps(r) + "\n" for r in rows))
    manifest_path = paths[0] / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["output_sha256"][raw.name] = _digest(raw)
    manifest_path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="round sums differ"):
        _export(paths, tmp_path / "out")
    assert not (tmp_path / "out").exists()


def test_conflicting_links_incomplete_rounds_and_duplicate_bouts_are_rejected(tmp_path):
    paths = _bridge(tmp_path)
    _manifest, rows = read_bridge(paths[0])
    registry = load_fighter_registry(paths[2])
    changed = deepcopy(rows)
    changed["fighter_link_proposals.jsonl"][0]["candidates"][0]["upset_fighter_id"] = B
    with pytest.raises(ValueError, match="Fighter proposals differ"):
        select_verified_rounds(changed, registry)
    changed = deepcopy(rows)
    changed["round_stats_staged.jsonl"].pop()
    with pytest.raises(ValueError, match="round coverage differs"):
        select_verified_rounds(changed, registry)
    changed = deepcopy(rows)
    changed["bout_matches.jsonl"].append(changed["bout_matches.jsonl"][0])
    with pytest.raises(ValueError, match="Duplicate provider bout"):
        select_verified_rounds(changed, registry)


def test_result_revisions_stay_separate_and_unreviewed_changes_have_no_current_label(tmp_path):
    paths = _bridge(tmp_path)
    _manifest, rows = read_bridge(paths[0])
    match = rows["bout_matches.jsonl"][0]
    match["reviewed_current_result"] = {"outcome": "no_contest", "winner_upset_fighter_id": None,
                                        "revision_effective_date": None}
    record = result_record(match)
    assert record["resolution"] == "reviewed_amendment"
    assert record["current_result"]["winner_upset_fighter_id"] is None
    assert record["frozen_result"]["winner_upset_fighter_id"] == A
    del match["reviewed_current_result"]
    match["metadata_differences"] = [{"field": "method", "cito": "Decision - Majority", "historical": "Overturned"}]
    record = result_record(match)
    assert record["current_result"] is None
    assert record["resolution"] == "requires_result_review"
    match["metadata_differences"] = [{"field": "method", "cito": "KO/TKO", "historical": "TKO - Doctor's Stoppage"}]
    assert result_record(match)["resolution"] == "historical_result_verified"


def test_gap_plan_targets_missing_rows_including_failed_other_competition():
    rows = {"bout_matches.jsonl": [
        {"cito_bout_id": "12315", "status": "candidate_requires_review", "total_rows": 0, "round_rows": 0,
         "cito_has_stats": False, "candidates": [{"historical_bout_id": "history-a"}]},
        {"cito_bout_id": "12979", "status": "post_snapshot", "total_rows": 0, "round_rows": 2,
         "cito_has_stats": True, "candidates": []}],
        "historical_without_verified_totals.jsonl": [
            {"source_bout_id": "history-a", "event_date": "2025-09-06"},
            {"source_bout_id": "history-b", "event_date": "2025-08-22"}]}
    event = {"event_date": "2025-08-21", "slug": "ufc-road-to-ufc-4-6", "provider_event_id": "event-1"}
    key = "2025-08-21/ufc-road-to-ufc-4-6/event-1"
    plan = gap_plan(rows, {"events": [event]}, {"cards": {key: {"status": "failed"}}})
    assert plan["primary_requests"] == 7
    assert plan["maximum_requests_including_fallbacks"] == 9
    assert sum(r["scope"] == "events" for r in plan["requests"]) == 2
    assert sum(r.get("fallback_identifier") == "history-a" for r in plan["requests"]) == 2
