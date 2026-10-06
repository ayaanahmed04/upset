# Local UPSET research preview

The first product layer uses SQLite and Python's standard-library HTTP server.
It needs no extra dependencies or provider requests. It binds to `127.0.0.1`
only and serves a packaged HTML/JavaScript interface.

```bash
python -m upset.data.review_cito_fighter_bundles
python -m upset.data.build_research_db
python -m upset.research_app
```

Then visit http://127.0.0.1:8765. Keep the server terminal running; Ctrl+C
stops it. This is a local research preview, not a production deployment.

## Input cohort

The database requires the accepted historical identified files, the hash-checked
current export, its exact supplementary registry, and the accepted historical
result overlay. Expected full inputs: 4,455 historical profiles, 8,551 frozen
historical bouts and 245 verified current bouts (8,796 total / 17,592 fighter
stat rows). These counts are expectations until the private full build runs.
The 94 current bouts involving unresolved identities stay outside the viewer.
Eleven missing historical round records do not prevent a fight-total viewer.

The builder saves `data/processed/research_v1/upset.sqlite` and its manifest.
It checks paired participants, provider links, source hashes, duplicate dated
matchups, counts, durations and SQLite integrity. Repeating reuses an intact
database; altered inputs or output fail instead of being silently refreshed.
The viewer opens the database in read-only mode and checks its hash at startup.
Distinct bout IDs from the same source can share a date and both participants,
as with Silveira/Sakuraba on December 21, 1997. Both records remain in the
viewer; repeated bout IDs, cross-provider same-date matches and invalid fighter
identities still fail. The date cutoff excludes all bouts on the selected date.

## Available product features

- Accent-insensitive fighter-name search; word order may differ. Duplicate
  names remain separate identities with visible source IDs.
- Fighter profiles and all accepted fight rows strictly before a selected date.
- Metrics over the last 3, 5 or 10 recorded fights, or all recorded fights.
- Offense and defense from each fighter and their paired opponent counts.
- Per-fight striking-differential charts and same-window comparisons.
- Explicit archive dates, excluded current cohort and evidence counts.

Rates use total counts divided by total observed minutes, not averages of
per-fight rates. Accuracy and defense use summed attempts. Zero opponent
attempts give unknown defense, not 100%. Zero-duration bouts remain in the
history but are excluded from rate calculations. Control margin only uses
bouts where both control fields are observed; it shows that exposure.
Profile measurements are the frozen source snapshot, not measurements known
at every selected fight date. A fight-date filter is not proof of historical
source availability. This viewer is descriptive research, not the model's
as-of reconstruction or a forecasting endpoint.

Reviewed result amendments are displayed as currently reviewed outcomes, with
the frozen result retained separately on each history row. Their observation
does not establish the amendment's effective date. Original research files,
registry links, features and model coefficients remain unchanged.

## Fighter-bundle review

`review_cito_fighter_bundles` checks the complete saved plan and all responses,
normalizes profile observations, and compares name candidates against the
private historical profiles. It adds **no identity links**. Age never becomes
an invented DOB; zero/implausible body measurements stay unavailable.

The real uploaded cohort had 303 successful responses for 101 provider IDs,
zero source DOBs and no external UFCStats crosswalk. Four career-stat responses
fall below already captured current-cohort counts (Shanelle Dyer, Mark
Vologdin, Kurtis Campbell and Victor Valenzuela); scope, freshness or identity
needs review. Victor's Joe Boxer profile versus Psicosis bout history is
separately flagged using the two distinct UFC athlete pages. The current
paired bout stats remain usable independently of those profile aggregates.

Output: `data/processed/cito_fighter_review_v1/{profile_observations.jsonl,
identity_review.jsonl,manifest.json}`. The new observations are unlinked and
are not stitched onto historical identities or historical model features.
The actual uploaded responses and normalized shapes were checked here;
historical demographic comparisons require the local private profile file.

## Validation and limits

Tests exercise read-only serving, literal/token search and duplicate names,
exclusive date cutoffs, identical comparison windows, weighted rates, paired
defense counts, control missingness, amended/frozen result separation, source
tampering and output reuse. HTML is served over a real test HTTP server;
JavaScript syntax is checked separately. A browser rendering/interaction
review remains to be done on the local full-data preview.

Independent full UFC calendar coverage remains unverified. No natural-language
query engine, opponent-adjusted product rating or win probabilities are
provided in this preview. Public launch is separate: Cito's terms distinguish
application display from feed/API redistribution, and post-cancellation public
display needs specific clarification beyond the personal-retention email.
Sources: https://citoapi.com/terms/ and the retained provider correspondence.
