# Experimental UPSET overall rating protocol v1

Declared November 4, 2026 before fitting the overall weights, replaying the new
features on real bouts, calculating development scores, or choosing the display
curve. This is a separate local experimental index, not a validated latent
skill, opponent-effect release, calibrated win probability, or public launch.
Earlier striking/defense studies, failures, gates and prospective freeze remain
unaltered. The user authorized completing the rating system; local display is
permitted only with the experimental label and the checks below.

## Inputs and chronology

Read the reviewed serving SQLite database through exclusive November 4, 2026.
Keep accepted permanent identities, both sides, current reviewed outcomes,
draw/NC separation, missing measurements and database/manifest hashes. Current
amendments are hindsight, not reconstructed publication-time knowledge. Do not
acquire new data or consume previously excluded bouts.

Use whole calendar-date batches. Predict all bouts on a date from earlier
states, then update all fighters from frozen earlier opponent baselines and
emit one post-date state per fighter. At page cutoff d only states with event
date < d are available. A rating stays latched between that fighter's bouts;
other fighters' results, age, calendar time and inactivity do not move it.
Same-day multiple bouts are a single update batch. No request-time fitting.

## Fixed feature construction

Earlier bouts receive relative weight 0.85 per later recorded bout. Use
denominator-aware sufficient counts, with fixed starting priors: 45 minutes
for rate features, 500 significant-strike attempts, 50 takedown attempts,
20 submission attempts, and 5 bouts for result rates. These are declared
research choices, not validated reliability thresholds. Adjust each observed
feature against the opponent's corresponding earlier shrunken allowed/attack
rate; favor stronger-than-expected performance. Opponent baselines shrink to
the earlier division pool, then earlier global pool. First-date empty pools
use explicit neutral defaults (probability/control 0.5, differentials and
nonnegative event rates 0). An own adjusted residual shrinks toward zero.

Components and fixed within-component weights:

| Part | Features, oriented higher-is-better | Weights |
| --- | --- | --- |
| Striking | significant-strike difference/min, accuracy, defense, knockdowns/15min, negative knockdowns received/15min, negative KO losses/bout | .30,.15,.20,.20,.10,.05 |
| Wrestling | takedowns/15min, takedown accuracy, defense, control share | .25,.20,.35,.20 |
| Grappling | submission attempts/15min, submission wins/bout, negative submission losses/opposing attempts, ground-strike difference/min | .30,.25,.20,.25 |

No reversals or unavailable round-level traits are fabricated. Missing control
stays missing. Zero attempts supply no accuracy likelihood. Submission loss
conversion is unavailable when attempts are zero or recorded losses exceed
attempts. Reweight only observed features within a component; an entirely
unavailable component stays unavailable. Do not silently equate missing to zero.

Standardize residuals using earlier peer fighter states in the latest division
(minimum 20); otherwise use earlier global peers, then the fixed floor alone.
Clip each standardized residual to [-3,3]. Standard-deviation floors in feature
order above: striking [1,.10,.10,.5,.5,.10], wrestling [1,.10,.10,.15], grappling
[.5,.10,.10,.5], in each feature's stated units. Weighted z -> standard-normal
CDF × 100 yields a raw component index, not a posterior probability. Résumé
uses independent Elo (initial1500, K32, scale400, decisive results only), then
normal-CDF((Elo−1500)/200)×100. No finish/decision multipliers are introduced.

For displayable component units use 60 + .39×raw component. All calculations
retain full precision; displayed component decimals are rounded. Cold starts
have neutral modeling components of 50 but never a displayed debut score.

## Overall selection and probability assessment

Skills blend = .50 strongest + .30 second + .20 third, using the three
full-precision component values. Candidate résumé weights are [.25,.50,.75];
overall raw combined = w×résumé + (1−w)×skills. Compare résumé-only separately;
it cannot silently replace the requested four-part model. No protected earlier
opponent-model coefficients are reused.

For each candidate fit one positive logistic slope (no intercept; symmetric
fight ordering) on decisive bouts in 2012–2015 with earlier recorded history
and all components available for both fighters. Bound slope to [.001,5]. Select
lowest per-bout logistic NLL in 2016–2018; deterministic ties favor listed order.
Refit that selected candidate's slope on 2012–2018 only. Fit the résumé-only
reference the same way. The 2019–October24,2026 block is already inspected
development evidence, not a pristine holdout. October31 may update the serving
snapshot but is not used to select or score this study.

Report matched support, NLL, Brier, ordering accuracy, ties/abstentions, a .5
baseline and résumé-only reference; paired whole-date bootstrap differences
(1000, seed20261104) and fighter-trajectory sensitivity where interpretable.
Show performance by year, division and prior experience. Report an honest
higher-*displayed*-rating track record on earlier available displayed scores,
excluding ties, debuts and unavailable ratings; distinguish it from the raw
combined probability assessment. Never copy the PDF's illustrative 57–58% claim.

## Frozen display curve and protective rules

Freeze the empirical reference using eligible post-date combined scores
strictly before January1,2019. This uses historical UFC moments through2018,
not today's whole roster, and never uses the development outcomes to choose
the curve. Midrank empirical percentile maps through fixed anchors:
(0,60),(.10,69),(.50,77),(.80,84),(.95,89),(.97,94),(.995,98),(.9999,99),(1,99).
Interpolate and round half-up to an integer. The curve is a presentation layer;
winner-model features remain raw combined, never the 60–99 grade.

Fewer than five recorded UFC bouts caps the displayed score at88. Fewer than
four marks Provisional. From the second displayed post-date state, cap each
date-batch display change to ±5; store unclipped curve score and both protective
adjustments. These are explicit product guardrails, not mathematical results
of the underlying model. Peak/history use final displayed scores. Unavailable
components abstain rather than inventing an overall. Pre-2019 grades are
retrospective applications of the frozen2018 model/curve; predictive evaluation
begins2019 and does not claim the older grades were available at that time.

## Local experimental serving gate and limitations

Must pass strict chronology/future invariance, same-day handling, correct Elo
direction, missingness, finite values, no rating before first bout, invariant
idle/window values, correct caps/changes/peaks, model/database/hash binding and
request-time lookup-only tests. Must have ≥500 matched development bouts, a
finite positive slope and mean development NLL below ln(2). Record whether the
composite beats résumé-only; a failure there remains visible and bars claims
of added predictive value, even if the modest experimental-index gate passes.
No dataset-specific hero-score tuning or post-result threshold changes.

A gate pass permits the user's requested local numerical prototype labelled
Experimental v1, with explicit method/coverage, résumé comparison, development
track record and limitations. It does not establish validated individual skill,
calibrated intervals, fresh future performance, causal opponent effects, or
public release. If the gate fails, retain all results and keep scores off.

Save source/config/protocol/input hashes, pre-date features, dated ratings.jsonl,
fitted choices/reference curve, full development records, comparisons and
decision in a new immutable folder. Independently check formulas and source
counts. Preserve all prior studies, frozen defense and source database. New
database versions require separately rebuilt, tested bound snapshots.
