"""Future-only evaluation must fail closed on peeking or rewritten history."""

import json
from copy import deepcopy
from datetime import UTC, datetime

import numpy as np
import pytest

from upset.skill import defense_prospective as prospective
from upset.skill.defense_validation import augment
from upset.skill.takedown_defense import digest

IDS = [f"00000000-0000-4000-8000-{i:012d}" for i in range(4)]


def pair(day, name, counts=((3, 2), (4, 1))):
    result = []
    for i, (n, s) in enumerate(counts):
        result.append({"fighter_id": IDS[i], "opponent_id": IDS[1-i],
                       "fight_id": name, "event_date": day, "event_id": "event:"+day,
                       "division": "Lightweight", "status": "observed" if n else "zero_attempts",
                       "takedowns_stopped": s, "opponent_takedown_attempts": n,
                       "opponent_takedowns_landed": n-s, "source": "fixture",
                       "source_bout_id": name, "source_rows_sha256": "rows:"+name,
                       "database_sha256": "database", "source_fighter_id": str(i),
                       "opponent_source_fighter_id": str(1-i)})
    return result


def adapter(tmp_path, rows, before, name):
    folder = tmp_path/name
    folder.mkdir()
    database = folder/"database"
    database.write_text("test fixture "+name)
    rows = [{**r, "database_sha256": digest(database)} for r in rows]
    sides = folder/"sides.jsonl"
    sides.write_text("".join(json.dumps(r)+"\n" for r in rows))
    metadata = {"before_exclusive": before, "side_rows": len(rows),
                "input_database": str(database), "input_sha256": {"database_sha256": digest(database)},
                "output_sha256": {"sides.jsonl": digest(sides)}}
    (folder/"manifest.json").write_text(json.dumps(metadata))
    return folder


@pytest.fixture
def frozen(tmp_path, monkeypatch):
    monkeypatch.setattr(prospective, "utcnow", lambda: datetime(2026, 10, 26, tzinfo=UTC))
    source = adapter(tmp_path, pair("2026-10-24", "seed"), "2026-10-26", "seed")
    protocol = tmp_path/"protocol.md"
    protocol.write_text("Synthetic test-only prospective protocol")
    folder = tmp_path/"freeze"
    prospective.freeze(source, protocol, folder)
    return folder, source


def test_status_is_pending_and_has_no_scores(frozen):
    folder, source = frozen
    result = prospective.status(folder, source)
    assert result["status"] == "pending_future_block"
    assert result["new_block_sides"] == 0
    assert not result["scores_computed"] and not result["public_release"]
    assert "evaluation" not in result


def test_early_finalize_refuses_before_reading_any_outcomes(monkeypatch, tmp_path):
    monkeypatch.setattr(prospective, "utcnow", lambda: datetime(2026, 10, 26, tzinfo=UTC))
    with pytest.raises(ValueError, match="early scoring"):
        prospective.finalize(tmp_path/"no-freeze", tmp_path/"no-data", tmp_path/"no-review", tmp_path/"output")
    assert not (tmp_path/"output").exists()


def test_freeze_cannot_start_after_future_block_opens(monkeypatch, tmp_path):
    monkeypatch.setattr(prospective, "utcnow", lambda: datetime(2026, 10, 27, tzinfo=UTC))
    with pytest.raises(ValueError, match="precede"):
        prospective.freeze(tmp_path, tmp_path/"none", tmp_path/"freeze")


@pytest.mark.parametrize("which", ["seed.jsonl", "config.json", "protocol.md"])
def test_changed_frozen_files_rejected(frozen, which):
    folder, source = frozen
    (folder/which).write_text("{}")
    with pytest.raises(ValueError):
        prospective.status(folder, source)


def test_changed_source_hash_rejected(frozen):
    folder, source = frozen
    manifest = json.loads((folder/"manifest.json").read_text())
    key = next(iter(manifest["frozen_dependencies_sha256"]))
    manifest["frozen_dependencies_sha256"][key] = "bad hash"
    (folder/"manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="Frozen source"):
        prospective.status(folder, source)


def test_database_hash_may_change_when_all_history_is_identical():
    seed = pair("2026-10-24", "seed")
    latest = [{**r, "database_sha256": "new database"} for r in seed]+pair("2026-10-27", "future")
    assert len(prospective.compatible(seed, latest)) == 2


@pytest.mark.parametrize("change", ["counts", "date", "identity", "delete", "duplicate", "historical", "gap"])
def test_rewritten_history_and_backfills_rejected(change):
    seed = pair("2026-10-24", "seed")
    latest = deepcopy(seed)
    if change == "counts":
        latest[0]["takedowns_stopped"] = 0
    elif change == "date":
        latest[0]["event_date"] = "2026-10-23"
    elif change == "identity":
        latest[0]["opponent_id"] = IDS[2]
    elif change == "delete":
        latest.pop()
    elif change == "duplicate":
        latest.append(latest[0])
    else:
        latest.extend(pair("2026-10-26" if change == "gap" else "2026-10-20", "new-history"))
    with pytest.raises(ValueError):
        prospective.compatible(seed, latest)


def test_predictions_match_retained_reference_and_exclude_post_block():
    rows = pair("2026-10-24", "seed")+pair("2026-10-27", "future")+pair("2027-10-27", "outside")
    actual = prospective.predict(rows)
    expected = [r for r in augment(rows) if r["event_date"] == "2026-10-27"]
    assert len(actual) == len(expected) == 2
    for a, b in zip(actual, expected, strict=True):
        assert a["candidate"] == b["global25"]
        assert a["raw_career"] == b["raw_career"]
        assert a["raw_last5"] == b["raw_last5"]


def test_same_day_outcomes_and_future_do_not_change_same_day_predictions():
    rows = pair("2026-10-24", "seed")+pair("2026-10-27", "future")
    first = prospective.predict(rows)
    changed = deepcopy(rows)
    changed[2].update(takedowns_stopped=0, opponent_takedowns_landed=3)
    changed += pair("2026-10-28", "later")
    second = prospective.predict(changed)
    for a, b in zip(first, second[:2], strict=True):
        assert a["candidate"] == b["candidate"]
        assert a["raw_last5"] == b["raw_last5"]


def test_zero_attempts_consume_last_five_slot_without_added_trials():
    seed = pair("2026-10-24", "seed")
    zeros = [r for day in range(27, 32) for r in pair(f"2026-10-{day}", f"zero:{day}", ((0, 0), (0, 0)))]
    rows = prospective.predict(seed+zeros+pair("2026-11-01", "after"))
    last = [r for r in rows if r["event_date"] == "2026-11-01"]
    assert all(r["prior_attempts"] > 0 and r["raw_last5"] is None and not r["primary"] for r in last)


def complete_review(path, adapter_path):
    body = {"adapter_sides_sha256": digest(adapter_path/"sides.jsonl"),
            "start_inclusive": "2026-10-27", "end_exclusive": "2027-10-27",
            "unresolved_eligible_bouts": 0, "reviewed_by": "synthetic test fixture",
            "evidence": "Synthetic data only; not a real completeness assertion."}
    path.write_text(json.dumps(body))
    return path


def test_finalizer_requires_matching_completeness_review(frozen, monkeypatch, tmp_path):
    folder, _ = frozen
    monkeypatch.setattr(prospective, "utcnow", lambda: datetime(2027, 10, 27, tzinfo=UTC))
    rows = pair("2026-10-24", "seed")+pair("2026-10-27", "future")
    latest = adapter(tmp_path, rows, "2027-10-27", "latest")
    review = complete_review(tmp_path/"review.json", latest)
    body = json.loads(review.read_text());body["unresolved_eligible_bouts"] = 1
    review.write_text(json.dumps(body))
    with pytest.raises(ValueError, match="completeness"):
        prospective.finalize(folder, latest, review, tmp_path/"results")


def test_complete_but_empty_block_cannot_pass(frozen, monkeypatch, tmp_path):
    folder, _ = frozen
    monkeypatch.setattr(prospective, "utcnow", lambda: datetime(2027, 10, 27, tzinfo=UTC))
    latest = adapter(tmp_path, pair("2026-10-24", "seed"), "2027-10-27", "latest")
    review = complete_review(tmp_path/"review.json", latest)
    with pytest.raises(ValueError, match="empty block"):
        prospective.finalize(folder, latest, review, tmp_path/"results")


def test_synthetic_finalization_reports_thin_evidence_and_never_releases(frozen, monkeypatch, tmp_path):
    folder, _ = frozen
    monkeypatch.setattr(prospective, "utcnow", lambda: datetime(2027, 10, 27, tzinfo=UTC))
    rows = pair("2026-10-24", "seed")+pair("2026-10-27", "future")
    latest = adapter(tmp_path, rows, "2027-10-27", "latest")
    review = complete_review(tmp_path/"review.json", latest)
    report = prospective.finalize(folder, latest, review, tmp_path/"results")
    assert not report["public_release"]
    decision = report["evaluation"]["decision"]
    assert not decision["baseline_predictive_checks_pass"]
    assert "primary_inconclusive" in decision["failed_or_inconclusive_checks"]
    assert "calibration_inconclusive:attempts10+" in decision["failed_or_inconclusive_checks"]
    values = report["evaluation"]["primary"]["models"]["candidate"]["mean_predictive_nll"]
    assert np.isfinite(values)


def test_existing_output_directory_never_overwritten(frozen, tmp_path):
    folder, source = frozen
    with pytest.raises(ValueError, match="immutable"):
        prospective.freeze(source, tmp_path/"none", folder)
