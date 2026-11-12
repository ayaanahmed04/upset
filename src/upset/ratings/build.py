"""Build a hash-bound experimental rating snapshot under the declared v1 protocol."""

import argparse
import hashlib
import json
from bisect import bisect_left
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
from scipy.optimize import minimize_scalar
from scipy.special import expit

from upset.ratings.data import load_bouts
from upset.ratings.engine import replay
from upset.skill.striking_adapter import digest, encoded, verify_hashes, write_artifact

VERSION = 'upset_rating_experimental_v1'
KEYS = ('striking', 'wrestling', 'grappling', 'resume')
LABELS = ('Striking', 'Wrestling', 'Grappling', 'Résumé')
ANCHORS = [(0, 60), (.10, 69), (.50, 77), (.80, 84), (.95, 89),
           (.97, 94), (.995, 98), (.9999, 99), (1, 99)]
CONFIG = {'version': VERSION, 'recency': .85, 'minutes_prior': 45,
          'resume_weights': [.25, .5, .75], 'skill_weights': [.5, .3, .2],
          'fit_start': '2012-01-01', 'selection_before': '2016-01-01',
          'freeze_before': '2019-01-01', 'evaluation_before': '2026-10-26',
          'slope_bounds': [.001, 5.], 'minimum_evaluation_bouts': 500,
          'small_history_bouts': 5, 'small_history_cap': 88, 'change_cap': 5,
          'bootstrap_seed': 20261104, 'bootstrap_replicates': 1000}

PART_METRICS = {
    'striking': ['sig_landed_per_minute', 'sig_absorbed_per_minute', 'sig_differential_per_minute',
                 'striking_accuracy', 'striking_defense', 'knockdowns_per_15_minutes',
                 'knockdowns_received_per_15_minutes', 'ko_losses_per_bout'],
    'wrestling': ['takedowns_per_15_minutes', 'takedown_accuracy', 'takedown_defense', 'control_share'],
    'grappling': ['submission_attempts_per_15_minutes', 'submission_wins_per_bout',
                  'submission_losses_per_opponent_attempt', 'ground_strike_differential_per_minute'],
    'resume': ['elo'],
}


def combine(parts, weight):
    """Full-precision component units, before any empirical display curve/caps."""
    if any(parts.get(key) is None for key in KEYS):
        return None, None
    values = {key: 60 + .39 * parts[key] for key in KEYS}
    skills = sum(v * w for v, w in zip(sorted([values[key] for key in KEYS[:3]], reverse=True), [.5, .3, .2]))
    return weight * values['resume'] + (1 - weight) * skills, skills


def eligible(rows):
    return [row for row in rows if row['winner_id'] is not None
            and all(n > 0 for n in row['prior_bouts'])
            and all(all(part.get(key) is not None for key in KEYS) for part in row['parts'])]


def inputs(rows, weight):
    x = np.array([combine(row['parts'][0], weight)[0] - combine(row['parts'][1], weight)[0] for row in rows])
    y = np.array([int(row['winner_id'] == row['fighter_ids'][0]) for row in rows])
    return x, y


def fit_slope(rows, weight):
    x, y = inputs(rows, weight)
    if not len(x) or not np.any(x):
        raise ValueError('Insufficient nonconstant earlier training features.')
    def objective(slope):
        z = slope * x
        return float(np.mean(np.logaddexp(0, z) - y * z))
    fit = minimize_scalar(objective, bounds=CONFIG['slope_bounds'], method='bounded',
                          options={'xatol': 1e-10})
    if not fit.success or not np.isfinite(fit.fun):
        raise ValueError('Probability calibration did not converge.')
    candidates = [CONFIG['slope_bounds'][0], float(fit.x), CONFIG['slope_bounds'][1]]
    slope = min(candidates, key=objective)
    return {'slope': slope, 'training_nll': objective(slope), 'bouts': len(rows),
            'boundary': slope in CONFIG['slope_bounds']}


def score(rows, weight, slope):
    if not rows:
        raise ValueError('No eligible bouts for the declared scoring period.')
    x, y = inputs(rows, weight)
    z = slope * x
    losses = np.logaddexp(0, z) - y * z
    p = expit(z)
    ties = np.abs(x) <= 1e-12
    metrics = {'bouts': len(rows), 'nll': float(np.mean(losses)),
               'brier': float(np.mean((p - y)**2)), 'ties': int(ties.sum()),
               'ordering_accuracy_with_half_ties': float(np.mean(np.where(ties, .5, (x > 0) == y))),
               'slope': slope, 'resume_weight': weight}
    return metrics, losses, p


def select_model(rows):
    matched = eligible(rows)
    fit_rows = [r for r in matched if CONFIG['fit_start'] <= r['event_date'] < CONFIG['selection_before']]
    selection = [r for r in matched if CONFIG['selection_before'] <= r['event_date'] < CONFIG['freeze_before']]
    all_training = fit_rows + selection
    if not fit_rows or not selection:
        raise ValueError('Both declared training periods must be populated.')
    grid = []
    for weight in CONFIG['resume_weights']:
        fit = fit_slope(fit_rows, weight)
        result, _, _ = score(selection, weight, fit['slope'])
        grid.append({'resume_weight': weight, 'fit': fit, 'selection': result})
    winner = min(grid, key=lambda row: row['selection']['nll'])
    weight = winner['resume_weight']
    final = fit_slope(all_training, weight)
    reference = fit_slope(all_training, 1.)
    return {'resume_weight': weight, 'skill_weights': [.5, .3, .2],
            'probability_fit': final, 'resume_only_fit': reference, 'selection_grid': grid,
            'training_before': CONFIG['freeze_before'], 'within_part_weights': 'fixed protocol v1'}


def curve_value(value, reference):
    left, right = np.searchsorted(reference, value, side='left'), np.searchsorted(reference, value, side='right')
    percentile = float((left + right) / (2 * len(reference)))
    grade = float(np.interp(percentile, [p for p, _ in ANCHORS], [v for _, v in ANCHORS]))
    return int(np.floor(grade + .5)), percentile


def make_ratings(snapshots, bouts, model):
    reference = sorted(combine(row['raw_parts'], model['resume_weight'])[0] for row in snapshots
                       if row['event_date'] < CONFIG['freeze_before']
                       and combine(row['raw_parts'], model['resume_weight'])[0] is not None)
    if len(reference) < 100:
        raise ValueError('Too little earlier evidence for the fixed display reference.')
    last, peaks, rows = {}, {}, []
    bout_lookup = defaultdict(list)
    for bout in bouts:
        for uid in bout['fighter_ids']:
            bout_lookup[bout['event_date'], uid].append(bout)
    for source in snapshots:
        raw, skills = combine(source['raw_parts'], model['resume_weight'])
        if raw is None:
            continue
        uid = source['fighter_id']
        curve_score, percentile = curve_value(raw, reference)
        protected = min(curve_score, CONFIG['small_history_cap']) if source['bouts'] < 5 else curve_score
        previous = last.get(uid)
        shown = protected if previous is None else max(previous - 5, min(previous + 5, protected))
        # A previous provisional cap cannot relax the still-small-history cap.
        if source['bouts'] < 5:
            shown = min(shown, 88)
        peak = max(peaks.get(uid, shown), shown)
        parts = []
        for key, label in zip(KEYS, LABELS):
            metrics = {name: source['metrics'].get(name) for name in PART_METRICS[key]}
            if key == 'resume':
                metrics['elo'] = source['elo']
            parts.append({'key': key, 'label': label, 'score': 60 + .39 * source['raw_parts'][key],
                          'raw_score': source['raw_parts'][key], 'metrics': metrics})
        fights = bout_lookup[source['event_date'], uid]
        row = {'fighter_id': uid, 'event_date': source['event_date'], 'score': shown, 'peak': peak,
               'change': None if previous is None else shown - previous, 'bouts': source['bouts'],
               'provisional': source['bouts'] < 4, 'division': source['division'], 'elo': source['elo'],
               'parts': parts, 'raw_combined': raw, 'skills_combined': skills,
               'curve_score': curve_score, 'curve_percentile': percentile,
               'small_history_adjustment': protected - curve_score,
               'change_adjustment': shown - protected,
               'coverage': source['coverage'], 'fight_ids': [fight['fight_id'] for fight in fights],
               'last_outcomes': ['other' if fight['winner_id'] is None else
                                 'win' if fight['winner_id'] == uid else 'loss' for fight in fights]}
        rows.append(row)
        last[uid], peaks[uid] = shown, peak
    return rows, reference


def cluster_comparison(rows, differences, field):
    groups = defaultdict(lambda: [0., 0.])
    for row, value in zip(rows, differences):
        ids = [row['event_date']] if field == 'event_date' else row['fighter_ids']
        for group in ids:
            groups[group][0] += float(value)
            groups[group][1] += 1
    values = np.array([groups[key] for key in sorted(groups)])
    rng = np.random.default_rng(CONFIG['bootstrap_seed'])
    sampled = values[rng.integers(0, len(values), size=(1000, len(values)))].sum(axis=1)
    estimates = sampled[:, 0] / sampled[:, 1]
    return {'mean': float(np.mean(differences)), 'interval_95': [float(x) for x in np.quantile(estimates, [.025, .975])],
            'clusters': len(groups), 'replicates': 1000, 'seed': CONFIG['bootstrap_seed'],
            'limitation': 'One-way cluster sensitivity; crossed dependence and model-selection uncertainty remain.'}


def displayed_track_record(prefights, ratings):
    by_fighter = defaultdict(list)
    for row in ratings:
        by_fighter[row['fighter_id']].append(row)
    wins = total = tied = unavailable = 0
    for row in prefights:
        if not CONFIG['freeze_before'] <= row['event_date'] < CONFIG['evaluation_before'] or row['winner_id'] is None:
            continue
        scores = []
        for uid in row['fighter_ids']:
            history = by_fighter[uid]
            i = bisect_left([r['event_date'] for r in history], row['event_date']) - 1
            scores.append(history[i]['score'] if i >= 0 else None)
        if None in scores:
            unavailable += 1
        elif scores[0] == scores[1]:
            tied += 1
        else:
            total += 1
            wins += row['winner_id'] == row['fighter_ids'][int(scores[1] > scores[0])]
    return {'wins': wins, 'total': total, 'accuracy': wins / total if total else None,
            'ties_excluded': tied, 'unavailable_excluded': unavailable,
            'from_date': CONFIG['freeze_before'], 'before_exclusive': CONFIG['evaluation_before'],
            'label': 'Retrospective development track record; not fresh future validation.'}


def evaluation(prefights, ratings, model):
    decisive = [r for r in prefights if CONFIG['freeze_before'] <= r['event_date'] < CONFIG['evaluation_before']
                and r['winner_id'] is not None]
    rows = [r for r in eligible(prefights) if CONFIG['freeze_before'] <= r['event_date'] < CONFIG['evaluation_before']]
    candidate, losses, probabilities = score(rows, model['resume_weight'], model['probability_fit']['slope'])
    reference, reference_losses, _ = score(rows, 1., model['resume_only_fit']['slope'])
    subgroups = defaultdict(lambda: defaultdict(list))
    for i, row in enumerate(rows):
        subgroups['year'][row['event_date'][:4]].append(i)
        subgroups['experience']['1–3 prior' if min(row['prior_bouts']) < 4 else '4+ prior'].append(i)
        subgroups['division'][row.get('division') or 'Unknown'].append(i)
    summaries = {}
    for field, groups in subgroups.items():
        summaries[field] = {label: {'bouts': len(indices), 'nll': float(losses[indices].mean()),
                                    'candidate_minus_resume_nll': float((losses - reference_losses)[indices].mean())}
                            for label, indices in sorted(groups.items())}
    checks = all(60 <= r['score'] <= 99 and r['score'] <= r['peak'] <= 99
                 and (r['bouts'] >= 5 or r['score'] <= 88)
                 and (r['change'] is None or abs(r['change']) <= 5) for r in ratings)
    checks = checks and all(all(day is None or day < row['event_date']
                               for day in row['prior_snapshot_dates']) for row in prefights)
    eligible_for_serving = bool(checks and len(rows) >= 500 and np.isfinite(candidate['nll'])
                               and candidate['nll'] < np.log(2) and model['probability_fit']['slope'] > 0)
    result = {'version': VERSION, 'experimental': True, 'validated': False,
              'engineering_checks_passed': bool(checks), 'serving_eligible': eligible_for_serving,
              'evaluation_label': 'Previously inspected historical development data; not protected future validation.',
              'candidate': candidate, 'resume_only': reference,
              'coin_flip_nll': float(np.log(2)), 'coin_flip_brier': .25,
              'coin_flip_ordering_accuracy': .5,
              'support': {'decisive_development_bouts': len(decisive), 'matched_bouts': len(rows),
                          'excluded_debut_bouts': sum(any(n == 0 for n in r['prior_bouts']) for r in decisive),
                          'excluded_unavailable_parts_after_debuts': sum(all(n > 0 for n in r['prior_bouts'])
                              and any(any(part.get(key) is None for key in KEYS) for part in r['parts']) for r in decisive)},
              'beats_resume_only_point_nll': bool(losses.mean() < reference_losses.mean()),
              'paired_nll_comparisons': {field: cluster_comparison(rows, losses - reference_losses, field)
                                         for field in ('event_date', 'fighter_id')},
              'subgroups': summaries, 'track_record': displayed_track_record(prefights, ratings),
              'rating_rows': len(ratings), 'rated_fighters': len({r['fighter_id'] for r in ratings}),
              'cap_applied_rows': sum(bool(r['small_history_adjustment'] or r['change_adjustment']) for r in ratings),
              'display_99_rows': sum(r['score'] == 99 for r in ratings),
              'public_release': False,
              'limits': ['Opponent residual adjustment is a statistical prototype, not validated latent skill.',
                         'Component weights and exposure priors are fixed starting choices.',
                         'No individual confidence intervals or win-probability UI release.',
                         'Current reviewed amendments are hindsight.',
                         'Display changes are capped; the raw combined index is not.',
                         'Pre-2019 display history is a retrospective backcast under the frozen 2018 model.']}
    development = [{**row, 'candidate_probability_a': float(p), 'candidate_nll': float(loss),
                    'resume_nll': float(ref_loss)} for row, p, loss, ref_loss in zip(rows, probabilities, losses, reference_losses)]
    return result, development


def build(database, before, protocol, output):
    if output.exists() or output.resolve().is_relative_to(database.parent.resolve()):
        raise ValueError('Use a new immutable rating snapshot separate from the source database.')
    from upset.ratings import data, engine, serving
    dependencies = [Path(__file__), Path(data.__file__), Path(engine.__file__), Path(serving.__file__), protocol]
    input_hashes = {str(path.resolve()): digest(path) for path in dependencies}
    input_hashes[str(database.resolve())] = digest(database)
    bouts, metadata = load_bouts(database, before)
    print('Replaying paired history: ' + str(len(bouts)) + ' bouts', flush=True)
    snapshots, prefights = replay(bouts, minutes_prior=45, recency=.85)
    division_by_bout = {b['fight_id']: b['division'] for b in bouts}
    for row in prefights:
        row['division'] = division_by_bout[row['fight_id']]
    print('Chronological replay complete; selecting earlier weights', flush=True)
    model = select_model(prefights)
    ratings, reference = make_ratings(snapshots, bouts, model)
    print('Fixed curve and guarded display history complete', flush=True)
    assessed, development = evaluation(prefights, ratings, model)
    files = {'ratings.jsonl': ''.join(json.dumps(r, sort_keys=True, allow_nan=False) + '\n' for r in ratings),
             'prefights.jsonl': ''.join(json.dumps(r, sort_keys=True, allow_nan=False) + '\n' for r in prefights),
             'development.jsonl': ''.join(json.dumps(r, sort_keys=True, allow_nan=False) + '\n' for r in development),
             'evaluation.json': encoded(assessed), 'model.json': encoded({**model, 'reference_values': reference, 'anchors': ANCHORS}),
             'config.json': encoded(CONFIG), 'protocol.md': protocol.read_text()}
    manifest = {'version': VERSION, 'experimental': True, 'validated': False,
                'created_at_utc': datetime.now(UTC).isoformat(),
                'input_database': str(database.resolve()), 'database_sha256': digest(database),
                'before_exclusive': before, 'latest_event': max(b['event_date'] for b in bouts),
                'input_sha256': input_hashes,
                'output_sha256': {name: hashlib.sha256(body.encode()).hexdigest() for name, body in files.items()},
                'display_curve': {'reference_before': CONFIG['freeze_before'], 'reference_moments': len(reference),
                                  'description': 'Fixed historical UFC reference through 2018; retrospective before 2019.'},
                'model': model, 'source_metadata': metadata, 'public_release': False}
    verify_hashes(input_hashes)
    files['manifest.json'] = encoded(manifest)
    write_artifact(output, files)
    return assessed


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database', type=Path, required=True)
    parser.add_argument('--before', required=True)
    parser.add_argument('--protocol', type=Path, default=Path('docs/OVERALL_RATING_PROTOCOL_V1.md'))
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print(encoded(build(args.database, args.before, args.protocol, args.output)))


if __name__ == '__main__':
    main()
