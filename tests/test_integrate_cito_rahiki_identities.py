"""Reviewed identity changes must preserve records and reject conflicting evidence."""
import json
from copy import deepcopy
from dataclasses import asdict

import pytest
from test_integrate_cito_matchup_identities import setup
from test_research_app import C, build, write_rows
from upset.data.collect_cito_archive import _digest
from upset.data.identity import load_fighter_registry
from upset.data.integrate_cito_rahiki_identities import integrate, matchup_evidence
from upset.data.models import Fighter


def prepare(tmp_path):
    paths, review, bundles, rule, history, queue = setup(tmp_path)
    path = bundles / 'fighters/cito-a/fights.json'
    wrapper = json.loads(path.read_text())
    wrapper['response']['data'][0]['bout'].update(method='Decision - Unanimous', resultRound=3, resultTime='5:00')
    path.write_text(json.dumps(wrapper))
    rule['history_sha256'] = _digest(path)
    return paths, bundles, rule, wrapper['response']['data'], queue


def test_reviewed_identity_restages_without_changing_canonical_records(tmp_path):
    paths, bundles, rule, _, _ = prepare(tmp_path)
    before = {p: p.read_bytes() for p in tmp_path.rglob('*.json*')}
    output = tmp_path / 'linked'
    result = integrate(paths[1], bundles, paths[0] / 'fights_identified.jsonl', output,
                       rules=(rule,), expected_history=paths[4])
    assert result['identity_links_added'] == result['newly_identified_bouts'] == 1
    assert result['api_calls'] == 0
    assert all(p.read_bytes() == value for p, value in before.items())
    assert integrate(paths[1], bundles, paths[0] / 'fights_identified.jsonl', output,
                     rules=(rule,), expected_history=paths[4]) == result
    assert build((paths[0], output, output / 'fighter_registry.json', paths[3], paths[4], paths[5]),
                 tmp_path / 'research')['total_bouts'] == 2
    (bundles / 'fighters/cito-a/fights.json').write_text('{}')
    with pytest.raises(ValueError, match='hash differs'):
        integrate(paths[1], bundles, paths[0] / 'fights_identified.jsonl', tmp_path / 'bad',
                  rules=(rule,), expected_history=paths[4])


@pytest.mark.parametrize('field,value', [('resultTime', '4:59'), ('method', 'SUB'), ('resultRound', 2)])
def test_result_conflict_rejects_identity(tmp_path, field, value):
    paths, _, rule, history, queue = prepare(tmp_path)
    history = deepcopy(history)
    history[0]['bout'][field] = value
    with pytest.raises(ValueError, match='clock differs'):
        matchup_evidence(rule, [json.loads(l) for l in (paths[1] / 'fights.jsonl').read_text().splitlines()],
                         queue['unresolved_fighter_identities'][0], history, load_fighter_registry(paths[2]))


def test_new_profile_requires_verified_provider_link_and_cannot_replace_history(tmp_path):
    paths, bundles, rule, _, _ = prepare(tmp_path)
    # C already has a profile: supplement must reject replacing it, even with a valid link.
    current = paths[1]
    profile = {**asdict(Fighter('cito', 'cito-c', None, 'Alex Silva')), 'upset_fighter_id': C}
    write_rows(current / 'fighters_identified.jsonl', [profile])
    cm = json.loads((current / 'manifest.json').read_text())
    cm['output_sha256']['fighters_identified.jsonl'] = _digest(current / 'fighters_identified.jsonl')
    (current / 'manifest.json').write_text(json.dumps(cm))
    with pytest.raises(ValueError, match='Supplementary profile identity'):
        build(paths, tmp_path / 'bad')


def test_new_identity_profile_is_admitted_with_null_demographics(tmp_path):
    paths, bundles, rule, history, queue = prepare(tmp_path)
    current, historical = paths[1], paths[0]
    # Remove Alex's historical profile and identity only for this fixture, while
    # preserving the opponent and the accepted historical bout under a third identity.
    rule.pop('ufcstats_fighter_id')
    rule['name'] = 'New Fighter'
    rule['new_upset_fighter_id'] = '00000000-0000-4000-8000-000000000009'
    canonical = [json.loads(l) for l in (current / 'fights.jsonl').read_text().splitlines()]
    canonical[0]['fighter_1_name'] = canonical[0]['winner_name'] = canonical[0]['source_winner_label'] = 'New Fighter'
    write_rows(current / 'fights.jsonl', canonical)
    history[0]['fighterName'] = 'New Fighter'
    path = bundles / 'fighters/cito-a/fights.json'
    wrapper = json.loads(path.read_text()); wrapper['response']['data'] = history
    path.write_text(json.dumps(wrapper)); rule['history_sha256'] = _digest(path)
    queue['unresolved_fighter_identities'][0]['name_only_candidates'] = []
    (current / 'review.json').write_text(json.dumps(queue))
    cm = json.loads((current / 'manifest.json').read_text())
    cm['output_sha256'] = {str(p.relative_to(current)): _digest(p) for p in current.rglob('*') if p.is_file() and p != current / 'manifest.json'}
    (current / 'manifest.json').write_text(json.dumps(cm))
    output = tmp_path / 'linked'
    integrate(current, bundles, historical / 'fights_identified.jsonl', output,
              rules=(rule,), expected_history=paths[4])
    report = build((historical, output, output / 'fighter_registry.json', paths[3], paths[4], paths[5]), tmp_path / 'research')
    assert report['fighters'] == 4 and report['total_bouts'] == 2
    profile = json.loads((output / 'fighters_identified.jsonl').read_text())
    assert profile['date_of_birth'] is None and profile['height_inches'] is None
