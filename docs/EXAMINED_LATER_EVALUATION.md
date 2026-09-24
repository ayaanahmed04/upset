# Frozen recipe on the previously examined later dates

This is a **historical stress test**, not a fresh holdout. The original
nine-feature baseline already scored the August 26, 2023–March 7, 2026 test
period (1,260 decisive fights, 19 Draw/NC, 51.98% accuracy). That score was
examined before the current model was selected. Looking at this period again
cannot recover an unbiased estimate of future accuracy.

The candidate and protocol were fixed on September 24, 2026, after reviewing
the 2019/2021/2022/2023-partial development folds and before running these
two procedures on post-August 19, 2023 fights. The saved `recent_form_v1`
manifest SHA-256 `9c5f6228ffb3028d010bc70a644e34be47591626443285fc50e5345107f49787`
pins the accepted code, historical inputs, feature history audit and 1,279
later source bouts. Inputs are compared byte-for-byte by SHA-256 to its seven
recorded source files. A changed snapshot requires a *new* versioned study,
not a silent rerun.

## Frozen choices

| Item | Choice |
| --- | --- |
| Main candidate | Symmetric logistic defense + Elo + 365-day weighted recent performance (`symmetric_recent_elo`) |
| Primary comparator | Symmetric logistic defense + Elo (`symmetric_defense_elo`) |
| Fit dates | All decisive historical bouts through 2023-08-19; one fit for each model |
| Later dates | All 1,279 source bouts strictly after 2023-08-19 in the accepted historical snapshot |
| Preprocessing | Training-only median, missing indicators and scaling; mirrored training orientations weighted 0.5 each |
| Inference | Average forward probability and complemented reverse probability; check both fighter orders |
| Calibration | Identity: no fitted adjustment; inspect ten fixed probability bins of width 0.1 |
| Primary measure | Paired log loss; also report Brier, AUC, accuracy, bins and event-date bootstrap intervals |

Both models use the unchanged feature definitions and classifier settings from
`recent_form_v1`. Both are *refitted* on the same earlier cutoff. Their scores
are paired on exactly the same later bouts. The original 51.98% nine-feature
baseline is context, not a directly matched comparator: it used a different
training period and feature set.

The runner verifies the source hashes, joins permanent fighter IDs, confirms
matchup targets against identified source fights when scoring, and uses the
previous independently audited pre-fight Elo/recent histories. A later fight
can use UFC fights on **earlier dates** in its fighter histories, including
earlier dates within this later period. No same-date fight or current outcome
can enter its own features. The model and imputation are never refitted using
later outcomes. This is an offline simulation from retrospectively compiled
data, not proof those statistics were available before the event.

## Two-step evidence

`forecast` fits the frozen candidate and comparator and saves probabilities
for **every** later bout, including bouts later labeled Draw/NC. The forecast
file has no targets, outcome-derived exclusions, or score metrics; its
manifest records the forecast SHA-256, source hashes, code commit, fit cutoff,
and settings. It refuses to overwrite an existing output directory.

`score` verifies the saved forecast hash, original source hashes and code
commit, then joins outcomes from the same source snapshot. Only decisive
bouts enter binary metrics; Draw/NC stays in `scored_predictions.jsonl` as an
explicit exclusion. It independently checks matchup targets against the
identified fights and saves scored predictions plus a separate scored
manifest. Date-bootstrap intervals resample calendar dates (1,000 draws,
seed 20260923); repeated fighters can remain dependent. Year, history,
missingness, experience and weight-class slices are diagnostics only.
Reliability bins and ten-bin ECE are descriptive; no calibrator or division
switch may be selected using these later outcomes and then counted as if
independently validated.

## Run on the Mac

From the repository root on `feature/examined-later-evaluation`, after pulling
the committed branch and activating `.venv`:

```bash
python -m ruff check . && python -m pytest
python -m upset.modeling.run_examined_later forecast
python -m upset.modeling.run_examined_later score
```

Outputs are ignored under
`data/processed/kaggle_ufc_1994_2026/experiments/examined_later_v1/`:
`forecasts.jsonl`, `manifest.json`, `scored/scored_predictions.jsonl`, and
`scored/manifest.json`. Keep all four files. The command refuses to write if
the working tree is dirty or the original Mac study does not match its pinned
hash. A rerun requires a new output path and a separately documented
protocol; it must not overwrite these results.

The earlier source snapshot ends in March 2026 and no live pre-event model
artifact has been approved. This historical stress test cannot promote a
model or establish a 75% winner-pick rate. A future performance estimate
requires independently dated forecasts saved before real fight outcomes.
