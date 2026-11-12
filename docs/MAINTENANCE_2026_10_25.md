# October 25, 2026 maintenance

The live viewer at http://127.0.0.1:8767 now uses
`data/processed/research_2026_10_25_v1/upset.sqlite` in broadcast mode with
`data/roster/roster.json`. The homepage features Renato Moicano vs Tom Nolan.

| Card | Event date (provider convention) | Added bouts |
| --- | --- | ---: |
| Allen vs Duncan | 2026-10-10 | 12 |
| Buckley vs Malott | 2026-10-17 | 13 |
| UFC 333: Volkanovski vs Evloev | 2026-10-24 | 14 |

The validated database has 4,464 profiles, 8,854 bouts, and 17,708 stat rows.
All 4,456 prior profiles, 8,815 prior fights, and 17,630 prior statistical rows
are preserved exactly. Eight new identities were allocated; ten existing
identities gained reviewed Cito links. The 89 previously excluded bouts remain
withheld. Their inclusion policy was deliberately preserved, including earlier
bouts whose participants now have reviewed links. Independent all-calendar
coverage remains unverified; the manifest retains `coverage_verified: false`.

Cito supplied totals and complete reconciled round rows for all 39 new bouts.
No statistical measurements were fabricated or filled with zero. Draw results
remain distinct from NC and decisive results. Every result target in the handoff
was reconciled to the captured provider data. Official event results and
scorecards were reviewed for the new event outcomes and identity anchors:

- [Allen/Duncan scorecards](https://www.ufc.com/news/ufc-fight-night-allen-vs-duncan-official-scorecards)
- [Buckley/Malott scorecards](https://www.ufc.com/news/ufc-edmonton-official-scorecards-buckley-vs-malott)
- [UFC 333 scorecards](https://www.ufc.com/news/ufc-333-volkanovski-vs-evloev-official-scorecards)
- [UFC 333 main results](https://www.ufc.com/news/ufc-333-volkanovski-vs-evloev-results)
- [Upcoming Moicano/Nolan event](https://www.ufc.com/event/ufc-fight-night-october-31-2026)

Some UFC athlete-page result badges contradict their own narrative and the event
scorecards. Event results govern this import. Existing profile measurements and
DOBs were preserved when current profile observations differed. New profiles
have null unavailable demographics and no invented active status or portrait.
Tom Nolan had no existing roster portrait; his comparison continues to use the
existing fallback. Moicano, Volkanovski, and Yan portrait endpoints were checked.

Volkanovski and Yan retained their undisputed belts. Two reviewed retention
events were appended to `data/champions/champions.json`, effective October 25
under the existing strict-before-date contract. The original champion snapshot
and prior ledger events are unchanged. No historical defense count was inferred.

## Artifacts and validation

- Raw cards: `data/raw/cito_refresh_2026_10_25_v1` (26 requests: 17 inventory + 9 card endpoints).
- Identity evidence: `data/raw/cito_identity_review_2026_10_25_v1` (nine saved bundles reused; 18 requests for nine uncached fighters).
- Normalized cohort: `data/processed/cito_current_2026_10_25_v1`.
- Reviewed cohort: `data/processed/cito_current_2026_10_25_reviewed_v1`.
- Explicit reviewed rules: `data/mappings/cito_2026_10_25_reviewed_identities.json`.
- Offline integration: `scripts/integrate_october_2026_identities.py`.
- Serving manifest: `data/processed/research_2026_10_25_v1/manifest.json`.
- Validation evidence: `data/processed/maintenance_2026_10_25_validation.json`.
- Live API/asset checks: `data/processed/maintenance_2026_10_25_live_checks.json`.

SQLite integrity and foreign-key checks passed. All 78 participant cutoff checks
passed: a bout is excluded on its event date and included the following day.
All 36 selected refresh, identity-registry, export, and viewer tests passed.
The live search, featured comparison/common-opponent response, newcomer history,
championship status, portrait endpoints, and both belt assets passed checks.
`git diff --check` passed. Browser verification showed 8,854 bouts through
October 24 and the requested featured matchup.

Database SHA-256: `5f33dfb636701bf1126e7bd5fee1539173bc2009219db27c4d393055b6bdc9bd`.
The original database is still at `data/processed/research_rahiki_v1/upset.sqlite`
with SHA-256 `48e60ffc832216e93e81b64170e998b368d2e5a9af60e1c62e3e726ce5768607`.
No replay, training, model fitting, commit, push, branch switch, subscription
renewal, or archive reacquisition was performed.

## Preservation and running the viewer

Pre-edit backup: `backups/maintenance-20261025-143921-374646`.
It contains 443 original source/configuration/roster/media files, their hashes,
staged and unstaged Git patches, Git status, a consistent SQLite backup, and the
old serving manifest. Existing source changes, portraits, belts, and registry
files are intact. The only pre-existing files intentionally changed were the
one-line homepage selection and the append-only championship ledger.

The exact original viewer process was verified before stopping it. One viewer
now listens on 8767; unrelated processes and tunnels were left alone. It runs
under `caffeinate -i` with its output in the backup folder's `viewer.log`.
`viewer-process.json` records the launched command. The current listener PID was
58495 when verified; inspect the port before acting because PIDs are temporary.

The viewer is already running. For a future restart, stop only that viewer,
then use this complete command:

```bash
cd ~/Projects/upset
source .venv/bin/activate
caffeinate -i python -m upset.research_app \
  --database data/processed/research_2026_10_25_v1/upset.sqlite \
  --design broadcast \
  --roster data/roster/roster.json \
  --port 8767
```

Hard refresh the browser with Cmd+Shift+R. To roll back the dataset, stop the
viewer and use the same command with
`--database data/processed/research_rahiki_v1/upset.sqlite`. For the old database,
restore the original championship ledger from this backup to keep its belt
history consistent; the two newer reviewed fights do not exist in that old DB.
Restore the old feature only by replacing the PICKS line with the backed-up
names. Do not restore whole older HTML/source files over later user changes.
