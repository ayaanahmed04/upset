"""Stats recovery must keep source evidence and avoid repeated stats requests."""

import json

import pytest

from upset.data.collect_cito_archive import collect_archive_cards, collect_inventory
from upset.data.probe_cito_statless import probe_statless
from upset.data.recover_cito_statless import recover_cards


class Response:
    status_code = 200

    def __init__(self, data):
        self.data = data

    def json(self):
        return {"success": True, "data": self.data}


def _prepare(root):
    event = {"id": "event-1", "slug": "ufc-test-card", "eventDate": "2024-04-27",
             "hasStats": False, "status": "completed"}
    bout = {"id": "bout-1", "eventSlug": event["slug"]}
    collect_inventory(root, "secret", lambda *a, **k: Response([event]), delay=0)
    collect_archive_cards(root, "secret", lambda *a, **k: pytest.fail("No calls for statless"),
                          from_date="2024-01-01", through_date="2024-12-31", delay=0)
    probes = root / "probes"
    probe_statless(root, probes, "secret", lambda *a, **k: Response({
        "event": event, "bouts": [bout], "boutStats": [{"boutId": "bout-1"}],
        "roundStats": [{"boutId": "bout-1", "round": 1}]}),
        through_date="2026-09-28", delay=0, log=lambda *a, **k: None)
    return event, bout, probes


def test_recovery_reuses_stats_and_keeps_inventory_and_observation_time(tmp_path):
    event, bout, probes = _prepare(tmp_path)
    original_inventory = (tmp_path / "inventory/manifest.json").read_bytes()
    original_probe = (probes / "ufc-test-card.json").read_bytes()
    calls = []

    def get(url, **kwargs):
        calls.append(url)
        assert not url.endswith("/stats")
        return Response([bout] if url.endswith("/bouts") else {**event, "bouts": [bout]})

    report = recover_cards(tmp_path, probes, "secret", get, delay=0, log=lambda *a, **k: None)
    assert report["recovered_this_run"] == 1
    assert report["api_calls_this_run"] == 2
    assert report["remaining_target_cards"] == 0
    assert len(calls) == 2
    cached = json.loads((tmp_path / "cards/ufc-test-card/stats.json").read_text())
    probe = json.loads(original_probe)
    assert cached["response"] == probe["response"]
    assert cached["observed_at_utc"] == probe["observed_at_utc"]
    assert cached["source_url"] == probe["source_url"]
    assert (probes / "ufc-test-card.json").read_bytes() == original_probe
    assert (tmp_path / "inventory/manifest.json").read_bytes() == original_inventory
    report = recover_cards(tmp_path, probes, "secret", get, delay=0, log=lambda *a, **k: None)
    assert report["attempted_this_run"] == 0
    assert report["api_calls_this_run"] == 0


def test_changed_probe_fails_before_requests_or_progress_changes(tmp_path):
    _, _, probes = _prepare(tmp_path)
    before = (tmp_path / "collection_progress.json").read_bytes()
    path = probes / "ufc-test-card.json"
    path.write_text(path.read_text() + " ")
    with pytest.raises(ValueError, match="Probe changed"):
        recover_cards(tmp_path, probes, "secret", lambda *a, **k: pytest.fail("No requests"),
                      delay=0, log=lambda *a, **k: None)
    assert (tmp_path / "collection_progress.json").read_bytes() == before


def test_partial_failure_resumes_and_does_not_expose_secret(tmp_path):
    event, bout, probes = _prepare(tmp_path)

    def fail(*args, **kwargs):
        raise OSError("secret")

    report = recover_cards(tmp_path, probes, "secret", fail, delay=0, log=lambda *a, **k: None)
    assert report["recovered_this_run"] == 0
    assert report["remaining_target_cards"] == 1
    assert "secret" not in json.dumps(report)
    report = recover_cards(tmp_path, probes, "secret", lambda url, **k: Response(
        [bout] if url.endswith("/bouts") else {**event, "bouts": [bout]}),
        delay=0, log=lambda *a, **k: None)
    assert report["recovered_this_run"] == 1
    assert report["api_calls_this_run"] == 2
