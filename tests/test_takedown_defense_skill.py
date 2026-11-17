"""Offline adapter identity, missingness, chronology and prototype validation."""

from copy import deepcopy
from math import isfinite

import pytest
from test_research_app import A, B, build, fixture

from upset.skill.shrink_defense import (
    adjusted_mean,
    bootstrap,
    evaluate,
    predict,
    score,
)
from upset.skill.takedown_defense import export, paired_sides, read_sides


def pair():
    fight = {"source": "cito", "source_bout_id": "x", "event_date": "2026-10-10",
             "upset_fighter_1_id": A, "upset_fighter_2_id": B,
             "source_fighter_1_id": "a", "source_fighter_2_id": "b",
             "source_event_id": "card", "weight_class": "UFC Lightweight Title Bout"}
    stats = {uid: {"source": "cito", "source_bout_id": "x", "source_fighter_id": sid,
                   "upset_fighter_id": uid, "fight_duration_seconds": 300,
                   "takedowns_landed": landed, "takedowns_attempted": attempted}
             for uid, sid, landed, attempted in ((A, "a", 1, 4), (B, "b", 2, 5))}
    return fight, stats


def observation(day, fid, stopped, attempts, uid=A, division="Lightweight"):
    return {"event_date": day, "event_id": "event:" + day, "fight_id": fid,
            "fighter_id": uid, "division": division,
            "status": "observed" if attempts else "zero_attempts",
            "opponent_takedown_attempts": attempts, "takedowns_stopped": stopped}


def test_defense_uses_opponents_counts_and_permanent_identities():
    fight, stats = pair()
    a, b = paired_sides("cito:x", fight, stats, "hash")
    assert a["fighter_id"] == A and a["opponent_id"] == B
    assert (a["takedowns_stopped"], a["opponent_takedown_attempts"]) == (3, 5)
    assert a["observed_defense"] == .6
    assert b["observed_defense"] == .75
    assert a["division"] == "Lightweight" and a["event_id"] == "cito:card"


@pytest.mark.parametrize("landed,attempted,status", [
    (0, 0, "zero_attempts"), (None, 5, "missing_opponent_counts"),
    (2, None, "missing_opponent_counts"), (6, 5, "invalid_opponent_counts"),
    (False, 5, "invalid_opponent_counts"), (-1, 5, "invalid_opponent_counts"),
])
def test_missing_invalid_and_zero_attempts_never_become_perfect_defense(landed, attempted, status):
    fight, stats = pair()
    stats[B].update(takedowns_landed=landed, takedowns_attempted=attempted)
    a = paired_sides("cito:x", fight, stats, "hash")[0]
    assert a["status"] == status and a["observed_defense"] is None
    if status != "zero_attempts":
        assert a["takedowns_stopped"] is None and a["opponent_takedown_attempts"] is None


def test_structural_corruption_rejects_the_pair():
    fight, stats = pair()
    stats[B]["source_fighter_id"] = "different"
    with pytest.raises(ValueError, match="provider identity"):
        paired_sides("cito:x", fight, stats, "hash")
    fight, stats = pair()
    stats[B]["fight_duration_seconds"] = 299
    with pytest.raises(ValueError, match="durations"):
        paired_sides("cito:x", fight, stats, "hash")


def test_verified_export_is_readonly_exclusive_and_immutable(tmp_path):
    output = tmp_path / "serving"
    build(fixture(tmp_path), output)
    database = output / "upset.sqlite"
    original = database.read_bytes()
    rows, hashes = read_sides(database, "2026-09-20")
    assert len(rows) == 2 and all(r["event_date"] < "2026-09-20" for r in rows)
    assert all(r["database_sha256"] == hashes["database_sha256"] for r in rows)
    result = export(database, "2026-09-21", tmp_path / "adapter")
    assert result["side_rows"] == 4 and result["public_release"] is False
    assert database.read_bytes() == original
    with pytest.raises(ValueError, match="new output"):
        export(database, "2026-09-21", tmp_path / "adapter")
    database.write_bytes(original + b"tampered")
    with pytest.raises(ValueError, match="hash differs"):
        read_sides(database, "2026-09-21")


def test_known_adjustment_and_cold_start():
    assert adjusted_mean(8, 10, .5, 10) == .65
    assert adjusted_mean(0, 0, .6, 25) == .6
    assert adjusted_mean(0, 0, None, 25) is None
    assert abs(adjusted_mean(8000, 10000, .5, 10) - .8) < .001
    with pytest.raises(ValueError):
        adjusted_mean(11, 10, .5, 25)


def test_same_day_and_future_actions_cannot_change_prior_estimates():
    sides = [observation("2013-01-01", "a", 8, 10),
             observation("2013-02-01", "b", 1, 5),
             observation("2013-02-01", "c", 4, 5),
             observation("2020-01-01", "d", 4, 5)]
    original = predict(sides, 25)
    altered = deepcopy(sides)
    altered[1]["takedowns_stopped"] = 5
    altered[2]["takedowns_stopped"] = 0
    altered[3]["takedowns_stopped"] = 0
    changed = predict(altered, 25)
    for x, y in zip(original[:3], changed[:3]):
        assert all(x[k] == y[k] for k in ("raw_career", "raw_last5", "sample_adjusted", "prior_attempts", "baseline"))
    assert original[1]["prior_attempts"] == original[2]["prior_attempts"] == 10
    assert predict(sides[::-1], 25) == original


def test_last_five_is_bouts_not_last_five_nonzero_measurements():
    sides = [observation("2013-01-01", "a", 8, 10)]
    sides += [observation(f"2013-01-0{i}", str(i), 0, 0) for i in range(2, 7)]
    sides += [observation("2013-01-07", "g", 1, 1)]
    final = predict(sides, 25)[-1]
    assert final["raw_career"] == .8 and final["raw_last5"] is None
    assert final["prior_bouts"] == 6


def test_development_outcomes_cannot_select_the_prior_strength():
    sides = [observation("2013-01-01", "a", 8, 10),
             observation("2013-02-01", "b", 0, 5),
             observation("2014-01-01", "c", 4, 5),
             observation("2020-01-01", "d", 5, 5)]
    _, original = evaluate(sides)
    altered = deepcopy(sides)
    altered[-1]["takedowns_stopped"] = 0
    _, changed = evaluate(altered)
    assert changed["selected_prior_attempts"] == original["selected_prior_attempts"]
    assert changed["tuning_2012_2018"] == original["tuning_2012_2018"]
    assert not original["public_release"] and not original["opponent_adjusted"]


def test_score_extremes_are_finite_and_bootstrap_clusters_dates():
    row = {"stopped": 1, "attempts": 1, "raw_career": 0., "raw_last5": 1.,
           "sample_adjusted": .5, "event_date": "2020-01-01"}
    assert all(isfinite(score(row, m)[0]) for m in ("raw_career", "raw_last5", "sample_adjusted"))
    result = bootstrap([row, dict(row)])
    assert result == bootstrap([row, dict(row)])
    for comparison in result.values():
        low, high = comparison["date_cluster_bootstrap_95_interval"]
        assert low == high == comparison["adjusted_minus_baseline_nll"]
