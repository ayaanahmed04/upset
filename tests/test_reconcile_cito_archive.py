"""Historical joins require paired evidence and keep ambiguity/missingness visible."""

import json
from dataclasses import asdict

import pytest

from upset.data.collect_cito_archive import (
    _digest,
    collect_archive_cards,
    collect_inventory,
)
from upset.data.models import Fight, FightStats
from upset.data.reconcile_cito_archive import _numbers, match_bout, reconcile_archive

A = "00000000-0000-4000-8000-000000000001"
B = "00000000-0000-4000-8000-000000000002"
SOURCE = "kaggle_ufc_1994_2026"


def _raw(name, slug, *, round_number=None, bout_id="cito-bout", control="0:00"):
    row = {"id": f"{bout_id}/{slug}/{round_number}", "boutId": bout_id,
           "fighterName": name, "fighterSlug": slug, "knockdowns": 0,
           "submissionAttempts": 0, "reversals": 0, "controlTime": control,
           "significantStrikes": "1 of 2", "totalStrikes": "1 of 2",
           "takedowns": "0 of 0", "head": "1 of 2", "body": "0 of 0", "leg": "0 of 0",
           "distance": "1 of 2", "clinch": "0 of 0", "ground": "0 of 0"}
    if round_number is not None:
        row["round"] = round_number
    return row


def _history_rows():
    fight = {**asdict(Fight(SOURCE, "history-bout", "Alex", "Sam",
                            source_fighter_1_id="hist-a", source_fighter_2_id="hist-b",
                            winner_name="Alex", source_winner_label="Alex",
                            result_method="U-DEC", result_round=1, result_time="5:00",
                            event_date="2024-04-27")),
             "upset_fighter_1_id": A, "upset_fighter_2_id": B}
    stats = [{**asdict(FightStats(SOURCE, "history-bout", source_id, 300, "1x5",
                                  0, 1, 2, 0, 0, 0, None, 1, 0, 0, 1, 0, 0)),
              "upset_fighter_id": uid} for uid, source_id in ((A, "hist-a"), (B, "hist-b"))]
    return fight, {(r["source_bout_id"], r["upset_fighter_id"]): r for r in stats}


def _bout(bid="cito-bout"):
    return {"id": bid, "eventSlug": "ufc-test", "status": "completed", "hasStats": True,
            "isCancelled": False, "method": "Decision - Unanimous", "resultRound": 1,
            "resultTime": "5:00", "fighters": [
                {"fighterName": "Alex", "fighterSlug": "alex", "fighterId": "cito-a", "outcome": "win"},
                {"fighterName": "Sam", "fighterSlug": "sam", "fighterId": "cito-b", "outcome": "loss"}]}


def _match(bout, totals, *, histories=None, stats=None, reviewed=None, day="2024-04-26"):
    fight, default_stats = _history_rows()
    return match_bout(day, bout, totals,
                      {"2024-04-27": histories if histories is not None else [fight]},
                      stats if stats is not None else default_stats, reviewed or {})


def test_matches_swapped_order_date_offset_and_method_alias():
    bout = _bout()
    bout["fighters"].reverse()
    result = _match(bout, [_raw("Alex", "alex"), _raw("Sam", "sam")])
    assert result["status"] == "totals_verified_proposal"
    candidate = result["candidates"][0]
    assert candidate["upset_fighter_ids_in_cito_order"] == [B, A]
    assert candidate["date_offset_days"] == 1
    assert candidate["compared_stat_fields"] == 24
    assert result["metadata_differences"] == []


def test_names_date_without_totals_or_with_conflicting_totals_are_not_verified():
    assert _match(_bout(), [])["status"] == "candidate_requires_review"
    totals = [_raw("Alex", "alex"), _raw("Sam", "sam")]
    totals[0]["knockdowns"] = 1
    result = _match(_bout(), totals)
    assert result["status"] == "candidate_requires_review"
    assert result["candidates"][0]["stat_differences"][0]["field"] == "knockdowns"
    totals[0]["knockdowns"] = 0
    assert _match(_bout(), totals, reviewed={"cito-a": B})["status"] == "candidate_requires_review"


def test_identical_candidates_remain_ambiguous_but_unique_stat_evidence_resolves():
    fight, stats = _history_rows()
    duplicate = {**fight, "source_bout_id": "other-bout"}
    other = {(duplicate["source_bout_id"], uid): {**row, "source_bout_id": "other-bout"}
             for (_, uid), row in stats.items()}
    totals = [_raw("Alex", "alex"), _raw("Sam", "sam")]
    combined = {**stats, **other}
    assert _match(_bout(), totals, histories=[fight, duplicate], stats=combined)[
        "status"] == "ambiguous_historical_candidates"
    combined[("other-bout", A)]["knockdowns"] = 1
    result = _match(_bout(), totals, histories=[fight, duplicate], stats=combined)
    assert result["status"] == "totals_verified_proposal"
    assert result["candidates"][0]["historical_bout_id"] == "history-bout"
    assert result["other_name_date_candidates"]


def test_result_repairs_are_proposals_and_source_winner_is_not_inferred():
    bout = _bout()
    bout["status"] = "confirmed"
    for fighter in bout["fighters"]:
        fighter["outcome"] = None
    result = _match(bout, [_raw("Alex", "alex"), _raw("Sam", "sam")])
    assert result["status"] == "totals_verified_proposal"
    assert result["accepted_historical_result"]["winner_upset_fighter_id"] == A
    assert {r["field"] for r in result["metadata_differences"]} == {"winner", "status"}
    assert bout["fighters"][0]["outcome"] is None
    assert _match(bout, [], day="2026-09-12")["status"] == "post_snapshot"


def test_missing_control_stays_none_and_bad_breakdown_is_rejected():
    assert _numbers(_raw("Alex", "alex", control="--"))["control_seconds"] is None
    raw = _raw("Alex", "alex")
    raw["head"] = "0 of 0"
    with pytest.raises(ValueError, match="breakdown"):
        _numbers(raw)


@pytest.mark.parametrize("provider_id,source_name,historical_name", [
    ("5ac923a0-f9b1-4611-b3dc-14fc2d230899", "Magomed Bibulatov", "Bibulatov Magomed"),
    ("6fe35b97-d7c3-4ac7-b19a-cceaa43eeb02", "Kai Kamaka III", "Kai Kamaka"),
])
def test_reviewed_historical_alias_needs_scoped_id_and_paired_totals(
        provider_id, source_name, historical_name):
    history, _stats = _history_rows()
    history["fighter_1_name"] = historical_name
    bout = _bout()
    bout["fighters"][0].update(fighterId=provider_id, fighterName=source_name,
                                fighterSlug=source_name.lower().replace(" ", "-"))
    totals = [_raw(source_name, bout["fighters"][0]["fighterSlug"]), _raw("Sam", "sam")]
    assert _match(bout, totals, histories=[history])["status"] == "totals_verified_proposal"
    assert _match(bout, [], histories=[history])["status"] == "candidate_requires_review"
    totals[0]["knockdowns"] = 1
    assert _match(bout, totals, histories=[history])["status"] == "candidate_requires_review"
    bout["fighters"][0]["fighterId"] = "unreviewed-profile"
    assert _match(bout, totals, histories=[history])["status"] == "no_historical_candidate"


def test_current_no_contest_retains_frozen_result_and_does_not_invent_amendment_date():
    history, stats = _history_rows()
    history.update(source_bout_id="7ffdaa44fc8d111b", event_date="2026-02-21",
                   fighter_1_name="Alibi Idiris", fighter_2_name="Ode' Osbourne",
                   source_fighter_1_id="30cad5a751adcb48", source_fighter_2_id="6d68c1afe954f121",
                   winner_name="Alibi Idiris", result_round=3)
    stats = {(history["source_bout_id"], uid): row for (_, uid), row in stats.items()}
    bout = _bout()
    bout.update(method="Overturned", resultRound=3)
    for fighter, name in zip(bout["fighters"], ("Alibi Idiris", "Ode' Osbourne"), strict=True):
        fighter.update(fighterName=name, fighterSlug=name.lower().replace(" ", "-"), outcome="no_contest")
    totals = [_raw(f["fighterName"], f["fighterSlug"]) for f in bout["fighters"]]
    result = match_bout("2026-02-21", bout, totals, {"2026-02-21": [history]}, stats, {})
    assert result["accepted_historical_result"]["winner_upset_fighter_id"] == A
    revision = result["reviewed_current_result"]
    assert revision["winner_upset_fighter_id"] is None
    assert revision["outcome"] == "no_contest"
    assert revision["revision_effective_date"] is None
    assert revision["revision_verified_on"] == "2026-09-30"
    assert history["winner_name"] == "Alibi Idiris"
    bout["fighters"][0]["outcome"] = "win"
    with pytest.raises(ValueError, match="revision differs"):
        match_bout("2026-02-21", bout, totals, {"2026-02-21": [history]}, stats, {})


class Response:
    status_code = 200

    def __init__(self, data):
        self.data = data

    def json(self):
        return {"success": True, "data": self.data}


def _prepare(tmp_path, *, duplicate=False):
    root = tmp_path / "archive"
    historical = tmp_path / "historical"
    historical.mkdir()
    fight, stats = _history_rows()
    (historical / "fights_identified.jsonl").write_text(json.dumps(fight) + "\n")
    (historical / "fight_stats_identified.jsonl").write_text(
        "".join(json.dumps(row) + "\n" for row in stats.values()))
    registry = tmp_path / "registry.json"
    registry.write_text(json.dumps({"schema_version": 1,
        "identities": [{"upset_fighter_id": uid, "display_name": name} for uid, name in ((A, "Alex"), (B, "Sam"))],
        "provider_links": [{"provider": "ufcstats", "provider_fighter_id": sid,
                            "upset_fighter_id": uid, "evidence": "fixture"}
                           for uid, sid in ((A, "hist-a"), (B, "hist-b"))]}))
    bouts = [_bout()]
    if duplicate:
        bouts.append(_bout("cito-duplicate"))
    totals = [_raw(name, slug, bout_id=b["id"], control="--")
              for b in bouts for name, slug in (("Alex", "alex"), ("Sam", "sam"))]
    rounds = [_raw(name, slug, round_number=1, bout_id=b["id"], control="--")
              for b in bouts for name, slug in (("Alex", "alex"), ("Sam", "sam"))]
    event = {"id": "event-1", "slug": "ufc-test", "eventDate": "2024-04-26",
             "hasStats": True, "status": "completed", "bouts": bouts}
    collect_inventory(root, "secret", lambda *a, **k: Response([event]), delay=0)

    def get(url, **kwargs):
        if url.endswith("/bouts"):
            return Response(bouts)
        if url.endswith("/stats"):
            return Response({"event": event, "bouts": bouts, "boutStats": totals, "roundStats": rounds})
        return Response(event)

    collect_archive_cards(root, "secret", get, from_date="2024-01-01", through_date="2024-12-31", delay=0)
    return root, historical, registry


def _run(paths, output):
    return reconcile_archive(*paths, output,
                              expected_history_sha256=_digest(paths[1] / "fights_identified.jsonl"),
                              log=lambda *a, **k: None)


def test_offline_bridge_exports_rounds_links_and_coverage_without_mutating_inputs(tmp_path):
    paths = _prepare(tmp_path)
    before = {p: p.read_bytes() for p in tmp_path.rglob("*.json*")}
    output = tmp_path / "bridge"
    summary = _run(paths, output)
    assert summary["historical_bouts_with_verified_totals"] == 1
    assert summary["historical_bouts_without_verified_totals"] == 0
    assert summary["fighter_proposal_statuses"] == {"unique_evidence_proposal": 2}
    assert summary["api_calls"] == 0
    assert summary["training_ready"] is False
    rows = [json.loads(line) for line in (output / "round_stats_staged.jsonl").read_text().splitlines()]
    assert len(rows) == 2
    assert all(r["control_seconds"] is None for r in rows)
    assert rows[0]["proposed_upset_fighter_id"] == A
    assert rows[0]["reviewed_upset_fighter_id"] is None
    assert all(p.read_bytes() == value for p, value in before.items())
    assert all(_digest(output / name) == digest for name, digest in summary["output_sha256"].items())
    with pytest.raises(ValueError, match="Output exists"):
        _run(paths, output)


def test_duplicate_matches_are_visible_and_not_counted_twice_as_historical_coverage(tmp_path):
    paths = _prepare(tmp_path, duplicate=True)
    summary = _run(paths, tmp_path / "bridge")
    assert summary["historical_bouts_with_verified_totals"] == 1
    assert summary["historical_bouts_with_multiple_cito_matches"] == 1
    assert summary["staged_round_rows"] == 4
    rows = [json.loads(line) for line in (tmp_path / "bridge/round_stats_staged.jsonl").read_text().splitlines()]
    assert all(row["duplicate_historical_match"] for row in rows)


def test_changed_snapshot_or_raw_card_is_rejected_before_export(tmp_path):
    paths = _prepare(tmp_path)
    with pytest.raises(ValueError, match="accepted snapshot"):
        reconcile_archive(*paths, tmp_path / "bridge")
    raw = paths[0] / "cards/ufc-test/stats.json"
    raw.write_text(raw.read_text() + " ")
    with pytest.raises(ValueError, match="hash differs"):
        _run(paths, tmp_path / "bridge")
    assert not (tmp_path / "bridge").exists()
