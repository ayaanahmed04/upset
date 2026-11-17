"""Only bound, chronologically consistent overall-rating snapshots may serve."""

import hashlib
import json
from copy import deepcopy

import pytest

from upset.ratings.serving import VERSION, load_snapshot

A = "00000000-0000-4000-8000-000000000001"
B = "00000000-0000-4000-8000-000000000002"
C = "00000000-0000-4000-8000-000000000003"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def row(uid, day, bouts, score, peak, change):
    return {"fighter_id": uid, "event_date": day, "bouts": bouts, "score": score,
            "peak": peak, "change": change, "provisional": bouts < 4,
            "division": "Lightweight", "elo": 1500., "raw_combined": 76.3,
            "skills_combined": 74.6,
            "parts": [{"key": key, "label": key.title(), "score": 75.2,
                       "raw_score": 40., "metrics": {"rate": None if key == "grappling" else .5}}
                      for key in ("striking", "wrestling", "grappling", "resume")]}


def artifact(tmp_path):
    database = tmp_path/"serving.sqlite"
    database.write_bytes(b"test-only database binding")
    source = tmp_path/"protocol.md"
    source.write_text("Fixture source, not a fitted model.")
    folder = tmp_path/"snapshot"
    folder.mkdir()
    rows = [row(A, "2019-01-01", 1, 76, 76, None),
            row(B, "2019-01-01", 1, 70, 70, None),
            row(A, "2019-01-04", 2, 80, 80, 4),
            row(A, "2019-02-01", 3, 78, 80, -2),
            row(A, "2020-01-01", 4, 83, 83, 5),
            row(A, "2021-01-01", 5, 88, 88, 5)]
    evaluation = {"version": VERSION, "engineering_checks_passed": True,
                  "serving_eligible": True, "evaluation_label": "Inspected development evidence only.",
                  "track_record": {"wins": 6, "total": 10, "accuracy": .6, "from_date": "2019-01-01"}}
    metadata = {"version": VERSION, "experimental": True, "validated": False,
                "input_database": str(database), "database_sha256": digest(database),
                "before_exclusive": "2026-11-04", "latest_event": "2026-10-31",
                "display_curve": {"reference_before": "2019-01-01"},
                "model": {"resume_weight": .5, "skill_weights": [.5, .3, .2]},
                "input_sha256": {str(source): digest(source)}}
    write(folder, rows, evaluation, metadata)
    return folder, database, source, rows, evaluation, metadata


def write(folder, rows, evaluation, metadata):
    (folder/"ratings.jsonl").write_text("".join(json.dumps(r)+"\n" for r in rows))
    (folder/"evaluation.json").write_text(json.dumps(evaluation))
    metadata["output_sha256"] = {name: digest(folder/name) for name in ("ratings.jsonl", "evaluation.json")}
    (folder/"manifest.json").write_text(json.dumps(metadata))


def query(snapshot, database, before, uid=A, window=0):
    return snapshot.estimate(database, {"id": uid, "before": before, "window": window})


def test_exclusive_cutoff_and_latched_career_history(tmp_path):
    folder, database, _, _, _, _ = artifact(tmp_path)
    snapshot = load_snapshot(folder, database)
    assert query(snapshot, database, "2019-01-01")["status"] == "no_history"
    assert query(snapshot, database, "2019-01-04")["score"] == 76
    after = query(snapshot, database, "2019-01-05")
    assert after["score"] == 80 and after["peak"] == 80
    assert [r["score"] for r in after["history"]] == [76, 80]
    assert query(snapshot, database, "2019-01-31")["score"] == 80
    assert query(snapshot, database, "2019-02-02")["peak"] == 80
    assert query(snapshot, database, "2020-01-02")["provisional"] is False
    assert after["experimental"] is True and after["validated"] is False
    assert "development" in after["evaluation_label"]


def test_stats_windows_never_recompute_the_overall(tmp_path):
    folder, database, *_ = artifact(tmp_path)
    snapshot = load_snapshot(folder, database)
    career = query(snapshot, database, "2026-11-04")
    for window in (3, 5, 10):
        assert query(snapshot, database, "2026-11-04", window=window) == career
    assert query(snapshot, database, "2025-01-01")["score"] == career["score"]


def test_responses_cannot_mutate_index_and_requests_do_not_fit(tmp_path):
    folder, database, *_ = artifact(tmp_path)
    snapshot = load_snapshot(folder, database)
    request = {"id": A, "before": "2019-01-05", "window": 0}
    saved = deepcopy(request)
    response = snapshot.estimate(database, request)
    response["history"][0]["score"] = 99
    response["parts"][0]["metrics"]["rate"] = 99
    response["model"]["resume_weight"] = 0
    response["track_record"]["wins"] = 0
    fresh = snapshot.estimate(database, request)
    assert fresh["history"][0]["score"] == 76
    assert fresh["parts"][0]["metrics"]["rate"] == .5
    assert fresh["model"]["resume_weight"] == .5
    assert fresh["track_record"]["wins"] == 6
    assert request == saved


def test_no_default_score_for_unknown_fighter_or_unsupported_future(tmp_path):
    folder, database, *_ = artifact(tmp_path)
    snapshot = load_snapshot(folder, database)
    missing = query(snapshot, database, "2026-11-04", uid=C)
    assert missing["status"] == "no_history" and missing["score"] is None
    assert missing["history"] == []
    future = query(snapshot, database, "2026-11-05")
    assert future["status"] == "unsupported_cutoff" and future["score"] is None
    with pytest.raises(ValueError, match="different database"):
        query(snapshot, tmp_path/"different.sqlite", "2026-11-04")
    with pytest.raises(ValueError, match="ISO"):
        query(snapshot, database, "2026-1-1")


@pytest.mark.parametrize("target", ["database", "source", "ratings", "evaluation"])
def test_changed_bound_files_are_rejected(tmp_path, target):
    folder, database, source, *_ = artifact(tmp_path)
    paths = {"database": database, "source": source, "ratings": folder/"ratings.jsonl",
             "evaluation": folder/"evaluation.json"}
    with paths[target].open("ab") as stream:
        stream.write(b" ")
    with pytest.raises(ValueError, match="hash|database"):
        load_snapshot(folder, database)


@pytest.mark.parametrize("field", ["engineering_checks_passed", "serving_eligible"])
def test_model_not_ready_fails_even_with_rebound_valid_hashes(tmp_path, field):
    folder, database, _, rows, evaluation, metadata = artifact(tmp_path)
    evaluation[field] = False
    write(folder, rows, evaluation, metadata)
    with pytest.raises(ValueError, match="serving checks"):
        load_snapshot(folder, database)


@pytest.mark.parametrize("mutation", [
    "cap", "change", "peak", "provisional", "duplicate", "chronology", "future",
    "bout_count", "first_change", "first_peak", "part_nan", "duplicate_part", "raw_inf",
])
def test_semantic_contract_rejects_corruption_after_resigning(tmp_path, mutation):
    folder, database, _, rows, evaluation, metadata = artifact(tmp_path)
    if mutation == "cap":
        rows[0]["score"] = rows[0]["peak"] = 89
    elif mutation == "change":
        rows[2]["score"] = rows[2]["peak"] = 82
        rows[2]["change"] = 6
    elif mutation == "peak":
        rows[3]["peak"] = 78
    elif mutation == "provisional":
        rows[4]["provisional"] = True
    elif mutation == "duplicate":
        rows.insert(1, deepcopy(rows[0]))
    elif mutation == "chronology":
        rows[3]["event_date"] = "2019-01-03"
    elif mutation == "future":
        rows[-1]["event_date"] = "2026-11-04"
    elif mutation == "bout_count":
        rows[2]["bouts"] = 1
    elif mutation == "first_change":
        rows[0]["change"] = 0
    elif mutation == "first_peak":
        rows[0]["peak"] = 77
    elif mutation == "part_nan":
        rows[0]["parts"][0]["score"] = float("nan")
    elif mutation == "duplicate_part":
        rows[0]["parts"][0]["key"] = "resume"
    elif mutation == "raw_inf":
        rows[0]["parts"][0]["metrics"]["rate"] = float("inf")
    write(folder, rows, evaluation, metadata)
    with pytest.raises(ValueError):
        load_snapshot(folder, database)


def test_track_record_cannot_claim_a_different_success_rate(tmp_path):
    folder, database, _, rows, evaluation, metadata = artifact(tmp_path)
    evaluation["track_record"]["accuracy"] = .99
    write(folder, rows, evaluation, metadata)
    with pytest.raises(ValueError, match="accuracy"):
        load_snapshot(folder, database)


def test_model_metadata_and_version_are_not_substitutable(tmp_path):
    folder, database, _, rows, evaluation, metadata = artifact(tmp_path)
    metadata["model"]["resume_weight"] = float("nan")
    write(folder, rows, evaluation, metadata)
    with pytest.raises(ValueError, match="metadata"):
        load_snapshot(folder, database)
    metadata["model"]["resume_weight"] = .5
    metadata["validated"] = True
    write(folder, rows, evaluation, metadata)
    with pytest.raises(ValueError, match="version/database"):
        load_snapshot(folder, database)


@pytest.mark.parametrize("target", ["manifest", "evaluation", "row", "model"])
def test_wrong_top_level_json_types_are_explicitly_rejected(tmp_path, target):
    folder, database, _, rows, evaluation, metadata = artifact(tmp_path)
    if target == "evaluation":
        evaluation = []
    elif target == "row":
        rows[0] = []
    elif target == "model":
        metadata["model"] = []
    write(folder, rows, evaluation, metadata)
    if target == "manifest":
        (folder/"manifest.json").write_text("[]")
    with pytest.raises(TypeError, match="object"):
        load_snapshot(folder, database)
