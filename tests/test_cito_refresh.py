"""Later-card refresh must preserve the existing cohort and expose source gaps."""

import json
from copy import deepcopy
from datetime import UTC, date, datetime

import pytest
from test_collect_cito_archive import Response, _event, _page
from test_export_cito_current_archive import _export, _fixture, _sample

from upset.data.collect_cito_archive import _digest
from upset.data.export_cito_refresh import export_refresh
from upset.data.refresh_cito_current import refresh

NOW = datetime(2026, 10, 5, tzinfo=UTC)


def source(*, unknown=False, bad_rounds=False):
    bout, event, totals, rounds = _sample("later", unknown=unknown)
    bout["eventSlug"] = event["slug"] = "ufc-later"
    event["id"] = "ufc-later-id"
    event["eventDate"] = "2026-10-03"
    event["hasStats"] = False
    event["bouts"] = [bout]
    return {"event": {"data": event}, "bouts": {"data": [bout]},
            "stats": {"data": {"event": event, "bouts": [bout], "boutStats": totals,
                                 "roundStats": rounds[:1] if bad_rounds else rounds}}}


def getter(payloads, listing=None, *, fail_stats=False):
    calls = []
    listing = listing or [_event("ufc-later", "2026-10-03", False)]

    def get(url, **kwargs):
        calls.append(url)
        if "?page=" in url:
            return Response(_page(listing, False))
        if fail_stats and url.endswith("/stats"):
            raise OSError("failed-secret-key")
        kind = "bouts" if url.endswith("/bouts") else "stats" if url.endswith("/stats") else "event"
        return Response(deepcopy(payloads[kind]))

    return get, calls


def collect(root, payloads=None, **kwargs):
    get, calls = getter(payloads or source(), **kwargs)
    result = refresh(root, "secret-key", get, from_date="2026-09-27", through_date="2026-10-05",
                     delay=0, today=date(2026, 10, 5), log=lambda _: None)
    return result, calls


def base(root, monkeypatch):
    paths = _fixture(root, monkeypatch)
    current = root / "current"
    _export(paths, current)
    (current / "fighter_registry.json").write_bytes((paths[3] / "fighter_registry.json").read_bytes())
    (current / "identity_link_evidence.jsonl").write_text('{"basis": "prior reviewed link"}\n')
    manifest = json.loads((current / "manifest.json").read_text())
    for name in ("fighter_registry.json", "identity_link_evidence.jsonl"):
        manifest["output_sha256"][name] = _digest(current / name)
    (current / "manifest.json").write_text(json.dumps(manifest))
    return current, paths[4] / "fights_identified.jsonl", paths[5]


def test_false_stat_flag_is_collected_and_resume_makes_no_requests(tmp_path):
    report, calls = collect(tmp_path)
    assert len(calls) == report["api_calls_this_run"] == 4
    assert report["statuses"] == {"captured": 1} and report["remaining_cards"] == 0
    binding = (tmp_path / "refresh_report.json").read_bytes()
    again, calls = collect(tmp_path)
    assert calls == [] and again["api_calls_this_run"] == 0
    assert (tmp_path / "refresh_report.json").read_bytes() == binding
    raw = tmp_path / "cards/ufc-later/stats.json"
    raw.write_text(raw.read_text() + " ")
    with pytest.raises(ValueError, match="Raw card hash differs"):
        collect(tmp_path)


def test_failure_is_counted_redacted_and_cached_parts_resume(tmp_path):
    report, calls = collect(tmp_path, fail_stats=True)
    assert report["api_calls_this_run"] == len(calls) == 4
    assert report["statuses"] == {"failed": 1}
    assert "secret-key" not in (tmp_path / "refresh_progress.json").read_text()
    get, calls = getter(source())
    repaired = refresh(tmp_path, "secret-key", get, from_date="2026-09-27", through_date="2026-10-05",
                       retry_failed=True, delay=0, today=NOW.date(), log=lambda _: None)
    assert len(calls) == 1 and calls[0].endswith("/stats")
    assert repaired["statuses"] == {"captured": 1}


def test_other_competitions_are_explicit_and_old_archive_future_ranges_rejected(tmp_path):
    listing = [_event("dwcs-10-8", "2026-09-29", False), _event("ufc-later", "2026-10-03", False)]
    report, calls = collect(tmp_path, listing=listing)
    assert len(calls) == 4 and report["target_cards"] == 1
    assert report["excluded_listing_events"][0]["competition"] == "other_competition"
    with pytest.raises(ValueError, match="range differs"):
        refresh(tmp_path, "secret", None, from_date="2026-09-28", through_date="2026-10-05", today=NOW.date())
    with pytest.raises(ValueError, match="valid past date range"):
        refresh(tmp_path / "future", "secret", None, from_date="2026-10-05", through_date="2026-10-06", today=NOW.date())
    occupied = tmp_path / "archive"
    occupied.mkdir()
    (occupied / "collection_progress.json").write_text("{}")
    with pytest.raises(ValueError, match="occupied"):
        refresh(occupied, "secret", None, from_date="2026-09-27", through_date="2026-10-05", today=NOW.date())


def test_bounded_partial_capture_resumes_remaining_cards(tmp_path):
    listing = [_event("ufc-later", "2026-10-03", False), _event("ufc-second", "2026-10-04")]
    first = source()
    second = deepcopy(first)
    for item in (second["event"]["data"], second["stats"]["data"]["event"]):
        item.update(slug="ufc-second", id="ufc-second-id", eventDate="2026-10-04")
    for item in (second["event"]["data"]["bouts"][0], second["bouts"]["data"][0], second["stats"]["data"]["bouts"][0]):
        item.update(eventSlug="ufc-second", id="second")
    for kind in ("boutStats", "roundStats"):
        for row in second["stats"]["data"][kind]:
            row["boutId"] = "second"
    one, calls = getter(first, listing)
    two, other_calls = getter(second, listing)

    def get(url, **kwargs):
        return two(url, **kwargs) if "/ufc-second" in url else one(url, **kwargs)

    options = {"from_date": "2026-09-27", "through_date": "2026-10-05", "max_cards": 1,
               "delay": 0, "today": NOW.date(), "log": lambda _: None}
    assert refresh(tmp_path, "secret-key", get, **options)["remaining_cards"] == 1
    assert refresh(tmp_path, "secret-key", get, **options)["remaining_cards"] == 0
    assert len(calls) + len(other_calls) == 7


@pytest.mark.parametrize("unknown", [False, True])
def test_offline_overlay_preserves_old_records_and_known_links(tmp_path, monkeypatch, unknown):
    current, historical, expected = base(tmp_path, monkeypatch)
    raw = tmp_path / "refresh"
    collect(raw, source(unknown=unknown))
    before = {p: p.read_bytes() for p in tmp_path.rglob("*.json*")}
    output = tmp_path / "extended"
    report = export_refresh(current, raw, historical, output, expected_history=expected, observed_at=NOW)
    assert report["canonical_bouts_added"] == 1
    assert report["identified_bouts_added"] == (0 if unknown else 1)
    assert report["canonical_current_bouts"] == 3 and report["latest_bout"] == "2026-10-03"
    assert report["api_calls"] == 0 and report["coverage_verified"] is False
    assert all(p.read_bytes() == value for p, value in before.items())
    assert (output / "fights.jsonl").read_bytes().startswith((current / "fights.jsonl").read_bytes())
    assert (output / "fighter_registry.json").read_bytes() == (current / "fighter_registry.json").read_bytes()
    assert (output / "identity_link_evidence.jsonl").read_bytes() == (current / "identity_link_evidence.jsonl").read_bytes()
    collect(raw, source(unknown=unknown))
    assert export_refresh(current, raw, historical, output, expected_history=expected, observed_at=NOW) == report
    queue = json.loads((output / "review.json").read_text())["unresolved_fighter_identities"]
    assert len(queue) == 1
    if unknown:
        assert len(queue[0]["supporting_bouts"]) == 2
    (output / "fights.jsonl").write_text("changed")
    with pytest.raises(ValueError, match="Export hash differs"):
        export_refresh(current, raw, historical, output, expected_history=expected, observed_at=NOW)


def test_incomplete_rounds_are_quarantined_and_raw_tampering_stops_export(tmp_path, monkeypatch):
    current, historical, expected = base(tmp_path, monkeypatch)
    raw = tmp_path / "refresh"
    collect(raw, source(bad_rounds=True))
    report = export_refresh(current, raw, historical, tmp_path / "extended", expected_history=expected, observed_at=NOW)
    assert report["canonical_bouts_added"] == 0 and report["refresh_findings"] == 1
    findings = json.loads((tmp_path / "extended/review.json").read_text())["refresh_findings"]
    assert "coverage" in findings[0]["reason"]
    page = raw / "inventory/pages/page-0001.json"
    page.write_text(page.read_text() + " ")
    with pytest.raises(ValueError, match="inventory page hash differs"):
        export_refresh(current, raw, historical, tmp_path / "bad", expected_history=expected, observed_at=NOW)
    assert not (tmp_path / "bad").exists()


def test_refresh_preserves_verified_supplementary_profiles(tmp_path, monkeypatch):
    current, historical, expected = base(tmp_path, monkeypatch)
    profile = current / 'fighters_identified.jsonl'
    profile.write_text('{"source":"cito","source_fighter_id":"new-profile","name":"New fighter"}\n')
    manifest = json.loads((current / 'manifest.json').read_text())
    manifest['output_sha256'][profile.name] = _digest(profile)
    (current / 'manifest.json').write_text(json.dumps(manifest))
    raw = tmp_path / 'refresh'
    collect(raw)
    output = tmp_path / 'extended'
    report = export_refresh(current, raw, historical, output, expected_history=expected, observed_at=NOW)
    assert (output / profile.name).read_bytes() == profile.read_bytes()
    assert report['output_sha256'][profile.name] == _digest(profile)
