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

## Mac results and uploaded-file review

The Mac completed the protocol at code commit `534eb5e` (Python 3.12.14,
scikit-learn 1.9.1): Ruff and all **317 tests** passed, and 1,279 forecasts
were saved before scoring 1,260 decisive bouts and excluding 19 Draw/NC.
Both procedures were refitted on 7,140 pre-cutoff decisive bouts. The saved
forecast and scored-row hashes match their manifests, the scored manifest
references the exact forecast manifest and all seven source hashes match the
earlier `recent_form_v1` report. All 1,279 scored rows preserve the original
forecast fields verbatim; none of the forecast rows contains a target or
outcome-derived exclusion. Independent recomputation of the 48 saved pooled,
annual, history/experience/missingness and weight-class score sets (two
models each), fixed-bin calibration, symmetry and paired date-bootstrap
intervals matched the uploaded files. This is a read-back review of accepted
exported files, not a new replay of the Mac's unuploaded historical sources.

| Procedure | Correct / 1,260 | Accuracy | Log loss | Brier | AUC | Ten-bin ECE |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Symmetric defense + Elo | 767 | 60.87% | 0.659788 | 0.233848 | 0.648716 | 0.0224 |
| Plus recent performance | **784** | **62.22%** | **0.649515** | **0.228898** | **0.668938** | 0.0249 |

The paired difference, recent minus comparator, is **+1.35 accuracy points**
(17 additional correct picks); its date-bootstrap 95% interval is
**[-0.95, +3.51] points** and includes zero. The primary log-loss difference
is **-0.010273** with a date-bootstrap 95% interval
**[-0.018567, -0.002331]**. Brier falls 0.004950 and AUC increases 0.020222.
The recent candidate's coarse ten-bin ECE is slightly higher (0.0249 versus
0.0224); lower log loss is not proof of uniformly better calibration. The
intervals do not adjust for earlier model selection, this period's previous
baseline examination or repeated fighters across event dates.

| Period | Decisive bouts | Defense + Elo correct | Plus recent correct | Defense + Elo log loss | Plus recent log loss |
| --- | ---: | ---: | ---: | ---: | ---: |
| 2023 remainder | 156 | 94 | 93 | 0.67009 | 0.66102 |
| 2024 | 513 | 310 | 324 | 0.66054 | 0.64650 |
| 2025 | 515 | 312 | 321 | 0.66017 | 0.65064 |
| 2026 through March 7 | 76 | 51 | 46 | 0.63099 | 0.63865 |

The 2026 slice reverses direction and is small. With both fighters having
prior UFC history (1,041 bouts), recent features lower log loss by 0.01453
and add 30 correct picks; with only one having history (186), log loss rises
by 0.01171 and there are 13 fewer correct picks. The 33 double-debut bouts
have exact 0.5 ties in both procedures. The observed gain is also stronger
when all defense inputs are present (830 bouts, log-loss change -0.01647)
than when one is missing (430, +0.00169). These slices diagnose limitations;
they are **not** grounds to fit or select a subgroup-specific model on the
same examined outcomes. In the 1,260 decisive fights the recent procedure
reduces per-bout log loss on 705, increases it on 522 and ties on 33.

This comparison supports continued work on the recent feature family, but
does not promote a live model or establish its future accuracy. To claim a
fresh performance estimate, build the current-data and reviewed-identity
pipeline, save predictions with an external pre-event timestamp, and score
the resulting bouts after they finish. New feature and calibration ideas
must use separate development data; this examined period cannot be recycled
as their independent validation set.
