"""Independent probability, chronology, calibration and repeatability checks."""

import json
from copy import deepcopy
from math import comb, exp, lgamma

import numpy as np
import pytest
from scipy.stats import binom, spearmanr
from test_striking_skill import observation, pair

from upset.skill import striking_accuracy as original
from upset.skill import striking_validation as study
from upset.skill.striking_adapter import digest, paired_sides
from upset.skill.striking_repeatability import correlation, reliability, summarize_pairs


def history():
    return [observation('2011-01-01', 'seed', 20, 40),
            observation('2013-01-01', 'a', 8, 20), observation('2014-01-01', 'b', 9, 20),
            observation('2020-01-01', 'c', 12, 20), observation('2020-02-01', 'd', 7, 20)]


def test_independent_history_detects_drift():
    sides = history()
    predictions = original.predict(sides, 500)
    assert study.independent_history_check(sides, predictions) == len(sides)
    altered = deepcopy(predictions)
    altered[2]['prior_landed'] += 1
    with pytest.raises(ValueError, match='reconstruction differs'):
        study.independent_history_check(sides, altered)
    with pytest.raises(ValueError, match='counts differ'):
        study.independent_history_check(sides, predictions[:-1])


def test_same_date_outcomes_do_not_enter_same_date_distribution_parameters():
    sides = history()[:2] + [observation('2014-01-01', 'b', 8, 10),
                             observation('2014-01-01', 'c', 1, 10)]
    frozen = original.predict(sides, 500)
    altered = deepcopy(sides)
    altered[-2]['landed'], altered[-1]['landed'] = 0, 10
    changed = original.predict(altered, 500)
    for before, after in zip(frozen, changed, strict=True):
        for family in ('binomial', 'history_beta_binomial', 'bout_beta_binomial'):
            spec = study.distribution_spec('test', 'sample_adjusted', family, 20)
            if before['sample_adjusted'] is not None:
                a, b = (study.distribution_parameters([r], spec) for r in (before, after))
                assert a[3] == pytest.approx(b[3])
                assert a[0].var() == pytest.approx(b[0].var())
    assert frozen[-1]['prior_attempts'] == frozen[-2]['prior_attempts']


def test_dispersion_and_reference_selection_exclude_development_outcomes():
    sides = history()
    specs, tuning = study.select_distributions(original.predict(sides, 500))
    altered = deepcopy(sides)
    altered[-2]['landed'], altered[-1]['landed'] = 0, 20
    new_specs, new_tuning = study.select_distributions(original.predict(altered, 500))
    assert new_tuning == tuning and new_specs == specs
    assert tuning['side_bouts'] == 2
    assert all(x['selected_concentration'] in study.CONFIG['concentrations']
               for x in tuning['bout_concentration_tuning'].values())
    with pytest.raises(ValueError, match='tuning observations'):
        study.select_distributions(original.predict(sides[-2:], 500))


def test_stationary_uncertainty_is_distinct_from_bout_variation():
    row = original.predict(history(), 500)[-1]
    for model, concentration in [('sample_adjusted', row['prior_attempts']+500),
                                 ('career_jeffreys', row['prior_attempts']+1),
                                 ('last5_jeffreys', row['last5_attempts']+1)]:
        spec = study.distribution_spec(model, model, 'history_beta_binomial')
        dist, n, _, p, c = study.distribution_parameters([row], spec)
        assert c[0] == concentration and p[0] == row[model]
        assert dist.mean()[0] == pytest.approx(n[0]*row[model])
    spec = study.distribution_spec('bout', 'sample_adjusted', 'bout_beta_binomial', 20)
    dist, n, _, p, c = study.distribution_parameters([row], spec)
    assert c[0] == 20 and p[0] == row['sample_adjusted']
    assert dist.var()[0] == pytest.approx(n[0]*p[0]*(1-p[0])*(n[0]+20)/21)
    assert dist.var()[0] > binom.var(n[0], p[0])


def test_beta_binomial_matches_direct_enumerated_mass_and_quantiles():
    spec = study.distribution_spec('bout', 'sample_adjusted', 'bout_beta_binomial', 5)
    dist, _, _, _, _ = study.distribution_parameters([{'attempts': 7, 'landed': 4, 'sample_adjusted': .4}], spec)
    a, b, n = 2, 3, 7
    def lbeta(x, y):
        return lgamma(x)+lgamma(y)-lgamma(x+y)
    masses = [comb(n, k)*exp(lbeta(k+a, n-k+b)-lbeta(a, b)) for k in range(n+1)]
    assert sum(masses) == pytest.approx(1)
    assert dist.pmf(np.arange(n+1)) == pytest.approx(masses)
    for q in (.05, .25, .75, .95):
        expected = next(k for k in range(n+1) if sum(masses[:k+1]) >= q)
        assert dist.ppf(q)[0] == expected


@pytest.mark.parametrize('concentration', [-1, 0, float('nan'), float('inf'), True])
def test_invalid_concentration_rejected(concentration):
    with pytest.raises(ValueError, match='positive finite'):
        study.distribution_parameters([{'attempts': 10, 'landed': 4, 'sample_adjusted': .4}],
            study.distribution_spec('bad', 'sample_adjusted', 'bout_beta_binomial', concentration))


def test_point_scores_match_original_and_independent_binomial():
    rows = original.predict(history(), 500)[1:]
    for model in original.MODELS:
        nll, cross, brier = study.point_arrays(rows, model)
        expected = np.array([original.score(r, model) for r in rows]).T
        assert np.allclose([nll, cross, brier], expected, atol=1e-12)
        assert np.allclose(nll, [-binom.logpmf(r['landed'], r['attempts'], r[model]) for r in rows])


def test_pit_randomization_identity_order_seed_and_range():
    rows = [{'fight_id': str(i), 'fighter_id': str(i % 2)} for i in range(100)]
    values = study.pit_uniforms(rows, 20261105)
    assert np.array_equal(values, study.pit_uniforms(rows[::-1], 20261105)[::-1])
    assert np.all((values >= 0) & (values < 1))
    assert not np.array_equal(values, study.pit_uniforms(rows, 20261106))


def test_discrete_range_mass_and_thin_empty_groups():
    row = original.predict(history(), 500)[-1]
    arrays = study.distribution_diagnostics([row], study.distribution_spec(
        'candidate', 'sample_adjusted', 'bout_beta_binomial', 20))
    result = study.calibration([row], arrays, overall=True)
    for nominal in (.5, .9):
        level = result['levels'][str(nominal)]
        assert level['expected_integer_mass'] >= nominal
        assert level['status'] == 'inconclusive_thin_group'
        assert level['randomized_pit_coverage']['interval_95'] is None
        assert len(level['seed_sensitivity']) == 3
    assert sum(result['pit_histogram_10_bins']) == 1
    empty = study.calibration([row], arrays, [])
    assert empty['side_bouts'] == 0 and empty['mean_predictive_nll'] is None


def test_matching_bout_distribution_calibration_and_dispersion():
    rng = np.random.default_rng(415)
    n, p, c, size = 70, .4, 20, 1200
    ys = rng.binomial(n, rng.beta(p*c, (1-p)*c, size))
    rows = [{'event_date': f'2020-01-{i%25+1:02}', 'fight_id': str(i), 'fighter_id': str(i),
             'landed': int(y), 'attempts': n, 'sample_adjusted': p} for i, y in enumerate(ys)]
    arrays = study.distribution_diagnostics(rows, study.distribution_spec(
        'candidate', 'sample_adjusted', 'bout_beta_binomial', c))
    result = study.calibration(rows, arrays, overall=True)
    assert study.within_bands(result)
    assert .8 < result['pearson_dispersion']['mean'] < 1.2
    assert sum(b['side_bouts'] for b in result['probability_bins']) == size
    assert result['observed_accuracy'] == pytest.approx(ys.sum()/(n*size))


def test_all_pit_seeds_must_pass():
    rows = [{'event_date': f'2020-01-{i%25+1:02}', 'fight_id': str(i), 'fighter_id': str(i),
             'landed': 4, 'attempts': 10, 'sample_adjusted': .4} for i in range(600)]
    arrays = study.distribution_diagnostics(rows, study.distribution_spec(
        'candidate', 'sample_adjusted', 'bout_beta_binomial', 20))
    for seed in study.CONFIG['pit_seeds']:
        arrays['pit'][seed] = (np.arange(600)+.5)/600
    arrays['pit'][study.CONFIG['pit_seeds'][1]] = np.full(600, .5)
    result = study.calibration(rows, arrays, overall=True)
    assert result['levels']['0.9']['seed_sensitivity'][0]['in_band']
    assert result['levels']['0.9']['status'] == 'outside_band'


def test_cluster_weighting_matches_explicit_resampling():
    result = study.cluster_interval([1., 2., 4., 9.], ['a', 'a', 'b', 'c'])
    rng = np.random.default_rng(study.CONFIG['seed'])
    choices = rng.integers(0, 3, size=(1000, 3))
    groups = [[1., 2.], [4.], [9.]]
    direct = [sum(sum(groups[i]) for i in chosen)/sum(len(groups[i]) for i in chosen)
              for chosen in choices]
    assert result['mean'] == 4 and result['clusters'] == 3
    assert result['interval_95'] == pytest.approx(np.quantile(direct, [.025, .975]))
    assert study.cluster_interval([], [])['interval_95'] is None
    assert study.cluster_interval([1, 2], ['a', 'a'])['interval_95'] is None
    with pytest.raises(ValueError):
        study.cluster_interval([float('nan')], ['a'])


def test_fixed_subgroup_boundaries():
    row = original.predict(history(), 500)[-1]
    for n, expected in [(1, '1-24'), (25, '25-49'), (50, '50-99'), (100, '100-199'), (200, '200+')]:
        assert study.labels({**row, 'attempts': n})['actual_attempts'] == expected
    for seconds, expected in [(None, 'missing_or_zero'), (0, 'missing_or_zero'), (59, 'under_60s'),
                              (60, '60-299s'), (300, '300-899s'), (900, '900+s')]:
        assert study.labels({**row, 'duration_seconds': seconds})['duration'] == expected


@pytest.mark.parametrize('landed,attempts', [(1.5, 10), (1, True), (False, 10)])
def test_count_type_coercion_cannot_create_valid_measurements(landed, attempts):
    row = {'landed': landed, 'attempts': attempts, 'sample_adjusted': .4}
    with pytest.raises(ValueError, match='integer measurements'):
        study.point_arrays([row], 'sample_adjusted')
    with pytest.raises(ValueError, match='integer measurements'):
        study.distribution_parameters([row], study.distribution_spec('test', 'sample_adjusted', 'binomial'))


def test_material_point_regression_requires_size_effect_and_date_interval():
    row = original.predict(history(), 500)[-1]
    rows = [{**row, 'event_date': f'2020-01-{i%25+1:02}',
             'sample_adjusted': .9, 'landed': 2, 'attempts': 20,
             **{m: .1 for m in original.REFERENCES}} for i in range(120)]
    assert study.point_summary(rows, 'population_mean')['material_point_regression']
    assert not study.point_summary(rows[:10], 'population_mean')['material_point_regression']
    for r in rows:
        r['sample_adjusted'] = .1
    assert not study.point_summary(rows, 'population_mean')['material_point_regression']


def test_tie_aware_rank_and_degenerate_correlations():
    x, y = [1, 1, 2, 3, 4], [5, 5, 4, 3, 2]
    assert correlation(x, y, ranked=True) == pytest.approx(spearmanr(x, y).statistic)
    assert correlation([1, 1, 1], [1, 2, 3]) is None
    assert correlation([1, 2], [2, 1]) is None
    with pytest.raises(ValueError):
        correlation([1, 2, 3], [1, 2, float('nan')])


def test_repeatability_counts_zero_bouts_and_rejects_split_dates_and_missing_counts():
    sides = [observation('2013-01-01', 'a', 20, 100), observation('2013-02-01', 'b', 0, 0),
             observation('2013-02-01', 'c', 20, 100), observation('2013-03-01', 'd', 20, 100)]
    result, pairs = reliability(sides, replicates=20)
    assert result['2']['attrition_mutually_exclusive'] == {'same_date_split_boundary': 1}
    assert not pairs
    sides[2]['event_date'] = '2013-02-02'
    result, pairs = reliability(sides, replicates=20)
    assert result['2']['primary_100_attempts_per_half']['fighters'] == 1
    assert pairs[0]['first_fight_ids'] == ['cito:a', 'cito:b']
    sides[1]['status'], sides[1]['landed'], sides[1]['attempts'] = 'missing_counts', None, None
    result, _ = reliability(sides, replicates=20)
    assert result['2']['attrition_mutually_exclusive'] == {'missing_or_invalid_selected_counts': 1}


def test_repeatability_end_date_and_exposure_attrition():
    sides = [observation(f'2013-01-0{i}', str(i), 5, 10) for i in range(1, 5)]
    sides += [observation('2013-01-04', 'extra', 5, 10)]
    result, _ = reliability(sides, replicates=20)
    assert result['2']['attrition_mutually_exclusive'] == {'same_date_end_boundary': 1}
    result, pairs = reliability(sides[:-1], replicates=20)
    assert result['2']['attrition_mutually_exclusive'] == {'below_100_attempts_in_a_half': 1}
    assert result['2']['primary_100_attempts_per_half']['fighters'] == 0
    assert result['2']['secondary_positive_attempts_per_half']['fighters'] == 1
    assert set(pairs[0]['first_fight_ids']).isdisjoint(pairs[0]['second_fight_ids'])


def test_fighter_bootstrap_repeatability():
    rng = np.random.default_rng(7)
    x = rng.uniform(.2, .8, 80)
    y = x + rng.normal(0, .05, 80)
    pairs = [{'first_rate': float(a), 'second_rate': float(b),
              'first_attempts': 200, 'second_attempts': 200} for a, b in zip(x, y, strict=True)]
    result = summarize_pairs(pairs)
    assert result == summarize_pairs(pairs)
    assert result['status'] == 'descriptive_sized_group'
    assert result['pearson']['correlation'] > .9
    assert result['pearson']['finite_replicates'] == 1000


@pytest.fixture
def synthetic_artifacts(tmp_path):
    database = tmp_path/'source.sqlite'
    database.write_bytes(b'synthetic hash fixture')
    dbhash, sides = digest(database), []
    for day, bid in [('2011-01-01', 'seed'), ('2013-01-01', 'a'), ('2014-01-01', 'b'),
                     ('2020-01-01', 'c'), ('2020-02-01', 'd')]:
        fight, stats = pair(day, bid)
        sides.extend(paired_sides('cito:'+bid, fight, stats, dbhash))
    adapter, prototype = tmp_path/'adapter', tmp_path/'prototype'
    adapter.mkdir()
    prototype.mkdir()
    (adapter/'sides.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in sides))
    metadata = {'adapter_version': sides[0]['adapter_version'], 'before_exclusive': '2026-10-26',
                'input_database': str(database), 'database_sha256': dbhash, 'side_rows': len(sides),
                'fights': len(sides)//2, 'input_sha256': {str(database): dbhash},
                'output_sha256': {'sides.jsonl': digest(adapter/'sides.jsonl')}}
    (adapter/'manifest.json').write_text(json.dumps(metadata))
    predictions = original.predict(sides, 500)
    (prototype/'predictions.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in predictions))
    (prototype/'config.json').write_text(json.dumps(original.CONFIG))
    (prototype/'protocol.md').write_text('Synthetic prototype fixture.')
    common = [r for r in predictions if r['event_date'] >= '2019-01-01' and original.common_support(r)]
    tuning = [r for r in predictions if '2012-01-01' <= r['event_date'] < '2019-01-01' and original.common_support(r)]
    prior = {'config': original.CONFIG, 'selected_prior_attempts': 500, 'before_exclusive': '2026-10-26',
             'input_sha256': {str(database): dbhash},
             'output_sha256': {name: digest(prototype/name) for name in ('predictions.jsonl', 'config.json', 'protocol.md')},
             'development_common_support': original.summarize(common),
             'established_common_support': original.summarize([r for r in common if r['prior_bouts'] >= 3
                                                             and r['prior_attempts'] >= 100]),
             'tuning_2012_2018': [{'side_bouts': len(tuning)}]}
    (prototype/'report.json').write_text(json.dumps(prior))
    protocol = tmp_path/'validation.md'
    protocol.write_text('Synthetic separate validation protocol.')
    return adapter, prototype, protocol


def fast_evaluation(monkeypatch):
    monkeypatch.setitem(study.CONFIG, 'bootstrap_replicates', 10)
    monkeypatch.setattr(study, 'reliability', lambda sides: ({}, []))
    monkeypatch.setattr(study, 'synthetic_checks', lambda: {'numerical_check_passed': True})


def test_end_to_end_reproduction_and_immutable_bound_outputs(synthetic_artifacts, tmp_path, monkeypatch):
    fast_evaluation(monkeypatch)
    output = tmp_path/'validation'
    result = study.run(*synthetic_artifacts, output)
    assert result['reproduced_v1_predictions'] == result['independently_checked_histories'] == 10
    assert result['coverage']['common_support'] == 4
    assert result['public_release'] is False and result['opponent_adjusted'] is False
    assert result['decision']['candidate_bout_overall_calibration_within_bands_all_seeds'] is False
    for name, expected in result['output_sha256'].items():
        assert digest(output/name) == expected
    assert (output/'protocol.md').read_bytes() == synthetic_artifacts[2].read_bytes()
    with pytest.raises(ValueError, match='new, separate'):
        study.run(*synthetic_artifacts, output)


@pytest.mark.parametrize('target', ['predictions.jsonl', 'config.json', 'protocol.md'])
def test_prototype_output_tampering_rejected(synthetic_artifacts, tmp_path, target):
    adapter, prototype, protocol = synthetic_artifacts
    (prototype/target).write_text((prototype/target).read_text()+' ')
    with pytest.raises(ValueError, match='output hash differs'):
        study.run(adapter, prototype, protocol, tmp_path/'out')


def test_updated_hash_cannot_hide_prediction_drift(synthetic_artifacts, tmp_path):
    adapter, prototype, protocol = synthetic_artifacts
    path = prototype/'predictions.jsonl'
    records = [json.loads(line) for line in path.read_text().splitlines()]
    records[-1]['sample_adjusted'] = .9
    path.write_text(''.join(json.dumps(r)+'\n' for r in records))
    report = json.loads((prototype/'report.json').read_text())
    report['output_sha256']['predictions.jsonl'] = digest(path)
    (prototype/'report.json').write_text(json.dumps(report))
    with pytest.raises(ValueError, match='reproduce exactly'):
        study.run(adapter, prototype, protocol, tmp_path/'out')


def test_protocol_change_during_analysis_blocks_publication(synthetic_artifacts, tmp_path, monkeypatch):
    fast_evaluation(monkeypatch)
    adapter, prototype, protocol = synthetic_artifacts
    real_evaluate = study.evaluate
    def changing_evaluation(*args, **kwargs):
        result = real_evaluate(*args, **kwargs)
        protocol.write_text('Changed mid-run.')
        return result
    monkeypatch.setattr(study, 'evaluate', changing_evaluation)
    with pytest.raises(ValueError, match='input changed'):
        study.run(adapter, prototype, protocol, tmp_path/'out')
    assert not (tmp_path/'out').exists()


def test_matching_stationary_and_bout_simulations():
    result = study.synthetic_checks()
    assert result['numerical_check_passed']
    assert result['bout_matching_beta_binomial']['selected_concentration'] == 20
    groups = result['stationary_matching_beta_4_6']['by_prior_attempts']
    for group in groups.values():
        assert .87 <= group['latent_rate_interval_90_coverage'] <= .93
        assert .87 <= group['randomized_pit_90_coverage'] <= .93
    assert groups['500']['mean_rmse'] < groups['25']['mean_rmse'] < groups['0']['mean_rmse']
