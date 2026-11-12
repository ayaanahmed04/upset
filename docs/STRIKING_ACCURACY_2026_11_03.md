# Significant-striking dataset and accuracy prototype — November 3, 2026

**First offline milestone completed.** The adapter and chronological accuracy
prototype are implemented and have been run on the retained research snapshot.
The website continues to display descriptive raw statistics. No adjusted skill
rating or interval has been released.

## Dataset

The adapter contains 17,708 paired fighter-side observations from 8,854 bouts
through October 24, using the exclusive October 26 cutoff. It records 1,463,253
attempts and 656,433 landed significant strikes. All 17,708 sides have positive
shared duration; 17,610 have positive attempts and 98 have true zero attempts.
The 758 sides from fights under one minute remain included and flagged.
There are 790 calendar-date clusters and 522 sides with an unclassified division.

Own counts, opposing counts, full-fight duration, accuracy, descriptive landed
strikes per minute, permanent IDs, provider/event identities and source hashes
are retained. Missing or invalid counts remain distinct from true zero exposure.
No component attempts, joint strike cells or positional clocks were invented.

The serving database's actual reviewed registry is
`data/processed/cito_current_2026_10_25_reviewed_v1/fighter_registry.json`.
The top-level registry lacks many reviewed Cito links, so it cannot substitute
for the serving-bound registry. The adapter requires the registry bound in the
serving manifest. Source data and all frozen defense dependencies are unchanged.

## Declared development comparison

[Protocol v1](STRIKING_ACCURACY_PROTOCOL_V1.md) was saved before calculating
these results. All bouts on a calendar date are predicted before any observations
on that date update history. Last-five counts five recorded bouts, including
missing and zero-attempt bouts. The prior global rate also uses earlier dates.

The striking-specific grid was k={1,5,20,100,500}. On 5,279 common-support sides
in 2012–2018, mean binomial NLL declined from 5.6633 at k=1 to 4.7348 at k=500.
**k=500 was selected, at the upper boundary of the declared grid.** It was not
expanded or retuned after examining the development comparison. This result
does not establish an optimal population variance or an opponent-adjusted skill.

From 2019 onward, primary common support contains 7,028 sides, 672,393 attempts
and 333 dates. Every method below is evaluated on that same population. Lower
scores are better.

| Estimate | Binomial NLL / side | Attempt-weighted cross entropy | Attempt-level Brier |
| --- | ---: | ---: | ---: |
| Raw career | 6.14335 | 0.70537 | 0.25114 |
| Raw last five | 6.23140 | 0.70629 | 0.25158 |
| Career Jeffreys | 5.19698 | 0.69547 | 0.25078 |
| Last-five Jeffreys | 5.28410 | 0.69639 | 0.25122 |
| Earlier global mean | 4.97534 | 0.69316 | 0.25000 |
| Career shrunk toward earlier global mean, k=500 | 4.61724 | 0.68942 | 0.24814 |

Candidate-minus-reference NLL differences and 95% date-cluster bootstrap ranges:

- Raw career: −1.5261 [−2.2808, −0.9522].
- Raw last five: −1.6142 [−2.3735, −1.0506].
- Career Jeffreys: −0.5797 [−0.6873, −0.4817].
- Last-five Jeffreys: −0.6669 [−0.7772, −0.5599].
- Earlier global mean: −0.3581 [−0.4064, −0.3078].

These intervals describe paired score differences, not fighter skill. Repeated
fighters across dates remain a dependence limitation.

The established subset (3+ prior bouts and 100+ prior attempts) contains 5,370
sides. Candidate NLL is 4.63331, compared with raw career 4.79452, career Jeffreys
4.79223 and population-only 5.07328. This narrower difference shows why the
large overall improvement should not be generalized to every experienced fighter.

There are 7,860 development side rows: 7,845 positive-trial rows and 15 zero-trial
rows. Primary support excludes 817 positive-trial rows. There are 817 rows with
no prior recorded bouts and 820 with no prior attempts; these counts are reported
separately rather than quietly dropping cold starts. No development last-five
window split a same-day boundary in this snapshot.

## Checks, interpretation and next milestone

Synthetic matching-prior checks reproduce the intended shrinkage arithmetic;
shrinkage reduced RMSE versus raw proportions at each nonzero synthetic sample
size. This verifies arithmetic under a known Beta(4,6) generator, not real MMA
assumptions. Numeric binomial scores were checked against direct probability
calculations, and bootstrap weighting against explicit whole-date resampling.

Twenty-eight new striking tests cover identity/count validation, cutoffs,
missing/zero handling, small-sample arithmetic, same-date/future leakage, last-five
semantics, tuning separation, immutable artifacts and tampering. Together with
the card-import, viewer, refresh, archive-normalization and frozen-defense tests,
88 relevant tests passed; the viewer HTTP test required localhost socket access.
Targeted Ruff checks, the existing JavaScript UI checks and Git whitespace checks
passed. The frozen defense seed and every frozen dependency hash remain valid.

These are already inspected historical development years. Conditional binomial
scores do not establish within-bout independence, a calibrated count law, a
future opportunity forecast, latent skill reliability or public-release validity.
The new October 31 serving card is deliberately outside this fixed research run.

**Next:** declare a separate striking validation protocol covering predictive
dispersion/calibration, repeatability and subgroup behavior, including whether
the upper-grid-boundary smoothing result warrants a new development experiment.
Opponent adjustment and serving snapshots/windows follow separately. Preserve
this v1 result without tuning it against later observations.

## Reproduce

```bash
cd /Users/ayaanahmed/Projects/upset
.venv/bin/python -m pytest -q tests/test_striking_skill.py
.venv/bin/python -m upset.skill.striking_adapter \
  --database data/processed/research_2026_10_25_v1/upset.sqlite \
  --registry data/processed/cito_current_2026_10_25_reviewed_v1/fighter_registry.json \
  --before 2026-10-26 \
  --output data/processed/striking_adapter_2026_11_03_recheck
.venv/bin/python -m upset.skill.striking_accuracy \
  --adapter data/processed/striking_adapter_2026_11_03_recheck \
  --output data/processed/striking_accuracy_2026_11_03_recheck
```

Outputs are immutable; choose fresh names for another run. Original artifacts:

- `data/processed/striking_adapter_2026_11_03_v1/{manifest.json,sides.jsonl}`.
- `data/processed/striking_accuracy_2026_11_03_v1/{report.json,predictions.jsonl,config.json,protocol.md}`.
- `data/processed/striking_accuracy_start_2026_11_03.json` preservation baseline.
