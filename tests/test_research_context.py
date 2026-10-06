"""Dated opponent context and shared exposure cannot silently use future/missing data."""

import json
import sqlite3

import pytest

from test_research_app import A, B, C, build, fixture
from upset.research_app import connect, fighter_report, route
from upset.research_context import control_shares, opponent_records


def add_fight(db, bid, day, a, b, winner, amendment=None):
    payload = {"upset_fighter_1_id": a, "upset_fighter_2_id": b,
               "fighter_1_name": a, "fighter_2_name": b, "winner_name": winner}
    if amendment:
        payload["reviewed_result"] = {"winner_name": None}
    db.execute("INSERT INTO fights VALUES (?,?,?,?,?)", (bid, day, a, b, json.dumps(payload)))


def test_opponent_records_exclude_future_and_same_day_and_use_reviewed_results():
    with sqlite3.connect(":memory:") as db:
        db.execute("CREATE TABLE fights (id,event_date,fighter_1,fighter_2,payload)")
        add_fight(db, "b-win", "2020-01-01", B, "x", B)
        add_fight(db, "b-loss", "2020-02-01", "x", B, "x")
        add_fight(db, "b-amendment", "2020-03-01", B, "x", B, amendment=True)
        add_fight(db, "c-win", "2020-04-01", C, "x", C)
        add_fight(db, "c-win-2", "2020-04-02", C, "x", C)
        add_fight(db, "c-win-3", "2020-04-03", C, "x", C)
        add_fight(db, "same-day", "2020-05-01", B, A, B)
        add_fight(db, "future", "2020-06-01", B, "x", B)
        history = [{"fight_id": bid, "date": "2020-05-01", "opponent_id": uid, "opponent": uid}
                   for bid, uid in (("meet-b", B), ("meet-c", C), ("debut", "z"))]
        result = opponent_records(db, history, 0)
        b, c, debut = result["meetings"]
        assert (b["wins"], b["losses"], b["other"]) == (1, 1, 1)
        assert (c["wins"], c["losses"]) == (3, 0)
        assert debut["win_fraction"] is None
        assert result["mean_opponent_win_fraction"] == .75
        assert result["pooled_opponent_win_fraction"] == .8
        assert result["opponents_without_decisive_history"] == 1
        history.insert(0, {"fight_id": "rematch", "date": "2020-07-01", "opponent_id": B, "opponent": B})
        result = opponent_records(db, history, 3)
        assert result["bouts"] == 3
        assert (result["meetings"][0]["wins"], result["meetings"][0]["losses"]) == (3, 1)
        assert result["mean_opponent_win_fraction"] == pytest.approx((.75 + .5 + 1) / 3)
        assert opponent_records(db, [], 0)["mean_opponent_win_fraction"] is None


def test_context_endpoint_and_absorption_denominator_obey_exclusive_cutoff(tmp_path):
    output = tmp_path / "research"
    build(fixture(tmp_path), output)
    database = output / "upset.sqlite"
    old = route(database, f"/api/fighter?id={A}&before=2026-09-20&window=0")
    new = route(database, f"/api/fighter?id={A}&before=2026-09-21&window=0")
    assert old["metrics"]["opponent_records"]["bouts"] == 1
    assert new["metrics"]["opponent_records"]["bouts"] == 2
    records = new["metrics"]["opponent_records"]
    assert records["opponents_with_decisive_history"] == 0  # prior fight reviewed to NC
    assert records["meetings"][0]["other"] == 1
    power = new["metrics"]["power_durability"]
    assert power["sig_strikes_absorbed"] == 30
    assert power["knockdowns_received_per_100_sig_absorbed"] == pytest.approx(200 / 30)
    control = new["metrics"]["control_shares"]
    assert control["observed_bouts"] == control["missing_control_bouts"] == 1
    assert control["observed_seconds"] == 300
    assert control["in_control_fraction"] == pytest.approx(100 / 300)
    assert control["controlled_fraction"] == pytest.approx(40 / 300)
    assert control["neither_credited_fraction"] == pytest.approx(160 / 300)
    with connect(database) as db:
        empty = fighter_report(db, C, "2026-09-21", 0)["metrics"]
        assert empty["power_durability"]["knockdowns_received_per_100_sig_absorbed"] is None
        assert empty["control_shares"]["in_control_fraction"] is None


def test_control_excludes_missing_and_overlapping_totals_instead_of_clamping():
    def row(own, other, duration=300):
        return {"own": {"fight_duration_seconds": duration, "control_seconds": own},
                "opponent_stats": {"control_seconds": other}}
    result = control_shares([row(0, 0), row(100, 40), row(None, 0), row(250, 100), row(-1, 0)])
    assert result["observed_bouts"] == 2
    assert result["missing_control_bouts"] == 1
    assert result["invalid_control_bouts"] == 2
    assert result["observed_seconds"] == 600
    assert sum(result[k] for k in ("in_control_fraction", "controlled_fraction", "neither_credited_fraction")) == pytest.approx(1)
    assert control_shares([row(None, 0)])["neither_credited_fraction"] is None
