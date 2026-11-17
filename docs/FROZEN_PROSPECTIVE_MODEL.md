# Frozen prospective model: implementation and limits

September 25, 2026. The saved symmetric recent + Elo logistic is the
**working research reference**, not a promoted live model. An opponent-adjusted
candidate gained 23 development picks but worsened pooled log loss and Brier.
UPSET will continue pursuing better probabilities with audited new data and
fresh, pre-event evidence.

`python -m upset.modeling.run_frozen_replay freeze` validates the pinned
`recent_form_v1` manifest and its seven historical input hashes, then fits
the unchanged 36-feature symmetric logistic recipe on all decisive fights
through 2026-03-07. It saves imputation, missingness, scaling and logistic
parameters as **numeric JSON** in `model.bin` (the archive's existing file
name), plus `model_spec.json` with source/model hashes, code commit, feature
order and training cutoff. It independently recomputes every fitted training
probability from the saved parameters and demands agreement within 1e-12.
Output is immutable. On Ayaan's Mac the run passed Ruff and all 351 tests,
froze 8,400 decisive fights, and produced model SHA-256
`55bf4a6f363c9c45bd3db008b74faab5927318b6614836e440024f52d9c8894c`.
The full historical files and the artifact remain on that Mac; the full-data
fit was not independently rerun in the assistant environment. See
`ASOF_PREFIGHT_FEATURES.md` for the completed full-data feature audit.

`record` accepts a schedule and one matching JSONL row per bout with exactly
`source_bout_id`, `fighter_a_id`, `fighter_b_id` and
`feature_differences` (all 36 columns, numeric or null). It generates the
probabilities and sends them to the existing prospective archive. For the
named frozen model, **record and verify recompute each probability** from
the stored feature row and JSON parameters and reject any disagreement.
The archive also checks reviewed provider identity links, schedule timing,
hashes, and repeated bout keys. It never imports outcomes into the forecast.

On the Mac, after pulling the branch and running lint/tests, freeze with:

```bash
cd ~/Projects/upset
git switch feature/frozen-prospective-replay
git pull --ff-only
source .venv/bin/activate
python -m ruff check . && python -m pytest
python -m upset.modeling.run_frozen_replay freeze
```

Once **real pre-fight features** and the reviewed schedule exist, record with:

```bash
python -m upset.modeling.run_frozen_replay record \
  --schedule /path/to/reviewed_schedule.jsonl \
  --features /path/to/audited_prefight_features.jsonl
```

**The `record` input is not ready yet.** The reviewed completed-fight intake
below does not fetch provider records. An as-of-date builder now derives all
36 features from linked fights/stats. Its full historical audit subsequently
matched all 8,551 bouts and 36 columns with zero absolute error; complete
current-source coverage remains unverified. Replay proves that *given*
submitted values produce the submitted probability; it cannot prove the
values are accurate or existed before the fight. Before a genuine live
forecast, ingest reviewed current fights and
fighter statistics, audit identity links, build features strictly from earlier
fights and independently verify them. Then publish forecast hashes to an
external timestamped location before the actual bout starts. Schedule
timestamps and actual start times need later reconciliation. Cito Pro is
optional; coverage and account entitlement require validation if purchased.

## Current completed-fight intake

`python -m upset.data.stage_current` accepts two **already normalized** JSONL
files with the exact existing `Fight` and `FightStats` dataclass fields. For
each completed bout it requires an HTTPS source URL, reviewed provider links
for both fighter IDs in the registry, unambiguous winner or Draw/NC, event
date after the historical cutoff and on/before acquisition day, and exactly
two matching fighter-stat rows with equal durations and valid totals. The
historical fight file must match the accepted reference SHA-256. It
rejects duplicate fighter pairs on the same date, including historical
cross-provider duplicates. Output is an immutable directory containing
identified fight/stats JSONL and a source/output hash manifest; it is
explicitly a **partial stage**, not a new training input or proof of complete
date coverage. No current fight files have been provided or imported here.

```bash
python -m upset.data.stage_current \
  --fights /path/to/normalized_completed_fights.jsonl \
  --stats /path/to/normalized_completed_fight_stats.jsonl \
  --output data/processed/current/reviewed_batch_001
```

Provider response acquisition, normalization into these canonical types,
review of unknown fighter links, and reconciliation of missing dates are
required upstream. This contract cannot by itself fill the March–September
gap; a provider may supply only part of it. The next implementation milestone
is to independently audit and join accepted current batches to the historical
source, then build a dated as-of feature generator. A model artifact by itself
adds **zero** new prediction accuracy; it makes subsequent measurements
credible and repeatable.
