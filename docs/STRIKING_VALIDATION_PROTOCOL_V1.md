# Striking accuracy validation protocol v1

Declared November 4, 2026 before calculating the new calibration, dispersion,
repeatability or subgroup validation results. This extends an already examined
historical development study; it is not an untouched holdout or independent
preregistration. No site/source-data updates, mean retuning, opponent adjustment,
winner prediction or public release are included in this milestone.

## Input and chronology contract

Verify the original striking adapter and prototype, all recorded input/output
hashes, saved configuration and protocol. Reproduce every v1 prediction exactly
with its selected k=500, and reconstruct pre-date integer sufficient counts
independently. Preserve the original 17,708 sides through October 24 with the
exclusive October 26 cutoff. Do not use the separately imported October 31 card.
The real run must retain v1's exact 7,028 common-support development observations
and 5,279 tuning observations. Thin synthetic fixtures may exercise the code
without claiming the real-data contract has passed.

All bouts on one calendar date are predicted before any same-date updates.
The prior global mean, career and last-five counts use earlier dates. Last-five
means five recorded bouts, including unavailable and zero-attempt bouts. Retain
same-date bouts in deterministic fight-ID order; report boundary windows that
cut such a date. Missing or invalid counts never become zeros. Zero-attempt
current bouts receive predictions but are excluded from count scoring. The
estimand is own landed significant strikes conditional on the actual current
attempt count, not future opportunities, duration or outcome of the fight.

## Frozen point estimates and reference selection

Keep all six v1 means unchanged: raw career, raw last five, career Jeffreys,
last-five Jeffreys, earlier global mean and career sample adjustment (k=500).
Choose the strongest simple reference from the first five by mean conditional
binomial NLL on common support in 2012–2018 only, listed-order ties. This does
not reselect k or rewrite the v1 result. From 2019 onward compare every mean on
identical v1 common support, plus the fixed established subset (3+ prior bouts,
100+ prior attempts) and the subset where both raw rates are strictly inside
(0,1). Report mean NLL, attempt-weighted cross entropy and attempt-level Brier.
All scoring means are clipped to [1e-6,1-1e-6]. Preserve v1 sensitivity at 1e-3
and 1e-2 without reselection. The upper-boundary k=500 finding remains explicit;
no wider mean-strength grid will be tried in this study.

## Predictive distributions and tuning

Compare three different interpretations, keeping means fixed:

1. Plug-in binomial for all six means.
2. Stationary-history beta-binomial for candidate, career Jeffreys and last-five
   Jeffreys. Candidate alpha=prior landed+500*earlier global rate and
   beta=prior missed+500*(1-earlier global rate); Jeffreys adds 0.5 to the
   corresponding landed/missed counts. Preserve the mean and concentration;
   apply the same scoring clip to the mean if needed for positive parameters.
   This treats the pooled prior/k as fixed and assumes a constant fighter rate.
3. Bout-varying beta-binomial for candidate and selected simple-reference mean:
   alpha=p*c, beta=(1-p)*c. Tune each distribution's concentration c independently
   over {2,5,10,20,50,100,200,500,1000} using 2012–2018 common-support mean
   beta-binomial NLL only, tie toward smaller c. This is an explicitly new
   striking dispersion comparison. No defense dispersion parameter is copied.
   Conditional bout variation is not opponent adjustment or latent fighter skill.

Save all concentration tuning scores, selections and grid-boundary indicators.
Do not select/repair concentrations, means, calibration bands or subgroup cutoffs
using 2019+ outcomes. Use SciPy binomial/beta-binomial log-PMF, CDF and PPF.

## Calibration and score checks

On identical primary support, report predictive NLL and paired differences,
50%/90% equal-tail integer count ranges, observed coverage, mean width and actual
expected distribution mass. Discrete ranges may cover more than their nominal
level. Also use randomized PIT U=F(y-1)+V*P(Y=y), where V is bound to seed,
bout ID and fighter ID and is shared across methods. Seeds are 20261105,
20261106 and 20261107 (first is primary). Report central 50%/90% PIT coverage,
ten-bin histograms and date-cluster 95% intervals, including seed sensitivity.

Diagnostic bands are 45–55% for central 50% and 87–93% for central 90%. Overall
calibration requires 500 sides and 20 dates to be interpretable; subgroup checks
require 100 sides and 20 dates. All three PIT seeds must be in band to label a
level "within_band_all_seeds"; otherwise label "outside_band". Thin groups are
"inconclusive_thin_group", never passing. Bands and counts are engineering
diagnostics, not a public-release gate or hypothesis test. Save mean error,
attempt-weighted observed/predicted accuracy, trial-weighted mean residuals in
ten fixed predicted-probability bins, and Pearson dispersion (sum of squared
count residuals / stated count variance per side; descriptive, not a chi-square
test). Out-of-band diagnostics are retained without repair.

Bootstrap whole calendar dates 1,000 times with seed 20261104; preserve both
sides of shared bouts on the same resampled date. For primary comparisons also
report fighter-trajectory bootstrap sensitivity, using the same replicates and
seed: it preserves a fighter's observations across dates but not shared-bout
dependence. Neither one-way scheme resolves both dependence structures at once.
Require at least two distinct clusters for any interval. Report finite counts.
Intervals describe differences/coverage, not fighter skill. No multiplicity
correction or confirmatory significance claim is made for overlapping groups.

Report point comparisons and candidate bout-distribution calibration by year,
era (2019–2022 / 2023+), division, provider, prior attempts (1–99/100–499/500+),
prior bouts (0/1–2/3–5/6+), actual current attempts (1–24/25–49/50–99/100–199/200+)
and full-fight duration (<60s/60–299s/300–899s/900+s/missing-or-zero). Show all
groups, including thin ones. For sufficiently sized groups, flag a material
point regression only if candidate-minus-selected-reference binomial NLL exceeds
0.05/side and its whole-date 95% interval lies above zero. Also compare candidate
and simple-reference bout beta-binomial predictive NLL. These are distinct checks;
better dispersion must not hide a regressing mean.

Broader positive-trial coverage and cold starts are reported separately from
paired support. Calibration of the candidate bout distribution on that broader
population is secondary. No distribution comparison uses mismatched rows.

## Repeatability

For M={2,3,5,8,10} recorded bouts per half, compare each fighter's first M with
their next M; retain zero/missing bouts in the slot count. Reject a split that
shares a calendar date, and a 2M end boundary that cuts a same-date batch. Require
observed counts for every selected bout in the primary complete-count analysis,
then at least 100 total attempts in each half. Show separate attrition counts
for short careers, same-date boundaries, missing/invalid counts, zero exposure
and insufficient exposure. Report a secondary complete-count, positive-attempt
subset and stable-division slices (50+ eligible fighters), plus all slice sizes.

Save the exact fighter and bout IDs assigned to each half for auditing. Compute
pooled landed/attempted proportions in each half, Pearson and tie-aware Spearman
correlations, with 1,000 fighter-bootstrap replicates, seed 20261104. Correlation
is undefined for constant values or fewer than three fighters; report null and
finite-replicate counts. Fewer than 50 fighters or fewer than 900 defined
replicates makes the summary inconclusive. No minimum-career threshold or
Spearman–Brown extrapolation is inferred. Career selection, changing opponents,
division/time changes and noise remain confounders. This is descriptive
repeatability, not validation against real latent skill truth.

## Synthetic verification and decision

Verify stationary matching-model arithmetic using 8,000 independent fighters
with p~Beta(4,6), prior attempts sampled from {0,25,100,500}, future attempts
uniformly 1–200, seed 20261104. Report posterior bias/RMSE, 90% latent-rate
interval coverage, predictive count coverage and randomized-PIT coverage by
prior exposure. Latent intervals are tested against simulated p, not individual
fight outcomes. Synthetic diagnostic bands are 87–93% for each nominal 90%
coverage, |overall mean bias|<0.01. Separately simulate 8,000 beta-binomial bouts
with p uniform on [.2,.8], concentration 20, attempts 1–200 and seed 20261108;
verify grid concentration recovery and PIT coverage. These numerical fixtures
cannot prove that MMA data follow either model.

Test leakage, immutable-hash/config/protocol checks, exact v1 reproduction,
independent sufficient-count reconstruction, tuning separation, score/variance
arithmetic, PMF enumeration, discrete-range mass, PIT ordering/seeds, whole-date
and whole-fighter bootstrap weighting, missingness/zero handling, repeatability
boundaries/attrition and synthetic end-to-end artifacts before the real run.

Always save public_release=false and opponent_adjusted=false. Report separately
point-score evidence, dispersion evidence, overall and subgroup calibration,
repeatability, synthetic checks and thin groups. No universal repeatability
threshold, release approval or future-validation pass can emerge from this run.
The documented decision must retain a research reference, specify a separate
revision study, or retain raw site statistics based on the results. Full release
still needs protected future evidence, reliability/skill-interval requirements,
opponent-adjustment evaluation and versioned serving snapshots/windows.

Preserve all existing source/artifacts, both serving databases, the website,
portrait collection, registry and frozen defense experiment. All new outputs
are immutable, separately versioned, bound to input/config/protocol/source and
runtime hashes, and accompanied by a saved report and static diagnostic figure.

Implementation references: [SciPy binomial](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.binom.html),
[beta-binomial](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.betabinom.html),
[rank correlation](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.spearmanr.html).
