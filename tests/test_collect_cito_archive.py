"""Archive acquisition must resume, bound its calls, and expose missing data."""

import json

import pytest

from upset.data.collect_cito_archive import collect_archive_cards, collect_inventory


class Response:
    status_code = 200

    def __init__(self, payload):
        self.payload = payload

    def json(self):
        return self.payload


def _event(slug, day, stats=True):
    return {"id": slug + "-id", "slug": slug, "eventDate": day,
            "hasStats": stats, "status": "completed"}


def _page(events, more):
    return {"success": True, "data": {"events": events,
                                      "pagination": {"hasNextPage": more}}}


def test_inventory_caches_pages_and_only_completes_after_last_page(tmp_path):
    one = _page([_event("ufc-2026", "2026-09-01")], True)
    two = _page([_event("ufc-2025", "2025-09-01", False)], False)
    calls = []

    def get(url, **kwargs):
        calls.append(url)
        return Response(one if "page=1" in url else two)

    partial = collect_inventory(tmp_path, "secret-key", get, max_pages=1, delay=0)
    assert partial["status"].startswith("partial")
    assert not (tmp_path / "inventory/manifest.json").exists()
    finished = collect_inventory(tmp_path, "secret-key", get, max_pages=2, delay=0)
    assert finished["events"] == 2
    assert finished["api_calls"] == 1
    assert len(calls) == 2
    manifest = json.loads((tmp_path / "inventory/manifest.json").read_text())
    assert manifest["coverage_verified"] is False
    assert len(manifest["page_sha256"]) == 2
    assert "secret-key" not in (tmp_path / "inventory/pages/page-0001.json").read_text()


def test_inventory_preserves_duplicate_slug_and_flags_collision(tmp_path):
    first = _page([_event("repeat", "2026-09-01")], True)
    second = _page([_event("repeat", "2025-09-01")], False)
    responses = iter((first, second))
    result = collect_inventory(tmp_path, "secret", lambda *a, **k: Response(
        next(responses)), max_pages=2, delay=0)
    assert result["events"] == 2
    manifest = json.loads((tmp_path / "inventory/manifest.json").read_text())
    assert manifest["slug_collisions"] == ["repeat"]


def test_inventory_rejects_repeated_identical_row(tmp_path):
    repeated = _event("same", "2026-09-01")
    with pytest.raises(ValueError, match="Repeated event listing row"):
        collect_inventory(tmp_path, "secret", lambda *a, **k: Response(
            _page([repeated, repeated], False)), delay=0)


def test_one_card_then_resume_and_report_provider_statless(tmp_path):
    events = [_event("ufc-a", "2026-09-20"),
              _event("ufc-b", "2026-09-13"),
              _event("ufc-no-stats", "2026-09-06", False)]
    collect_inventory(tmp_path, "secret", lambda *a, **k: Response(
        _page(events, False)), delay=0)
    calls = []

    def get(url, **kwargs):
        calls.append(url)
        slug = url.split("/events/")[1].split("/")[0]
        if url.endswith("/bouts"):
            return Response({"success": True, "data": {"bouts": [
                {"id": slug + "-bout", "eventSlug": slug}]}})
        if url.endswith("/stats"):
            return Response({"success": True, "data": {"boutStats": [
                {"boutId": slug + "-bout"}]}})
        return Response({"success": True, "data": {"slug": slug}})

    first = collect_archive_cards(tmp_path, "secret", get, from_date="2026-09-01",
                                  through_date="2026-09-30", delay=0)
    assert first["attempted_this_run"] == 1
    assert first["captured"] == 1
    second = collect_archive_cards(tmp_path, "secret", get, from_date="2026-09-01",
                                   through_date="2026-09-30", delay=0,
                                   max_cards=2)
    assert second["attempted_this_run"] == 1
    assert second["captured"] == 2
    assert second["provider_has_no_stats"] == 1
    assert len(calls) == 6
    progress = json.loads((tmp_path / "collection_progress.json").read_text())
    assert progress["cards"]["2026-09-06/ufc-no-stats/ufc-no-stats-id"][
        "status"] == "provider_has_no_stats"
    assert all(row["coverage_verified"] is False for row in (first, second))


def test_failed_card_is_recorded_not_silently_retried(tmp_path):
    collect_inventory(tmp_path, "secret", lambda *a, **k: Response(_page([
        _event("ufc-a", "2026-09-20")], False)), delay=0)
    calls = []

    def denied(url, **kwargs):
        calls.append(url)
        if url.endswith("/stats"):
            result = Response({"error": {"type": "forbidden", "code": "NO_ACCESS",
                                                 "message": "secret"}})
            result.status_code = 403
            return result
        if url.endswith("/bouts"):
            return Response({"success": True, "data": {"bouts": [
                {"id": "one", "eventSlug": "ufc-a"}]}})
        return Response({"success": True, "data": {"slug": "ufc-a"}})

    args = {"from_date": "2026-09-01", "through_date": "2026-09-30",
            "delay": 0}
    result = collect_archive_cards(tmp_path, "secret", denied, **args)
    assert result["failed"] == 1
    assert "secret" not in (tmp_path / "collection_progress.json").read_text()
    assert collect_archive_cards(tmp_path, "secret", denied, **args)[
        "attempted_this_run"] == 0
    assert len(calls) == 3
    resumed = collect_archive_cards(tmp_path, "secret", denied, retry_failed=True,
                                    **args)
    assert resumed["attempted_this_run"] == 1
    assert calls[-1].endswith("/stats")  # The first two responses stayed cached.
    assert len(calls) == 4


def test_statless_stray_does_not_block_same_slug_real_card(tmp_path):
    events = [_event("ufc-315", "2026-05-10", False),
              _event("ufc-315", "2025-05-10", True)]
    collect_inventory(tmp_path, "secret", lambda *a, **k: Response(
        _page(events, False)), delay=0)
    calls = []

    def get(url, **kwargs):
        calls.append(url)
        if url.endswith("/bouts"):
            return Response({"success": True, "data": {"bouts": [
                {"id": "real-bout", "eventSlug": "ufc-315"}]}})
        if url.endswith("/stats"):
            return Response({"success": True, "data": {"boutStats": [
                {"boutId": "real-bout"}]}})
        return Response({"success": True, "data": {"slug": "ufc-315"}})

    result = collect_archive_cards(tmp_path, "secret", get, from_date="2025-01-01",
                                   through_date="2026-12-31", delay=0)
    assert result["captured"] == 1
    assert result["provider_has_no_stats"] == 1
    assert result["ambiguous_slug"] == 0
    assert len(calls) == 3
