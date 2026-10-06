"""The archive audit must preserve source gaps and verify captured round rows."""

import json

from upset.data.audit_cito_archive import (
    PAIR_FIELDS,
    _check_card,
    _competition,
    _participant,
    audit_archive,
)
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
    for row in totals + rounds:
        row.update(dict.fromkeys(PAIR_FIELDS, "0 of 0"))
        row.update(knockdowns=0, submissionAttempts=0, reversals=0, controlTime="0:00")
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
    assert report["numerically_reconciled_bouts"] == 1
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
    assert _competition("the-ultimate-fighter-28-finale") == "ufc_candidate"
    assert _competition("ortiz-vs-shamrock-3-the-final-chapter") == "ufc_candidate"
    assert _competition("the-ultimate-fighter-28-episode-1") == "unclassified"


def test_matching_uses_unique_slug_profile_name_or_reviewed_provider_identity():
    fighters = [{"fighterName": "Jose Miguel Delgado", "fighterSlug": "jose-miguel-delgado",
                 "profile": {"name": "Jose Delgado"}},
                {"fighterName": "Andre Fili", "fighterSlug": "andre-fili"}]
    assert _participant({"fighterName": "Jose Delgado", "fighterSlug": None}, fighters) == 0
    assert _participant({"fighterName": "Other Name", "fighterSlug": "andre-fili"}, fighters) == 1
    assert _participant({"fighterName": "Andre Fili", "fighterSlug": "jose-miguel-delgado"},
                        fighters) is None
    assert _participant({"fighterName": "Joseph Delgado"}, fighters) is None
    fighters[0] = {"fighterName": "Max Grishin",
                   "fighterId": "cc11ae04-67dd-4f52-9a7c-b7f25dd6d856"}
    assert _participant({"fighterName": "Maxim Grishin"}, fighters) == 0
    fighters[0]["fighterId"] = "different-person"
    assert _participant({"fighterName": "Maxim Grishin"}, fighters) is None


def _replace_fixture_stats(tmp_path, change):
    # Refresh acquisition hashes after editing the fixture, so this tests math.
    from upset.data.collect_cito_archive import _atomic_json, _digest

    card = tmp_path / "cards/ufc-fight-night-march-14-2026"
    raw = json.loads((card / "stats.json").read_text())
    change(raw["response"]["data"])
    _atomic_json(card / "stats.json", raw)
    manifest = json.loads((card / "manifest.json").read_text())
    manifest["sha256"]["stats"] = _digest(card / "stats.json")
    _atomic_json(card / "manifest.json", manifest)
    progress = json.loads((tmp_path / "collection_progress.json").read_text())
    next(r for r in progress["cards"].values() if r["status"] == "captured")[
        "card_manifest_sha256"] = _digest(card / "manifest.json")
    _atomic_json(tmp_path / "collection_progress.json", progress)


def test_numerical_difference_does_not_pass_reconciliation(tmp_path):
    _archive(tmp_path)
    _replace_fixture_stats(tmp_path, lambda stats: stats["boutStats"][0].update(
        significantStrikes="1 of 2"))
    report = audit_archive(tmp_path)
    assert report["structurally_complete_bouts"] == 1
    assert report["numerically_reconciled_bouts"] == 0
    assert any(r["finding"] == "round_sums_differ:bout-1" for r in report["findings"])


def test_unavailable_control_is_preserved_and_other_stats_still_checked(tmp_path):
    _archive(tmp_path)

    def missing_control(stats):
        for row in stats["boutStats"] + stats["roundStats"]:
            row["controlTime"] = "--"

    _replace_fixture_stats(tmp_path, missing_control)
    report = audit_archive(tmp_path)
    assert report["findings"] == []
    assert report["numerically_reconciled_bouts"] == 0
    assert report["observed_stats_reconciled_bouts"] == 1
    assert report["bouts_with_unavailable_stat_fields"] == 1
    assert len(report["unavailable_stat_fields"][0]["fields"]) == 2
    _replace_fixture_stats(tmp_path, lambda stats: stats["boutStats"][0].update(
        significantStrikes="1 of 2"))
    report = audit_archive(tmp_path)
    assert report["observed_stats_reconciled_bouts"] == 0
    assert any(r["finding"] == "round_sums_differ:bout-1" for r in report["findings"])


def test_bout_with_stats_and_unfinished_status_is_visible_for_review(tmp_path):
    _archive(tmp_path)
    from upset.data.export_cito_card import _read_card

    payloads, _, _ = _read_card(tmp_path / "cards/ufc-fight-night-march-14-2026")
    payloads["bouts"][0]["status"] = "confirmed"
    result = _check_card(payloads, {"slug": "ufc-fight-night-march-14-2026",
                                    "event_date": "2026-03-14",
                                    "provider_event_id": "event-1"})
    assert result["eligible_bouts"] == 0
    assert result["findings"] == ["bout_metadata_conflicts_with_stats:bout-1"]
    assert result["excluded_bouts"][0]["total_rows"] == 2
    assert len(result["review_bouts"][0]["round_rows"]) == 2


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
