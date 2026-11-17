"""Striking identity boundaries, chronology, score arithmetic and artifact checks."""

import hashlib
import json
from copy import deepcopy
from math import comb, isfinite, log

import numpy as np
import pytest
from test_research_app import A, B, build, fixture

from upset.skill.striking_accuracy import (
    CONFIG,
    MODELS,
    adjusted_mean,
    evaluate,
    paired_comparisons,
    predict,
    run,
    score,
    synthetic_recovery,
)
from upset.skill.striking_adapter import (
    audit_rows,
    digest,
    export,
    load_adapter,
    paired_sides,
    read_sides,
)


def pair(day="2026-10-10", bid="x"):
    fight = {"source": "cito", "source_bout_id": bid, "event_date": day,
             "upset_fighter_1_id": A, "upset_fighter_2_id": B,
             "source_fighter_1_id": "a", "source_fighter_2_id": "b",
             "source_event_id": "card", "weight_class": "UFC Lightweight Title Bout"}
    stats = {uid: {"source": "cito", "source_bout_id": bid, "source_fighter_id": sid,
                   "upset_fighter_id": uid, "fight_duration_seconds": 300,
                   "sig_strikes_landed": y, "sig_strikes_attempted": n}
             for uid, sid, y, n in ((A, "a", 30, 50), (B, "b", 10, 40))}
    return fight, stats


def observation(day, bid, landed, attempts):
    fight, stats = pair(day, bid)
    stats[A].update(sig_strikes_landed=landed, sig_strikes_attempted=attempts)
    return paired_sides("cito:" + bid, fight, stats, "hash")[0]


def test_own_and_opposing_counts_and_full_fight_time_are_distinct():
    fight, stats = pair()
    a, b = paired_sides("cito:x", fight, stats, "hash")
    assert a["fighter_id"] == A and a["opponent_id"] == B
    assert (a["landed"], a["attempts"], a["observed_accuracy"]) == (30, 50, .6)
    assert (a["opponent_landed"], a["opponent_attempts"]) == (10, 40)
    assert b["observed_accuracy"] == .25 and a["landed_per_minute"] == 6
    assert a["division"] == "Lightweight" and a["event_id"] == "cito:card"
    assert a["source_rows_sha256"] == b["source_rows_sha256"]
    audit_rows([a, b], "2026-10-11", "hash")


@pytest.mark.parametrize("landed,attempts,status", [
    (0, 0, "zero_attempts"), (None, 10, "missing_counts"),
    (1, None, "missing_counts"), (11, 10, "invalid_counts"),
    (-1, 10, "invalid_counts"), (False, 10, "invalid_counts"),
    (1, True, "invalid_counts"), (1.0, 10, "invalid_counts"),
])
def test_missing_invalid_zero_and_boolean_counts(landed, attempts, status):
    fight, stats = pair()
    stats[A].update(sig_strikes_landed=landed, sig_strikes_attempted=attempts)
    a, b = paired_sides("cito:x", fight, stats, "hash")
    assert a["status"] == status and a["observed_accuracy"] is None
    assert a["raw_counts"]["own"] == {"landed": landed, "attempts": attempts}
    assert b["status"] == "observed" and b["opponent_status"] == status
    if status != "zero_attempts":
        assert a["landed"] is None and a["attempts"] is None
    audit_rows([a, b], "2026-10-11", "hash")


@pytest.mark.parametrize("seconds,status,rate", [
    (None, "observed", None), (0, "positive_attempts_zero_duration", None),
    (30, "observed", 60), (300, "observed", 6),
])
def test_duration_eligibility_and_short_fights(seconds, status, rate):
    fight, stats = pair()
    for row in stats.values():
        row['fight_duration_seconds'] = seconds
    a, b = paired_sides("cito:x", fight, stats, "hash")
    assert a["status"] == status and a["landed_per_minute"] == rate
    assert a["short_fight"] == (seconds == 30)
    audit_rows([a, b], "2026-10-11", "hash")


@pytest.mark.parametrize("corruption", ["duration", "provider", "participant", "date"])
def test_structural_corruption_stops_export(corruption):
    fight, stats = pair()
    if corruption == "duration":
        stats[B]['fight_duration_seconds'] = 100
    elif corruption == "provider":
        stats[B]['source_fighter_id'] = 'other'
    elif corruption == "participant":
        fight['upset_fighter_2_id'] = A
    else:
        fight['event_date'] = '20261010'
    with pytest.raises(ValueError):
        paired_sides("cito:x", fight, stats, "hash")


def test_strict_cutoff_readonly_inputs_and_registry_binding(tmp_path):
    paths = fixture(tmp_path)
    folder = tmp_path / "database"
    build(paths, folder)
    database = folder / "upset.sqlite"
    before = database.read_bytes()
    rows, _, excluded = read_sides(database, paths[2], "2026-09-20")
    assert len(rows) == 2 and excluded == 1
    assert all(r["event_date"] < "2026-09-20" for r in rows)
    exported = tmp_path / "striking"
    result = export(database, paths[2], "2026-09-21", exported)
    assert result["side_rows"] == 4 and result["statuses"] == {"observed": 4}
    assert load_adapter(exported)[0] == read_sides(database, paths[2], "2026-09-21")[0]
    assert database.read_bytes() == before
    with pytest.raises(ValueError, match="new output"):
        export(database, paths[2], "2026-09-21", exported)
    (exported / "sides.jsonl").write_bytes((exported / "sides.jsonl").read_bytes() + b'\n')
    with pytest.raises(ValueError, match="output hash"):
        load_adapter(exported)
    other_registry = tmp_path / 'other-registry.json'
    other_registry.write_bytes(paths[2].read_bytes())
    with pytest.raises(ValueError, match="not bound"):
        read_sides(database, other_registry, "2026-09-21")
    database.write_bytes(before + b"tampered")
    with pytest.raises(ValueError, match="database hash"):
        read_sides(database, paths[2], "2026-09-21")


def test_adapter_pair_cutoff_and_measurement_tampering():
    fight, stats = pair()
    rows = paired_sides("cito:x", fight, stats, "hash")
    for altered in ([rows[0]], rows + [rows[0]]):
        with pytest.raises(ValueError):
            audit_rows(altered, "2026-10-11", "hash")
    with pytest.raises(ValueError, match="cutoff"):
        audit_rows(rows, "2026-10-10", "hash")
    changed = deepcopy(rows)
    changed[0]['observed_accuracy'] = .9
    with pytest.raises(ValueError, match="measurements disagree"):
        audit_rows(changed, "2026-10-11", "hash")


def test_known_smoothing_and_large_sample_convergence():
    assert adjusted_mean(30, 50, .4, 20) == 38/70
    assert adjusted_mean(0, 0, .4, 20) == .4
    assert adjusted_mean(0, 0, None, 20) is None
    assert abs(adjusted_mean(60000, 100000, .4, 20)-.6) < .0001
    for y, n, p, k in [(11, 10, .4, 20), (1, 10, .4, -1), (1, 10, float('nan'), 20)]:
        with pytest.raises(ValueError):
            adjusted_mean(y, n, p, k)


def test_same_date_and_future_results_cannot_leak_into_earlier_predictions():
    rows = [observation('2013-01-01', 'a', 20, 40),
            observation('2013-02-01', 'b', 1, 10),
            observation('2013-02-01', 'c', 9, 10),
            observation('2020-01-01', 'd', 8, 10)]
    original = predict(rows, 20)
    altered = deepcopy(rows)
    for row in altered[1:]:
        row['landed'] = 0
    changed = predict(altered, 20)
    for old, new in zip(original[:3], changed[:3]):
        assert all(old[k] == new[k] for k in (*MODELS, 'prior_attempts', 'prior_bouts'))
    assert original[1]['prior_attempts'] == original[2]['prior_attempts'] == 40
    assert predict(rows[::-1], 20) == original
    with pytest.raises(ValueError, match='Duplicate'):
        predict(rows + rows[:1], 20)


def test_zero_and_missing_bouts_consume_last_five_slots():
    rows = [observation('2013-01-01', 'a', 20, 40)]
    rows += [observation(f'2013-01-0{i}', str(i), None if i % 2 else 0,
                         None if i % 2 else 0) for i in range(2, 7)]
    rows += [observation('2013-01-07', 'g', 1, 10)]
    final = predict(rows, 20)[-1]
    assert final['raw_career'] == .5 and final['raw_last5'] is None
    assert final['last5_jeffreys'] == .5 and final['prior_bouts'] == 6


def test_same_day_last_five_boundary_is_explicit():
    rows = [observation('2013-01-01', 'a', 1, 10),
            observation('2013-01-01', 'b', 2, 10)]
    rows += [observation(f'2013-01-0{i}', str(i), 3, 10) for i in range(2, 8)]
    predictions = predict(rows, 20)
    assert predictions[-2]['last5_splits_same_day_boundary']
    assert not predictions[-1]['last5_splits_same_day_boundary']


def test_development_outcomes_do_not_select_striking_k():
    rows = [observation('2011-01-01', 'seed', 20, 40),
            observation('2013-01-01', 'a', 8, 10),
            observation('2014-01-01', 'b', 2, 10),
            observation('2020-01-01', 'c', 7, 10),
            observation('2020-02-01', 'd', 3, 10)]
    _, original = evaluate(rows)
    altered = deepcopy(rows)
    altered[-1]['landed'] = 10
    altered[-2]['landed'] = 0
    _, changed = evaluate(altered)
    assert changed['selected_prior_attempts'] == original['selected_prior_attempts']
    assert changed['tuning_2012_2018'] == original['tuning_2012_2018']
    assert original['development_common_support']['side_bouts'] == 2
    assert not original['public_release'] and not original['opponent_adjusted']


def test_binomial_score_matches_independent_probability_and_brier_arithmetic():
    for n in range(1, 12):
        for y in range(n+1):
            row = {'landed': y, 'attempts': n, 'p': .37}
            nll, ce, brier = score(row, 'p')
            assert nll == pytest.approx(-log(comb(n, y) * .37**y * .63**(n-y)))
            assert brier == pytest.approx(sum((.37-x)**2 for x in [1]*y + [0]*(n-y)))
            assert ce >= nll - 1e-12
    for p in (0., 1.):
        assert all(isfinite(x) for x in score({'landed': 3, 'attempts': 5, 'p': p}, 'p'))


def test_bootstrap_resamples_whole_dates_with_side_weighting():
    def row(day, y, n, p):
        return {'event_date': day, 'landed': y, 'attempts': n,
                **{m: .4 for m in MODELS}, 'sample_adjusted': p}
    rows = [row('2020-01-01', 5, 10, .6), row('2020-01-02', 3, 10, .3),
            row('2020-01-02', 7, 10, .7)]
    result = paired_comparisons(rows)['raw_career']
    rng = np.random.default_rng(CONFIG['seed'])
    selections = rng.integers(0, 2, size=(1000, 2))
    differences = [[score(r, 'sample_adjusted')[0] - score(r, 'raw_career')[0]
                    for r in rows if r['event_date'] == day]
                   for day in ['2020-01-01', '2020-01-02']]
    direct = [sum(sum(differences[i]) for i in chosen) /
              sum(len(differences[i]) for i in chosen) for chosen in selections]
    assert result['date_cluster_bootstrap_95_interval'] == pytest.approx(np.quantile(direct, [.025, .975]))
    assert paired_comparisons(rows) == paired_comparisons(rows)
    assert paired_comparisons(rows[:1])['raw_career']['date_cluster_bootstrap_95_interval'] is None


def test_matching_synthetic_prior_reduces_finite_sample_error():
    result = synthetic_recovery()
    assert result == synthetic_recovery()
    for row in result['results']:
        assert abs(row['mean_bias']) < .01
        if row['prior_attempts'] > 0:
            assert row['shrink_rmse'] < row['raw_rmse']


def test_end_to_end_immutable_prototype_and_input_tampering(tmp_path):
    # Build an isolated synthetic artifact, without changing serving data.
    sides = []
    for day, bid in [('2011-01-01', 'seed'), ('2013-01-01', 'a'), ('2020-01-01', 'b')]:
        fight, stats = pair(day, bid)
        sides += paired_sides('cito:' + bid, fight, stats, 'dbhash')
    adapter = tmp_path / 'adapter'
    adapter.mkdir()
    body = ''.join(json.dumps(r) + '\n' for r in sides).encode()
    (adapter / 'sides.jsonl').write_bytes(body)
    fake_db = tmp_path / 'seed.sqlite'
    fake_db.write_bytes(b'fixture')
    dbhash = digest(fake_db)
    for row in sides:
        row['database_sha256'] = dbhash
    body = ''.join(json.dumps(r) + '\n' for r in sides).encode()
    (adapter / 'sides.jsonl').write_bytes(body)
    manifest = {'adapter_version': sides[0]['adapter_version'], 'before_exclusive': '2026-10-26',
                'side_rows': 6, 'fights': 3, 'input_database': str(fake_db), 'database_sha256': dbhash,
                'input_sha256': {str(fake_db): dbhash},
                'output_sha256': {'sides.jsonl': hashlib.sha256(body).hexdigest()}}
    (adapter / 'manifest.json').write_text(json.dumps(manifest))
    protocol = tmp_path / 'protocol.md'
    protocol.write_text('Synthetic end-to-end fixture, no real outcomes.')
    out = tmp_path / 'prototype'
    result = run(adapter, protocol, out)
    assert result['public_release'] is False
    for name, expected in result['output_sha256'].items():
        assert digest(out / name) == expected
    with pytest.raises(ValueError, match='new output'):
        run(adapter, protocol, out)
    fake_db.write_bytes(b'changed')
    with pytest.raises(ValueError, match='hash differs'):
        run(adapter, protocol, tmp_path / 'tampered')
