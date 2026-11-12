"""Rating explanation fields use historical component and opponent snapshots."""

from copy import deepcopy

import pytest
from test_rating_integration import raw_report, site_snapshot, target, without_updates
from test_rating_serving import A, B, artifact, row, write

from upset import research_app as app
from upset.ratings.serving import load_snapshot


def test_latest_win_has_unrounded_part_changes_and_strictly_pre_fight_best_win(tmp_path, monkeypatch):
    database, folder = site_snapshot(tmp_path)
    import json
    rows = [json.loads(line) for line in (folder/"ratings.jsonl").read_text().splitlines()]
    metadata = json.loads((folder/"manifest.json").read_text())
    evaluation = json.loads((folder/"evaluation.json").read_text())
    current = next(item for item in rows if item["fighter_id"] == A and item["event_date"] == "2026-09-20")
    current["parts"][3]["score"] = 80.123456
    current["parts"][0]["score"] = 74.987654
    write(folder, rows, evaluation, metadata)
    snapshot = load_snapshot(folder, database)
    monkeypatch.setattr(app, "RATING_SNAPSHOT", snapshot)
    response = app.route(database, target())
    rating = response["rating"]
    assert rating["previous_score"] == 76
    changes = {item["key"]: item for item in rating["part_changes"]}
    assert changes["resume"]["previous"] == 75.2
    assert changes["resume"]["current"] == 80.123456
    assert changes["resume"]["change"] == pytest.approx(4.923456)
    assert changes["striking"]["change"] == pytest.approx(-.212346)
    assert rating["last_results"] == [{"fight_id": "cito:new", "date": "2026-09-20",
                                        "opponent_id": B, "opponent": "Sam", "method": "Decision - Unanimous",
                                        "outcome": "win"}]
    assert rating["best_wins"] == [{"fight_id": "cito:new", "date": "2026-09-20", "opponent_id": B,
                                     "opponent": "Sam", "opponent_rating": 70, "method": "Decision - Unanimous"}]
    # Opponent is now 73, but the win explanation must use the earlier 70.
    assert snapshot.estimate(database, {"id": B, "before": "2026-09-21", "window": 0})["score"] == 73
    assert rating["best_wins_basis"] == "opponent pre-fight rating under this version"
    raw = raw_report(database)
    assert response["metrics"] == raw["metrics"]
    assert response["summary"] == raw["summary"]
    assert without_updates(response["history"]) == raw["history"]


def test_first_rating_and_reviewed_no_contest_do_not_invent_deltas_or_wins(tmp_path, monkeypatch):
    database, folder = site_snapshot(tmp_path)
    monkeypatch.setattr(app, "RATING_SNAPSHOT", load_snapshot(folder, database))
    rating = app.route(database, target("2026-03-08"))["rating"]
    assert rating["previous_score"] is None
    assert rating["part_changes"] == []
    assert rating["best_wins"] == []
    assert rating["last_results"][0]["outcome"] == "other"
    assert rating["last_results"][0]["method"] == "No Contest"
    before = app.route(database, target("2026-03-07"))["rating"]
    assert before["status"] == "no_history"
    assert "part_changes" not in before and "best_wins" not in before


def test_explanations_are_career_based_and_unchanged_by_window(tmp_path, monkeypatch):
    database, folder = site_snapshot(tmp_path)
    monkeypatch.setattr(app, "RATING_SNAPSHOT", load_snapshot(folder, database))
    career = app.route(database, target())["rating"]
    for window in (3, 5, 10):
        rating = app.route(database, target(window=window))["rating"]
        assert rating == career
    cutoff = app.route(database, target("2026-09-20"))["rating"]
    assert cutoff["event_date"] == "2026-03-07"
    assert cutoff["best_wins"] == []
    assert cutoff["last_results"][0]["date"] < "2026-09-20"


def test_best_wins_rank_old_opponent_scores_not_current_or_same_day_scores(tmp_path, monkeypatch):
    folder, database, _, _, evaluation, metadata = artifact(tmp_path)
    opponents = [f"00000000-0000-4000-8000-{i:012d}" for i in range(2, 9)]
    pre_scores = [85, 88, None, 86, 84, 81, 90]
    rows = [row(A, "2026-01-01", 1, 75, 75, None)]
    for opponent, score in zip(opponents, pre_scores):
        if score is not None:
            rows.append(row(opponent, "2026-05-01", 5, score, score, None))
            rows.append(row(opponent, "2026-09-01", 6, score+5, score+5, 5))
    rows.append(row(A, "2026-09-01", 8, 79, 79, 4))
    rows.sort(key=lambda item: (item["event_date"], item["fighter_id"]))
    write(folder, rows, evaluation, metadata)
    snapshot = load_snapshot(folder, database)
    calls = []

    class LookupOnly:
        def estimate(self, path, request):
            calls.append(deepcopy(request))
            return snapshot.estimate(path, request)

    monkeypatch.setattr(app, "RATING_SNAPSHOT", LookupOnly())
    history = [{"fight_id": "sample:"+str(i), "date": "2026-09-01", "opponent_id": opponent,
                "opponent": "Opponent "+str(i), "method": "Decision", "outcome": "win"}
               for i, opponent in enumerate(opponents)]
    future = {**history[0], "fight_id": "sample:future", "date": "2026-11-05"}
    report = {"id": A, "before": "2026-09-02", "window": 3, "history": history+[future],
              "rating": snapshot.estimate(database, {"id": A, "before": "2026-09-02", "window": 0})}
    unchanged_history = deepcopy(report["history"])
    app.rating_explanations(database, report)
    assert [item["opponent_rating"] for item in report["rating"]["best_wins"]] == [90, 88, 86, 85, 84]
    assert len(report["rating"]["last_results"]) == 7
    assert calls[0] == {"id": A, "before": "2026-09-01", "window": 0}
    assert all(request["before"] == "2026-09-01" and request["window"] == 0 for request in calls)
    assert report["history"] == unchanged_history


def test_unrated_opponents_are_retained_as_unknown_and_sorted_last(tmp_path, monkeypatch):
    database, folder = site_snapshot(tmp_path)
    snapshot = load_snapshot(folder, database)
    monkeypatch.setattr(app, "RATING_SNAPSHOT", snapshot)
    current = snapshot.estimate(database, {"id": A, "before": "2026-09-21", "window": 0})
    unknown = "00000000-0000-4000-8000-000000000003"
    history = [{"fight_id": "win:unrated", "date": "2026-09-20", "opponent_id": unknown,
                "opponent": "Unrated opponent", "method": "KO/TKO", "outcome": "win"},
               {"fight_id": "win:rated", "date": "2026-09-20", "opponent_id": B,
                "opponent": "Rated opponent", "method": "Submission", "outcome": "win"}]
    report = {"id": A, "before": "2026-09-21", "window": 0, "history": history, "rating": current}
    app.rating_explanations(database, report)
    assert [item["opponent_rating"] for item in report["rating"]["best_wins"]] == [70, None]
    assert report["rating"]["best_wins"][-1]["opponent"] == "Unrated opponent"
    assert len(report["rating"]["last_results"]) == 2


@pytest.mark.parametrize("snapshot_enabled", [False, True])
def test_unavailable_rating_is_preserved_without_fabricated_explanations(tmp_path, monkeypatch, snapshot_enabled):
    database, folder = site_snapshot(tmp_path)
    monkeypatch.setattr(app, "RATING_SNAPSHOT", load_snapshot(folder, database) if snapshot_enabled else None)
    rating = app.route(database, target("2026-03-07"))["rating"]
    assert rating["score"] is None
    assert "previous_score" not in rating and "part_changes" not in rating
    assert "best_wins" not in rating and "last_results" not in rating
