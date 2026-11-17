# Bounded chronological opponent pilot — v1

Defined October 26, 2026 after the first fitter's numerical gates passed.
**Not run in the fitter milestone.** Before scoring, implement the matched
defense-only fit and prediction exporter, and test them against this contract.
Do not change this protocol after looking at pilot scores without declaring
a new study. These years have already informed earlier model work and are
development data, including the 2018 diagnostic year.

## Bounded schedule and selection

Use six annual snapshots at January 1 of 2012 through 2017. Each uses only
eligible positive-attempt adapter sides strictly before its cutoff and predicts
all eligible positive-attempt sides in that calendar year. All sides on one
date share the same model. Annual snapshots deliberately limit runtime; they
are not the previous studies' event-updated predictions. Use the same freshness
for every comparator. No 2019+ predictive scoring in this pilot.

For the defense-only and attack/defense models separately, select the shared
role penalty from {1,4,16} using pooled side-weighted predictive NLL across
2012-2017. All six snapshots must be scored for every candidate on identical
rows. Ties within 1e-12 choose the larger penalty. The attack/defense candidate
uses the same penalty for both roles. No division or era term, recency window,
new concentration or alternative grid will be tuned during this pilot.

Freeze both selected penalties, refit before 2018-01-01 and evaluate calendar
2018 once as a development diagnostic. Report the entire selection table and
per-year scores, not just the winning candidate. Fits use the existing v1
beta-binomial objective (concentration 5, intercept penalty 0.01, bounds and
three-start numerical gates unchanged). A failed candidate fit blocks the
matched comparison; do not silently drop its rows or replace its penalty.

## Four matched means, one predictive family

1. Raw career stopped/attempted at the snapshot, clipped to [1e-6,1-1e-6]
   for finite probabilities. Report how many means require clipping.
2. Global shrink25: (defender's earlier stopped + 25*earlier global rate) /
   (defender's earlier trials + 25). Earlier global rate uses only snapshot
   observations. This is an annual-snapshot recreation, not the existing
   event-updated v3 prediction file.
3. Defense-only: intercept + defender effect, same working likelihood and
   context as the opponent candidate, with its own training-selected penalty.
4. Attack/defense: intercept + defense - opponent attack, fitted by v1.

Every mean uses beta-binomial(n, 5*mu, 5*(1-mu)) at the actual held-out attempt
count. This is conditional count prediction, not forecasting opportunities,
latent skill intervals or victory probability. Mean/hyperparameter uncertainty
is omitted equally and must be stated.

Primary support: held-out positive-count sides whose defender had at least two
positive-count bouts before the snapshot. Evaluate every model on those exact
rows. Raw career has no cold-start mean; report broader positive sides and
zero-history defender/opponent cohorts separately for the other three models.
An unknown role uses zero effect; global shrink25 cold starts use the global
rate. Excluded/zero-attempt sides remain counted in the audit, not imputed.

## Diagnostics, dependence and interpretation

Record per-side predictions, source hashes, cutoff, history exposures,
defender/opponent cold starts and role-graph component membership. Predicting
across role components is allowed by the penalty anchor but labeled as such;
report within-component and across-component groups separately.

Report conditional NLL, normalized RPS, integer 50%/90% ranges with their
expected discrete masses and interval scores, randomized PIT checks and
histograms. Use v3's PIT keys/seeds (20261027/28/29) and diagnostic bands
45-55% / 87-93%; require 500 sides and 20 dates for an overall diagnostic,
100 sides and 20 dates for subgroup diagnostics. Thin groups are inconclusive.
Include division, year, defender/opponent history and actual n=1,2-4,5-9,10+
slices. Keep overlapping flags separate from independent discoveries.

Use paired loss differences with whole-date bootstrap (1000 replicates,
seed 20261026). Add a crossed-fighter sensitivity: assign independent
Exponential(1) weights to permanent IDs, give each held-out side the product
of its defender and attacker weights, normalize within each replicate and
recompute paired mean losses (1000 replicates, seed 20261030). Both sides of
a bout share the same fighter-product weight. This probes repeated-fighter
dependence; it is not a universally valid confidence interval. Present it
beside the date bootstrap, without treating either as a protected test.

The primary opponent-specific contrast is attack/defense minus defense-only.
Global-shrink comparisons describe the whole candidate change. Proceed to a
larger event-updated development backfill only if 2018 mean NLL improves on
both, normalized RPS does not worsen, the upper paired NLL intervals under
both resampling schemes are below zero, no sized subgroup has a >0.05 NLL
regression with a positive lower date-bootstrap bound, and fit gates pass.
Otherwise retain the references and report the failed gate. Do not tune to
repair 2018. Even passing this pilot cannot authorize public display: the
high-attempt diagnostic and protected future evaluation remain open.
