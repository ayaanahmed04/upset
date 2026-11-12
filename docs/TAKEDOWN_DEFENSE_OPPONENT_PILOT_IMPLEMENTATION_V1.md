# Pilot implementation notes — fixed before scoring

October 26, 2026. Complements the preserved pilot protocol; no model or gate
changes. Penalty selection uses its primary support (at least two earlier
positive-count defender bouts), pooled by side across 2012-2017. Secondary
cohorts do not select penalties. Calendar 2018 stays out of selection.

Defender history counts positive opponent-attempt observations. Attacker
history counts positive attempts made by the opposing fighter, using their
appearances as opponent_id in those same paired observations. Defender and
attacker cold starts mean zero exposure in the corresponding role, rather
than zero appearances in any role. History slices are 0, 1, 2-4, 5-9 and 10+.

Role-graph membership is reconstructed separately for each snapshot, using
only positive earlier observations. Edges join a defender role to an attacker
role. Held-out sides are within-component, across-component, or unseen-role;
unseen roles do not receive invented component IDs. The source adapter is
hash-verified and paired-audited through the end of 2018 before any fitting.

The defense-only objective is exactly the preserved v1 objective with all
attack coefficients fixed at zero, optimizing only intercept and defense.
Its bounds, penalties, starts, tolerances and numerical gates match v1.
No fitted v1 files are edited. All raw career clipping is counted, including
the number on primary support. Shrinkage means require a nondegenerate global
rate; fail rather than invent a prior if no such earlier rate exists.

The proceed gate applies to the primary 2018 cohort and compares attack/defense
with **both** global shrink25 and defense-only. No normalized-RPS worsening
means the paired mean is <=0 for both. Subgroup regression flags are checked
against both comparators on primary 2018 slices; secondary cohorts have their
own diagnostics. Each comparison records paired date-bootstrap and crossed
fighter-weight sensitivity for NLL, RPS and both interval scores. Thin-group
flags remain inconclusive. All intervals describe these fixed predictions and
do not include re-selection or re-fitting uncertainty.

If a declared optimizer gate fails, stop real scoring. Retain the failed fit's
diagnostic log and report the numerical block; do not relax the acceptance
thresholds or substitute a different penalty based on pilot data.
