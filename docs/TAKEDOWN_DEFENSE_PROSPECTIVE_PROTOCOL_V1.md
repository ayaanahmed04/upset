# Frozen takedown-defense reference: prospective protocol v1

Declared October 26, 2026, after the exploratory opponent pilot failed its
proceed gate. This is a new future-only evaluation of the retained global
shrinkage / bout-variation reference, not a repaired opponent experiment.

## Fixed block and immutable freeze

Future event dates: **2026-10-27 inclusive to 2027-10-27 exclusive**. No earlier
outcome is a prospective test observation. The input seed contains all 17,708
adapter sides strictly before 2026-10-26; its latest event is 2026-10-24.
The gap day October 26 contributes no new observations unless a new study is
declared before its future block. Freeze before the block starts. Record the
UTC creation time, seed/database/manifest hashes, source dependencies, protocol,
fixed configuration and installed Python/numpy/scipy versions.

Future full-history adapters must preserve every seed side and all original
fields exactly, except database_sha256, which legitimately changes when the
serving snapshot gains rows. Reject changed counts, provenance, dates, IDs,
deleted sides, duplicate sides, altered pairings, new pre-block historical rows,
invalid measurements, unverified database hashes and changed frozen code/config.
Historical corrections require a separately declared study; never silently
rewrite the protected input. Reject known post-block rows only from scoring,
not from an otherwise valid later full-history adapter.

The code can verify preservation of known history, not completeness of future
acquisition. A final evaluation additionally requires a saved local completeness
attestation with the exact future adapter hash, the exact block, zero unresolved
eligible bouts and an evidence note from a separate source review. Its presence
is an explicit human/reviewer assertion, not proof supplied by this evaluator.
Do not fabricate that attestation for today's empty future block.

## Frozen predictions and support

Update histories only after every side on a calendar date is predicted.
The candidate mean is (career stopped + 25*earlier global rate) /
(career attempts + 25). The earlier global rate pools all observed attempts.
Candidate predictive counts use beta-binomial(n, 5*mu, 5*(1-mu)). No opponent
adjustment, mean uncertainty or hyperparameter uncertainty is represented.
Actual held-out attempts condition these predictions; they are not forecast.

References: raw career and raw last-five means, each with the same fixed
beta-binomial concentration 5. Last-five consumes all recorded bouts, including
zero or unavailable measurements; only valid attempts enter its denominator.
An additional global25 binomial reference isolates the variation component.
Clip scoring means consistently to [1e-6,1-1e-6] and count clipping.

Primary support is positive held-out attempts with both raw-history rates and
the candidate mean available. No estimated minimum-data release threshold is
implied. Report broader positive-count and zero-prior-attempt defender groups
for the candidate/binomial models separately. Zero-attempt sides update bout
history but contribute no trials or rate score. Missing/invalid measurements
consume a last-five slot, never become measured zero counts.

## No early score peeking

Before 2027-10-27 UTC, status inspection may report only dates/counts and hash
compatibility. Finalization must refuse **before reading future outcome rows**.
There is no rolling score, automatic notification, scheduled refresh or public
display. At the end, use one complete adapter with before_exclusive at least
2027-10-27 and the separate completeness attestation. Refuse a finalized report
with no positive prospective observations. A status file with zero observations
is pending, not a passed test.

## Fixed diagnostics and interpretation

Use predictive NLL, normalized RPS, integer 50%/90% ranges with expected discrete
mass/width/interval score, randomized PIT checks and 10-bin histograms. Reuse
existing PIT keys/seeds 20261027/28/29 and whole-date paired bootstrap (1000,
seed 20261026). Also show crossed-fighter weight sensitivity (1000,
seed 20261030), whose limitations remain explicit.

Require 500 primary positive sides and 20 dates for overall interpretation;
100 sides and 20 dates for each subgroup. Report division, calendar year,
prior positive-trial exposure (0,1-9,10-24,25+ attempts) and opposing attempts
(1,2-4,5-9,10+). Thin groups are inconclusive. The high-attempt slice is a
required critical check: it cannot pass while thin. All thresholds remain fixed
even if the one-year block is too small; do not extend the block after results.

A baseline-evaluation pass requires candidate NLL below raw career and raw
last-five, upper paired NLL intervals below zero under both dependence schemes,
nonworse mean RPS against both, overall PIT 50% in [45%,55%] and 90% in
[87%,93%], and a sized 10+ attempt group passing both bands. Any sized subgroup
with >0.05 NLL regression and positive lower date-bootstrap bound blocks a pass.
Compare the binomial reference descriptively; it is not another tuning choice.

This is only a retained-baseline predictive check. **public_release always
remains false**: no validated skill interval, reliability threshold, opponent
adjustment or displayed window estimator is supplied. Do not remove the raw
site's disclaimer or restore rankings. Even a future predictive pass does not
complete the handoff's per-stat release requirements.
