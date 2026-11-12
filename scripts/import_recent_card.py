"""Import an explicitly reviewed card additively; preserve prior serving rows."""

import argparse
import json
import sqlite3
from copy import deepcopy
from dataclasses import asdict
from pathlib import Path
from tempfile import TemporaryDirectory

from upset.data.audit_cito_archive import _name
from upset.data.build_research_db import build_database, rows
from upset.data.collect_cito_archive import _digest
from upset.data.export_cito_card import _bout_signature, _read_card
from upset.data.export_cito_current_archive import _manifest, normalize_completed_bout
from upset.data.identity import (
    FighterIdentity,
    FighterProviderLink,
    FighterRegistry,
    load_fighter_registry,
    save_fighter_registry,
)
from upset.data.models import Fighter
from upset.data.reconcile_cito_archive import _write_verified
from upset.data.stage_current import stage_completed_fights


def normalize_reviewed_card(card, rules):
    for name, expected in rules['raw_card_sha256'].items():
        if _digest(card / name) != expected:
            raise ValueError('Reviewed raw card hash differs.')
    payloads, _, _ = _read_card(card)
    event, raw_stats = payloads['event'], payloads['stats']
    if (event['id'] != rules['event_id'] or event['slug'] != rules['event_slug']
            or event['eventDate'] != rules['event_date']):
        raise ValueError('Reviewed event identity differs.')
    listing = payloads['bouts']
    if isinstance(listing, dict):
        listing = next(listing[key] for key in ('bouts', 'fights', 'items', 'results') if key in listing)
    wanted = {r['source_bout_id']: r for r in rules['bouts']}
    bids = {str(b['id']) for b in listing}
    if len(bids) != len(listing) or bids != set(wanted):
        raise ValueError('Reviewed rules must account for every listed bout exactly once.')
    for endpoint in (event, raw_stats):
        embedded = endpoint['bouts']
        if len(embedded) != len(listing) or {str(b['id']) for b in embedded} != bids:
            raise ValueError('Endpoint coverage differs.')
    if any(str(r['boutId']) not in bids for kind in ('boutStats', 'roundStats') for r in raw_stats[kind]):
        raise ValueError('Orphan card statistics.')
    fights, stats, rounds, notes = [], [], [], []
    for original in listing:
        bid = str(original['id'])
        rule = wanted[bid]
        for endpoint in (event, raw_stats):
            embedded = next(b for b in endpoint['bouts'] if str(b['id']) == bid)
            if _bout_signature(original) != _bout_signature(embedded):
                raise ValueError('Source endpoint participants/results disagree.')
        if ([f['fighterId'] for f in original['fighters']] != rule['participant_ids']
                or original['method'] != rule['source_method'] or not rule['public_sources']):
            raise ValueError('Reviewed participant or source method differs.')
        bout = deepcopy(original)
        if rule['source_method'] != rule['normalized_method']:
            if (rule['source_method'], rule['normalized_method']) != ("TKO - Doctor's Stoppage", 'KO/TKO'):
                raise ValueError('Unreviewed method conversion.')
            bout['method'] = rule['normalized_method']
            notes.append({'bout_id': bid, 'source_method': original['method'],
                          'normalized_method': bout['method'], 'public_sources': rule['public_sources']})
        totals = deepcopy([r for r in raw_stats['boutStats'] if str(r['boutId']) == bid])
        raw_rounds = deepcopy([r for r in raw_stats['roundStats'] if str(r['boutId']) == bid])
        alias = rules['stat_alias']
        if bid == alias['bout_id']:
            fighter = next(f for f in bout['fighters'] if f['fighterId'] == alias['fighter_id'])
            if fighter['fighterSlug'] != alias['slug']:
                raise ValueError('Reviewed statistics alias participant differs.')
            for batch, ids in ((totals, alias['total_row_ids']), (raw_rounds, alias['round_row_ids'])):
                targets = [r for r in batch if r.get('fighterName') == alias['source_name']]
                if {r['id'] for r in targets} != set(ids):
                    raise ValueError('Reviewed alias source-row IDs differ.')
                for row in targets:
                    if row.get('fighterSlug') is not None:
                        raise ValueError('Alias applies only to the reviewed absent slugs.')
                    row['fighterSlug'] = alias['slug']
            notes.append(alias)
        fight, paired, reconciled = normalize_completed_bout(bout, event, totals, raw_rounds)
        if (fight['winner_name'], fight['result_method'], fight['result_round'], fight['result_time']) != (
                rule['winner_name'], rule['normalized_method'], rule['round'], rule['time']):
            raise ValueError('Normalized result differs from explicit reviewed result.')
        if rule.get('source_discrepancy_note'):
            notes.append({'bout_id': bid, 'note': rule['source_discrepancy_note'],
                          'public_sources': rule['public_sources']})
        fights.append(fight)
        stats.extend(paired)
        rounds.extend(reconciled)
    return fights, stats, rounds, notes


def reviewed_identities(prior_registry, namespace_registry, bundles, rules, fights):
    registry = load_fighter_registry(prior_registry)
    namespace = load_fighter_registry(namespace_registry)
    known_names = {_name(i.display_name) for i in (*registry.identities, *namespace.identities)}
    known_ids = {i.upset_fighter_id for i in (*registry.identities, *namespace.identities)}
    links = {link.provider_fighter_id: link.upset_fighter_id for link in registry.provider_links
             if link.provider == 'cito'}
    profiles, evidence, hashes = [], [], {}
    for rule in rules['new_identities']:
        pid, uid, name = rule['cito_fighter_id'], rule['upset_fighter_id'], rule['name']
        if (pid in links or uid in known_ids or _name(name) in known_names
                or rule['identity_action'] != 'new_identity' or not rule['public_sources']):
            raise ValueError('New reviewed identity conflicts with a known identity.')
        wrappers = {}
        for kind, field in (('profile', 'profile_sha256'), ('fights', 'history_sha256')):
            path = bundles / 'fighters' / pid / (kind + '.json')
            hashes[str(path)] = _digest(path)
            if hashes[str(path)] != rule[field]:
                raise ValueError('Reviewed identity bundle hash differs.')
            wrapper = json.loads(path.read_text())
            if (wrapper['http_status'] != 200 or wrapper['expected_cito_fighter_id'] != pid
                    or wrapper['response'].get('success') is False):
                raise ValueError('Reviewed bundle response identity differs.')
            wrappers[kind] = wrapper['response']['data']
        profile = wrappers['profile'].get('fighter', wrappers['profile'])
        if (profile['id'], profile['slug'], profile['name']) != (pid, rule['slug'], name):
            raise ValueError('Reviewed provider profile differs.')
        history = wrappers['fights']
        history = history.get('fights', []) if isinstance(history, dict) else history
        anchors = [h for h in history if str(h['bout']['id']) == rule['anchor_bout_id']
                   and h['event']['eventDate'] == rules['event_date']
                   and h['event']['id'] == rules['event_id'] and h['fighterName'] == name
                   and h['opponent']['name'] == rule['anchor_opponent_name']
                   and h['isCompleted'] is True]
        fight = next(f for f in fights if f['source_bout_id'] == rule['anchor_bout_id'])
        if len(anchors) != 1 or rule['anchor_opponent_id'] not in links:
            raise ValueError('Identity lacks a dated anchor against an already linked opponent.')
        side = next((i for i in (1, 2) if fight[f'source_fighter_{i}_id'] == pid), None)
        if (side is None or fight[f'source_fighter_{3-side}_id'] != rule['anchor_opponent_id']
                or fight[f'fighter_{3-side}_name'] != rule['anchor_opponent_name']):
            raise ValueError('Reviewed history participant differs from card.')
        anchor = anchors[0]
        if (anchor['outcome'] != ('win' if fight['winner_name'] == name else 'loss')
                or anchor['bout']['resultRound'] != fight['result_round']
                or anchor['bout']['resultTime'] != fight['result_time']):
            raise ValueError('Reviewed history result differs from card.')
        item = {**rule, 'reviewed_at': rules['reviewed_at'],
                'basis': 'explicit profile/provider ID and dated matchup with linked opponent'}
        registry = FighterRegistry((*registry.identities, FighterIdentity(uid, name)),
            (*registry.provider_links, FighterProviderLink('cito', pid, uid, json.dumps(item, sort_keys=True))))
        profiles.append({**asdict(Fighter('cito', pid, rule['slug'], name,
                          source_url='https://www.ufc.com/athlete/' + rule['slug'])),
                         'upset_fighter_id': uid})
        evidence.append(item)
        known_names.add(_name(name))
        known_ids.add(uid)
    return registry, profiles, evidence, hashes


def integrate(prior, card, bundles, rules_path, namespace, historical, output):
    if output.exists() or any(output.resolve().is_relative_to(p.resolve())
                              for p in (prior, card, bundles, historical, namespace, rules_path)):
        raise ValueError('Use a new output separate from inputs.')
    hashes = {str(p): _digest(p) for p in (rules_path, namespace, Path(__file__))}
    prior_manifest = _manifest(prior, hashes)
    rules = json.loads(rules_path.read_text())
    if rules['schema_version'] != 1 or rules['reviewed_at'] != '2026-11-03':
        raise ValueError('Unsupported review rules.')
    new_fights, new_stats, new_rounds, notes = normalize_reviewed_card(card, rules)
    hashes.update({str(card / name): expected for name, expected in rules['raw_card_sha256'].items()})
    registry, profiles, evidence, identity_hashes = reviewed_identities(
        prior / 'fighter_registry.json', namespace, bundles, rules, new_fights)
    hashes.update(identity_hashes)
    links = {l.provider_fighter_id: l.upset_fighter_id for l in registry.provider_links if l.provider == 'cito'}
    for fight in new_fights:
        for side in (1, 2):
            fight[f'upset_fighter_{side}_id'] = links[fight[f'source_fighter_{side}_id']]
    for row in (*new_stats, *new_rounds):
        row['upset_fighter_id'] = links[row['source_fighter_id']]
    canonical = rows(prior / 'fights.jsonl')
    accepted = rows(prior / 'identified/fights_identified.jsonl')
    old_ids = {f['source_bout_id'] for f in canonical}
    if old_ids & {f['source_bout_id'] for f in new_fights}:
        raise ValueError('Card repeats a prior canonical bout.')
    queue = json.loads((prior / 'review.json').read_text())
    resolved = {r['cito_fighter_id'] for r in evidence}
    queue['unresolved_fighter_identities'] = [r for r in queue['unresolved_fighter_identities']
                                            if r['cito_fighter_id'] not in resolved]
    queue['reviewed_card_normalization'] = notes
    accepted_ids = {f['source_bout_id'] for f in accepted}
    queue['withheld_prior_bout_ids'] = sorted(old_ids - accepted_ids)
    output.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=output.parent, prefix='.upset-reviewed-card-') as temporary:
        folder = Path(temporary) / 'current'
        folder.mkdir()
        save_fighter_registry(registry, folder / 'fighter_registry.json')
        for name, batch in (
                ('fights.jsonl', canonical + [{k: v for k, v in f.items() if not k.startswith('upset_')}
                                             for f in new_fights]),
                ('fight_stats.jsonl', rows(prior / 'fight_stats.jsonl') +
                 [{k: v for k, v in s.items() if k != 'upset_fighter_id'} for s in new_stats]),
                ('fighters_identified.jsonl', rows(prior / 'fighters_identified.jsonl') + profiles),
                ('identity_link_evidence.jsonl', rows(prior / 'identity_link_evidence.jsonl') + evidence),
                ('rounds_staged.jsonl', rows(prior / 'rounds_staged.jsonl') + new_rounds),
                ('bout_provenance.jsonl', rows(prior / 'bout_provenance.jsonl') + [
                    {'source_bout_id': f['source_bout_id'], 'event': rules['event_slug'],
                     'raw_stats_sha256': rules['raw_card_sha256']['stats.json'],
                     'totals_basis': 'provider_totals_reconciled_with_rounds',
                     'provider_fight_totals_present': True, 'reviewed_rules_sha256': hashes[str(rules_path)]}
                    for f in new_fights])):
            _write_verified(folder / name, batch)
        (folder / 'review.json').write_text(json.dumps(queue, indent=2, sort_keys=True) + '\n')
        (folder / 'reviewed_card.json').write_text(json.dumps(rules, indent=2, sort_keys=True) + '\n')
        subset = Path(temporary) / 'subset'
        subset.mkdir()
        accepted_fights = accepted + new_fights
        accepted_stats = rows(prior / 'identified/fight_stats_identified.jsonl') + new_stats
        _write_verified(subset / 'fights.jsonl', [
            {k: v for k, v in f.items() if not k.startswith('upset_')} for f in accepted_fights])
        _write_verified(subset / 'fight_stats.jsonl', [
            {k: v for k, v in s.items() if k != 'upset_fighter_id'} for s in accepted_stats])
        staged = stage_completed_fights(subset / 'fights.jsonl', subset / 'fight_stats.jsonl',
            folder / 'fighter_registry.json', historical, folder / 'identified')
        staged['input_paths'] = {'registry': str(output / 'fighter_registry.json'), 'historical': str(historical)}
        (folder / 'identified/manifest.json').write_text(json.dumps(staged, indent=2, sort_keys=True) + '\n')
        excluded = len(canonical) - len(accepted)
        if excluded != prior_manifest['bouts_awaiting_identity_review']:
            raise ValueError('Prior exclusion accounting differs.')
        summary = {**prior_manifest, 'status': 'Reviewed additive October 31 card; prior cohort preserved',
                   'identified_current_bouts': len(accepted_fights),
                   'canonical_current_bouts': len(canonical) + len(new_fights),
                   'canonical_fighter_stats': 2 * (len(canonical) + len(new_fights)),
                   'current_round_rows': len(rows(folder / 'rounds_staged.jsonl')),
                   'bouts_awaiting_identity_review': excluded,
                   'unresolved_provider_fighters': len(queue['unresolved_fighter_identities']),
                   'new_bouts': len(new_fights), 'new_identities': len(profiles),
                   'latest_bout': rules['event_date'], 'coverage_verified': False,
                   'cohort_policy': rules['cohort_policy'], 'input_sha256': hashes,
                   'identified_subset_manifest': staged,
                   'output_sha256': {str(p.relative_to(folder)): _digest(p)
                                     for p in folder.rglob('*') if p.is_file()}}
        if any(_digest(Path(p)) != expected for p, expected in hashes.items()):
            raise ValueError('Import inputs changed during integration.')
        (folder / 'manifest.json').write_text(json.dumps(summary, indent=2, sort_keys=True) + '\n')
        folder.rename(output)
    return summary


def verify_preservation(old_database, new_database):
    result = {}
    with sqlite3.connect(old_database.resolve().as_uri() + '?mode=ro', uri=True) as old, \
            sqlite3.connect(new_database.resolve().as_uri() + '?mode=ro', uri=True) as new:
        for table in ('fighters', 'fights', 'stats'):
            prior = set(old.execute('SELECT * FROM ' + table).fetchall())
            updated = set(new.execute('SELECT * FROM ' + table).fetchall())
            if not prior <= updated:
                raise ValueError('Existing serving rows changed: ' + table)
            result[table] = {'preserved': len(prior), 'added': len(updated) - len(prior)}
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prior', type=Path, required=True)
    parser.add_argument('--database', type=Path, required=True)
    parser.add_argument('--card', type=Path, required=True)
    parser.add_argument('--bundles', type=Path, required=True)
    parser.add_argument('--rules', type=Path, required=True)
    parser.add_argument('--namespace', type=Path, default=Path('data/mappings/fighter_registry.json'))
    parser.add_argument('--historical', type=Path,
                        default=Path('data/processed/kaggle_ufc_1994_2026/identified'))
    parser.add_argument('--current-output', type=Path, required=True)
    parser.add_argument('--database-output', type=Path, required=True)
    args = parser.parse_args()
    rules = json.loads(args.rules.read_text())
    if _digest(args.database) != rules['prior_database_sha256']:
        raise ValueError('Prior serving database differs from reviewed baseline.')
    summary = integrate(args.prior, args.card, args.bundles, args.rules, args.namespace,
                        args.historical / 'fights_identified.jsonl', args.current_output)
    manifest = build_database(args.historical, args.current_output,
        args.current_output / 'fighter_registry.json', Path('data/processed/cito_historical_rounds_v1'),
        args.database_output)
    preservation = verify_preservation(args.database, args.database_output / 'upset.sqlite')
    print(json.dumps({'new_bouts': summary['new_bouts'], 'new_identities': summary['new_identities'],
                      'total_bouts': manifest['total_bouts'], 'preservation': preservation}, indent=2))


if __name__ == '__main__':
    main()
