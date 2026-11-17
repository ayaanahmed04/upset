"""Post-result descriptive audit: aggregate bias is not individual-fight accuracy.

This does not fit a model, change a release gate, or produce fresh validation.
"""

import argparse
import json
from collections import defaultdict
from pathlib import Path

import numpy as np

from upset.skill.striking_adapter import digest, encoded, verify_hashes, write_artifact
from upset.skill.striking_validation import labels

METHODS = ('population_mean', 'raw_career', 'raw_last5', 'sample_adjusted',
           'retained_adaptation_mean', 'recent_calibrated')


def metrics(rows, field):
    n = np.array([r['attempts'] for r in rows], dtype=float)
    y = np.array([r['landed'] for r in rows], dtype=float)
    p = np.array([r[field] for r in rows], dtype=float)
    if not len(rows) or not np.all(n > 0) or not np.all(np.isfinite(p)):
        raise ValueError('Audit requires positive exposure and finite estimates.')
    error = p-y/n
    return {'sides': len(rows), 'attempts': int(n.sum()),
            'observed_accuracy': float(y.sum()/n.sum()),
            'predicted_accuracy': float(np.average(p, weights=n)),
            'aggregate_bias_percentage_points': float(100*np.average(error, weights=n)),
            'mean_absolute_error_percentage_points': float(100*np.abs(error).mean()),
            'root_mean_squared_error_percentage_points': float(100*np.sqrt(np.mean(error**2))),
            'attempt_weighted_mean_absolute_error_percentage_points': float(100*np.average(np.abs(error), weights=n)),
            'median_absolute_error_percentage_points': float(100*np.median(np.abs(error))),
            'p90_absolute_error_percentage_points': float(100*np.quantile(np.abs(error), .9)),
            'fraction_within_5_percentage_points': float(np.mean(np.abs(error) <= .05)),
            'fraction_within_10_percentage_points': float(np.mean(np.abs(error) <= .1))}


def mae_comparison(rows, cluster_field):
    groups = defaultdict(lambda: [0., 0])
    for row in rows:
        observed = row['landed']/row['attempts']
        delta = 100*(abs(row['recent_calibrated']-observed)-abs(row['sample_adjusted']-observed))
        group = groups[row[cluster_field]]
        group[0] += delta
        group[1] += 1
    values = np.array([groups[key] for key in sorted(groups)])
    rng = np.random.default_rng(20261104)
    sampled = values[rng.integers(0, len(values), size=(1000, len(values)))].sum(axis=1)
    boot = sampled[:, 0]/sampled[:, 1]
    return {'candidate_minus_original_mae_percentage_points': float(values[:, 0].sum()/values[:, 1].sum()),
            'interval_95': [float(v) for v in np.quantile(boot, [.025, .975])],
            'clusters': len(groups), 'replicates': 1000, 'seed': 20261104,
            'limitation': 'One-way cluster sensitivity; does not resolve crossed dependence or adaptive development.'}


def audit(study, output):
    report = json.loads((study/'report.json').read_text())
    verify_hashes(report['input_sha256'])
    for name, value in report['output_sha256'].items():
        if digest(study/name) != value:
            raise ValueError('Retained study changed.')
    outcomes = [json.loads(line) for line in (study/'calibration_rows.jsonl').read_text().splitlines()]
    keys = {(r['fight_id'], r['fighter_id']) for r in outcomes}
    if len(outcomes) != 7028 or len(keys) != len(outcomes):
        raise ValueError('Original common support changed.')
    lookup = {(r['fight_id'], r['fighter_id']): r for r in
              map(json.loads, (study/'predictions.jsonl').read_text().splitlines())}
    rows = []
    for outcome in outcomes:
        row = lookup[outcome['fight_id'], outcome['fighter_id']]
        if any(row[key] != outcome[key] for key in ('landed', 'attempts', 'event_date')):
            raise ValueError('Saved outcome and prediction disagree.')
        rows.append(row)
    summary = {name: metrics(rows, name) for name in METHODS}
    for name, method in [('sample_adjusted', 'frozen_constant'), ('recent_calibrated', 'rolling_volume')]:
        original = report['primary_distributions'][method]
        for field in ('observed_accuracy', 'predicted_accuracy'):
            if abs(summary[name][field]-original[field]) > 1e-12:
                raise ValueError('Aggregate accuracy did not reproduce.')
    groups = defaultdict(lambda: defaultdict(list))
    for row in rows:
        for field, label in labels(row).items():
            groups[field][label].append(row)
    subgroup_summary = {field: {label: {name: metrics(subset, name)
                                      for name in ('sample_adjusted', 'recent_calibrated')}
                                for label, subset in sorted(slices.items())}
                        for field, slices in sorted(groups.items())}
    uncertainty = {}
    for label, group in report['subgroups']['actual_attempts'].items():
        cal = group['candidate_calibration']
        uncertainty[label] = {
            'sides': group['side_bouts'],
            'observed_accuracy': cal['observed_accuracy'], 'predicted_accuracy': cal['predicted_accuracy'],
            'levels': {level: {'status': values['status'],
                               'primary_seed_randomized_pit_coverage': values['randomized_pit_coverage']['mean'],
                               'all_seeds': values['seed_sensitivity']}
                       for level, values in cal['levels'].items()}}
    hashes = {str(p.resolve()): digest(p) for p in
              [study/'report.json', Path(__file__), *[study/name for name in report['output_sha256']]]}
    result = {'audit_version': 'striking_point_error_audit_v1',
              'purpose': 'Explain aggregate bias versus realized per-fighter-bout error; no model fitting or gate change.',
              'evaluation_label': 'Post-result descriptive analysis of reused development evidence.',
              'before_exclusive': report['before_exclusive'], 'methods': summary,
              'mae_comparisons': {field: mae_comparison(rows, field) for field in ('event_date', 'fighter_id')},
              'subgroups': subgroup_summary, 'retained_attempt_volume_uncertainty': uncertainty,
              'distribution_failure_groups': report['decision']['distribution_calibration_failure_groups'],
              'input_sha256': hashes, 'public_release': False, 'opponent_adjusted': False,
              'important_limit': 'Observed fight accuracy includes sampling and matchup variability; these errors do not measure latent skill error.'}
    # A mean can be exactly right overall while missing each observation badly.
    illustration = [{'attempts': 100, 'landed': 40, 'p': .5},
                    {'attempts': 100, 'landed': 60, 'p': .5}]
    check = metrics(illustration, 'p')
    if abs(check['aggregate_bias_percentage_points']) > 1e-12 or abs(check['mean_absolute_error_percentage_points']-10) > 1e-12:
        raise ValueError('Bias/absolute-error distinction failed independent illustration.')
    verify_hashes(hashes)
    write_artifact(output, {'report.json': encoded(result)})
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--study', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = audit(args.study, args.output)
    print(encoded({'methods': result['methods'], 'mae_comparisons': result['mae_comparisons']}))
