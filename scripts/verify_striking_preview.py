"""Independently audit saved repair scores, serving parity and preserved inputs."""

import json
from pathlib import Path

import numpy as np
from scipy.special import betaln, gammaln

from upset.skill.defense_prospective import load_freeze
from upset.skill.striking_adapter import digest, verify_hashes
from upset.skill.striking_preview import load_preview


def verify(root):
    processed = root/'data/processed'
    baseline = json.loads((processed/'striking_adaptation_start_2026_11_04.json').read_text())
    changed = {path for path, value in baseline.items() if digest(Path(path)) != value}
    allowed = {str(root/name) for name in ('src/upset/research_app.py', 'src/upset/web/research.html')}
    assert changed == allowed, changed
    for path in changed:
        original = root/'backups/experimental-striking-preview-20261104-v1/files'/Path(path).relative_to(root)
        assert digest(original) == baseline[path]
    seed, _ = load_freeze(processed/'td_defense_prospective_freeze_2026_10_26_v1')
    artifacts, pmf_checks, enumeration_checks, max_error = {}, 0, 0, 0.
    for stem in ('striking_adaptation', 'striking_rolling'):
        folder = processed/(stem+'_2026_11_04_v1')
        report = json.loads((folder/'report.json').read_text())
        verify_hashes(report['input_sha256'])
        for name, value in report['output_sha256'].items():
            assert digest(folder/name) == value
        rows = [json.loads(line) for line in (folder/'calibration_rows.jsonl').read_text().splitlines()]
        assert len(rows) == 7028
        keys = [(r['fight_id'], r['fighter_id']) for r in rows]
        assert len(keys) == len(set(keys))
        predictions = [json.loads(line) for line in (folder/'predictions.jsonl').read_text().splitlines()]
        lookup = {(r['fight_id'], r['fighter_id']): r for r in predictions}
        totals = {}
        for i, row in enumerate(rows):
            y, n = row['landed'], row['attempts']
            source = lookup[row['fight_id'], row['fighter_id']]
            assert (y, n, row['event_date']) == (source['landed'], source['attempts'], source['event_date'])
            coefficient = gammaln(n+1)-gammaln(y+1)-gammaln(n-y+1)
            for method, record in row['methods'].items():
                p, c = record['probability'], record['concentration']
                a, b = p*c, (1-p)*c
                nll = -coefficient-betaln(y+a, n-y+b)+betaln(a, b)
                max_error = max(max_error, abs(nll-record['nll']))
                totals.setdefault(method, []).append(nll)
                pmf_checks += 1
                if i % 111 == 0:
                    k = np.arange(n+1)
                    mass = np.exp(gammaln(n+1)-gammaln(k+1)-gammaln(n-k+1)
                                  +betaln(k+a, n-k+b)-betaln(a, b))
                    assert abs(mass.sum()-1) < 1e-8
                    cdf = mass.cumsum()
                    for level, interval in record['ranges'].items():
                        lo, hi, tail = interval['lower'], interval['upper'], (1-float(level))/2
                        assert cdf[lo] >= tail-1e-8 and (lo == 0 or cdf[lo-1] < tail+1e-8)
                        assert cdf[hi] >= 1-tail-1e-8 and (hi == 0 or cdf[hi-1] < 1-tail+1e-8)
                        assert abs(mass[lo:hi+1].sum()-interval['expected_mass']) < 1e-8
                    enumeration_checks += 1
        assert max_error < 1e-8
        for name, values in totals.items():
            assert abs(np.mean(values)-report['primary_distributions'][name]['mean_predictive_nll']) < 1e-10
        for name, scores in report['point_scores'].items():
            values = []
            for row in rows:
                p = np.clip(lookup[row['fight_id'], row['fighter_id']][name], 1e-6, 1-1e-6)
                y, n = row['landed'], row['attempts']
                values.append(-gammaln(n+1)+gammaln(y+1)+gammaln(n-y+1)-y*np.log(p)-(n-y)*np.log1p(-p))
            assert abs(np.mean(values)-scores['binomial_nll']) < 1e-10
        artifacts[stem] = {p.name: digest(p) for p in folder.iterdir() if p.is_file()}
    database = processed/'research_2026_11_03_v1/upset.sqlite'
    snapshot = processed/'experimental_striking_preview_2026_11_04_v1'
    preview = load_preview(snapshot, database)
    max_parity_error = 0.
    for row in rows:
        pred = lookup[row['fight_id'], row['fighter_id']]
        assert pred['calibration_latest_date'] is None or pred['calibration_latest_date'] < pred['event_date']
        estimate = preview.estimate(database, {'id': row['fighter_id'], 'before': row['event_date'], 'window': 0})
        max_parity_error = max(max_parity_error, abs(estimate['estimate']-pred['recent_calibrated']))
    assert max_parity_error < 1e-10
    artifacts['preview'] = {p.name: digest(p) for p in snapshot.iterdir() if p.is_file()}
    return {'verified': True, 'independent_pmf_checks': pmf_checks,
            'enumerated_distributions': enumeration_checks, 'maximum_pmf_error': float(max_error),
            'historical_serving_parity_checks': len(rows), 'maximum_serving_error': max_parity_error,
            'preserved_baseline_files': len(baseline)-len(changed),
            'authorized_site_changes': sorted(changed), 'frozen_defense_seed_sides': len(seed),
            'artifact_sha256': artifacts, 'audit_source_sha256': digest(Path(__file__))}


if __name__ == '__main__':
    result = verify(Path(__file__).resolve().parents[1])
    output = Path('data/processed/striking_preview_verification_2026_11_04.json')
    with output.open('x') as stream:
        stream.write(json.dumps(result, indent=2, sort_keys=True)+'\n')
    print(json.dumps({k: v for k, v in result.items() if k != 'artifact_sha256'}, indent=2))
