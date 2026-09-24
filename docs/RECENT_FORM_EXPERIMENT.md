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
and refusal to overwrite evidence. Mac validation and actual scores are pending.

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
dataset. The experiment writes a new `experiments/recent_form_v1/` directory
and refuses to overwrite it. Export/audit commands are offline and use the
identified statistics already on the Mac. The original Elo exports and
experiments do not need to be rerun. Full-data scores remain pending until
the Mac runs this study; synthetic tests establish behavior only.
