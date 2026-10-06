"""Independent temporal audit and fixed comparative integration."""

import json
from copy import deepcopy
from dataclasses import replace
from math import exp2

import numpy as np
import pytest
import test_recent_form as fixtures
from test_prefight_defense import ALICE, BOB, _bout, _pair

from upset.data.audit_prefight_adjusted import audit_prefight_adjusted
from upset.data.prefight_adjusted import (
    build_adjusted_history,
    read_adjusted_history,
)
from upset.data.prefight_recent import build_recent_history
from upset.modeling.defense_ablation import export_defense_ablation
from upset.modeling.elo_comparison import export_elo_comparison
from upset.modeling.evaluation import _sha256
from upset.modeling.opponent_adjusted import (
    ADJUSTED_COLUMNS,
    CANDIDATE,
    COLUMNS,
    REFERENCE,
    SIGNS,
    VARIANTS,
    compare_opponent_adjusted,
    export_opponent_adjusted,
    feature_matrix,
    join_adjusted,
)
from upset.modeling.recent_form import export_recent_form
from upset.modeling.symmetric import swap_features

history = fixtures.history
stats = fixtures.stats
recent = fixtures.recent
comparison = fixtures.comparison
new_comparison = fixtures.new_comparison


def indexed(rows):
    return {(row.source_bout_id, row.upset_fighter_id): row for row in rows}


@pytest.fixture(scope="module")
def adjusted(history, stats, recent):
    return indexed(build_adjusted_history(history[3], stats, recent))


@pytest.fixture(scope="module")
def adjusted_comparison(history, recent, adjusted, new_comparison):
    rows, defense, ratings, _ = history
    return compare_opponent_adjusted(
        rows, defense, ratings, recent, adjusted, new_comparison[0]
    )


def test_known_expectation_half_life_and_zero_history():
    fights = [
        _bout("first", "2020-01-01"),
        _bout("second", "2020-02-01"),
        _bout("target", "2021-01-31"),
    ]
    rows = (
        _pair("first", a_sig=10, b_sig=5)
        + _pair("second", a_sig=12, b_sig=3)
        + _pair("target")
    )
    recent = indexed(build_recent_history(fights, rows))
    adjusted = indexed(build_adjusted_history(fights, rows, recent))
    assert adjusted["first", ALICE].prior_fights == 0
    assert adjusted["second", ALICE].prior_fights == 1
    assert adjusted["second", ALICE].features["sig_excess_per_minute"] == 0
    # First day's opponent had no strictly earlier population rate. Second
    # day's conceded rate is known and uses B's *pre-second* snapshot.
    expected_rate = recent["second", BOB].features["sig_absorbed_per_minute"]
    assert expected_rate is not None
    excess = 12 - expected_rate * 300 / 60
    decay = exp2(-365 / 365)
    target = adjusted["target", ALICE]
    assert target.prior_fights == 2
    assert target.weighted_excess["sig_excess_per_minute"] == pytest.approx(
        excess * decay
    )
    assert target.weighted_seconds["sig_excess_per_minute"] == pytest.approx(150)
    assert target.features["sig_excess_per_minute"] == pytest.approx(
        60 * excess * decay / (150 + 900)
    )
    assert (
        audit_prefight_adjusted(fights, rows, recent, adjusted)["comparison"]
        == "matched"
    )


def test_opponent_prior_quality_changes_residual_not_own_landed_count():
    # A faces B and C with the same landed output. B previously absorbed 10,
    # C previously absorbed 2; their separately dated prior defenses differ.
    c = "00000000-0000-4000-8000-000000000003"
    d = "00000000-0000-4000-8000-000000000004"
    first = _bout("ab-first", "2020-01-01")
    cd = _bout("cd-first", "2020-01-01")
    cd = replace(cd, upset_fighter_1_id=c, upset_fighter_2_id=d)
    ab = _bout("ab-second", "2020-02-01")
    ac = _bout("ac-second", "2020-02-01")
    ac = replace(ac, upset_fighter_2_id=c)
    stats = _pair("ab-first", a_sig=10, b_sig=1)
    stats += [
        replace(row, upset_fighter_id=fighter_id)
        for row, fighter_id in zip(
            _pair("cd-first", a_sig=1, b_sig=2), (c, d), strict=True
        )
    ]
    stats += _pair("ab-second", a_sig=10) + [
        replace(row, upset_fighter_id=c) if side else row
        for side, row in enumerate(_pair("ac-second", a_sig=10))
    ]
    # The source fight fighter IDs must follow the revised second participant.
    ac = replace(ac, fight=replace(ac.fight, source_fighter_2_id="b"))
    fights = [first, cd, ab, ac]
    recent = indexed(build_recent_history(fights, stats))
    adjusted = indexed(build_adjusted_history(fights, stats, recent))
    rate_b = recent["ab-second", BOB].features["sig_absorbed_per_minute"]
    rate_c = recent["ac-second", c].features["sig_absorbed_per_minute"]
    assert rate_b > rate_c
    # Same-day bouts share the same pre-fight history. The impact of these
    # two actual observations can be compared by swapping their opponents in
    # an otherwise identical one-bout continuation.
    ab_only = indexed(
        build_adjusted_history(
            [first, cd, ab],
            stats[:6],
            indexed(build_recent_history([first, cd, ab], stats[:6])),
        )
    )
    ac_only = indexed(
        build_adjusted_history(
            [first, cd, ac],
            stats[:4] + stats[6:],
            indexed(build_recent_history([first, cd, ac], stats[:4] + stats[6:])),
        )
    )
    assert (
        adjusted["ab-second", ALICE].features == adjusted["ac-second", ALICE].features
    )
    assert ab_only["ab-second", ALICE].features == ac_only["ac-second", ALICE].features
    # Attach a third date to observe the adjusted past exposures.
    next_bout = _bout("next", "2020-03-01")
    ending = _pair("next")
    from_ab = indexed(
        build_adjusted_history(
            [first, cd, ab, next_bout],
            stats[:6] + ending,
            indexed(
                build_recent_history([first, cd, ab, next_bout], stats[:6] + ending)
            ),
        )
    )
    from_ac = indexed(
        build_adjusted_history(
            [first, cd, ac, next_bout],
            stats[:4] + stats[6:] + ending,
            indexed(
                build_recent_history(
                    [first, cd, ac, next_bout], stats[:4] + stats[6:] + ending
                )
            ),
        )
    )
    assert (
        from_ac["next", ALICE].features["sig_excess_per_minute"]
        > (from_ab["next", ALICE].features["sig_excess_per_minute"])
    )


def test_same_date_current_and_future_results_do_not_change_prior_features():
    fights = [_bout("first", "2020-01-01"), _bout("target", "2020-12-31")]
    stats = _pair("first") + _pair("target")
    original = indexed(
        build_adjusted_history(
            fights, stats, indexed(build_recent_history(fights, stats))
        )
    )
    changed_fights = fights + [
        _bout("same", "2020-12-31", winner=None),
        _bout("future", "2022-01-01"),
    ]
    changed_stats = (
        _pair("first")
        + _pair("target", a_sig=19)
        + _pair("same", a_sig=18)
        + _pair("future", a_sig=17)
    )
    changed_recent = indexed(build_recent_history(changed_fights, changed_stats))
    changed = indexed(
        build_adjusted_history(
            list(reversed(changed_fights)),
            list(reversed(changed_stats)),
            changed_recent,
        )
    )
    assert changed["target", ALICE] == original["target", ALICE]
    assert changed["target", BOB] == original["target", BOB]
    assert changed["same", ALICE].features == changed["target", ALICE].features
    assert changed["future", ALICE].prior_fights == 3
    assert (
        audit_prefight_adjusted(changed_fights, changed_stats, changed_recent, changed)[
            "comparison"
        ]
        == "matched"
    )


def test_independent_audit_rejects_corruption_and_changed_builder_half_life(
    monkeypatch,
):
    fights = [
        _bout("first", "2020-01-01"),
        _bout("second", "2020-02-01"),
        _bout("target", "2021-01-31"),
    ]
    stats = _pair("first") + _pair("second") + _pair("target")
    recent = indexed(build_recent_history(fights, stats))
    history = indexed(build_adjusted_history(fights, stats, recent))
    bad = dict(history)
    altered = history["target", ALICE]
    bad["target", ALICE] = replace(
        altered,
        features={
            **altered.features,
            "sig_excess_per_minute": altered.features["sig_excess_per_minute"] + 0.1,
        },
    )
    with pytest.raises(ValueError, match="Incorrect adjusted"):
        audit_prefight_adjusted(fights, stats, recent, bad)
    monkeypatch.setattr("upset.data.prefight_adjusted.HALF_LIFE_DAYS", 730)
    wrong = indexed(build_adjusted_history(fights, stats, recent))
    with pytest.raises(ValueError, match="Incorrect adjusted"):
        audit_prefight_adjusted(fights, stats, recent, wrong)


def test_swapped_fighter_ids_reconstruct_exact_signed_columns(
    history, recent, adjusted
):
    rows, defense, ratings, _ = history
    original = join_adjusted(rows, defense, ratings, recent, adjusted)
    flipped = [
        replace(
            row,
            fighter_a_id=row.fighter_b_id,
            fighter_b_id=row.fighter_a_id,
            feature_differences={
                name: None if value is None else -value
                for name, value in row.feature_differences.items()
            },
        )
        for row in rows
    ]
    swapped = join_adjusted(flipped, defense, ratings, recent, adjusted)
    assert len(COLUMNS) == 42 and len(ADJUSTED_COLUMNS) == 6
    assert np.array_equal(
        swap_features(feature_matrix(rows, original), SIGNS),
        feature_matrix(flipped, swapped),
        equal_nan=True,
    )


def test_cohort_reference_preservation_refit_and_diagnostics(
    adjusted_comparison, new_comparison
):
    old, _ = new_comparison
    predictions, report = adjusted_comparison
    assert len(predictions) == len(old) == 96
    assert report["decisive_bouts"] == 95 and report["draw_nc_exclusions"] == 1
    for older, newer in zip(old, predictions, strict=True):
        for field in (
            "probabilities_a_win",
            "swapped_probabilities_b_win",
            "raw_directional_probabilities",
        ):
            assert {
                name: value for name, value in newer[field].items() if name != CANDIDATE
            } == older[field]
        assert newer["event_date"] <= "2023-08-19"
        assert (newer["probabilities_a_win"][CANDIDATE] is None) == (
            newer["target_a_win"] is None
        )
    assert all(CANDIDATE not in r["probabilities_a_win"] for r in old)
    assert all(
        f["matched_logistic_refit_maximum_absolute_error"] <= 1e-12
        for f in report["folds"]
    )
    assert report["symmetry"][CANDIDATE]["maximum_absolute_error"] <= 1e-12
    assert report["symmetry"][CANDIDATE]["conflicting_winner_picks"] == 0
    assert len(report["paired_comparison"]) == 1
    assert set(report["pooled"]) == set(VARIANTS)


def test_validation_labels_isolate_fitted_predictions(
    history, recent, adjusted, new_comparison, adjusted_comparison
):
    rows, defense, ratings, _ = history
    altered = [
        replace(row, target_a_win=1 - row.target_a_win)
        if "2023-01-01" <= row.event_date <= "2023-08-19"
        and row.target_a_win is not None
        else row
        for row in rows
    ]
    saved = deepcopy(new_comparison[0])
    for row in saved:
        if row["fold"] == "2023_partial" and row["target_a_win"] is not None:
            row["target_a_win"] = 1 - row["target_a_win"]
    predictions, _ = compare_opponent_adjusted(
        altered, defense, ratings, recent, adjusted, saved
    )
    assert [r["probabilities_a_win"] for r in predictions] == [
        r["probabilities_a_win"] for r in adjusted_comparison[0]
    ]


@pytest.mark.parametrize("corruption", ["missing", "groups", "probability", "refit"])
def test_bad_reference_or_history_cannot_enter_fit(
    history, recent, adjusted, new_comparison, corruption
):
    rows, defense, ratings, _ = history
    saved = deepcopy(new_comparison[0])
    if corruption == "missing":
        saved.pop()
    elif corruption == "groups":
        saved[0]["diagnostic_groups"]["history"] = "invented"
    elif corruption == "probability":
        saved[0]["probabilities_a_win"][REFERENCE] = float("nan")
    else:
        saved[0]["probabilities_a_win"][REFERENCE] += 0.01
    with pytest.raises(ValueError, match="[Rr]eference|refit"):
        compare_opponent_adjusted(rows, defense, ratings, recent, adjusted, saved)


def test_export_full_hash_chain_readback_no_overwrite(tmp_path, history, stats, recent):
    rows, defense, ratings, fights = history
    paths = [
        tmp_path / name
        for name in (
            "matchups",
            "defense",
            "ratings",
            "recent",
            "fights",
            "stats",
            "registry",
        )
    ]
    for path, records in zip(
        paths[:-1],
        (rows, defense.values(), ratings.values(), recent.values(), fights, stats),
        strict=True,
    ):
        path.write_text("".join(json.dumps(row.as_record()) + "\n" for row in records))
    paths[-1].write_text('{"fixture":true}\n')
    first, elo, reference, output = [
        tmp_path / name for name in ("first", "elo", "reference", "output")
    ]
    export_defense_ablation(paths[0], paths[1], paths[-1], first, "base")
    export_elo_comparison(
        paths[0], paths[1], paths[2], paths[4], paths[-1], first, elo, "elo"
    )
    export_recent_form(*paths, elo, reference, "recent")
    pinned = _sha256(reference / "manifest.json")
    sources = {
        path: path.read_bytes()
        for path in (
            *paths,
            reference / "manifest.json",
            reference / "predictions.jsonl",
        )
    }
    result = export_opponent_adjusted(
        *paths, reference, output, "adjusted", expected_reference_sha256=pinned
    )
    assert result == json.loads((output / "manifest.json").read_text())
    assert result["adjusted_history_sha256"] == _sha256(
        output / "adjusted_history.jsonl"
    )
    assert result["predictions_sha256"] == _sha256(output / "predictions.jsonl")
    assert result["adjusted_audit"]["all_adjusted_rows_checked"] == len(recent)
    assert read_adjusted_history(output / "adjusted_history.jsonl") == (
        indexed(build_adjusted_history(fights, stats, recent))
    )
    assert all(path.read_bytes() == original for path, original in sources.items())
    with pytest.raises(ValueError, match="already exists"):
        export_opponent_adjusted(
            *paths, reference, output, "again", expected_reference_sha256=pinned
        )
    rejected = tmp_path / "rejected"
    with pytest.raises(ValueError, match="manifest hash"):
        export_opponent_adjusted(
            *paths, reference, rejected, "bad", expected_reference_sha256="other"
        )
    paths[5].write_bytes(sources[paths[5]] + b"\n")
    with pytest.raises(ValueError, match="source hash"):
        export_opponent_adjusted(
            *paths, reference, rejected, "bad", expected_reference_sha256=pinned
        )
    assert not rejected.exists()
