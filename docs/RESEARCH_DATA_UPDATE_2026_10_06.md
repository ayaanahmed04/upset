# October 5 Chicago / October 6 UTC: correct serving snapshot and fighter gaps

The screenshots show the viewer using `research_v2`: 8,799 bouts through
September 26, hence the strict Before cutoff of September 27. UFC 332 was
already captured in the completed October 5 refresh (14 canonical bouts,
9 with accepted identity links). The running server never switched databases.
No new acquisition is necessary for this update.

Harry Hardwick's March 14 bout was excluded because Marwan Rahiki's Cito ID
was unresolved. Rahiki and Tommy McMillen already have permanent historical
profile identities but no linked current bouts. Ollie Schmid has no historical
profile/candidate and needs a new identity. This is a known cohort coverage
problem, not missing raw stats or a date-filter bug; other fighters remain
incomplete until their identities are reviewed.

## Reviewed repair

`integrate_cito_rahiki_identities.py` checks the exact saved history hashes,
provider IDs, candidate IDs, dated opponents, winner, method, round and clock.
It applies the three individually reviewed rules in sequence, writes a new
registry overlay and restages complete paired stats. Existing canonical fight,
stat and provenance bytes stay unchanged. Existing accepted bouts cannot be
lost. New Ollie identity is a fixed UUID4 and a minimal verified profile with
unknown demographic fields left null. UFC record excludes DWCS.

Public primary identity anchors reviewed on October 6 UTC:

- https://www.ufc.com/athlete/harry-hardwick
- https://www.ufc.com/athlete/marwan-rahiki
- https://www.ufc.com/athlete/tommy-mcmillen
- https://www.ufc.com/athlete/ollie-schmid

Search-indexed UFC histories match the saved dated fights. Direct public page
fetches were blocked. Evidence does not assert independent verification of
every measured statistic or full calendar coverage.

`build_research_db.py` admits supplementary profiles only when bound to the
verified current manifest, matching the reviewed provider link and display
name. It rejects collisions with historical profiles. `export_cito_refresh.py`
carries these profiles into later refresh exports.

Observed real saved-data integration here: three links, five newly identified
bouts; 264 current bouts accepted, 89 pending, 98 unresolved provider identities.
Research build: 4,456 profiles, 8,815 bouts, 17,630 stat rows through October 3;
Harry 0–2 (2 bouts), Rahiki 2–1 (3 bouts), Tommy 3–0 (3 bouts), Ollie 0–1 (1).
The historical fights and stat JSONL recovered from the uploaded research_v2
SQLite match their accepted SHA-256 values exactly. The three result amendments
were preserved from that database in the local verification fixture. This is
not a rerun against the full original historical-round export. The Mac command
uses its genuine accepted export and original historical files. Mac execution
and installation of this particular update are not yet confirmed.

New immutable outputs:

- `data/processed/cito_current_rahiki_v1`
- `data/processed/research_rahiki_v1`

Start the site using the second directory's `upset.sqlite`. The default Before
cutoff is October 4, because dates are strictly exclusive. Only nine of UFC
332's fourteen bouts currently have accepted identities; five remain pending.
No model was changed or retrained. No API requests are required.

## Homepage feature

Edit only the `PICKS` array in `src/upset/web/research.html`:

```js
const PICKS=['Brendan Allen','Christian Leroy Duncan'];  /* featured matchup */
```

Both lookups and rendering now use that array; there are no duplicate
Oliveira/Holloway keys to edit. Use exact fighter display names shown in search.
The feature is currently set to the October 10 main event, confirmed against:
https://www.ufc.com/event/ufc-fight-night-october-10-2026
https://www.ufc.com/news/tickets-sale-october-10-october-31-and-november-7-ufc-fight-night-events-meta-apex
It remains a manually selected homepage feature, not an automated schedule.
Refresh after editing; HTML-only edits need no server restart.

## After the Cito subscription

Existing downloads and offline rebuilds do not require an active key. New
results still need a source. Current Cito collection requires usable Cito
access; it will not automatically switch after cancellation. Public UFCStats
exposes event listings, fight totals and rounds, and is the intended candidate
for an incremental replacement collector feeding the same canonical models,
identity registry, validation and new database outputs. That collector has
not been implemented/tested in this repository. Availability and publication
lag need to be checked during implementation; no guaranteed free service is
implied. Hand-entering every count should not be the normal workflow. Build
and verify the replacement before relying on it for weekly updates.

Validation: 32 focused identity/research/refresh tests plus UI/hero source checks pass;
real saved cohort and generated API reports checked as described above.
