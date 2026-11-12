# Opponent pilot v3 — align stopping and acceptance tolerances

October 26, 2026. Declared before penalty selection and 2018 scoring. The v2
restart failed on the same first-year fit, returning ABNORMAL with zero new
iterations and the same 1.10e-5 maximum absolute gradient. Its source and
diagnostics are preserved in the separate v2_blocked directory. No completed
pilot evaluation exists from v1 or v2.

Use the original likelihood, gradient, parameter bounds, penalties, three
starts and ftol 1e-16. Set the optimizer gtol to **5e-5**, half the existing
absolute-gradient acceptance threshold 1e-4, for both model families and all
penalties. Disable the v2 retry. This allows gradient convergence to stop
before attempting changes below objective floating-point resolution. Bounds
must remain inactive, so projected and ordinary gradients agree on accepted
fits. The original gtol 1e-7 demanded much more precision than acceptance.

The actual acceptance criteria are unchanged: every start must report
success, absolute gradient <=1e-4, no bound within 1e-5, objective spread <=1e-6
and prediction spread <=1e-5. If any criterion fails, stop. Do not accept an
ABNORMAL result or loosen the fit, prediction or statistical gates.

All data, support, annual cutoffs, {1,4,16} penalty selection, predictive family,
dependence checks and proceed gates remain exactly as in the preserved v1
pilot protocol and implementation notes. Use a new immutable v3 output folder,
record the optimizer tolerance and retain every start's diagnostics. This is a
numerical stopping correction, not evidence that any predictive model wins.
