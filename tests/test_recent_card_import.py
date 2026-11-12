"""Scoped card normalization preserves raw counts and rejects unsupported edits."""

import importlib.util
import json
import shutil
import sqlite3
from copy import deepcopy
from pathlib import Path
from uuid import uuid4

import pytest
from test_collect_cito_card import Response
from test_export_cito_current_archive import _sample
from test_research_app import A, build, fixture

from upset.data.collect_cito_archive import _digest
from upset.data.collect_cito_card import collect_card

spec = importlib.util.spec_from_file_location(
    'recent_card', Path(__file__).parents[1] / 'scripts/import_recent_card.py')
recent = importlib.util.module_from_spec(spec)
spec.loader.exec_module(recent)


def captured_card(tmp_path):
    bout, event, totals, rounds = _sample('fixture')
    bout['method'] = "TKO - Doctor's Stoppage"
    event['bouts'] = [bout]
    opponent = bout['fighters'][1]
    target_total = next(r for r in totals if r['fighterSlug'] == opponent['fighterSlug'])
    target_round = next(r for r in rounds if r['fighterSlug'] == opponent['fighterSlug'])
    for row in (target_total, target_round):
        row.update(fighterName='S. Alias', fighterSlug=None)
    source = [{'data': event}, {'data': [bout]}, {'data': {
        'event': event, 'bouts': [bout], 'boutStats': totals, 'roundStats': rounds}}]
    payloads = iter(deepcopy(source))
    card = tmp_path / 'card'
    collect_card(event['slug'], card, 'secret', lambda *a, **k: Response(next(payloads)), delay=0)
    rule = {'source_bout_id': 'fixture', 'participant_ids': [f['fighterId'] for f in bout['fighters']],
            'source_method': bout['method'], 'normalized_method': 'KO/TKO', 'winner_name': 'Alex',
            'round': bout['resultRound'], 'time': bout['resultTime'], 'public_sources': ['https://example.org/result']}
    rules = {'event_id': event['id'], 'event_slug': event['slug'], 'event_date': event['eventDate'],
             'raw_card_sha256': {name: _digest(card / name) for name in (
                 'manifest.json', 'bouts.json', 'event.json', 'stats.json')},
             'bouts': [rule], 'stat_alias': {'bout_id': 'fixture',
                 'fighter_id': opponent['fighterId'], 'slug': opponent['fighterSlug'],
                 'source_name': 'S. Alias', 'total_row_ids': [target_total['id']],
                 'round_row_ids': [target_round['id']]}}
    return card, rules


def test_doctor_method_and_absent_slug_are_scoped_without_raw_mutation(tmp_path):
    card, rules = captured_card(tmp_path)
    original = {p: p.read_bytes() for p in card.iterdir()}
    fights, stats, rounds, notes = recent.normalize_reviewed_card(card, rules)
    assert len(fights) == 1 and len(stats) == len(rounds) == 2
    assert fights[0]['result_method'] == 'KO/TKO' and len(notes) == 2
    assert all(p.read_bytes() == body for p, body in original.items())
    # The alias changes identity metadata only; counts still reconcile exactly.
    assert all(r['sig_strikes_landed'] >= 0 for r in stats)


@pytest.mark.parametrize('change', ['winner', 'participants', 'method', 'alias_rows', 'coverage'])
def test_reviewed_card_rejects_unreviewed_results_participants_and_aliases(tmp_path, change):
    card, rules = captured_card(tmp_path)
    if change == 'winner':
        rules['bouts'][0]['winner_name'] = 'Sam'
    elif change == 'participants':
        rules['bouts'][0]['participant_ids'].reverse()
    elif change == 'method':
        rules['bouts'][0]['normalized_method'] = 'Submission'
    elif change == 'alias_rows':
        rules['stat_alias']['round_row_ids'] = ['unreviewed']
    else:
        rules['bouts'] = []
    with pytest.raises(ValueError):
        recent.normalize_reviewed_card(card, rules)


def test_raw_source_changes_are_rejected_before_import(tmp_path):
    card, rules = captured_card(tmp_path)
    path = card / 'stats.json'
    path.write_text(path.read_text() + ' ')
    with pytest.raises(ValueError, match='raw card hash'):
        recent.normalize_reviewed_card(card, rules)


def test_new_identity_requires_exact_profile_and_linked_opponent_history(tmp_path):
    paths = fixture(tmp_path)
    pid, uid, name = 'new-person', str(uuid4()), 'New Person'
    bundle = tmp_path / 'bundles'
    folder = bundle / 'fighters' / pid
    folder.mkdir(parents=True)
    profile = {'id': pid, 'name': name, 'slug': 'new-person'}
    history = [{'fighterName': name, 'event': {'eventDate': '2026-10-31', 'id': 'event'},
                'opponent': {'name': 'Alex Silva'}, 'isCompleted': True, 'outcome': 'win',
                'bout': {'id': 'new', 'resultRound': 1, 'resultTime': '1:00'}}]
    for kind, data in [('profile', profile), ('fights', history)]:
        (folder / (kind + '.json')).write_text(json.dumps({
            'http_status': 200, 'expected_cito_fighter_id': pid, 'response': {'data': data}}))
    rule = {'name': name, 'slug': 'new-person', 'cito_fighter_id': pid, 'upset_fighter_id': uid,
            'identity_action': 'new_identity', 'public_sources': ['https://example.org/fighter'],
            'profile_sha256': _digest(folder / 'profile.json'),
            'history_sha256': _digest(folder / 'fights.json'), 'anchor_bout_id': 'new',
            'anchor_opponent_id': 'cito-a', 'anchor_opponent_name': 'Alex Silva'}
    rules = {'reviewed_at': '2026-11-03', 'event_id': 'event', 'event_date': '2026-10-31',
             'new_identities': [rule]}
    fight = {'source_bout_id': 'new', 'source_fighter_1_id': pid, 'source_fighter_2_id': 'cito-a',
             'fighter_1_name': name, 'fighter_2_name': 'Alex Silva', 'winner_name': name,
             'result_round': 1, 'result_time': '1:00'}
    registry, profiles, evidence, _ = recent.reviewed_identities(paths[2], paths[2], bundle, rules, [fight])
    assert any(i.upset_fighter_id == uid for i in registry.identities)
    assert profiles[0]['date_of_birth'] is None and len(evidence) == 1
    rule['anchor_opponent_id'] = 'unlinked'
    with pytest.raises(ValueError, match='already linked opponent'):
        recent.reviewed_identities(paths[2], paths[2], bundle, rules, [fight])
    rule['anchor_opponent_id'] = 'cito-a'
    rule['upset_fighter_id'] = A
    with pytest.raises(ValueError, match='conflicts'):
        recent.reviewed_identities(paths[2], paths[2], bundle, rules, [fight])


def test_preservation_detects_changed_existing_rows(tmp_path):
    paths = fixture(tmp_path)
    build(paths, tmp_path / 'old')
    old, new = tmp_path / 'old/upset.sqlite', tmp_path / 'new.sqlite'
    shutil.copy2(old, new)
    assert recent.verify_preservation(old, new)['fighters']['added'] == 0
    with sqlite3.connect(new) as db:
        db.execute('UPDATE fighters SET name=? WHERE id=?', ('changed', A))
    with pytest.raises(ValueError, match='Existing serving rows changed'):
        recent.verify_preservation(old, new)
