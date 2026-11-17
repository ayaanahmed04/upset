# Preserve source records for unresolved current identities

All 339 current bouts normalized successfully. The remaining identity queue
has 101 provider fighters across 94 bouts: 41 single name candidates, 59 with
none, and one duplicate-name case. A name candidate is not a verified link.

Cito documents three endpoints for a fighter slug:

- `GET /ufc/fighters/{slug}`: profile/bio context.
- `GET /ufc/fighters/{slug}/stats`: career aggregates and breakdowns.
- `GET /ufc/fighters/{slug}/fights`: source fight history.

Primary reference: https://docs.citoapi.com/docs/api/ufc/fighters/
Rate headers: https://docs.citoapi.com/docs/rate-limits/

The documentation does **not** promise a UFCStats ID/crosswalk or DOB in every
response. This collection preserves potentially useful identity and product
records, not a guarantee that the remaining links are resolved. Today's
career aggregates must not be injected into historical pre-fight features.

```bash
python -m upset.data.collect_cito_fighter_bundles --max-requests 303
```

Input: `data/processed/cito_current_archive_v1`. Output:
`data/raw/cito_fighter_bundles_v1`. Targets come from its verified review;
an embedded profile slug is preferred when its provider ID agrees, otherwise
one unambiguous recorded fighter slug is required. The actual uploaded export
produces 303 targets for 101 distinct provider IDs. All nine current input
files (manifest plus eight outputs) are hash-checked.

The collector logs each request, saves source URLs and observation times,
records relevant rate headers, uses 30-second timeouts and disables redirects.
Default delay is 2.2 seconds; an observed lower per-minute header slows it.
It caps new requests, reuses saved responses, and stops on 401/403/429.
Responses that identify a different provider fighter are retained for review;
that fighter's remaining endpoints are skipped. Missing IDs remain unverified.
No Cito key is written or printed. Credential echoes are rejected before saving.

`plan.json` fixes the targets and source-export hashes. Raw wrappers are under
`fighters/{provider_id}/{profile,stats,fights}.json`. `report.json` lists source
hashes, statuses, remaining targets, requests this run and any pause reason.
Repeating resumes targets not yet saved; successful and unsuccessful responses
are preserved rather than silently refreshed. A cached access/rate-limit
failure stops again and needs an explicitly reviewed retry strategy.

No identity links, permanent IDs, original registry files, model features or
forecasts change. Returned records require review against the canonical cohort
and independent identity evidence. Present-day career totals are source records
for analysis/product work, not temporally valid historical observations.

The previous current ZIP is already reviewed. The next small bundle only needs
this new fighter-evidence directory; do not rerun the archive collection or
upload the full historical dataset again.
