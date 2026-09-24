# Frozen development evaluation (v1)

The separately versioned opponent-strength/boosted-tree implementation is
specified in `docs/ELO_EXPERIMENT.md`. It retains these folds and exact saved
reference probabilities. The Mac run at `ddba4ab` completed: defense + Elo
scored 1,073/1,857 (57.78%) versus full defense's 1,067 (57.46%), with paired
accuracy interval [-1.51, +2.15] percentage points. Boosted defense + Elo had
the lowest pooled log loss (0.674022) but lower accuracy (57.08%) than full
defense. These are mixed development results; no model is promoted. Full
diagnostics and the separate Mac Ruff/pytest summary await review.

This experiment is separate from the original nine-feature baseline report.
The original export and `python -m upset.modeling.run_baseline` stay unchanged.

## Prediction task and cutoff

For each completed, decisive UFC bout in a validation window, predict fighter
A's win probability before the event. Fighter A is the lower permanent UPSET
UUID, independent of the winner. A fighter's history includes only fights on
strictly earlier calendar dates. All bouts on the same date are excluded from
one another's history. Combined `Draw/NC` rows are retained in the prediction
file with a null probability and an explicit exclusion reason; they do not
contribute to binary fitting or metrics.

The cohort is the accepted José Silva 1994–2026 historical snapshot. These
features describe **observed UFC fights**, not complete professional careers.
The snapshot and its results were downloaded later, so historical result
corrections cannot always be timestamped to their first public availability.

## Frozen date windows

| Fold | Training through | Validation period |
| --- | --- | --- |
| 2019 | 2018-12-31 | 2019-01-01 to 2019-12-31 |
| 2021 | 2020-12-31 | 2021-01-01 to 2021-12-31 |
| 2022 | 2021-12-31 | 2022-01-01 to 2022-12-31 |
| 2023_partial | 2022-12-31 | 2023-01-01 to 2023-08-19 |

The windows were chosen by calendar year before any richer-feature scores
were seen. Each fold refits the model and preprocessing on its earlier training
rows only. Between validation windows, later training includes intervening
completed bouts. Within a validation window, the fitted coefficients stay
fixed while fighter histories may reflect prior completed dates. The already
examined 2023-08-26 through 2026-03-07 test remains a historical reference;
it is absent from these training and validation folds. It is **not** a fresh
unbiased holdout after these modeling choices. Future prospective predictions
must be saved before results occur.

## Saved evidence

`python -m upset.modeling.run_development` writes ignored local files:

- `data/processed/kaggle_ufc_1994_2026/experiments/development_v1/predictions.jsonl`
- `data/processed/kaggle_ufc_1994_2026/experiments/development_v1/manifest.json`

The manifest records the code commit, entire matchup input hash, committed
registry hash, original examined test boundary, per-fold dates and metrics,
exclusion counts, feature list, fit protocol, and Python/numeric library
versions. Per-bout rows retain both permanent IDs, the target, probability,
cutoff, fold and exclusion reason. It does not save a production model.
The original full-data export and original baseline result must be compared on
the Mac; synthetic tests in the assistant environment cannot establish counts
or predictive performance on the user's ignored CSV and JSONL files.

## First separate defensive history

`python -m upset.data.export_prefight_defense` produces
`data/processed/kaggle_ufc_1994_2026/prefight/defensive_history_v2.jsonl`.
Each row is a snapshot before one bout for one fighter. Incoming strikes,
takedowns and recorded knockdowns come from the *opponent's* paired fight
statistics; only prior event dates contribute. Rates with zero observed
duration or zero opponent attempts remain null, with exposure counts retained.
The source's knockdowns are a recorded durability proxy, not a medical
measurement of a fighter's chin.

Only the exact `KO/TKO` and `Submission` method labels can count as their
respective finish losses, and only with an unambiguous named winner. Decisions,
doctor stoppages, `Could Not Continue`, `DQ`, `Overturned`, `Other`, and
combined `Draw/NC` receive no inferred KO or submission loss. The defensive
export enters a separate **candidate comparison** through
`python -m upset.modeling.run_defense_ablation`. This command refits the
original nine-feature logistic baseline and the same logistic procedure with
eight added defensive differences on each frozen training window. It joins
every one of the 8,551 matchup rows to both defensive rows by bout and
permanent fighter ID, checks the dates, and fails on missing or extra rows.
Both models are scored on precisely the same decisive validation bouts.
Combined Draw/NC rows appear with null probabilities.

The command writes local `experiments/defense_ablation_v1/predictions.jsonl`
and `manifest.json`. The manifest contains hashes, feature lists, per-fold
metrics, pooled paired differences and a 1,000-replicate bootstrap interval
that resamples calendar dates. The interval accounts for bouts sharing an
event date; repeated fighters and time dependence can still affect uncertainty.
The Mac completed this comparison at `3af4212`: 1,857 decisive bouts across
the four validation folds, with accuracy 53.04% for the original model and
57.46% with defense. Log loss improved from 0.69062 to 0.68159. Each fold
improved on both measures. The date-cluster bootstrap interval for the
paired accuracy difference was approximately +1.75 to +6.86 percentage
points. These are encouraging development results, not a fresh test score
or a forecast of future accuracy. More experiments using these folds will
increase selection pressure; preserve per-bout predictions and the original
reference.

`python -m upset.data.audit_prefight_defense` independently recomputes a
deterministic sample of saved defensive totals from the identified earlier
source bouts and checks the strictly earlier prior-fight count for every
fighter-bout row. On the Mac at `ef2e3af`, the audit matched source identities,
dates and earlier fight counts for all 17,102 rows. It independently
recalculated totals for 44 sampled rows from 41 fighters; all matched.

## Exploratory defensive group diagnostics

`python -m upset.modeling.run_defense_groups` saves ignored local outputs in
`experiments/defense_groups_v1/`. It retains the baseline and complete
defensive model probabilities from the prior paired comparison, then refits
eight variants on the identical frozen folds and decisive validation bouts.
Four variants add only one defensive group to the nine baseline features;
four omit one group from the full 17-feature model. The groups are incoming
strikes, takedowns, recorded knockdowns, and explicit finish losses (two
features each). The report includes per-fold and pooled accuracy, correct
counts, ROC AUC, log loss and Brier score, plus differences from the two fixed
references. Prediction rows include null values for combined Draw/NC across
all ten variants. The manifest records the input hashes, code revision,
feature lists, excluded rows, and runtime versions.

These comparisons are exploratory: the folds have already influenced feature
selection, groups are correlated, and the results cannot identify causal
contributions or provide an independent test. No Cito rounds enter this model.

The first Mac group run on 1,857 decisive bouts (35 Draw/NC excluded) gave:

| Variant | Correct | Accuracy | ROC AUC | Log loss |
| --- | ---: | ---: | ---: | ---: |
| Original baseline | 985 | 53.04% | 0.5548 | 0.69062 |
| Add striking | 1,029 | 55.41% | 0.5839 | 0.68467 |
| Add grappling | 990 | 53.31% | 0.5544 | 0.69072 |
| Add knockdowns | 997 | 53.69% | 0.5623 | 0.68836 |
| Add finish losses | 1,007 | 54.23% | 0.5708 | 0.68719 |
| All defense | 1,067 | 57.46% | 0.5966 | 0.68159 |
| All except striking | 1,041 | 56.06% | 0.5748 | 0.68637 |
| All except grappling | 1,067 | 57.46% | 0.5999 | 0.68138 |
| All except knockdowns | 1,077 | 58.00% | 0.5970 | 0.68235 |
| All except finish losses | 1,044 | 56.22% | 0.5872 | 0.68307 |

Striking and finish-loss histories show the clearest differences in these
variants. Removing grappling leaves accuracy unchanged and slightly improves
log loss, while removing knockdowns improves accuracy but worsens log loss.
Because the feature groups overlap and these folds have already been examined,
none of these ranks or the 58.00% variant is a prospective performance claim.

The add-striking variant beat the original baseline's correct-bout count in
all four folds (2019, 2021, 2022, and partial 2023). The full defensive model
also beat the baseline in all four. Other group comparisons were less stable:
add-finish-losses beat the baseline in two folds, and removing striking from
the full model *improved* 2022 accuracy by 11 bouts. Removing knockdowns
improved the pooled accuracy mostly because of 2022 (+16 correct versus full),
while it hurt partial 2023 (-6). These observations strengthen the reason to
avoid treating a pooled group ranking as a production feature choice.

The Mac reran the experiment at code commit `228a8ba` with the previously
accepted matchup SHA-256 `02daa2db24fa80e318ea007127b712e5af1dfa017cf326f7aebbf49c2470146b`
and defensive history SHA-256 `fcb0eee0853aafe5d9dc8f41f8d4051e53260528a0084988328907c4cf7674e8`.
Ruff and all 249 automated tests passed; the working tree was clean.

## Dated outcome and activity candidate (v1)

`python -m upset.data.export_prefight_outcomes` reads identified historical
fights and saves a separate ignored
`prefight/outcome_history_v1.jsonl` file: one row per fighter per bout. Each
row contains the number of earlier UFC appearances, earlier decisive bouts,
wins, losses, and win fraction; wins and losses in the **previous 365 calendar
days**; and days since the fighter's last observed UFC bout. The four modeled
inputs are the A-minus-B differences in prior win fraction, recent wins,
recent losses, and days since last bout. Counts and the fight IDs/dates remain
in the saved file as audit evidence. No other promotion's bouts are inferred.

Only event dates strictly before the target event contribute. A fight exactly
365 days earlier is in the recent window; a fight 366 days earlier is out.
The combined `Draw/NC` label contributes an appearance and can set last-bout
recency, but it is never called a win or loss. Win fraction is null until a
fighter has a decisive UFC bout. Days since last bout is null for a debut;
recent wins/losses are zero when there were none. Same-day outcomes cannot
enter one another's snapshots. The historical snapshot was downloaded after
the fights, so its labels may reflect later corrections.

`python -m upset.data.audit_prefight_outcomes` independently scans earlier
identified fights for **every** saved fighter-bout row, recalculates all
counts, rates and dates, and fails on a mismatch. The modeling command also
runs this source audit before writing its results. It checks coverage by
permanent fighter ID and bout ID, and the saved output reader rejects bad
schemas, duplicate keys and internally inconsistent counts or rates.

After export and audit, `python -m upset.modeling.run_outcome_recency` writes
ignored `experiments/outcome_recency_v1/predictions.jsonl` and
`manifest.json`. It preserves the **exact** original nine-feature baseline
and all-defense probabilities from the paired defense comparison and fits
two new variants: baseline plus the four outcome/activity differences, and
all defense plus those four. Each uses the same logistic procedure and frozen
development training dates. All variants score the identical decisive bouts,
while Draw/NC rows retain null probabilities. The manifest records input,
registry and identified-fight SHA-256 hashes, code revision, model features,
per-fold and pooled metrics, source-audit result and exclusions.

The Mac ran this comparison at `7f4cde9` after Ruff and all 257 tests passed.
The export produced 17,102 rows, and the independent audit recomputed every
one against the identified source fights and matched. The matchup SHA-256
remained `02daa2db24fa80e318ea007127b712e5af1dfa017cf326f7aebbf49c2470146b`
and the defensive history SHA-256 remained
`fcb0eee0853aafe5d9dc8f41f8d4051e53260528a0084988328907c4cf7674e8`.
The branch's tracked working tree was clean. On the same 1,857 decisive
validation bouts, with 35 combined Draw/NC rows excluded:

| Variant | Correct | Accuracy | ROC AUC | Log loss |
| --- | ---: | ---: | ---: | ---: |
| Nine-feature baseline | 985 | 53.04% | 0.5548 | 0.69062 |
| Full defense | 1,067 | 57.46% | 0.5966 | 0.68159 |
| Baseline + outcomes/activity | 1,055 | 56.81% | 0.5796 | 0.68601 |
| Full defense + outcomes/activity | 1,053 | 56.70% | 0.5977 | 0.68083 |

The new family substantially improved the weak baseline, but its combination
with full defense had 14 fewer correct bouts than full defense alone. AUC rose
by roughly 0.0011 and log loss improved by roughly 0.00076 relative to full
defense; these are very small development differences. The correct-bout counts
for the four frozen folds were:

| Fold | Baseline | Full defense | Baseline + outcomes | Defense + outcomes |
| --- | ---: | ---: | ---: | ---: |
| 2019 | 272 | 297 | 298 | 296 |
| 2021 | 269 | 289 | 287 | 288 |
| 2022 | 264 | 274 | 278 | 282 |
| 2023 partial | 180 | 207 | 192 | 187 |

Adding outcomes/activity to full defense helped 2022 by eight correct bouts
but hurt partial 2023 by 20. No model has been promoted from this comparison.
These folds have already been used for several feature decisions, so even the
baseline-to-outcome gain is exploratory. The original 2023-08-26+ test is an
examined historical reference, not a fresh holdout. Repeated fighters and
possible later corrections to the downloaded history also remain limitations.
The practical next evidence is a dated prospective prediction archive saved
before results occur.

The prototype archive contract, its input gates and the remaining live-data
requirements are documented in `docs/PROSPECTIVE_EVALUATION.md`. It has not
produced a real pre-event prediction or a new performance estimate.
