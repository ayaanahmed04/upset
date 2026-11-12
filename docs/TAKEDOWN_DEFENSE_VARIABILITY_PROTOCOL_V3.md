# Takedown-defense fight-variability protocol v3

Declared October 26, 2026 before evaluating these new predictive distributions.
This is a new development iteration motivated by v2 failures. Earlier outcomes
have been inspected. There is no protected holdout or public release in this run.

## Fixed inputs and estimand

Reuse the immutable v1 adapter and v2 extended predictions/report. Verify their
hashes and reproduce every v2 prediction with the frozen code. Keep all existing
point estimates, the 25-prior-attempt global adjustment, histories, cutoff
2026-10-26, and date grouping unchanged. All mean-model updates use earlier
calendar dates only. No source changes, API acquisition, site changes, rankings,
winner-model training, opponent adjustment or skill intervals are authorized by
this study.

The target is a future bout's stopped-takedown count, conditional on its actual
opposing attempt count n. This is not a forecast of n, duration, winner, or a
fighter's underlying constant skill. Use the earlier global-mean adjustment mu
for all candidate predictive families. Any gain therefore concerns distribution
shape/variance, not a more accurate mean estimate.

## Three predictive families

1. **Global binomial:** Y~Binomial(n,mu), the frozen strong point reference.
2. **Global stationary posterior:** Y~BetaBinomial(n,A,B), where
   A=earlier career stopped+25*earlier global baseline and
   B=earlier career allowed+25*(1-earlier global baseline).
   Its concentration A+B grows with prior attempt exposure. This supplies the
   matched global-prior posterior comparison missing from v2.
3. **Global bout variability:** q~Beta(mu*kappa,(1-mu)*kappa),
   Y|q~Binomial(n,q). Marginally Y is beta-binomial. Its mean remains n*mu and
   variance is n*mu*(1-mu)*(1+(n-1)/(kappa+1)). Kappa is a predictive concentration,
   not prior fighter attempts. The corresponding rho=1/(kappa+1) is a working
   distribution parameter, not a measurement of within-bout correlation.

Choose one common kappa in {2,5,10,20,50,100,500} by mean conditional predictive
negative log likelihood on the fixed 2012-2018 common-support cohort only.
Tie-break toward the first listed value. Freeze it before 2019+ comparisons.
Report whether selection touches a grid edge; do not expand the grid after
seeing outcomes. Report the count of n>=2 training bouts because n=1 cannot
identify beta-binomial concentration. Bootstrap whole training-date clusters
1,000 times (seed 20261026) to report selection frequencies, without propagating
that uncertainty into the published predictive candidate.

The bout-variability law combines unmodeled effects statistically. It cannot
identify whether variation comes from opponent quality, within-bout dependence,
time changes or source error. It treats mu and selected kappa as fixed and does
not propagate mean/hyperparameter uncertainty. It is not a fully hierarchical
posterior, and q variability must not be presented as a fighter skill interval.

## Development comparison and diagnostics

Primary support is exactly the v2 4,197 common-support side-bouts, with both
stronger baselines available. Also report established support (3+ prior bouts,
10+ prior attempts) and all positive-trial rows as separate populations,
including a cold-start subgroup with zero prior attempt exposure. Zero-attempt
held-out rows remain unavailable for rate calibration and contribute no trials.
Do not add easier rows to just one candidate's primary comparison.

Primary score is mean conditional predictive NLL per side-bout, including the
combinatorial term. Secondary score is the discrete ranked probability score
RPS=sum over k=0..n-1 (F(k)-1[y<=k])^2, normalized by n and averaged per side-bout.
Report paired new-minus-reference differences with 95% whole-date bootstrap
intervals, 1,000 replicates, seed 20261026. Point-probability Brier scores are
identical across families and cannot support a new mean-accuracy claim.

For 50% and 90% equal-tail integer-count ranges, report observed coverage,
expected probability mass under the stated distribution, width, and interval
score IS=(upper-lower)+2/alpha*(lower-y)1[y<lower]
+2/alpha*(y-upper)1[y>upper], where alpha=1-level. Wider ranges receive a width
penalty; coverage improvement alone is insufficient.

Retain randomized PIT diagnostics to account for integer-count discreteness:
U=F(y-1)+V*P(Y=y), with identity-hashed V shared across families. Primary seed
20261027, sensitivity seeds 20261028/20261029. Report central 90% and 50%
coverage, ten-bin histograms, and whole-date bootstrap intervals. Diagnostic
bands remain 87-93% and 45-55%. A primary population needs 500+ side-bouts; a
subgroup needs 100+ side-bouts and 20+ date clusters. A band result is a
predeclared descriptive diagnostic, not proof of complete calibration.

Report years, eras (2019-2022 / 2023+), divisions, prior exposure (0,1-9,10-24,
25-49,50+), and actual attempts (1,2-3,4-9,10+). Thin groups are inconclusive.
Flag a sufficiently sized material score regression if new-minus-reference
mean NLL exceeds +0.05 and its 95% cluster interval lies above zero, against
either reference. Report calibration failures separately, without hiding them
inside an aggregate success. Multiple slices are exploratory diagnostics.

## Synthetic and numerical checks

Generate 8,000 synthetic bouts, fixed seed 20261026: known mu~Beta(6,4),
n uniformly 1..20, true kappa=10, q~Beta(mu*kappa,(1-mu)*kappa), Y~Binomial(n,q).
Use first 4,000 for the same kappa grid selection and the remaining 4,000 for
held-out synthetic diagnostics. Check recovery of the true grid value, count
means/variance, predictive 50/90 PIT coverage and finite outputs. This checks a
known matching count model only; no latent fighter skill interval is constructed.
Independently check beta-binomial probabilities/CDFs by closed-form enumeration
on deterministic real-row samples. Test that n=1 predictions are concentration
invariant and that development outcomes cannot select kappa or change any
pre-bout mean. Preserve all existing study inputs/outputs.

## Decision and next-step bounds

Always retain public_release=false and opponent_adjusted=false. Record separately:
score evidence against both global references, interval-score evidence,
calibration bands, subgroup flags, numerical recovery and unchanged point means.
Require score intervals below zero against both references for a positive
predictive-score conclusion. Overall band compliance cannot erase subgroup
failure, data-selection limitations or the absence of protected future evidence.
No public UI, minimum-history threshold or stronger causal interpretation follows.
Do not retune on 2019+ outcomes or repair failed slices within this protocol.

Implementation references:
- https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.betabinom.html
- https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.binom.html
