"""Verify that removing later bouts cannot change a frozen rating model's past.

Replays dated features and applies the already selected pre-2019 model. It does
not select weights, fit slopes, alter priors or inspect new model candidates.
"""

import argparse
import hashlib
import json
from datetime import date
from pathlib import Path

from upset.ratings.build import make_ratings
from upset.ratings.data import load_bouts
from upset.ratings.engine import replay


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_rows(path):
    return [json.loads(line) for line in path.read_text().splitlines()]


def verify(snapshot, database, before):
    if date.fromisoformat(before).isoformat() != before or before <= '2019-01-01':
        raise ValueError('Use an ISO prefix cutoff later than the frozen model period.')
    manifest = json.loads((snapshot/'manifest.json').read_text())
    if before >= manifest['before_exclusive']:
        raise ValueError('The prefix must exclude part of the full snapshot.')
    inputs = dict(manifest['input_sha256'])
    inputs[str((snapshot/'manifest.json').resolve())] = digest(snapshot/'manifest.json')
    inputs[str(Path(__file__).resolve())] = digest(Path(__file__))
    for name, expected in manifest['output_sha256'].items():
        path = snapshot/name
        if not path.resolve().is_relative_to(snapshot.resolve()) or digest(path) != expected:
            raise ValueError('Frozen output hash differs: '+name)
        inputs[str(path.resolve())] = expected
    for path, expected in inputs.items():
        if digest(path) != expected:
            raise ValueError('Input source/hash differs: '+path)
    bouts, metadata = load_bouts(database, manifest['before_exclusive'])
    if metadata['database_sha256'] != manifest['database_sha256']:
        raise ValueError('Source database differs.')
    prefix = [bout for bout in bouts if bout['event_date'] < before]
    if not prefix or len(prefix) == len(bouts):
        raise ValueError('Need nonempty prefix and excluded future bouts.')
    snapshots, prefights = replay(prefix, minutes_prior=45, recency=.85)
    full_prefights = [row for row in read_rows(snapshot/'prefights.jsonl') if row['event_date'] < before]
    if len(prefights) != len(full_prefights):
        raise ValueError('Prefix pre-fight count differs from full replay.')
    for produced, saved in zip(prefights, full_prefights):
        if produced != {key: saved[key] for key in produced}:
            raise ValueError('Future bouts changed earlier pre-fight state: '+produced['fight_id'])
    model = json.loads((snapshot/'model.json').read_text())
    if model['training_before'] != '2019-01-01':
        raise ValueError('Unexpected frozen model period.')
    ratings, reference = make_ratings(snapshots, prefix, model)
    full_ratings = [row for row in read_rows(snapshot/'ratings.jsonl') if row['event_date'] < before]
    if ratings != full_ratings:
        raise ValueError('Future bouts changed earlier displayed history.')
    if reference != model['reference_values']:
        raise ValueError('Pre-2019 reference curve changed in the prefix.')
    for path, expected in inputs.items():
        if digest(path) != expected:
            raise ValueError('Frozen input changed while auditing: '+path)
    return {'verified': True, 'prefix_before_exclusive': before,
            'full_before_exclusive': manifest['before_exclusive'],
            'prefix_bouts': len(prefix), 'future_bouts_excluded': len(bouts)-len(prefix),
            'prefight_states_exactly_matched': len(prefights),
            'dated_ratings_exactly_matched': len(ratings),
            'frozen_reference_moments_exactly_matched': len(reference),
            'selected_resume_weight': model['resume_weight'],
            'fitting_performed': False, 'parameters_changed': False,
            'input_sha256': inputs,
            'interpretation': 'Actual later bouts removed; every earlier feature/display state is unchanged under the already frozen pre-2019 model. This is chronology verification, not fresh predictive validation.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--snapshot', type=Path, required=True)
    parser.add_argument('--database', type=Path, required=True)
    parser.add_argument('--before', default='2024-01-01')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists() or args.output.resolve().is_relative_to(args.snapshot.resolve()):
        raise ValueError('Use a new verification file outside the frozen snapshot.')
    result = verify(args.snapshot, args.database, args.before)
    with args.output.open('x') as output:
        output.write(json.dumps(result, indent=2, sort_keys=True, allow_nan=False)+'\n')
    print(json.dumps({key: value for key, value in result.items() if key != 'input_sha256'}, indent=2))


if __name__ == '__main__':
    main()
