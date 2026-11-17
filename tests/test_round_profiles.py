from upset.data import round_profiles as P


def row(n, **values):
    base = {"round_number": n, "sig_strikes_landed": 0, "sig_strikes_attempted": 0,
            "takedowns_landed": 0, "knockdowns": 0, "control_seconds": 0}
    base.update(values)
    return base


def test_outcome_and_finish_labels():
    assert P.outcome({"winner": 0, "method": "KO/TKO"}, 0) == "W"
    assert P.outcome({"winner": 0, "method": "KO/TKO"}, 1) == "L"
    assert P.outcome({"winner": None, "method": "Decision - Split"}, 0) == "D"
    assert P.outcome({"winner": None, "method": "Overturned"}, 0) == "NC"
    assert P.outcome({"winner": None, "method": "Could Not Continue"}, 1) == "NC"
    assert [P.finish_code(m) for m in ("KO/TKO", "TKO - Doctor's Stoppage", "Submission", "Decision - Unanimous", "DQ")] == \
        ["KO", "KO", "SUB", None, "DQ"]


def test_strip_scores_full_rounds_and_marks_the_finish():
    fight = {"ids": ["a", "b"], "names": ["A", "B"], "day": "2024-01-01", "round": 2, "time": "3:10"}
    by = {"a": {1: row(1, sig_strikes_landed=20), 2: row(2, sig_strikes_landed=5)},
          "b": {1: row(1, sig_strikes_landed=10), 2: row(2, sig_strikes_landed=9)}}
    lines = P.RR.round_lines(fight, by)
    result = {"winner": 1, "method": "Submission"}
    a = P.strip("f", fight, lines, 0, result, {"b": "Bee"})
    b = P.strip("f", fight, lines, 1, result, {})
    assert [r["code"] for r in a["rounds"]] == ["W", "X"] and a["result"] == "L" and a["opponent"] == "Bee"
    assert [r["code"] for r in b["rounds"]] == ["L", "F"] and b["finish"] == "SUB" and b["opponent"] == "A"
    assert a["rounds"][0]["d"][:2] == [20, 10] and b["rounds"][0]["d"][:2] == [10, 20]


def test_percentile_and_profile_view():
    assert P.percentile([1, 2, 3, 4], 4) == 88
    assert P.percentile([1, 2, 3, 4], 0) == 0
    assert P.percentile([], 3) is None and P.percentile([1], None) is None
    data = {"league": {"late_change": 7}, "fighters": {"x": {"recent": [{"fight_id": "f"}], "rounds": 3}, "y": {"recent": []}}}
    assert P.profile(data, "x")["status"] == "available" and P.profile(data, "x")["league"] == {"late_change": 7}
    assert P.profile(data, "y") == {"status": "unavailable"} and P.profile(data, "nobody") == {"status": "unavailable"}
