# UPSET results-only rating comparison

Use the November 10 reviewed database and the verified v4 snapshot through
November 7. This is a retrospective walk-forward study. The historical archive
uses reviewed outcomes and was available for development. Keep live ratings
separate from the probability experiment.

## Models and timing

- Use v4's unrounded combined score difference as the v4 research input.
  Evaluate both the original pre-2019 logistic fit and a yearly refit of its
  slope. Report the displayed badge's ordering on the same bouts.
- Use the current résumé rule as the results-only baseline. Both fighters
  start at Elo 1500, the logistic scale is 400, and a decisive result updates
  Elo with K=32. Use the expected-score term to credit wins over stronger
  opponents. Replay a responsive variant with K=64 and a 730-day half-life
  for the difference from Elo 1500. Each fighter's Elo regresses toward 1500
  between decisive fights. A draw or no-contest leaves results-only state
  alone. Every bout on one date uses the same pre-date state.
- Compare the recalibrated model probabilities on identical decisive bouts
  where both fighters had a v4 state before the event. Calibrate one
  nonnegative, zero-intercept logistic slope per model using matched bouts
  from 2012 up to the start of each evaluation year. Use score differences
  divided by 10 points for v4, and Elo differences divided by 100. Evaluate
  2019 through November 7, 2026. Report the 2025–26 subset, known title bouts,
  and annual folds separately. Give ties half credit in ordering, and report
  tie counts. Exclude debuts without a prior v4 grade from the matched sample
  and count the exclusions.
- Compare mean natural-log loss and Brier score on matched bouts. Report
  paired event-date bootstrap intervals for log-loss differences with the
  project's existing bootstrap convention. These intervals describe
  sensitivity to the event-date sample. The same fighters can appear across
  event dates.

## Market comparison

Use the November 10, 2026 download of the CC0 UFC Betting Odds Daily archive.
Match UFCStats bout IDs and both permanent fighter identities when a source
bout ID is available. For rows without UFCStats bout IDs, require a unique
exact normalized fighter-name pair on the same event date. Use the most
recent unambiguous paired BetOnline.ag US moneyline strictly before 00:00 UTC
on the event date, at most seven days old. Check both odds and align corners.
Divide each reciprocal decimal price by the sum of both reciprocals to
remove the bookmaker margin proportionally. Use the resulting probability as
the market comparator on the same covered bouts. The source has daily
observations and no verified closing timestamp. This benchmark uses pre-event
prices. Source rows timestamped after the cutoff and untimestamped backfills
are excluded.
[Odds archive](https://www.kaggle.com/datasets/jerzyszocik/ufc-betting-odds-daily-dataset)

## Rating interpretation

For known title fights since January 2025 and the matchups named in the
November 10 review, show the recorded winner and each model's ordering before
the fight, after the fight date and at the end of the reviewed archive.
Report how often the recorded winner trails the loser in each view, with ties
separate. The end-of-archive ranking can reflect later fights. Cases are
diagnostics and do not select the model or override individual grades.

Use the retrospective results to select models for a prospective comparison.
Record each candidate’s predictions before the fight so future results can be
scored against the probabilities that were actually recorded.
