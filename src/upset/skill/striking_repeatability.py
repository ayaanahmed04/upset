"""Disjoint, complete-count striking windows and descriptive repeatability."""

from collections import Counter, defaultdict

import numpy as np
from scipy.stats import rankdata

HALVES = (2, 3, 5, 8, 10)
SEED = 20261104
REPLICATES = 1000


def correlation(x, y, ranked=False):
    x, y = np.asarray(x, dtype=float), np.asarray(y, dtype=float)
    if (x.shape != y.shape or x.ndim != 1 or not np.isfinite(x).all()
            or not np.isfinite(y).all()):
        raise ValueError('Correlations require paired finite vectors.')
    if len(x) < 3 or np.ptp(x) == 0 or np.ptp(y) == 0:
        return None
    if ranked:
        x, y = rankdata(x), rankdata(y)
    return float(np.corrcoef(x, y)[0, 1])


def summarize_pairs(pairs, replicates=REPLICATES):
    if type(replicates) is not int or replicates < 1:
        raise ValueError('Require positive bootstrap replicates.')
    x = np.array([p['first_rate'] for p in pairs])
    y = np.array([p['second_rate'] for p in pairs])
    result = {'fighters': len(pairs), 'first_attempts': sum(p['first_attempts'] for p in pairs),
              'second_attempts': sum(p['second_attempts'] for p in pairs),
              'seed': SEED, 'replicates': replicates}
    rng = np.random.default_rng(SEED)
    indices = rng.integers(0, len(pairs), size=(replicates, len(pairs))) if pairs else []
    for name, ranked in (('pearson', False), ('spearman', True)):
        estimate = correlation(x, y, ranked)
        values = [correlation(x[i], y[i], ranked) for i in indices] if estimate is not None else []
        values = [v for v in values if v is not None and np.isfinite(v)]
        result[name] = {'correlation': estimate,
                        'fighter_bootstrap_95_interval': np.quantile(values, [.025, .975]).tolist()
                        if values else None, 'finite_replicates': len(values)}
    enough = (len(pairs) >= 50 and all(result[m]['correlation'] is not None
              and result[m]['finite_replicates'] >= .9 * replicates
              for m in ('pearson', 'spearman')))
    result['status'] = 'descriptive_sized_group' if enough else 'inconclusive'
    return result


def reliability(rows, replicates=REPLICATES):
    """Never skip missing/zero bouts to construct seemingly complete histories."""
    fighters = defaultdict(list)
    keys = set()
    for row in sorted(rows, key=lambda r: (r['event_date'], r['fight_id'], r['fighter_id'])):
        key = row['fight_id'], row['fighter_id']
        if key in keys:
            raise ValueError('Duplicate repeatability side.')
        keys.add(key)
        fighters[row['fighter_id']].append(row)
    results, all_pairs = {}, []
    for half in HALVES:
        counts = Counter()
        pairs = []
        for uid, history in sorted(fighters.items()):
            if len(history) < 2 * half:
                counts['fewer_than_2m_recorded_bouts'] += 1
                continue
            first, second = history[:half], history[half:2 * half]
            if first[-1]['event_date'] == second[0]['event_date']:
                counts['same_date_split_boundary'] += 1
                continue
            if len(history) > 2 * half and second[-1]['event_date'] == history[2 * half]['event_date']:
                counts['same_date_end_boundary'] += 1
                continue
            if any(r['status'] not in ('observed', 'zero_attempts') for r in first + second):
                counts['missing_or_invalid_selected_counts'] += 1
                continue
            totals = [(sum(r['landed'] for r in block), sum(r['attempts'] for r in block))
                      for block in (first, second)]
            if any(n == 0 for _, n in totals):
                counts['zero_exposure_in_a_half'] += 1
                continue
            (y1, n1), (y2, n2) = totals
            divisions = {r['division'] for r in first + second}
            primary = min(n1, n2) >= 100
            pair = {'fighter_id': uid, 'bouts_per_half': half,
                    'first_fight_ids': [r['fight_id'] for r in first],
                    'second_fight_ids': [r['fight_id'] for r in second],
                    'first_start': first[0]['event_date'], 'first_end': first[-1]['event_date'],
                    'second_start': second[0]['event_date'], 'second_end': second[-1]['event_date'],
                    'first_landed': y1, 'first_attempts': n1, 'first_rate': y1 / n1,
                    'second_landed': y2, 'second_attempts': n2, 'second_rate': y2 / n2,
                    'primary_100_attempts_per_half': primary,
                    'stable_division': next(iter(divisions))
                    if len(divisions) == 1 and None not in divisions else None}
            pairs.append(pair)
            counts['eligible_primary' if primary else 'below_100_attempts_in_a_half'] += 1
        primary = [p for p in pairs if p['primary_100_attempts_per_half']]
        slices = {}
        for division in sorted({p['stable_division'] for p in primary if p['stable_division']}):
            group = [p for p in primary if p['stable_division'] == division]
            slices[division] = summarize_pairs(group, replicates) if len(group) >= 50 else {
                'fighters': len(group), 'status': 'inconclusive_thin_group'}
        if sum(counts.values()) != len(fighters):
            raise ValueError('Repeatability attrition accounting failed.')
        results[str(half)] = {'recorded_bouts_per_half': half, 'all_fighters': len(fighters),
                              'attrition_mutually_exclusive': dict(counts),
                              'primary_100_attempts_per_half': summarize_pairs(primary, replicates),
                              'secondary_positive_attempts_per_half': summarize_pairs(pairs, replicates),
                              'stable_division_slices': slices}
        all_pairs.extend(pairs)
    return results, all_pairs
