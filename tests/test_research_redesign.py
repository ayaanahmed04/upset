"""Descriptive rankings and roster observations must respect their evidence."""

import json
from contextlib import closing
from http.server import ThreadingHTTPServer
from threading import Thread
from urllib.error import HTTPError
from urllib.request import urlopen

import pytest
from test_research_app import A, build, fixture

from upset import research_app as app


def test_rankings_removed_without_changing_recorded_stats(tmp_path):
    paths = fixture(tmp_path)
    output = tmp_path / "research"
    build(paths, output)
    report = app.route(output / "upset.sqlite", "/api/fighter?id=" + A + "&before=2026-09-21&window=0")
    assert "percentiles" not in report
    assert report["metrics"]["takedown_defense"] == .8
    with pytest.raises(KeyError, match="Page not found"):
        app.route(output / "upset.sqlite", "/api/rankings?metric=takedown_defense")
    assert "research_leaderboards.js" not in app.WEB_FILES
    assert "research_leaderboards.css" not in app.WEB_FILES


@pytest.mark.parametrize("cutoff,shown", [("2026-09-30", False), ("2026-10-01", True),
                                         ("2026-12-02", True), ("2026-12-03", False)])
def test_roster_status_never_appears_before_observation_or_after_expiry(monkeypatch, cutoff, shown):
    monkeypatch.setattr(app, "ROSTER", {"as_of": "2026-10-01", "source": "fixture",
                                      "fighters": {A: {"status": "active", "image": "fighter.png"}}})
    result = app.roster_entry({"id": A, "profile": {}, "before": cutoff})
    assert result["status_current"] is shown
    assert result["status"] == ("active" if shown else None)


@pytest.mark.parametrize("value", [{}, {"as_of": "wrong", "fighters": {}},
                                   {"as_of": "2026-10-01", "fighters": {A: "bad"}}])
def test_invalid_roster_fails_at_load(tmp_path, value):
    path = tmp_path / "roster.json"
    path.write_text(json.dumps(value))
    with pytest.raises((ValueError, TypeError, KeyError)):
        app.load_roster(path)


def test_assets_are_served_and_unknown_or_traversing_paths_are_rejected(tmp_path):
    paths = fixture(tmp_path)
    database = tmp_path / "research"
    build(paths, database)
    server = ThreadingHTTPServer(("127.0.0.1", 0), app.handler(database / "upset.sqlite"))
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        with urlopen(base + "/assets/favicon.png") as response:
            assert response.headers["Content-Type"] == "image/png"
            assert response.read().startswith(b"\x89PNG")
        for path in ("/assets/missing.png", "/assets/../research_app.py", "/assets/%2e%2e/research_app.py"):
            with pytest.raises(HTTPError) as error:
                urlopen(base + path)
            assert error.value.code == 404
        with closing(app.connect(database / "upset.sqlite")) as db:
            assert app.metadata(db)["total_bouts"] == 2
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
