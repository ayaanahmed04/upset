from upset.ratings import round_research as RR


def row(n, **values):
    base = {"round_number": n, "sig_strikes_landed": 0, "sig_strikes_attempted": 0,
            "takedowns_landed": 0, "knockdowns": 0, "control_seconds": 0}
    base.update(values)
    return base


def test_round_lines_use_the_finish_time_for_the_last_round():
    fight = {"ids": ["a", "b"], "round": 2, "time": "1:30"}
    by = {"a": {1: row(1), 2: row(2)}, "b": {1: row(1), 2: row(2)}}
    lines = RR.round_lines(fight, by)
    assert [line["minutes"] for line in lines] == [5.0, 1.5]
    assert [line["full"] for line in lines] == [True, False]
    assert RR.round_lines({"ids": ["a", "b"], "round": 3, "time": None}, by) == []


def test_judge_and_wrestled():
    own = row(1, sig_strikes_landed=10, takedowns_landed=1)
    opp = row(1, sig_strikes_landed=15)
    assert RR.judge(own, opp) == -3
    assert RR.judge(opp, own) == 3
    assert RR.wrestled(own) and not RR.wrestled(opp)
    assert RR.wrestled(row(1, control_seconds=60)) and not RR.wrestled(row(1, control_seconds=59))


def test_audit_keeps_only_rounds_that_add_up():
    fights = {f: {"ids": ["a", "b"], "round": 2, "time": "5:00", "day": "2015-01-01"} for f in ("ok", "bad", "short")}
    by = {"a": {1: row(1, sig_strikes_landed=3), 2: row(2, sig_strikes_landed=4)},
          "b": {1: row(1, sig_strikes_landed=1), 2: row(2, sig_strikes_landed=1)}}
    stats = {"ok": {"a": {"sig_strikes_landed": 7}, "b": {"sig_strikes_landed": 2}},
             "bad": {"a": {"sig_strikes_landed": 8}, "b": {"sig_strikes_landed": 2}},
             "short": {"a": {"sig_strikes_landed": 7}, "b": {"sig_strikes_landed": 2}}}
    short = {"a": {1: by["a"][1]}, "b": {1: by["b"][1]}}
    good, why = RR.audit({"ok": by, "bad": by, "short": short}, stats, fights, conflicts=set())
    assert set(good) == {"ok"}
    assert why["rounds do not add up to fight totals"] == 1
    assert why["round count differs from result"] == 1


def test_history_only_uses_earlier_fights():
    fights = {"f1": {"ids": ["a", "b"], "names": ["A", "B"], "round": 2, "time": "5:00", "day": "2015-01-01"},
              "f2": {"ids": ["a", "c"], "names": ["A", "C"], "round": 1, "time": "2:00", "day": "2015-06-01"}}
    first = {"a": {1: row(1, sig_strikes_attempted=20, takedowns_landed=1), 2: row(2, sig_strikes_attempted=30)},
             "b": {1: row(1, sig_strikes_attempted=10), 2: row(2, sig_strikes_attempted=12)}}
    second = {"a": {1: row(1)}, "c": {1: row(1)}}
    forecasts = {f: {"y": 1, "fighter_ids": fights[f]["ids"], "prior_decisive_bouts": [1, 1]} for f in fights}
    records, league, _ = RR.build(fights, {"f1": first, "f2": second}, forecasts, {"f1": 0.6, "f2": 0.6})
    assert [r["fid"] for r in records] == ["f1", "f2"]
    assert all(sum(h.values()) == 0 for h in records[0]["h"])
    assert records[1]["h"][0]["all_rounds"] == 2 and records[1]["h"][1]["all_rounds"] == 0
    empty = RR.describe(records[0]["h"][0], league, 24)
    for key in ("rounds_won", "late_edge", "fade", "suppressed"):
        assert abs(empty[key]) < 1e-12
