# First opponent-quality model: bounded specification draft

Prepared October 26, 2026 after the v4 variance study. This is a draft for the
next offline implementation, not a fitted model, a complete preregistered
evaluation protocol, or authorization to publish a statistic.

## Question and observed response

Can we explain held-out stopped-takedown counts better by separating a fighter's
defense from the takedown ability of the opponents they faced?

Use the existing paired adapter. For defender i facing attacker j, the response
is opposing takedowns stopped s out of opposing attempts n. Keep permanent
fighter/opponent IDs, event/date, source hashes, measurement eligibility and
zero-attempt handling. Missing or invalid counts stay unavailable. n=0 adds no
binomial likelihood contribution. No position-time proxy or joint strike count
is required. The existing global-mean adjustment remains a fixed reference.

## Candidate mean model and sign convention

A minimal candidate is:

logit(p_stopped(i,j)) = context + defense_i - attack_j.

Higher defense increases the chance of stopping an attempt; higher opponent
attack decreases it. Attack and defense are separate coefficients even when
the same fighter ID appears in both roles. The response is not fight victory.
A synthetic high-attack opponent must lower expected stopped counts at fixed
defense; a synthetic high-defense fighter must raise them at fixed attack.

Partially pool both sets of effects toward zero with explicit penalties.
The context initially needs a documented intercept/division/era treatment, an
identifiability convention, and a policy for unknown or sparse contexts. Those
choices and a small penalty grid must be fixed in a separate runnable protocol
before inspecting any new model scores. Do not select them on 2019+ outcomes.
An unobserved fighter begins at the context baseline, with cold starts reported
separately. These effects are statistical schedule adjustments, not causal
measurements of technique or physical ability.

## First implementation milestone

1. Build a paired design-contract audit, including the attacker/defender sign,
   event grouping, sources, connected components, context coverage and zero
   opportunities. Carry forward the existing adapter, not a new data scrape.
2. Implement one regularized count/trial fitter with a fully specified objective,
   numerical-gradient checks, and synthetic recovery under a matching model.
   Decide explicitly whether the first fitting likelihood is binomial or the
   frozen beta-binomial working law; do not silently mix their uncertainty
   interpretations or treat within-bout attempts as independent evidence.
3. Measure one small fit and one representative pre-2019 fit. Require finite
   output, convergence diagnostics, reproducibility and measured runtime before
   attempting a long event-by-event backfill.
4. Only after the fit contract passes, define a bounded chronological experiment
   against the frozen global mean using matched observations and predictive
   families. Keep prior v3 concentration=5 as an explicit reference; any retuning
   must be training-only and separately declared.

No full 20-model expansion, winner-model refitting, composite rating, web API or
public display is part of that first milestone.

## Chronology and comparisons

Fit only rows strictly before the event being described. Snapshot all outcomes
on one date before updating either fighter role. Do not use a fighter's current
career aggregates or the evaluated bout to estimate its opponent effects.
For a later page window, distinguish a cutoff-snapshot résumé view from an
'as known before the original fight' prediction. Do not imply they are identical.

Keep the already inspected 2019+ years labeled development. A protected future
block is still needed before a public validation claim. Compare raw baselines,
the global shrink-only reference, a shrink-only candidate with matching context,
and the actual opponent-adjusted candidate on the same eligible rows. This
separates gains from context/pooling from gains due to opponent quality.

Use paired whole-event/date comparisons, proper predictive scores, conditional
50%/90% calibration and subgroup/experience breakdowns. Report exclusions,
newcomers, unconnected schedules and thin contexts. Fighter reuse across dates
creates dependence beyond the event bootstrap and needs a documented sensitivity
analysis. Reliability, latent-parameter recovery and predictive calibration have
different purposes; none substitutes for the others.

## No premature uncertainty or release claims

A penalized optimum plus diagonal curvature is not automatically a Bayesian
posterior. Define the estimand, approximation and covariance treatment before
producing a fighter skill interval. The observed fight distribution also needs
outcome variation; v3 variability is a candidate predictive law, not uncertainty
about a constant fighter skill. The high-attempt failure remains unresolved.

No opponent adjustment is implemented merely by writing this specification.
All existing public statistics remain raw, and rankings stay removed. Per-stat
release gates apply before any future display or disclaimer changes.
