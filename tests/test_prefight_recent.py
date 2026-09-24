"""Known arithmetic, independent replay and strict temporal separation."""

import json
from copy import deepcopy
from dataclasses import replace
from math import exp2

import pytest
from test_prefight_defense import ALICE, BOB, _bout, _pair

from upset.data.audit_prefight_recent import audit_prefight_recent
from upset.data.export_prefight_recent import export_prefight_recent
from upset.data.prefight_recent import build_recent_history, read_recent_history


def _controlled_pair(bout):
    pair = _pair(bout)
    return [
        replace(row, stats=replace(row.stats, control_seconds=seconds))
        for row, seconds in zip(pair, (120, 30), strict=True)
    ]


def _indexed(rows):
    return {(r.source_bout_id, r.upset_fighter_id): r for r in rows}


def test_known_half_life_exposure_shrinkage_and_incoming_pair():
    fights = [_bout("first", "2020-01-01"), _bout("next", "2020-12-31")]
    stats = _controlled_pair("first") + _pair("next")
    rows = _indexed(build_recent_history(fights, stats))
    first, alice, bob = rows["first", ALICE], rows["next", ALICE], rows["next", BOB]
    assert first.prior_fights == 0
    assert all(x is None for x in first.features.values())
    assert alice.weighted_totals["appearances"] == 0.5
    assert alice.weighted_totals["seconds"] == 150
    assert alice.weighted_totals["sig_landed"] == 5
    assert alice.weighted_totals["sig_absorbed"] == 2.5
    assert alice.population_rates["sig_landed_per_minute"] == 1.5
    assert alice.features["sig_landed_per_minute"] == pytest.approx(1650 / 1050)
    assert alice.features["sig_defense"] == pytest.approx((2.5 + 50 * 0.5) / 55)
    assert alice.features["control_margin"] == pytest.approx(45 / 1050)
    assert bob.features["control_margin"] == -alice.features["control_margin"]
    assert audit_prefight_recent(fights, stats, rows)["all_recent_rows_checked"] == 4


def test_missing_control_is_distinct_from_observed_zero():
    fights = [_bout("first", "2020-01-01"), _bout("next", "2020-02-01")]
    stats = _pair("first") + _pair("next")
    missing = _indexed(build_recent_history(fights, stats))["next", ALICE]
    assert missing.features["control_margin"] is None
    assert missing.weighted_totals["control_seconds"] == 0
    zero_stats = [replace(s, stats=replace(s.stats, control_seconds=0)) for s in stats]
    observed = _indexed(build_recent_history(fights, zero_stats))["next", ALICE]
    assert observed.features["control_margin"] == 0
    assert observed.weighted_totals["control_seconds"] > 0
    zero_stats[1] = replace(
        zero_stats[1], stats=replace(zero_stats[1].stats, control_seconds=None)
    )
    partial = _indexed(build_recent_history(fights, zero_stats))["next", ALICE]
    assert partial.features["control_margin"] is None


def test_weighted_counts_over_seconds_not_average_of_bout_rates():
    fights = [
        _bout("brief", "2020-01-01"),
        _bout("long", "2020-01-02"),
        _bout("target", "2020-01-03"),
    ]
    stats = _pair("brief", seconds=10) + _pair("long", seconds=900) + _pair("target")
    row = _indexed(build_recent_history(fights, stats))["target", ALICE]
    expected_seconds = 10 * exp2(-2 / 365) + 900 * exp2(-1 / 365)
    expected_landed = 10 * exp2(-2 / 365) + 10 * exp2(-1 / 365)
    expected_prior = 30 * 60 / 1820
    assert row.features["sig_landed_per_minute"] == pytest.approx(
        (60 * expected_landed + 900 * expected_prior) / (expected_seconds + 900)
    )


def test_same_date_current_future_statistics_and_order_leave_earlier_rows_unchanged():
    fights = [_bout("first", "2020-01-01"), _bout("target", "2020-12-31")]
    stats = _pair("first") + _pair("target")
    original = _indexed(build_recent_history(fights, stats))
    changed_fights = fights + [
        _bout("same", "2020-12-31", winner=None),
        _bout("future", "2022-01-01"),
    ]
    changed_stats = (
        _pair("first")
        + _pair("target", a_kd=50)
        + _pair("same", a_kd=80)
        + _pair("future", a_kd=100)
    )
    changed = _indexed(
        build_recent_history(
            list(reversed(changed_fights)), list(reversed(changed_stats))
        )
    )
    assert all(changed[key] == row for key, row in original.items())
    assert changed["same", ALICE].features == changed["target", ALICE].features
    assert changed["future", ALICE].prior_fights == 3  # Draw/NC still supplies stats.
    assert (
        audit_prefight_recent(changed_fights, changed_stats, changed)["comparison"]
        == "matched"
    )


def test_debutant_uses_earlier_population_without_inventing_personal_exposure():
    first, newcomer = _bout("first", "2020-01-01"), _bout("new", "2021-01-01")
    cid, did = (
        "00000000-0000-4000-8000-000000000003",
        "00000000-0000-4000-8000-000000000004",
    )
    newcomer = replace(newcomer, upset_fighter_1_id=cid, upset_fighter_2_id=did)
    new_stats = [
        replace(s, upset_fighter_id=i)
        for s, i in zip(_pair("new"), (cid, did), strict=True)
    ]
    rows = _indexed(build_recent_history([first, newcomer], _pair("first") + new_stats))
    for i in (cid, did):
        row = rows["new", i]
        assert row.prior_fights == 0
        assert row.weighted_totals["seconds"] == 0
        assert row.features["sig_landed_per_minute"] == 1.5
        assert row.features == row.population_rates


@pytest.mark.parametrize(
    "field,name",
    [
        ("weighted_totals", "seconds"),
        ("population_rates", "sig_accuracy"),
        ("features", "td_defense"),
    ],
)
def test_audit_rejects_numeric_corruption(field, name):
    fights = [_bout("first", "2020-01-01"), _bout("next", "2020-12-31")]
    stats = _pair("first") + _pair("next")
    rows = _indexed(build_recent_history(fights, stats))
    corrupted = deepcopy(rows)
    getattr(corrupted["next", ALICE], field)[name] += 0.01
    with pytest.raises(ValueError, match="Incorrect recent"):
        audit_prefight_recent(fights, stats, corrupted)


def test_audit_does_not_share_builder_weighting_arithmetic(monkeypatch):
    fights = [_bout("first", "2020-01-01"), _bout("next", "2020-12-31")]
    stats = _pair("first") + _pair("next")
    monkeypatch.setattr("upset.data.prefight_recent.HALF_LIFE_DAYS", 730)
    bad = _indexed(build_recent_history(fights, stats))
    with pytest.raises(ValueError, match="Incorrect recent"):
        audit_prefight_recent(fights, stats, bad)


def test_export_roundtrip_repeatability_and_refusal_to_replace_different_output(
    tmp_path,
):
    fights = [_bout("first", "2020-01-01"), _bout("next", "2020-12-31")]
    stats = _pair("first") + _pair("next")
    fp, sp, output = [
        tmp_path / n for n in ("fights.jsonl", "stats.jsonl", "recent.jsonl")
    ]
    for path, records in ((fp, fights), (sp, stats)):
        path.write_text("".join(json.dumps(r.as_record()) + "\n" for r in records))
    assert export_prefight_recent(fp, sp, output) == 4
    original = output.read_bytes()
    assert export_prefight_recent(fp, sp, output) == 4
    assert output.read_bytes() == original
    assert read_recent_history(output) == _indexed(build_recent_history(fights, stats))
    output.write_text("preserve this evidence\n")
    with pytest.raises(ValueError, match="Existing recent history differs"):
        export_prefight_recent(fp, sp, output)
    assert output.read_text() == "preserve this evidence\n"
    with pytest.raises(ValueError, match="distinct"):
        export_prefight_recent(fp, sp, fp)


def test_source_pairs_dates_and_nonfinite_saved_values_are_rejected(tmp_path):
    fights, stats = [_bout("first", "2020-01-01")], _pair("first")
    with pytest.raises(ValueError, match="Missing paired"):
        build_recent_history(fights, stats[:1])
    bad = replace(stats[0], stats=replace(stats[0].stats, submission_attempts=-1))
    with pytest.raises(ValueError, match="submission_attempts"):
        build_recent_history(fights, [bad, stats[1]])
    records = [r.as_record() for r in build_recent_history(fights, stats)]
    records[0]["weighted_totals"]["seconds"] = float("nan")
    path = tmp_path / "bad.jsonl"
    path.write_text("\n".join(json.dumps(r) for r in records))
    with pytest.raises(ValueError, match="numeric value"):
        read_recent_history(path)
