# Takedown-defense prototype protocol v1

Declared October 26, 2026 before evaluating this prototype.

Purpose: validate a side-level adapter and one offline sample-size adjustment.
No opponent adjustment, ranking, public UI, model retraining, or release gate
approval is part of this prototype.

The outcome is opposing takedown attempts stopped: opposing attempts minus
opposing landed takedowns. Missing/invalid counts remain unavailable; zero
attempts have no observed defense percentage and contribute no trial exposure.
Both sides must have consistent permanent identities and paired source rows.
The input database is read-only and bound to its verified manifest hash.
A cutoff c excludes events on/after c. All observations sharing a calendar date
are predicted before any observation from that date updates history. Event IDs
are retained; date grouping conservatively prevents same-day leakage.

At each event, the prior mean is the earlier division's pooled stopped/attempted
rate if at least 200 earlier attempts exist in that division; otherwise the
pooled earlier all-division rate. With no earlier attempts, use no estimate.
No estimated position clock is needed. The prototype mean is
(stopped + k * prior_mean) / (attempts + k), using career observations strictly
before the event. This is sample-size adjustment, not opponent adjustment. It
estimates defense conditional on takedown attempts occurring; it does not
forecast how many attempts or what duration a future fight will have.

Tune only k in {5, 10, 25, 50, 100} on dated predictions during 2012-2018.
Use earlier observations to seed histories. Select the lowest mean conditional
binomial negative log likelihood per scored side-bout; break ties toward the
smaller k. Freeze k before examining 2019+ results. Update observed histories
and baseline sufficient counts only after each later date has been predicted.
This is a first tuning rule; the resulting prior is not a fitted population
variance or a fully Bayesian hierarchy.

Compare the chosen mean against raw career and raw last-five rates. Last-five
means the five previous bouts, including bouts with zero/unavailable attempts;
only available attempt counts enter its denominator. All primary comparisons
use the exact same eligible side-bouts where all three estimates exist and the
held-out bout has positive attempts. Include the binomial combinatorial term.
Clip all scoring probabilities to [1e-6, 1-1e-6] using the same rule. Report
counts, trial exposure, cold starts, zero-trial rows, missingness, division/year
breakdowns, and a separate common-support comparison restricted to at least
three prior bouts and ten prior attempts.

Pair comparisons by side-bout and bootstrap whole calendar-date clusters 1,000
times with fixed RNG seed 20261026. The interval is for the score difference,
not fighter skill or observed fight outcomes. Discrete attempts are not treated
as independent bootstrap units. Report both mean side-bout log score and the
secondary attempt-weighted cross entropy.

2019+ is development evaluation: these years overlap previous project work and
are not a pristine holdout. This prototype does not implement or pass the
handoff's full per-stat release gates. No skill or predictive interval is
shipped. Any later public release requires a separate preregistered validation
including calibration, reliability, subgroup regressions, and a protected
future evaluation block. Keep the public page raw.
