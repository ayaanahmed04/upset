# Recent-feature ablation and current-data coverage

## What was implemented

The September 24 external proposal correctly identifies two immediate tasks:
test the existing recent-performance columns in smaller groups, and distinguish
the current-data feed gap from feature engineering on the accepted historical
snapshot. This branch adds a fixed exploratory study and a read-only coverage
reconciliation tool. Neither changes the frozen model or yields a new score
without running against Ayaan's ignored historical files on the Mac.

The source audit already established **8,551 fights through 2026-03-07** and
17,102 complete fighter-fight statistics. The full 36-column as-of replay
matched those saved rows exactly. There are no current-fight batches in the
repository to verify the missing March-to-forecast interval yet.

## Pinned recent-performance groups

`python -m upset.modeling.run_recent_groups` uses the existing 2019, 2021,
2022 and partial 2023 development windows. It checks all seven historical
input hashes and the accepted `recent_form_v1` manifest, independently audits
the saved rating/recent histories, and refits the 36-column logistic reference
to its saved forward/reverse probabilities in every fold. Every experiment
fits only fights dated before its validation window, uses mirrored training,
and checks fighter-order symmetry. The 12 prior reference probability series
are copied unchanged. Dates after 2023-08-19 are not scored.

The common base is the 17 original offense/defense columns, Elo difference,
and four log exposure columns for recent fight time and appearances. Five
groups partition the other 14 columns exactly:

| Group | Columns | Why this boundary matters |
| --- | ---: | --- |
| Strikes | 4 | Landed, absorbed, accuracy, defense |
| Takedowns | 4 | Landed, conceded, accuracy, defense |
| Knockdowns | 2 | Delivered and conceded rates |
| Submissions | 1 | Submission attempt rate |
| Control margin | 3 | Margin plus both *known-control exposure* columns |

For each group, `add_*` compares with the common base, and the saved full
reference compares with `without_*`. Thus control availability is removed
**with** control margin in the leave-out fit; otherwise an exposure field
could smuggle some of the same information into its comparator. Both sides
of each comparison use the same decisive bouts. The report saves accuracy,
log loss, Brier, date-cluster paired intervals, subgroups, calibration and
prediction rows. The groups overlap in meaning and share fighters; these
tests do **not** isolate causal or independent predictive contributions.
There are ten paired comparisons across five groups on folds already examined
many times. A striking looking best result remains exploratory.

On Ayaan's Mac, after updating to this branch and passing tests:

```bash
cd ~/Projects/upset
source .venv/bin/activate
python -m upset.modeling.run_recent_groups
```

The command requires a clean committed checkout, the exact historical
source files and accepted recent-form report, and a new result directory. It
saves `data/processed/kaggle_ufc_1994_2026/experiments/recent_groups_v1/`
without rewriting the accepted report. Upload the `manifest.json` and
`predictions.jsonl` plus Terminal output for independent review before any
model decision.

## Coverage: three separate lists

`python -m upset.data.audit_current_coverage` compares a separately reviewed
UFC calendar, a provider's completed-event/bout listing, and one or more
immutable batches created by `stage_current`. It detects an entire event
missing from the provider list, a missing bout within a listed event, missing
fighter stats, wrong event/date, extra staged bouts, repeated records, changed
stage hashes and inconsistent registry versions. The event and provider
inventories must both be saved after the events, with HTTPS evidence URLs and
UTC observation times. Calendar `event_key` is a reviewer-assigned matching
key, **not** a claim that two providers share an event identifier.

One calendar JSONL row:

```json
{"event_key":"ufc-example-2026-09-20","event_date":"2026-09-20","source_url":"https://example.org/reviewed-calendar-event","observed_at_utc":"2026-09-22T14:00:00Z"}
```

One provider inventory JSONL row for the same event:

```json
{"event_key":"ufc-example-2026-09-20","event_date":"2026-09-20","provider":"cito","source_event_id":"example-event-id","completed_bout_ids":["example-bout-id"],"source_url":"https://example.org/provider-event","observed_at_utc":"2026-09-22T14:10:00Z"}
```

These are *schema examples*, not real event evidence. The stage's canonical
fights need `source_event_id` populated to tie each bout to that inventory.
Completed, including Draw/NC, bouts belong in `completed_bout_ids`; canceled
or scheduled bouts do not. A provider's event listing and independently
reviewed calendar should cover every completed UFC event from March 8 up to
the chosen coverage cutoff. Capture and review the actual provider responses;
do not fabricate a complete-looking inventory from whatever was already
staged. Run the audit after staging normalized fights and two stat rows per
bout with reviewed fighter identity links:

```bash
python -m upset.data.audit_current_coverage \
  --calendar /path/to/independent_calendar.jsonl \
  --inventory /path/to/provider_inventory.jsonl \
  --stage /path/to/first_reviewed_batch \
  --stage /path/to/next_reviewed_batch \
  --through-date YYYY-MM-DD \
  --output /path/to/new_coverage_report.json
```

An incomplete report lists issues and exits with status 1. An exact match
only establishes agreement **between supplied lists and staged files**:
`prospective_ready` remains false. Independently verify that the calendar
itself includes *every* UFC event, that provider stats are credible, that
identity links and timing are correct, and that the batch ends before any
scheduled forecast. The current repository has no March-to-present acquired
feed to run this real audit; no live completeness claim has been made.

## Review of the other suggested signals

| Proposal | What the repository actually has | Next sound experiment |
| --- | --- | --- |
| Ground durability under control | Past bout control and result methods are available after the 1999 coverage boundary; there is no history of submission threats or near finishes | Predefine significant opponent control as a fraction of *observed* duration, identify losses by finish method, and count eligible bouts; separate short fights, censor unknown control, and shrink sparse denominators. Don't call survival proof of a gas tank. |
| Strike location and position | All six landed totals are in historical CSV and canonical `FightStats`; none is in the 36-feature frozen model | Build dated, smoothed pre-fight shares with a zero-strike/missing flag; test by source era and sparse history. No Cito purchase needed for bout totals. |
| Knockdown/finish-loss rates | Recent knockdown *rates* already have exposure shrinkage; older defensive fields include raw knockdown/finish-loss counts | Test a dated, shrinkage-adjusted defensive outcome rate against a precisely matched reference. This is a refinement, not a wholly absent feature. |
| Stance interactions | Fighter profiles have stance but 849 of 4,455 entries lack it; the frozen model doesn't use it | Audit whether a profile value represents stance as known at fight date, then test opposing stance plus striking interactions with missingness. Current profiles alone may encode future updates. |
| Country/region | Neither historical CSV schema nor the canonical fighter model stores nationality | Acquire and validate fight-date residence/nationality before attempting a categorical test. It is not a one-hour column addition. |
| Camp lineage | No dated gym affiliation or reliable camp changes are recorded | Curate dated affiliation with evidence and coverage accounting; account for camp changes and sample size. |
| Round pace decay | Kaggle has 37 *fight-total* columns, no per-round strike rows; Cito has a small recent cached sample and historical requests were denied under the tested plan | Pilot historical round access before buying. Use actual elapsed seconds, an explicit later-round eligibility count, and a missing value for no eligible bout; avoid late/early division by zero and survivor bias. |

The addendum's raw-fighter-value boosted-tree test and opponent-adjusted
performance are already complete in `PAIRED_CONTEXT_EXPERIMENT.md` and
`OPPONENT_ADJUSTED_EXPERIMENT.md`. Their development results did not establish
better probability quality. Its public benchmark and market claims are
external proposals, not measured UPSET results; a matched timestamped odds
benchmark still requires actual source coverage and prices.
