"""Audit saved validation artifacts with independent PMF arithmetic and histories."""

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
from scipy.special import betaln, gammaln

from upset.skill.defense_prospective import load_freeze
from upset.skill.striking_adapter import digest, load_adapter, verify_hashes


def verify(folder, adapter, baseline, freeze):
    report = json.loads((folder/'report.json').read_text())
    verify_hashes(report['input_sha256'])
    for name, expected in report['output_sha256'].items():
        if digest(folder/name) != expected:
            raise ValueError('Validation artifact hash mismatch: '+name)
    sides, metadata, _ = load_adapter(adapter)
    predictions = [json.loads(line) for line in (folder/'predictions.jsonl').read_text().splitlines()]
    expected = {(r['fight_id'], r['fighter_id']) for r in predictions
                if r['event_date'] >= '2019-01-01' and r['status'] == 'observed'
                and all(r[m] is not None for m in ('raw_career', 'raw_last5', 'career_jeffreys',
                                                  'last5_jeffreys', 'population_mean', 'sample_adjusted'))}
    rows = [json.loads(line) for line in (folder/'calibration_rows.jsonl').read_text().splitlines()]
    actual = [(r['fight_id'], r['fighter_id']) for r in rows]
    if len(actual) != len(set(actual)) or set(actual) != expected:
        raise ValueError('Primary calibration support differs from frozen predictions.')
    source = {(r['fight_id'], r['fighter_id']): r for r in sides}
    maximum_error, checked, enumerated = 0., 0, 0
    selected = set(np.linspace(0, len(rows)-1, min(64, len(rows)), dtype=int))
    totals = defaultdict(list)
    for index, row in enumerate(rows):
        n, y = row['attempts'], row['landed']
        original = source[row['fight_id'], row['fighter_id']]
        if (n, y, row['event_date']) != (original['attempts'], original['landed'], original['event_date']):
            raise ValueError('Saved outcome differs from source adapter.')
        coefficient = gammaln(n+1)-gammaln(y+1)-gammaln(n-y+1)
        for name, record in row['methods'].items():
            p = record['probability']
            if name.startswith('binomial:'):
                nll = -coefficient-y*np.log(p)-(n-y)*np.log1p(-p)
            else:
                c = record['concentration']
                a, b = p*c, (1-p)*c
                nll = -coefficient-betaln(y+a, n-y+b)+betaln(a, b)
            maximum_error = max(maximum_error, abs(float(nll)-record['nll']))
            totals[name].append(record['nll'])
            checked += 1
            if index in selected:
                k = np.arange(n+1)
                log_mass = gammaln(n+1)-gammaln(k+1)-gammaln(n-k+1)
                if name.startswith('binomial:'):
                    log_mass += k*np.log(p)+(n-k)*np.log1p(-p)
                else:
                    log_mass += betaln(k+a, n-k+b)-betaln(a, b)
                mass = np.exp(log_mass)
                if not np.isclose(mass.sum(), 1, atol=1e-8, rtol=0):
                    raise ValueError('Enumerated probability mass does not sum to one.')
                cumulative = mass.cumsum()
                for level, interval in record['ranges'].items():
                    tail = (1-float(level))/2
                    lo, hi = interval['lower'], interval['upper']
                    if (cumulative[lo] < tail-1e-8 or lo > 0 and cumulative[lo-1] >= tail+1e-8
                            or cumulative[hi] < 1-tail-1e-8
                            or hi > 0 and cumulative[hi-1] >= 1-tail+1e-8
                            or not np.isclose(mass[lo:hi+1].sum(), interval['expected_mass'], atol=1e-8, rtol=0)):
                        raise ValueError('Saved predictive range or mass differs from enumeration.')
                enumerated += 1
    if maximum_error > 1e-8:
        raise ValueError('Independent NLL formula differs.')
    for name, values in totals.items():
        if not np.isclose(np.mean(values), report['primary_predictive_distributions'][name]['mean_predictive_nll'],
                          atol=1e-10, rtol=0):
            raise ValueError('Saved score aggregate differs.')
    pairs = [json.loads(line) for line in (folder/'repeatability_pairs.jsonl').read_text().splitlines()]
    histories = defaultdict(list)
    for row in sorted(sides, key=lambda r: (r['event_date'], r['fight_id'], r['fighter_id'])):
        histories[row['fighter_id']].append(row)
    eligible = Counter()
    pair_keys = set()
    for pair in pairs:
        uid, half = pair['fighter_id'], pair['bouts_per_half']
        if (uid, half) in pair_keys:
            raise ValueError('Duplicate repeatability pair.')
        pair_keys.add((uid, half))
        history = histories[uid]
        if (pair['first_fight_ids'] != [r['fight_id'] for r in history[:half]]
                or pair['second_fight_ids'] != [r['fight_id'] for r in history[half:2*half]]
                or not set(pair['first_fight_ids']).isdisjoint(pair['second_fight_ids'])
                or pair['first_end'] >= pair['second_start']
                or len(history) > 2*half and history[2*half-1]['event_date'] == history[2*half]['event_date']):
            raise ValueError('Repeatability window is not a disjoint, complete-date prefix.')
        for prefix in ('first', 'second'):
            block = [source[fid, uid] for fid in pair[prefix+'_fight_ids']]
            if (len(block) != half or any(r['status'] not in ('observed', 'zero_attempts') for r in block)
                    or sum(r['landed'] for r in block) != pair[prefix+'_landed']
                    or sum(r['attempts'] for r in block) != pair[prefix+'_attempts']):
                raise ValueError('Repeatability selected counts differ.')
        primary = min(pair['first_attempts'], pair['second_attempts']) >= 100
        if pair['primary_100_attempts_per_half'] != primary:
            raise ValueError('Repeatability exposure flag differs.')
        eligible[half] += primary
    for half, group in report['repeatability'].items():
        if (sum(group['attrition_mutually_exclusive'].values()) != len(histories)
                or eligible[int(half)] != group['primary_100_attempts_per_half']['fighters']):
            raise ValueError('Repeatability attrition/size mismatch.')
    preservation = json.loads(baseline.read_text())
    verify_hashes(preservation)
    seed, _ = load_freeze(freeze)
    return {'verified': True, 'primary_sides': len(rows), 'independent_log_pmf_checks': checked,
            'maximum_log_pmf_error': maximum_error, 'enumerated_distributions_checked': enumerated,
            'disjoint_repeatability_pairs_audited': len(pairs), 'preserved_files': len(preservation),
            'frozen_defense_seed_sides': len(seed), 'before_exclusive': metadata['before_exclusive'],
            'report_sha256': digest(folder/'report.json'), 'audit_source_sha256': digest(Path(__file__))}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--validation', type=Path, required=True)
    parser.add_argument('--adapter', type=Path, required=True)
    parser.add_argument('--baseline', type=Path, required=True)
    parser.add_argument('--defense-freeze', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError('Use a new immutable audit output.')
    result = verify(args.validation, args.adapter, args.baseline, args.defense_freeze)
    result['artifact_sha256'] = {str(p): hashlib.sha256(p.read_bytes()).hexdigest()
                                for p in args.validation.iterdir() if p.is_file()}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x') as output:
        output.write(json.dumps(result, indent=2, sort_keys=True)+'\n')
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
