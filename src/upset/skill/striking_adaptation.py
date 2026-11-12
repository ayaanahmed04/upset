"""New, train-only striking drift and volume repairs; not a public skill release."""

import argparse
import hashlib
import json
import platform
from collections import defaultdict
from datetime import date
from itertools import groupby
from pathlib import Path

import numpy as np
import scipy
from scipy.optimize import minimize_scalar
from scipy.special import expit, logit
from scipy.stats import betabinom

from upset.skill import striking_accuracy as original
from upset.skill import striking_validation as validation
from upset.skill.striking_adapter import (
    digest,
    encoded,
    load_adapter,
    verify_hashes,
    write_artifact,
)

CONFIG = {'version': 'striking_adaptation_v1', 'half_lives_days': [365, 730, 1460, 2920],
          'strengths': [100, 500, 1000], 'intercept_bounds': [-.5, .5],
          'c100_grid': [5, 10, 20, 50, 100], 'gamma_grid': [0, .5, 1, 1.5, 2],
          'before_exclusive': '2026-10-26', 'clip': 1e-6,
          'preview_bias_max_percentage_points': 1., 'public_release': False, 'opponent_adjusted': False}
CANDIDATE = 'recent_calibrated_volume'


def decay_factor(elapsed_days, half_life):
    if (type(elapsed_days) not in (int, float) or not np.isfinite(elapsed_days) or elapsed_days < 0
            or type(half_life) not in (int, float) or not np.isfinite(half_life) or half_life <= 0):
        raise ValueError('Require nonnegative elapsed days and positive finite half-life.')
    return float(2**(-elapsed_days/half_life))


def calibrated_mean(p, intercept):
    if not np.isfinite(intercept) or not -.5 <= intercept <= .5:
        raise ValueError('Intercept must lie in the declared bounds.')
    if p is None:
        return None
    p = np.asarray(p, dtype=float)
    if not np.isfinite(p).all() or np.any((p < 0) | (p > 1)):
        raise ValueError('Invalid mean probability.')
    value = expit(logit(np.clip(p, CONFIG['clip'], 1-CONFIG['clip'])) + intercept)
    return float(value) if value.ndim == 0 else value


def recent_predictions(sides, half_life, strength, base=None):
    decay_factor(0, half_life)
    if type(strength) not in (int, float) or not np.isfinite(strength) or strength <= 0:
        raise ValueError('Require positive finite prior exposure.')
    base = original.predict(sides, 500) if base is None else base
    mapping = {(r['fight_id'], r['fighter_id']): r for r in base}
    if len(mapping) != len(sides):
        raise ValueError('Duplicate or unmatched history side.')
    state, global_counts, global_day = {}, np.zeros(2), None
    result = []
    for day, group in groupby(sorted(sides, key=lambda r: (
            r['event_date'], r['fight_id'], r['fighter_id'])), key=lambda r: r['event_date']):
        batch, today = list(group), date.fromisoformat(day)
        if global_day is not None:
            global_counts *= decay_factor((today-global_day).days, half_life)
        global_day = today
        population = global_counts[0]/global_counts[1] if global_counts[1] else None
        prior = {}
        for side in batch:
            uid = side['fighter_id']
            y, n, previous = state.get(uid, (0., 0., today))
            weight = decay_factor((today-previous).days, half_life)
            y, n = y*weight, n*weight
            prior[uid] = (y, n)
            p = (y+strength*population)/(n+strength) if population is not None else None
            result.append({**mapping[side['fight_id'], uid], 'recent_uncalibrated': p,
                           'weighted_prior_landed': y, 'weighted_prior_attempts': n,
                           'recent_population_mean': float(population) if population is not None else None,
                           'weighted_population_attempts': float(global_counts[1])})
        # Each fighter's pre-date history is decayed once, then all same-day bouts update it.
        updates = defaultdict(lambda: np.zeros(2))
        for side in batch:
            if side['status'] in ('observed', 'zero_attempts'):
                updates[side['fighter_id']] += [side['landed'], side['attempts']]
                global_counts += [side['landed'], side['attempts']]
        for uid, (y, n) in prior.items():
            values = updates[uid]
            state[uid] = (y+values[0], n+values[1], today)
    return result


def fit_recent_mean(sides, base):
    grid = []
    for half_life in CONFIG['half_lives_days']:
        for strength in CONFIG['strengths']:
            rows = recent_predictions(sides, half_life, strength, base)
            support = [r for r in rows if '2012-01-01' <= r['event_date'] < '2016-01-01'
                       and original.common_support(r)]
            if not support:
                raise ValueError('Missing 2012-2015 mean-tuning observations.')
            loss = float(validation.point_arrays(support, 'recent_uncalibrated')[0].mean())
            grid.append({'half_life_days': half_life, 'strength': strength,
                         'side_bouts': len(support), 'mean_binomial_nll': loss})
    chosen = min(grid, key=lambda r: r['mean_binomial_nll'])
    rows = recent_predictions(sides, chosen['half_life_days'], chosen['strength'], base)
    calibration = [r for r in rows if '2016-01-01' <= r['event_date'] < '2019-01-01'
                   and original.common_support(r)]
    if not calibration:
        raise ValueError('Missing 2016-2018 intercept-fitting observations.')
    def objective(intercept):
        extended = [{**r, 'recent_calibrated': calibrated_mean(r['recent_uncalibrated'], intercept)}
                    for r in calibration]
        return float(validation.point_arrays(extended, 'recent_calibrated')[0].mean())
    fit = minimize_scalar(objective, bounds=tuple(CONFIG['intercept_bounds']), method='bounded',
                          options={'xatol': 1e-10})
    if not fit.success or not np.isfinite(fit.fun):
        raise ValueError('Intercept optimization failed.')
    # Include endpoints explicitly; bounded optimization itself returns an interior point.
    options = [(float(fit.x), float(fit.fun))] + [(d, objective(d)) for d in CONFIG['intercept_bounds']]
    intercept, loss = min(options, key=lambda value: value[1])
    for row in rows:
        row['recent_calibrated'] = calibrated_mean(row['recent_uncalibrated'], intercept)
    return rows, {'mean_tuning_period': '2012-2015', 'grid_scores': grid,
                  'selected_half_life_days': chosen['half_life_days'], 'selected_strength': chosen['strength'],
                  'mean_grid_boundary': chosen['half_life_days'] in (
                      CONFIG['half_lives_days'][0], CONFIG['half_lives_days'][-1]) or chosen['strength'] in (
                      CONFIG['strengths'][0], CONFIG['strengths'][-1]),
                  'intercept_fit_period': '2016-2018', 'intercept_fit_sides': len(calibration),
                  'selected_intercept': intercept, 'calibration_binomial_nll': loss,
                  'intercept_at_bound': intercept in CONFIG['intercept_bounds']}


def concentration(attempts, c100, gamma):
    n = np.asarray(attempts)
    if (not np.issubdtype(n.dtype, np.integer) or np.any(n < 0) or not np.isfinite(c100)
            or c100 <= 0 or not np.isfinite(gamma) or not 0 <= gamma <= 2):
        raise ValueError('Invalid attempts or exposure-variation parameters.')
    value = c100*(np.maximum(n, 1)/100.)**gamma
    if not np.isfinite(value).all() or np.any(value <= 0):
        raise ValueError('Invalid derived concentration.')
    return value


def parameters(rows, field, c100, gamma):
    if any(type(r['attempts']) is not int or type(r['landed']) is not int for r in rows):
        raise ValueError('Counts require integer measurements.')
    n, y = np.array([r['attempts'] for r in rows]), np.array([r['landed'] for r in rows])
    p = np.array([r[field] for r in rows], dtype=float)
    if (np.any((n <= 0) | (y < 0) | (y > n)) or not np.isfinite(p).all()
            or np.any((p < 0) | (p > 1))):
        raise ValueError('Invalid conditional count observations.')
    p = np.clip(p, CONFIG['clip'], 1-CONFIG['clip'])
    c = concentration(n, c100, gamma)
    return betabinom(n, p*c, (1-p)*c), n, y, p, c


def fit_dispersion(rows, field, constant=False):
    training = [r for r in rows if '2012-01-01' <= r['event_date'] < '2019-01-01'
                and original.common_support(r)]
    if not training:
        raise ValueError('Missing distribution-fitting history.')
    grid = []
    for c100 in CONFIG['c100_grid']:
        for gamma in ([0] if constant else CONFIG['gamma_grid']):
            dist, _, y, _, _ = parameters(training, field, c100, gamma)
            grid.append({'c100': c100, 'gamma': gamma,
                         'mean_predictive_nll': float(-dist.logpmf(y).mean())})
    chosen = min(grid, key=lambda r: r['mean_predictive_nll'])
    return {**chosen, 'field': field, 'training_sides': len(training), 'period': '2012-2018',
            'grid_scores': grid, 'at_grid_boundary': chosen['c100'] in (
                CONFIG['c100_grid'][0], CONFIG['c100_grid'][-1]) or not constant and chosen['gamma'] in (
                CONFIG['gamma_grid'][0], CONFIG['gamma_grid'][-1])}


def diagnostics(rows, spec):
    dist, n, y, p, c = parameters(rows, spec['field'], spec['c100'], spec['gamma'])
    left, mass = np.clip(dist.cdf(y-1), 0, 1), dist.pmf(y)
    mean, variance = n*p, np.asarray(dist.var())
    arrays = {'nll': -dist.logpmf(y), 'p': p, 'mean': mean, 'variance': variance,
              'count_residual': y-mean, 'pearson_dispersion': (y-mean)**2/variance,
              'concentration': c,
              'pit': {seed: np.clip(left+validation.pit_uniforms(rows, seed)*mass, 0, 1)
                      for seed in validation.CONFIG['pit_seeds']}, 'levels': {}}
    for level in (.5, .9):
        tail = (1-level)/2
        lo, hi = np.asarray(dist.ppf(tail)), np.asarray(dist.ppf(1-tail))
        arrays['levels'][str(level)] = {'lo': lo, 'hi': hi, 'included': (y >= lo) & (y <= hi),
                                       'expected_mass': np.asarray(dist.cdf(hi)-dist.cdf(lo-1))}
    if any(not np.isfinite(arrays[key]).all() for key in ('nll', 'mean', 'variance', 'pearson_dispersion')):
        raise ValueError('Nonfinite predictive diagnostics.')
    return arrays


def point_comparison(rows, field, reference):
    loss = validation.point_arrays(rows, field)[0]
    reference_loss = validation.point_arrays(rows, reference)[0]
    dates = [r['event_date'] for r in rows]
    result = validation.cluster_interval(loss-reference_loss, dates)
    enough = len(rows) >= 100 and len(set(dates)) >= 20
    return {'candidate_minus_reference_nll': result,
            'material_regression': bool(enough and result['interval_95'] is not None
                                        and result['mean'] > .05 and result['interval_95'][0] > 0),
            'status': 'sized_for_diagnostic' if enough else 'inconclusive_thin_group'}


def synthetic_recovery():
    rng = np.random.default_rng(20261109)
    n = rng.integers(5, 301, 8000)
    p = rng.uniform(.2, .8, 8000)
    c = concentration(n, 20, 1)
    y = rng.binomial(n, rng.beta(p*c, (1-p)*c))
    scores = []
    for c100 in CONFIG['c100_grid']:
        for gamma in CONFIG['gamma_grid']:
            value = concentration(n, c100, gamma)
            scores.append({'c100': c100, 'gamma': gamma,
                           'nll': float(-betabinom.logpmf(y, n, p*value, (1-p)*value).mean())})
    chosen = min(scores, key=lambda value: value['nll'])
    return {'seed': 20261109, 'bouts': 8000, 'true_c100': 20, 'true_gamma': 1,
            'selected': chosen, 'numerical_check_passed': chosen['c100'] == 20 and chosen['gamma'] == 1}


def evaluate(sides, base, progress=print):
    rows, mean_fit = fit_recent_mean(sides, base)
    progress('Recent-history mean selected on 2012-2015; intercept fitted on 2016-2018.')
    specs = {'frozen_constant': {'field': 'sample_adjusted', 'c100': 20, 'gamma': 0},
             'simple_constant': {'field': 'population_mean', 'c100': 20, 'gamma': 0},
             'frozen_volume': fit_dispersion(rows, 'sample_adjusted'),
             'recent_calibrated_constant': fit_dispersion(rows, 'recent_calibrated', constant=True),
             CANDIDATE: fit_dispersion(rows, 'recent_calibrated'),
             'recent_uncalibrated_volume': fit_dispersion(rows, 'recent_uncalibrated')}
    progress('All dispersion parameters selected on 2012-2018 only.')
    development = [r for r in rows if r['event_date'] >= '2019-01-01']
    common = [r for r in development if original.common_support(r)]
    if not common:
        raise ValueError('Missing matched development support.')
    arrays, summaries = {}, {}
    for name, spec in specs.items():
        progress('Checking repaired count distribution: '+name)
        arrays[name] = diagnostics(common, spec)
        summaries[name] = {'specification': spec, **validation.calibration(common, arrays[name], overall=True)}
    mean_losses = {}
    for field in ('sample_adjusted', 'population_mean', 'recent_uncalibrated', 'recent_calibrated'):
        nll, cross, brier = validation.point_arrays(common, field)
        attempts = sum(r['attempts'] for r in common)
        mean_losses[field] = {'binomial_nll': float(nll.mean()), 'cross_entropy': float(cross.sum()/attempts),
                              'attempt_brier': float(brier.sum()/attempts)}
    groups = defaultdict(lambda: defaultdict(list))
    for i, row in enumerate(common):
        for field, label in validation.labels(row).items():
            groups[field][label].append(i)
    subgroup_report, point_flags, calibration_flags, thin = {}, [], [], []
    for field, slices in sorted(groups.items()):
        subgroup_report[field] = {}
        for label, indices in sorted(slices.items()):
            subset = [common[i] for i in indices]
            comparisons = {ref: point_comparison(subset, 'recent_calibrated', ref)
                           for ref in ('sample_adjusted', 'population_mean')}
            cal = validation.calibration(common, arrays[CANDIDATE], indices)
            subgroup_report[field][label] = {'side_bouts': len(subset), 'point_comparisons': comparisons,
                                             'candidate_calibration': cal}
            if any(v['material_regression'] for v in comparisons.values()):
                point_flags.append(field+':'+label)
            if any(v['status'] == 'outside_band' for v in cal['levels'].values()):
                calibration_flags.append(field+':'+label)
            if any(v['status'] == 'inconclusive_thin_group' for v in cal['levels'].values()):
                thin.append(field+':'+label)
        progress('Completed repaired subgroup checks: '+field)
    established = [i for i, row in enumerate(common) if row['prior_bouts'] >= 3 and row['prior_attempts'] >= 100]
    positive = [r for r in development if r['status'] == 'observed' and r['recent_calibrated'] is not None]
    positive_arrays = diagnostics(positive, specs[CANDIDATE])
    cold = [i for i, row in enumerate(positive) if row['prior_attempts'] == 0]
    comparisons = {name: validation.predictive_comparison(common, arrays[CANDIDATE], values,
                                                         fighter_sensitivity=True)
                   for name, values in arrays.items() if name != CANDIDATE}
    point = {ref: point_comparison(common, 'recent_calibrated', ref)
             for ref in ('sample_adjusted', 'population_mean')}
    delta = point['sample_adjusted']['candidate_minus_reference_nll']
    bias = 100*(summaries[CANDIDATE]['predicted_accuracy']-summaries[CANDIDATE]['observed_accuracy'])
    preview = (delta['interval_95'] is not None and delta['interval_95'][1] < 0
               and abs(bias) <= CONFIG['preview_bias_max_percentage_points'] and not point_flags)
    distribution_pass = validation.within_bands(summaries[CANDIDATE]) and not calibration_flags and not point_flags
    report = {'study_version': CONFIG['version'], 'config': CONFIG, 'mean_fit': mean_fit,
              'distribution_fits': specs, 'point_scores': mean_losses, 'primary_point_comparisons': point,
              'primary_distributions': summaries, 'primary_predictive_comparisons': comparisons,
              'subgroups': subgroup_report,
              'established_candidate_calibration': validation.calibration(common, arrays[CANDIDATE], established, overall=True),
              'broader_candidate_calibration': validation.calibration(positive, positive_arrays, overall=True),
              'cold_start_calibration': validation.calibration(positive, positive_arrays, cold),
              'synthetic_checks': synthetic_recovery(),
              'coverage': {'adapter_sides': len(sides), 'matched_development_sides': len(common),
                           'established_sides': len(established), 'broader_positive_sides': len(positive),
                           'cold_start_sides': len(cold)},
              'decision': {'eligible_for_experimental_mean_preview': bool(preview),
                           'mean_bias_percentage_points_predicted_minus_observed': bias,
                           'material_point_regression_groups': point_flags,
                           'distribution_calibration_failure_groups': calibration_flags,
                           'inconclusive_groups': thin, 'distribution_diagnostics_passed': bool(distribution_pass),
                           'public_release': False, 'opponent_adjusted': False,
                           'reason': 'Experimental mean preview requires its separate point checks; '
                           'historical diagnostics do not validate an opponent-adjusted skill rating.'},
              'evaluation_label': 'Repeatedly inspected development years; not protected future validation.',
              'public_release': False, 'opponent_adjusted': False}
    return report, rows, common, arrays


def run(adapter, prototype, previous_validation, protocol, output):
    if output.exists() or any(output.resolve().is_relative_to(p.resolve()) for p in (adapter, prototype, previous_validation)):
        raise ValueError('Use a new immutable output separate from all inputs.')
    sides, metadata, hashes = load_adapter(adapter)
    previous = json.loads((previous_validation/'report.json').read_text())
    verify_hashes(previous['input_sha256'])
    for name, expected in previous['output_sha256'].items():
        if digest(previous_validation/name) != expected:
            raise ValueError('Previous validation artifact hash differs.')
    base = original.predict(sides, 500)
    saved = [json.loads(line) for line in (prototype/'predictions.jsonl').read_text().splitlines()]
    if base != saved or metadata['before_exclusive'] != CONFIG['before_exclusive']:
        raise ValueError('Original predictions/cutoff did not reproduce.')
    validation.independent_history_check(sides, base)
    hashes.update(previous['input_sha256'])
    paths = [previous_validation/'report.json', protocol, Path(__file__)]
    paths += [previous_validation/name for name in previous['output_sha256']]
    hashes.update({str(p.resolve()): digest(p) for p in paths})
    report, rows, common, arrays = evaluate(sides, base, lambda msg: print(msg, flush=True))
    if len(common) != previous['coverage']['common_support']:
        raise ValueError('Primary support differs from original validation.')
    for name, oldname in [('frozen_constant', 'bout_beta_binomial:sample_adjusted'),
                          ('simple_constant', 'bout_beta_binomial:population_mean')]:
        if not np.isclose(report['primary_distributions'][name]['mean_predictive_nll'],
                          previous['primary_predictive_distributions'][oldname]['mean_predictive_nll'], atol=1e-10, rtol=0):
            raise ValueError('Frozen predictive reference did not reproduce.')
    report.update(input_sha256=hashes, before_exclusive=metadata['before_exclusive'], reproduced_original_sides=len(base),
                  versions={'python': platform.python_version(), 'numpy': np.__version__, 'scipy': scipy.__version__})
    def jsonl(records):
        return ''.join(json.dumps(r, sort_keys=True, allow_nan=False)+'\n' for r in records)
    files = {'predictions.jsonl': jsonl(rows),
             'calibration_rows.jsonl': jsonl(validation.calibration_rows(common, arrays)),
             'protocol.md': protocol.read_text(), 'config.json': encoded(CONFIG)}
    report['output_sha256'] = {name: hashlib.sha256(body.encode()).hexdigest() for name, body in files.items()}
    verify_hashes(hashes)
    write_artifact(output, {**files, 'report.json': encoded(report)})
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--adapter', type=Path, required=True)
    parser.add_argument('--prototype', type=Path, required=True)
    parser.add_argument('--validation', type=Path, required=True)
    parser.add_argument('--protocol', type=Path, default=Path('docs/STRIKING_ADAPTATION_PROTOCOL_V1.md'))
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = run(args.adapter, args.prototype, args.validation, args.protocol, args.output)
    print(encoded({key: report[key] for key in ('mean_fit', 'point_scores', 'coverage', 'decision')}))


if __name__ == '__main__':
    main()
