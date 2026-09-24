# Chronological opponent-strength experiment (v1)

Implementation and first Mac result: September 24, 2026. Ayaan ran the full
historical comparison at `ddba4abef112737a23967bf6adef8d6fec7cf413` and supplied
the terminal output. Defense plus Elo reached 1,073/1,857 correct (57.78%),
six more than full defense; the paired accuracy interval includes zero.
Boosting plus Elo gave the lowest pooled log loss but lower accuracy than
full defense. No model is promoted. The 75% goal remains a research target.

Assistant-environment validation: 288 pytest tests and 16 subtests passed;
Ruff clean. Python 3.12.14, NumPy 2.3.5 and scikit-learn 1.8.0 were used.
The original 260 tests also passed before adding the new tests. Synthetic
fixture metrics are not UFC performance estimates.

The Mac output confirms the real-data export, full rating replay and model
comparison. A separate Mac Ruff/pytest summary and the complete manifest
have not yet been supplied in this session. Do not describe the assistant's
288-test result as a confirmed Mac test run.

## Question and fixed comparison

Does a dated record of opponent strength improve the existing inputs? Does
one fixed nonlinear model help on those same features? Both questions use
the existing 2019, 2021, 2022 and partial-2023 development folds. Each model
scores the same decisive bouts; Draw/NC rows retain explicit exclusions and
null predictions. Debutants are included. The 2023-08-26+ examined test is
outside this study.

| Variant | Inputs | Procedure |
| --- | --- | --- |
| `baseline` | Original nine differences | Preserved logistic reference |
| `all_defense` | Original nine plus eight defensive differences | Preserved logistic reference |
| `elo_only` | Two pre-date ratings | Direct Elo probability, no fitted classifier |
| `defense_plus_elo` | 17 defensive/reference inputs plus Elo difference | Same logistic procedure |
| `boosted_defense` | Same 17 inputs | Fixed histogram gradient boosting |
| `boosted_defense_plus_elo` | Same 17 inputs plus Elo difference | Identical boosting settings |

The logistic variants fit median imputation, missing indicators, standard
scaling and `LogisticRegression(max_iter=1000, solver="lbfgs")` using each
fold's earlier training rows. Boosting receives the numerical differences
with native missing values, without the logistic imputer/scaler. Its
histogram binning also fits only on the earlier training rows.

Fixed boosting choices, declared before full-data scoring: learning rate
0.05, 150 iterations, maximum seven leaves and depth three, minimum 30 rows
per leaf, L2 regularization 5, 255 bins, no categorical inputs, random state
20260924, and **early stopping disabled**. No shuffled validation, calibration,
mirrored training, search grid or tuning is used. The manifest records all
resolved estimator parameters and runtime versions. This compares complete
model procedures; the two families handle missingness differently.

## Elo definition and source limits

Every permanent UPSET fighter identity starts at 1500. The probability of
fighter A beating B is `1 / (1 + 10 ** ((rating_B - rating_A) / 400))`.
After a decisive bout, A's change is `32 * (result_A - probability_A)` and B
receives its negative. A win is 1 and a loss is 0. A surprise win produces a
larger increase than an expected win.

Every bout on a calendar date uses the ratings and counts from **before
that entire date**. Daily changes are calculated from those snapshots and
then summed. This handles early same-day tournaments without inventing bout
order. Combined Draw/NC results add appearances but no rating update; the
source cannot distinguish draws from no contests. The rating carries across
division changes. No method, margin, inactivity decay, current ranking or
future outcome affects this version.

Ratings use observed UFC results only. Early careers are truncated; debutants
have no measured prior UFC strength, and disconnected fighter populations
are weakly comparable. Initial 1500 is a common starting assumption, not a
claim that every debutant is equally skilled. Elo is one strength feature;
it does not adjust the historical striking or grappling rates themselves.
Later corrections in the downloaded results remain a source limitation.

`prefight/rating_history_v1.jsonl` stores one row per fighter per bout:
source bout ID, event date, own permanent ID, opponent ID, prior appearances,
prior decisive appearances, own rating, opponent pre-date rating, and direct
Elo probability. No UUIDs or existing feature schemas are regenerated.

The independent audit replays a separate per-fighter ledger from source
fights and recomputes **every** saved count, rating and probability. It does
not call the exporter's accumulator or expectation helper. Rating comparisons
allow absolute floating-point error of 1e-9; probability error allows 1e-12.
Same-day and future-result isolation are separately exercised by tests.

## Preserved evidence and interpretation

The model command requires the existing `defense_ablation_v1` prediction
file and manifest. Its matchup, defensive-history and registry hashes must
match this run. The command regenerates references, verifies identity,
fold/date/target/exclusion agreement and probability agreement within 1e-12,
then copies the **exact saved probability values** into the new comparison.
A mismatch stops the run; do not overwrite the reference to make it pass.
Check input provenance and library versions first.

The experiment also audits matchup dates, participants and labels against
identified source fights, and cross-checks prior appearance counts across
ratings, original matchups and defensive rows. Input hashes are checked again
after computation. Each new experiment directory is staged before publication;
an existing output directory is rejected. The rating export can be repeated
only if its bytes agree with an existing output. Use a new output path for
intentional changes. Original datasets and experiment outputs remain inputs.

The manifest saves pooled/per-fold accuracy, correct counts, AUC, log loss,
Brier score and five predeclared paired comparisons: each new candidate
against full defense, plus boosted defense with Elo against boosted defense.
Date-cluster bootstrap intervals use the existing 1,000-replicate procedure.
These intervals do not remove repeated-fighter dependence or selection bias
from previously examined folds.

Log loss is the primary probability measure. We will call an improvement
on both objectives only when pooled log loss decreases **and pooled accuracy
does not decrease** relative to the named reference; fold consistency and
paired uncertainty must also be examined. A lower-accuracy result can be
reported as a probability-score gain but not an accuracy gain. No candidate
is automatically promoted, and none of these development scores establishes
75% future accuracy.

Diagnostics retain every eligible bout while reporting history (neither,
one, or both fighters with prior UFC bouts), low experience (either below
three prior appearances), missingness in the 17 inputs, and weight class.
Small subgroups are descriptive. Fixed probability deciles save bin counts,
mean probabilities and observed A-win fractions for later reliability plots;
no calibration transform is fitted. A lower log loss alone is not evidence
that calibration improved.

For each model, the same fitted procedure also receives negated feature
differences to measure `abs(p(A,B) + p(B,A) - 1)`. This is a diagnostic, not a
change to predictions. Elo should complement within floating-point tolerance;
the logistic/tree procedures need not. Exact 0.5 ties pick UUID-ordered A,
following the preserved references.

## First Mac result

Evidence is Ayaan's pasted terminal output from the implementation commit
above. All 17,102 rating rows were checked, all numeric fields independently
recomputed, and the comparison reported a match. It retained 1,857 decisive
bouts, excluded 35 combined Draw/NC rows, and preserved the saved baseline
and full-defense probabilities. The new manifest was saved successfully.
Input-hash, source-label and reference-refit gates therefore completed;
the exact new file hashes and environment values still need the manifest.

Metrics below have the precision printed by the CLI; they are not fabricated
full-precision values. All six variants use the identical development cohort.

| Variant | Correct / 1,857 | Accuracy | Log loss | Brier |
| --- | ---: | ---: | ---: | ---: |
| Baseline | 985 | 53.04% | 0.690624 | 0.248392 |
| Full defense | 1,067 | 57.46% | 0.681592 | 0.243498 |
| Elo alone | 1,006 | 54.17% | 0.687688 | 0.247291 |
| Defense + Elo | 1,073 | 57.78% | 0.677938 | 0.241999 |
| Boosted defense | 1,049 | 56.49% | 0.675734 | 0.241560 |
| Boosted defense + Elo | 1,060 | 57.08% | 0.674022 | 0.240889 |

Correct counts by fold:

| Variant | 2019 / 506 | 2021 / 497 | 2022 / 506 | 2023 partial / 348 |
| --- | ---: | ---: | ---: | ---: |
| Baseline | 272 | 269 | 264 | 180 |
| Full defense | 297 | 289 | 274 | 207 |
| Elo alone | 256 | 279 | 289 | 182 |
| Defense + Elo | 285 | 293 | 297 | 198 |
| Boosted defense | 283 | 293 | 283 | 190 |
| Boosted defense + Elo | 273 | 294 | 301 | 192 |

Log loss by fold:

| Variant | 2019 | 2021 | 2022 | 2023 partial |
| --- | ---: | ---: | ---: | ---: |
| Baseline | 0.692238 | 0.693037 | 0.684863 | 0.693208 |
| Full defense | 0.683313 | 0.688228 | 0.672234 | 0.683220 |
| Elo alone | 0.695580 | 0.683070 | 0.682718 | 0.690035 |
| Defense + Elo | 0.687497 | 0.678162 | 0.667581 | 0.678778 |
| Boosted defense | 0.683091 | 0.670138 | 0.671009 | 0.679902 |
| Boosted defense + Elo | 0.692012 | 0.669035 | 0.659787 | 0.675684 |

Brier score by fold:

| Variant | 2019 | 2021 | 2022 | 2023 partial |
| --- | ---: | ---: | ---: | ---: |
| Baseline | 0.249528 | 0.248684 | 0.245918 | 0.249920 |
| Full defense | 0.244981 | 0.244995 | 0.239573 | 0.244911 |
| Elo alone | 0.251219 | 0.245006 | 0.244799 | 0.248466 |
| Defense + Elo | 0.247172 | 0.240851 | 0.237325 | 0.242914 |
| Boosted defense | 0.245285 | 0.238349 | 0.239538 | 0.243669 |
| Boosted defense + Elo | 0.249680 | 0.238252 | 0.234173 | 0.241638 |

Paired accuracy differences, in percentage points:

| Comparison | Difference | Date-bootstrap 95% interval |
| --- | ---: | ---: |
| Elo alone minus full defense | -3.28 | [-6.09, -0.59] |
| Defense + Elo minus full defense | +0.32 | [-1.51, +2.15] |
| Boosted defense minus full defense | -0.97 | [-3.19, +1.14] |
| Boosted defense + Elo minus full defense | -0.38 | [-2.81, +2.01] |
| Boosted defense + Elo minus boosted defense | +0.59 | [-1.25, +2.62] |

Interpretation:

- Defense + Elo improved pooled log loss by approximately 0.003654 and
  accuracy by six bouts (+0.32 points). Its fold changes in correct picks
  were -12, +4, +23 and -9. That is a small, uneven accuracy difference whose
  interval includes both harm and improvement. It is not an established
  future accuracy gain. Log loss improved in three folds but worsened in 2019.
- Boosted defense + Elo had the best pooled log loss (0.674022) and Brier
  score (0.240889) among these six variants, while getting seven fewer picks
  right than full defense and thirteen fewer than logistic defense + Elo.
  Lower probability losses do not by themselves establish better calibration.
- Adding Elo to the boosted model improved pooled accuracy by eleven bouts
  and log loss by approximately 0.001712, but the accuracy interval again
  includes zero. Its largest benefit was in 2022; it hurt 2019.
- The earlier exploratory defense-without-knockdowns variant remains higher
  in observed accuracy at 1,077/1,857 (58.00%). This study does not establish
  a new overall accuracy record, and it did not include that variant as a
  newly fitted competitor.
- The result supports retaining Elo and boosting as research candidates,
  with full defense preserved as the reference. Before selecting the next
  comparison, inspect saved symmetry, reliability, subgroup and probability
  difference intervals. These have not been reviewed from the pasted output.
  Do not start parameter searches or call any result a live model score.

PR #15 remains a draft pending that evidence review and the Mac check
summary. Recording successful research does not require a candidate to beat
every reference, and merging an experiment would not promote a model.

## Mac reproduction commands

Suggested model for this bounded implementation/check: Sol High.

With the feature branch checked out and a clean working tree:

```bash
source .venv/bin/activate
python -m ruff check .
python -m pytest
python -m upset.data.export_prefight_ratings
python -m upset.data.audit_prefight_ratings
python -m upset.modeling.run_elo_comparison
```

The first Mac run confirmed 17,102 rating rows, 1,857 decisive validation
bouts and 35 Draw/NC exclusions. Baseline/full-defense probabilities matched
their saved references (985 and 1,067 correct respectively). The successful
run need not be repeated to share or inspect its saved manifest.

New experiment outputs:

- `data/processed/kaggle_ufc_1994_2026/experiments/elo_comparison_v1/predictions.jsonl`
- `data/processed/kaggle_ufc_1994_2026/experiments/elo_comparison_v1/manifest.json`

The terminal prints pooled and fold tables plus accuracy intervals. The
manifest includes all diagnostics and source/code hashes. If rerunning is
necessary, retain the original and choose, for example,
`--output data/processed/kaggle_ufc_1994_2026/experiments/elo_comparison_v1_rerun`.
Do not rerun old exports or replace prior reference files merely to sync code.

No Cito key, paid data, network collection, production model or prospective
archive extension is needed for this experiment. After reviewing its actual
results, decide on the next feature family; recent performance is still pending.

API reference checked during implementation:
[scikit-learn HistGradientBoostingClassifier](https://scikit-learn.org/stable/modules/generated/sklearn.ensemble.HistGradientBoostingClassifier.html).
The settings above are experiment choices, not recommendations from that API.
