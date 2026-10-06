"""Fighter collection is bounded, resumable and separate from identity acceptance."""

import json

import pytest

from upset.data.collect_cito_archive import _digest
from upset.data.collect_cito_fighter_bundles import bundle_targets, collect_bundles

PID = "00000000-0000-4000-8000-000000000001"


class Response:
    def __init__(self, data, status=200, headers=None):
        self.data, self.status_code, self.headers = data, status, headers or {}

    def json(self):
        return self.data


def _current(tmp_path):
    path = tmp_path / "current"
    path.mkdir()
    (path / "review.json").write_text(json.dumps({"unresolved_fighter_identities": [
        {"cito_fighter_id": PID, "source_names": ["Alex"], "source_slugs": ["alex-old"],
         "profile_observations": [{"profile": {"id": PID, "slug": "alex"}}]}]}))
    (path / "manifest.json").write_text(json.dumps({"output_sha256": {"review.json": _digest(path / "review.json")}}))
    return path


def test_capture_once_resume_and_zero_identity_acceptance(tmp_path):
    current, output = _current(tmp_path), tmp_path / "bundles"
    calls = []
    def get(url, **kwargs):
        calls.append(url)
        return Response({"success": True, "data": {"id": PID, "name": "Alex"}})
    result = collect_bundles(current, output, "secret", get, delay=0, log=lambda *a, **k: None)
    assert len(calls) == 3 and calls[0].endswith("/fighters/alex")
    assert result["target_requests"] == 3 and result["remaining_targets"] == 0
    assert result["identity_links_added"] == 0 and result["training_ready"] is False
    saved = {p: p.read_bytes() for p in (output / "fighters").rglob("*.json")}
    again = collect_bundles(current, output, "secret", lambda *a, **k: pytest.fail("Unexpected request"),
                            delay=0, log=lambda *a, **k: None)
    assert again["api_calls_this_run"] == 0
    assert all(p.read_bytes() == b for p, b in saved.items())


def test_request_cap_resumes_only_unsaved_targets_and_obeys_header_limit(tmp_path):
    current, output = _current(tmp_path), tmp_path / "bundles"
    get = lambda *a, **k: Response({"data": {"id": PID}}, headers={"X-RateLimit-Limit": "10"})
    first = collect_bundles(current, output, "secret", get, max_requests=1, delay=0, log=lambda *a, **k: None)
    assert first["remaining_targets"] == 2
    delays = []
    second = collect_bundles(current, output, "secret", get, delay=0, sleep=delays.append, log=lambda *a, **k: None)
    assert second["api_calls_this_run"] == 2 and second["remaining_targets"] == 0
    assert delays == [6.2]


@pytest.mark.parametrize("status", [401, 403, 429])
def test_denied_access_or_rate_limit_stops_and_retains_response(tmp_path, status):
    current, output = _current(tmp_path), tmp_path / "bundles"
    result = collect_bundles(current, output, "secret", lambda *a, **k: Response({"error": "denied"}, status),
                              delay=0, log=lambda *a, **k: None)
    assert result["api_calls_this_run"] == 1 and result["remaining_targets"] == 2
    assert result["paused_reason"] == "access_or_rate_limit_response"
    assert (output / "fighters" / PID / "profile.json").exists()


def test_wrong_provider_profile_is_not_followed_or_linked(tmp_path):
    current, output = _current(tmp_path), tmp_path / "bundles"
    result = collect_bundles(current, output, "secret", lambda *a, **k: Response({"data": {"id": "wrong"}}),
                              delay=0, log=lambda *a, **k: None)
    assert result["api_calls_this_run"] == 1
    assert result["statuses"] == {"different_provider_identity": 1, "skipped_after_identity_conflict": 2}
    assert result["identity_links_added"] == 0


def test_tampered_review_is_rejected(tmp_path):
    current = _current(tmp_path)
    (current / "review.json").write_text("tampered")
    with pytest.raises(ValueError, match="hash differs"):
        bundle_targets(current)


def test_key_is_never_saved(tmp_path):
    current, output = _current(tmp_path), tmp_path / "bundles"
    with pytest.raises(ValueError, match="API key"):
        collect_bundles(current, output, "secret", lambda *a, **k: Response({"data": {"echo": "secret"}}),
                        delay=0, log=lambda *a, **k: None)
    assert not (output / "fighters").exists()
