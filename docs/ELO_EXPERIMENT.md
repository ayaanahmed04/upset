# Chronological opponent-strength experiment (v1)

Implementation checkpoint: September 24, 2026. The implementation and
synthetic tests are available. **No full historical-data score has been
produced for this experiment.** The Mac must run the commands below before
we can assess predictive value. The preserved 57.46% full-defense result is
still the main development reference; the 75% goal remains a research target.

Assistant-environment validation: 288 pytest tests and 16 subtests passed;
Ruff clean. Python 3.12.14, NumPy 2.3.5 and scikit-learn 1.8.0 were used.
The original 260 tests also passed before adding the new tests. Synthetic
fixture metrics are not UFC performance estimates.

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

## Mac run

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

On the accepted snapshot, expect 17,102 rating rows, 1,857 decisive validation
bouts and 35 Draw/NC exclusions. These are expected cohort counts, not results
observed here. Baseline/full-defense probabilities must match their saved
references (985 and 1,067 correct respectively). New accuracy is unknown.

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
