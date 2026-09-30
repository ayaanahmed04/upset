"""The archive audit must preserve source gaps and verify captured round rows."""

import json

from upset.data.audit_cito_archive import _competition, audit_archive
from upset.data.collect_cito_archive import collect_archive_cards, collect_inventory


class Response:
    status_code = 200

    def __init__(self, data):
        self.data = data

    def json(self):
        return {"success": True, "data": self.data}


def _archive(tmp_path, *, duplicate_total=False, missing_round=False,
             differing_name=False):
    slug = "ufc-fight-night-march-14-2026"
    event = {"id": "event-1", "slug": slug, "eventDate": "2026-03-14",
             "title": "UFC Test Card",
             "status": "completed", "hasStats": True}
    bout = {"id": "bout-1", "eventSlug": slug, "status": "completed",
            "hasStats": True, "isCancelled": False, "resultRound": 1,
            "fighters": [{"fighterName": "A"}, {"fighterName": "B"}]}
    event["bouts"] = [bout]
    totals = [{"id": "stat-a", "boutId": "bout-1", "fighterName": "A"},
              {"id": "stat-b", "boutId": "bout-1", "fighterName": "B"}]
    if duplicate_total:
        totals.append({"id": "stat-a-copy", "boutId": "bout-1",
                       "fighterName": "A"})
    rounds = [{"boutId": "bout-1", "fighterName": "A", "round": 1},
              {"boutId": "bout-1", "fighterName": "B", "round": 1}]
    if missing_round:
        rounds.pop()
    if differing_name:
        totals[0]["fighterName"] = "Full Name A"
        rounds[0]["fighterName"] = "Full Name A"
    stats = {"event": dict(event), "bouts": [bout],
             "boutStats": totals, "roundStats": rounds}
    inventory_rows = [dict(event), {"id": "dwcs-1", "slug": "dwcs-10-5",
                                    "eventDate": "2026-09-08", "hasStats": False}]
    collect_inventory(tmp_path, "secret", lambda *a, **k: Response({
        "events": inventory_rows, "pagination": {"hasNextPage": False},
    }), delay=0)

    def get(url, **kwargs):
        if url.endswith("/bouts"):
            return Response([bout])
        if url.endswith("/stats"):
            return Response(stats)
        return Response(event)

    result = collect_archive_cards(tmp_path, "secret", get,
                                   from_date="2026-01-01",
                                   through_date="2026-12-31", delay=0,
                                   max_cards=10)
    assert result["captured"] == 1


def test_audit_checks_rounds_and_preserves_statless_events(tmp_path):
    _archive(tmp_path)
    report = audit_archive(tmp_path)
    assert report["progress_statuses"] == {
        "captured": 1, "provider_has_no_stats": 1,
    }
    assert report["eligible_completed_stat_bearing_bouts"] == 1
    assert report["structurally_complete_bouts"] == 1
    assert report["findings"] == []
    assert report["inventory_events"][0]["title"] == "UFC Test Card"
    assert report["support_spot_checks"]["ufc-fight-night-march-14-2026"][
        "structure_matches_support_claim"] is False  # The fixture has one bout.
    assert report["coverage_verified"] is False


def test_audit_reports_duplicate_totals_and_missing_rounds(tmp_path):
    _archive(tmp_path, duplicate_total=True, missing_round=True)
    report = audit_archive(tmp_path)
    assert report["structurally_complete_bouts"] == 0
    assert any("fighter_total_row_count_differs" in item["finding"]
               for item in report["findings"])
    assert len(report["review_bouts"][0]["fighter_totals"]) == 3


def test_name_difference_has_separate_finding_and_saved_evidence(tmp_path):
    _archive(tmp_path, differing_name=True)
    report = audit_archive(tmp_path)
    assert report["findings"][0]["finding"] == "fighter_names_differ:bout-1"
    evidence = report["review_bouts"][0]
    assert evidence["bout"]["fighters"][0]["fighterName"] == "A"
    assert evidence["fighter_totals"][0]["fighterName"] == "Full Name A"
    assert len(evidence["round_rows"]) == 2
    assert evidence["card_manifest_sha256"]


def test_road_ufc_variants_are_outside_ufc_candidate_group():
    assert _competition("road-ufc-season-4-semifinals") == "other_competition"
    assert _competition("ufc-road-to-ufc-4-6") == "other_competition"


def test_audit_reports_missing_round_separately(tmp_path):
    _archive(tmp_path, missing_round=True)
    report = audit_archive(tmp_path)
    assert report["structurally_complete_bouts"] == 0
    assert any("missing_or_duplicate_round_rows" in item["finding"]
               for item in report["findings"])


def test_audit_detects_changed_raw_card(tmp_path):
    _archive(tmp_path)
    path = tmp_path / "cards/ufc-fight-night-march-14-2026/stats.json"
    path.write_text(path.read_text() + " ")
    report = audit_archive(tmp_path)
    assert report["findings"][0]["finding"] == "invalid_raw_card"


def test_audit_detects_changed_inventory_page(tmp_path):
    _archive(tmp_path)
    page = tmp_path / "inventory/pages/page-0001.json"
    page.write_text(json.dumps({}))
    try:
        audit_archive(tmp_path)
    except ValueError as error:
        assert "Inventory page changed" in str(error)
    else:
        raise AssertionError("Expected changed page to be rejected")
