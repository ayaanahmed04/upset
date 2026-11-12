"""Experimental means are gated, dated and separate from recorded statistics."""

import json
from datetime import date, timedelta

import pytest
from test_research_app import A, B, build, fixture

from upset import research_app as app
from upset.skill import striking_rolling
from upset.skill.striking_adapter import digest
from upset.skill.striking_preview import (
    ExperimentalPreview,
    daily_intercepts,
    load_preview,
    verify_gate,
)


def gate_report():
    return {'decision': {'eligible_for_experimental_mean_preview': True,
                         'mean_bias_percentage_points_predicted_minus_observed': .1,
                         'material_point_regression_groups': []},
            'primary_point_comparisons': {'sample_adjusted': {
                'candidate_minus_reference_nll': {'interval_95': [-.1, -.01]}}},
            'subgroups': {}, 'public_release': False, 'opponent_adjusted': False,
            'base_model': {'half_life_days': 365, 'strength': 100}}


def preview(database):
    observations = [{'fighter_id': A, 'event_date': '2019-01-01', 'status': 'observed', 'landed': 50, 'attempts': 100},
                    {'fighter_id': B, 'event_date': '2019-01-01', 'status': 'observed', 'landed': 20, 'attempts': 100},
                    {'fighter_id': A, 'event_date': '2019-01-04', 'status': 'observed', 'landed': 100, 'attempts': 100}]
    metadata = {'input_database': str(database), 'model': {'half_life_days': 365, 'strength': 100},
                'latest_event': '2019-01-04', 'before_exclusive': '2019-01-05'}
    lookup = {f'2019-01-0{i}': {'intercept': 0, 'sides': 2, 'latest_event': None if i == 1 else '2019-01-01'}
              for i in range(1, 6)}
    return ExperimentalPreview(metadata, observations, lookup)


def test_gate_cannot_be_enabled_with_a_failed_bias_interval_or_subgroup():
    verify_gate(gate_report())
    for field, value in [('eligible_for_experimental_mean_preview', False),
                         ('mean_bias_percentage_points_predicted_minus_observed', 1.01),
                         ('mean_bias_percentage_points_predicted_minus_observed', float('nan')),
                         ('material_point_regression_groups', ['Heavyweight'])]:
        report = gate_report()
        report['decision'][field] = value
        with pytest.raises(ValueError, match='preview checks'):
            verify_gate(report)
    report = gate_report()
    report['primary_point_comparisons']['sample_adjusted']['candidate_minus_reference_nll']['interval_95'] = [-.1, .01]
    with pytest.raises(ValueError):
        verify_gate(report)


def test_estimate_uses_strict_cutoff_and_matches_weighted_mean_math(tmp_path):
    database = tmp_path/'source.sqlite'
    p = preview(database)
    report = {'id': A, 'before': '2019-01-04', 'window': 0}
    result = p.estimate(database, report)
    weight = 2**(-3/365)
    expected = (50*weight+100*.35)/(100*weight+100)
    assert result['estimate'] == pytest.approx(expected)
    assert result['raw_accuracy'] == .5 and result['attempts'] == 100 and result['bouts'] == 1
    assert result['experimental'] and not result['validated_skill'] and not result['opponent_adjusted']
    next_day = p.estimate(database, {**report, 'before': '2019-01-05'})
    assert next_day['bouts'] == 2 and next_day['raw_accuracy'] == .75


def test_preview_rejects_mismatched_database_and_unsupported_windows_dates(tmp_path):
    database = tmp_path/'source.sqlite'
    p = preview(database)
    row = {'id': A, 'before': '2019-01-04', 'window': 0}
    assert p.estimate(database, {**row, 'window': 5})['status'] == 'career_only'
    for cutoff in ('2018-12-31', '2019-01-06'):
        assert p.estimate(database, {**row, 'before': cutoff})['status'] == 'unsupported_cutoff'
    assert p.estimate(database, {**row, 'before': '2019-01-01'})['status'] == 'insufficient_history'
    with pytest.raises(ValueError, match='different serving database'):
        p.estimate(tmp_path/'other.sqlite', row)


def test_request_time_does_not_fit_and_cache_is_bounded(tmp_path, monkeypatch):
    def fail(*args, **kwargs):
        raise AssertionError('Fitting at request time is forbidden.')
    monkeypatch.setattr(striking_rolling, 'fit_intercept', fail)
    p = preview(tmp_path/'source.sqlite')
    assert p.estimate(p.database, {'id': A, 'before': '2019-01-04', 'window': 0})['status'] == 'available'
    for i in range(30):
        p.state((date(2019, 1, 1)+timedelta(days=i)).isoformat())
    assert len(p._states) == 16


def test_offline_daily_lookup_excludes_same_date_outcomes():
    rows = [{'fighter_id': A, 'event_date': '2019-01-01', 'status': 'observed', 'landed': 8,
             'attempts': 10, 'recent_uncalibrated': .5}]
    result = daily_intercepts(rows, '2019-01-02')
    assert result['2019-01-01']['intercept'] == 0
    assert result['2019-01-01']['sides'] == 0
    assert result['2019-01-02']['intercept'] == .5
    assert result['2019-01-02']['latest_event'] < '2019-01-02'


def test_loading_refuses_observation_tampering_or_model_substitution(tmp_path):
    database = tmp_path/'source.sqlite'
    database.write_bytes(b'isolated fixture')
    p = preview(database)
    folder = tmp_path/'preview'
    folder.mkdir()
    report_path = tmp_path/'gate.json'
    report_path.write_text(json.dumps(gate_report()))
    (folder/'observations.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in p.observations))
    (folder/'daily_intercepts.json').write_text(json.dumps(p.intercepts))
    metadata = {**p.metadata, 'version': 'experimental_striking_mean_v1', 'experimental': True,
                'validated_skill': False, 'database_sha256': digest(database),
                'gate_report': str(report_path), 'gate_report_sha256': digest(report_path),
                'observations': len(p.observations), 'input_sha256': {},
                'output_sha256': {name: digest(folder/name) for name in ('observations.jsonl', 'daily_intercepts.json')}}
    path = folder/'manifest.json'
    path.write_text(json.dumps(metadata))
    assert load_preview(folder, database).database == database
    metadata['model'] = {'half_life_days': 1, 'strength': 1}
    path.write_text(json.dumps(metadata))
    with pytest.raises(ValueError, match='model differs'):
        load_preview(folder, database)
    metadata['model'] = gate_report()['base_model']
    path.write_text(json.dumps(metadata))
    (folder/'observations.jsonl').write_text('tampered')
    with pytest.raises(ValueError, match='output hash'):
        load_preview(folder, database)


def test_optional_api_field_does_not_replace_or_change_raw_metrics(tmp_path, monkeypatch):
    paths = fixture(tmp_path)
    build(paths, tmp_path/'research')
    database = tmp_path/'research/upset.sqlite'
    monkeypatch.setattr(app, 'STRIKING_PREVIEW', None)
    url = '/api/fighter?id='+A+'&before=2026-09-21&window=0'
    raw = app.route(database, url)
    p = preview(database)
    monkeypatch.setattr(app, 'STRIKING_PREVIEW', p)
    result = app.route(database, url)
    assert result['experimental_striking']['status'] == 'unsupported_cutoff'
    assert {k: v for k, v in result.items() if k != 'experimental_striking'} == raw
