"""Current archive normalization preserves provenance and never links by name."""

import json
from copy import deepcopy
from datetime import UTC, datetime

import pytest
from test_collect_cito_card import Response
from test_reconcile_cito_archive import A, _bout, _prepare, _raw, _run

from upset.data.collect_cito_archive import _digest
from upset.data.collect_cito_card import collect_card
from upset.data.export_cito_archive_rounds import export_rounds
from upset.data.export_cito_current_archive import (
    export_current,
    normalize_completed_bout,
)
from upset.data.reconcile_cito_gap_probes import reconcile_rounds

NOW = datetime(2026, 10, 1, 3, tzinfo=UTC)


def _sample(bid="current", *, unknown=False):
    bout = _bout(bid)
    bout["eventSlug"] = "ufc-current"
    bout["winnerFighterSlug"] = "alex"
    if unknown:
        bout["fighters"][0]["fighterId"] = "unknown-a"
        bout["fighters"][0]["profile"] = {"name": "Alex", "id": "unknown-a"}
    event = {"id": "event-current", "slug": "ufc-current", "eventDate": "2026-03-14",
             "status": "completed", "hasStats": True}
    totals = [_raw(name, slug, bout_id=bid, control="--") for name, slug in (("Alex", "alex"), ("Sam", "sam"))]
    rounds = [_raw(name, slug, bout_id=bid, round_number=1, control="--")
              for name, slug in (("Alex", "alex"), ("Sam", "sam"))]
    return bout, event, totals, rounds


def _fixture(tmp_path, monkeypatch):
    root, historical, registry = _prepare(tmp_path)
    first, event, totals_a, rounds_a = _sample("known")
    second, _, totals_b, rounds_b = _sample("unknown", unknown=True)
    event["bouts"] = [first, second]
    payloads = [{"data": event}, {"data": [first, second]}, {"data": {
        "event": event, "bouts": [first, second], "boutStats": totals_a + totals_b,
        "roundStats": rounds_a + rounds_b}}]
    responses = iter(payloads)
    card = root / "cards/ufc-current"
    collect_card("ufc-current", card, "secret", lambda *a, **k: Response(next(responses)), delay=0)
    inventory_path = root / "inventory/manifest.json"
    inventory = json.loads(inventory_path.read_text())
    inventory["events"].append({"provider_event_id": event["id"], "slug": event["slug"],
                                 "event_date": event["eventDate"], "has_stats": True})
    inventory_path.write_text(json.dumps(inventory))
    progress_path = root / "collection_progress.json"
    progress = json.loads(progress_path.read_text())
    progress["inventory_sha256"] = _digest(inventory_path)
    progress["cards"]["2026-03-14/ufc-current/event-current"] = {
        "status": "captured", "card_manifest_sha256": _digest(card / "manifest.json")}
    progress_path.write_text(json.dumps(progress))
    bridge = tmp_path / "bridge"
    _run((root, historical, registry), bridge)
    accepted = tmp_path / "accepted"
    expected = _digest(historical / "fights_identified.jsonl")
    export_rounds(bridge, historical, registry, root, accepted, expected_history_sha256=expected)
    supplement = tmp_path / "supplement"
    supplement.mkdir()
    (supplement / "fighter_registry.json").write_bytes((accepted / "fighter_registry.json").read_bytes())
    (supplement / "current_totals_derived.jsonl").write_text("")
    (supplement / "manifest.json").write_text(json.dumps({"schema_version": 1,
        "input_sha256": {str(accepted / "manifest.json"): _digest(accepted / "manifest.json")},
        "output_sha256": {n: _digest(supplement / n) for n in ("fighter_registry.json", "current_totals_derived.jsonl")}}))
    # The synthetic accepted fixture predates the real March 7, 2026 cutoff.
    monkeypatch.setattr("upset.data.stage_current.LAST_HISTORICAL_DATE", "2024-04-27")
    return root, bridge, accepted, supplement, historical, expected


def _export(paths, output):
    return export_current(*paths[:5], output, expected_history_sha256=paths[5], observed_at=NOW)


def test_full_offline_export_stages_known_fighters_and_keeps_names_only_unlinked(tmp_path, monkeypatch):
    paths = _fixture(tmp_path, monkeypatch)
    before = {p: p.read_bytes() for p in tmp_path.rglob("*.json*")}
    output = tmp_path / "current"
    result = _export(paths, output)
    assert result["canonical_current_bouts"] == 2 and result["canonical_fighter_stats"] == 4
    assert result["identified_current_bouts"] == 1 and result["unresolved_provider_fighters"] == 1
    assert result["api_calls"] == 0 and result["training_ready"] is False
    assert result["bout_validation_issues"] == 0
    review = json.loads((output / "review.json").read_text())["unresolved_fighter_identities"]
    assert review[0]["cito_fighter_id"] == "unknown-a"
    assert review[0]["name_only_candidates"][0]["upset_fighter_id"] == A
    assert review[0]["profile_observations"][0]["profile"]["id"] == "unknown-a"
    identified = [json.loads(line) for line in (output / "identified/fights_identified.jsonl").read_text().splitlines()]
    assert len(identified) == 1 and identified[0]["source_bout_id"] == "known"
    assert all(p.read_bytes() == b for p, b in before.items())
    assert _export(paths, output) == result
    (output / "fight_stats.jsonl").write_text("tampered")
    with pytest.raises(ValueError, match="Existing current export differs"):
        _export(paths, output)


def test_raw_card_and_bridge_changes_are_rejected(tmp_path, monkeypatch):
    paths = _fixture(tmp_path, monkeypatch)
    raw = paths[0] / "cards/ufc-current/stats.json"
    raw.write_text(raw.read_text() + " ")
    with pytest.raises(ValueError, match="hash differs"):
        _export(paths, tmp_path / "current")
    assert not (tmp_path / "current").exists()


@pytest.mark.parametrize("outcome,method", [("draw", "Decision - Majority"), ("no_contest", "CNC")])
def test_nondecisive_bouts_keep_no_winner(outcome, method):
    bout, event, totals, rounds = _sample()
    bout.update(method=method, winnerFighterSlug=None)
    for f in bout["fighters"]:
        f["outcome"] = outcome
    fight, stats, _ = normalize_completed_bout(bout, event, totals, rounds)
    assert fight["winner_name"] is None and fight["source_winner_label"] == "Draw/NC"
    assert len(stats) == 2


def test_missing_totals_require_matching_supplement_and_keep_control_unknown():
    bout, event, _, rounds = _sample()
    _, derived = reconcile_rounds(bout, rounds, expected_rounds=1)
    with pytest.raises(ValueError, match="Missing provider totals"):
        normalize_completed_bout(bout, event, [], rounds)
    fight, stats, _ = normalize_completed_bout(bout, event, [], rounds, derived_evidence=derived)
    assert fight["winner_name"] == "Alex" and all(r["control_seconds"] is None for r in stats)
    derived[0]["knockdowns"] = 1
    with pytest.raises(ValueError, match="Derived totals differ"):
        normalize_completed_bout(bout, event, [], rounds, derived_evidence=derived)


@pytest.mark.parametrize("change,reason", [
    (lambda b, t, r: b.update(winnerFighterSlug="sam"), "winner contradicts"),
    (lambda b, t, r: b.update(method="Unknown"), "Unreviewed"),
    (lambda b, t, r: r.pop(), "coverage"),
    (lambda b, t, r: t[0].update(knockdowns=1), "round sums"),
])
def test_winner_unknown_method_incomplete_rounds_and_bad_totals_are_rejected(change, reason):
    bout, event, totals, rounds = _sample()
    change(bout, totals, rounds)
    with pytest.raises(ValueError, match=reason):
        normalize_completed_bout(bout, event, totals, rounds)


def test_duplicate_provider_totals_and_false_no_contest_winners_are_rejected():
    bout, event, totals, rounds = _sample()
    totals.append(deepcopy(totals[0]))
    with pytest.raises(ValueError, match="two unique participants"):
        normalize_completed_bout(bout, event, totals, rounds)
    bout["method"] = "CNC"
    with pytest.raises(ValueError, match="winner contradicts"):
        normalize_completed_bout(bout, event, totals[:2], rounds)
