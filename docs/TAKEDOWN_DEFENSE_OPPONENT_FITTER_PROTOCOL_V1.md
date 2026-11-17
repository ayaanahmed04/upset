# Opponent fitter contract, v1 — October 26, 2026

Fixed before fitting real outcomes. This is a numerical/design milestone, not
a test that opponent adjustment improves prediction. Existing 2019+ data have
already been inspected and remain development data.

## Data and objective

Read and hash-verify the existing paired adapter. Validate reciprocal permanent
IDs, event date/ID, source, source-row and database hashes, nonnegative integer
counts and stopped = attempts - landed. Exclude missing/invalid measurements;
zero attempts add no likelihood or fighter-role exposure. Use only dates
strictly before the requested cutoff, sorting deterministically. Never use
future rows to create the fitted role dictionaries.

For defender i and attacker j, eta = intercept + defense_i - attack_j,
mu = logistic(eta), a = 5*mu, b = 5*(1-mu). Minimize the **sum** of negative
beta-binomial log PMFs plus (4/2) times the sum of squared role coefficients
and (0.01/2) times the squared intercept. Concentration 5 is fixed from v3;
4 is a fixed engineering regularization choice, not selected by real scores.
No independence of attempts within a bout is assumed. The objective treats
bout-side outcomes as independent working contributions; repeated fighters
and paired sides remain dependent. No inferential standard errors follow.

The first context is one global intercept, without division or era terms.
Audit division/era/source coverage and separate-role schedule connectivity.
Effects can absorb these omitted contexts and cannot support public skill
comparisons. Independent zero-centered role penalties anchor shift freedoms,
including disconnected schedules. This defines the penalized fit; it does not
make disconnected schedules empirically comparable. Unknown roles predict
zero effect. An entirely unseen matchup uses the fitted intercept.

Use analytic digamma derivatives and SciPy L-BFGS-B with all coefficients
bounded to [-8,8], maxiter 2000, gtol 1e-7 and ftol 1e-16. Run three fixed
starts: zero role effects, and deterministic +/-0.1 perturbations, all with
intercept logit((total stopped+1)/(total attempts+2)). Keep the lowest objective,
record every start. Reject publication of an output if any run fails, any
coefficient reaches a bound within 1e-5, maximum absolute gradient exceeds
1e-4, objective spread exceeds 1e-6, or prediction spread exceeds 1e-5.
Multiple starts diagnose numerical stability, not global optimality.

Numerical revision before real-data fits: the initial ftol 1e-14 stopped on
objective reduction with gradient 1.18e-4 in the matching simulation. Tightened
ftol to 1e-16; the original absolute-gradient acceptance gate stays unchanged.

The beta-binomial PMF and optimizer stopping conditions follow the
[SciPy distribution documentation](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.betabinom.html)
and [L-BFGS-B documentation](https://docs.scipy.org/doc/scipy/reference/optimize.minimize-lbfgsb.html).
Record the installed versions, not the online documentation version.

## Numerical gates and bounded fits

Before real fits, require central finite-difference gradient checks including
all-stopped/none-stopped/n=1 rows and disconnected schedules, equality of the
objective with independent SciPy log PMFs, the correct attacker/defender sign,
zero-attempt invariance, future-outcome/identity invariance, finite extreme
predictions, and explicit rejection of invalid counts/identities or failed fits.

Matching simulation: 36 fighters, centered separate normal effects (SD 0.6),
intercept 0.4, six full directed round robins, random n in [1,18], beta-binomial
concentration 5, RNG seed 20261026. First five repetitions fit, sixth predicts.
Require attack and defense correlations with truth >0.85, each centered RMSE
<0.3 and absolute held-out average probability error <0.05. This checks recovery
under an assumed matching model; it is not real-world validation.

Then fit all positive rows strictly before 2006-01-01 (small benchmark) and
2019-01-01 (representative benchmark). Report rows, trials, dates, fighters,
role-graph components, objective, every optimizer result, elapsed wall time,
convergence and start agreement. Repeat the representative fit and compare
coefficients at 1e-10. No held-out real predictive scores, tuning, event-by-event
backfill, site changes, skill intervals or public release in this milestone.

## Next experiment, after gates pass

Write an executable chronological protocol before real predictive comparisons.
It must compare global shrink25, context-matched defense-only and attack/defense
models with the same fixed beta-binomial concentration 5 and matched rows;
training-only regularization grid {1,4,16}; strictly earlier-date fits; cold
starts; proper NLL/RPS and interval diagnostics; event/date clustering plus
fighter-dependence sensitivity; connectedness, experience, division and era
breakdowns. Distinguish context gains from opponent effects. Do not use
in-sample likelihood or synthetic recovery to claim improvement. A protected
future block and the unresolved high-attempt diagnostics remain release gates.
