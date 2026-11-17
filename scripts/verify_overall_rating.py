"""Read-only, independent arithmetic audit of a saved experimental rating study.

No fitting or display-parameter selection occurs here. Input features themselves
retain the engine's separate tests; this audit reconstructs dated exposure
counts, recorded weighted inputs, Elo, published formulas and saved scores.
"""

import argparse
import hashlib
import json
from bisect import bisect_left, bisect_right
from collections import Counter, defaultdict
from itertools import groupby, pairwise
from math import erfc, exp, floor, isclose, log, sqrt
from pathlib import Path

import numpy as np

from upset.ratings.data import load_bouts
from upset.ratings.serving import load_snapshot
from upset.skill.defense_prospective import load_freeze

PARTS = ('striking', 'wrestling', 'grappling', 'resume')
WEIGHTS = {
    'striking': {'sig_diff': .30, 'sig_accuracy': .15, 'sig_defense': .20,
                 'kd_scored': .20, 'kd_avoided': .10, 'ko_avoided': .05},
    'wrestling': {'td_rate': .25, 'td_accuracy': .20, 'td_defense': .35, 'control_share': .20},
    'grappling': {'sub_rate': .30, 'sub_win': .25, 'sub_avoided': .20, 'ground_diff': .25},
}
ANCHORS = [(0, 60), (.10, 69), (.50, 77), (.80, 84), (.95, 89),
           (.97, 94), (.995, 98), (.9999, 99), (1, 99)]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def close(a, b, label, tolerance=1e-9):
    if a is None or b is None:
        if a is not b:
            raise ValueError('Missingness differs: ' + label)
    elif not isclose(a, b, rel_tol=0, abs_tol=tolerance):
        raise ValueError(f'{label}: {a!r} != {b!r}')


def records(path):
    return [json.loads(line) for line in path.read_text().splitlines()]


def combined(raw, weight):
    if any(raw.get(key) is None for key in PARTS):
        return None, None
    values = {key: 60+.39*raw[key] for key in PARTS}
    a, b, c = sorted((values[key] for key in PARTS[:3]), reverse=True)
    skills = .5*a+.3*b+.2*c
    return weight*values['resume']+(1-weight)*skills, skills


def probability(z):
    return 1/(1+exp(-z)) if z >= 0 else exp(z)/(1+exp(z))


def log_score(rows, weight, slope):
    values, probabilities, briers, ordering, differences = [], [], [], [], []
    for row in rows:
        a, _ = combined(row['parts'][0], weight)
        b, _ = combined(row['parts'][1], weight)
        x, y = a-b, int(row['winner_id'] == row['fighter_ids'][0])
        z = slope*x
        # log(1+exp(z))-y*z, evaluated independently with stable logaddexp.
        nll = float(np.logaddexp(0., z))-y*z
        p = probability(z)
        values.append(nll)
        probabilities.append(p)
        briers.append((p-y)**2)
        ordering.append(.5 if abs(x) <= 1e-12 else float((x > 0) == bool(y)))
        differences.append(x*(p-y))
    return {'nll': sum(values)/len(values), 'brier': sum(briers)/len(briers),
            'ordering_accuracy_with_half_ties': sum(ordering)/len(ordering),
            'gradient': sum(differences)/len(differences)}, values, probabilities


def weighted_metrics(history):
    totals = defaultdict(lambda: [0., 0.])
    for bout, side in history:
        # Every observation on a simultaneous date has the same relative weight.
        weight = .85**sum(other['event_date'] > bout['event_date'] for other, _ in history)
        own, opponent = bout['stats'][side], bout['stats'][1-side]
        minute = bout['duration_seconds']/60
        loss = bout['winner_id'] is not None and bout['winner_id'] != bout['fighter_ids'][side]
        win = bout['winner_id'] == bout['fighter_ids'][side]

        def add(key, numerator, denominator, weight=weight):
            if denominator > 0:
                totals[key][0] += weight*numerator
                totals[key][1] += weight*denominator

        for key, numerator in (
                ('sig_landed_per_minute', own['sig_strikes_landed']),
                ('sig_absorbed_per_minute', opponent['sig_strikes_landed']),
                ('sig_differential_per_minute', own['sig_strikes_landed']-opponent['sig_strikes_landed']),
                ('knockdowns_per_15_minutes', 15*own['knockdowns']),
                ('knockdowns_received_per_15_minutes', 15*opponent['knockdowns']),
                ('takedowns_per_15_minutes', 15*own['takedowns_landed']),
                ('submission_attempts_per_15_minutes', 15*own['submission_attempts']),
                ('ground_strike_differential_per_minute', own['ground_landed']-opponent['ground_landed'])):
            add(key, numerator, minute)
        add('striking_accuracy', own['sig_strikes_landed'], own['sig_strikes_attempted'])
        add('striking_defense', opponent['sig_strikes_attempted']-opponent['sig_strikes_landed'], opponent['sig_strikes_attempted'])
        add('takedown_accuracy', own['takedowns_landed'], own['takedowns_attempted'])
        add('takedown_defense', opponent['takedowns_attempted']-opponent['takedowns_landed'], opponent['takedowns_attempted'])
        add('ko_losses_per_bout', int(loss and bout['method_group'] == 'ko'), 1)
        add('submission_wins_per_bout', int(win and bout['method_group'] == 'sub'), 1)
        sub_loss = int(loss and bout['method_group'] == 'sub')
        if sub_loss <= opponent['submission_attempts']:
            add('submission_losses_per_opponent_attempt', sub_loss, opponent['submission_attempts'])
        if own['control_seconds'] is not None and opponent['control_seconds'] is not None:
            add('control_share', own['control_seconds']/60, (own['control_seconds']+opponent['control_seconds'])/60)
    return {key: num/den for key, (num, den) in totals.items()}


def curve(raw, reference):
    percentile = (bisect_left(reference, raw)+bisect_right(reference, raw))/(2*len(reference))
    for (p0, v0), (p1, v1) in pairwise(ANCHORS):
        if percentile <= p1:
            grade = v0+(v1-v0)*(percentile-p0)/(p1-p0)
            return floor(grade+.5), percentile
    raise ValueError('Curve percentile outside [0,1].')


def verify(snapshot, database):
    root = Path(__file__).resolve().parents[1]
    manifest = json.loads((snapshot/'manifest.json').read_text())
    for name, value in manifest['input_sha256'].items():
        if sha(name) != value:
            raise ValueError('Input hash differs: '+name)
    for name, value in manifest['output_sha256'].items():
        path = snapshot/name
        if not path.resolve().is_relative_to(snapshot.resolve()) or sha(path) != value:
            raise ValueError('Output hash differs: '+name)
    close(sha(database) == manifest['database_sha256'], True, 'database hash', 0)
    bouts, metadata = load_bouts(database, manifest['before_exclusive'])
    assert metadata == manifest['source_metadata']
    prefights, ratings = records(snapshot/'prefights.jsonl'), records(snapshot/'ratings.jsonl')
    model = json.loads((snapshot/'model.json').read_text())
    evaluation = json.loads((snapshot/'evaluation.json').read_text())
    config = json.loads((snapshot/'config.json').read_text())
    assert model['resume_weight'] in [.25, .5, .75]
    assert model['skill_weights'] == [.5, .3, .2] and model['training_before'] == '2019-01-01'
    source = {row['fight_id']: row for row in bouts}
    assert len(prefights) == len(source) == len(bouts)
    assert {row['fight_id'] for row in prefights} == source.keys()
    rating_keys = {(r['fighter_id'], r['event_date']): r for r in ratings}
    assert len(rating_keys) == len(ratings)
    assert ratings == sorted(ratings, key=lambda r: (r['event_date'], r['fighter_id']))
    earlier, counts, histories, elos = {}, Counter(), defaultdict(list), defaultdict(lambda: 1500.)
    source_date_fighters = set()
    feature_matches = raw_input_checks = elo_checks = 0
    display_wins = display_total = display_ties = display_unavailable = 0
    for day, dated in groupby(prefights, key=lambda r: r['event_date']):
        batch, changes = list(dated), defaultdict(list)
        for row in batch:
            bout = source[row['fight_id']]
            assert all(row[k] == bout[k] for k in ('event_date', 'fighter_ids', 'winner_id', 'outcome', 'division'))
            scores = []
            for side, uid in enumerate(row['fighter_ids']):
                assert row['prior_bouts'][side] == counts[uid]
                assert row['prior_snapshot_dates'][side] == earlier.get(uid)
                if earlier.get(uid) is None:
                    assert row['parts'][side] == dict.fromkeys(PARTS, 50.)
                    scores.append(None)
                else:
                    prior = rating_keys.get((uid, earlier[uid]))
                    if prior is not None:
                        expected = {p['key']: p['raw_score'] for p in prior['parts']}
                        for key in PARTS:
                            close(row['parts'][side][key], expected[key], 'pre-date '+key)
                            feature_matches += 1
                        scores.append(prior['score'])
                    else:
                        assert any(row['parts'][side][key] is None for key in PARTS)
                        scores.append(None)
            if '2019-01-01' <= day < '2026-10-26' and row['winner_id'] is not None:
                if None in scores:
                    display_unavailable += 1
                elif scores[0] == scores[1]:
                    display_ties += 1
                else:
                    display_total += 1
                    display_wins += row['winner_id'] == row['fighter_ids'][int(scores[1] > scores[0])]
            a, b = row['fighter_ids']
            if row['winner_id'] is not None:
                expected_a = 1/(1+10**((elos[b]-elos[a])/400))
                delta = 32*(int(row['winner_id'] == a)-expected_a)
                changes[a].append(delta)
                changes[b].append(-delta)
        for row in batch:
            for side, uid in enumerate(row['fighter_ids']):
                counts[uid] += 1
                histories[uid].append((source[row['fight_id']], side))
                earlier[uid] = day
                source_date_fighters.add((uid, day))
        for uid in {uid for row in batch for uid in row['fighter_ids']}:
            elos[uid] += sum(changes[uid])
            published = rating_keys.get((uid, day))
            if published is None:
                continue
            assert published['bouts'] == counts[uid]
            close(published['elo'], elos[uid], 'independent Elo', 1e-8)
            elo_checks += 1
            raw_metrics = weighted_metrics(histories[uid])
            for part in published['parts']:
                for key, value in part['metrics'].items():
                    close(value, elos[uid] if key == 'elo' else raw_metrics.get(key), 'weighted source input '+key, 1e-8)
                    raw_input_checks += 1
    assert rating_keys.keys() <= source_date_fighters
    reference = sorted(combined({p['key']: p['raw_score'] for p in row['parts']}, model['resume_weight'])[0]
                       for row in ratings if row['event_date'] < '2019-01-01')
    assert len(reference) == len(model['reference_values'])
    for reconstructed, saved in zip(reference, model['reference_values']):
        close(reconstructed, saved, 'pre-2019 empirical reference moment')
    # Independent operation ordering can differ at ~1e-14. Rank the saved full
    # precision values after checking their arithmetic, not rounded equivalents.
    reference = model['reference_values']
    assert manifest['display_curve']['reference_moments'] == len(reference)
    previous, peaks = {}, {}
    component_checks = 0
    for row in ratings:
        uid = row['fighter_id']
        raw = {p['key']: p['raw_score'] for p in row['parts']}
        for part in row['parts']:
            key = part['key']
            close(part['score'], 60+.39*part['raw_score'], 'linear component display')
            if key == 'resume':
                expected = 50*erfc(-(row['elo']-1500)/200/sqrt(2))
            else:
                available = row['coverage']['available_features'][key]
                numerator = sum(WEIGHTS[key][f]*row['coverage']['feature_z'][f] for f in available)
                denominator = sum(WEIGHTS[key][f] for f in available)
                assert all(-3 <= row['coverage']['feature_z'][f] <= 3 for f in available)
                expected = 50*erfc(-(numerator/denominator)/sqrt(2))
            close(part['raw_score'], expected, 'composite component formula')
            component_checks += 1
        value, skills = combined(raw, model['resume_weight'])
        close(row['raw_combined'], value, 'overall blend')
        close(row['skills_combined'], skills, 'ordered skills blend')
        grade, percentile = curve(row['raw_combined'], reference)
        assert row['curve_score'] == grade
        close(row['curve_percentile'], percentile, 'frozen empirical percentile')
        protected = min(grade, 88) if row['bouts'] < 5 else grade
        last = previous.get(uid)
        shown = protected if last is None else max(last-5, min(last+5, protected))
        if row['bouts'] < 5:
            shown = min(shown, 88)
        assert row['score'] == shown and row['provisional'] == (row['bouts'] < 4)
        assert row['small_history_adjustment'] == protected-grade
        assert row['change_adjustment'] == shown-protected
        assert row['change'] == (None if last is None else shown-last)
        peaks[uid] = max(peaks.get(uid, shown), shown)
        assert row['peak'] == peaks[uid]
        previous[uid] = shown
    matched = [r for r in prefights if r['winner_id'] is not None and min(r['prior_bouts']) > 0
               and all(all(part.get(key) is not None for key in PARTS) for part in r['parts'])]
    fit = [r for r in matched if '2012-01-01' <= r['event_date'] < '2016-01-01']
    selection = [r for r in matched if '2016-01-01' <= r['event_date'] < '2019-01-01']
    development = [r for r in matched if '2019-01-01' <= r['event_date'] < '2026-10-26']
    for candidate in model['selection_grid']:
        fitted, _, _ = log_score(fit, candidate['resume_weight'], candidate['fit']['slope'])
        close(fitted['nll'], candidate['fit']['training_nll'], 'earlier slope fit score')
        selected, _, _ = log_score(selection, candidate['resume_weight'], candidate['fit']['slope'])
        close(selected['nll'], candidate['selection']['nll'], 'earlier weight selection score')
    best = min(model['selection_grid'], key=lambda r: r['selection']['nll'])
    assert model['resume_weight'] == best['resume_weight']
    for method, weight, fit_name in [('candidate', model['resume_weight'], 'probability_fit'), ('resume_only', 1., 'resume_only_fit')]:
        fitted, _, _ = log_score(fit+selection, weight, model[fit_name]['slope'])
        close(fitted['nll'], model[fit_name]['training_nll'], 'refit earlier NLL')
        if not model[fit_name]['boundary']:
            close(fitted['gradient'], 0, 'positive symmetric slope score equation', 1e-5)
        measured, values, probabilities = log_score(development, weight, model[fit_name]['slope'])
        assert evaluation[method]['bouts'] == len(development)
        for key in ('nll', 'brier', 'ordering_accuracy_with_half_ties'):
            close(measured[key], evaluation[method][key], 'development '+method+' '+key)
        if method == 'candidate':
            own_losses, own_probabilities = values, probabilities
        else:
            reference_losses = values
    saved_development = records(snapshot/'development.jsonl')
    assert len(saved_development) == len(development)
    for source_row, saved, loss, p, ref_loss in zip(development, saved_development, own_losses, own_probabilities, reference_losses):
        assert all(saved[key] == value for key, value in source_row.items())
        close(saved['candidate_probability_a'], p, 'saved probability')
        close(saved['candidate_nll'], loss, 'saved logistic NLL')
        close(saved['resume_nll'], ref_loss, 'saved reference NLL')
    record = evaluation['track_record']
    assert (record['wins'], record['total'], record['ties_excluded'], record['unavailable_excluded']) == (
        display_wins, display_total, display_ties, display_unavailable)
    close(record['accuracy'], display_wins/display_total, 'higher-displayed-score track record')
    loader = load_snapshot(snapshot, database)
    serving_checks = 0
    for row in development:
        for side, uid in enumerate(row['fighter_ids']):
            served = loader.estimate(database, {'id': uid, 'before': row['event_date'], 'window': 0})
            parts = {part['key']: part['raw_score'] for part in served['parts']}
            for key in PARTS:
                close(parts[key], row['parts'][side][key], 'serving pre-date component')
            assert served['event_date'] < row['event_date'] and served['status'] == 'available'
            serving_checks += 1
    baseline_path = root/'data/processed/overall_rating_start_2026_11_04.json'
    baseline = json.loads(baseline_path.read_text())
    changed = sorted(name for name, value in baseline.items() if sha(name) != value)
    allowed = {str(root/'src/upset/research_app.py'), str(root/'src/upset/web/research.html')}
    assert set(changed) <= allowed, changed
    seed, _ = load_freeze(root/'data/processed/td_defense_prospective_freeze_2026_10_26_v1')
    assert evaluation['serving_eligible'] == (len(development) >= 500 and evaluation['candidate']['nll'] < log(2))
    assert evaluation['public_release'] is False and manifest['public_release'] is False
    assert config['freeze_before'] == '2019-01-01' and config['evaluation_before'] == '2026-10-26'
    # Recheck binding after the entire audit; no fitting or input mutations.
    for name, value in manifest['input_sha256'].items():
        assert sha(name) == value
    return {'verified': True, 'source_bouts': len(bouts), 'source_stat_sides': 2*len(bouts),
            'prefight_component_matches': feature_matches, 'independent_elo_states': elo_checks,
            'weighted_source_input_checks': raw_input_checks, 'component_formula_checks': component_checks,
            'dated_curve_cap_peak_checks': len(ratings), 'development_bouts': len(development),
            'independent_logistic_scores': 2*len(development), 'historical_serving_checks': serving_checks,
            'higher_displayed_winner_count': display_wins, 'higher_displayed_bouts': display_total,
            'preserved_baseline_files': len(baseline)-len(changed), 'authorized_viewer_changes': changed,
            'frozen_defense_seed_sides': len(seed), 'snapshot_manifest_sha256': sha(snapshot/'manifest.json'),
            'audit_source_sha256': sha(Path(__file__)), 'baseline_sha256': sha(baseline_path),
            'limits': 'Checks saved engine features/formulas and independent source exposures, not fresh predictive evidence or latent-skill validity.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--snapshot', type=Path, required=True)
    parser.add_argument('--database', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists() or args.output.resolve().is_relative_to(args.snapshot.resolve()):
        raise ValueError('Use a new audit output outside the immutable snapshot.')
    result = verify(args.snapshot, args.database)
    with args.output.open('x') as output:
        output.write(json.dumps(result, indent=2, sort_keys=True, allow_nan=False)+'\n')
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
