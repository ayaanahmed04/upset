# One real Cito card: raw acquisition pilot

The historical model stops at March 7, 2026. Before importing current fight
statistics, capture one recent completed card and inspect the provider's
actual event, bout and card-stat responses. The existing one-bout probes and
round audit do not establish a complete event inventory.

Run from the project root with its virtual environment active and a working
`CITO_API_KEY` in the ignored `.env` file. Discover a recent event slug with
`python -m upset.data.probe_cito_recent`, then run:

```bash
python -m upset.data.collect_cito_card --event EVENT_SLUG
```

The command makes at most three new requests, separated by seven seconds:
event detail, its bout listing and its card statistics. It saves the complete
JSON responses separately under `data/raw/cito_current/EVENT_SLUG/`, with the
source URLs, observation times, hashes and an unverified manifest. It prints
the **full count** of bout IDs in the listing, even though the old discovery
probe prints only the first ten. It rejects an explicitly paginated, empty or
internally inconsistent bout list. Existing component files are checked and
reused on retry, and a finished snapshot cannot be overwritten. To take a
second snapshot, supply a new `--output` directory.

If the stats request returns 403, the event and bout files remain cached and
there is no success manifest. Preserve the status and structured error code;
do not repeat an out-of-window request on the same account. Even when the
command succeeds, `coverage_verified` is **false**: the provider's listed
bouts have not been reconciled with an independent event calendar or checked
for two complete fighter-stat rows each. Do not feed the raw snapshot directly
to `stage_current` or `export_asof_features`.

The next step is to inspect the real saved response structures, then convert
the bouts and totals to the exact existing `Fight` and `FightStats` formats.
The converter must preserve named winner versus Draw/NC, event date, both
provider fighter IDs, source URLs, fight duration, control missingness and
target/position strike totals. Review new fighter links, stage the resulting
files, and run `audit_current_coverage` against a separately checked calendar.
No model promotion follows from the pilot.
