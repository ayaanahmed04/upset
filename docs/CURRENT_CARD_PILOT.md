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

## Canonical export from an observed card

Ayaan captured the completed August 29, 2026 Shanghai card on September 28.
The raw snapshot contains 13 listed completed bouts, 26 fight-total records
and 50 round-stat records. The saved hashes match the three uploaded source
responses. Event detail, bout listing and event stats agree on event identity,
all bout IDs and key result fields. Every round count adds up to its fighter's
fight total across the recorded stat fields. This is agreement within Cito;
the [official UFC event page](https://www.ufc.com/event/ufc-fight-night-august-29-2026)
confirms the card exists, but that page was not used to validate all 26
statistical records independently.

Run the converter against that exact raw snapshot:

```bash
python -m upset.data.export_cito_card \
  --card data/raw/cito_current/ufc-fight-night-august-29-2026 \
  --output data/processed/current/cito_aug29_canonical_v1
```

It validates the raw manifest, reconciles event/bout/stat response fields,
requires two complete fighter totals per bout, checks every round and then
writes immutable `fights.jsonl`, `fight_stats.jsonl`, a
`fighter_link_review.json` queue and a hash manifest. Source method codes
observed on this card are normalized explicitly: `SUB`, `U-DEC`, `S-DEC`,
and `KO/TKO`. Unknown outcomes or methods fail rather than becoming wins.
Five-minute rounds yield an elapsed fight duration from the result round/time.

Two fighters have different slugs in the bout and stat records: Yan Xiaonan
(`xiaonan-yan` versus `yan-xiaonan`) and Hector Santiago
(`hector-de-sousa-santiago` versus `hector-santiago`). The converter matches
the **exact fighter name only within its own two-person bout**, validates
round totals against fight totals, and records both slug differences for
review. It uses Cito's fighter profile ID from the bout for the canonical
stat row; a name or slug does not become a permanent UPSET identity.

The accepted historical registry currently links **none of this card's 26
Cito fighter IDs**. The review queue offers 19 single exact-name candidates
and identifies seven names with no exact historical identity label. These
are research hints, never automatic links. Review each profile against
evidence before using the existing `export_reviewed_cito_links` workflow
or `stage_current`. A single converted card does not fill the March–August
gap or establish a complete current feed. The three-list
`audit_current_coverage` must still reconcile a reviewed UFC calendar,
provider bout inventory and all completed stages before any pre-event
forecast claims. No model promotion follows from the pilot.
