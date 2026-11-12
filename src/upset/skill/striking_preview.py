"""Gate-bound experimental mean snapshot; request time is lookup/arithmetic only."""

import argparse
import hashlib
import json
from collections import OrderedDict, defaultdict, deque
from datetime import date, timedelta
from math import exp, isfinite, log
from pathlib import Path
from threading import RLock

from upset.skill.striking_adapter import (
    digest,
    encoded,
    iso_date,
    read_sides,
    verify_hashes,
    write_artifact,
)

VERSION = 'experimental_striking_mean_v1'


def verify_gate(report):
    decision = report['decision']
    comparison = report['primary_point_comparisons']['sample_adjusted']['candidate_minus_reference_nll']
    interval = comparison['interval_95']
    bias = decision['mean_bias_percentage_points_predicted_minus_observed']
    if (decision.get('eligible_for_experimental_mean_preview') is not True
            or interval is None or not all(isfinite(v) for v in interval) or interval[1] >= 0
            or not isfinite(bias) or abs(bias) > 1
            or decision['material_point_regression_groups']
            or report['public_release'] is not False or report['opponent_adjusted'] is not False):
        raise ValueError('The study did not pass the separate experimental mean-preview checks.')
    for slices in report['subgroups'].values():
        for group in slices.values():
            if any(v['material_regression'] for v in group['point_comparisons'].values()):
                raise ValueError('Preview report contains a material point regression.')


def daily_intercepts(predictions, end):
    # This runs in the offline builder, never inside an HTTP request.
    from upset.skill.striking_rolling import fit_intercept
    usable = sorted([r for r in predictions if r['status'] == 'observed'
                     and r['recent_uncalibrated'] is not None], key=lambda r: r['event_date'])
    queue, pointer, values = deque(), 0, {}
    current, end_date = date(2019, 1, 1), date.fromisoformat(end)
    while current <= end_date:
        day, lower = current.isoformat(), (current-timedelta(days=730)).isoformat()
        while pointer < len(usable) and usable[pointer]['event_date'] < day:
            queue.append(usable[pointer])
            pointer += 1
        while queue and queue[0]['event_date'] < lower:
            queue.popleft()
        values[day] = {'intercept': fit_intercept(list(queue)), 'sides': len(queue),
                       'latest_event': queue[-1]['event_date'] if queue else None}
        current += timedelta(days=1)
    return values


def build(study, database, registry, before, output):
    if output.exists() or output.resolve().is_relative_to(database.parent.resolve()):
        raise ValueError('Use a new snapshot separate from the serving database.')
    report_path = study/'report.json'
    report = json.loads(report_path.read_text())
    verify_gate(report)
    verify_hashes(report['input_sha256'])
    for name, value in report['output_sha256'].items():
        if digest(study/name) != value:
            raise ValueError('Gate-passed study output hash differs.')
    sides, hashes, _ = read_sides(database, registry, before)
    from upset.skill.striking_adaptation import recent_predictions
    model = report['base_model']
    predictions = recent_predictions(sides, model['half_life_days'], model['strength'])
    intercepts = daily_intercepts(predictions, before)
    hashes.update({str(report_path.resolve()): digest(report_path), str(Path(__file__).resolve()): digest(Path(__file__))})
    observations = [{k: row[k] for k in ('fighter_id', 'event_date', 'status', 'landed', 'attempts')} for row in sides]
    body = ''.join(json.dumps(r, sort_keys=True)+'\n' for r in observations)
    intercept_body = encoded(intercepts)
    manifest = {'version': VERSION, 'experimental': True, 'validated_skill': False,
                'input_database': str(database.resolve()), 'database_sha256': digest(database),
                'before_exclusive': before, 'latest_event': max(r['event_date'] for r in sides),
                'model': model, 'gate_report': str(report_path.resolve()), 'gate_report_sha256': digest(report_path),
                'observations': len(sides), 'input_sha256': hashes,
                'output_sha256': {'observations.jsonl': hashlib.sha256(body.encode()).hexdigest(),
                                   'daily_intercepts.json': hashlib.sha256(intercept_body.encode()).hexdigest()}}
    verify_hashes(hashes)
    write_artifact(output, {'observations.jsonl': body, 'daily_intercepts.json': intercept_body,
                            'manifest.json': encoded(manifest)})
    return manifest


class ExperimentalPreview:
    def __init__(self, metadata, observations, intercepts):
        self.metadata, self.observations, self.intercepts = metadata, observations, intercepts
        self.database = Path(metadata['input_database']).resolve()
        self._states = OrderedDict()
        self._lock = RLock()

    def state(self, before):
        with self._lock:
            if before in self._states:
                self._states.move_to_end(before)
                return self._states[before]
        cutoff = date.fromisoformat(before)
        counts = defaultdict(lambda: [0., 0., 0, 0, 0])
        global_y = global_n = 0.
        half_life = self.metadata['model']['half_life_days']
        for row in self.observations:
            if row['event_date'] >= before:
                continue
            values = counts[row['fighter_id']]
            values[2] += 1
            if row['status'] not in ('observed', 'zero_attempts'):
                continue
            weight = 2**(-(cutoff-date.fromisoformat(row['event_date'])).days/half_life)
            y, n = row['landed'], row['attempts']
            values[0] += weight*y
            values[1] += weight*n
            values[3] += y
            values[4] += n
            global_y += weight*y
            global_n += weight*n
        result = dict(counts), global_y/global_n if global_n else None
        with self._lock:
            self._states[before] = result
            if len(self._states) > 16:
                self._states.popitem(last=False)
        return result

    def estimate(self, database, report):
        if Path(database).resolve() != self.database:
            raise ValueError('Experimental snapshot belongs to a different serving database.')
        before = iso_date(report['before'])
        base = {'experimental': True, 'opponent_adjusted': False, 'validated_skill': False,
                'method': 'Recent-weighted UFC career estimate', 'data_through': self.metadata['latest_event']}
        if report['window'] != 0:
            return {**base, 'status': 'career_only', 'message': 'Switch to Career to view the experimental estimate.'}
        if before < '2019-01-01' or before > self.metadata['before_exclusive'] or before not in self.intercepts:
            return {**base, 'status': 'unsupported_cutoff', 'message': 'No experimental estimate is available for this date.'}
        state, population = self.state(before)
        y, n, bouts, landed, attempts = state.get(report['id'], (0., 0., 0, 0, 0))
        if not attempts or population is None:
            return {**base, 'status': 'insufficient_history', 'message': 'More linked strike-attempt history is needed.'}
        k = self.metadata['model']['strength']
        p = min(1-1e-6, max(1e-6, (y+k*population)/(n+k)))
        log_odds = log(p)-log(1-p)+self.intercepts[before]['intercept']
        estimate = 1/(1+exp(-log_odds))
        return {**base, 'status': 'available', 'estimate': estimate, 'bouts': bouts,
                'attempts': attempts, 'raw_accuracy': landed/attempts, 'before': before}


def load_preview(folder, database):
    metadata = json.loads((folder/'manifest.json').read_text())
    if (metadata['version'] != VERSION or metadata['experimental'] is not True
            or metadata['validated_skill'] is not False or digest(database) != metadata['database_sha256']
            or Path(metadata['input_database']).resolve() != database.resolve()):
        raise ValueError('Experimental snapshot version/database differs.')
    verify_hashes(metadata['input_sha256'])
    report_path = Path(metadata['gate_report'])
    if digest(report_path) != metadata['gate_report_sha256']:
        raise ValueError('Experimental snapshot gate report differs.')
    report = json.loads(report_path.read_text())
    verify_gate(report)
    if metadata['model'] != report['base_model']:
        raise ValueError('Preview model differs from the gate-passed model.')
    for name, expected in metadata['output_sha256'].items():
        if not (folder/name).resolve().is_relative_to(folder.resolve()) or digest(folder/name) != expected:
            raise ValueError('Experimental snapshot output hash differs.')
    observations = [json.loads(line) for line in (folder/'observations.jsonl').read_text().splitlines()]
    if len(observations) != metadata['observations']:
        raise ValueError('Experimental snapshot row count differs.')
    for row in observations:
        if iso_date(row['event_date']) >= metadata['before_exclusive']:
            raise ValueError('Snapshot contains an observation beyond its cutoff.')
        if row['status'] in ('observed', 'zero_attempts') and (
                type(row['landed']) is not int or type(row['attempts']) is not int
                or not 0 <= row['landed'] <= row['attempts']):
            raise ValueError('Invalid experimental snapshot counts.')
    intercepts = json.loads((folder/'daily_intercepts.json').read_text())
    for day, record in intercepts.items():
        if (not -.5 <= record['intercept'] <= .5 or record['latest_event'] is not None
                and record['latest_event'] >= iso_date(day)):
            raise ValueError('Invalid/future experimental calibration lookup.')
    return ExperimentalPreview(metadata, observations, intercepts)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--study', type=Path, required=True)
    parser.add_argument('--database', type=Path, required=True)
    parser.add_argument('--registry', type=Path, required=True)
    parser.add_argument('--before', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print(encoded(build(args.study, args.database, args.registry, args.before, args.output)))


if __name__ == '__main__':
    main()
