"""Behavior of the v2 KO/TKO input and compatibility with the v1 replay."""

import pytest
from test_rating_engine import bout, by_uid

from upset.ratings import engine, engine_v2


def test_ko_win_increases_striking_without_a_recorded_knockdown():
    decision = bout("one", "2020-01-01")
    stoppage = dict(decision, method_group="ko")
    decision_snapshot = by_uid(engine_v2.replay([decision])[0], "A")[0]
    ko_snapshot = by_uid(engine_v2.replay([stoppage])[0], "A")[0]

    assert decision_snapshot["metrics"]["ko_wins_per_bout"] == 0
    assert ko_snapshot["metrics"]["ko_wins_per_bout"] == 1
    assert ko_snapshot["metrics"]["knockdowns_per_15_minutes"] == 0
    assert ko_snapshot["coverage"]["feature_z"]["ko_win"] == pytest.approx(1 / 6 / .10)
    assert ko_snapshot["coverage"]["feature_exposures"]["ko_win"] == 1
    assert ko_snapshot["raw_parts"]["striking"] > decision_snapshot["raw_parts"]["striking"]
    for part in ("wrestling", "grappling", "resume"):
        assert ko_snapshot["raw_parts"][part] == decision_snapshot["raw_parts"][part]


def test_equal_ko_wins_get_more_credit_against_less_stoppable_opponent():
    rows = [
        bout("b1", "2020-01-01", "B", "C", "C", method="ko"),
        bout("d1", "2020-01-01", "D", "E", "E"),
        bout("a1", "2020-02-01", "A", "B", "A", method="ko"),
        bout("f1", "2020-02-01", "F", "D", "F", method="ko"),
    ]
    snapshots, _ = engine_v2.replay(rows)
    a = by_uid(snapshots, "A")[0]
    f = by_uid(snapshots, "F")[0]

    assert a["metrics"]["ko_wins_per_bout"] == f["metrics"]["ko_wins_per_bout"] == 1
    # The opponents differ by one KO loss across one bout with five prior bouts.
    # The finish residual then shrinks by five bouts and uses the .10 peer floor.
    difference = f["coverage"]["feature_z"]["ko_win"] - a["coverage"]["feature_z"]["ko_win"]
    assert difference == pytest.approx(1 / 6 / 6 / .10)


def test_same_day_and_future_results_do_not_change_ko_context_or_prefights():
    earlier = bout("first", "2020-01-01", "B", "D", "B")
    target = bout("target", "2020-02-01", "A", "B", "A", method="ko")
    same_day = bout("other", "2020-02-01", "B", "C", "C", method="ko")
    future = bout("future", "2020-03-01", "A", "D", "D", method="ko")

    baseline, baseline_prefights = engine_v2.replay([earlier, target])
    expanded, prefights = engine_v2.replay([future, target, same_day, earlier])
    assert by_uid(expanded, "A")[0] == by_uid(baseline, "A")[0]
    assert prefights[0] == baseline_prefights[0]
    assert prefights[2] == baseline_prefights[1]
    for row in prefights:
        assert all(day is None or day < row["event_date"] for day in row["prior_snapshot_dates"])


def test_v2_keeps_v1_feature_semantics_and_result_schema():
    assert "ko_win" not in engine.FEATURES
    assert engine.FEATURES["sig_diff"].weight == .30
    for key, spec in engine.FEATURES.items():
        expected_weight = spec.weight * .90 if spec.part == "striking" else spec.weight
        assert engine_v2.FEATURES[key].weight == pytest.approx(expected_weight)
    assert sum(spec.weight for spec in engine_v2.FEATURES.values() if spec.part == "striking") == pytest.approx(1)

    rows = [bout("one", "2020-01-01"), bout("two", "2020-02-01", "A", "C", method="ko")]
    v1_snapshots, v1_prefights = engine.replay(rows)
    v2_snapshots, v2_prefights = engine_v2.replay(rows)
    for v1, v2 in zip(v1_snapshots, v2_snapshots, strict=True):
        assert v1.keys() == v2.keys()
        assert v1["metrics"].keys() | {"ko_wins_per_bout"} == v2["metrics"].keys()
        assert v1["coverage"].keys() == v2["coverage"].keys()
        for part in ("wrestling", "grappling", "resume"):
            assert v1["raw_parts"][part] == v2["raw_parts"][part]
    for v1, v2 in zip(v1_prefights, v2_prefights, strict=True):
        assert v1.keys() == v2.keys()
        assert {key: v1[key] for key in v1 if key != "parts"} == {
            key: v2[key] for key in v2 if key != "parts"
        }
    assert engine.replay(rows) == (v1_snapshots, v1_prefights)
