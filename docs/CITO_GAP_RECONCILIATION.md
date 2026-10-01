# Offline reconciliation of the September 30 gap probes

The Mac export succeeded after resolving the status-document conflict:
8,538 of 8,551 accepted historical bouts, 40,268 round rows, 2,644 Cito
identity links and 432 round rows with unavailable control. The seven scoped
name-alias cases passed the paired totals and full round-sum checks. Original
history, tracked registry and research model remain unchanged.

The uploaded integration ZIP includes the manifest, review, probe plan and all
48 saved responses. All included manifest output hashes and response hashes
were independently verified. The full exported round file and private accepted
historical stats were not in this ZIP; their numerical verification ran on the
Mac, and the new supplemental historical verification also runs there.

## What the responses actually contain

* Eleven historical bouts still have no totals or rounds. Their provider IDs
  return HTTP 200 with empty lists; 18 alternate-ID requests return HTTP 404.
  They are five bouts from September 6, 2025 and six from November 22, 2025.
* The two August 22, 2025 Road to UFC bouts return four totals and eight round
  rows via the event endpoint. Requested historical IDs resolve to different
  canonical Cito IDs. The bout and event endpoints agree on the numerical rows,
  and every observed provider total reconciles with the rounds. Acceptance
  additionally requires agreement with both private historical fighter totals.
* Both September 12, 2026 endpoints return rounds but an empty `boutStats` list.
  A positive returned-row count did not mean fight totals had been recovered.
  Four totals can be derived from eight complete fighter-round rows; they are
  marked as derived and never represented as provider totals.
* Shi Ming–Bruna Brasil has provider clock `15:00`, versus historical final-round
  clock `5:00`. Both observations remain explicit; no revision date or clock
  interpretation is invented. Uppercase method labels are only cosmetic.

The 44 `requires_provider_review` entries count requests, including alternate
IDs and four successful Road to UFC responses whose returned IDs differ. They
do not describe 44 missing bouts.

## Run once, offline

```bash
python -m upset.data.reconcile_cito_gap_probes
```

Default output: `data/processed/cito_gap_reconciliation_v1/`.
No API key or network requests are used. Existing intact output is reused;
changed inputs or output hashes require a new immutable output directory.

The command verifies all accepted-export and bridge output hashes, probe URL,
plan, raw response hashes, dated observations, historical input hashes, both
participants' identities, full paired round coverage, all observed provider
round sums, and at least 12 accepted historical fields for each fighter. It
also compares current probe rounds with the already captured card's staged
round rows. Missing control remains null, including when summing rounds.

Outputs:

| File | Purpose |
| --- | --- |
| `historical_rounds_additional.jsonl` | Verified historical additions only |
| `historical_bout_results.jsonl` | Frozen results and explicit provider differences |
| `fighter_registry.json` | Existing evidence-backed registry plus verified new links |
| `current_rounds_staged.jsonl` | Rechecked current rounds, with known identities where available |
| `current_totals_derived.jsonl` | Round-summed totals with `provider_fight_totals_present: false` |
| `provider_issues.json` | Remaining historical gaps and dated endpoint evidence |
| `manifest.json` | Input/output hashes, subset counts and zero API calls |

If the two historical comparisons pass on the Mac, the combined historical
subset is 8,540 bouts and 40,276 round rows, leaving eleven missing historical
round records. This is a separate supplement, not an overwrite or automatic
training-file merge. Identities without historical evidence stay unresolved.

## Work remaining

The eleven historical rounds can be pursued with Cito using the saved endpoint
evidence while retaining accepted historical fight totals. That support issue
does not need to block current integration. Normalize the 339 post-snapshot
staged bouts, resolve fighter identities and known source duplicates, verify
the independent UFC event calendar, then build frozen prospective forecasts.
Full calendar coverage and training readiness remain unverified.
