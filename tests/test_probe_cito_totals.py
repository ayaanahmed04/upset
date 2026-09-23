"""Verify that a Cito totals probe saves data and reveals only its shape."""

import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

import pytest

from upset.data.collect_cito_rounds import RoundDownloadError
from upset.data.probe_cito_totals import probe_one


def response(payload, status=200):
    return SimpleNamespace(status_code=status, json=lambda: payload)


def test_totals_probe_saves_once_and_reads_back_without_another_request():
    payload = {"success": True, "data": [
        {"boutId": "bout-1", "fighterSlug": "alpha", "knockdowns": 2},
        {"boutId": "bout-1", "fighterSlug": "beta", "knockdowns": 0},
    ]}
    calls = []

    def get(url, *, headers, timeout):
        calls.append((url, headers, timeout))
        return response(payload)

    with TemporaryDirectory() as folder:
        output = Path(folder)
        result = probe_one("bout-1", output, "secret", get)
        assert result == {
            "bout_id": "bout-1", "fetched": True,
            "shape": {
                "response_keys": ["data", "success"], "data_type": "list",
                "row_count": 2,
                "first_row_keys": ["boutId", "fighterSlug", "knockdowns"],
            },
        }
        saved = json.loads((output / "bout-1.json").read_text())
        assert saved["response"] == payload
        assert "secret" not in str(saved)
        again = probe_one("bout-1", output, "secret", get)
        assert again["fetched"] is False
        assert len(calls) == 1
        assert calls[0][0].endswith("/bouts/bout-1/stats")


@pytest.mark.parametrize("payload,status", [
    ({"data": []}, 200),
    ({"data": [{"boutId": "other"}]}, 200),
    ({"error": {"code": "HISTORY_WINDOW_EXCEEDED"}}, 403),
    ({"data": [{"note": "secret"}]}, 200),
])
def test_totals_probe_does_not_cache_bad_response(payload, status):
    with TemporaryDirectory() as folder:
        directory = Path(folder)
        with pytest.raises(RoundDownloadError):
            probe_one(
                "bout-1", directory, "secret",
                lambda *args, **kwargs: response(payload, status),
            )
        assert not (directory / "bout-1.json").exists()


def test_totals_probe_rejects_corrupt_cache_without_new_request():
    with TemporaryDirectory() as folder:
        path = Path(folder) / "bout-1.json"
        path.write_text("not json", encoding="utf-8")
        with pytest.raises(RoundDownloadError, match="Invalid cached"):
            probe_one(
                "bout-1", Path(folder), "secret",
                lambda *args, **kwargs: pytest.fail("Cache should be read"),
            )
