"""Reviewed bout identities do not depend on provider round availability."""

import json
from copy import deepcopy

import pytest
from test_research_app import A, build, fixture, write_rows

from upset.data.collect_cito_archive import _digest
from upset.data.identity import (
    FighterRegistry,
    load_fighter_registry,
    save_fighter_registry,
)
from upset.data.integrate_cito_history_identities import history_evidence, integrate


def prepare(root):
    paths = fixture(root)
    historical, current, registry_path, _accepted = paths[:4]
    registry = load_fighter_registry(registry_path)
    registry = FighterRegistry(registry.identities, tuple(r for r in registry.provider_links
                                                        if (r.provider, r.provider_fighter_id) != ("cito", "cito-a")))
    save_fighter_registry(registry, registry_path, overwrite=True)
    frozen = json.loads((historical / "fights_identified.jsonl").read_text())
    rule = {"name": "Alex Silva", "cito_fighter_id": "cito-a", "ufcstats_fighter_id": "hist-a",
            "historical_bout_id": "old", "cito_bout_id": "alias-old", "event_date": "2026-03-07",
            "opponent_cito_id": "cito-b"}
    history = [{"fighterName": "Alex Silva", "opponent": {"name": "Sam"},
                "event": {"eventDate": "2026-03-07"}, "outcome": "win", "isCompleted": True,
                "bout": {"id": "alias-old", "status": "completed", "method": "U-DEC",
                         "resultRound": 3, "resultTime": "5:00", "hasStats": False}}]
    old_identified = current / "identified/fights_identified.jsonl"
    canonical = [json.loads(line) for line in old_identified.read_text().splitlines()]
    for r in canonical:
        r.pop("upset_fighter_1_id")
        r.pop("upset_fighter_2_id")
    canonical_stats = [json.loads(line) for line in (current / "identified/fight_stats_identified.jsonl").read_text().splitlines()]
    for r in canonical_stats:
        r.pop("upset_fighter_id")
    write_rows(current / "fights.jsonl", canonical)
    write_rows(current / "fight_stats.jsonl", canonical_stats)
    write_rows(current / "rounds_staged.jsonl", [{"source_fighter_id": "cito-a", "upset_fighter_id": None}])
    write_rows(current / "bout_provenance.jsonl", [{"source_bout_id": "new", "basis": "fixture"}])
    write_rows(old_identified, [])
    write_rows(current / "identified/fight_stats_identified.jsonl", [])
    (current / "review.json").write_text(json.dumps({"bout_validation_issues": [],
        "unresolved_fighter_identities": [{"cito_fighter_id": "cito-a", "name_only_candidates": [{"upset_fighter_id": A}]}]}))
    cm = json.loads((current / "manifest.json").read_text())
    cm.update(identified_current_bouts=0, bouts_awaiting_identity_review=1, unresolved_provider_fighters=1)
    cm["identified_subset_manifest"]["input_sha256"]["registry"] = _digest(registry_path)
    cm["output_sha256"] = {str(p.relative_to(current)): _digest(p) for p in current.rglob("*") if p.is_file() and p.name != "manifest.json"}
    (current / "manifest.json").write_text(json.dumps(cm))
    bundles = root / "bundles"
    history_path = bundles / "fighters/cito-a/fights.json"
    history_path.parent.mkdir(parents=True)
    history_path.write_text(json.dumps({"http_status": 200, "expected_cito_fighter_id": "cito-a",
        "observed_at_utc": "2026-10-01T00:00:00Z", "source_url": "https://example.org/fighters/alex/fights",
        "response": {"data": history}}))
    review = root / "review"
    review.mkdir()
    write_rows(review / "identity_review.jsonl", [{"cito_fighter_id": "cito-a"}])
    (review / "manifest.json").write_text(json.dumps({"identity_links_added": 0,
        "input_sha256": {str(p): _digest(p) for p in (current / "manifest.json", registry_path, history_path)},
        "output_sha256": {"identity_review.jsonl": _digest(review / "identity_review.jsonl")}}))
    return paths, review, bundles, rule, history, frozen


def run(prepared, output):
    paths, review, bundles, rule, _, _ = prepared
    return integrate(paths[1], review, bundles, paths[0] / "fights_identified.jsonl", paths[2], output,
                     expected_history=paths[4], rules=(rule,))


def test_missing_rounds_do_not_block_reviewed_history_link_and_database(tmp_path):
    prepared = prepare(tmp_path)
    before = {p: p.read_bytes() for p in tmp_path.rglob("*.json*")}
    output = tmp_path / "integrated"
    result = run(prepared, output)
    assert result["identity_links_added"] == result["newly_identified_bouts"] == 1
    assert result["identified_current_bouts"] == 1 and result["unresolved_provider_fighters"] == 0
    assert result["api_calls"] == 0 and result["training_ready"] is False
    assert run(prepared, output) == result
    assert all(p.read_bytes() == value for p, value in before.items())
    assert json.loads((output / "rounds_staged.jsonl").read_text())["upset_fighter_id"] == A
    paths = prepared[0]
    build_paths = (paths[0], output, output / "fighter_registry.json", paths[3], paths[4], paths[5])
    assert build(build_paths, tmp_path / "research")["total_bouts"] == 2


@pytest.mark.parametrize("field,value", [("resultTime", "4:59"), ("resultRound", 2), ("method", "SUB")])
def test_result_clock_and_method_conflicts_do_not_create_links(tmp_path, field, value):
    paths, _, _, rule, history, frozen = prepare(tmp_path)
    changed = deepcopy(history)
    changed[0]["bout"][field] = value
    with pytest.raises(ValueError, match="date, matchup or result differs"):
        history_evidence(rule, changed, [frozen], load_fighter_registry(paths[2]))


def test_known_opponent_and_unique_bout_evidence_are_required(tmp_path):
    paths, _, _, rule, history, frozen = prepare(tmp_path)
    registry = load_fighter_registry(paths[2])
    with pytest.raises(ValueError, match="Missing or duplicate"):
        history_evidence(rule, history * 2, [frozen], registry)
    with pytest.raises(ValueError, match="opponent or historical identity differs"):
        history_evidence(dict(rule, opponent_cito_id="unknown"), history, [frozen], registry)
    for key, value in (("outcome", "loss"), ("fighterName", "Namesake")):
        changed = deepcopy(history)
        changed[0][key] = value
        with pytest.raises(ValueError, match="date, matchup or result differs"):
            history_evidence(rule, changed, [frozen], registry)
    changed = deepcopy(history)
    changed[0]["event"]["eventDate"] = "2026-03-06"
    with pytest.raises(ValueError, match="date, matchup or result differs"):
        history_evidence(rule, changed, [frozen], registry)


def test_source_tampering_and_existing_output_changes_fail_closed(tmp_path):
    prepared = prepare(tmp_path)
    output = tmp_path / "integrated"
    run(prepared, output)
    (output / "identity_link_evidence.jsonl").write_text("changed")
    with pytest.raises(ValueError, match="Export hash differs"):
        run(prepared, output)
    history = prepared[2] / "fighters/cito-a/fights.json"
    history.write_text(history.read_text() + " ")
    with pytest.raises(ValueError, match="Profile review input hash differs"):
        run(prepared, tmp_path / "unpublished")
    assert not (tmp_path / "unpublished").exists()
