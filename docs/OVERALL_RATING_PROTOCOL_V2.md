# Experimental UPSET rating v2 — declared November 5, 2026

This protocol was written before running v2 on the recorded bouts. It responds
to the v1 review. Preserve v1 and its source bindings. This is a product-design
comparison on previously inspected historical data, not independent future
validation. No fighter's particular result determines a parameter or gate.

## Fixed changes

1. Add KO/TKO wins per recorded bout to Striking. Use the recorded method
   group; no guessed doctor or corner stoppage. Credit the observed KO/TKO win
   relative to the opponent's earlier pooled KO loss rate. Use five prior
   bouts, a standard-deviation floor of .10 and weight .10. Multiply the six
   original Striking weights by .90. The separate KO loss feature stays.
   Preserve all other feature definitions, divisions/fallbacks, exposure
   priors, .85 bout recency, Elo K32, date batching, and missingness rules.
2. Fix the overall blend to 50% Résumé and 50% Skills for product reasons:
   the badge should give achievement substantial weight. Retain the
   50/30/20 strongest-to-weakest skills blend. Do not choose the résumé weight
   using later outcomes. Fit only the positive logistic slope, using the v1
   matched 2012–2018 training rule. This slope is for evaluation, not a displayed
   individual win probability.
3. Rebuild a fixed empirical reference from v2 combined values strictly
   before 2019, with the same midrank method and interpolation anchors as v1.
   Retain half-up rounding except 99 requires both an unrounded grade of 99
   and a reference percentile at least .9999. Check the resulting names as a
   descriptive sanity check; do not tune a cutoff around any name. The reference
   is a distribution of fighter-date states, not unique fighters or a division
   ranking. Preserve raw component and combined values.
4. Keep the first-rating, fewer-than-five cap of 88, provisional label below
   four bouts, and per-date ±5 movement cap. After these, hold the previous
   displayed score if an all-win date would lower it, or an all-loss date would
   raise it. All-win/all-loss means every recorded bout for that fighter on the
   date has that same decisive result. Debut has no prior score to hold; mixed,
   draw, NC and unresolved dates are not held. Save the original curve grade,
   small-history and change-limit adjustments, unheld grade, hold reason, final
   grade, history and peak. A hold affects the displayed grade and next date's
   display baseline, not the underlying skill components, Elo or evaluation
   features. A result can leave the badge unchanged. An already earned 99 can
   be retained by a win hold; a new attainment still requires a qualifying
   curve grade. Report earned and held 99 states separately.

## Comparisons and decisions

Use the same reviewed database, identities, dated information contract and
matched decisive development fights from 2019 to before 2026-10-26 as v1.
Exclude debuts, unavailable components and nondecisive bouts from probability
scoring. October 31 is serving history only. Reproduce v1 from its saved outputs,
including the same cutoff ordering and pre-fight score convention. Compare:

- v1 versus v2 raw combined probability log loss and Brier on identical fights;
- v2 with and without the outcome holds, to isolate display-policy effects;
- higher displayed grade winner share on each version's eligible non-tied
  fights, and separately on the intersection where both give unequal grades;
- actual limit applications versus changes that simply equal ±5, both overall
  and with ten or more prior bouts; wrong-direction wins/losses, holds, ties,
  grade distributions and distinct fighters reaching 99. Report exact scopes
  and explain differences from the pasted review's denominators.

Save whole-date paired bootstrap intervals (1,000, seed 20261105), subgroup
summaries, a worked Gaethje example, and exact prefix/chronology checks. Report
qualitative cases and the effect of fixed-curve steepness separately. Do not
change the volatility cap in this run.

Local experimental activation requires all of: byte-preserved v1 inputs,
same matched support of at least 500 development bouts, finite features and
scores, strict earlier-date lookups, snapshot/hash and hold/cap/peak/99 checks,
zero wrong-direction updates in the all-win/all-loss group, v2 mean development
log loss below ln(2) and no more than .010 worse than v1, and higher-grade
winner share no more than two percentage points worse on the common non-tied
display support (at least 500 fights). These are practical preview thresholds,
not statistical proof of non-inferiority. A failure preserves the experimental
results offline and leaves v1 numerical ratings live. A pass permits a clearly
labelled local Experimental v2 with rollback instructions. No public release,
validated skill or new-fight performance claim.

## Viewer and review package

Show the percentage of earlier reference states below or tied-midrank with
the combined score in plain language. Explain the reference ends in 2018 and
state actual caps/holds. A result summary uses recorded method, opponent and
selected raw stats, never an invented stoppage cause or a claim that one stat
fully caused the change. Keep the user's tier colors and distinguish negative
changes through a minus sign and direction label in neutral text. In the
shareable ZIP add fighter names to evaluation records, a named 99 list, v1/v2
outcome and volatility tables, exact formulas, and verified outputs. Omit
private browser screenshots, credentials, and machine-specific paths. Provide
the file to the user; do not send it to other people.
