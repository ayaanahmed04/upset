# Normalize the cached current UFC archive

The historical round integration passed on the Mac on September 30, 2026.
Mac commit `ebc776c` is the cherry-pick of remote
`97b8dfaf63e1b29ee40e450eb9e98e0b2eb9dc13`. The gap supplement added two
historical bouts, eight round rows and one Cito registry link. The combined
historical subset is **8,540 bouts / 40,276 fighter-round rows**. Eleven
historical bouts still lack Cito rounds; their accepted historical fight
totals remain available. The supplement also rechecked eight current round
rows and exported four explicitly derived fighter totals. One supplemental
result clock needs review: Shi Ming–Bruna Brasil, provider `15:00` versus
historical final-round clock `5:00`. See `CITO_GAP_RECONCILIATION.md`.

## Current data step

```bash
python -m upset.data.export_cito_current_archive
```

This runs offline against `data/raw/cito_archive`,
`data/processed/cito_archive_bridge_v2`, the accepted historical-round export
and the verified gap supplement. Default output is
`data/processed/cito_current_archive_v1`. Repeating reuses intact output after
checking all hashes; changed input/output requires a new immutable directory.
No API key, requests, historical rewrite, registry edit or model fit is used.

The uploaded review contains **339 current bout records**, March 14 through
September 26, 2026. All have completed source status. Four are nondecisive:
three draws and a no-contest. The listed method variants include KO/TKO,
submission, unanimous/split/majority decisions, DQ and CNC. The exporter accepts
these observed classifications while retaining their raw source evidence.

It validates source hashes and dated observations, raw card identity, agreement
of result/participant fields between endpoints, paired totals, complete rounds,
observed sums, result clocks/control bounds and source winner consistency.
The two September 12 bouts with missing provider totals require the verified
derived supplement. Their provenance says `derived_from_complete_rounds` and
`provider_fight_totals_present: false`; the provider gap remains visible.

Every examined bout either appears in the canonical output or has an explicit
validation issue in `review.json`. Any bouts without reviewed Cito identity
links stay outside the identified subset. Name matches produce candidates,
never links or new identities. Existing embedded Cito profile observations
are included for later review; current photos/records are not model features.
All normalized round rows retain provider fighter IDs and known canonical IDs.

## Output files

| File | Purpose |
| --- | --- |
| `fights.jsonl` | Canonical current bouts with decisive or Draw/NC labels |
| `fight_stats.jsonl` | Two canonical fighter totals per normalized bout |
| `rounds_staged.jsonl` | Current rounds with source and identity evidence |
| `bout_provenance.jsonl` | Capture timestamps, hashes and provider/derived total basis |
| `identified/` | Existing staging contract applied to bouts with verified identities |
| `review.json` | Validation issues and unresolved fighter identities with name-only candidates |
| `manifest.json` | Counts, hashes, provenance and zero API calls |

The identified subset uses the existing `stage_completed_fights` checks for
historical cutoff, reviewed identities, paired totals and duplicate dated
matchups. A names-only candidate does not pass that contract. `training_ready`
and independent UFC `coverage_verified` remain false. The original research
model, historical data and tracked registry remain unchanged.

The full current export passed on the Mac at commit `a8570e6`: 339 normalized
bouts, 678 fighter totals, 1,534 round rows, zero validation issues, 245
identified bouts and 94 bouts awaiting evidence for 101 provider identities.
There are 337 bouts with observed provider totals and two with derived totals.
The uploaded output hashes were verified. Independent recalculation from all
current rounds agrees with all 8,814 canonical total fields.

The identity queue has 41 single name candidates, 59 without a name candidate
and one duplicate-name case. These are candidates, not accepted links.
`collect_cito_fighter_bundles` preserves the documented profile/stat/history
responses for these identities; see `CITO_FIGHTER_BUNDLES.md`.

Next: review the generated identity candidates using independent evidence,
verify the UFC calendar, then use the existing as-of/frozen forecast pipeline.
The eleven missing historical round records need not block this current-data
work. Do not repeatedly rerun acquisition or tune the old development folds.
