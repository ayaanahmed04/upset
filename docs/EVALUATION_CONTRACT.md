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
export has **not yet** been added to a trained model; its coverage and impact
must be measured against the baseline on identical validation bouts.
