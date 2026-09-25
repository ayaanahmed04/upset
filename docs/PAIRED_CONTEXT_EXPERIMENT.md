# Paired fighter context v1

Design fixed September 25, 2026 UTC, after reviewing the external modeling
critique and before running this candidate on the full historical data.
Implemented on `feature/paired-fighter-context`, stacked on the completed
examined-period work. This is one exploratory experiment on the four existing
development windows. It does not establish future performance or promote a model.

**Implementation verification:** Ruff passes; **334 tests and 16 subtests
pass** in the assistant environment. Full-data Mac results are pending. The
historical source exports remain on the Mac; synthetic test scores are not
UFC performance estimates.

## Why this next

The best supported recent change improved probability losses. On development
bouts, symmetric recent + Elo logistic reached log loss 0.666020 versus
0.677363 for symmetric defense + Elo. On the already examined later period,
the corresponding losses were 0.649515 versus 0.659788, with 784/1,260
(62.22%) versus 767/1,260 (60.87%) correct. Paired log-loss intervals exclude
zero; paired accuracy intervals include zero. Coarse-bin calibration and
some history/year slices remain weaker. These are reasons to retain recent
performance for further research, not to declare a released probability model.

The existing trees receive feature differences and joint exposure measures.
They cannot generally distinguish two high-volume fighters from two
low-volume fighters with the same difference. For example, 5 versus 4
significant strikes per minute and 2 versus 1 both become +1. If one fighter's
cumulative rate is missing, the difference also discards the other fighter's
known rate. Individual values retain both kinds of context.

Add those values while holding the classifier settings fixed. Changing
regularization, ratings, feature families and calibration at the same time
would obscure what produced any change. More columns can also hurt; an
improvement is a hypothesis to test.

## Fixed comparison

| Role | Variant | Inputs |
| --- | --- | --- |
| One new candidate | `paired_boosted_recent_elo` | Existing 36 inputs plus 66 individual fighter columns |
| Primary comparator | `symmetric_boosted_recent_elo` | Existing 36 inputs, same tree settings |
| Secondary reference | `symmetric_recent_elo` | Existing 36 inputs, saved logistic model predictions |

All 12 saved variants from `recent_form_v1` remain in the output, including
their forward/reverse predictions and the six symmetric variants' raw
directional outputs. Only one new candidate is fit. The primary comparison
isolates the added representation. Beating the old tree alone would not
establish an advantage over the stronger saved logistic candidate.

The new columns contain 33 values for each fighter:

| Family | Values per fighter |
| --- | ---: |
| Original cumulative pre-fight measures, including history exposure | 9 |
| Cumulative defensive measures | 8 |
| Own pre-fight Elo rating | 1 |
| Shrunk, 365-day weighted recent performance rates | 12 |
| `log1p` weighted seconds, appearances and paired-control seconds | 3 |
| Total | 33 |

The old 36 columns include three exposure sums; they are not exclusively
differences. Retaining their component exposures adds a convenient tree
representation, not new information beyond those existing sums/differences.
All 102 ordered column names are saved in the manifest. These are individual
**pre-fight history values**, not statistics from the fight being predicted
or current career-profile totals. Age, reach, stance, weight class, odds,
outcome-rate monotonic constraints and new Cito features are not model inputs
in this experiment. Weight class remains a reporting slice.

Use the prior symmetric tree settings unchanged: log loss, learning rate
0.05, 150 iterations, at most seven leaves, maximum depth three, minimum
leaf size 60 augmented rows, L2 regularization 5, 255 bins, seed 20260924,
no categorical features and no early stopping. Training uses one thread.
No search or fitted calibration is performed. The leaf size counts augmented
rows; it does not guarantee 30 distinct bouts in each leaf.

## Dates, missingness and fighter order

| Window | Train through | Validate from | Validate through |
| --- | --- | --- | --- |
| 2019 | 2018-12-31 | 2019-01-01 | 2019-12-31 |
| 2021 | 2020-12-31 | 2021-01-01 | 2021-12-31 |
| 2022 | 2021-12-31 | 2022-01-01 | 2022-12-31 |
| 2023 partial | 2022-12-31 | 2023-01-01 | 2023-08-19 |

There are 1,857 decisive validation bouts **in total**, plus 35 Draw/NC rows.
Classifier fitting uses earlier decisive fights. Histories can incorporate
earlier event dates inside a validation window, as in the accepted studies;
same-date and current-fight statistics/results cannot enter their own inputs.
The full snapshot is audited, but dates after August 19, 2023 are not scored.
The previously examined later-period report is preserved.

Mirror each training bout after selecting the date split, with weight 0.5
per orientation. On a swap, signed differences reverse, exposure sums stay
fixed, and each A/B pair exchanges values, including missingness. Validate
that the transformation is an involution. Infer with
`0.5 + 0.5 * (forward - reverse)` and independently invoke the same procedure
on swapped inputs to verify complementarity within 1e-12. Score each bout
once; report exact 0.5 ties under the existing canonical-A tie policy.

Keep NaNs for native tree routing. Remove a column only when it is entirely
unobserved in the mirrored training set; use that training-derived mask for
all subsequent predictions. This preserves the scikit-learn 1.9.1 fix from
the recent-form experiment. One fighter's missing value does not erase a
known value on the other side.

## Evidence checks

The accepted `recent_form_v1/manifest.json` is pinned to SHA-256
`9c5f6228ffb3028d010bc70a644e34be47591626443285fc50e5345107f49787`.
Verify its experiment schema, settings, prediction hash and the seven source
hashes. A changed source snapshot or regenerated reference is a different
study, not permission to silently replace accepted evidence.

Rebuild cumulative individual features from the identified fight/stat
histories. Rebuilt matchups and defense must match the saved exports. Replay
Elo and recent performance with the existing independent numeric audits.
Verify every participant join, date and history exposure, then reconstruct
every existing difference and sum from the paired values. Current profile
aggregates never enter this path.

Before fitting the new tree, refit the directly matched old tree in each fold
and compare its final, swapped and raw directional probabilities with the
saved values. Any error above 1e-12 stops the run. This catches changed
features or an environment that cannot reproduce the accepted comparator;
it does not refit or replace the other saved references. Both the original
and current environment versions are recorded through the pinned reference
and new manifest.

Preserve the original files and reference values, record source and output
hashes, and verify inputs have not changed during evaluation. Write results
with read-back verification and refuse to overwrite an existing output
directory. The CLI requires a clean Git working tree and records its commit.

New tests cover actual participant reversal, missing values, context retained
despite equal differences, current/same-day/future source changes, validation
label isolation, invalid joins, altered references, comparator replay and
complete export preservation. These check correctness, not predictive gain.

## How to interpret the run

Primary measure: paired log loss against `symmetric_boosted_recent_elo` on
exactly the same decisive bouts. Also compare with saved
`symmetric_recent_elo`. Lower loss differences favor the new candidate.
Report Brier, AUC, accuracy, date-bootstrap intervals, individual windows,
history/experience/missingness/weight-class slices, reliability bins,
ten-bin ECE and fighter-swap diagnostics. Do not select a subgroup policy
from whichever slice happens to win.

These development dates have been examined repeatedly. Date resampling does
not remove selection bias, shared training histories or dependence between
recurring fighters. Intervals are exploratory and unadjusted for multiple
comparisons. A smaller ECE is descriptive, not a calibration guarantee.
Lower loss with unchanged accuracy does not by itself diagnose overfitting.

If the candidate improves both reference comparisons without a concerning
pattern across years/history groups, freeze it for a separately specified
follow-up. An uncertain or negative result is a reason to retain the saved
logistic research reference and test the next feature family separately.
Opponent-adjusted performance remains a plausible later step; current-data
ingestion and externally dated prospective evidence remain necessary either
way. No model is automatically promoted by this runner.

## Assessment of the external review

The paired-value suggestion is actionable with data already owned. Other
claims need qualifications:

- Public accuracy figures do not establish parity with UPSET. UFCalendar's
  live Power Index page covers multiple organizations and excludes exact
  50/50 picks. Its totals also change. UPSET's selected 62.22% is on 1,260
  UFC bouts in an already examined period, with its own tie rule. These are
  different cohorts and evidence histories. [S1]
- The cited market study reports 68.6% closing-favorite and 66.2%
  opening-favorite accuracy on 6,210 UFC fights since 2012 with both prices
  available. It also reports 76.8% closing-favorite accuracy for 2024.
  Those are the publisher's figures, not an independently reproduced
  matched UPSET benchmark. They do not establish an absolute 75% ceiling,
  nor a sustainable 75% target for this model. [S2]
- Four validation windows are not four independent experiments: training
  periods overlap and fighters recur. The quoted recent-form loss interval
  is pooled; it is not four separate fold intervals excluding zero.
- Defensive rates are affected by opponent quality; that does not make
  them opponent-adjusted. Redundancy with Elo is a hypothesis. The observed
  incremental probability-loss gains do not support discarding Elo merely
  because winner accuracy barely changed.
- Scikit-learn supports monotonic constraints on binary probabilities, but
  “higher recent win rate must always help” is an additional conditional
  modeling assumption. Opponent quality and sparse histories complicate it.
  Constraints are not included as an untested guarantee. [S3]
- The Odds API advertises historical MMA/UFC prices from June 2020 on
  **paid** plans; current prices are available on its free plan. A fair
  market baseline needs reviewed bout matching, a fixed pre-event cutoff,
  margin removal and the same scored cohort. A closing-price reference also
  has a different information horizon from a forecast issued days earlier.
  No market benchmark has been implemented or paid access purchased. [S4]

Cito is not required for this experiment. Hold the broader purchase while
using existing history, but retain the separate current-data gap and the
historical-access pilot from the research plan. Round histories may eventually
help; neither their incremental value nor their ceiling is established yet.

Sources checked September 25, 2026 UTC:

- [S1: UFCalendar Power Index accuracy](https://www.ufcalendar.com/power-index/accuracy)
- [S2: UFCalendar market study, August 11, 2026](https://www.ufcalendar.com/blog/ufc-odds-line-movement-14-year-study)
- [S3: scikit-learn HistGradientBoostingClassifier](https://scikit-learn.org/1.8/modules/generated/sklearn.ensemble.HistGradientBoostingClassifier.html)
- [S4: The Odds API MMA/UFC coverage](https://the-odds-api.com/sports/mma-ufc-odds.html)

## Mac run

Run in Terminal using the existing project virtual environment. An LLM is
not needed to execute these commands. Keep the accepted exports and
`recent_form_v1` files in place; there is no source regeneration step.

```bash
cd ~/Projects/upset
git status
git fetch origin &&
git switch feature/paired-fighter-context &&
git pull --ff-only &&
source .venv/bin/activate &&
python -m ruff check . &&
python -m pytest &&
python -m upset.modeling.run_paired_context
```

Results are saved under
`data/processed/kaggle_ufc_1994_2026/experiments/paired_context_v1/`.
Share the terminal summary, `manifest.json` and `predictions.jsonl` for
row-level review. To open that folder in Finder:

```bash
open ~/Projects/upset/data/processed/kaggle_ufc_1994_2026/experiments/paired_context_v1/
```

If output already exists, preserve it. An intentional verification rerun
must use a new `--output` directory. If the accepted reference hash or matched
tree replay fails, inspect the difference before changing inputs or dependencies.
