# Symmetric recent-performance comparison v1

Design fixed September 24, 2026, after inspecting the Elo v1 diagnostics and
before running these candidates on the historical data. This is exploratory
development on previously examined folds; no future accuracy is claimed.

Implemented on `feature/symmetric-recent-form`, based on PR #15's Elo work.
Assistant-environment validation: Ruff clean; **313 tests and 16 subtests
passed** on Python 3.12.14, NumPy 2.3.5 and scikit-learn 1.8.0. Tests exercise
known rate/shrinkage arithmetic, cold starts, missing control, current/same-day/
future isolation, independent audit corruption, swapped feature construction,
complementary probabilities, validation-label isolation, preserved references
and refusal to overwrite evidence. On the Mac at `4bc2941`, Ruff and all
313 tests passed; the export, audit and comparison then completed.
The first Mac run at `3cb9f18` passed Ruff, then pytest reported 308 passed,
two failures and three setup errors. All five affected cases entered boosted
fitting with a training feature that was entirely missing; scikit-learn 1.9.1
failed during histogram binning. The chained export/audit/comparison commands
did not execute. The subsequent fold-local column fix passed the Mac rerun.

## Question

Does removing fighter-order dependence improve the existing procedures, and
does exposure-aware recent performance add useful information beyond defense
and Elo? The first Elo run gave a six-pick gain with an interval crossing zero.
Its fitted classifiers also changed winner picks when the participants were
reversed. Those are distinct questions and need separate comparisons.

Keep the six original Elo-study variants as exact saved references. Fit six
new candidates, with no parameter search:

| Name | Features | Classifier |
| --- | --- | --- |
| `symmetric_defense` | Original 17 defense inputs | Logistic |
| `symmetric_defense_elo` | Defense plus Elo difference | Logistic |
| `symmetric_recent_elo` | Defense, Elo and recent performance | Logistic |
| `symmetric_boosted_defense` | Original 17 defense inputs | Histogram boosting |
| `symmetric_boosted_defense_elo` | Defense plus Elo difference | Histogram boosting |
| `symmetric_boosted_recent_elo` | Defense, Elo and recent performance | Histogram boosting |

## Symmetry

Split by date first. For every decisive training bout, include the forward
features/target and the swapped features/complemented target. Each orientation
has weight 0.5, retaining total training weight of one per actual bout. This
is augmentation, not two independent observations. Score each bout once.

At inference return `0.5 + 0.5 * (p_forward - p_reverse)`. Running the procedure
with reversed fighters must complement the probability within 1e-12. Signed
differences change sign; exposure sums stay fixed. Missing values remain
missing. Final probabilities are tested by actually invoking both directions.
The underlying raw directional outputs remain available in the report.

Use the existing train-only median/indicator/scaler/logistic pipeline with
max_iter=1000, lbfgs and C=1. Boosting retains the Elo study's fixed settings,
with min_samples_leaf=60 mirrored rows (previously 30 rows), 150 iterations,
7 leaves, depth 3, learning rate 0.05, L2=5, fixed seed and no random early
stopping. Doubling the leaf row threshold compensates for augmentation in
aggregate; it is not a guarantee of 30 unique bouts in every leaf.
For boosting, columns with no observed value in a training fold are removed
from that fold's fit and its later predictions. Partly missing columns keep
their NaNs for native missing-value routing. A future observation cannot
bring back a column that was absent during training. This handles an
all-missing-column binning failure observed on the Mac with scikit-learn
1.9.1, without fitting feature availability on validation bouts.

## Recent performance

Every earlier bout contributes weight `2 ** (-age_in_days / 365)`. Accumulate
weighted counts and weighted denominators, then form ratios. A short bout
does not receive the same influence on a pace estimate as a full decision.
Draw/NC stats can enter subsequent histories but never create winner targets.

The 12 measures are significant strikes landed/absorbed per minute,
significant-strike accuracy/defense, takedowns landed/conceded per 15 minutes,
takedown accuracy/defense, knockdowns delivered/conceded per 15 minutes,
submission attempts per 15 minutes, and control margin divided by observed
fight duration. Control margin is own minus opponent control; it uses only
paired bouts with both control values observed. Missing control is not zero.

Shrink each weighted rate toward the population rate from **all strictly
earlier dates**, with fixed equivalent exposure: 900 seconds for pace/control,
50 attempts for significant-strike accuracy/defense, and 5 attempts for
takedown accuracy/defense. Formula in rate units:

`(weighted_numerator * unit_multiplier + prior_rate * prior_exposure)
 / (weighted_denominator + prior_exposure)`

For defensive success, the numerator counts failed opponent attempts.
Population priors use earlier cumulative fighter-bout totals, including
earlier dates within a validation window. They are not computed from the
whole dataset or fitted to validation labels. They are UFC-wide, not
division-specific. If no earlier population denominator exists, the rate is
missing. A debutant otherwise receives the earlier population rate and zero
personal exposure. This retains a known opponent's information in a matchup.

Use A-minus-B differences for the 12 measures. Also include the difference
and sum of log1p(weighted seconds), log1p(weighted appearances), and
log1p(weighted paired-control seconds): 18 added columns. The sums describe
joint evidence and do not change sign under a fighter swap. Elo remains
initial=1500, scale=400, K=32 with simultaneous same-date updates. There is
no tuning of K, half-life or shrinkage, no odds, and no new paid data.

## Evidence and acceptance

Preserve `elo_comparison_v1` and its six forward/reverse probability columns
exactly. Verify its saved prediction hash and source hashes, validate cohort,
identities, dates, targets and exclusions, and independently replay Elo and
every recent-history numeric field from identified source fights/statistics.
Rebuild the original matchup and defense features from those same source
statistics and require agreement, so a different source snapshot cannot
silently enter only the recent-feature side of the comparison.
The recent audit uses direct age-weighted source sums, not the exporter's
decaying accumulator. Save recent totals and population priors for inspection.

Keep the four existing validation windows and all 1,857 decisive bouts, plus
35 excluded Draw/NC rows in the historical snapshot. No new split or favorable
subgroup. Save fold/pooled accuracy, correct counts, AUC, log loss and Brier,
paired date-bootstrap differences, reliability bins, history/missingness/
division slices, ties, and final/raw symmetry diagnostics. A mean-zero
symmetry error alone does not establish accuracy or calibration.

Primary probability measure: log loss. Accuracy remains explicit. Compare
symmetry against its matching old procedure, Elo against symmetric defense,
and recent performance against symmetric defense plus Elo. Also compare each
new candidate against saved full defense. Report mixed folds and intervals
crossing zero. No automatic promotion or claim of a 75% result.

## Historical Mac results at `4bc2941`

Mac Ruff and 313 tests passed. Exported and independently audited all 17,102
recent-performance rows: numeric fields matched direct source recomputation,
dates and population priors were strictly earlier, and read-back passed. The
comparison kept all six original Elo-study forward/reverse probability series
exactly. The four existing development windows contain 1,857 decisive bouts;
35 Draw/NC bouts are excluded. These figures come from the Mac terminal run;
the generated manifest and row-level predictions were subsequently supplied
and independently checked as described below.

| Variant | Correct / 1,857 | Accuracy | Log loss | Brier |
| --- | ---: | ---: | ---: | ---: |
| Saved full defense | 1,067 | 57.46% | 0.681592 | 0.243498 |
| Saved defense + Elo | 1,073 | 57.78% | 0.677938 | 0.241999 |
| Saved boosted defense + Elo | 1,060 | 57.08% | 0.674022 | 0.240889 |
| Symmetric defense | 1,074 | 57.84% | 0.681038 | 0.243295 |
| Symmetric defense + Elo | 1,075 | 57.89% | 0.677363 | 0.241769 |
| Symmetric defense + Elo + recent | 1,071 | 57.67% | **0.666020** | **0.236867** |
| Symmetric boosted defense | 1,055 | 56.81% | 0.675754 | 0.241579 |
| Symmetric boosted defense + Elo | 1,061 | 57.14% | 0.672901 | 0.240217 |
| Symmetric boosted defense + Elo + recent | 1,070 | 57.62% | 0.670808 | 0.239236 |

The recent logistic model improves log loss over its directly matched
symmetric defense + Elo comparator by **0.011342** (paired date-bootstrap 95%
interval for new minus comparator: [-0.019443, -0.003091]); its accuracy
difference is **-0.22 percentage points** [-2.28, +1.86]. Against saved full
defense, log loss changes by -0.015572 [-0.026140, -0.004711], while accuracy
changes by +0.22 points [-2.02, +2.39]. All intervals are exploratory and
unadjusted for the multiple models examined and earlier looks at these folds.
They do not establish future performance.

The matched logistic log-loss comparison improves in each window:

| Window | Symmetric defense + Elo | Plus recent | Correct, plus recent |
| --- | ---: | ---: | ---: |
| 2019 | 0.688571 | 0.671615 | 286/506 (56.52%) |
| 2021 | 0.677836 | 0.659531 | 294/497 (59.15%) |
| 2022 | 0.664591 | 0.661593 | 292/506 (57.71%) |
| 2023 partial | 0.678959 | 0.673590 | 199/348 (57.18%) |

Adding recent features to the symmetric boosted defense + Elo model reduces
log loss by 0.002092, with a paired 95% interval [-0.007288, +0.003018]; the
interval includes zero. All six new final procedures have zero maximum
fighter-swap complement error, zero conflicting winner picks and 42 exact
0.5 ties on the validation set. The order problem is resolved for these
procedures, but symmetry alone is not a predictive improvement. The recent
logistic model is the strongest *development probability candidate*, while
win-pick accuracy remains about 58%. No model is promoted.

### Review of the uploaded manifest and predictions

The uploaded `recent_form_v1` manifest identifies `4bc2941` and scikit-learn
1.9.1 on the Mac. The 1,892 uploaded prediction records match its recorded
SHA-256. Both saved Elo-study input-file hashes match the earlier uploaded
Elo manifest and prediction file, and all six old forward/reverse values,
identities, dates, targets and exclusions are identical for every bout.
Independently recomputing all 12 variants' accuracy, AUC, log loss and Brier
from the uploaded rows matched all 47 reported pooled, fold, subgroup and
weight-class score sets. Recomputing the matched date-cluster bootstrap from
the rows and the recorded seed reproduced its paired intervals. The saved
source-data audit reports 17,102 matching rows and strictly earlier priors;
the full original historical source files were not uploaded here, so that
source replay cannot be independently rerun in this review.

The recent candidate has AUC **0.628908** versus **0.605321** for symmetric
defense + Elo. Adding recent inputs lowers log loss for matchups with both
fighters experienced (962 bouts: 0.673780 to 0.664477), at least one under
three earlier UFC bouts (895: 0.681213 to 0.667679), both fighters with some
history (1,487: 0.676191 to 0.666477), and only one with history (328:
0.680651 to 0.660476). The 42 matchups where neither fighter had history
receive exactly 0.5 from both symmetric logistic models. At the individual
bout level, the recent model reduces log loss on 997 bouts, increases it on
818 and ties on 42; its pooled gain remains after descriptively removing the
ten largest improvements. These analyses are retrospective, not independent
tests of which subgroup to serve with which model.

The fixed ten-bin expected calibration error, recomputed from the saved
probabilities, is **0.0352** for the recent logistic model versus **0.0074**
for symmetric defense + Elo. Its mean predicted winner confidence is 60.34%
while 57.67% of its winner picks are correct. The recent model improves
pooled log loss and Brier but has a worse *coarse-bin calibration diagnostic*;
in particular, its 0.4–0.5 A-side probability bin averages 0.453 and wins
0.506 of bouts (504 observations). The matched model's corresponding bin
averages 0.456 and wins 0.452 (633 observations). These bins are descriptive,
depend on bin edges, and do not license calibration on the same validation
bouts followed by reporting the calibrated score as a new validation result.

The weight-class slices are mixed: featherweight (201 bouts) and women's
bantamweight (61 bouts) have higher recent-model log loss than their matched
comparator, while lightweight (246) and bantamweight (204) have lower loss.
Class-specific estimates are exploratory and too thin for selective model
switching. The manifest counts 1,279 source bouts after the last development
date (August 19, 2023); their outcomes have not been scored by this study.
Freeze the model and any calibration plan before testing on a later-date
cohort. Historical later-date testing still differs from timestamped live
forecasts.

The fixed follow-up is now implemented on a separate branch. See
`docs/EXAMINED_LATER_EVALUATION.md`: it forecasts and then scores the
**previously examined** August 2023–March 2026 period. The original baseline
already reported results there, so this is a historical stress test, not a
fresh holdout. The Mac completed the test: recent performance scored
784/1,260 (62.22%) versus the matched comparator's 767 (60.87%), with lower
log loss but an accuracy interval including zero. The small 2026 slice and
one-fighter-history slice favor the comparator. No model was promoted.

## Mac commands

After checking out this branch, activating the environment and ensuring the
working tree is clean:

```bash
python -m ruff check . && python -m pytest
python -m upset.data.export_prefight_recent
python -m upset.data.audit_prefight_recent
python -m upset.modeling.run_recent_form
```

The export is `prefight/recent_history_v1.jsonl` under the existing processed
dataset. The experiment wrote `experiments/recent_form_v1/` and refuses to
overwrite it. Export/audit commands are offline and use the identified
statistics already on the Mac. The original Elo exports and experiments did
not need to be rerun. Keep the saved manifest and row-level predictions for
later diagnostics and reproducibility review.
