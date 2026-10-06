"""Current public identity anchors are separate from outcome verification."""

import json
from copy import deepcopy

import pytest
from test_integrate_cito_history_identities import prepare
from test_research_app import A, build, write_rows

from upset.data.collect_cito_archive import _digest
from upset.data.identity import load_fighter_registry
from upset.data.integrate_cito_matchup_identities import integrate, matchup_evidence


def setup(root):
    paths, review, bundles, _, history, _ = prepare(root)
    current = paths[1]
    (current / "fighter_registry.json").write_bytes(paths[2].read_bytes())
    write_rows(current / "identity_link_evidence.jsonl", [{"basis": "previous link preserved"}])
    queue = json.loads((current / "review.json").read_text())
    queue["unresolved_fighter_identities"][0]["name_only_candidates"][0]["ufcstats_fighter_ids"] = ["hist-a"]
    (current / "review.json").write_text(json.dumps(queue))
    rule = {"name": "Alex Silva", "cito_fighter_id": "cito-a", "ufcstats_fighter_id": "hist-a",
            "bout_id": "new", "event_date": "2026-09-20", "opponent_name": "Sam",
            "opponent_cito_id": "cito-b", "opponent_ufcstats_id": "hist-b",
            "public_profile_url": "https://ufcstats.com/fighter-details/hist-a",
            "public_bout_url": "https://ufcstats.com/fight-details/new"}
    history[0]["bout"]["id"] = "new"
    history[0]["event"]["eventDate"] = "2026-09-20"
    history_path = bundles / "fighters/cito-a/fights.json"
    wrapper = json.loads(history_path.read_text())
    wrapper["response"]["data"] = history
    history_path.write_text(json.dumps(wrapper))
    rm = json.loads((review / "manifest.json").read_text())
    rm["input_sha256"][str(history_path)] = _digest(history_path)
    (review / "manifest.json").write_text(json.dumps(rm))
    cm = json.loads((current / "manifest.json").read_text())
    cm["input_sha256"] = {str(review / "manifest.json"): _digest(review / "manifest.json")}
    cm["output_sha256"] = {str(p.relative_to(current)): _digest(p) for p in current.rglob("*") if p.is_file() and p != current / "manifest.json"}
    (current / "manifest.json").write_text(json.dumps(cm))
    return paths, review, bundles, rule, history, queue


def run(prepared, output):
    paths, review, bundles, rule, *_ = prepared
    return integrate(paths[1], review, bundles, paths[0] / "fights_identified.jsonl", output,
                     rules=(rule,), expected_history=paths[4])


def test_matchup_link_preserves_prior_evidence_sources_and_research_compatibility(tmp_path):
    prepared = setup(tmp_path)
    before = {p: p.read_bytes() for p in tmp_path.rglob("*.json*")}
    output = tmp_path / "linked"
    report = run(prepared, output)
    assert report["identity_links_added"] == report["newly_identified_bouts"] == 1
    assert report["identified_current_bouts"] == 1
    assert report["unresolved_provider_fighters"] == 0
    assert report["api_calls"] == 0 and report["training_ready"] is False
    assert all(p.read_bytes() == value for p, value in before.items())
    evidence = [json.loads(l) for l in (output / "identity_link_evidence.jsonl").read_text().splitlines()]
    assert evidence[0] == {"basis": "previous link preserved"}
    assert evidence[1]["upset_fighter_id"] == A
    assert evidence[1]["public_evidence_is_result_verification"] is False
    assert run(prepared, output) == report
    paths = prepared[0]
    assert build((paths[0], output, output / "fighter_registry.json", paths[3], paths[4], paths[5]),
                 tmp_path / "research")["total_bouts"] == 2


@pytest.mark.parametrize("field,value", [("event_date", "2026-09-19"), ("opponent_name", "Namesake"),
                                        ("opponent_cito_id", "unknown")])
def test_wrong_date_or_opponent_does_not_create_link(tmp_path, field, value):
    paths, _, _, rule, history, queue = setup(tmp_path)
    canonical = [json.loads(l) for l in (paths[1] / "fights.jsonl").read_text().splitlines()]
    with pytest.raises(ValueError, match="differs"):
        matchup_evidence(dict(rule, **{field: value}), canonical, queue["unresolved_fighter_identities"][0],
                         history, load_fighter_registry(paths[2]))


def test_candidate_id_and_duplicate_history_must_match(tmp_path):
    paths, _, _, rule, history, queue = setup(tmp_path)
    canonical = [json.loads(l) for l in (paths[1] / "fights.jsonl").read_text().splitlines()]
    q = queue["unresolved_fighter_identities"][0]
    registry = load_fighter_registry(paths[2])
    with pytest.raises(ValueError, match="Missing or duplicate"):
        matchup_evidence(rule, canonical, q, history * 2, registry)
    wrong = deepcopy(q)
    wrong["name_only_candidates"][0]["ufcstats_fighter_ids"] = ["hist-c"]
    with pytest.raises(ValueError, match="candidate differs"):
        matchup_evidence(rule, canonical, wrong, history, registry)


def test_input_and_output_tampering_fail_before_new_stage(tmp_path):
    prepared = setup(tmp_path)
    output = tmp_path / "linked"
    run(prepared, output)
    (output / "identity_link_evidence.jsonl").write_text("changed")
    with pytest.raises(ValueError, match="Export hash differs"):
        run(prepared, output)
    history = prepared[2] / "fighters/cito-a/fights.json"
    history.write_text(history.read_text() + " ")
    with pytest.raises(ValueError, match="history hash differs"):
        run(prepared, tmp_path / "bad")
    assert not (tmp_path / "bad").exists()
