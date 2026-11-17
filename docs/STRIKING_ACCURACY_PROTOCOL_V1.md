# Significant-strike accuracy prototype protocol v1

Declared November 3, 2026 before computing this prototype's tuning or evaluation
scores. This is a new development experiment over already inspected historical
years, not an untouched holdout or independent preregistration.

## Bounded milestone and data

Export paired side-level total significant-strike observations from the verified
serving SQLite snapshot. Open it read-only, check its manifest hash, integrity,
paired participants, permanent UUID4 identities, provider links against the
explicit registry, source IDs, stored/payload dates and shared duration. Preserve
database, registry, source-row and implementation hashes. Cutoff is exclusive;
the first real run uses before=2026-10-26 and the retained snapshot through
2026-10-24. This run makes no provider requests or claims of current coverage.

Retain own and opposing landed/attempted totals, shared full-fight seconds,
division, event ID (or explicitly labeled provider/date fallback), source URL,
identities and provenance. Missing counts stay unavailable; invalid counts stay
unavailable with a distinct reason; observed 0/0 remains a true zero-attempt
observation with no accuracy percentage. Positive attempts with zero duration
are ineligible. Missing duration can still support count accuracy, but never a
per-minute rate. Both recorded durations must agree, including missingness.
Invalid numeric types, negative durations and structural identity errors stop
the export. Short fights are retained, flagged and reported; no silent minimum
duration filter. Record raw invalid/missing inputs separately from usable counts.

Accuracy eligibility is side-specific: missing opposing counts do not erase
observed own counts. The adapter also records landed significant strikes per
full fight minute when own counts and positive duration exist. That descriptive
rate is not a pace/intensity model. Component attempts, positional clocks and
position-by-target intersections are outside this version.

## Estimator and chronology

The outcome is a fighter's significant strikes landed conditional on that
bout's actual recorded significant-strike attempts. No opponent adjustment,
future attempt/duration forecast, winner prediction, ranking, skill interval,
predictive interval or site integration is included.

At each date, use only earlier dates to compute career landed/attempted counts,
the previous five recorded bouts, and the global pooled landed/attempted rate.
Predict every bout on a calendar date before updating any history for that date.
Distinct same-day bouts are retained. Their deterministic fight-ID order only
defines subsequent last-five history when a window ends inside a same-day batch;
report how many such boundary windows occur. All missing/zero-attempt bouts
consume last-five slots but add no trial exposure. Cold-start raw rates are
unavailable. No earlier global attempts means no population mean or shrinkage
estimate; fixed Jeffreys estimates can still be computed.

The candidate mean is (prior landed + k * earlier global rate) /
(prior attempts + k). Tune k independently for striking over {1,5,20,100,500}
using 2012-01-01 through 2018-12-31 only. Choose the lowest mean binomial negative
log likelihood on identical common support; tie toward smaller k. Earlier dates
seed histories. No defense parameter or previously selected concentration is
reused. Challenger/reference means are raw career, raw last-five, career
Jeffreys (landed+0.5)/(attempted+1), last-five Jeffreys, and earlier global rate.
References and all thresholds are fixed before the real run.

## Development comparison

Evaluate from 2019-01-01 through the adapter cutoff. Common support requires
positive observed current attempts and all six means available. Preserve every
prediction and report coverage/attrition for all side-bouts, cold starts,
missingness and zero attempts. Report an established subset with at least three
prior recorded bouts and 100 prior attempts. Report each method's broader
coverage separately; never compare methods on different primary populations.

Primary score: mean conditional binomial negative log likelihood per side-bout,
including the combinatorial term. Secondary scores: attempt-weighted cross
entropy and attempt-level Brier score from landed/missed counts. Clip all scoring
probabilities consistently to [1e-6,1-1e-6]; also report common-support sensitivity
at 1e-3 and 1e-2 without selecting again. Binomial independence is a working
scoring assumption and can understate within-bout variation; no calibrated count
distribution or interval claim follows from a better point-estimate score.

Compare the candidate to every fixed reference on paired side-bouts; bootstrap
whole calendar dates 1,000 times, RNG seed 20261103. With fewer than two dates,
return no bootstrap interval. These are score-difference intervals, not fighter
skill intervals. Date clustering preserves bout/date dependence but does not
resolve dependence from fighters appearing across dates. Report the limitation.

Report scores by year, division, provider, current duration (<60s vs >=60s vs
missing/zero), and prior attempt exposure (0,1-99,100-499,500+). Label subgroup
comparisons descriptive; do not declare subgroup success or select release
thresholds. Bootstrap the primary and established comparisons only.

## Software checks and decision

Use synthetic fixtures for identity/count validation, missing/zero distinction,
strict cutoffs, same-day leakage, future outcomes not influencing earlier
predictions or k selection, last-five semantics, boundary clipping and immutable
artifact verification. Independently check binomial probability arithmetic and
paired date-bootstrap weighting. Simulate matching Beta(4,6) constant fighter
rates with a known 10-trial prior to check shrinkage arithmetic/recovery only
(8,000 fighters, prior attempts in {0,10,100,1000}, seed 20261103). This prior
does not select k or certify the real-data model. Save numerical bias/RMSE and
compare with raw estimates when defined; no latent-interval calibration claim.

Always report public_release=false and opponent_adjusted=false. Retain results
even if the simple references win. Predictive calibration, reliability,
opponent adjustment, versioned serving snapshots/windows and a separately
declared protected future evaluation remain later milestones. Frozen defense
dependencies and artifacts, serving data, site, portraits and registry stay
unchanged. A new run requires a new output directory; saved artifacts include
protocol/configuration/source/input hashes and cannot silently overwrite results.
