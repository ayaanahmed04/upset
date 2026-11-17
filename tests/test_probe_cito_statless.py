"""Probe metadata exclusions without changing or refetching captured cards."""

import json

from upset.data.collect_cito_archive import collect_inventory
from upset.data.probe_cito_statless import probe_statless


class Response:
    status_code = 200

    def __init__(self, data):
        self.data = data

    def json(self):
        return {"success": True, "data": self.data}


def test_probes_only_past_statless_ufc_and_resumes_without_calls(tmp_path):
    events = [{"id": str(i), "slug": slug, "eventDate": day, "hasStats": stats}
              for i, (slug, day, stats) in enumerate([
                  ("ufc-statless-a", "2024-05-11", False),
                  ("ufc-statless-b", "2025-03-15", False),
                  ("ufc-captured", "2025-03-22", True),
                  ("dwcs-10-5", "2026-09-08", False),
                  ("ufc-future", "2026-10-03", False)])]
    collect_inventory(tmp_path, "secret", lambda *a, **k: Response(events), delay=0)
    inventory_before = (tmp_path / "inventory/manifest.json").read_bytes()
    output = tmp_path / "probes"
    calls = []

    def get(url, **kwargs):
        calls.append(url)
        event = next(e for e in events if f"/{e['slug']}/stats" in url)
        if event["slug"] == "ufc-statless-b":
            raise OSError("secret must not be logged")
        return Response({"event": event, "boutStats": [{"id": "total"}],
                         "roundStats": [{"id": "round"}]})

    report = probe_statless(tmp_path, output, "secret", get,
                            through_date="2026-09-28", max_events=1, delay=0,
                            log=lambda *a, **k: None)
    assert report["target_events"] == 2
    assert report["examined_events"] == 1
    assert report["statuses"] == {"stats_returned": 1}
    report = probe_statless(tmp_path, output, "secret", get,
                            through_date="2026-09-28", delay=0, log=lambda *a, **k: None)
    assert report["statuses"] == {"stats_returned": 1, "requires_provider_review": 1}
    assert report["api_calls_this_run"] == 1
    assert len(calls) == 2
    assert "secret" not in (output / "ufc-statless-b.json").read_text()
    assert (tmp_path / "inventory/manifest.json").read_bytes() == inventory_before
    assert not (tmp_path / "collection_progress.json").exists()
    report = probe_statless(tmp_path, output, "secret", get,
                            through_date="2026-09-28", delay=0, log=lambda *a, **k: None)
    assert report["api_calls_this_run"] == 0


def test_wrong_event_response_is_preserved_but_not_accepted(tmp_path):
    event = {"id": "1", "slug": "ufc-test", "eventDate": "2024-01-01", "hasStats": False}
    collect_inventory(tmp_path, "secret", lambda *a, **k: Response([event]), delay=0)
    report = probe_statless(tmp_path, tmp_path / "probes", "secret",
                            lambda *a, **k: Response({"event": {**event, "id": "wrong"},
                                                     "boutStats": [1], "roundStats": [1]}),
                            through_date="2026-09-28", delay=0, log=lambda *a, **k: None)
    assert report["events"][0]["event_identity_matches"] is False
    assert report["statuses"] == {"requires_provider_review": 1}
    assert json.loads((tmp_path / "probes/ufc-test.json").read_text())["response"]
