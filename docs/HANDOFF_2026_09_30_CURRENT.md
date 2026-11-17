# UPSET handoff — September 30, 2026, current integration

This updates `HANDOFF_2026_09_30.md`; older pending-run counts in that document
are superseded below. Read `CITO_GAP_RECONCILIATION.md` and
`CITO_CURRENT_ARCHIVE.md` for code behavior and source limitations.

## Latest verified Mac state

The documentation cherry-pick conflict was resolved while preserving local
status notes. Mac `9329ce0` applied the historical-round acceptance batch.
Its export passed: 8,538 historical bouts, 40,268 round rows, 2,644 Cito links,
432 unavailable-control rows, three reviewed outcome overlays, one unresolved
clock. All seven scoped name-alias cases passed full private historical sums.

The integration ZIP was read. Included manifest output hashes and all 48 raw
response hashes agree. Eleven historical bouts still return empty source
lists. Four successful Road to UFC bout responses were classified for review
because the returned IDs differ from the requested historical IDs; they do
contain the expected rows, witnessed by event endpoints. September 12 stats
endpoints return rounds, not totals. Returned-row counts do not prove totals.

Mac `ebc776c` applied remote `97b8dfaf63e1b29ee40e450eb9e98e0b2eb9dc13`
and ran `reconcile_cito_gap_probes` successfully:

- Two historical bouts and eight round rows added; combined **8,540 / 40,276**.
- One new Cito registry link.
- Eleven historical bouts without verified rounds remain.
- Four derived current fighter totals and eight current round rows checked.
- One supplemental result metadata issue: provider total-time clock `15:00`
  versus frozen final-round clock `5:00` for Shi Ming–Bruna Brasil.
- Zero API calls; independent coverage/training readiness remain false.

Accepted original fights remain 8,551 / paired stats 17,102 through March 7.
Historical fight hash:
`a5b3076e08b540bef41529300d3e092dc2477f458bba88c1118ebe94a721c53e`.
Original labels, source hashes and registry are not overwritten. Reviewed
Idiris NC / Brundage draw / Bellato NC amendments remain separate from frozen
results; exact amendment availability dates cannot be inferred retrospectively.

## Current export passed

`export_cito_current_archive` normalizes the cached current cards offline and
uses the existing current staging contract on the verified-identity subset.
It does not acquire data or fit a model. Default output:
`data/processed/cito_current_archive_v1`.

Mac `a8570e6` applied remote `c74e3f8331ac6ba0cb6213cf076a0c656a94be43`.
It passed all **339 completed current records**, March 14 through September 26:
678 fighter totals, 1,534 rounds, zero validation issues and four nondecisive
outcomes. The identified subset has 245 bouts; 94 await identity evidence for
101 provider IDs. There are 337 provider-total bouts and two derived-total
bouts. The ZIP was read: all eight output hashes agree and all 8,814 canonical
total fields independently reconcile with its round rows.

There are 41 single name candidates, 59 without a name candidate and one
duplicate-name case. Do not assume these need 101 new identities; profile-only
historical identities may exist. Names alone never assign identities.

The exporter checks all accepted/supplement/bridge hashes and relevant raw
cards, result/participant agreement between endpoints, complete paired rounds,
all observed sums, declared winners and duration/control bounds. Missing totals
are accepted for staging only when the already verified derived supplement
agrees. It retains the distinction in per-bout provenance. Invalid bouts and
unknown identities remain explicit. The original registry/history/model stay
unchanged. Repeated runs verify/reuse intact output rather than downloading.

Assistant normalized the actual uploaded August 29 sample: 13 bouts, 26 totals,
50 round rows. Synthetic end-to-end tests cover names-only candidates staying
unlinked, verified subset staging, immutable files, hash changes, output reuse,
draw/NC consistency, full round coverage and derived-total evidence. Full Mac
current normalization is complete; independent UFC calendar coverage and the
remaining identity links are still pending.

The current ZIP is already available and reviewed. Do not request it or the
entire historical archive again. `collect_cito_fighter_bundles` is the next
bounded source capture: three documented endpoints for the 101 unresolved
fighters, maximum 303 new requests. It saves raw responses, dates, source
hashes and rate-limit headers; repeats reuse saved evidence. It never creates
links or uses current career aggregates as historical features. See
`CITO_FIGHTER_BUNDLES.md`. Review returned source fields rather than assuming
the endpoints contain a UFCStats ID or DOB. Direct UFCStats requests from this
environment returned a JavaScript browser-check page; no challenge bypass was
attempted. Some primary pages remain available through search indexes.

Resolve identity evidence, independently audit the UFC calendar and move to
the existing as-of feature and frozen prospective prediction pipeline.
Continue current work while the eleven 2025 round gaps are addressed.

## Model contract

The frozen 36-input symmetric recent + Elo logistic model is replay-verified;
SHA `55bf4a6f363c9c45bd3db008b74faab5927318b6614836e440024f52d9c8894c`.
The historical as-of audit already matched every row and all 36 inputs at zero
error. These systems are present, not missing. Development 1,071/1,857 and
best subsets 1,095/1,857 come from repeatedly examined folds; later 784/1,260
is also examined, not prospective. No clean 75% claim or scored externally
dated prospective forecast exists. Do not promote a variant from more slicing
of those same folds, and do not imply more rounds automatically improve picks.
