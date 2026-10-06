"""Gap probes cache failures, cap requests and never claim reconciled coverage."""

import json

import pytest

from upset.data.collect_cito_card import BASE_URL
from upset.data.probe_cito_archive_gaps import probe_gaps


class Response:
    def __init__(self, payload, status=200):
        self.payload, self.status_code = payload, status

    def json(self):
        return self.payload


def _plan(tmp_path, *, fallback=False, count=1):
    targets = []
    for i in range(count):
        identifier = f"bout-{i}"
        target = {"scope": "bouts", "identifier": identifier, "endpoint": "rounds",
                  "source_url": f"{BASE_URL}/bouts/{identifier}/rounds", "reason": "missing_rounds"}
        if fallback:
            target["fallback_identifier"] = f"historical-{i}"
        targets.append(target)
    path = tmp_path / "immutable/plan.json"
    path.parent.mkdir()
    path.write_text(json.dumps({"schema_version": 1, "requests": targets}))
    return path


def test_cap_resume_and_cache_have_actual_request_counts(tmp_path):
    plan = _plan(tmp_path, count=2)
    calls = []

    def get(url, **kwargs):
        calls.append(url)
        return Response({"success": True, "data": [{"boutId": url.split("/")[-2]}]})

    output = tmp_path / "raw"
    first = probe_gaps(plan, output, "SECRET", get, max_requests=1, delay=0, log=lambda *a, **k: None)
    assert first["api_calls_this_run"] == 1
    assert first["remaining_primary_targets"] == 1
    second = probe_gaps(plan, output, "SECRET", get, max_requests=1, delay=0, log=lambda *a, **k: None)
    assert second["api_calls_this_run"] == 1
    assert second["remaining_primary_targets"] == 0
    third = probe_gaps(plan, output, "SECRET", get, delay=0, log=lambda *a, **k: None)
    assert third["api_calls_this_run"] == 0
    assert len(calls) == 2
    assert third["coverage_verified"] is False
    assert all("SECRET" not in path.read_text() for path in output.rglob("*.json"))


def test_fallback_only_after_missing_primary_and_caches_both_responses(tmp_path):
    plan = _plan(tmp_path, fallback=True)
    calls = []

    def get(url, **kwargs):
        calls.append(url)
        if "historical" not in url:
            return Response({"success": False, "error": {"code": "NOT_FOUND"}}, 404)
        return Response({"success": True, "data": {"rounds": [{"boutId": "historical-0"}]}})

    output = tmp_path / "raw"
    report = probe_gaps(plan, output, "SECRET", get, delay=0, log=lambda *a, **k: None)
    assert len(calls) == report["api_calls_this_run"] == 2
    assert report["requests"][1]["fallback"] is True
    assert report["requests"][1]["status"] == "rows_returned_for_review"
    assert len(list((output / "requests").glob("*.json"))) == 2
    assert probe_gaps(plan, output, "SECRET", get, delay=0, log=lambda *a, **k: None)["api_calls_this_run"] == 0


def test_success_skips_fallback_and_access_errors_stop(tmp_path):
    plan = _plan(tmp_path, fallback=True, count=2)
    calls = []

    def get(url, **kwargs):
        calls.append(url)
        if "bout-0" in url:
            return Response({"success": True, "data": [{"boutId": "bout-0"}]})
        return Response({"success": False}, 429)

    report = probe_gaps(plan, tmp_path / "raw", "SECRET", get, delay=0, log=lambda *a, **k: None)
    assert len(calls) == 2
    assert not any(r["fallback"] for r in report["requests"])
    assert report["requests"][-1]["http_status"] == 429


def test_wrong_bout_id_and_timeout_are_visible_without_raising_completion_claim(tmp_path):
    plan = _plan(tmp_path, count=2)

    def get(url, **kwargs):
        if "bout-0" in url:
            return Response({"success": True, "data": [{"boutId": "wrong"}]})
        raise OSError("connection error")

    report = probe_gaps(plan, tmp_path / "raw", "SECRET", get, delay=0, log=lambda *a, **k: None)
    assert report["statuses"] == {"requires_provider_review": 2}
    assert report["requests"][0]["contradictory_bout_id"] is True
    assert report["requests"][1]["request_error"] == "OSError"


def test_plan_url_injection_and_leaked_key_are_rejected(tmp_path):
    plan = _plan(tmp_path)
    targets = json.loads(plan.read_text())
    targets["requests"][0]["identifier"] = "../other"
    plan.write_text(json.dumps(targets))
    with pytest.raises(ValueError, match="unsafe identifier"):
        probe_gaps(plan, tmp_path / "raw", "SECRET", lambda *a, **k: pytest.fail("No request allowed"))
    targets["requests"][0]["identifier"] = "bout-0"
    plan.write_text(json.dumps(targets))
    with pytest.raises(ValueError, match="contains API key"):
        probe_gaps(plan, tmp_path / "raw", "SECRET",
                   lambda *a, **k: Response({"success": True, "data": [{"note": "SECRET"}]}))
    assert not list((tmp_path / "raw").rglob("*.json"))
