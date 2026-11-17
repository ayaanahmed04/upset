"""Optional overall ratings preserve the recorded viewer and date contract."""

import json
from contextlib import closing
from copy import deepcopy

import pytest
from test_rating_serving import artifact, digest, row, write
from test_research_app import A, B, add_same_date_historical_bout, build, fixture

from upset import research_app as app
from upset.ratings import serving


def site_snapshot(tmp_path, *, same_day=False):
    paths = fixture(tmp_path)
    if same_day:
        paths = add_same_date_historical_bout(paths)
    output = tmp_path/"research"
    build(paths, output)
    database = output/"upset.sqlite"
    binding = tmp_path/"binding"
    binding.mkdir()
    folder, _, _, _, evaluation, metadata = artifact(binding)
    initial = 2 if same_day else 1
    rows = [row(A, "2026-03-07", initial, 76, 76, None),
            row(B, "2026-03-07", initial, 70, 70, None),
            row(A, "2026-09-20", initial+1, 80, 80, 4),
            row(B, "2026-09-20", initial+1, 73, 73, 3)]
    metadata.update(input_database=str(database), database_sha256=digest(database), latest_event="2026-09-20")
    write(folder, rows, evaluation, metadata)
    return database, folder


def raw_report(database, before="2026-09-21", window=0, uid=A):
    with closing(app.connect(database)) as db:
        return app.fighter_report(db, uid, before, window)


def target(before="2026-09-21", window=0, uid=A):
    return f"/api/fighter?id={uid}&before={before}&window={window}"


def without_updates(history):
    result = deepcopy(history)
    for item in result:
        item.pop("rating_update", None)
    return result


def test_optional_off_preserves_readiness_and_unannotated_history(tmp_path, monkeypatch):
    database, _ = site_snapshot(tmp_path)
    monkeypatch.setattr(app, "RATING_SNAPSHOT", None)
    monkeypatch.setattr(app, "STRIKING_PREVIEW", None)
    raw = raw_report(database)
    response = app.route(database, target())
    assert response["rating"] == app.rating_availability(raw)
    assert response["rating"]["score"] is None
    assert response["history"] == raw["history"]
    assert response["metrics"] == raw["metrics"]


def test_enabled_rating_and_date_batch_chips_preserve_raw_observations(tmp_path, monkeypatch):
    database, folder = site_snapshot(tmp_path)
    monkeypatch.setattr(app, "RATING_SNAPSHOT", serving.load_snapshot(folder, database))
    monkeypatch.setattr(app, "STRIKING_PREVIEW", None)
    raw = raw_report(database)
    response = app.route(database, target())
    assert response["rating"]["status"] == "available" and response["rating"]["score"] == 80
    assert response["metrics"] == raw["metrics"]
    assert response["summary"] == raw["summary"]
    assert without_updates(response["history"]) == raw["history"]
    assert [item["rating_update"]["change"] for item in response["history"]] == [4, None]
    for item in response["history"]:
        update = item["rating_update"]
        assert update["date"] == item["date"]
        assert update["scope"] == "post-date batch" and update["experimental"] is True
        assert update["version"] == serving.VERSION


def test_same_date_multiple_bouts_get_only_one_post_batch_delta(tmp_path, monkeypatch):
    database, folder = site_snapshot(tmp_path, same_day=True)
    monkeypatch.setattr(app, "RATING_SNAPSHOT", serving.load_snapshot(folder, database))
    response = app.route(database, target("2026-03-08"))
    assert len(response["history"]) == 2
    annotated = [item for item in response["history"] if "rating_update" in item]
    assert len(annotated) == 1
    assert annotated[0] is response["history"][0]
    assert annotated[0]["rating_update"]["date"] == "2026-03-07"
    assert response["rating"]["bouts"] == 2


def test_cutoff_excludes_same_date_score_and_handles_unavailable_states(tmp_path, monkeypatch):
    database, folder = site_snapshot(tmp_path)
    monkeypatch.setattr(app, "RATING_SNAPSHOT", serving.load_snapshot(folder, database))
    for before, score in (("2026-03-07", None), ("2026-03-08", 76),
                           ("2026-09-20", 76), ("2026-09-21", 80)):
        response = app.route(database, target(before))
        assert response["rating"]["score"] == score
        assert all(item["rating_update"]["date"] < before for item in response["history"]
                   if "rating_update" in item)
    later = app.route(database, target("2026-11-05"))
    assert later["rating"]["score"] == 80
    assert later["rating"]["before"] == "2026-11-05"
    assert later["rating"]["snapshot_before"] == "2026-11-04"


def test_saved_model_is_not_carried_forward_past_uncovered_bouts(tmp_path):
    database, _ = site_snapshot(tmp_path)

    class EarlierSnapshot:
        def __init__(self):
            self.metadata = {"before_exclusive": "2026-09-20"}

        def estimate(self, path, report):
            assert report["before"] == "2026-11-05"
            return {"status": "unsupported_cutoff"}

    result = app.estimate_on_saved_data(EarlierSnapshot(), database, raw_report(database, "2026-11-05"))
    assert result["status"] == "unsupported_cutoff"


def test_comparison_and_windows_use_the_same_career_rating(tmp_path, monkeypatch):
    database, folder = site_snapshot(tmp_path)
    monkeypatch.setattr(app, "RATING_SNAPSHOT", serving.load_snapshot(folder, database))
    career = app.route(database, target())["rating"]
    for window in (3, 5, 10):
        response = app.route(database, target(window=window))
        assert response["rating"] == career
        assert response["metrics"] == raw_report(database, window=window)["metrics"]
    comparison = app.route(database, f"/api/compare?a={A}&b={B}&before=2026-09-21&window=3")
    a, b = comparison["fighters"]
    assert a["rating"] == career
    assert b["rating"]["score"] == 73
    assert all(item["rating_update"]["version"] == serving.VERSION for fighter in (a, b)
               for item in fighter["history"])


def test_striking_preview_remains_an_independent_optional_field(tmp_path, monkeypatch):
    database, folder = site_snapshot(tmp_path)
    monkeypatch.setattr(app, "RATING_SNAPSHOT", serving.load_snapshot(folder, database))
    calls = []

    class ExistingStrikingPreview:
        def estimate(self, path, report):
            calls.append((path, report["id"], report["window"]))
            return {"status": "available", "estimate": .47, "experimental": True}

    monkeypatch.setattr(app, "STRIKING_PREVIEW", ExistingStrikingPreview())
    response = app.route(database, target(window=5))
    assert response["rating"]["score"] == 80
    assert response["experimental_striking"]["estimate"] == .47
    assert calls == [(database, A, 5)]


def test_startup_loads_snapshot_once_without_fitting_or_socket_binding(tmp_path, monkeypatch):
    database, folder = site_snapshot(tmp_path)
    original_loader = serving.load_snapshot
    calls = []

    def load_once(path, bound_database):
        calls.append((path, bound_database))
        return original_loader(path, bound_database)

    class LocalServer:
        def __init__(self, *args):
            self.closed = False

        def serve_forever(self):
            pass

        def server_close(self):
            self.closed = True

    monkeypatch.setattr(app, "RATING_SNAPSHOT", None)
    monkeypatch.setattr(app, "STRIKING_PREVIEW", None)
    monkeypatch.setattr(app, "ThreadingHTTPServer", LocalServer)
    monkeypatch.setattr(serving, "load_snapshot", load_once)
    monkeypatch.setattr("sys.argv", ["upset", "--database", str(database), "--rating-snapshot", str(folder)])
    app.main()
    assert calls == [(folder, database)]
    for _ in range(3):
        assert app.route(database, target())["rating"]["score"] == 80
    assert len(calls) == 1


def test_startup_rejects_invalid_rating_binding_before_server_creation(tmp_path, monkeypatch):
    database, folder = site_snapshot(tmp_path)
    manifest = json.loads((folder/"manifest.json").read_text())
    manifest["database_sha256"] = "0"*64
    (folder/"manifest.json").write_text(json.dumps(manifest))

    def unexpected_server(*args):
        raise AssertionError("Server must not start with an invalid rating snapshot.")

    monkeypatch.setattr(app, "RATING_SNAPSHOT", None)
    monkeypatch.setattr(app, "ThreadingHTTPServer", unexpected_server)
    monkeypatch.setattr("sys.argv", ["upset", "--database", str(database), "--rating-snapshot", str(folder)])
    with pytest.raises(SystemExit) as error:
        app.main()
    assert error.value.code == 2
