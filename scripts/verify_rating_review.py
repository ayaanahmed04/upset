"""Check the portable UPSET review bundle with Python's standard library."""

import hashlib
import json
from bisect import bisect_left, bisect_right
from math import exp, floor, fsum, isclose, log, log1p
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SKILLS = ('striking', 'wrestling', 'grappling')


def read(name):
    return json.loads((ROOT/name).read_text())


def rows(name):
    return [json.loads(line) for line in (ROOT/name).read_text().splitlines()]


def check(condition, message):
    if not condition:
        raise ValueError(message)


def near(actual, saved, message):
    check(isclose(actual, saved, rel_tol=0, abs_tol=1e-10), message)


def blend(parts, weight):
    values = sorted((parts[key] for key in SKILLS), reverse=True)
    skill = fsum(w*v for w, v in zip((.5, .3, .2), values))
    return skill, weight*parts['resume']+(1-weight)*skill


def curve(combined, model):
    reference = model['reference_values']
    percentile = (bisect_left(reference, combined)+bisect_right(reference, combined))/(2*len(reference))
    for (a, x), (b, y) in zip(model['anchors'], model['anchors'][1:]):
        if percentile <= b:
            return percentile, x+(percentile-a)*(y-x)/(b-a)
    raise ValueError('Reference percentile is out of bounds.')


def verify_case(case, model):
    before, after = (case['gaethje'][stage] for stage in ('before', 'after'))
    weight = model['resume_weight']
    for item in (before, after):
        parts = {p['key']: p['score'] for p in item['parts']}
        skill, combined = blend(parts, weight)
        near(skill, item['skills_combined'], 'Skills blend differs.')
        near(combined, item['raw_combined'], 'Combined score differs.')
        percentile, grade = curve(item['raw_combined'], model)
        near(percentile, item['curve_percentile'], 'Reference percentile differs.')
        check(floor(grade+.5) == item['curve_score'] == item['score'], 'Display grade differs.')
        check(item['small_history_adjustment'] == item['change_adjustment'] == 0, 'Unexpected cap.')
    opponent = case['topuria']['before']
    expected = 1/(1+10**((opponent['elo']-before['elo'])/400))
    near(before['elo']+32*(1-expected), after['elo'], 'Elo result update differs.')
    print(f"Gaethje: {before['score']} → {after['score']}; combined {before['raw_combined']:.6f} → {after['raw_combined']:.6f}")


def verify_development(model, evaluation):
    development = rows('evidence/development.jsonl')
    for label, weight, fit in [('candidate', model['resume_weight'], 'probability_fit'),
                               ('resume_only', 1., 'resume_only_fit')]:
        losses, errors = [], []
        for row in development:
            a, b = [blend({key: 60+.39*val for key, val in parts.items()}, weight)[1] for parts in row['parts']]
            z = model[fit]['slope']*(a-b)
            y = int(row['winner_id'] == row['fighter_ids'][0])
            loss = max(z, 0)+log1p(exp(-abs(z)))-y*z
            probability = 1/(1+exp(-z))
            near(loss, row['candidate_nll' if label == 'candidate' else 'resume_nll'], 'Saved per-fight log loss differs.')
            losses.append(loss)
            errors.append((probability-y)**2)
        n = len(losses)
        check(n == evaluation[label]['bouts'], 'Matched development count differs.')
        near(fsum(losses)/n, evaluation[label]['nll'], 'Mean log loss differs.')
        near(fsum(errors)/n, evaluation[label]['brier'], 'Brier score differs.')
        print(f'{label}: {n:,} matched fights; mean log loss {fsum(losses)/n:.5f}')


def verify_display(evaluation):
    wins = total = ties = unavailable = 0
    for row in rows('evidence/displayed_comparisons.jsonl'):
        grades = row['pre_fight_grades']
        check(all(s is None or s < row['event_date'] for s in row['rating_state_dates']), 'Future or same-day grade used.')
        if None in grades:
            unavailable += 1
        elif grades[0] == grades[1]:
            ties += 1
        else:
            total += 1
            wins += row['winner_id'] == row['fighter_ids'][int(grades[1] > grades[0])]
    record = evaluation['track_record']
    check((wins, total, ties, unavailable) == (record['wins'], record['total'], record['ties_excluded'], record['unavailable_excluded']),
          'Displayed-rating track record differs.')
    near(wins/total, record['accuracy'], 'Displayed-rating accuracy differs.')
    print(f'Higher pre-fight grade: {wins:,}/{total:,} winners ({100*wins/total:.1f}%); {ties} ties and {unavailable} unavailable excluded.')


def main():
    for name, expected in read('SHA256.json').items():
        path = (ROOT/name).resolve()
        check(ROOT in path.parents and hashlib.sha256(path.read_bytes()).hexdigest() == expected,
              'Bundle file differs: '+name)
    model, evaluation = read('evidence/model.json'), read('evidence/evaluation.json')
    verify_case(read('case/gaethje-topuria.json'), model)
    verify_development(model, evaluation)
    verify_display(evaluation)
    check(evaluation['candidate']['nll'] < log(2), 'Development chance reference differs.')
    print('Bundle arithmetic verified. This does not refit the model or establish future performance.')


if __name__ == '__main__':
    main()
