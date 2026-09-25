# Opponent-adjusted performance v1

Design fixed September 25, 2026 UTC, after independently reviewing the
unsuccessful paired-context study and before this candidate is run on the
full historical files. This is a single exploratory development experiment,
implemented on `feature/opponent-adjusted-performance` and stacked on PR #18.
The expected improvement was a hypothesis; the full-data Mac run is complete.
In the assistant environment, Ruff and all **346 tests plus 16 subtests** pass.
Tests cover known arithmetic, opponent-specific expectations, same-date
isolation, corruption caught by an independent audit, swap symmetry,
validation-label isolation and the full pinned-export chain. On the Mac, Ruff
and all **346 tests** passed in 54.64 seconds at code commit
`6a4727da97cec7af1211a1825e125dbe614a4a2a`. Synthetic tests do not
measure UFC accuracy. The exploratory result and independent uploaded-file
review follow below; **no model was promoted**.

## Full-data result and decision (September 25)

The Mac independently audited all 17,102 adjusted rows, reported an exact
matched-logistic refit in every fold, preserved all 12 accepted probability
series, and scored the same 1,857 decisive development bouts (35 Draw/NC
excluded). The results for the prespecified paired comparison are:

| Cohort | Reference correct | Adjusted correct | Reference log loss | Adjusted log loss |
| --- | ---: | ---: | ---: | ---: |
| Pooled (1,857) | 1,071 (57.67%) | 1,094 (58.91%) | 0.666020 | 0.666722 |
| 2019 (506) | 286 | 295 | 0.671615 | 0.669887 |
| 2021 (497) | 294 | 290 | 0.659531 | 0.663569 |
| 2022 (506) | 292 | 303 | 0.661593 | 0.664003 |
| 2023 partial (348) | 199 | 206 | 0.673590 | 0.670574 |

Adjusted minus reference: **+23 correct, +1.24 accuracy points**, with a
calendar-date bootstrap 95% interval [+0.11, +2.48] points. The primary
probability comparison, log loss, is **+0.000701** (worse), interval
[-0.002571, +0.004019]. Brier increases from 0.236867 to 0.237185
(worse). AUC moves by only +0.000142. Ten-bin ECE decreases from 0.035222
to 0.018755; this coarse descriptive statistic does not cancel the poorer
proper scores. The candidate flipped 147 picks: 85 fixes and 62 regressions.
The 2021 fold loses on both accuracy and log loss, while 2022 gains picks but
loses on log loss.

With both fighters having prior history (1,487 bouts), the candidate gains
26 picks and its log loss improves only 0.000097. With **only one fighter
having prior history** (328 bouts), it loses three picks and log loss rises
from 0.660476 to 0.664885. The neither-history group (42 bouts) has exactly
0.5 probabilities for both models. The candidate is therefore not a
demonstrated probability improvement on the predeclared primary metric;
retain the saved symmetric recent + Elo logistic as the **working research
reference**, with no automatic promotion. The narrow positive accuracy
interval is conditional on the repeatedly examined development period,
this candidate comparison and date resampling; it is not fresh confirmation.
The previously examined 784/1,260 (62.22%) later-period result belongs to
a different cohort and was not rerun.

The uploaded `manifest.json`, `predictions.jsonl` and
`adjusted_history.jsonl` have SHA-256 respectively
`5496dfddea446cd54c4a5013835433107cfcb78bebd38ec45b7fcf5edb090d23`,
`7c14098b30f80c7c0885f3d2739477945764b29bf53a0eb8bd44f6de5ab38cc5`,
and `8c565bec3e08417aad55f4bbcac1971b8739088065aab5b0909465a9cd8435c2`.
Independent row calculations reproduced **611** reported metric sets across
the 13 variants, all reported calibration bins/ECE and symmetry values, and
the paired date-bootstrap interval. All 12 previous variants' predictions
and all seven source hashes match the accepted saved reference. The history
hash and 17,102 row count match; all 8,551 bouts have two distinct fighters
on the same date. Each fighter's recorded prior count excludes all same-date
bouts; both per-family residual rates recompute from excess and weighted
exposure, and zero-prior rows have zero exposures and features. The uploaded
files do not include the original source fight statistics, earlier opponent
rates or serialized model, so the Mac's independent source replay and refit
are reported by its manifest, not separately repeated in this review.

Next prioritize reviewed current-fight ingestion, frozen model replay and
externally dated pre-event forecasts. If another historical feature family
is explored, specify it before fitting and continue to label these windows
exploratory; neither this accuracy interval nor a new later-period score
would turn already examined dates into a fresh holdout.

## Question and comparison

Does a fighter's output *relative to that past opponent's known defense*
improve probability quality beyond the accepted symmetric recent + Elo
logistic model? For example, landing ten significant strikes against an
opponent who historically allowed very few may tell a different story from
landing ten against someone who historically allowed many. The prior
opponent rate is available from the independently audited recent-history
export; no new data vendor is needed.

| Role | Variant | Inputs |
| --- | --- | --- |
| One candidate | `symmetric_opponent_adjusted_recent_elo` | Saved logistic model's 36 columns plus six opponent-adjusted columns |
| Matched reference | `symmetric_recent_elo` | Same 36 saved columns, classifier settings and folds |

All **12** accepted `recent_form_v1` probability series and their forward,
swapped and (for six symmetric models) raw directional values remain exact
saved references. The current cohort contains 1,857 decisive development
bouts and 35 Draw/NC exclusions in the four 2019, 2021, 2022 and partial
2023 windows (ending August 19, 2023). Earlier results inside a window can
enter *subsequent* fights' dated histories. No validation labels can enter
the fitted classifier for that window. The 1,279 later source bouts are not
automatically scored; the later 62.22% result has already been examined.

The symmetric recent + Elo logistic reference previously scored 1,071/1,857
(57.67%), log loss 0.666020 and Brier 0.236867 in this cohort. The proposed
family must be compared on exactly these same bouts. Pick accuracy alone is
insufficient to claim a better probability model; paired log loss is primary.

## Dated historical feature

For each *past* bout, use the opponent's **pre-bout**, 365-day weighted,
earlier-population-shrunk conceded rate. Set the predicted significant
strikes landed per minute equal to that opponent's pre-bout
`sig_absorbed_per_minute`; set the predicted takedowns landed per 15 minutes
equal to the opponent's pre-bout `td_conceded_per_15`. This is a **fixed
heuristic expectation**, not a learned or independently calibrated opponent
model. Its value comes from the existing dated `recent_history_v1` rows and
is audited before use. We deliberately make no claim that a conceding rate
alone captures the fighter's true expected output.

For a completed past fight of duration `t` seconds, the striking excess is

`actual significant strikes landed - opponent's pre-bout absorbed/min * t / 60`.

The takedown excess is

`actual takedowns landed - opponent's pre-bout conceded/15 * t / 900`.

If the opponent's rate is unavailable, that past bout supplies **zero
observations and zero exposure** for that family. This applies to the first
event date before a population prior exists. A previously unobserved opponent
with a valid earlier-population prior is treated by the source as a prior
rate, not as measured personal defense. A Draw/NC has fight statistics and
can update *later* histories, but does not enter binary model fitting.

Decay each eligible past bout by `2 ** (-days_since_bout / 365)`. The feature
for a current fighter at a current event date is

`unit * sum(decayed past excess) / (900 + sum(decayed eligible fight seconds))`,

with `unit=60` for strikes/minute and `unit=900` for takedowns/15 minutes.
The fixed 900 seconds pull a sparse residual toward **zero excess**, and
exposure is retained. When no eligible past bout exists, excess, exposure
and feature all equal zero; that is a neutral prior, not a fabricated
performance observation. A negative feature means the fighter historically
landed less than the fixed conceded-rate expectation. The current and
same-date bout's statistics do not enter its own historical feature.

Add **six** matchup columns: the A-minus-B adjusted rate for each of the
two families, and the difference and sum of each fighter's `log1p(eligible
weighted fight seconds)`. The sums report evidence shared by the matchup;
the differences and residuals reverse sign when fighter order is swapped.
Do not add current career totals, odds, Cito rounds, current-fight output,
physical measurements or later-period outcomes. The 42-column ordered
schema is saved in the manifest.

## Safeguards and fixed scoring

Use the exact previous symmetric logistic recipe: training-only median
imputation, missing indicators, scaling, default fixed C=1 with lbfgs and
maximum 1,000 iterations; mirror both participant orientations only **after**
selecting the strictly earlier training fold, with 0.5 sample weight each.
Final inference uses `0.5 + 0.5 * (forward - reverse)`, checked by making an
independent swapped-input call. No new hyperparameter search or fitted
calibration. Exact ties use the existing canonical-A pick rule and are
reported. Report four fold scores, pooled log loss/Brier/AUC/accuracy,
date-bootstrap paired intervals, missingness/history/experience/weight-class
slices, fixed reliability bins/ECE and symmetry. Every decisive bout is
scored once. These already examined development folds and their intervals
do not establish a new unbiased future-performance estimate.

Pin the accepted Mac `recent_form_v1/manifest.json` SHA-256
`9c5f6228ffb3028d010bc70a644e34be47591626443285fc50e5345107f49787`.
Check that manifest's prediction SHA-256 and the seven unchanged source
file hashes. Rebuild saved matchup and defense features from identified
fights/statistics; independently audit all 17,102 Elo and recent snapshots.
Build adjusted histories for all participant appearances, then recompute
every saved numeric value via a **separate direct earlier-bout ledger**
rather than reusing the rolling-sum builder. This audit fixes the half-life
independently, checks IDs, dates, prior counts and missing-rate exclusions,
and checks all adjusted rows. The exported history is read back and hashed.

Refit the directly matched saved logistic model on each old training fold
and require its final, swapped and raw predictions to match the accepted
rows within 1e-12. If feature definitions or the Mac training environment
drift, the run stops instead of quietly treating a changed model as the
reference. Preserve the original prediction bytes and original files;
record input, adjusted-history and output hashes, code commit, library
versions and the exact settings. Refuse to replace an existing output
directory. A clean Git working tree is required.

Interpret paired log loss first, then accuracy and Brier, and look for
consistent direction across years and history groups. If the new result
has no demonstrated gain or worsens sparse-history behavior, retain the
saved symmetric recent + Elo logistic research reference. No automatic
model promotion or later-period rerun is performed. Current-data
ingestion and externally dated prospective forecasts are still needed to
judge live performance.

## Run on the Mac

These are Terminal commands; no different LLM model is required to run
them. They use the accepted processed data already in the local repo's
ignored `data/` directory:

```bash
cd ~/Projects/upset &&
git status &&
git fetch origin &&
git switch feature/opponent-adjusted-performance &&
git pull --ff-only &&
source .venv/bin/activate &&
python -m ruff check . &&
python -m pytest &&
python -m upset.modeling.run_opponent_adjusted
```

The new `data/processed/kaggle_ufc_1994_2026/experiments/opponent_adjusted_v1/`
directory contains `adjusted_history.jsonl`, `predictions.jsonl` and
`manifest.json`. Share the final terminal output and the **manifest plus
predictions** for row-level review. The history remains on your Mac unless
an audit needs the full numeric evidence; its SHA-256 is in the manifest.
The output directory is immutable; use a new `--output` path for a deliberate
additional run.
