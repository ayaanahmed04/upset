# Striking rolling calibration protocol v1

Declared November 4, 2026 after the retained adaptation v1 study missed its
experimental preview bias criterion. This is an explicit subsequent development
study; prior results and thresholds remain unchanged. No fresh-validation claim.

Keep adaptation v1's selected recent-history half-life and prior strength,
chosen using 2012–2015 only. Replace its fixed 2016–2018 intercept with a
prequential 730-calendar-day calibration window. At each prediction date d,
fit one intercept in [-0.5,0.5] using positive-trial, available-base-mean rows
whose dates satisfy d-730 <= date < d. The input means for those rows were
themselves calculated before their event date. All same-day predictions precede
all updates. No current/future outcome can affect an intercept. With no eligible
past calibration rows use intercept=0 and report that fallback. The 730-day
window and bounds are fixed in this protocol, not selected using new scores.

Solve the monotone binomial score equation sum(y-n*expit(logit(base_p)+d))=0;
use the corresponding boundary if the optimum lies beyond the bounds. Verify
against independent bounded binomial-NLL minimization in tests. This correction
updates from earlier outcomes as they become available; it does not refit the
base-model half-life/strength on development observations.

Fit the same declared concentration-at-100 and slope grids on 2012–2018 only,
using the rolling-calibrated historical means. Compare the original fixed
mean/c=20, retained adaptation v1 repair, rolling mean/constant dispersion and
rolling mean/exposure-dependent dispersion on the exact 7,028 original sides.
Retain all previous PIT bands, seeds, subgroup sizes, point-regression criteria,
paired bootstraps and the separate experimental mean-preview gate unchanged.
Do not use October 31 outcomes to score/select this study.

The preview gate still requires point NLL improvement versus the original with
a date-bootstrap upper endpoint below zero, <=1 percentage-point aggregate bias,
and no material point-regression groups. A pass permits only the user's approved
experimental mean-only local preview. No rankings, uncertainty range, opponent
adjustment, winner forecast, validated skill label or public_release approval.

Preserve the failed adaptation v1 and previous validation artifacts. Save the
new source/protocol/config/input hashes, all pre-date intercepts and exposure,
predictions, diagnostics, exact comparisons and decision as new artifacts.
Test chronological window boundaries, simultaneous bouts, future invariance,
empty windows and analytic/optimization agreement before real-data analysis.

For a passing preview, compute the intercept lookup offline for supported daily
cutoffs, using only preceding dated outcomes at each cutoff. Request-time work
is strictly lookup and weighted-history arithmetic, with no fitting. Bind a
separate preview snapshot to its gate-passed report, model and serving database;
reject tampering, future/unsupported cutoffs, and non-career windows explicitly.
