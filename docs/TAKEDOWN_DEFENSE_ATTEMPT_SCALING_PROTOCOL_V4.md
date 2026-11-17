# Takedown-defense attempt-scaling protocol v4

Declared October 26, 2026 before scoring these alternatives. This is a further
iteration on repeatedly inspected development data, prompted by the v3 10+
attempt calibration failure. It is not an untouched holdout, independent
preregistration, opponent model or public release.

## Frozen reference, mean and cohort

Preserve all v1-v3 artifacts and source files. Verify their hashes, reproduce
all 17,708 v3 prediction rows and the selected v3 constant concentration of 5.
Keep the global defense mean, 25 prior attempts, date-group chronology and
exclusive 2026-10-26 cutoff unchanged. Means and point Brier scores must remain
identical. No API acquisition, website edits, rankings, source-stat changes,
frozen winner-model fitting, or fighter skill intervals.

The outcome remains stopped takedowns conditional on the actual opposing
attempt count n. Dependence on n is allowed in this conditional variance study;
it is not evidence for forecasting n, fight duration or winners before a fight.

## Candidate variance law and training-only selection

Use the same beta-binomial family as v3 with alpha=mu*kappa(n),
beta=(1-mu)*kappa(n). Change concentration to:

kappa(n) = c * (max(n,1)/5)^gamma.

The anchor is five attempts. c is concentration at that anchor, not fighter
prior attempts. gamma=0 recovers constant concentration; gamma=1 makes
high-n count variance grow approximately linearly rather than quadratically.
The variance is n*mu*(1-mu)*(1+(n-1)/(kappa(n)+1)). At gamma=1 the large-n
variance multiplier tends to 1+5/c. n=1 still cannot identify concentration.
This is a working conditional count distribution, not observed physical
correlation, a causal model, or uncertainty about a fighter's underlying skill.

Predeclare c in {2,5,10,20,50,100} and gamma in {0,0.5,1}: 18 candidates.
The fixed v3 reference (c=5,gamma=0) is included. Select by mean predictive NLL
on the unchanged 2012-2018 common-support cohort only. Ties within 1e-12 prefer
the first listed candidate, with gamma ordered 0,0.5,1 then c ascending.
Freeze c/gamma for all later outcomes. Report grid-edge selection and whole
training-date bootstrap selection frequencies (1,000 replicates, seed 20261026).
Do not expand the grid, select by interval coverage or repair subgroups after
seeing 2019+ results.

## Comparison

Primary reference: the frozen v3 constant-concentration 5 distribution, with
exactly the same mean and 4,197 common-support sides / 333 date clusters.
Also retain global binomial and global stationary-posterior references. Report
proper predictive NLL, normalized discrete RPS, and 50%/90% interval scores.
For each reference report new-minus-reference paired whole-date bootstrap
intervals, 1,000 replicates, seed 20261026. A positive score conclusion requires
the NLL interval below zero against the v3 reference, not just the older models.
Report 90% interval-score evidence separately; coverage gains alone are not
sufficient. Point mean accuracy cannot improve when only variance changes.

Retain all v3 populations and diagnostics: primary common support, established
history, all 5,000 positive-trial sides, 778 zero-prior-exposure sides; years,
eras, divisions, prior exposure, and actual-attempt slices. Mark primary groups
below 500 sides and subgroups below 100 sides / 20 date clusters inconclusive.
Flag material NLL regression if mean new-minus-reference exceeds +0.05 and its
95% cluster interval lies above zero. Multiple slices remain exploratory and
are not independent formal tests.

For count intervals report actual coverage, expected discrete mass, width and
interval scores. For discrete-adjusted calibration use the same identity-hashed
PIT seeds 20261027/28/29, bands 45-55% for 50% and 87-93% for 90%. Report bootstrap
intervals and sensitivity, not just pass/fail. The known high-attempt slice must
be reported even if aggregate metrics improve. Do not tune toward those bands.

## Synthetic and numerical verification

Synthetic recovery: 8,000 independent bouts, mu~Beta(6,4), n uniformly 1..30,
true c=5 and gamma=1, seed 20261026. Draw q from Beta(mu*kappa(n),
(1-mu)*kappa(n)), then stopped count from Binomial(n,q). Use first 4,000 for the
same candidate selection and remaining 4,000 for synthetic diagnostics. Check
recovery of the known grid pair, analytical mean/variance, and 50%/90% PIT
coverage. Synthetic success verifies a matching model, not real-data validity.

Unit tests must cover gamma=0 exactly reproducing v3, the five-attempt anchor,
n=1 concentration invariance, the gamma=1 high-n variance limit, chronology,
future-independent parameter selection, invalid parameters and finite count
probabilities. Independently enumerate PMFs/CDFs/moments/RPS on deterministic
real-row samples. Validate all output and original-input hashes.

## Decision and limits

Always retain public_release=false and opponent_adjusted=false. Separate score
improvement beyond v3, aggregate calibration, subgroup failures/inconclusiveness
and mean preservation. Report the strongest honest conclusion even if the
training-selected model does not fix the known slice. No change to predictive
means or claim of a reliable minimum history follows. Mean/hyperparameter
uncertainty, longitudinal dependence and protected future validation remain
outstanding. Opponent adjustment requires a separate specification.

References:
- https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.betabinom.html
- docs/TAKEDOWN_DEFENSE_VARIABILITY_PROTOCOL_V3.md
