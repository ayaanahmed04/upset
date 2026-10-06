"""Fan statistics retain real denominators, identities and date boundaries."""

import json
import sqlite3
from copy import deepcopy

import pytest

from test_research_app import A, B, C, build, fixture
from upset.research_app import common_opponents, connect, fighter_report, route
from upset.data.reviewed_bout_metadata import REVIEWED_TITLE_BOUTS, reviewed_title_evidence


def test_count_metrics_include_zero_clock_bouts_and_use_paired_knockdowns(tmp_path):
    output = tmp_path / "research"
    build(fixture(tmp_path), output)
    database = output / "upset.sqlite"
    with sqlite3.connect(database) as db:
        for uid in (A, B):
            payload = json.loads(db.execute(
                "SELECT payload FROM stats WHERE fight_id='cito:new' AND fighter_id=?", (uid,)).fetchone()[0])
            payload.update(fight_duration_seconds=0, knockdowns=2 if uid == A else 4)
            db.execute("UPDATE stats SET payload=? WHERE fight_id='cito:new' AND fighter_id=?",
                       (json.dumps(payload), uid))
    with connect(database) as db:
        report = fighter_report(db, A, "2026-09-21", 0)
        power = report["metrics"]["power_durability"]
        assert report["metrics"]["timed_bouts"] == 1
        assert power["bouts"] == 2
        assert power["knockdowns_scored"] == 3
        assert power["sig_strikes_landed"] == 90
        assert power["knockdowns_per_100_sig_landed"] == pytest.approx(100 * 3 / 90)
        assert power["knockdowns_received"] == 5
        assert power["ko_tko_losses"] == 0


def test_zero_strike_denominator_and_empty_history_are_unavailable(tmp_path):
    output = tmp_path / "research"
    build(fixture(tmp_path), output)
    database = output / "upset.sqlite"
    with sqlite3.connect(database) as db:
        for fight_id, content in db.execute("SELECT fight_id,payload FROM stats WHERE fighter_id=?", (A,)).fetchall():
            payload = json.loads(content)
            payload.update(sig_strikes_landed=0, knockdowns=0)
            db.execute("UPDATE stats SET payload=? WHERE fight_id=? AND fighter_id=?",
                       (json.dumps(payload), fight_id, A))
    with connect(database) as db:
        for uid in (A, C):
            power = fighter_report(db, uid, "2026-09-21", 0)["metrics"]["power_durability"]
            assert power["knockdowns_per_100_sig_landed"] is None
            assert power["sig_strikes_landed"] == 0
        power = fighter_report(db, A, "2026-03-07", 0)["metrics"]["power_durability"]
        assert power["bouts"] == 0  # exclusive cutoff


def test_common_opponents_endpoint_keeps_rematches_cutoffs_and_amendments(tmp_path):
    output = tmp_path / "research"
    build(fixture(tmp_path), output)
    database = output / "upset.sqlite"
    with sqlite3.connect(database) as db:
        payload = json.loads(db.execute("SELECT payload FROM fights WHERE id='kaggle:old'").fetchone()[0])
        payload.update(source_bout_id="third", upset_fighter_1_id=C, source_fighter_1_id="hist-c",
                       event_date="2026-03-06", winner_name="Sam", result_method="TKO - Doctor's Stoppage")
        payload.pop("reviewed_result", None)
        db.execute("INSERT INTO fights VALUES (?,?,?,?,?)", ("kaggle:third", "2026-03-06", C, B, json.dumps(payload)))
        for uid, content in db.execute("SELECT fighter_id,payload FROM stats WHERE fight_id='kaggle:old'").fetchall():
            stat = json.loads(content)
            new_uid = C if uid == A else uid
            stat.update(source_bout_id="third", upset_fighter_id=new_uid)
            db.execute("INSERT INTO stats VALUES (?,?,?)", ("kaggle:third", new_uid, json.dumps(stat)))
    request = f"/api/compare?a={A}&b={C}&window=0&before="
    assert route(database, request + "2026-03-07")["common_opponents"] == []
    result = route(database, request + "2026-09-21")
    shared, = result["common_opponents"]
    assert shared["opponent_id"] == B
    a, c = shared["fighters"]
    assert [m["fight_id"] for m in a["meetings"]] == ["cito:new", "kaggle:old"]
    assert [m["outcome"] for m in a["meetings"]] == ["win", "other"]
    assert a["meetings"][1]["result_amended"] is True
    assert c["meetings"][0]["outcome"] == "loss"
    power = result["fighters"][1]["metrics"]["power_durability"]
    assert power["ko_tko_losses"] == power["losses"] == 1
    assert len(route(database, request + "2026-09-20")["common_opponents"][0]["fighters"][0]["meetings"]) == 1


def test_common_opponents_obeys_each_window_and_does_not_join_names():
    def meeting(opponent, day, fid):
        return {"opponent_id": opponent, "opponent": "Same name", "fight_id": fid,
                "date": day, "outcome": "win", "method": "Decision", "result_round": 3,
                "result_time": "5:00", "reviewed_result": None}
    a = {"id": A, "window": 3, "history": [meeting(f"other-{i}", "2026-05-01", str(i)) for i in range(3)]
         + [meeting(B, "2026-01-01", "old-a")]}
    c = {"id": C, "window": 3, "history": [meeting(B, "2026-02-01", "old-c")]}
    original = deepcopy([a, c])
    assert common_opponents([a, c]) == []
    assert [a, c] == original
    a["window"] = c["window"] = 0
    assert [row["opponent_id"] for row in common_opponents([a, c])] == [B]
    c["history"][0]["opponent_id"] = "same-name-different-id"
    assert common_opponents([a, c]) == []


def test_reviewed_title_metadata_requires_exact_bout_date_and_pair():
    for (source, bid), entry in REVIEWED_TITLE_BOUTS.items():
        a, b = sorted(entry["fighter_ids"])
        fight = {"source": source, "source_bout_id": bid, "event_date": entry["event_date"],
                 "upset_fighter_1_id": a, "upset_fighter_2_id": b, "weight_class": entry["division"]}
        assert reviewed_title_evidence(fight)["source_url"].startswith("https://www.ufc.com/")
        assert reviewed_title_evidence({**fight, "upset_fighter_1_id": b, "upset_fighter_2_id": a})
        for change in ({"event_date": "2026-05-10"}, {"upset_fighter_1_id": A}, {"weight_class": "Heavyweight"}):
            with pytest.raises(ValueError, match="does not match"):
                reviewed_title_evidence({**fight, **change})
        assert reviewed_title_evidence({**fight, "source_bout_id": "unreviewed-five-round-main-event"}) is None
