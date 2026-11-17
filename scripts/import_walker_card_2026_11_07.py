"""Add the reviewed November 7 card and the related saved UFC debuts."""
import json
from dataclasses import asdict
from pathlib import Path
from tempfile import TemporaryDirectory

from import_recent_card import verify_preservation

from upset.data.build_research_db import build_database, rows
from upset.data.collect_cito_archive import _digest
from upset.data.export_cito_card import _bout_signature, _read_card
from upset.data.export_cito_current_archive import _manifest, normalize_completed_bout
from upset.data.identity import (
    FighterIdentity, FighterProviderLink, FighterRegistry, load_fighter_registry, save_fighter_registry,
)
from upset.data.models import Fighter
from upset.data.reconcile_cito_archive import _write_verified
from upset.data.stage_current import stage_completed_fights

PROCESSED = Path('data/processed')
PRIOR = PROCESSED / 'cito_current_2026_11_05_backfill_v1'
OLD_DB = PROCESSED / 'research_2026_11_05_backfill_v1/upset.sqlite'
CARD = Path('data/raw/cito_walker_2026_11_08_v1')
HISTORY = PROCESSED / 'kaggle_ufc_1994_2026/identified'
ARCHIVE = PROCESSED / 'cito_current_2026_11_08_reviewed_v1'
DB = PROCESSED / 'research_2026_11_08_reviewed_v1'
UFC = 'https://www.ufc.com/'
EVENT = UFC + 'event/ufc-fight-night-november-07-2026'
# The archive uses two provider IDs for some fighters in different sources.
# Each listed Cito ID is reviewed against the dated matchup and UFC profile.
IDENTITIES = (
    ('f39ca6c4-d608-41e0-939e-5f581df28768', 'Lucas Fernando', 'lucas-fernando', 'e2a04d57-e951-4163-8ced-dc57a8b81047'),
    ('e4dc8d85-7f37-4d0f-8b7c-f00b913324c8', 'Nina Milošević', 'nina-milosevic', None),
    ('27a49aff-0106-4c6a-ba10-528ffc4f3ee6', 'Marcos Degli', 'marcos-degli', None),
    ('79e1f6d2-4cfd-4d37-9277-8dd2ab83835f', 'Gabriel Lorenço', 'gabriel-lorenco', None),
    ('57414bcb-54af-4efd-8029-cee43d38f303', 'Murtazali Magomedov', 'murtazali-magomedov', '91d58ecd-8b2c-4c27-961f-be3a1194d215'),
    ('84760727-5bb0-4146-8d8a-75ed7fc282d6', 'Jose Delano', 'jose-delano', '5ba94cb0-7d50-480f-ac35-32b951b3e25c'),
    ('242a9091-9cd6-47da-93d3-6cd3d1482071', 'Carlos Calderon', 'carlos-calderon', 'a89f8461-8fde-476a-955d-32f58b971049'),
    ('29d9fb0c-e709-4ac8-8e94-a9e31b854575', 'Mantas Kondratavičius', 'mantas-kondratavicius', 'd714fa75-e560-451d-9c52-8a40505b8f81'),
    ('4919764f-b74e-40ba-b57b-e3eeef512bdf', 'José Souza', 'jose-souza', None),
    ('690db284-c298-4c79-9228-18996fd0cee9', 'Ding Meng', 'ding-meng', '63b37800-d7fa-4ebb-b828-cc80007b816b'),
    ('316a2b77-01c2-4caf-9386-1281b8afde7b', 'Cam Nelson', 'cam-nelson', None),
)
NEW_IDS = {'Cam Nelson': 'ae8f10d8-fa4f-442b-b6b7-5a5311988709', 'Nina Milošević': '0f342172-0296-46aa-9bb7-85b1a80f013d', 'Marcos Degli': '99177fcf-6238-4a95-9dea-19d445dfeba6', 'Gabriel Lorenço': '083319ae-9815-4c20-9731-5cf60a01396b', 'José Souza': 'c9487215-6157-4d6d-8e6d-715f9b13da0d'}
RESULTS = {
    'Johnny Walker': ('KO/TKO', 3, '2:27'),
    'Tatiana Suarez': ('Decision - Unanimous', 3, '5:00'),
    'Elijah Smith': ('KO/TKO', 1, '1:00'),
    'Lucas Fernando': ('Decision - Unanimous', 3, '5:00'),
    'Nina Milošević': ('KO/TKO', 2, '3:40'),
    'Mitch Raposo': ('Decision - Unanimous', 3, '5:00'),
    'Ollie Schmid': ('Decision - Unanimous', 3, '5:00'),
    'Thomas Petersen': ('KO/TKO', 3, '4:47'),
    'Karine Silva': ('Decision - Unanimous', 3, '5:00'),
    'Murtazali Magomedov': ('Decision - Unanimous', 3, '5:00'),
    'Austin Bashi': ('Submission', 1, '1:07'),
    'Andre Petroski': ('KO/TKO', 2, '4:39'),
    'Seokhyeon Ko': ('Decision - Unanimous', 3, '5:00'),
    'José Souza': ('KO/TKO', 1, '4:16'),
}
BACKFILLS = {
    '8817bd21b6d0a989': 'mantas-kondratavicius',
    '7924f10aac3543de': 'jose-delano',
    'bc0b3c16246e0d1d': 'jose-souza',
    'e4849375d1949c74': 'murtazali-magomedov',
    'f78f34ef2ee7b02c': 'nina-milosevic',
    '13011': 'lucas-fernando',
    '6cd4457edf4089f9': 'ding-meng',
}


def main():
    if ARCHIVE.exists() or DB.exists():
        raise ValueError('Use fresh release directories.')
    hashes = {str(Path(__file__).resolve()): _digest(Path(__file__))}
    prior = _manifest(PRIOR, hashes)
    payload, _, _ = _read_card(CARD)
    listing, event, stats = (payload[key] for key in ('bouts', 'event', 'stats'))
    assert event['eventDate'] == '2026-11-07'
    hashes.update({str(path): _digest(path) for path in CARD.glob('*.json')})
    ids = {str(row['id']) for row in listing}
    assert len(ids) == len(listing) == len(RESULTS)
    for source in (event, stats):
        assert {str(row['id']): _bout_signature(row) for row in source['bouts']} == {
            str(row['id']): _bout_signature(row) for row in listing}
    assert all(str(row['boutId']) in ids for kind in ('boutStats', 'roundStats') for row in stats[kind])
    new_fights, new_stats, new_rounds = [], [], []
    for bout in listing:
        bid = str(bout['id'])
        totals, rounds = ([row for row in stats[key] if str(row['boutId']) == bid]
                          for key in ('boutStats', 'roundStats'))
        fight, paired, reconciled = normalize_completed_bout(bout, event, totals, rounds)
        assert RESULTS[fight['winner_name']] == (fight['result_method'], fight['result_round'], fight['result_time'])
        new_fights.append(fight)
        new_stats.extend(paired)
        new_rounds.extend(reconciled)
    assert {row['winner_name'] for row in new_fights} == RESULTS.keys()
    assert len(new_stats) == 28 and len(new_rounds) == 68

    registry = load_fighter_registry(PRIOR / 'fighter_registry.json')
    identities, links = list(registry.identities), list(registry.provider_links)
    names = {row.upset_fighter_id: row.display_name for row in identities}
    provider_ids = {row.provider_fighter_id for row in links if row.provider == 'cito'}
    profiles = rows(PRIOR / 'fighters_identified.jsonl')
    existing = {row['upset_fighter_id'] for row in profiles + rows(HISTORY / 'fighters_identified.jsonl')}
    evidence = rows(PRIOR / 'identity_link_evidence.jsonl')
    participants = {row['fighterId']: row['fighterName'] for bout in listing for row in bout['fighters']}
    assert participants.keys() - provider_ids == {row[0] for row in IDENTITIES[:-2]}
    for pid, name, slug, uid in IDENTITIES:
        assert pid not in provider_ids
        if pid in participants:
            assert participants[pid] == name
        if uid is None:
            assert name not in names.values()
            uid = NEW_IDS[name]
            identities.append(FighterIdentity(uid, name))
        else:
            name = names[uid]
        source = UFC + 'athlete/' + slug
        note = {'cito_fighter_id': pid, 'upset_fighter_id': uid, 'name': name,
                'public_sources': [source, EVENT], 'reviewed_at': '2026-11-08'}
        links.append(FighterProviderLink('cito', pid, uid, json.dumps(note, sort_keys=True)))
        evidence.append(note)
        if uid not in existing:
            profile = Fighter('cito', pid, slug, name, source_url=source)
            profiles.append({**asdict(profile), 'upset_fighter_id': uid})

    old_fights = rows(PRIOR / 'fights.jsonl')
    accepted = {row['source_bout_id'] for row in rows(PRIOR / 'identified/fights_identified.jsonl')}
    queue = json.loads((PRIOR / 'review.json').read_text())
    assert BACKFILLS.keys() <= set(queue['withheld_prior_bout_ids'])
    assert not ids & {row['source_bout_id'] for row in old_fights}
    all_fights = old_fights + new_fights
    all_stats = rows(PRIOR / 'fight_stats.jsonl') + new_stats
    included = accepted | ids | BACKFILLS.keys()
    queue['withheld_prior_bout_ids'] = sorted({row['source_bout_id'] for row in all_fights} - included)
    queue['unresolved_fighter_identities'] = [row for row in queue['unresolved_fighter_identities']
                                             if row['cito_fighter_id'] not in {entry[0] for entry in IDENTITIES}]
    queue['walker_card_review'] = {'event': EVENT, 'backfills': {bid: UFC + 'athlete/' + slug for bid, slug in BACKFILLS.items()}}
    with TemporaryDirectory(dir=ARCHIVE.parent) as tmp:
        folder = Path(tmp) / 'reviewed'
        folder.mkdir()
        save_fighter_registry(FighterRegistry(tuple(identities), tuple(links)), folder / 'fighter_registry.json')
        provenance = rows(PRIOR / 'bout_provenance.jsonl') + [
            {'source_bout_id': bid, 'event': event['slug'], 'raw_stats_sha256': hashes[str(CARD / 'stats.json')],
             'totals_basis': 'provider_totals_reconciled_with_rounds', 'provider_fight_totals_present': True}
            for bid in sorted(ids)]
        for name, batch in (
            ('fights.jsonl', all_fights), ('fight_stats.jsonl', all_stats),
            ('fighters_identified.jsonl', profiles), ('identity_link_evidence.jsonl', evidence),
            ('rounds_staged.jsonl', rows(PRIOR / 'rounds_staged.jsonl') + new_rounds),
            ('bout_provenance.jsonl', provenance),
            ('accepted_fights.jsonl', [row for row in all_fights if row['source_bout_id'] in included]),
            ('accepted_fight_stats.jsonl', [row for row in all_stats if row['source_bout_id'] in included]),
        ):
            _write_verified(folder / name, batch)
        (folder / 'review.json').write_text(json.dumps(queue, ensure_ascii=False, indent=2) + '\n')
        staged = stage_completed_fights(folder / 'accepted_fights.jsonl', folder / 'accepted_fight_stats.jsonl',
                                       folder / 'fighter_registry.json', HISTORY / 'fights_identified.jsonl',
                                       folder / 'identified')
        staged['input_paths'] = {'registry': str(ARCHIVE / 'fighter_registry.json'),
                                 'historical': str(HISTORY / 'fights_identified.jsonl')}
        (folder / 'identified/manifest.json').write_text(json.dumps(staged, indent=2) + '\n')
        manifest = {**prior, 'status': 'Reviewed November 7 card and seven related archived bouts',
                    'latest_bout': event['eventDate'], 'acquisition_through_date': event['eventDate'],
                    'identified_current_bouts': len(included), 'canonical_current_bouts': len(all_fights),
                    'canonical_fighter_stats': len(all_stats), 'new_bouts': len(ids),
                    'backfilled_bouts': len(BACKFILLS), 'new_identities': len(identities) - len(registry.identities),
                    'identity_links_added': len(IDENTITIES),
                    'unresolved_provider_fighters': len(queue['unresolved_fighter_identities']),
                    'bouts_awaiting_identity_review': len(queue['withheld_prior_bout_ids']),
                    'current_round_rows': len(rows(folder / 'rounds_staged.jsonl')),
                    'identified_subset_manifest': staged, 'input_sha256': hashes,
                    'output_sha256': {str(path.relative_to(folder)): _digest(path)
                                      for path in folder.rglob('*') if path.is_file()}}
        (folder / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
        folder.rename(ARCHIVE)
    build_database(HISTORY, ARCHIVE, ARCHIVE / 'fighter_registry.json',
                   PROCESSED / 'cito_historical_rounds_v1', DB)
    print(verify_preservation(OLD_DB, DB / 'upset.sqlite'))


if __name__ == '__main__':
    main()
