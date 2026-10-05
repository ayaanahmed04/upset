"""Research calculations preserve cutoffs, missingness and identity boundaries."""

import json
import sqlite3
import threading
from copy import deepcopy
from dataclasses import asdict
from http.server import ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.request import urlopen

import pytest

from upset.data.build_research_db import build_database
from upset.data.collect_cito_archive import _digest
from upset.data.identity import (
    FighterIdentity,
    FighterProviderLink,
    FighterRegistry,
    save_fighter_registry,
)
from upset.data.models import Fight, Fighter, FightStats
from upset.research_app import connect, fighter_report, handler, route, search

A = "00000000-0000-4000-8000-000000000001"
B = "00000000-0000-4000-8000-000000000002"
C = "00000000-0000-4000-8000-000000000003"


def write_rows(path, values):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r) + "\n" for r in values))


def fixture(root):
    historical, current, accepted = (root / n for n in ("historical", "current", "accepted"))
    registry_path = root / "registry.json"
    ids = [(A, "Alex Silva", "hist-a", "cito-a"), (B, "Sam", "hist-b", "cito-b"), (C, "Alex Silva", "hist-c", "cito-c")]
    registry = FighterRegistry(tuple(FighterIdentity(uid, name) for uid, name, _, _ in ids),
        tuple(FighterProviderLink(provider, pid, uid, "fixture") for uid, _, old, new in ids for provider, pid in (("ufcstats", old), ("cito", new))))
    save_fighter_registry(registry, registry_path)
    profiles = [{**asdict(Fighter("kaggle", pid, None, name, height_inches=70, reach_inches=72)), "upset_fighter_id": uid} for uid, name, pid, _ in ids]
    def fight(bid, day, provider, s1, s2):
        return {**asdict(Fight(provider, bid, "Alex Silva", "Sam", source_fighter_1_id=s1,
            source_fighter_2_id=s2, winner_name="Alex Silva", source_winner_label="Alex Silva",
            result_method="Decision - Unanimous", result_round=3, result_time="5:00", event_date=day,
            source_url="https://example.org/" + bid)), "upset_fighter_1_id": A, "upset_fighter_2_id": B}
    def stat(bid, provider, sid, uid, landed, attempted, duration, control):
        return {**asdict(FightStats(provider, bid, sid, duration, "3x5", 1, landed, attempted,
            2 if uid == A else 1, 4 if uid == A else 5, 0, control, landed, 0, 0, landed, 0, 0)), "upset_fighter_id": uid}
    old = fight("old", "2026-03-07", "kaggle", "hist-a", "hist-b")
    new = fight("new", "2026-09-20", "cito", "cito-a", "cito-b")
    old_stats = [stat("old", "kaggle", sid, uid, landed, attempted, 600, None) for sid, uid, landed, attempted in (("hist-a", A, 60, 100), ("hist-b", B, 20, 80))]
    new_stats = [stat("new", "cito", sid, uid, landed, attempted, 300, control) for sid, uid, landed, attempted, control in (("cito-a", A, 30, 50, 100), ("cito-b", B, 10, 40, 40))]
    write_rows(historical / "fighters_identified.jsonl", profiles)
    write_rows(historical / "fights_identified.jsonl", [old])
    write_rows(historical / "fight_stats_identified.jsonl", old_stats)
    write_rows(current / "identified/fights_identified.jsonl", [new])
    write_rows(current / "identified/fight_stats_identified.jsonl", new_stats)
    history_hash, stat_hash = _digest(historical / "fights_identified.jsonl"), _digest(historical / "fight_stats_identified.jsonl")
    current_manifest = {"identified_current_bouts": 1, "bouts_awaiting_identity_review": 94,
        "unresolved_provider_fighters": 101, "identified_subset_manifest": {"input_sha256": {
            "registry": _digest(registry_path), "historical": history_hash}},
        "output_sha256": {str(p.relative_to(current)): _digest(p) for p in current.rglob("*.jsonl")}}
    (current / "manifest.json").write_text(json.dumps(current_manifest))
    frozen = {k: old[k] for k in ("winner_name", "source_winner_label", "result_method", "result_round", "result_time")}
    amendment = {"winner_name": None, "result_method": "No Contest", "reason": "reviewed fixture", "revision_effective_date": None}
    write_rows(accepted / "bout_results.jsonl", [{"historical_bout_id": "old", "resolution": "reviewed_amendment", "frozen_result": frozen, "current_result": amendment}])
    (accepted / "manifest.json").write_text(json.dumps({"input_sha256": {"historical_fights": history_hash}, "output_sha256": {"bout_results.jsonl": _digest(accepted / "bout_results.jsonl")}}))
    return historical, current, registry_path, accepted, history_hash, stat_hash


def build(paths, output):
    return build_database(*paths[:4], output, expected_fights=paths[4], expected_stats=paths[5])


def test_build_readonly_query_and_reuse_preserve_inputs(tmp_path):
    paths = fixture(tmp_path)
    before = {p: p.read_bytes() for p in tmp_path.rglob("*.json*")}
    output = tmp_path / "research"
    result = build(paths, output)
    assert result["total_bouts"] == 2 and result["fighter_stat_rows"] == 4
    assert result["excluded_current_bouts"] == 94
    assert build(paths, output) == result
    assert all(p.read_bytes() == value for p, value in before.items())
    with connect(output / "upset.sqlite") as db:
        assert len(search(db, "Alex Silva")) == 2
        assert len(search(db, "Silva Aléx")) == 2
        assert search(db, "%' OR 1=1 --") == []
        with pytest.raises(sqlite3.OperationalError, match="readonly"):
            db.execute("DELETE FROM fighters")


def add_same_date_historical_bout(paths, *, source="kaggle", bid="rematch", uid=A):
    historical = paths[0]
    fight_path = historical / "fights_identified.jsonl"
    stats_path = historical / "fight_stats_identified.jsonl"
    fight = json.loads(fight_path.read_text().splitlines()[0])
    fight.update(source=source, source_bout_id=bid, upset_fighter_1_id=uid)
    write_rows(fight_path, [json.loads(fight_path.read_text()), fight])
    stats = [json.loads(line) for line in stats_path.read_text().splitlines()]
    extra = [dict(s, source=source, source_bout_id=bid) for s in stats]
    write_rows(stats_path, stats + extra)
    history_hash, stat_hash = _digest(fight_path), _digest(stats_path)
    current_manifest_path = paths[1] / "manifest.json"
    current_manifest = json.loads(current_manifest_path.read_text())
    current_manifest["identified_subset_manifest"]["input_sha256"]["historical"] = history_hash
    current_manifest_path.write_text(json.dumps(current_manifest))
    accepted_manifest_path = paths[3] / "manifest.json"
    accepted_manifest = json.loads(accepted_manifest_path.read_text())
    accepted_manifest["input_sha256"]["historical_fights"] = history_hash
    accepted_manifest_path.write_text(json.dumps(accepted_manifest))
    return (*paths[:4], history_hash, stat_hash)


def test_distinct_same_source_same_date_rematches_preserve_both_bouts(tmp_path):
    paths = add_same_date_historical_bout(fixture(tmp_path))
    output = tmp_path / "research"
    result = build(paths, output)
    assert result["historical_bouts"] == 2
    assert result["total_bouts"] == 3 and result["fighter_stat_rows"] == 6
    with connect(output / "upset.sqlite") as db:
        assert {r[0] for r in db.execute("SELECT id FROM fights")} == {
            "kaggle:old", "kaggle:rematch", "cito:new"}
        assert fighter_report(db, A, "2026-03-07", 0)["metrics"]["bouts"] == 0
        assert fighter_report(db, A, "2026-03-08", 0)["metrics"]["bouts"] == 2


@pytest.mark.parametrize("changes,message", [
    ({"bid": "old"}, "Duplicate research bout ID: kaggle:old"),
    ({"source": "cito"}, "Cross-provider same-date duplicate research bout"),
    ({"uid": B}, "Invalid or unknown research fighter identity"),
    ({"uid": "unknown"}, "Invalid or unknown research fighter identity"),
])
def test_same_date_policy_still_rejects_duplicate_ids_and_invalid_identities(tmp_path, changes, message):
    paths = add_same_date_historical_bout(fixture(tmp_path), **changes)
    output = tmp_path / "research"
    with pytest.raises(ValueError, match=message):
        build(paths, output)
    assert not output.exists()


def test_metrics_use_opponent_counts_weighted_duration_and_missing_control(tmp_path):
    paths = fixture(tmp_path)
    output = tmp_path / "research"
    build(paths, output)
    report = route(output / "upset.sqlite", "/api/fighter?id=" + A + "&before=2026-09-21&window=0")
    metrics = report["metrics"]
    assert metrics["sig_landed_per_minute"] == 6
    assert metrics["sig_absorbed_per_minute"] == 2
    assert metrics["striking_defense"] == .75
    assert metrics["takedown_defense"] == .8
    assert metrics["control_margin_seconds_per_minute"] == 12
    assert metrics["control_observed_bouts"] == 1
    assert metrics["wins"] == 1 and metrics["other_results"] == 1
    old = report["history"][1]
    assert old["frozen_outcome"] == "win" and old["outcome"] == "other"
    assert old["reviewed_result"]["revision_effective_date"] is None


def test_date_cutoff_is_exclusive_and_comparison_uses_same_window(tmp_path):
    paths = fixture(tmp_path)
    output = tmp_path / "research"
    build(paths, output)
    result = route(output / "upset.sqlite", f"/api/compare?a={A}&b={B}&before=2026-09-20&window=5")
    assert all(r["metrics"]["bouts"] == 1 for r in result["fighters"])
    assert result["fighters"][0]["metrics"]["control_margin_seconds_per_minute"] is None
    with connect(output / "upset.sqlite") as db:
        assert fighter_report(db, C, "2026-09-21", 5)["metrics"]["sig_landed_per_minute"] is None
        with pytest.raises(ValueError):
            fighter_report(db, A, "2026-09-21", 4)
        with pytest.raises(KeyError):
            fighter_report(db, "missing", "2026-09-21", 5)


def test_builder_rejects_tampering_and_missing_stats_before_publishing(tmp_path):
    paths = fixture(tmp_path)
    with pytest.raises(ValueError, match="snapshot differs"):
        build_database(*paths[:4], tmp_path / "bad")
    stat_path = paths[1] / "identified/fight_stats_identified.jsonl"
    original = stat_path.read_text()
    stat_path.write_text(original.splitlines()[0] + "\n")
    with pytest.raises(ValueError, match="hash differs"):
        build(paths, tmp_path / "bad")
    manifest_path = paths[1] / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["output_sha256"][str(stat_path.relative_to(paths[1]))] = _digest(stat_path)
    manifest_path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="Missing paired"):
        build(paths, tmp_path / "bad")
    assert not (tmp_path / "bad").exists()


def test_database_tampering_does_not_silently_rebuild(tmp_path):
    paths = fixture(tmp_path)
    output = tmp_path / "research"
    build(paths, output)
    with sqlite3.connect(output / "upset.sqlite") as db:
        db.execute("DELETE FROM stats")
    with pytest.raises(ValueError, match="Existing research database differs"):
        build(paths, output)


def test_zero_opponent_attempts_are_unavailable_not_perfect_defense(tmp_path):
    paths = fixture(tmp_path)
    stat_path = paths[1] / "identified/fight_stats_identified.jsonl"
    stats = [json.loads(line) for line in stat_path.read_text().splitlines()]
    opponent = deepcopy(stats[1])
    opponent.update(sig_strikes_landed=0, sig_strikes_attempted=0, takedowns_landed=0, takedowns_attempted=0)
    write_rows(stat_path, [stats[0], opponent])
    manifest_path = paths[1] / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["output_sha256"][str(stat_path.relative_to(paths[1]))] = _digest(stat_path)
    manifest_path.write_text(json.dumps(manifest))
    output = tmp_path / "research"
    build(paths, output)
    report = route(output / "upset.sqlite", "/api/fighter?id=" + A + "&before=2026-09-21&window=0")
    assert report["metrics"]["striking_defense"] == .75  # historical attempts only
    recent = route(output / "upset.sqlite", "/api/fighter?id=" + A + "&before=2026-09-21&window=3")
    assert recent["metrics"]["opponent_strike_attempts"] == 80
    with sqlite3.connect(output / "upset.sqlite") as db:
        for key, payload in db.execute("SELECT fight_id,payload FROM stats WHERE fighter_id=?", (B,)).fetchall():
            row = json.loads(payload)
            row.update(sig_strikes_landed=0, sig_strikes_attempted=0, takedowns_landed=0, takedowns_attempted=0)
            db.execute("UPDATE stats SET payload=? WHERE fight_id=? AND fighter_id=?", (json.dumps(row), key, B))
    no_attempts = route(output / "upset.sqlite", "/api/fighter?id=" + A + "&before=2026-09-21&window=5")
    assert no_attempts["metrics"]["striking_defense"] is None
    assert no_attempts["metrics"]["takedown_defense"] is None


def test_http_serves_packaged_viewer_and_reports_validation_errors(tmp_path):
    paths = fixture(tmp_path)
    output = tmp_path / "research"
    build(paths, output)
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler(output / "upset.sqlite"))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = "http://127.0.0.1:" + str(server.server_address[1])
    try:
        with urlopen(base, timeout=5) as response:
            body = response.read().decode()
            assert response.status == 200 and 'id="search"' in body
            assert 'id="before"' in body and 'id="window"' in body
        with urlopen(base + "/api/fighters?q=Alex", timeout=5) as response:
            assert len(json.loads(response.read())) == 2
        with pytest.raises(HTTPError) as error:
            urlopen(base + "/api/fighter?id=" + A + "&before=wrong", timeout=5)
        assert error.value.code == 400
        with pytest.raises(HTTPError) as error:
            urlopen(base + "/api/fighter?id=missing", timeout=5)
        assert error.value.code == 404
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
