# Striking drift and exposure adaptation protocol v1

Declared November 4, 2026 before calculating this study's fits or comparisons.
Purpose: repair the mean drift and attempt-volume calibration failures found
in striking validation v1, and prepare a bounded path to an experimental local
preview. This is an explicitly new development experiment over already inspected
years, not fresh validation. Earlier studies, data and frozen defense are intact.

## Data and chronology

Reuse and hash-check the original adapter, accuracy prototype and validation
report/artifacts. Reproduce the original fixed-k=500 predictions and verify the
prior study's primary support before fitting new parameters. Keep the exclusive
October 26 cutoff and original 7,028 comparable development sides. Do not use
October 31 outcomes. Separate point-mean tuning (2012–2015), intercept fitting
(2016–2018), distribution fitting (2012–2018), and development diagnostics (2019+).
All calendar-date predictions precede every update from that date.

## Recent-weighted means and train-only calibration

For each proposed half-life h in {365,730,1460,2920} days, decay both global
landed/attempted totals and each fighter's counts by 2^(-elapsed_days/h) before
each date. Predict p=(fighter_landed+k*global_rate)/(fighter_attempted+k) using
only earlier dates. Tune k over {100,500,1000}. The missing-history/global-mean
rules, true zeros and recorded-bout slots remain explicit. A missing/invalid
measurement contributes no exposure and no invented outcome.

Select (h,k) by mean conditional binomial NLL on original common support during
2012–2015, tie toward listed half-life then listed k. This is a new mean family;
do not alter the original k=500 study. Add a single bounded logit intercept d:
p_calibrated=expit(logit(p)+d). Fit d in [-0.5,0.5] by binomial NLL on 2016–2018
original common support only. No actual current attempt count enters the mean;
no 2019+ outcome is used to select or repair any parameter. Evaluate clipped
means at [1e-6,1-1e-6]. Retain uncalibrated recent-weighted mean as an ablation.

## Exposure-dependent bout variation

Use beta-binomial counts with a=p*c(n), b=(1-p)*c(n),
c(n)=c100*(max(n,1)/100)^g. Fit (c100,g) on 2012–2018 common-support predictive
NLL over c100={5,10,20,50,100}, g={0,0.5,1,1.5,2}, deterministic listed-order
ties. Actual current attempts are an explicitly conditioned scoring exposure,
not a pre-fight opportunity forecast. No attempt count is needed for the
experimental site mean; no count/skill interval will be displayed there.

Compare five families on exactly the original development support:
original fixed mean with c=20; original mean with independently tuned exposure
variation; calibrated recent mean with separately tuned constant concentration
c100 in {5,10,20,50,100}; calibrated recent mean with independently tuned exposure
variation; and uncalibrated recent mean with independently tuned exposure
variation. Report every grid and boundary; do not expand them after inspection.
Retain the selected population-mean/c=20 reference from prior validation too.

## Diagnostics and decisions

Reuse the previous PIT seeds 20261105/6/7 and bootstrap seed 20261104 so paired
comparisons and diagnostics are directly comparable. Report predictive NLL,
point binomial NLL/cross entropy/Brier, mean count error, attempt-weighted
observed/predicted accuracy, 50%/90% randomized-PIT coverage, integer interval
coverage/mass/width and Pearson dispersion. Primary and established support
remain identical. Retain cold-start coverage separately.

Use 1,000 whole-date bootstrap replicates and primary fighter-trajectory
sensitivity. No one-way procedure resolves all crossed dependence. Inspect all
40 prior subgroup definitions and unchanged diagnostic size/band rules:
overall 500 sides/20 dates, subgroups 100 sides/20 dates, central 50% bands
45–55%, central 90% bands 87–93%, all three PIT seeds in band. Flag material
point regressions versus both original mean and prior selected simple mean
when the paired NLL increase is >0.05/side and the date interval is above zero.
Compare repairs against original and simple-reference predictive distributions.
No multiplicity-adjusted or pristine-holdout claims.

The experimental *mean-only* preview criterion is deliberately separate from
full distribution validation: candidate point NLL must improve on the original
with a date-bootstrap upper endpoint below zero, aggregate accuracy error must
be within +/-1 percentage point, and there must be no material point-regression
flags in sufficiently sized groups. A preview must be explicitly labelled
experimental and recent-weighted, preserve raw statistics and never claim
opponent adjustment, calibrated skill uncertainty or winner prediction. Passing
these engineering checks is not public_release or a validated skill rating.
Enabling that optional local UI depends on the user's stated preview preference.

Full distribution checks require overall and all sufficiently sized
actual-attempt groups in band, no other sufficiently sized subgroup failures,
and no point regressions. Thin groups remain inconclusive. Even passing those
historical diagnostics does not complete protected future evidence or the
remaining skill release requirements. Record failures rather than retuning.

## Numerical and preservation checks

Test exact exponential decay, same-date and future leakage, missing/zero history,
intercept fitting separation, selection separation, conditional means/variances,
constant-concentration nesting, extreme/invalid inputs and artifact tampering.
Use a matching synthetic exposure-varying model with known concentration slope
to verify grid recovery; this is software arithmetic, not MMA evidence. Verify
all new predictive scores independently by log-beta/log-gamma formulas. Preserve
existing snapshots, reports, source, portraits, site and frozen defense. Any
later preview is a separate opt-in artifact/feature with its own explicit
provenance, coverage and checks; it cannot modify these historical studies.

Always report public_release=false and opponent_adjusted=false. Save source,
protocol, input, configuration and runtime hashes, all predictions, comparisons,
decisions and a static figure. Use new output paths; no overwrites.
