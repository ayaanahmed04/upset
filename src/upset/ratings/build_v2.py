"""Offline experimental v2 comparison; never modifies a v1 snapshot."""

import argparse
import hashlib
import json
from bisect import bisect_left, bisect_right
from collections import Counter, defaultdict
from datetime import UTC, datetime
from math import log
from pathlib import Path

import numpy as np

from upset.ratings import build as v1
from upset.ratings import data, engine, engine_v2, serving, serving_v2
from upset.skill.striking_adapter import digest, encoded, verify_hashes, write_artifact

VERSION = serving_v2.VERSION
START, END = '2019-01-01', '2026-10-26'
WEIGHT = .5
SEED = 20261105
GAETHJE = '678d50b2-742c-44e4-b833-d560794ba84c'


def read_rows(path):
    with path.open() as stream:
        for line in stream:
            yield json.loads(line)


def materialize(snapshots, bouts, *, hold=True):
    fights = defaultdict(list)
    for bout in bouts:
        for uid in bout['fighter_ids']:
            fights[bout['event_date'], uid].append(bout)
    reference = sorted(value for row in snapshots if row['event_date'] < START
                       and (value := v1.combine(row['raw_parts'], WEIGHT)[0]) is not None)
    if len(reference) < 100:
        raise ValueError('Insufficient fixed reference history.')
    last, output = {}, []
    for row in snapshots:
        combined, skills = v1.combine(row['raw_parts'], WEIGHT)
        if combined is None:
            continue
        uid, day = row['fighter_id'], row['event_date']
        p = (bisect_left(reference, combined)+bisect_right(reference, combined))/(2*len(reference))
        unrounded = float(np.interp(p, [a[0] for a in v1.ANCHORS], [a[1] for a in v1.ANCHORS]))
        grade = serving_v2.curve_grade(unrounded, p)
        dated = fights[day, uid]
        outcomes = ['other' if b['winner_id'] is None else 'win' if b['winner_id'] == uid else 'loss' for b in dated]
        prior = last.get(uid)
        adjusted = serving_v2.display_adjustments(grade, row['bouts'], outcomes, prior['score'] if prior else None, hold=hold)
        shown = adjusted['score']
        parts = []
        for key, label in zip(v1.KEYS, v1.LABELS):
            names = v1.PART_METRICS[key] + (['ko_wins_per_bout'] if key == 'striking' else [])
            values = {name: row['elo'] if name == 'elo' else row['metrics'].get(name) for name in names}
            raw = row['raw_parts'][key]
            parts.append({'key': key, 'label': label, 'score': 60+.39*raw, 'raw_score': raw, 'metrics': values})
        current = {'fighter_id': uid, 'event_date': day, 'bouts': row['bouts'], 'division': row['division'],
                   'provisional': row['bouts'] < 4, 'elo': row['elo'], 'parts': parts,
                   'raw_combined': combined, 'skills_combined': skills, 'curve_score': grade,
                   'curve_percentile': p, 'curve_unrounded': unrounded, 'coverage': row['coverage'],
                   'fight_ids': [b['fight_id'] for b in dated], 'last_outcomes': outcomes,
                   **adjusted, 'peak': max(shown, prior['peak']) if prior else shown,
                   'change': shown-prior['score'] if prior else None}
        output.append(current)
        last[uid] = current
    return output, reference


def policy(rows, names):
    counts, first, latest = Counter(), {}, {}
    for row in rows:
        uid, day = row['fighter_id'], row['event_date']
        previous = latest.get(uid)
        latest[uid] = row
        if day < START:
            continue
        if row['score'] == 99:
            first.setdefault(uid, day)
            counts['display_99_states'] += 1
            counts['held_99_states'] += bool(row.get('outcome_hold'))
        outcomes = row['last_outcomes']
        if not previous or not outcomes or outcomes[0] not in ('win', 'loss') or len(set(outcomes)) != 1:
            continue
        result, change = outcomes[0], row['score']-previous['score']
        wrong = change < 0 if result == 'win' else change > 0
        counts[result+'_updates'] += 1
        counts[result+'_wrong_direction'] += wrong
        counts['wrong_direction_updates'] += wrong
        counts['decisive_updates'] += 1
        counts['full_five_moves'] += abs(change) == 5
        counts['actual_limit_applications'] += bool(row['change_adjustment'])
        counts['win_holds'] += row.get('outcome_hold') == 'held_after_win'
        counts['loss_holds'] += row.get('outcome_hold') == 'held_after_loss'
        if previous['bouts'] >= 10:
            counts['ten_plus_updates'] += 1
            counts['ten_plus_full_five_moves'] += abs(change) == 5
            counts['ten_plus_actual_limit_applications'] += bool(row['change_adjustment'])
    return {**dict(counts), 'wrong_direction_updates': counts['wrong_direction_updates'],
            'named_99_fighters': [{'fighter_id': uid, 'name': names[uid], 'first_99_in_window': day}
                                  for uid, day in sorted(first.items(), key=lambda item: (item[1], names[item[0]]))]}


def display_rows(bouts, versions, names):
    indexes = {}
    for version, rows in versions.items():
        histories = defaultdict(list)
        for row in rows:
            histories[row['fighter_id']].append((row['event_date'], row['score']))
        indexes[version] = histories, {uid: [d for d, _ in h] for uid, h in histories.items()}
    for row in bouts:
        day, ids = row['event_date'], row['fighter_ids']
        if not START <= day < END or row['winner_id'] is None:
            continue
        result = {key: row[key] for key in ('fight_id', 'event_date', 'fighter_ids', 'winner_id')}
        result['fighter_names'] = [names[uid] for uid in ids]
        for version, (histories, dates) in indexes.items():
            selected = [histories[uid][i] if (i := bisect_left(dates.get(uid, []), day)-1) >= 0 else (None, None) for uid in ids]
            result[version] = {'state_dates': [p[0] for p in selected], 'grades': [p[1] for p in selected]}
        yield result


def display_result(rows, version):
    tally = Counter()
    for row in rows:
        a, b = row[version]['grades']
        if None in (a, b):
            tally['unavailable'] += 1
        elif a == b:
            tally['ties'] += 1
        else:
            tally['total'] += 1
            tally['wins'] += row['winner_id'] == row['fighter_ids'][int(b > a)]
    return {'wins': tally['wins'], 'total': tally['total'],
            'accuracy': tally['wins']/tally['total'] if tally['total'] else None,
            'ties_excluded': tally['ties'], 'unavailable_excluded': tally['unavailable'],
            'from_date': START, 'before_exclusive': END,
            'label': 'Retrospective development track record; not fresh future validation.'}


def paired_dates(rows, differences):
    groups = defaultdict(lambda: [0., 0])
    for row, delta in zip(rows, differences):
        entry = groups[row['event_date']]
        entry[0] += float(delta)
        entry[1] += 1
    values = np.array([groups[day] for day in sorted(groups)])
    rng = np.random.default_rng(SEED)
    sampled = values[rng.integers(len(values), size=(1000, len(values)))].sum(axis=1)
    return {'difference': float(np.mean(differences)), 'interval_95': np.quantile(sampled[:, 0]/sampled[:, 1], [.025, .975]).tolist(),
            'clusters': len(values), 'replicates': 1000, 'seed': SEED}


def build(database, before, baseline, protocol, output):
    if output.exists() or output.resolve().is_relative_to(database.parent.resolve()):
        raise ValueError('Use a new output directory outside the serving database folder.')
    old_manifest = json.loads((baseline/'manifest.json').read_text())
    if old_manifest['version'] != serving.VERSION or digest(database) != old_manifest['database_sha256']:
        raise ValueError('V1 must bind the same reviewed data.')
    hashes = dict(old_manifest['input_sha256'])
    for name, value in old_manifest['output_sha256'].items():
        hashes[str((baseline/name).resolve())] = value
    for path in (Path(__file__), Path(data.__file__), Path(engine.__file__), Path(engine_v2.__file__),
                 Path(serving.__file__), Path(serving_v2.__file__), protocol, baseline/'manifest.json'):
        hashes[str(path.resolve())] = digest(path)
    verify_hashes(hashes)
    bouts, source = data.load_bouts(database, before)
    names = source['fighter_labels']
    print(f'Replaying {len(bouts):,} recorded bouts under the declared v2 rules', flush=True)
    snapshots, prefights = engine_v2.replay(bouts)
    match = v1.eligible(prefights)
    training = [r for r in match if '2012-01-01' <= r['event_date'] < START]
    slope = v1.fit_slope(training, WEIGHT)
    matched = [r for r in match if START <= r['event_date'] < END]
    prior_eval = json.loads((baseline/'evaluation.json').read_text())
    old_dev = list(read_rows(baseline/'development.jsonl'))
    identity = ('fight_id', 'event_date', 'fighter_ids', 'winner_id')
    if [tuple(r[k] for k in identity) for r in matched] != [tuple(r[k] for k in identity) for r in old_dev]:
        raise ValueError('V2 changed the frozen matched development support.')
    candidate, losses, probabilities = v1.score(matched, WEIGHT, slope['slope'])
    old_losses = np.array([r['candidate_nll'] for r in old_dev])
    if not np.isclose(old_losses.mean(), prior_eval['candidate']['nll'], atol=1e-12, rtol=0):
        raise ValueError('V1 scores do not reproduce.')
    rows, reference = materialize(snapshots, bouts)
    unheld, _ = materialize(snapshots, bouts, hold=False)
    old_rows = list(read_rows(baseline/'ratings.jsonl'))
    versions = {'v1': old_rows, 'v2': rows, 'v2_no_holds': unheld}
    displays = list(display_rows(prefights, versions, names))
    records = {key: display_result(displays, key) for key in versions}
    if records['v1'] != prior_eval['track_record']:
        raise ValueError('Frozen displayed track record did not reproduce.')
    common = [r for r in displays if all(None not in r[k]['grades'] and len(set(r[k]['grades'])) == 2 for k in ('v1', 'v2'))]
    common_scores = {key: display_result(common, key) for key in ('v1', 'v2')}
    diff = common_scores['v2']['accuracy']-common_scores['v1']['accuracy'] if common else None
    nll_comparison = paired_dates(matched, losses-old_losses)
    policies = {key: policy(value, names) for key, value in versions.items()}
    print('Checking real-data prefix invariance and all display states', flush=True)
    prefix = [b for b in bouts if b['event_date'] < '2024-01-01']
    prefix_states, prefix_prefights = engine_v2.replay(prefix)
    prefix_rows, prefix_reference = materialize(prefix_states, prefix)
    chronology = (prefix_rows == [r for r in rows if r['event_date'] < '2024-01-01']
                  and prefix_prefights == [r for r in prefights if r['event_date'] < '2024-01-01']
                  and prefix_reference == reference
                  and all(all(day is None or day < r['event_date'] for day in r['prior_snapshot_dates']) for r in prefights))
    metadata = {'before_exclusive': before, 'latest_event': source['latest_event']}
    previous = {}
    for row in rows:
        uid = row['fighter_id']
        serving_v2._validate_row(row, metadata, previous.get(uid))
        previous[uid] = row
    engineering = chronology and policies['v2']['wrong_direction_updates'] == 0
    eligible = (engineering and len(matched) >= 500 and candidate['nll'] < log(2)
                and nll_comparison['difference'] <= .010 and len(common) >= 500 and diff >= -.02)
    comparison = {'matched_bouts': len(matched), 'v1_nll': prior_eval['candidate']['nll'],
                  'nll_difference': nll_comparison['difference'], 'paired_date_nll': nll_comparison,
                  'v1_brier': prior_eval['candidate']['brier'],
                  'common_display': {'bouts': len(common), 'accuracy_difference': diff, **common_scores}}
    subgroups = defaultdict(list)
    division = {b['fight_id']: b['division'] for b in bouts}
    for i, row in enumerate(matched):
        subgroups['year', row['event_date'][:4]].append(i)
        subgroups['division', division[row['fight_id']] or 'Unknown'].append(i)
        subgroups['experience', '1–3 prior' if min(row['prior_bouts']) < 4 else '4+ prior'].append(i)
    groups = defaultdict(dict)
    for (kind, label), indices in sorted(subgroups.items()):
        groups[kind][label] = {'bouts': len(indices), 'v2_nll': float(losses[indices].mean()),
                               'v1_nll': float(old_losses[indices].mean())}
    case = {key: [r for r in value if r['fighter_id'] == GAETHJE and r['event_date'] >= '2026-01-24'] for key, value in versions.items()}
    evaluation = {'version': VERSION, 'experimental': True, 'validated': False, 'public_release': False,
                  'evaluation_label': 'Previously inspected historical development evidence; not future validation.',
                  'engineering_checks_passed': engineering, 'serving_eligible': eligible, 'candidate': candidate,
                  'comparison_to_v1': comparison, 'track_record': records['v2'], 'display_records': records,
                  'policy': policies['v2'], 'policies': policies, 'subgroups': dict(groups),
                  'chronology': {'passed': chronology, 'later_bouts_removed': len(bouts)-len(prefix),
                                 'prefix_ratings': len(prefix_rows), 'prefix_prefights': len(prefix_prefights)},
                  'gaethje_example': case}
    model = {'resume_weight': WEIGHT, 'skill_weights': [.5, .3, .2], 'training_before': START,
             'probability_fit': slope, 'within_part_weights': 'Declared v2; KO/TKO win feature weight .10 in Striking'}
    dev = [{**r, 'fighter_names': [names[uid] for uid in r['fighter_ids']],
            'v2_probability_a': float(p), 'v2_nll': float(loss), 'v1_nll': float(old)}
           for r, p, loss, old in zip(matched, probabilities, losses, old_losses)]
    def jsonl(values):
        return ''.join(json.dumps(row, sort_keys=True, allow_nan=False)+'\n' for row in values)

    files = {'ratings.jsonl': jsonl(rows), 'development.jsonl': jsonl(dev), 'displayed_comparisons.jsonl': jsonl(displays),
             'prefights.jsonl': jsonl(prefights), 'evaluation.json': encoded(evaluation),
             'model.json': encoded({**model, 'reference_values': reference, 'anchors': v1.ANCHORS}),
             'protocol.md': protocol.read_text()}
    manifest = {'version': VERSION, 'experimental': True, 'validated': False, 'public_release': False,
                'created_at_utc': datetime.now(UTC).isoformat(), 'input_database': str(database.resolve()),
                'database_sha256': digest(database), **metadata, 'input_sha256': hashes,
                'output_sha256': {name: hashlib.sha256(body.encode()).hexdigest() for name, body in files.items()},
                'display_curve': {'reference_before': START, 'reference_moments': len(reference), 'strict_99_percentile': .9999},
                'model': model, 'source_metadata': source}
    verify_hashes(hashes)
    files['manifest.json'] = encoded(manifest)
    write_artifact(output, files)
    return evaluation


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('database', 'baseline', 'output'):
        parser.add_argument('--'+name, type=Path, required=True)
    parser.add_argument('--before', required=True)
    parser.add_argument('--protocol', type=Path, default=Path('docs/OVERALL_RATING_PROTOCOL_V2.md'))
    a = parser.parse_args()
    result = build(a.database, a.before, a.baseline, a.protocol, a.output)
    print(encoded({key: result[key] for key in ('serving_eligible', 'candidate', 'comparison_to_v1', 'track_record', 'chronology')}))


if __name__ == '__main__':
    main()
