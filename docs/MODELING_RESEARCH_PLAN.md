# Modeling research plan — September 24, 2026

**Implementation follow-up:** The first chronological Elo and bounded
boosted-tree experiment is now implemented alongside the existing models.
See `ELO_EXPERIMENT.md` for fixed settings, source audit, saved-reference
checks and the first Mac results at `ddba4ab`. Defense + Elo reached 57.78%
(six more correct than full defense); its accuracy interval includes zero.
Boosted defense + Elo had the best pooled probability losses in that study
but lower accuracy than full defense. Diagnostic review found material
fighter-order dependence in the fitted classifiers; the full manifest and
Mac Ruff/288-test result are confirmed. No model is promoted.

`RECENT_FORM_EXPERIMENT.md` now specifies an implemented, separate follow-up:
mirrored training and symmetric inference, 365-day weighted performance,
earlier-population shrinkage, and actual control margin. Six fixed new
candidates retain the original six predictions as references. The Mac passed
Ruff and 313 tests; 17,102 histories were independently audited. The best
pooled candidate improved log loss to 0.666020 but made 57.67% correct picks,
without an accuracy gain over its matching comparator. The uploaded report
and row-level predictions matched their hashes; coarse-bin calibration is
worse than the comparator's. `EXAMINED_LATER_EVALUATION.md` freezes the next
comparison on the already examined later dates; it cannot be a fresh holdout.
The Mac completed that comparison: on 1,260 decisive fights, recent + Elo
scored 784 (62.22%) versus symmetric defense + Elo's 767 (60.87%), with lower
log loss (0.649515 versus 0.659788). The paired accuracy interval includes
zero, and the small 2026 and one-fighter-history slices favor the comparator.
No model was promoted; fresh evidence requires externally dated pre-event
forecasts on data newer than the historical snapshot.

**September 25 follow-up:** `PAIRED_CONTEXT_EXPERIMENT.md` specifies the next
implemented comparison: one fixed symmetric tree adds each fighter's own
pre-fight values to the existing difference/exposure inputs (102 columns
versus 36), with unchanged settings. All 12 saved reference variants are
preserved; the directly matched old tree must reproduce its saved outputs.
Ruff and 334 tests plus 16 subtests pass in the assistant environment. The
Mac passed Ruff and all 334 tests, then completed the run at `26334e8`.
The new tree's 1,062/1,857 correct (57.19%) and log loss 0.670842 do not
improve on the old tree's 1,070/0.670808 or logistic's 1,071/0.666020.
The paired intervals include zero. All 611 uploaded metric sets, bins,
symmetry and both paired intervals were reproduced from the saved rows;
the 12 earlier reference series are unchanged. Retain recent + Elo logistic
as the research reference and specify opponent-adjusted performance next.
Only the existing development windows were scored; the later 62.22% result
is a separate cohort. No model was promoted. No paid data or monotonic
constraints were added. That document also qualifies the external review's
public-model comparisons, claimed 75% ceiling, dependence between folds and
historical-odds costs. A market benchmark remains important separate work.

**Opponent-adjusted follow-up completed:** `OPPONENT_ADJUSTED_EXPERIMENT.md`
records a single fixed comparison adding six residual/exposure features to
the saved recent + Elo logistic model. The Mac passed Ruff and all 346 tests,
audited 17,102 adjusted rows and matched the reference refit exactly. The
candidate gained 23 picks (1,094 versus 1,071/1,857; date-bootstrap
accuracy interval [+0.11, +2.48] percentage points), but pooled log loss
rose 0.666020 to 0.666722 and Brier rose 0.236867 to 0.237185. The paired
loss interval spans zero and the one-history slice deteriorates. Uploaded
hashes, old prediction series, 611 metric sets, interval and adjusted-history
arithmetic were independently checked. This is mixed exploratory evidence,
not a demonstrated probability gain: **no promotion**. Prioritize current
data, replay and timestamped prospective forecasts for fresh evidence.

**Prospective foundation:** `FROZEN_PROSPECTIVE_MODEL.md` implements the
accepted logistic recipe as a replay-verified numeric artifact and adds a
provider-neutral completed-fight intake contract after the March snapshot.
The Mac froze 8,400 decisive fights after passing Ruff and 351 tests;
the artifact hash and full result are documented. This does not claim a new
score. `ASOF_PREFIGHT_FEATURES.md` adds a strictly dated 36-column builder;
its full-data historical audit is pending. To improve the model, first measure coverage
and reconcile the missing current fights/stats, then derive and audit strictly
dated features. Independently specify a genuinely different available-signal
family (for example fight-date age/reach with missingness and class context),
and compare against the saved reference on identical bouts. A timestamped
market-only comparator would show how much signal is still missing from
historical stats. Report both proper probability losses and accuracy on
prospectively locked forecasts; repeated historical fold exploration cannot
establish a 75% all-fights result. Cito purchase is a source-coverage
decision, not a prerequisite for freezing or replaying the model.

The historical review below describes the state before these implementations.
Physical features and broader Cito acquisition remain proposed.

## Status and purpose

This plan records the modeling review requested after PR #13. It is a research
plan, not an implementation or a new performance result. Ayaan still wants
to pursue approximately 75% pre-event winner accuracy. No paid Cito purchase
or new model experiment occurred during this review.

The implementation reviewed was `3d2af42607bc1c7bc28533e7f2f8d0f861320c58`.
PR #13 merged the prospective archive after the Mac passed Ruff and all
260 tests on `6246578`. The archive preserves supplied forecasts; it does
not generate a live prediction. Work is in advanced analytics and early
modeling, with current-data ingestion and the public product still pending.

## Evidence we have

The original examined 2023-08-26–2026-03-07 test remains 655/1,260 correct
(51.98%). It is a different cohort from the following development comparisons:

| Variant | Correct / 1,857 | Accuracy | Log loss |
| --- | ---: | ---: | ---: |
| Nine-feature logistic baseline | 985 | 53.04% | 0.69062 |
| Baseline plus eight defensive features | 1,067 | 57.46% | 0.68159 |
| Defense without recorded-knockdown features | 1,077 | 58.00% | 0.68235 |
| Baseline plus four outcome/activity features | 1,055 | 56.81% | 0.68601 |
| Defense plus outcome/activity features | 1,053 | 56.70% | 0.68083 |

The 58.00% variant was selected from exploratory comparisons; it is not an
independent test or the promoted model. Full defense improved accuracy and
log loss in each of four folds versus the weak baseline. Adding outcomes to
defense produced mixed results and lower pooled accuracy. All these models
use logistic regression and existing historical data. Cito rounds did not
cause these gains. See `EVALUATION_CONTRACT.md` for dates, audits, uncertainty,
per-fold counts and source hashes.

## Implemented versus proposed

| Area | Implemented | Next useful work |
| --- | --- | --- |
| Recent form | Prior UFC win fraction, previous-365-day wins/losses, layoff days; performance rates aggregate all prior UFC history | Last-three-bout and exponentially weighted performance, with exposure and small-sample shrinkage |
| Opponent quality | Opponents are identified, but strength is not modeled | Chronological Elo as a feature and standalone comparison; performance adjustment is a separate later step |
| Matchups | Nine original A-minus-B features; defense/outcome differences | Offense against the particular opponent's defense, quantitative style profiles, symmetric predictions |
| Physical/context | Historical DOB, height, reach, stance and bout class available to varying degrees; layoff modeled | Age at fight date, both ages plus difference, height/reach, class interactions; timestamped notice/travel data later |
| Finish history | Exact KO/TKO and submission loss counts | Exposure-adjusted finish wins/losses; a separately evaluated method model later |
| Existing unused stats | Head/body/leg and distance/clinch/ground landed totals and actual control seconds are stored | Dated style shares, net control and striking metrics; respect missing exposure |
| Models | Median imputation, missing indicators, scaling, logistic regression | A bounded boosted-tree comparison on identical features and bouts |
| Odds | No imported market data or market benchmark | Timestamped odds, market-only baseline, separate market-assisted candidate |
| Evaluation | Whole-date chronological folds, log loss, Brier, AUC, accuracy, saved predictions/hashes; one date bootstrap | Reliability plots, subgroup diagnostics, bounded tuning and future evidence |
| Prospective evidence | Supplied-forecast archive with validation and hashes | Current data, reviewed links, trained artifact, replay, external timestamp and separate scoring |

`control_observed_fraction` is a coverage measure, not the amount of control
a fighter achieved. Elo captures outcome-based opponent strength; adding an
Elo column does not automatically adjust every strike/takedown rate. A raw
profile fetched today is not a historical pre-fight career-stat snapshot.

## Recommended sequence

### 1. Opponent strength and a small model comparison

This is the recommended next implementation milestone; it needs no paid data.

- Add a separately versioned pre-fight Elo export using permanent IDs.
  Start with rating 1500, logistic scale 400 and K=32 as fixed development
  choices, not claims of MMA-optimal settings. Snapshot every fighter on a
  date before updating any result from that date. Skip combined Draw/NC
  updates because draws cannot be distinguished from no contests.
- Preserve a global per-fighter rating across division changes for the first
  version; record that disconnected fighter populations and debutants have
  weakly anchored ratings. Do not use current rankings or future outcomes.
- Retain opponent pre-bout rating, own rating, prior appearances and the
  direct Elo probability as audit evidence. Independently replay histories.
- Compare Elo alone, the existing nine-feature and 17-feature references,
  and 17 features plus Elo difference on the same frozen development bouts.
- Include one fixed, regularized `HistGradientBoostingClassifier` reference on
  the 17 inputs and on 17 plus Elo. Predeclare settings before scoring; use
  no outer-fold-driven search. Disable automatic random validation for early
  stopping, or use an explicitly earlier inner period.
- Diagnose performance by history size and missingness; audit A/B swap
  behavior. Preserve the original models' probabilities and schemas.

Glicko-2 is a later candidate. Its rating uncertainty is attractive, but
Glickman's design uses rating periods and assumes more frequent play than
typical UFC careers. It is not automatically superior. [S4]

### 2. Recent performance, reliability and available physical context

- Build per-bout performance histories from identified fight stats and paired
  opponents. Candidate windows: all prior history, last three bouts, and
  calendar decay with a predeclared half-life (initial proposal: 365 days).
- Compute weighted counts divided by weighted exposure. For accuracy use
  attempted strikes; for pace use observed seconds. Avoid averaging extreme
  per-bout percentages from tiny denominators.
- Shrink sparse rates toward an earlier population reference, using prior
  attempts/minutes as evidence; retain missingness and both fighters'
  exposure. Define priors without future data.
- Add actual control share and target/position landed shares from existing
  records; do not call them target-specific accuracy without attempts.
- Join DOB to event date for age, and audit profile measurements before
  physical features. Use the bout's class rather than today's profile weight.
- Keep small predeclared feature families and compare each against fixed
  references. Recent finish rates and time since explicit finish losses can
  be investigated without changing the binary prediction target.

### 3. Cito acquisition pilot and current-data repair

A one-month Pro research purchase is reasonable if Ayaan chooses it and the
account provides the promised old-bout detail. Purchase is not authorized by
this plan. Existing free-data experiments can proceed first.

Current provider pages list Pro at $59/month, 250,000 calls/month and
100/minute; the pricing table lists a 25,000/day cap and **90 days** of
history, while the terms say **full archive** for Pro and above. Confirm the
actual account entitlement rather than assuming either page settles it.
[S1, S2]

The previous handoff and project status record Aidan's September 16 email:
one paid month can acquire historical UFC rounds for local retention.
Preserve that evidence; do not reopen retention as an unanswered question.
The original email was not reread during this review.

Recommended pilot: 20–30 bouts across several years, divisions, 3/5-round
schedules, decisions and early finishes. Discover provider IDs, review both
fighter links and bout identity, record availability, and reconcile round
sums with totals and selected independent source records. Audit actual round
duration and missing-field semantics. A recent successful response does not
establish the whole archive's coverage.

After pilot acceptance, inventory the desired historical cohort, estimate
requests, and use resumable bounded collection with checksums and a coverage
report. Repair completed-fight/stat coverage after 2026-03-07 before live
forecasts. Target/position attempts, total strikes, reversals and round
trajectories are possible additions; none has a measured incremental benefit
yet. Do not count multiple rounds as independent winner-label samples.

Cito advertises odds endpoints, but the reviewed documentation does not
establish timestamped historical closing-odds coverage. Test this separately.
The Odds API advertises paid historical MMA odds from June 2020; it would not
cover the 2019 development fold from that archive alone. [S3, S5, S6]

### 4. Market comparison and prospective release

Maintain separate core and market-assisted models. Pair prices from the same
book/time and remove the two-way margin before comparing probabilities.
Use odds observed by the actual forecast cutoff. A later closing price can
be an evaluation reference but cannot be a feature for a day-before forecast.

Release a trained, versioned model only after the input pipeline is ready.
Verify replayed probabilities, archive every eligible prediction before the
declared cutoff, externally anchor the hashes, and score later outcomes in a
separate file. Extend the archive's feature-set whitelist deliberately when a
new model is approved.

## Evaluation and interpretation rules

- Freeze all cohort, cutoff, exclusion and fallback rules before scoring.
  Keep low-history fighters in the primary all-eligible score; report
  restricted subsets separately with coverage.
- The four development folds and original test were already inspected.
  Continue using them for research, with an experiment ledger; do not relabel
  them as untouched. Later historical data are retrospective unless real
  pre-event evidence was captured.
- Log loss remains the primary probability-selection measure; retain accuracy
  as an explicit co-reported target. Predeclare any acceptable tradeoff.
  Small changes in log loss do not establish better calibration by themselves.
  Add reliability plots with bin counts. [S7]
- Tune, impute, scale, choose features and calibrate only inside earlier
  training periods. Avoid shuffled CV and random early-stopping holdouts.
- Report paired comparisons on identical bouts, each fold, pooled counts,
  exclusions, uncertainty, missingness and performance by history size/class.
  Event/date bootstrap intervals do not eliminate repeated-fighter dependence
  or model-selection bias.
- Audit prediction symmetry: swapping A/B should complement probabilities.
  Differences alone do not guarantee this with an intercept or imputation.
- Preserve raw source disagreements and missing fields. Do not choose an
  arbitrary 2013 cutoff without auditing actual coverage.
- Treat claims such as “grapplers age better,” universal home advantage or
  short-notice penalties as hypotheses. Do not hardcode folklore.
- Method prediction is a separate task. A six-way winner/method target needs
  reviewed labels and its own evaluation; it does not guarantee better winner
  accuracy.
- A 75% accuracy target has no established feasibility estimate here.
  Better data can improve finish-risk estimates without making individual
  finishes certain. The existing 57–58% result is also not a proven ceiling.
- Market comparison matters for predicting competitively. Failure to beat
  closing prices does not erase the project's analytics or engineering value;
  higher accuracy alone would not establish a profitable betting strategy.

## Sources checked on September 24, 2026

- S1: [Cito pricing](https://citoapi.com/pricing/)
- S2: [Cito terms](https://citoapi.com/terms/), historical window and service-use statements
- S3: [Cito UFC documentation](https://citoapi.com/docs/api/ufc/)
- S4: [Glickman's Glicko-2 specification](https://glicko.net/glicko/glicko2.pdf)
- S5: [Cito odds documentation article](https://citoapi.com/blog/ufc-odds-api/)
- S6: [The Odds API MMA coverage](https://the-odds-api.com/sports/mma-ufc-odds.html)
- S7: [scikit-learn calibration](https://scikit-learn.org/stable/modules/calibration.html)
- S8: [scikit-learn histogram gradient boosting](https://scikit-learn.org/stable/modules/generated/sklearn.ensemble.HistGradientBoostingClassifier.html)

Modeling priorities, pilot sizes and parameter choices above are recommendations
from this review. The sources describe capabilities and principles; they do
not establish a predicted accuracy gain for UPSET.
