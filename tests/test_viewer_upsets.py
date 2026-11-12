import json
import sqlite3
from contextlib import closing

from upset.data.viewer_upsets import build_upset_index


def test_tracker_uses_pre_bout_grades_and_reviewed_decisions():
    class Snapshot:
        metadata = {"display_curve": {"reference_before": "2019-01-01"}, "latest_event": "2026-11-07"}

        def estimate(self, database, report):
            uid, day = report["id"], report["before"]
            assert report["window"] == 0
            return {"status": "available", "bouts": 4 if uid == "rookie" else 8,
                    "score": 80 if uid in ("lower", "equal") else 90,
                    "event_date": day if uid == "same-day" else "2025-01-01"}

    def fight(key, day, one, two, winner, *, amended=False):
        row = {"source": "fixture", "source_bout_id": key, "event_date": day,
               "fighter_1_name": one, "fighter_2_name": two, "upset_fighter_1_id": one,
               "upset_fighter_2_id": two, "winner_name": winner, "result_method": "KO/TKO"}
        if amended:
            row["reviewed_result"] = {"winner_name": None, "result_method": "No Contest"}
        return key, day, json.dumps(row)

    with closing(sqlite3.connect(":memory:")) as db:
        db.row_factory = sqlite3.Row
        db.execute("CREATE TABLE fights (id TEXT, event_date TEXT, payload TEXT)")
        db.executemany("INSERT INTO fights VALUES (?,?,?)", [
            fight("first", "2026-09-01", "lower", "higher", "lower"),
            fight("second", "2026-10-01", "higher", "lower", "lower"),
            fight("loss", "2026-11-01", "lower", "higher", "higher"),
            fight("tie", "2026-11-02", "lower", "equal", "lower"),
            fight("overturned", "2026-11-03", "lower", "higher", "lower", amended=True),
            fight("insufficient", "2026-11-04", "lower", "rookie", "lower"),
            fight("same-date", "2026-11-05", "lower", "same-day", "lower"),
        ])
        tracker = build_upset_index(db, None, Snapshot(), None)
    assert tracker["eligible_bouts"] == 4
    assert tracker["upset_count"] == 2
    assert [row["id"] for row in tracker["biggest"]] == ["second", "first"]
    assert tracker["biggest"][0]["gap"] == 10
    repeat, = tracker["repeat_winners"]
    assert (repeat["fighter"]["id"], repeat["wins"], repeat["opportunities"]) == ("lower", 2, 3)
