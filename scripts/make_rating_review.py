"""Package a portable, read-only review of the November 5 rating snapshot."""

import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import zipfile
from bisect import bisect_left
from collections import defaultdict
from contextlib import closing
from pathlib import Path

from upset.research_app import connect, fighter_report

ROOT = Path(__file__).resolve().parents[1]
PROCESSED = ROOT/'data/processed'
SNAPSHOT = PROCESSED/'overall_rating_2026_11_05_v1'
DATABASE = PROCESSED/'research_2026_11_03_v1/upset.sqlite'
GAETHJE = '678d50b2-742c-44e4-b833-d560794ba84c'
TOPURIA = '7a1b1eb6-1471-4f85-987c-d77c340947eb'
FIGHT = 'cito:7208e40818401e88'
NAME = 'UPSET-Rating-Review-2026-11-05'


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def lines(path):
    with path.open() as stream:
        for line in stream:
            yield json.loads(line)


def save(path, data):
    path.write_text(json.dumps(data, indent=2, sort_keys=True, allow_nan=False)+'\n')


def create_review():
    manifest_path = SNAPSHOT/'manifest.json'
    manifest = json.loads(manifest_path.read_text())
    if sha(DATABASE) != manifest['database_sha256']:
        raise ValueError('Source database hash differs.')
    for name, expected in manifest['output_sha256'].items():
        if sha(SNAPSHOT/name) != expected:
            raise ValueError('Saved study file differs: '+name)
    for name, expected in manifest['input_sha256'].items():
        if sha(Path(name)) != expected:
            raise ValueError('Saved source hash differs: '+Path(name).name)

    out = ROOT/'docs/share'
    out.mkdir(parents=True, exist_ok=True)
    archive = out/(NAME+'.zip')
    if archive.exists():
        raise ValueError('Review archive already exists; preserve the delivered copy.')
    with tempfile.TemporaryDirectory(dir=out, prefix='.rating-review-') as tmp:
        bundle = Path(tmp)/NAME
        for name in ('case', 'evidence', 'methods', 'source', 'tests', 'figures'):
            (bundle/name).mkdir(parents=True)

        states, history = defaultdict(list), defaultdict(list)
        for row in lines(SNAPSHOT/'ratings.jsonl'):
            uid = row['fighter_id']
            states[uid].append((row['event_date'], row['score']))
            if uid in (GAETHJE, TOPURIA):
                history[uid].append(row)
        dates = {uid: [day for day, _ in records] for uid, records in states.items()}
        case = {}
        for uid, name in [(GAETHJE, 'gaethje'), (TOPURIA, 'topuria')]:
            position = dates[uid].index('2026-06-14')
            case[name] = {'before': history[uid][position-1], 'after': history[uid][position],
                          'displayed_history': [{'event_date': d, 'score': v} for d, v in states[uid]]}

        with closing(connect(DATABASE)) as db:
            report = fighter_report(db, GAETHJE, '2026-11-05', 0)
        bout = next(item for item in report['history'] if item['fight_id'] == FIGHT)
        stat_fields = ('sig_strikes_landed', 'sig_strikes_attempted', 'takedowns_landed',
                       'takedowns_attempted', 'control_seconds', 'knockdowns', 'ground_landed',
                       'submission_attempts', 'fight_duration_seconds')
        case['recorded_bout'] = {key: bout[key] for key in ('fight_id', 'date', 'opponent', 'outcome',
            'method', 'result_round', 'result_time', 'title_bout', 'source', 'weight_class')}
        case['recorded_bout']['stats_by_fighter'] = {
            name: {key: bout[field][key] for key in stat_fields}
            for name, field in [('Justin Gaethje', 'own'), ('Ilia Topuria', 'opponent_stats')]}
        case['scope'] = 'UPSET stored records; not an independent event or source-data verification.'
        save(bundle/'case/gaethje-topuria.json', case)

        evaluation = json.loads((SNAPSHOT/'evaluation.json').read_text())
        record = evaluation['track_record']
        with (bundle/'evidence/displayed_comparisons.jsonl').open('w') as stream:
            for row in lines(SNAPSHOT/'prefights.jsonl'):
                day = row['event_date']
                if not record['from_date'] <= day < record['before_exclusive'] or row['winner_id'] is None:
                    continue
                selected = []
                for uid in row['fighter_ids']:
                    i = bisect_left(dates.get(uid, []), day)-1
                    selected.append(states[uid][i] if i >= 0 else (None, None))
                result = {key: row[key] for key in ('fight_id', 'event_date', 'fighter_ids', 'winner_id')}
                result['rating_state_dates'], result['pre_fight_grades'] = map(list, zip(*selected))
                stream.write(json.dumps(result, sort_keys=True)+'\n')

        for name in ('model.json', 'config.json', 'evaluation.json', 'development.jsonl'):
            shutil.copyfile(SNAPSHOT/name, bundle/'evidence'/name)
        for source, name, omit in [
            ('overall_rating_verification_2026_11_05.json', 'audit-summary.json', {'authorized_viewer_changes'}),
            ('overall_rating_prefix_verification_2026_11_05.json', 'chronology-summary.json', {'input_sha256'}),
        ]:
            audit = json.loads((PROCESSED/source).read_text())
            save(bundle/'evidence'/name, {key: value for key, value in audit.items() if key not in omit})
        save(bundle/'evidence/snapshot-provenance.json', {
            **{key: manifest[key] for key in ('version', 'experimental', 'validated', 'public_release',
                'database_sha256', 'before_exclusive', 'latest_event', 'display_curve', 'output_sha256')},
            'original_manifest_sha256': sha(manifest_path),
            'original_source_sha256': {Path(name).name: value for name, value in manifest['input_sha256'].items()},
            'note': 'Fingerprints of original inputs and outputs; the database and full snapshot are not included.',
        })

        shutil.copyfile(ROOT/'docs/GAETHJE_RATING_WALKTHROUGH_2026_11_05.md', bundle/'case/GAETHJE_WALKTHROUGH.md')
        shutil.copyfile(SNAPSHOT/'protocol.md', bundle/'methods/OVERALL_RATING_PROTOCOL_V1.md')
        report = (ROOT/'docs/OVERALL_RATING_2026_11_05.md').read_text().split('## Start UPSET after a shutdown')[0]
        report = report.split('Screenshots:')[0].replace('assets/overall_rating_2026_11_04_v1/development_checks.png',
                                                       '../figures/development_checks.png')
        (bundle/'methods/VALIDATION_REPORT.md').write_text(report.rstrip()+'\n')
        for path in sorted((ROOT/'src/upset/ratings').glob('*.py')):
            shutil.copyfile(path, bundle/'source'/path.name)
        for path in sorted((ROOT/'tests').glob('test_rating_*.py')):
            shutil.copyfile(path, bundle/'tests'/path.name)
        shutil.copyfile(ROOT/'scripts/verify_rating_review.py', bundle/'verify_review.py')
        shutil.copyfile(ROOT/'docs/assets/overall_rating_2026_11_04_v1/development_checks.png', bundle/'figures/development_checks.png')
        shutil.copyfile(ROOT/'docs/assets/overall_rating_2026_11_05_v1/breakdown-phone.jpg', bundle/'figures/gaethje-breakdown.jpg')
        (bundle/'START_HERE.md').write_text('''# UPSET Experimental v1 — independent review package

Start with [Why Gaethje went from 84 to 83](case/GAETHJE_WALKTHROUGH.md).
It explains the calculation, the model choice worth questioning, and what
to review next. The sample is drawn from UPSET's recorded data.

| File | What it contains |
| --- | --- |
| `case/gaethje-topuria.json` | Full precision before/after rows for both fighters, score history, and the recorded fight inputs |
| `methods/OVERALL_RATING_PROTOCOL_V1.md` | Declared feature, selection, date, and display rules |
| `methods/VALIDATION_REPORT.md` | Historical development results, limitations, and preservation audit |
| `evidence/model.json`, `config.json` | Fitted blend and slopes, full fixed reference curve, and settings |
| `evidence/evaluation.json` | Detailed comparison, subgroup results, and the displayed-rating track record |
| `evidence/development.jsonl` | All 3,149 matched scored fights with pre-fight component indices |
| `evidence/displayed_comparisons.jsonl` | Every decisive fight considered for the displayed-grade record, including ties and unavailable grades |
| `evidence/*summary.json`, `snapshot-provenance.json` | Audit summaries and original file fingerprints |
| `source/`, `tests/` | Original model/serving sources and project tests for inspection |
| `figures/` | Model comparison and a clean screenshot of the Gaethje panel |

After extracting the ZIP, run `python3 verify_review.py` from this folder to
check the worked example, saved development log loss, displayed-grade track
record, and bundle hashes. It requires only Python's standard library.

The source and project tests are reference copies, not a standalone UPSET
installation. A complete replay from raw bouts requires the original reviewed
database and the rest of the repository. This package contains selected fight
inputs and evaluation records, not the full database, credentials, roster
assets, or private browser screenshot. It does not change or retrain the model.

This is an experimental performance index. Historical development results do
not establish its performance on fresh fights or determine an individual
fighter's win probability.
''')
        save(bundle/'SHA256.json', {str(path.relative_to(bundle)): sha(path) for path in sorted(bundle.rglob('*')) if path.is_file()})
        subprocess.run([sys.executable, str(bundle/'verify_review.py')], check=True)
        staged = Path(tmp)/archive.name
        with zipfile.ZipFile(staged, 'x', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zipped:
            for path in sorted(bundle.rglob('*')):
                if path.is_file():
                    zipped.write(path, arcname=str(path.relative_to(bundle.parent)))
        with zipfile.ZipFile(staged) as zipped:
            if zipped.testzip() is not None:
                raise ValueError('Review archive failed integrity checks.')
        staged.replace(archive)
    print(f'{archive} ({archive.stat().st_size:,} bytes)')


if __name__ == '__main__':
    create_review()
