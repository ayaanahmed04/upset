# Cito archive acquisition

The one-card August 29 pilot proved that the event, bout and event-stat APIs
can return a complete recent card. Cito support told Ayaan on September 28
that Pro grants access to the full UFC archive, including the March–August
2026 gap, and that one month of locally retained responses may be used for
personal noncommercial research after cancellation. These are provider
statements, not independent proof that every historical round row exists.

`collect_cito_archive` first caches the provider's paginated **unfiltered**
event listing, including events marked without stats. Each raw page has a
source URL, UTC observation time and verified SHA-256 in the completed
inventory manifest. Then it calls the already tested three-endpoint card
collector for events marked `hasStats=true`. The ignored raw directory is
resumable; successful cards are never refetched, and statless or failed cards
stay visible in `collection_progress.json`. A failed card is retried only with
`--retry-failed`. Neither stage asserts independent UFC calendar coverage.
Repeated slugs with distinct event IDs or dates remain in the inventory and
are listed in `slug_collisions`. If more than one such listing claims stats,
the batch records `ambiguous_slug` and requests neither by that ambiguous
slug. A statless stray listing does not block a single stat-bearing card.

From the project root, with `.venv` active and the key in ignored `.env`:

```bash
# One page first; inspect the summary and a raw page before a large run.
python -m upset.data.collect_cito_archive inventory --max-pages 1

# Resume saved pages; a completed inventory prints its event count and hash.
python -m upset.data.collect_cito_archive inventory --max-pages 100

# Pilot a single recent and a single older card from the completed inventory.
python -m upset.data.collect_cito_archive cards \
  --from-date 2026-03-08 --through-date 2026-09-28 --max-cards 1
python -m upset.data.collect_cito_archive cards \
  --from-date 2026-03-08 --through-date 2026-03-31 --max-cards 1

# Once the two pilots are reviewed, resume through the rest of this window.
python -m upset.data.collect_cito_archive cards \
  --from-date 2026-03-08 --through-date 2026-09-28 --max-cards 1000

# The older available archive uses the same inventory and card cache.
python -m upset.data.collect_cito_archive cards \
  --from-date 1994-03-11 --through-date 2026-03-07 --max-cards 2000
```

`--max-pages` and `--max-cards` are **caps per run**, not promises of a
complete download. Re-run with a higher cap after partial inventory, or the
same card command to resume. The cache prevents repeated successful calls.
The inventory includes all event listing rows, including scheduled events and
other competitions; the chosen date window and `hasStats` determine which
cards are attempted. Inspect the provider inventory against an independent
UFC calendar before claiming complete UFC coverage. One event page is at most
50 rows; every eligible card requires at most three new requests, spaced by
seven seconds, plus a seven-second inter-card pause. Provider request quota
and actual page counts must be checked from the completed inventory.

Known provider anomalies reported to Ayaan: a stray no-stat `ufc-315` event
dated May 10, 2026, a duplicate July 18 Ezra Elliott bout, and a duplicated
Rafa Garcia stat row on April 25. The raw collector **does not discard** any
of them. Review their raw evidence and record explicit exclusions only in a
later normalization and coverage audit. UFC 326's March 7 US date corresponds
to March 8 UTC and may already be in the accepted historical snapshot; avoid
double counting by event and bout identity, not a naive UTC date boundary.
Contender Series and Road to UFC records are outside the UFC-only baseline;
inventory classification must be reviewed before inclusion.

The existing `export_cito_card` validates only the observed post-March 2026
shape and rejects older dates. Raw archive acquisition does **not** make old
rounds model features, link fighter identities, overwrite the accepted Kaggle
snapshot or establish that 1994–2026 round data is complete. Subsequent work
must audit per-event inventory and stat availability, inspect source changes
by era, normalize compatible records, and independently verify UFC coverage.

## Read-only structural audit

After collection and any targeted retries, run:

```bash
python -m upset.data.audit_cito_archive
```

The command makes no API calls and never edits raw files. It checks cached
manifest and page hashes, compares the event detail to the inventory, and
counts completed stat-bearing bouts with exactly two fighter totals and one
round row per fighter per reported round. It prints aggregate statuses and
the two provider-confirmed March 14 and June 6 spot checks. The detailed
findings and all provider-statless event labels go to the ignored processed
file `data/processed/cito_archive_audit_v1.json`. Competition labels are
heuristics based on event slugs; manually review ambiguous entries. The
statless May 2026 `ufc-315` remains in that list. A Road to UFC event that
failed collection is also left in the report rather than silently omitted.

Passing structural checks does not establish independent UFC calendar
coverage or accuracy against another source. The audit now separately counts
bouts whose round sums reconcile to supplied totals for all nine strike and
takedown pairs, knockdowns, submissions, reversals and control time. Invalid
numerical fields and unequal sums remain explicit findings. The provider's
explicit `controlTime="--"` marker stays unavailable, separate from errors.
This is internal consistency, not a comparison with official recorded stats.

The report also includes the raw bout, total-stat and round-stat rows behind
each bout finding, together with the captured card manifest hash. A name
disagreement is reported separately from an incorrect total-row count; it
does not establish that statistics are missing. Unique matching slugs,
normalized spellings, embedded profile names and explicitly reviewed aliases
scoped to provider fighter IDs can resolve spelling differences. Conflicting
or ambiguous matches remain findings. Resolved differences are listed in the
report; raw rows are never renamed. All event inventory entries and provider titles are
included to review duplicate listings and the heuristic competition labels.

## September 30 evidence review and targeted endpoint probes

The saved v2 report contained 77 name disagreements and two bouts without
supplied totals. Reviewing those 77 bouts with unique participant matching
found complete rounds, and every supplied numerical field reconciled. In
particular, March 14's Jose Miguel Delgado/Jose Delgado bout has both totals
and six round rows; it is not a missing-bout example. The two September 12
bouts (Djorden Santos/Yousri Belgaroui and Rongzhu/Rafa Garcia) have round rows
but no supplied totals in either the event stats or embedded bout evidence.
Keep them flagged; do not represent round-derived totals as provider totals.

Nickname reviews use the captured fighter profiles and official UFC pages:
<https://www.ufc.com/athlete/ronaldo-souza>,
<https://www.ufc.com/athlete/alberto-pereira> and
<https://www.ufc.com/athlete/max-grishin>. Delgado's short and full names
appear under the same fighter ID in the captured source profiles and rows.
TUF **Finale** cards and the named Ortiz/Shamrock finale are UFC candidates;
this does not admit TUF exhibition episodes to the baseline.

The 35 statless UFC listings in the v2 inventory are named 2024–2025 cards.
No captured event exists within one day of those listings in that inventory.
They cannot be dismissed as duplicate aliases. The collector skipped them
because of provider `hasStats=false` metadata. Probe the actual stats endpoint:

```bash
python -m upset.data.audit_cito_archive \
  --output data/processed/cito_archive_audit_v3.json
python -m upset.data.probe_cito_statless \
  --through-date 2026-09-28 --max-events 50
```

The probe issues one request per targeted past UFC listing, seven seconds
apart, and prints progress immediately. It preserves successful and error
JSON responses, observation times and hashes under ignored
`data/raw/cito_archive/statless_probes_v1/`, with a summary `report.json`.
It checks returned event identity before labeling stats returned. This label
means totals and rounds are present, not that every bout is complete.
Future cards, other competitions and already captured cards are not queried;
inventory and collection progress are unchanged. Repeating resumes cached
probes without refetching, including saved errors. A deliberate fresh probe
can use a different `--output` directory. The 35-card batch is at most 35
requests; network time varies, with about four minutes of pacing alone.
Actual endpoint evidence will decide whether to recover cards locally or
request missing archive data from Cito during the paid access window.

## Recovering the 35 cards from saved endpoint evidence

All 35 probes returned totals and rounds despite the event's false availability
flag. The responses contain 424 listed bouts, including 414 marked completed
whose totals and rounds reconcile. Ten others have stats but are still marked
`confirmed`; their outcomes are null, and four also lack result details. Their
statistics are retained, but they need result/status review before model use.
The archive audit now lists all excluded bouts and flags excluded bouts that
nevertheless contain stats. It does not infer winners from strike counts.

The v3 report's 181 unreadable numerical flags all have `controlTime="--"`
in 1994–1999 cards. Reviewing their remaining supplied fields found exact
round-to-total agreement. The audit now reports these as unavailable fields,
not corrupt counts or zero control. `numerically_reconciled_bouts` requires
every field; `observed_stats_reconciled_bouts` allows the explicitly unavailable
control field while still checking every other supplied stat.

Finish the full card cache and rerun the audit:

```bash
python -m upset.data.recover_cito_statless --max-cards 50
python -m upset.data.audit_cito_archive \
  --output data/processed/cito_archive_audit_v4.json
```

Recovery verifies the probe hashes and inventory identity before requesting
anything. It rewraps the saved stats response into the existing card-cache
format, retaining its actual `/stats` source URL and original observation
timestamp. It fetches only the event detail and bout listing still needed:
at most 70 requests for 35 cards, spaced seven seconds apart. No stats are
refetched and the original 755 cards are untouched. Both the original false
inventory flag and probe hash remain in recovery provenance. Inventory and
probe files stay immutable; collection progress is updated per completed
card and a local `statless_recovery_report.json` records the run. Repeat the
recovery command to resume partial requests; captured cards are skipped.
The complete summary should show 790 captured cards if every recovery succeeds.
The v4 audit may reveal cross-endpoint metadata differences; raw acquisition
never certifies independent calendar coverage, canonical linking or training
readiness. Historical dates and results still need comparison with the accepted
Kaggle snapshot before joining the Cito round archive to model histories.
