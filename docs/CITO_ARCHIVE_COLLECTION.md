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

Passing structural checks does not verify the numerical totals, fighter
identities, or independent UFC calendar coverage. The two spot checks compare
bout and round-row counts only; Cito support's completeness statement is
source testimony until the numbers and calendar are separately reconciled.

The report also includes the raw bout, total-stat and round-stat rows behind
each bout finding, together with the captured card manifest hash. A name
disagreement is reported separately from an incorrect total-row count; it
does not establish that statistics are missing. Names are not silently
treated as aliases. All event inventory entries and provider titles are
included to review duplicate listings and the heuristic competition labels.
