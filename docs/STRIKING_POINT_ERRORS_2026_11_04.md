# What the accuracy-gap improvement really means

The 1.78 → 0.11 percentage-point result measures **overall bias**, not the
typical error in one fighter's next fight. The updated model largely fixed its
aggregate tendency to estimate striking accuracy too low. Individual estimates
improved modestly. The earlier delivery's phrase “average historical accuracy
gap” should be read with this distinction.

This follow-up audit fits nothing and changes no model, feature or release
decision. It uses the exact same 7,028 fighter-bout observations, on 333 dates
and 1,257 distinct fighters, as the retained rolling study. Each fighter-bout
is one fighter's side of a fight; these are not 7,028 independent fights. There
are 672,393 significant-strike attempts in this matched support.

## Overall bias versus individual error

Pooling attempts across these observations gives:

| Quantity | Significant-strike accuracy |
| --- | ---: |
| Recorded overall accuracy | 46.99% |
| Original model's overall estimate | 45.21% |
| Updated model's overall estimate | 47.10% |

The original estimate was 1.78 percentage points low; the updated estimate is
0.11 points high. Absolute aggregate bias fell about 94%. **That does not mean
predictions became 94% better, or that they are 99.89% accurate.**

A simple example explains the limitation. If two fighters each attempt 100
strikes, land 40 and 60, and the model estimates 50% for both, the overall bias
is zero. Both individual estimates still miss by ten percentage points.

## The newly checked individual errors

For each fighter-bout, this audit compares the pre-date estimate with that
fighter's realized landed/attempted rate, then averages the absolute misses.
Each fighter-bout receives equal weight in the primary descriptive MAE.

| Descriptive measure | Original model | Updated model |
| --- | ---: | ---: |
| Mean absolute miss | 11.08 pp | 10.86 pp |
| Median absolute miss | 8.53 pp | 8.48 pp |
| 90th percentile absolute miss | 23.62 pp | 22.82 pp |
| Estimates within 5 pp of realized accuracy | 30.72% | 31.47% |
| Estimates within 10 pp of realized accuracy | 56.87% | 56.86% |
| Attempt-weighted mean absolute miss | 8.54 pp | 8.42 pp |

The primary mean absolute miss improves by 0.217 percentage points, about
1.95% relative to the original. Whole-date resampling gives a descriptive 95%
interval of [−0.290, −0.148] points for updated minus original MAE; resampling
fighter trajectories gives [−0.268, −0.168]. Each uses 1,000 replicates with
seed 20261104. These one-way sensitivities do not jointly resolve shared-fight
and repeated-fighter dependence, or account for adaptive model development.

The new model also improves over simply using each fighter's previous recorded
career accuracy: that baseline's mean absolute miss is 11.75 pp, versus 10.86
pp for the updated model, approximately a 7.55% reduction. Nevertheless, that
plain baseline has an aggregate bias of only −0.014 pp, *smaller* than the new
model's +0.113 pp. That is direct evidence that minimizing aggregate bias alone
does not identify the best individual estimates.

These are errors against realized fight accuracy, which includes sampling,
fight circumstances and matchup variation. They are not measurements of an
unobserved true skill, a fighter's win probability, or a fixed ±10.86-point
confidence range. No fighter-level uncertainty interval can be inferred from
this average. About 57% being within ten points describes this development
sample; it is not an established future success rate.

## What the uncertainty failures are telling us

The retained rolling study's 24 failed overlapping subgroup labels remain
failed. In its actual-attempt groups, the mean bias also changes direction:

| Actual attempts in the observed fight | Observations | Recorded accuracy | Estimated accuracy | Bias |
| --- | ---: | ---: | ---: | ---: |
| 1–24 | 1,283 | 49.96% | 47.28% | −2.69 pp |
| 25–49 | 1,098 | 51.27% | 47.58% | −3.68 pp |
| 50–99 | 1,797 | 48.82% | 47.30% | −1.51 pp |
| 100–199 | 2,147 | 46.48% | 47.00% | +0.52 pp |
| 200+ | 703 | 45.32% | 47.01% | +1.69 pp |

This cancellation helps explain why a small overall bias can coexist with
substantial subgroup errors. The actual attempt count is known after a fight;
it is a diagnostic and conditional scoring exposure, not an available pre-fight
feature. Using it to revise a purported pre-fight mean would leak information.

The rolling count distribution also tends toward overly broad central ranges
in several groups. For example, the primary-seed central 90% randomized-PIT
coverage is 94.0% in the 1–24 attempt group and 94.8% in 2025. These values come
from the retained report; they are not a fresh set of repaired intervals. The
90% diagnostic band remains 87–93%, and all three seeds must pass. Some groups
fail only because another seed crosses a boundary; flags are diagnostic and
overlapping, not 24 independent tests proving a universal failure.

The next uncertainty study should separate mean errors that vary with fight
conditions from dispersion errors, retain the chronological information
contract and compare against the frozen references. It must declare its
selection rule before fitting and retain failed results. Any correction would
still need protected future evaluation before stronger product claims.

## Audit and reproduction

The saved artifact is
`data/processed/striking_point_error_audit_2026_11_04_v1/report.json`. It includes
all six reference methods, all prior subgroup definitions, both cluster
sensitivities, retained attempt-group uncertainty diagnostics and source/input
hashes. The audit verifies the retained study's input/output hashes, exact
common support, matching outcomes and reproduction of its aggregate accuracy.
A separate arithmetic illustration verifies that zero bias can coexist with
ten-point mean absolute error.

```bash
cd /Users/ayaanahmed/Projects/upset
.venv/bin/python scripts/audit_striking_point_errors.py \
  --study data/processed/striking_rolling_2026_11_04_v1 \
  --output data/processed/striking_point_error_audit_2026_11_04_v2
```

Use a new output directory on each run. Ruff passes for the audit source.
No serving files, snapshots, earlier reports or frozen models were changed.
The experimental site and its [restart instructions](STRIKING_EXPERIMENTAL_PREVIEW_2026_11_04.md)
remain available.
