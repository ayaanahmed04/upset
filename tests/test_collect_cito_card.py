"""The one-card pilot must preserve raw evidence and fail on partial access."""

import json

import pytest

from upset.data.collect_cito_card import collect_card
from upset.data.collect_cito_rounds import RoundDownloadError


class Response:
    def __init__(self, data, status_code=200):
        self.data = data
        self.status_code = status_code

    def json(self):
        return self.data


def _payloads(slug):
    return [
        {"success": True, "data": {"id": "event-1", "slug": slug}},
        {"success": True, "data": {"bouts": [
            {"id": f"bout-{n}", "eventSlug": slug} for n in range(12)
        ]}},
        {"success": True, "data": {"boutStats": [{"boutId": "bout-0"}]}},
    ]


def test_full_card_is_saved_once_with_all_listed_bouts_and_hashes(tmp_path):
    slug = "ufc-2026-recent"
    responses = iter(_payloads(slug))
    calls = []

    def get(url, *, headers, timeout):
        calls.append((url, headers, timeout))
        return Response(next(responses))

    output = tmp_path / slug
    report = collect_card(slug, output, "private-api-key", get, delay=0)
    assert report["listed_bouts"] == 12  # The old discovery probe printed only 10.
    assert report["coverage_verified"] is False
    assert report["api_calls"] == 3
    assert [call[0].split("/")[-1] for call in calls] == [slug, "bouts", "stats"]
    for kind in ("event", "bouts", "stats"):
        assert len(report["sha256"][kind]) == 64
        assert "private-api-key" not in (output / f"{kind}.json").read_text()
    assert json.loads((output / "manifest.json").read_text()) == report
    with pytest.raises(ValueError, match="already captured"):
        collect_card(slug, output, "private-api-key", get, delay=0)
    assert len(calls) == 3


def test_denied_stats_keeps_metadata_and_retry_makes_only_one_call(tmp_path):
    slug = "ufc-2026-recent"
    output = tmp_path / slug
    first = iter([Response(p) for p in _payloads(slug)[:2]] + [
        Response({"error": {"type": "forbidden", "code": "HISTORY_WINDOW_EXCEEDED",
                            "message": "never print this"}}, 403),
    ])

    with pytest.raises(RoundDownloadError, match="HISTORY_WINDOW_EXCEEDED") as denied:
        collect_card(slug, output, "private-api-key", lambda *a, **k: next(first),
                     delay=0)
    assert "never print this" not in str(denied.value)
    assert (output / "event.json").exists()
    assert (output / "bouts.json").exists()
    assert not (output / "manifest.json").exists()

    calls = []

    def get(url, **kwargs):
        calls.append(url)
        return Response(_payloads(slug)[2])

    report = collect_card(slug, output, "private-api-key", get, delay=0)
    assert report["api_calls"] == 1
    assert calls == [f"https://api.citoapi.com/api/v1/ufc/events/{slug}/stats"]
    assert report["listed_bouts"] == 12


@pytest.mark.parametrize("mutate", [
    lambda p: p[1]["data"]["bouts"].append(p[1]["data"]["bouts"][0]),
    lambda p: p[1]["data"].update(pagination={"hasNextPage": True}),
    lambda p: p[1]["data"]["bouts"][0].update(eventSlug="other-event"),
])
def test_rejects_incomplete_or_inconsistent_bout_list(tmp_path, mutate):
    slug = "ufc-2026-recent"
    payloads = _payloads(slug)
    mutate(payloads)
    responses = iter(payloads)
    with pytest.raises(RoundDownloadError):
        collect_card(slug, tmp_path / slug, "private-api-key",
                     lambda *a, **k: Response(next(responses)), delay=0)
    assert not (tmp_path / slug / "bouts.json").exists()


def test_rejects_unsafe_slug_without_network_or_files(tmp_path):
    with pytest.raises(ValueError, match="slug"):
        collect_card("../other", tmp_path / "data", "private-api-key",
                     lambda *a, **k: pytest.fail("Unexpected API call"), delay=0)
    assert not (tmp_path / "data").exists()


def test_network_failure_does_not_include_key_in_error(tmp_path):
    def get(*args, **kwargs):
        raise OSError("request headers contain private-api-key")

    with pytest.raises(RoundDownloadError, match="OSError") as failure:
        collect_card("ufc-2026-recent", tmp_path / "data", "private-api-key",
                     get, delay=0)
    assert "private-api-key" not in str(failure.value)
