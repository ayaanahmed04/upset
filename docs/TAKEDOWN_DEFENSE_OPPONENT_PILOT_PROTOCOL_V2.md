# Opponent pilot v2 — numerical retry amendment

October 26, 2026, declared after v1's first-year numerical block and **before
2018 scoring or any penalty selection**. All statistical choices, supports,
scoring, seeds, penalty grid and proceed gates in the preserved
`TAKEDOWN_DEFENSE_OPPONENT_PILOT_PROTOCOL_V1.md` and implementation notes remain
fixed. This amendment changes only handling of an optimizer termination error.

V1 stopped at the 2012 opponent-model snapshot with penalty 4: one start
returned ABNORMAL line-search termination despite a 1.10e-5 maximum gradient,
objective agreement within 9.1e-13 and prediction spread 2.94e-8. Required
success flags were not all true. No completed v1 pilot scores or 2018 diagnostic
were produced. Failure, preceding fits and source snapshot are preserved in
`data/processed/td_defense_opponent_pilot_2026_10_26_v1_blocked/`.

For each of the original three starts, first run the exact original optimizer
configuration. If and only if it terminates unsuccessfully **and** its finite
gradient already meets the existing <=1e-4 gate, with no coefficient within
1e-5 of a bound, allow one restart from its final parameters using ftol 1e-14
instead of 1e-16. Objective, analytic gradient, gtol 1e-7, bounds, maximum
iterations and line search limit stay unchanged. The retry must report success
and still meet the original absolute-gradient and boundary gates. There is no
second retry. Initial errors are retained alongside final diagnostics.

Across the final results of all three original starts, require exactly the
original objective spread <=1e-6 and probability spread <=1e-5. Any failure
blocks scoring, as before. No result is accepted solely because its objective
is close or its gradient is small while the optimizer still reports failure.
Successful initial runs are not retried, including successful runs that fail
the gradient gate. No model/prediction change is selected by a later score.

Use a new immutable v2 output directory and record the total number of retries.
The original fitter implementation and previous artifacts remain untouched.
