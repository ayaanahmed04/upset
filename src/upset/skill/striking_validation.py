"""Separate historical validation of fixed striking means and count variation."""

import argparse
import hashlib
import json
import platform
from collections import Counter, defaultdict
from itertools import groupby
from pathlib import Path

import numpy as np
import scipy
from scipy.stats import beta, betabinom, binom

from upset.skill import striking_accuracy as original
from upset.skill.striking_adapter import (
    digest,
    encoded,
    load_adapter,
    verify_hashes,
    write_artifact,
)
from upset.skill.striking_repeatability import reliability

CONFIG = {'version': 'striking_validation_v1', 'mean_strength': 500,
          'tune_start': '2012-01-01', 'development_start': '2019-01-01',
          'before_exclusive': '2026-10-26', 'clip': 1e-6,
          'concentrations': [2, 5, 10, 20, 50, 100, 200, 500, 1000],
          'bootstrap_replicates': 1000, 'seed': 20261104,
          'pit_seeds': [20261105, 20261106, 20261107],
          'overall_minimum': 500, 'subgroup_minimum': 100, 'minimum_dates': 20,
          'material_nll_regression': .05, 'public_release': False, 'opponent_adjusted': False}
HISTORY_MODELS = ('sample_adjusted', 'career_jeffreys', 'last5_jeffreys')
CANDIDATE = 'bout_beta_binomial:sample_adjusted'


def independent_history_check(sides, predictions):
    """Recompute sufficient counts from prior raw histories, not v1 accumulators."""
    if len(sides) != len(predictions):
        raise ValueError('Prediction/adapter counts differ.')
    by_key = {(r['fight_id'], r['fighter_id']): r for r in predictions}
    if len(by_key) != len(predictions):
        raise ValueError('Duplicate prediction side.')
    history = defaultdict(list)
    global_y = global_n = 0
    for _, group in groupby(sorted(sides, key=lambda r: (
            r['event_date'], r['fight_id'], r['fighter_id'])), key=lambda r: r['event_date']):
        batch = list(group)
        for side in batch:
            prior = history[side['fighter_id']]
            usable = [r for r in prior if r['status'] in ('observed', 'zero_attempts')]
            recent = [r for r in prior[-5:] if r['status'] in ('observed', 'zero_attempts')]
            expected = {'prior_bouts': len(prior), 'prior_landed': sum(r['landed'] for r in usable),
                        'prior_attempts': sum(r['attempts'] for r in usable),
                        'last5_landed': sum(r['landed'] for r in recent),
                        'last5_attempts': sum(r['attempts'] for r in recent),
                        'population_prior_attempts': global_n,
                        'population_mean': global_y / global_n if global_n else None}
            saved = by_key.get((side['fight_id'], side['fighter_id']))
            if saved is None or any(saved[k] != value for k, value in expected.items()):
                raise ValueError('Independent pre-date history reconstruction differs.')
        for side in batch:
            history[side['fighter_id']].append(side)
            if side['status'] in ('observed', 'zero_attempts'):
                global_y += side['landed']
                global_n += side['attempts']
    return len(predictions)


def cluster_interval(values, labels, replicates=None):
    """Paired observation-weighted bootstrap over complete labeled clusters."""
    values = np.asarray(values, dtype=float)
    if values.ndim != 1 or len(values) != len(labels) or not np.isfinite(values).all():
        raise ValueError('Require paired finite values and cluster labels.')
    replicates = CONFIG['bootstrap_replicates'] if replicates is None else replicates
    if type(replicates) is not int or replicates < 1:
        raise ValueError('Require positive bootstrap replicates.')
    grouped = defaultdict(list)
    for value, label in zip(values, labels, strict=True):
        grouped[label].append(value)
    groups = [grouped[key] for key in sorted(grouped)]
    result = {'mean': float(values.mean()) if len(values) else None, 'clusters': len(groups),
              'replicates': replicates, 'seed': CONFIG['seed'], 'interval_95': None}
    if len(groups) < 2:
        return result
    counts = np.array([len(g) for g in groups])
    totals = np.array([sum(g) for g in groups])
    rng = np.random.default_rng(CONFIG['seed'])
    chosen = rng.integers(0, len(groups), size=(replicates, len(groups)))
    means = totals[chosen].sum(axis=1) / counts[chosen].sum(axis=1)
    result['interval_95'] = np.quantile(means, [.025, .975]).tolist()
    return result


def point_arrays(rows, model, clip=CONFIG['clip']):
    if not rows:
        return np.empty((3, 0))
    if any(type(r['landed']) is not int or type(r['attempts']) is not int for r in rows):
        raise ValueError('Count scores require integer measurements.')
    y, n = np.array([r['landed'] for r in rows]), np.array([r['attempts'] for r in rows])
    p = np.array([r[model] for r in rows], dtype=float)
    if (not np.isfinite(p).all() or np.any((p < 0) | (p > 1))
            or np.any((n <= 0) | (y < 0) | (y > n)) or not 0 < clip < .5):
        raise ValueError('Point scores require positive trials and valid means.')
    p = np.clip(p, clip, 1-clip)
    return np.array([-binom.logpmf(y, n, p), -y*np.log(p)-(n-y)*np.log1p(-p),
                     y*(1-p)**2+(n-y)*p**2])


def point_summary(rows, reference, fighter_sensitivity=False):
    dates = [r['event_date'] for r in rows]
    trials = sum(r['attempts'] for r in rows)
    losses, scores = {}, {}
    for model in original.MODELS:
        nll, cross, brier = point_arrays(rows, model)
        losses[model] = nll
        scores[model] = {'mean_binomial_nll': float(nll.mean()) if len(rows) else None,
                         'attempt_weighted_cross_entropy': float(cross.sum()/trials) if trials else None,
                         'attempt_level_brier': float(brier.sum()/trials) if trials else None}
    differences = {m: cluster_interval(losses['sample_adjusted']-losses[m], dates)
                   for m in original.REFERENCES}
    comparison = differences[reference]
    enough = len(rows) >= CONFIG['subgroup_minimum'] and len(set(dates)) >= CONFIG['minimum_dates']
    regression = bool(enough and comparison['interval_95'] is not None
                      and comparison['mean'] > CONFIG['material_nll_regression']
                      and comparison['interval_95'][0] > 0)
    result = {'side_bouts': len(rows), 'attempts': trials, 'date_clusters': len(set(dates)),
              'scores': scores, 'candidate_minus_reference_date_bootstrap': differences,
              'selected_simple_reference': reference, 'material_point_regression': regression,
              'status': 'sized_for_diagnostic' if enough else 'inconclusive_thin_group'}
    if fighter_sensitivity:
        result['fighter_trajectory_bootstrap_sensitivity'] = {
            m: cluster_interval(losses['sample_adjusted']-losses[m], [r['fighter_id'] for r in rows])
            for m in original.REFERENCES}
    return result


def distribution_spec(name, model, family, concentration=None):
    return {'name': name, 'model': model, 'family': family, 'concentration': concentration}


def distribution_parameters(rows, spec):
    model, family = spec['model'], spec['family']
    if any(type(r['landed']) is not int or type(r['attempts']) is not int for r in rows):
        raise ValueError('Predictive counts require integer measurements.')
    n = np.array([r['attempts'] for r in rows], dtype=int)
    y = np.array([r['landed'] for r in rows], dtype=int)
    p = np.array([r[model] for r in rows], dtype=float)
    if not np.isfinite(p).all() or np.any((p < 0) | (p > 1)) or np.any((n <= 0) | (y < 0) | (y > n)):
        raise ValueError('Invalid distribution rows.')
    p = np.clip(p, CONFIG['clip'], 1-CONFIG['clip'])
    if family == 'binomial':
        return binom(n, p), n, y, p, None
    if family == 'history_beta_binomial':
        if model not in HISTORY_MODELS:
            raise ValueError('Unsupported stationary-history distribution.')
        if model == 'sample_adjusted':
            c = np.array([r['prior_attempts'] + CONFIG['mean_strength'] for r in rows])
        else:
            field = 'prior_attempts' if model == 'career_jeffreys' else 'last5_attempts'
            c = np.array([r[field] + 1 for r in rows])
    elif family == 'bout_beta_binomial':
        value = spec['concentration']
        if type(value) not in (int, float) or not np.isfinite(value) or value <= 0:
            raise ValueError('Require a positive finite bout concentration.')
        c = np.full(len(rows), value)
    else:
        raise ValueError('Unknown predictive family.')
    return betabinom(n, p*c, (1-p)*c), n, y, p, c


def select_distributions(predictions):
    tuning = [r for r in predictions if CONFIG['tune_start'] <= r['event_date']
              < CONFIG['development_start'] and original.common_support(r)]
    if not tuning:
        raise ValueError('Missing common-support tuning observations.')
    reference_scores = {m: float(point_arrays(tuning, m)[0].mean()) for m in original.REFERENCES}
    reference = min(original.REFERENCES, key=lambda m: reference_scores[m])
    fitted = {}
    for model in ('sample_adjusted', reference):
        scores = []
        for c in CONFIG['concentrations']:
            spec = distribution_spec('tuning', model, 'bout_beta_binomial', c)
            dist, _, y, _, _ = distribution_parameters(tuning, spec)
            value = float(-dist.logpmf(y).mean())
            if not np.isfinite(value):
                raise ValueError('Nonfinite concentration tuning score.')
            scores.append({'concentration': c, 'mean_predictive_nll': value})
        selected = min(scores, key=lambda r: (r['mean_predictive_nll'], r['concentration']))['concentration']
        fitted[model] = {'grid_scores': scores, 'selected_concentration': selected,
                         'at_grid_boundary': selected in (
                             CONFIG['concentrations'][0], CONFIG['concentrations'][-1])}
    specs = [distribution_spec('binomial:'+m, m, 'binomial') for m in original.MODELS]
    specs += [distribution_spec('history_beta_binomial:'+m, m, 'history_beta_binomial')
              for m in HISTORY_MODELS]
    specs += [distribution_spec('bout_beta_binomial:'+m, m, 'bout_beta_binomial',
                               fitted[m]['selected_concentration']) for m in ('sample_adjusted', reference)]
    return specs, {'period': '2012-2018', 'side_bouts': len(tuning),
                   'reference_binomial_nll': reference_scores, 'selected_simple_reference': reference,
                   'bout_concentration_tuning': fitted}


def pit_uniforms(rows, seed):
    # Use exactly representable 53-bit fractions, always <1; independent of row order/method.
    return np.array([(int.from_bytes(hashlib.sha256(
        f"{seed}:{r['fight_id']}:{r['fighter_id']}".encode()).digest()[:8], 'big') >> 11) / 2**53
                     for r in rows])


def distribution_diagnostics(rows, spec):
    dist, n, y, p, concentration = distribution_parameters(rows, spec)
    log_mass = np.asarray(dist.logpmf(y))
    left, mass = np.clip(dist.cdf(y-1), 0, 1), np.exp(log_mass)
    pits = {seed: np.clip(left + pit_uniforms(rows, seed)*mass, 0, 1) for seed in CONFIG['pit_seeds']}
    variance = np.asarray(dist.var())
    means = n * p
    arrays = {'nll': -log_mass, 'p': p, 'mean': means, 'variance': variance,
              'count_residual': y-means, 'pearson_dispersion': (y-means)**2/variance,
              'pit': pits, 'levels': {}}
    if concentration is not None:
        arrays['concentration'] = concentration
    for level in (.5, .9):
        tail = (1-level)/2
        lo, hi = np.asarray(dist.ppf(tail)), np.asarray(dist.ppf(1-tail))
        expected = np.asarray(dist.cdf(hi)-dist.cdf(lo-1))
        arrays['levels'][str(level)] = {'lo': lo, 'hi': hi, 'expected_mass': expected,
                                       'included': (y >= lo) & (y <= hi)}
    numeric = [arrays[k] for k in ('nll', 'p', 'mean', 'variance', 'pearson_dispersion')]
    numeric += [v[k] for v in arrays['levels'].values() for k in ('lo', 'hi', 'expected_mass')]
    if any(not np.isfinite(v).all() for v in numeric) or np.any(variance <= 0):
        raise ValueError('Nonfinite/degenerate distribution diagnostic.')
    return arrays


def probability_bins(rows, arrays, indices):
    output = []
    for group in range(10):
        chosen = [i for i in indices if min(int(arrays['p'][i]*10), 9) == group]
        attempts = sum(rows[i]['attempts'] for i in chosen)
        observed = sum(rows[i]['landed'] for i in chosen)
        expected = sum(arrays['mean'][i] for i in chosen)
        output.append({'bin': [group/10, (group+1)/10], 'side_bouts': len(chosen),
                       'attempts': attempts, 'observed_accuracy': observed/attempts if attempts else None,
                       'predicted_accuracy': float(expected/attempts) if attempts else None,
                       'observed_minus_predicted': float((observed-expected)/attempts) if attempts else None})
    return output


def calibration(rows, arrays, indices=None, overall=False):
    indices = np.arange(len(rows), dtype=int) if indices is None else np.asarray(indices, dtype=int)
    subset = [rows[i] for i in indices]
    dates = [r['event_date'] for r in subset]
    minimum = CONFIG['overall_minimum'] if overall else CONFIG['subgroup_minimum']
    enough = len(subset) >= minimum and len(set(dates)) >= CONFIG['minimum_dates']
    attempts, landed = sum(r['attempts'] for r in subset), sum(r['landed'] for r in subset)
    levels = {}
    for level in (.5, .9):
        tail = (1-level)/2
        record = arrays['levels'][str(level)]
        bounds = [.45, .55] if level == .5 else [.87, .93]
        sensitivity = []
        for seed, values in arrays['pit'].items():
            pit = values[indices]
            central = (pit >= tail) & (pit <= 1-tail)
            observed = float(central.mean()) if len(pit) else None
            sensitivity.append({'seed': seed, 'coverage': observed,
                                'in_band': bool(observed is not None and bounds[0] <= observed <= bounds[1])})
        first = arrays['pit'][CONFIG['pit_seeds'][0]][indices]
        central = (first >= tail) & (first <= 1-tail)
        status = ('within_band_all_seeds' if all(r['in_band'] for r in sensitivity)
                  else 'outside_band') if enough else 'inconclusive_thin_group'
        levels[str(level)] = {
            'integer_count_coverage': cluster_interval(record['included'][indices], dates),
            'expected_integer_mass': float(record['expected_mass'][indices].mean()) if len(subset) else None,
            'mean_integer_width': float((record['hi']-record['lo'])[indices].mean()) if len(subset) else None,
            'randomized_pit_coverage': cluster_interval(central, dates),
            'diagnostic_band': bounds, 'seed_sensitivity': sensitivity, 'status': status}
    expected = float(arrays['mean'][indices].sum())
    return {'side_bouts': len(subset), 'attempts': attempts, 'date_clusters': len(set(dates)),
            'minimum_sides': minimum, 'minimum_dates': CONFIG['minimum_dates'],
            'mean_predictive_nll': float(arrays['nll'][indices].mean()) if len(subset) else None,
            'mean_count_error_observed_minus_expected': cluster_interval(arrays['count_residual'][indices], dates),
            'observed_accuracy': landed/attempts if attempts else None,
            'predicted_accuracy': expected/attempts if attempts else None,
            'pearson_dispersion': cluster_interval(arrays['pearson_dispersion'][indices], dates),
            'pit_histogram_10_bins': np.histogram(arrays['pit'][CONFIG['pit_seeds'][0]][indices],
                                               bins=np.linspace(0, 1, 11))[0].tolist(),
            'probability_bins': probability_bins(rows, arrays, indices), 'levels': levels}


def predictive_comparison(rows, candidate, reference, indices=None, fighter_sensitivity=False):
    indices = np.arange(len(rows), dtype=int) if indices is None else np.asarray(indices, dtype=int)
    values = candidate['nll'][indices] - reference['nll'][indices]
    result = {'candidate_minus_reference_nll': cluster_interval(values, [rows[i]['event_date'] for i in indices])}
    if fighter_sensitivity:
        result['fighter_trajectory_bootstrap_sensitivity'] = cluster_interval(
            values, [rows[i]['fighter_id'] for i in indices])
    return result


def labels(row):
    n, prior, bouts, seconds = row['attempts'], row['prior_attempts'], row['prior_bouts'], row['duration_seconds']
    return {'year': row['event_date'][:4],
            'era': '2019-2022' if row['event_date'] < '2023-01-01' else '2023+',
            'division': row['division'] or 'Unknown', 'source': row['source'],
            'prior_attempts': '0' if prior == 0 else '1-99' if prior < 100 else '100-499' if prior < 500 else '500+',
            'prior_bouts': '0' if bouts == 0 else '1-2' if bouts < 3 else '3-5' if bouts < 6 else '6+',
            'actual_attempts': '1-24' if n < 25 else '25-49' if n < 50 else '50-99' if n < 100 else '100-199' if n < 200 else '200+',
            'duration': 'missing_or_zero' if seconds is None or seconds == 0 else
            'under_60s' if seconds < 60 else '60-299s' if seconds < 300 else '300-899s' if seconds < 900 else '900+s'}


def synthetic_checks():
    rng = np.random.default_rng(CONFIG['seed'])
    size = 8000
    truth = rng.beta(4, 6, size)
    prior_n = rng.choice([0, 25, 100, 500], size=size)
    prior_y = rng.binomial(prior_n, truth)
    a, b = prior_y+4, prior_n-prior_y+6
    mean = a/(a+b)
    low, high = beta.ppf(.05, a, b), beta.ppf(.95, a, b)
    n = rng.integers(1, 201, size=size)
    y = rng.binomial(n, truth)
    dist = betabinom(n, a, b)
    lo, hi = dist.ppf(.05), dist.ppf(.95)
    pit = dist.cdf(y-1) + rng.uniform(size=size)*dist.pmf(y)
    def summary(mask):
        return {'fighters': int(mask.sum()), 'mean_bias': float((mean[mask]-truth[mask]).mean()),
                'mean_rmse': float(np.sqrt(np.mean((mean[mask]-truth[mask])**2))),
                'latent_rate_interval_90_coverage': float(((truth >= low) & (truth <= high))[mask].mean()),
                'integer_predictive_90_coverage': float(((y >= lo) & (y <= hi))[mask].mean()),
                'expected_integer_mass': float((dist.cdf(hi)-dist.cdf(lo-1))[mask].mean()),
                'randomized_pit_90_coverage': float(((pit >= .05) & (pit <= .95))[mask].mean())}
    stationary = {'overall': summary(np.ones(size, dtype=bool)),
                  'by_prior_attempts': {str(n): summary(prior_n == n) for n in (0, 25, 100, 500)}}
    stationary['numerical_check_passed'] = bool(abs(stationary['overall']['mean_bias']) < .01 and all(
        .87 <= group[key] <= .93 for group in stationary['by_prior_attempts'].values()
        for key in ('latent_rate_interval_90_coverage', 'randomized_pit_90_coverage')))
    rng = np.random.default_rng(20261108)
    p, n = rng.uniform(.2, .8, size), rng.integers(1, 201, size=size)
    latent = rng.beta(20*p, 20*(1-p))
    y = rng.binomial(n, latent)
    scores = [{'concentration': c, 'mean_predictive_nll': float(-betabinom.logpmf(y, n, p*c, (1-p)*c).mean())}
              for c in CONFIG['concentrations']]
    selected = min(scores, key=lambda r: (r['mean_predictive_nll'], r['concentration']))['concentration']
    dist = betabinom(n, 20*p, 20*(1-p))
    pit = dist.cdf(y-1) + rng.uniform(size=size)*dist.pmf(y)
    coverage = float(((pit >= .05) & (pit <= .95)).mean())
    bout = {'seed': 20261108, 'bouts': size, 'true_concentration': 20,
            'selected_concentration': selected, 'grid_scores': scores, 'randomized_pit_90_coverage': coverage,
            'numerical_check_passed': bool(selected == 20 and .87 <= coverage <= .93)}
    return {'stationary_matching_beta_4_6': stationary, 'bout_matching_beta_binomial': bout,
            'numerical_check_passed': stationary['numerical_check_passed'] and bout['numerical_check_passed'],
            'interpretation': 'Matching-model software checks only; not MMA model validation.'}


def within_bands(summary):
    return all(summary['levels'][str(level)]['status'] == 'within_band_all_seeds' for level in (.5, .9))


def evaluate(sides, predictions=None, progress=print):
    predictions = original.predict(sides, CONFIG['mean_strength']) if predictions is None else predictions
    independent_history_check(sides, predictions)
    specs, tuning = select_distributions(predictions)
    reference = tuning['selected_simple_reference']
    reference_name = 'bout_beta_binomial:' + reference
    progress('Selected the simple reference and both dispersions on 2012-2018 only.')
    development = [r for r in predictions if r['event_date'] >= CONFIG['development_start']]
    common = [r for r in development if original.common_support(r)]
    if not common:
        raise ValueError('No common-support development observations.')
    established_indices = [i for i, r in enumerate(common) if r['prior_bouts'] >= 3 and r['prior_attempts'] >= 100]
    nonboundary = [r for r in common if 0 < r['raw_career'] < 1 and 0 < r['raw_last5'] < 1]
    primary_point = point_summary(common, reference, fighter_sensitivity=True)
    diagnostics, calibrated = {}, {}
    for spec in specs:
        name = spec['name']
        progress('Checking predictive counts: ' + name)
        diagnostics[name] = distribution_diagnostics(common, spec)
        calibrated[name] = {'specification': spec, **calibration(common, diagnostics[name], overall=True)}
    candidate = diagnostics[CANDIDATE]
    primary_comparisons = {
        name: predictive_comparison(common, candidate, value, fighter_sensitivity=True)
        for name, value in diagnostics.items() if name != CANDIDATE}
    groups = defaultdict(lambda: defaultdict(list))
    for i, row in enumerate(common):
        for field, label in labels(row).items():
            groups[field][label].append(i)
    subgroups = {}
    for field, slices in sorted(groups.items()):
        subgroups[field] = {}
        for label, indices in sorted(slices.items()):
            subset = [common[i] for i in indices]
            subgroups[field][label] = {
                'point_scores': point_summary(subset, reference),
                'candidate_bout_calibration': calibration(common, candidate, indices),
                'candidate_vs_reference_bout_distribution': predictive_comparison(
                    common, candidate, diagnostics[reference_name], indices)}
        progress('Completed subgroup diagnostics: ' + field)
    positive = [r for r in development if r['status'] == 'observed' and r['sample_adjusted'] is not None]
    candidate_spec = next(s for s in specs if s['name'] == CANDIDATE)
    progress('Checking broader coverage and cold starts separately from paired support.')
    broader_arrays = distribution_diagnostics(positive, candidate_spec)
    cold_indices = [i for i, r in enumerate(positive) if r['prior_attempts'] == 0]
    broader = calibration(positive, broader_arrays, overall=True)
    cold = calibration(positive, broader_arrays, cold_indices)
    progress('Checking complete-count, disjoint split-half repeatability.')
    repeatability, pairs = reliability(sides)
    progress('Checking stationary and bout-varying synthetic recovery.')
    synthetic = synthetic_checks()
    material = [field + ':' + label for field, slices in subgroups.items()
                for label, record in slices.items() if record['point_scores']['material_point_regression']]
    calibration_failures, thin = [], []
    for field, slices in subgroups.items():
        for label, record in slices.items():
            levels = record['candidate_bout_calibration']['levels'].values()
            if any(level['status'] == 'outside_band' for level in levels):
                calibration_failures.append(field + ':' + label)
            if any(level['status'] == 'inconclusive_thin_group' for level in levels):
                thin.append(field + ':' + label)
    def upper_below_zero(record):
        interval = record['interval_95']
        return bool(interval is not None and interval[1] < 0)
    point_evidence = upper_below_zero(primary_point['candidate_minus_reference_date_bootstrap'][reference])
    point_sensitivity = upper_below_zero(primary_point['fighter_trajectory_bootstrap_sensitivity'][reference])
    dispersion_evidence = upper_below_zero(primary_comparisons['binomial:sample_adjusted']['candidate_minus_reference_nll'])
    predictive_reference_evidence = upper_below_zero(primary_comparisons[reference_name]['candidate_minus_reference_nll'])
    overall_ok = within_bands(calibrated[CANDIDATE])
    reason = ('Retain the fixed point estimate as an offline research reference; '
              'keep the website raw. Predictive calibration or subgroup checks require a separate revision study.'
              if not overall_ok or material or calibration_failures else
              'Retain the candidate as an offline research reference. These development diagnostics '
              'do not complete protected future evaluation, skill reliability or public-release requirements.')
    report = {
        'study_version': CONFIG['version'], 'config': CONFIG,
        'public_release': False, 'opponent_adjusted': False,
        'evaluation_label': 'Previously inspected historical development data, not an untouched holdout.',
        'estimand': 'Significant strikes landed conditional on actual current own attempts.',
        'frozen_mean_strength': CONFIG['mean_strength'], 'v1_strength_at_grid_boundary': True,
        'tuning_2012_2018': tuning, 'primary_point_scores': primary_point,
        'established_point_scores': point_summary([common[i] for i in established_indices], reference),
        'raw_nonboundary_point_scores': point_summary(nonboundary, reference),
        'clip_sensitivity_same_support': {str(eps): {m: float(point_arrays(common, m, eps)[0].mean())
                                                   for m in original.MODELS} for eps in (1e-6, 1e-3, 1e-2)},
        'primary_predictive_distributions': calibrated,
        'primary_candidate_predictive_comparisons': primary_comparisons,
        'established_candidate_bout_calibration': calibration(common, candidate, established_indices, overall=True),
        'subgroups': subgroups, 'broader_candidate_bout_calibration': broader,
        'cold_start_candidate_bout_calibration': cold,
        'repeatability': repeatability, 'synthetic_checks': synthetic,
        'coverage': {'all_adapter_sides': len(sides), 'development_sides': len(development),
                     'statuses': dict(Counter(r['status'] for r in development)),
                     'positive_trial_sides': sum(r['status'] == 'observed' for r in development),
                     'common_support': len(common), 'broader_candidate_sides': len(positive),
                     'cold_start_candidate_sides': len(cold_indices),
                     'established_common_support': len(established_indices),
                     'raw_nonboundary_common_support': len(nonboundary),
                     'same_day_last5_boundary_windows': sum(r['last5_splits_same_day_boundary'] for r in development)},
        'decision': {'point_score_evidence_vs_selected_reference_date_bootstrap': point_evidence,
                     'point_score_evidence_fighter_bootstrap_sensitivity': point_sensitivity,
                     'bout_dispersion_improves_candidate_predictive_nll': dispersion_evidence,
                     'candidate_beats_reference_with_separately_tuned_bout_dispersion': predictive_reference_evidence,
                     'candidate_bout_overall_calibration_within_bands_all_seeds': overall_ok,
                     'history_posterior_overall_calibration_within_bands_all_seeds': within_bands(
                         calibrated['history_beta_binomial:sample_adjusted']),
                     'material_point_regression_groups': material,
                     'candidate_bout_calibration_failure_groups': calibration_failures,
                     'inconclusive_calibration_groups': thin,
                     'synthetic_numerical_checks_passed': synthetic['numerical_check_passed'],
                     'repeatability_threshold': 'Not established; descriptive correlations and attrition only.',
                     'public_release': False, 'reason': reason},
        'limitations': ['Already examined development years; no fresh future validation',
                        'Mean/prior/concentration tuning uncertainty is not propagated',
                        'One-way date and fighter bootstraps do not jointly resolve both dependence structures',
                        'Conditional actual attempts; no future opportunity/duration/winner forecast',
                        'No opponent adjustment, real latent skill truth or validated skill intervals',
                        'Overlapping subgroup diagnostics have no multiplicity correction',
                        'Split-half correlations reflect career survival, schedule and time changes'],
    }
    return report, common, diagnostics, pairs


def calibration_rows(rows, diagnostics):
    result = []
    for i, row in enumerate(rows):
        methods = {}
        for name, arrays in diagnostics.items():
            methods[name] = {'probability': float(arrays['p'][i]), 'count_mean': float(arrays['mean'][i]),
                             'count_variance': float(arrays['variance'][i]), 'nll': float(arrays['nll'][i]),
                             'pit': {str(seed): float(values[i]) for seed, values in arrays['pit'].items()},
                             'ranges': {level: {'lower': int(v['lo'][i]), 'upper': int(v['hi'][i]),
                                               'expected_mass': float(v['expected_mass'][i])}
                                        for level, v in arrays['levels'].items()}}
            if 'concentration' in arrays:
                methods[name]['concentration'] = float(arrays['concentration'][i])
        result.append({**{k: row[k] for k in ('fight_id', 'fighter_id', 'opponent_id', 'event_date',
                                            'landed', 'attempts')}, 'methods': methods})
    return result


def run(adapter, prototype, protocol, output):
    if output.exists() or any(output.resolve().is_relative_to(p.resolve()) for p in (adapter, prototype)):
        raise ValueError('Use a new, separate immutable output directory.')
    sides, metadata, hashes = load_adapter(adapter)
    report_path = prototype / 'report.json'
    prior_body = report_path.read_bytes()
    prior = json.loads(prior_body)
    verify_hashes(prior['input_sha256'])
    original_bodies = {}
    for name, expected in prior['output_sha256'].items():
        path = prototype / name
        if not path.resolve().is_relative_to(prototype.resolve()):
            raise ValueError('Original prototype output path escapes artifact.')
        body = path.read_bytes()
        if hashlib.sha256(body).hexdigest() != expected:
            raise ValueError('Original prototype output hash differs.')
        original_bodies[name] = body
    if (prior['config'] != original.CONFIG or json.loads(original_bodies['config.json']) != original.CONFIG
            or prior['selected_prior_attempts'] != CONFIG['mean_strength']
            or prior['before_exclusive'] != metadata['before_exclusive']
            or metadata['before_exclusive'] != CONFIG['before_exclusive']):
        raise ValueError('Frozen prototype configuration or cutoff differs.')
    predictions = [json.loads(line) for line in original_bodies['predictions.jsonl'].splitlines()]
    reproduced = original.predict(sides, CONFIG['mean_strength'])
    if reproduced != predictions:
        raise ValueError('Every original prediction must reproduce exactly.')
    independent_history_check(sides, predictions)
    print(f'Reproduced all {len(predictions)} v1 predictions; independent histories agree.', flush=True)
    paths = [protocol, Path(__file__), Path(__file__).with_name('striking_repeatability.py')]
    hashes.update(prior['input_sha256'])
    hashes[str(report_path.resolve())] = hashlib.sha256(prior_body).hexdigest()
    hashes.update({str((prototype / name).resolve()): value for name, value in prior['output_sha256'].items()})
    hashes.update({str(p.resolve()): digest(p) for p in paths})
    report, common, diagnostics, pairs = evaluate(sides, predictions, lambda msg: print(msg, flush=True))
    if (len(common) != prior['development_common_support']['side_bouts']
            or report['tuning_2012_2018']['side_bouts'] != prior['tuning_2012_2018'][0]['side_bouts']
            or report['coverage']['established_common_support'] != prior['established_common_support']['side_bouts']):
        raise ValueError('Validation must retain the original support populations.')
    for model in original.MODELS:
        if not np.isclose(report['primary_point_scores']['scores'][model]['mean_binomial_nll'],
                          prior['development_common_support']['scores'][model]['mean_binomial_nll'],
                          rtol=0, atol=1e-10):
            raise ValueError('Independent point scores differ from v1.')
    report.update(input_sha256=hashes, before_exclusive=metadata['before_exclusive'],
                  reproduced_v1_predictions=len(predictions), independently_checked_histories=len(sides),
                  runtime_versions={'python': platform.python_version(),
                                    'numpy': np.__version__, 'scipy': scipy.__version__})
    def jsonl(rows):
        return ''.join(json.dumps(r, sort_keys=True, allow_nan=False)+'\n' for r in rows)
    files = {'config.json': encoded(CONFIG), 'protocol.md': protocol.read_text(),
             'calibration_rows.jsonl': jsonl(calibration_rows(common, diagnostics)),
             'repeatability_pairs.jsonl': jsonl(pairs), 'predictions.jsonl': jsonl(predictions)}
    report['output_sha256'] = {name: hashlib.sha256(body.encode()).hexdigest() for name, body in files.items()}
    verify_hashes(hashes)
    write_artifact(output, {**files, 'report.json': encoded(report)})
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--adapter', type=Path, required=True)
    parser.add_argument('--prototype', type=Path, required=True)
    parser.add_argument('--protocol', type=Path, default=Path('docs/STRIKING_VALIDATION_PROTOCOL_V1.md'))
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = run(args.adapter, args.prototype, args.protocol, args.output)
    print(encoded({k: report[k] for k in ('coverage', 'tuning_2012_2018', 'decision')}))


if __name__ == '__main__':
    main()
