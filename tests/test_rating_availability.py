"""The rating UI must never promote existing observations into invented scores."""

from contextlib import closing
from copy import deepcopy

import pytest
from test_research_app import A, B, build, fixture

from upset import research_app as app


@pytest.mark.parametrize("bouts,provisional", [(0, False), (1, True), (3, True), (4, False), (20, False)])
def test_unreleased_rating_has_no_score_despite_impressive_input_metrics(bouts, provisional):
    report = {"before": "2026-11-04", "history": [{} for _ in range(bouts)],
              "metrics": {"sig_accuracy": 1., "wins": 20}, "elo_rating": 2500,
              "experimental_striking": {"estimate": .99}, "score": 96}
    original = deepcopy(report)
    rating = app.rating_availability(report)
    assert rating["status"] == "not_available"
    assert rating["reason"] == "rating_model_not_ready"
    assert rating["score"] is None and rating["version"] is None
    assert rating["provisional"] is provisional and rating["recorded_bouts"] == bouts
    assert rating["before"] == report["before"]
    assert "in development" in rating["message"]
    assert ("Rated after first recorded UFC fight" in rating["message"]) is (bouts == 0)
    assert report == original


def test_availability_uses_full_pre_date_history_and_preserves_recorded_statistics(tmp_path, monkeypatch):
    output = tmp_path/"research"
    build(fixture(tmp_path), output)
    database = output/"upset.sqlite"
    monkeypatch.setattr(app, "STRIKING_PREVIEW", None)
    for cutoff, bouts in (("2026-03-07", 0), ("2026-03-08", 1),
                          ("2026-09-20", 1), ("2026-09-21", 2)):
        ratings = []
        for window in (0, 3, 5, 10):
            with closing(app.connect(database)) as db:
                raw = app.fighter_report(db, A, cutoff, window)
            response = app.route(database, f"/api/fighter?id={A}&before={cutoff}&window={window}")
            assert response["rating"]["recorded_bouts"] == bouts
            assert response["rating"]["before"] == cutoff
            assert response["rating"]["score"] is None
            assert response["metrics"] == raw["metrics"]
            assert response["history"] == raw["history"]
            assert response["summary"] == raw["summary"]
            ratings.append(response["rating"])
        assert all(rating == ratings[0] for rating in ratings)


def test_comparison_exposes_readiness_for_both_fighters_without_rating_history(tmp_path, monkeypatch):
    output = tmp_path/"research"
    build(fixture(tmp_path), output)
    monkeypatch.setattr(app, "STRIKING_PREVIEW", None)
    response = app.route(output/"upset.sqlite",
                         f"/api/compare?a={A}&b={B}&before=2026-09-20&window=3")
    for fighter in response["fighters"]:
        assert fighter["rating"]["score"] is None
        assert fighter["rating"]["recorded_bouts"] == 1
        assert fighter["rating"]["before"] == "2026-09-20"
        assert "history" not in fighter["rating"]
        assert "track_record" not in fighter["rating"]
    assert app.WEB_FILES["research_rating.js"] == "text/javascript; charset=utf-8"
    assert app.WEB_FILES["research_rating.css"] == "text/css; charset=utf-8"
