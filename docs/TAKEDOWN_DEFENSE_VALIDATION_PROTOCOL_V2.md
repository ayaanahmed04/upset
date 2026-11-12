# Takedown-defense validation protocol v2

Declared October 26, 2026 before computing the new challenger, interval, or
reliability results. This is an extension of an already inspected development
study, not a pristine holdout or independent preregistration.

## Inputs and chronology

Reuse the immutable v1 adapter, predictions, report, selected k=25 and cutoff
2026-10-26. Verify all hashes and reproduce every v1 prediction before adding
comparisons. Reconstruct earlier sufficient counts directly from adapter rows.
All bouts on one calendar date are predicted before that date updates any
history. Last-five means the previous five bouts, including unavailable and
zero-attempt bouts, with only observed counts entering the denominator.

No site changes, source-data changes, opponent adjustment or public release.
No parameter or threshold may be repaired using the new development results in
this run. If uncertainty fails, record the failure and propose a separate study.

## Point-estimate challengers

The existing sample adjustment is (career stopped + 25 * earlier division
baseline) / (career attempts + 25), with the v1 all-division fallback rule.
Preserve raw career and raw last-five as references. Add these fixed challengers:

1. Career Jeffreys: (stopped + 0.5) / (attempts + 1).
2. Career Laplace: (stopped + 1) / (attempts + 2).
3. Last-five Jeffreys, with the same 0.5/0.5 prior.
4. Global-mean shrinkage: 25 prior attempts centered on the earlier all-division
   pooled defense rate, without division assignment.
5. Earlier population mean alone, using the same division/fallback baseline as v1.

Choose the strongest simple challenger by conditional binomial negative log
likelihood on 2012-2018 common support only; deterministic listed-order ties.
Do not use 2019+ scores for challenger selection. Both this choice and the
already selected prototype k remain fixed throughout the 2019+ comparison.

Primary comparisons reuse the exact 4,197 v1 common-support side-bouts, when
available in this snapshot; also report the established subset (3+ prior bouts,
10+ prior attempts), raw non-boundary subset, and cold-start coverage separately.
Primary score: mean conditional binomial negative log likelihood per side-bout,
including the combinatorial term. Secondary: attempt-weighted cross entropy
and attempt-level Brier score, calculated from stopped/allowed counts.
All probabilities use the same [1e-6,1-1e-6] scoring clip. Report raw-reference
clip sensitivity at 1e-3 and 1e-2 without reselecting any model.

Bootstrap paired score differences using whole date clusters, 1,000 replicates,
seed 20261026. A score interval describes the comparison, never fighter skill.
Report years, eras (2019-2022 / 2023+), divisions and exposure groups. A subgroup
is sufficiently sized for a flag only with 100+ sides and 20+ date clusters.
Flag a material regression when adjusted minus selected simple challenger is
above +0.05 NLL/side and its 95% cluster interval lies above zero. Smaller groups
are explicitly inconclusive, not passing. These engineering flags are diagnostic,
not a clinical/scientific validation threshold or a public-release approval.

## Predictive uncertainty and calibration

The estimand is stopped takedowns in a later bout conditional on its actual
opposing attempt count and observed division. This does not validate a future
attempt-count, duration, opponent-quality or winner forecast.

Compare two explicit predictive families:

- Plug-in binomial with the frozen pre-date point estimates above.
- Beta-binomial posterior predictive distributions for career Jeffreys,
  career Laplace, last-five Jeffreys and the v1 sample adjustment. For the latter,
  alpha = prior stopped + 25 * earlier baseline and
  beta = prior allowed + 25 * (1-earlier baseline).
  This assumes a constant individual probability and conditionally binomial
  trials. The empirically estimated baseline and k are treated as fixed; their
  uncertainty, opponent variation, time variation and within-bout clustering
  are not propagated. This is a candidate approximation, not a full hierarchy.

Use SciPy binom/betabinom CDF, PMF and PPF. Evaluate 50% and 90% equal-tail
integer-count ranges, observed coverage, average width and their expected mass
under the stated distribution. Discrete ranges can exceed nominal coverage
even under a correct model; do not call that automatic calibration success.

Also calculate a randomized probability-integral transform:
U = F(y-1) + V * P(Y=y). V is reproducible from a hash of seed, fight ID and
fighter ID, shared across methods. Primary seed 20261027, sensitivity seeds
20261028 and 20261029. Under a correct conditional distribution this PIT is
uniform, avoiding conservative integer-range discreteness. Report PIT central
90%/50% coverage, ten-bin histograms, 95% date-cluster bootstrap intervals and
seed sensitivity. Diagnostic bands: 87-93% for nominal 90%, 45-55% for nominal
50%. Fewer than 500 side-bouts overall or subgroup sizes below the above minimum
are inconclusive. Bands are diagnostics; passing them does not satisfy all
handoff release gates. Use the same v1 support for primary comparisons and
report the broader positive-trial cohort as a separate coverage population.

A beta parameter interval is a different object. Do not test it against individual
observed fight outcomes. Validate its numerical coverage only in synthetic data
with a known, matching constant latent probability. Synthetic recovery uses
8,000 independent fighters, p~Beta(6,4), prior trials sampled from {0,5,20,100},
and a future binomial bout with 1-20 attempts; fixed seed 20261026. Check posterior
mean bias/RMSE, 90% latent-rate interval coverage, predictive count coverage and
PIT coverage by prior trial count. This verifies the matching model arithmetic;
it cannot establish that real MMA data obeys those assumptions.

## Reliability and stabilization

For M={2,3,5,8,10} recorded bouts per half, compare a fighter's first M with their
next M bouts. No fight appears in both halves. Exclude boundaries cutting one
calendar date, and require 10+ recorded opposing attempts in each half for the
primary reliability table; report a secondary positive-attempt-only threshold.
Report attrition, number of fighters, trials, Pearson and Spearman correlation,
and 500-replicate fighter-bootstrap 95% intervals, seed 20261026. No p-value or
Spearman-Brown correction is used. Also report consistent-division slices when
50+ fighters exist. Fixed first/second halves avoid cherry-picking windows.

This is descriptive repeatability among fighters who survive to enough recorded
bouts. Time changes, opponent schedules and career selection can affect it.
No universal minimum-fight threshold will be selected from this table. There is
no direct real-data ground truth for a fighter's latent defense probability.

## Decision

Always retain public_release=false and opponent_adjusted=false. Report separately:
point-score evidence beyond simple smoothing, subgroup flags, conditional
predictive calibration, synthetic checks and descriptive reliability. Identify
failed or inconclusive checks explicitly. A protected future evaluation block
and the remaining handoff gates are still required for any public release.
A later opponent-adjustment project needs a separate specification; this study
must not silently turn into it or restore rankings.

Implementation references:
- https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.binom.html
- https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.betabinom.html
- https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.beta.html
- https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.spearmanr.html
