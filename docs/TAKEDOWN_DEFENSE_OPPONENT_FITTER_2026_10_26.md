# First opponent-quality fitter — October 26, 2026

**Implemented and numerically checked.** The first offline fitter separates
defender effects from opposing takedown attack. Both real-data benchmarks
passed the declared numerical gates. This makes a chronological comparison
practical; it does not establish a predictive gain or validated fighter skill.

## Model and numerical checks

For each positive-attempt side, the stopped-takedown probability is
logistic(intercept + defender effect - attacker effect). Each permanent ID has
separate attack and defense roles. The count likelihood is beta-binomial with
the existing fixed concentration 5. Role effects have a fixed ridge penalty 4;
the intercept penalty is 0.01. These are penalized point estimates, without
skill intervals. Penalty 4 was fixed for engineering checks, not chosen by real
predictive scores. The initial context is one shared intercept.

The analytic objective/gradient agrees with independent SciPy PMFs and central
finite differences, including zero-stopped, all-stopped and one-attempt rows.
Tests verify the sign convention, unseen-role baseline, exact cutoff handling,
future identity/outcome exclusion, zero-attempt invariance, input-order
reproducibility, separate-role connectivity, provenance pair checks and
rejection of invalid data, failed optimization and existing output directories.

Matching simulation used 36 fighters, 6,300 fitting sides and 1,260 separate
synthetic validation sides. Recovered defense correlated 0.986 with its known
truth (centered RMSE 0.091); attack correlated 0.990 (RMSE 0.079). Mean held-out
probability error was -0.00142. These results check the implementation under
the model's own assumptions; they are not validation on real UFC outcomes.

All fits used three fixed starting points. Acceptance requires successful
optimizer termination, maximum absolute gradient <=1e-4, no boundary solution,
objective spread <=1e-6 and prediction spread <=1e-5. The initial simulation
revealed objective-based stopping before the gradient gate; ftol was tightened
before any real-data fitting. This change and the exact rules are recorded in
the [fitter protocol](TAKEDOWN_DEFENSE_OPPONENT_FITTER_PROTOCOL_V1.md).

## Real-data benchmarks

| Exclusive cutoff | Positive sides | Opposing attempts | Dates | Role parameters incl. intercept | Three-start fit time |
| --- | ---: | ---: | ---: | ---: | ---: |
| 2006-01-01 | 592 | 2,008 | 64 | 552 | 0.030 s |
| 2019-01-01 | 6,536 | 27,892 | 457 | 3,278 | 0.431 s |

Times are measured on this machine, excluding data validation/export and the
separate repeat run. All six optimizer starts passed. The representative fit's
largest absolute gradient was 6.24e-6; its starting-point prediction spread was
6.66e-8. Repeating the representative fit gave identical coefficients on this
environment (maximum difference 0). Multiple starts do not prove a global
optimum of the penalized beta-binomial objective.

The pre-2019 input contained 4,924 paired fights / 9,848 sides, including 3,312
zero-attempt sides. Reciprocal identities, event/date, provider participant
identities and paired source/database hashes passed. Positive observations
span 1,668 defender roles and 1,609 attacker roles, all from the existing Kaggle
source in this cutoff. No new data were acquired.

## What remains unresolved

The separate-role schedule graph has 90 components. The largest two have 2,858
and 225 role nodes; remaining components are tiny. Ridge makes their numerical
origin defined, but does not supply empirical comparisons across disconnected
schedules. There are 472 defender roles and 480 attacker roles with only one
positive-attempt bout. The model also omits division and era effects; 224
positive sides have unknown division. These limits preclude a public ranking
or a clean interpretation of coefficients as underlying technique.

No real held-out predictive scores were computed, and no historical winner
model, web display, percentile system or serving database was changed. The
previous high-attempt uncertainty issue remains unresolved. The next bounded
comparison is fixed in the [chronological pilot protocol](TAKEDOWN_DEFENSE_OPPONENT_PILOT_PROTOCOL_V1.md):
annual snapshots for 2012-2017 penalty selection and a frozen 2018 development
diagnostic, with global shrinkage and matched defense-only comparators. It
must establish opponent-specific value before a larger backfill.

## Verification and reproduction

72 relevant tests passed across the new fitter and the four existing skill
modules. Ruff and `git diff --check` passed. Independent real-fit objective
checks, source/output hashes and preservation checks are recorded in
`data/processed/td_defense_opponent_verification_2026_10_26.json`.

Code: `src/upset/skill/defense_opponent.py`. Immutable results:
`data/processed/td_defense_opponent_fitter_2026_10_26_v1/report.json` and
`coefficients.json`. Coefficients are offline diagnostics, not released ratings.
The initial draft specification remains preserved.

To reproduce into a new folder:

```bash
cd ~/Projects/upset
source .venv/bin/activate
python -m upset.skill.defense_opponent \
  --adapter data/processed/td_defense_adapter_2026_10_26_v1 \
  --protocol docs/TAKEDOWN_DEFENSE_OPPONENT_FITTER_PROTOCOL_V1.md \
  --output data/processed/<new-opponent-fitter-directory>
```

No package installation, server restart, commit or push was performed.
