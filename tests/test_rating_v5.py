"""Release checks for UPSET Rating v5 (the saved November 10 snapshot).

These read the committed artifact; they do not refit anything. Skipped when the
snapshot or its database is not present on this machine.
"""

import json
import math
from collections import defaultdict
from pathlib import Path

import pytest

from upset.ratings import serving_v5

ROOT = Path(__file__).resolve().parents[1]
FOLDER = ROOT / "data/processed/overall_rating_v5_1_2026_11_10_reviewed_v3"
DATABASE = ROOT / "data/processed/research_2026_11_10_reviewed_v3/upset.sqlite"
pytestmark = pytest.mark.skipif(not (FOLDER / "manifest.json").exists() or not DATABASE.exists(),
                                reason="v5 snapshot not present")


@pytest.fixture(scope="module")
def snapshot():
    return serving_v5.load_snapshot(FOLDER, DATABASE)


def rows():
    with (FOLDER / "ratings.jsonl").open() as stream:
        return [json.loads(line) for line in stream]


def test_gate_and_honest_comparison(snapshot):
    metrics = snapshot.evaluation["metrics"]
    assert snapshot.evaluation["engineering_checks_passed"] is True
    assert metrics["v5_forecast"]["test"]["log_loss"] < metrics["v4"]["test"]["log_loss"]
    assert metrics["v5"]["test"]["log_loss"] <= metrics["v4"]["test"]["log_loss"] + .002
    market = snapshot.evaluation["market"]
    # Reported as-is: the archived market is still better than UPSET on matched fights.
    assert market["market"]["log_loss"] < market["v5_forecast"]["log_loss"]


def test_rules_hold_on_every_served_number():
    history = defaultdict(list)
    for row in rows():
        history[row["fighter_id"]].append(row)
    at = {(row["fighter_id"], row["event_date"]): row for row in rows()}
    for fighter_rows in history.values():
        for before, after in zip(fighter_rows, fighter_rows[1:]):
            outcomes = set(after["last_outcomes"])
            if outcomes == {"win"}:
                assert after["score"] >= before["score"]
            if outcomes == {"loss"}:
                assert after["score"] <= before["score"]
        for row in fighter_rows:
            if len(row["fights"]) == 1 and row["fights"][0]["outcome"] == "win":
                loser = at.get((row["fights"][0]["opponent_id"], row["event_date"]))
                if loser is not None and len(loser["fights"]) == 1:
                    assert row["score"] >= loser["score"]


def test_scale_meaning_matches_the_model(snapshot):
    scale = snapshot.metadata["scale"]
    # Five points is a doubling of the odds for two fighters at the typical uncertainty.
    assert math.isclose(scale["points_per_unit"] * math.log(2) / scale["typical_g"], 5, rel_tol=1e-9)
    assert scale["floor"] == 60 and scale["cap"] == 99 and scale["center_score"] == 80


def test_stars_are_monotone(snapshot):
    levels = snapshot.metadata["stars"]["levels"]
    previous = None
    for score in range(60, 100):
        stars, _ = serving_v5.stars_for(score, snapshot.metadata["stars"])
        assert previous is None or stars >= previous
        previous = stars
    assert serving_v5.stars_for(levels[0]["min_score"], snapshot.metadata["stars"])[0] == 5.0


def test_estimate_and_matchup_contract(snapshot):
    ids = [row["fighter_id"] for row in rows() if row["bouts"] >= 8][:2]
    a, b = (snapshot.estimate(DATABASE, {"id": uid, "before": "2026-11-08"}) for uid in ids)
    for rating in (a, b):
        assert rating["status"] == "available" and rating["version"] == serving_v5.VERSION
        assert 60 <= rating["score"] <= 99 and rating["range"][0] <= rating["score"] <= rating["range"][1]
        assert [part["key"] for part in rating["parts"]][-1] == "results"
    forward, backward = snapshot.matchup(a, b), snapshot.matchup(b, a)
    assert math.isclose(forward["probabilities"][0], backward["probabilities"][1], rel_tol=1e-12)
    assert math.isclose(sum(forward["probabilities"]), 1, rel_tol=1e-12)
    early = snapshot.estimate(DATABASE, {"id": ids[0], "before": "1993-01-01"})
    assert early["status"] == "no_history"
