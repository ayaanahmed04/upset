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


def test_percentiles_use_midrank_and_even_pool_median(monkeypatch, tmp_path):
    key = "sig_landed_per_minute"
    pools = {"Lightweight": {"fighters": 25, "values": {k: [1, 2, 4, 5] for k in app.PERCENTILE_KEYS}}}
    monkeypatch.setattr(app, "distributions", lambda *args: pools)
    report = {"before": "2026-10-05", "window": 0, "summary": {"division": "Lightweight"},
              "metrics": {k: 2 for k in app.PERCENTILE_KEYS} | {"timed_bouts": 3, "minutes": 15}}
    result = app.percentiles(tmp_path / "fixture.sqlite", report)
    assert result["values"][key] == {"percentile": 37.5, "median": 3.0, "pool": 4}
    pools["Lightweight"]["values"][key] = [2, 2, 2]
    assert app.percentiles(tmp_path / "fixture.sqlite", report)["values"][key]["percentile"] == 50
    report["metrics"][key] = None
    assert app.percentiles(tmp_path / "fixture.sqlite", report)["values"][key] is None


def test_rankings_fallback_and_minimum_evidence_are_explicit(monkeypatch, tmp_path):
    values = {k: [1, 3] for k in app.PERCENTILE_KEYS}
    monkeypatch.setattr(app, "distributions", lambda *args: {"All divisions": {"fighters": 30, "values": values}})
    report = {"before": "2026-10-05", "window": 3, "summary": {"division": "Lightweight"},
              "metrics": {k: 1 for k in app.PERCENTILE_KEYS} | {"timed_bouts": 3, "minutes": 15}}
    assert app.percentiles(tmp_path / "fixture.sqlite", report)["scope"] == "All divisions"
    report["metrics"]["minutes"] = 14.9
    assert app.percentiles(tmp_path / "fixture.sqlite", report)["eligible"] is False


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
