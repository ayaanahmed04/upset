# Frozen development evaluation (v1)

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
