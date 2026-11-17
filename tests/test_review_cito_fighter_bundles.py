import json
import shutil

import pytest
from test_collect_cito_fighter_bundles import PID, Response, _current

from upset.data.collect_cito_archive import _digest
from upset.data.collect_cito_fighter_bundles import collect_bundles
from upset.data.identity import (
    FighterIdentity,
    FighterProviderLink,
    FighterRegistry,
    save_fighter_registry,
)
from upset.data.review_cito_fighter_bundles import (
    compare_candidate,
    normalize_profile,
    review_bundles,
)


def test_profile_zero_measurements_stay_unknown_and_age_never_becomes_dob():
    result, issues = normalize_profile({"id": "a", "slug": "a", "name": "A", "heightInches": "0", "age": 29}, "2026-10-01T03:00:00Z", "https://example.org")
    assert result["height_inches"] is None and result["date_of_birth"] is None
    assert result["reported_age"] == 29 and issues


def test_candidate_measurement_conflicts_remain_unaccepted():
    result = compare_candidate({"height_inches": 70, "reach_inches": 72, "stance": "Orthodox", "reported_age": 29,
                                "observed_at_utc": "2026-10-01T03:00:00Z"},
                               {"height_inches": 70, "reach_inches": 74, "stance": "Orthodox", "date_of_birth": "1997-01-29"})
    assert result["status"] == "conflicting_profile_evidence"
    assert [r["field"] for r in result["conflicting_fields"]] == ["reach_inches"]
    assert len(result["matching_fields"]) == 3


def prepare(tmp_path, max_requests=3):
    current = _current(tmp_path)
    uid = "00000000-0000-4000-8000-000000000002"
    review_path = current / "review.json"
    review = json.loads(review_path.read_text())
    review["unresolved_fighter_identities"][0].update(supporting_bouts=[], name_only_candidates=[{"upset_fighter_id": uid}])
    review_path.write_text(json.dumps(review))
    (current / "manifest.json").write_text(json.dumps({"output_sha256": {"review.json": _digest(review_path)}}))
    profiles, registry = tmp_path / "profiles.jsonl", tmp_path / "registry.json"
    profiles.write_text(json.dumps({"upset_fighter_id": uid, "source_fighter_id": "hist", "name": "Alex", "height_inches": 70}) + "\n")
    save_fighter_registry(FighterRegistry((FighterIdentity(uid, "Alex"),), (FighterProviderLink("ufcstats", "hist", uid, "fixture"),)), registry)
    bundles = tmp_path / "bundles"
    def get(url, **kwargs):
        data = [] if url.endswith("/fights") else {"id": PID, "slug": "alex", "name": "Alex", "heightInches": "70"}
        return Response({"data": data})
    collect_bundles(current, bundles, "secret", get, max_requests=max_requests, delay=0, log=lambda *a, **k: None)
    return current, bundles, profiles, registry


def test_full_review_preserves_inputs_and_does_not_accept_matching_names(tmp_path):
    paths = prepare(tmp_path)
    before = {p: p.read_bytes() for p in tmp_path.rglob("*.json*")}
    output = tmp_path / "review"
    result = review_bundles(*paths, output)
    assert result["api_calls"] == 0 and result["identity_links_added"] == 0
    assert result["candidate_statuses"] == {"profile_candidate_requires_review": 1}
    assert all(p.read_bytes() == value for p, value in before.items())
    assert review_bundles(*paths, output) == result
    raw = paths[1] / "fighters" / PID / "profile.json"
    raw.write_text("tampered")
    with pytest.raises(ValueError, match="hash differs"):
        review_bundles(*paths, tmp_path / "other")


def test_incomplete_bundle_is_not_silently_reviewed(tmp_path):
    paths = prepare(tmp_path, max_requests=1)
    with pytest.raises(ValueError, match="incomplete"):
        review_bundles(*paths, tmp_path / "review")


def test_relocated_bundle_checks_file_contents_instead_of_original_paths(tmp_path):
    current, bundles, profiles, registry = prepare(tmp_path)
    moved = tmp_path / "moved"
    shutil.copytree(current, moved / "current")
    shutil.copytree(bundles, moved / "bundles")
    result = review_bundles(moved / "current", moved / "bundles", profiles, registry, moved / "review")
    assert result["provider_profiles"] == 1 and result["identity_links_added"] == 0


@pytest.mark.parametrize("value", ["nan", "inf", "770"])
def test_implausible_measurements_are_not_product_values(value):
    result, issues = normalize_profile({"id": "a", "slug": "a", "name": "A", "weightLbs": value}, "2026-10-01T03:00:00Z", "https://example.org")
    assert result["weight_lbs"] is None and issues
