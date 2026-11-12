"""Dated rolling-intercept study after the retained fixed-intercept repair."""

import argparse
import hashlib
import json
import platform
from collections import defaultdict, deque
from datetime import date, timedelta
from itertools import groupby
from pathlib import Path

import numpy as np
import scipy
from scipy.optimize import brentq
from scipy.special import expit, logit

from upset.skill import striking_accuracy as original
from upset.skill import striking_adaptation as repair
from upset.skill import striking_validation as validation
from upset.skill.striking_adapter import (
    digest,
    encoded,
    load_adapter,
    verify_hashes,
    write_artifact,
)

CONFIG = {'version': 'striking_rolling_calibration_v1', 'window_days': 730,
          'intercept_bounds': [-.5, .5], 'clip': 1e-6, 'preview_bias_max_percentage_points': 1.,
          'public_release': False, 'opponent_adjusted': False}
CANDIDATE = 'rolling_volume'


def fit_intercept(rows):
    if not rows:
        return 0.
    y = np.array([r['landed'] for r in rows])
    n = np.array([r['attempts'] for r in rows])
    p = np.array([r['recent_uncalibrated'] for r in rows], dtype=float)
    if (any(type(r['landed']) is not int or type(r['attempts']) is not int for r in rows)
            or np.any((n <= 0) | (y < 0) | (y > n)) or not np.isfinite(p).all()
            or np.any((p < 0) | (p > 1))):
        raise ValueError('Rolling calibration requires valid pre-date means and positive trials.')
    logits = logit(np.clip(p, CONFIG['clip'], 1-CONFIG['clip']))
    def gradient(delta):
        return float(np.sum(n*expit(logits+delta)-y))
    low, high = CONFIG['intercept_bounds']
    if gradient(low) >= 0:
        return low
    if gradient(high) <= 0:
        return high
    return float(brentq(gradient, low, high, xtol=1e-12))


def rolling_predictions(rows):
    history, result = deque(), []
    for day, group in groupby(sorted(rows, key=lambda r: (
            r['event_date'], r['fight_id'], r['fighter_id'])), key=lambda r: r['event_date']):
        batch = list(group)
        start = (date.fromisoformat(day)-timedelta(days=CONFIG['window_days'])).isoformat()
        while history and history[0]['event_date'] < start:
            history.popleft()
        intercept = fit_intercept(list(history))
        for row in batch:
            result.append({**row, 'retained_adaptation_mean': row['recent_calibrated'],
                           'recent_calibrated': repair.calibrated_mean(row['recent_uncalibrated'], intercept),
                           'rolling_intercept': intercept, 'calibration_sides': len(history),
                           'calibration_attempts': sum(r['attempts'] for r in history),
                           'calibration_window_start': start,
                           'calibration_latest_date': history[-1]['event_date'] if history else None})
        history.extend(r for r in batch if r['status'] == 'observed' and r['recent_uncalibrated'] is not None)
    return result


def evaluate(rows, progress=print):
    predictions = rolling_predictions(rows)
    specs = {'frozen_constant': {'field': 'sample_adjusted', 'c100': 20, 'gamma': 0},
             'simple_constant': {'field': 'population_mean', 'c100': 20, 'gamma': 0},
             'retained_adaptation': repair.fit_dispersion(predictions, 'retained_adaptation_mean'),
             'rolling_constant': repair.fit_dispersion(predictions, 'recent_calibrated', constant=True),
             CANDIDATE: repair.fit_dispersion(predictions, 'recent_calibrated')}
    development = [r for r in predictions if r['event_date'] >= '2019-01-01']
    common = [r for r in development if original.common_support(r)]
    if not common:
        raise ValueError('Missing matched development observations.')
    arrays, summaries = {}, {}
    for name, spec in specs.items():
        progress('Checking rolling repair: '+name)
        arrays[name] = repair.diagnostics(common, spec)
        summaries[name] = {'specification': spec, **validation.calibration(common, arrays[name], overall=True)}
    point = {ref: repair.point_comparison(common, 'recent_calibrated', ref)
             for ref in ('sample_adjusted', 'population_mean', 'retained_adaptation_mean')}
    groups = defaultdict(lambda: defaultdict(list))
    for i, row in enumerate(common):
        for field, label in validation.labels(row).items():
            groups[field][label].append(i)
    subgroups, point_flags, cal_flags, thin = {}, [], [], []
    for field, slices in sorted(groups.items()):
        subgroups[field] = {}
        for label, indices in sorted(slices.items()):
            subset = [common[i] for i in indices]
            comparisons = {ref: repair.point_comparison(subset, 'recent_calibrated', ref)
                           for ref in ('sample_adjusted', 'population_mean')}
            cal = validation.calibration(common, arrays[CANDIDATE], indices)
            subgroups[field][label] = {'side_bouts': len(subset), 'point_comparisons': comparisons,
                                      'candidate_calibration': cal}
            if any(v['material_regression'] for v in comparisons.values()):
                point_flags.append(field+':'+label)
            if any(v['status'] == 'outside_band' for v in cal['levels'].values()):
                cal_flags.append(field+':'+label)
            if any(v['status'] == 'inconclusive_thin_group' for v in cal['levels'].values()):
                thin.append(field+':'+label)
        progress('Completed rolling subgroup: '+field)
    bias = 100*(summaries[CANDIDATE]['predicted_accuracy']-summaries[CANDIDATE]['observed_accuracy'])
    delta = point['sample_adjusted']['candidate_minus_reference_nll']
    eligible = (delta['interval_95'] is not None and delta['interval_95'][1] < 0
                and abs(bias) <= 1. and not point_flags)
    scores = {}
    for field in ('sample_adjusted', 'retained_adaptation_mean', 'recent_calibrated'):
        nll, cross, brier = validation.point_arrays(common, field)
        trials = sum(r['attempts'] for r in common)
        scores[field] = {'binomial_nll': float(nll.mean()), 'cross_entropy': float(cross.sum()/trials),
                         'attempt_brier': float(brier.sum()/trials)}
    report = {'study_version': CONFIG['version'], 'config': CONFIG, 'distribution_fits': specs,
              'primary_distributions': summaries, 'primary_point_comparisons': point, 'point_scores': scores,
              'primary_predictive_comparisons': {
                  name: validation.predictive_comparison(common, arrays[CANDIDATE], value, fighter_sensitivity=True)
                  for name, value in arrays.items() if name != CANDIDATE},
              'subgroups': subgroups,
              'coverage': {'adapter_sides': len(rows), 'matched_development_sides': len(common),
                           'rolling_empty_history_sides': sum(r['calibration_sides'] == 0 for r in development)},
              'decision': {'eligible_for_experimental_mean_preview': bool(eligible),
                           'mean_bias_percentage_points_predicted_minus_observed': bias,
                           'material_point_regression_groups': point_flags,
                           'distribution_calibration_failure_groups': cal_flags,
                           'inconclusive_groups': thin,
                           'distribution_diagnostics_passed': validation.within_bands(summaries[CANDIDATE])
                           and not point_flags and not cal_flags,
                           'public_release': False, 'opponent_adjusted': False},
              'evaluation_label': 'Subsequent inspected development study; not protected future validation.',
              'public_release': False, 'opponent_adjusted': False}
    return report, predictions, common, arrays


def run(adapter, adaptation, protocol, output):
    if output.exists() or any(output.resolve().is_relative_to(p.resolve()) for p in (adapter, adaptation)):
        raise ValueError('Use a new immutable output separate from inputs.')
    sides, metadata, hashes = load_adapter(adapter)
    prior = json.loads((adaptation/'report.json').read_text())
    verify_hashes(prior['input_sha256'])
    for name, expected in prior['output_sha256'].items():
        if digest(adaptation/name) != expected:
            raise ValueError('Retained adaptation hash differs.')
    saved = [json.loads(line) for line in (adaptation/'predictions.jsonl').read_text().splitlines()]
    mean_fit = prior['mean_fit']
    reproduced = repair.recent_predictions(sides, mean_fit['selected_half_life_days'], mean_fit['selected_strength'])
    for row in reproduced:
        row['recent_calibrated'] = repair.calibrated_mean(row['recent_uncalibrated'], mean_fit['selected_intercept'])
    if reproduced != saved:
        raise ValueError('Retained adaptation predictions did not reproduce.')
    hashes.update(prior['input_sha256'])
    paths = [adaptation/'report.json', protocol, Path(__file__)] + [adaptation/name for name in prior['output_sha256']]
    hashes.update({str(p.resolve()): digest(p) for p in paths})
    report, predictions, common, arrays = evaluate(saved, lambda msg: print(msg, flush=True))
    if len(common) != prior['coverage']['matched_development_sides']:
        raise ValueError('Matched support changed.')
    report.update(input_sha256=hashes, before_exclusive=metadata['before_exclusive'],
                  base_model={'half_life_days': mean_fit['selected_half_life_days'],
                              'strength': mean_fit['selected_strength']},
                  reproduced_retained_sides=len(saved),
                  versions={'python': platform.python_version(), 'numpy': np.__version__, 'scipy': scipy.__version__})
    def jsonl(records):
        return ''.join(json.dumps(r, sort_keys=True, allow_nan=False)+'\n' for r in records)
    files = {'predictions.jsonl': jsonl(predictions),
             'calibration_rows.jsonl': jsonl(validation.calibration_rows(common, arrays)),
             'config.json': encoded(CONFIG), 'protocol.md': protocol.read_text()}
    report['output_sha256'] = {name: hashlib.sha256(body.encode()).hexdigest() for name, body in files.items()}
    verify_hashes(hashes)
    write_artifact(output, {**files, 'report.json': encoded(report)})
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--adapter', type=Path, required=True)
    parser.add_argument('--adaptation', type=Path, required=True)
    parser.add_argument('--protocol', type=Path, default=Path('docs/STRIKING_ROLLING_CALIBRATION_PROTOCOL_V1.md'))
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = run(args.adapter, args.adaptation, args.protocol, args.output)
    print(encoded({key: report[key] for key in ('base_model', 'coverage', 'point_scores', 'decision')}))


if __name__ == '__main__':
    main()
