# UPSET Project Status

**Last updated:** September 24, 2026

**Current phase:** Historical modeling and data integration

**Current focus:** Review the completed Elo/boosted-tree experiment and its saved diagnostics

## Project Goal

Build a professional UFC analytics and machine learning platform that serves as both a real public product and a flagship portfolio project.

## Career Focus

Primary:

- Data Science / Machine Learning

Secondary:

- Software Engineering / Backend / Full Stack

Additional:

- Data Analytics

## Current Technical Decisions

- Python 3.12
- Git and GitHub for version control
- Private GitHub repository during initial development
- UFC-only scope for v1
- Analytics/research platform positioning
- Betting-specific functionality deferred until later
- Public web application planned
- Historical dataset used for local data science and ML development
- Provider-independent canonical data models implemented
- UPSET-owned fighter identities use permanent UUID4 identifiers
- Provider fighter IDs are stored through separate evidence-backed links
- Display names are labels and are not identity keys
- Raw source data remains immutable
- Fighter names will not be used as permanent unique identifiers
- Historical name collisions require evidence-backed, version-controlled overrides
- Multiple data providers may be used for different purposes
- Cito is a candidate for early API experimentation
- UFCalendar is a candidate for future application/update ingestion
- SportsDataIO and Sportradar remain possible future production-grade providers
- Tapology and Sherdog are validation/research sources rather than automated ingestion sources

## Completed

- Created private GitHub repository `ayaanahmed04/upset`
- Cloned repository to `~/Projects/upset`
- Configured GitHub CLI authentication
- Configured Git identity with personal email
- Installed Python 3.12.14 with Homebrew
- Created and verified `.venv`
- Configured `.gitignore`
- Created initial project structure
- Added `ROADMAP.md`, `PROJECT_STATUS.md`, and `DECISIONS.md`
- Created `src/upset`, `tests`, `notebooks`, and data directories
- Added `pyproject.toml`
- Added NumPy, pandas, scikit-learn, and matplotlib
- Added pytest, Ruff, and JupyterLab development tooling
- Installed UPSET as an editable Python package
- Added first import test
- Verified pytest passes: `1 passed`
- Verified Ruff passes: `All checks passed`
- Researched UFC data-source options and licensing/access considerations
- Established initial source strategy
- Downloaded José Silva UFC 1994–2026 Kaggle dataset
- Stored raw files under `data/raw/kaggle_ufc_1994_2026/`
- Verified raw dataset is ignored by Git
- Created `notebooks/01_data_audit.ipynb`
- Configured notebook to use project `.venv` Python 3.12.14 kernel
- Loaded fighter dataset: 4,455 rows × 18 columns
- Loaded fight dataset: 8,551 rows × 37 columns
- Audited fighter-profile missingness
- Identified substantial missing reach, stance, DOB, height, and weight data
- Identified suspicious zero-valued career statistics requiring semantic validation
- Confirmed fight-data coverage from 1994-03-11 through 2026-03-07
- Confirmed no duplicate `Fighter_URL` records
- Confirmed no duplicate `Fight_URL` records
- Confirmed all 2,647 distinct fighter-name labels appearing in fight rows have a matching fighter-profile name
- Identified 1,801 profile-only fighter names requiring later investigation
- Identified seven fighter-name collisions representing distinct people
- Established that fighter names cannot safely serve as permanent unique identifiers
- Identified structural control-time missingness in early UFC history
- Found strong evidence that control-time coverage begins around UFC 21 on 1999-07-16
- Established a working assumption that pre-UFC-21 control-time zeros may represent unavailable data rather than true zero control
- Confirmed raw source data should remain unchanged and corrections should occur during processing/normalization
- Investigated 1,803 profile-only fighter rows representing 1,801 unique names
- Confirmed profile-only row/name difference is caused by duplicate fighter-name identities
- Confirmed all profile-only fighter records originate from UFCStats profiles
- Formally accepted the Kaggle dataset as UPSET's initial historical development snapshot
- Created and authenticated a Cito API account
- Added `requests` and `python-dotenv` project dependencies
- Configured local `.env` secrets handling and verified `.env` is ignored by Git
- Successfully queried Cito from both the terminal and Python
- Compared Islam Makhachev across Kaggle and Cito
- Confirmed Cito provides structured fighter IDs, event IDs, and bout IDs
- Confirmed Cito provides true fighter-by-round statistics
- Confirmed historical round-stat access is restricted by Cito API plan
- Successfully retrieved recent round statistics for Curtis Blaydes vs Waldo Cortes Acosta
- Validated that head/body/leg and distance/clinch/ground round-stat breakdowns reconcile with significant-strike totals
- Created `src/upset/data/normalization.py`
- Added normalization helpers for landed/attempted statistics and control time
- Added initial Cito round-stat normalization into UPSET-owned field names
- Added normalization tests
- Verified pytest passes: `4 passed`
- Verified Ruff passes: `All checks passed`
- Defined canonical provider-independent `RoundStats` dataclass
- Updated Cito round normalization to return a typed `RoundStats` object instead of a generic dictionary
- Added canonical `Fighter` dataclass
- Added Cito fighter normalization
- Added numeric normalization for optional fighter measurements
- Confirmed current provider values such as height, weight, and reach are converted from API strings into numeric UPSET values
- Added canonical `Event` dataclass
- Added Cito event normalization
- Added canonical `Fight` dataclass
- Established the initial canonical entities: `Fighter`, `Event`, `Fight`, and `RoundStats`
- Established that fighter identity information should remain separate from time-dependent career-statistic snapshots
- Expanded automated normalization and canonical-model tests
- Verified the canonical data layer with pytest and Ruff
- Implemented `normalize_cito_fight()` using inspected Cito bout fields
- Preserved fighter profile IDs using `fighterId`
- Resolved winner names by matching `winnerFighterSlug` to a participant
- Added optional event linking with provider and event-slug validation
- Verified fight normalization and event linking on the sampled Cito bout
- Added 10 automated fight-normalization test cases; 17 total tests passed
- Verified Ruff and Git whitespace checks pass
- Verified sampled Cito fight connections to both fighter profiles and six round-stat records
- Added event_date, source_url, and source_winner_label to the Fight model
- Implemented normalize_kaggle_fight() for historical fight identity and result fields
- Converted all 8,551 historical fight rows in notebook memory with zero rejections
- Confirmed 8,551 unique normalized fight IDs
- Preserved 151 combined Draw/NC labels with winner_name=None
- Left unavailable historical fighter IDs and event IDs unset
- Added 14 historical normalization test cases; 31 total tests passed
- Verified Ruff and Git whitespace checks pass
- Added a repeatable historical fight export command:
  `python -m upset.data.export_historical`
- Exported 8,551 normalized fights to
  `data/processed/kaggle_ufc_1994_2026/fights.jsonl`
- Verified the saved records exactly match the normalized records
- Preserved missing values, string IDs, source URLs, and Draw/NC labels
- Added checks for invalid records, duplicate fight IDs, and empty input
- Write and verify a temporary file before replacing the processed export
- Added five export test cases; 36 total tests passed
- Added historical fighter measurement parsing for height, weight, and reach
- Extended Fighter with optional birth date and source URL; allowed absent slugs
- Normalized all 4,455 historical profiles with zero rejected records and
  4,455 unique source profile IDs
- Preserved missing values: height 318, weight 86, reach 1,940,
  stance 849, and birth date 506
- Kept career aggregates separate from normalized fighter profiles
- Added the repeatable profile export command:
  `python -m upset.data.export_profiles`
- Exported 4,455 profiles to
  `data/processed/kaggle_ufc_1994_2026/fighters.jsonl`
- Verified exported profiles match the normalized records on read-back
- Added 30 profile normalization and export test cases; 66 total tests passed
- Verified Ruff and Git whitespace checks pass

- Audited all 17,102 historical fight-participant slots
- Found 17,056 slots with one same-source profile candidate, 46 with multiple candidates, and zero without a candidate
- Identified five collided names requiring fight-level review: Bruno Silva, Michael McDonald, Jean Silva, Mike Davis, and Joey Gomez
- Resolved all 46 ambiguous slots from UFCStats profile histories by matching event date and opponent
- Added the version-controlled reviewed mapping:
  `data/mappings/kaggle_fighter_overrides.json`
- Implemented deterministic historical fight-to-profile linking
- Added validation for missing or ambiguous participants, duplicate records and overrides, inconsistent mapping evidence, invalid candidate IDs, conflicting links, same-profile opponents, and unused overrides
- Linked both participants in all 8,551 historical fights: 17,102 linked slots and zero unresolved slots
- Added the repeatable linked-fight export command:
  `python -m upset.data.export_linked`
- Exported linked fights to
  `data/processed/kaggle_ufc_1994_2026/fights_linked.jsonl`
- Verified the linked export matches the in-memory records on read-back
- Added 24 linking and linked-export test cases; 90 total tests passed
- Verified Ruff and Git whitespace checks pass
- Added `docs/FIELD_MAPPINGS.md` documenting the implemented Kaggle and Cito field mappings, provider-specific identifiers, dataset grain, units, missing-value behavior, outcome handling, identity overrides, and repeatable export contracts
- Audited historical target and position strike breakdowns across all 17,102 fighter appearances
- Confirmed `Head + Body + Leg` and `Distance + Clinch + Ground` equal significant strikes landed in every historical fighter appearance
- Added the canonical `FightStats` model with one record per fighter per complete fight
- Implemented historical fighter-fight statistic normalization
- Added validation for nonnegative whole-number counts, landed/attempted relationships, linked fight identity, and significant-strike breakdowns
- Applied the pre-UFC-21 control-time rule in the processed statistics layer
- Converted 360 structurally unavailable control-time values to missing while preserving 2,667 recorded zero-control values
- Normalized all 8,551 historical fights into 17,102 unique fighter-fight statistic records with zero rejected fights
- Added the repeatable historical fight-stat export command: `python -m upset.data.export_fight_stats`
- Exported and verified `data/processed/kaggle_ufc_1994_2026/fight_stats.jsonl`
- Added 23 fight-stat normalization and export tests; 113 total tests passed
- Verified Ruff and Git whitespace checks pass
- Added permanent UPSET-owned fighter identities using canonical UUID4 values
- Added evidence-backed mappings from provider fighter IDs to UPSET identities
- Added validation for malformed UUIDs, duplicate identities, conflicting
  provider links, unknown identity references, and invalid registry structure
- Added versioned JSON registry persistence with deterministic ordering,
  temporary-file writing, and read-back verification
- Added the repeatable identity-registry export command:
  `python -m upset.data.export_identity_registry`
- Created 4,455 permanent UPSET fighter identities from the normalized
  historical fighter profiles
- Created 4,455 unique UFCStats provider links
- Preserved all seven duplicate-name groups as separate identities
- Verified that a second export reused all 4,455 identities, created zero new
  identities, and produced the same SHA-256 checksum
- Added 20 identity, registry, and registry-export tests; 133 total tests passed
- Verified Ruff and Git whitespace checks pass
- Added a separate historical identity-enrichment stage for profiles, linked
  fights, and fighter-fight statistics. It preserves the existing source JSONL
  contracts and reads permanent UUIDs from the committed registry.
- Added cross-file checks for missing mappings, duplicate records, missing
  profiles, participant identity collisions, and missing or extra statistics.
- Added the repeatable command `python -m upset.data.export_identified`.
- Verified 141 tests, Ruff, and a sample mapping against the committed registry.
- Added a pure reviewed-Cito-link operation that preserves historical UUIDs,
  requires evidence, and rejects unknown or conflicting provider IDs.
- Reviewed Islam Makhachev across live Cito profile and fight-history responses
  and UFCStats profile and UFC 311 fight details. Both providers identify fight
  `daef1691c7d6b1e4` against Renato Moicano on 2025-01-18 with a submission
  in round 1 at 4:05; documented the 0.5-inch reach discrepancy.
- Added `data/mappings/cito_fighter_reviews.json` and the repeatable command
  `python -m upset.data.export_reviewed_cito_links`.
- Added the first reviewed Cito provider link to the existing Islam Makhachev
  UPSET UUID. Audited 4,455 identities unchanged, all historical links
  unchanged, and 4,456 total provider links. Verified the repeat run is
  byte-for-byte identical and 152 automated tests and Ruff pass.
- Added dated pre-fight snapshots from identified fights and fighter-fight
  statistics. Each snapshot includes only earlier event dates, with same-day
  fights excluded from each other's prior history.
- Added repeatable `python -m upset.data.export_prefight` with complete
  participant-stat validation and atomic, verified JSONL publication.
- Verified 160 automated tests and Ruff. The Mac exported 17,102 snapshots
  from 8,551 fights, passed read-back verification, and produced the same
  SHA-256 checksum on a second run. An independent audit checked each row's
  prior fight count against strictly earlier event dates and passed.
- Added initial descriptive pre-fight fighter metrics for striking pace and
  accuracy, takedown pace and accuracy, knockdown and submission-attempt pace,
  and the fraction of prior bouts with observed control time.
- Added `python -m upset.data.export_prefight_features` with strict input
  validation and verified atomic export. The local suite has 176 passing tests
  and Ruff is clean. The Mac exported 17,102 feature rows; a second run had an
  identical checksum. A full-data audit matched every row's keys, date, history
  count, and seven rate calculations to its pre-fight snapshot. A subsequent
  identity/date audit explained the 2,699 zero-prior-fight rows: 2,648 distinct
  UPSET fighter IDs plus 51 additional first-date appearances by 38 IDs.
- Added one historical matchup row per fight with nine A-minus-B pre-fight
  numeric differences, a separate binary training target, and an explicit
  exclusion reason for combined `Draw/NC` source labels.
- Added the repeatable `python -m upset.data.export_matchups` command.
  Verified 187 automated tests and Ruff. The Mac exported 8,551 matchup rows:
  8,400 decisive binary targets and 151 excluded combined `Draw/NC` labels.
  An independent full-data audit checked every bout's participant IDs, event
  date, all nine feature differences, and target against the identified fight
  and both fighter feature rows. A second export had the same SHA-256 checksum:
  `02daa2db24fa80e318ea007127b712e5af1dfa017cf326f7aebbf49c2470146b`.
- Added a fixed first binary prediction baseline with grouped chronological
  splits, training-only median filling and scaling, and a training-prevalence
  comparison. The command reports label balance, feature missingness, and
  metrics by period. The Mac passed 198 tests and Ruff and independently
  audited all 8,551 split rows (8,400 decisive, 151 Draw/NC). Two baseline
  reports matched SHA-256
  `a707b96f68146c3ddde4690b42810587c173c237051d4c8f74af66c40587b1df`.
  The held-out test period (2023-08-26 through 2026-03-07) contained 1,260
  decisive fights. Model accuracy was 0.5198 and ROC AUC was 0.5351; its log
  loss (0.69328) and Brier score (0.25008) were slightly worse than the
  training-prevalence comparison (0.69319 and 0.25002). This is a weak
  historical baseline, not evidence of reliable live prediction.
- Added source audits for potential durability and round-level features. The
  historical audit pairs each bout's identified fighter-stat rows, counts
  recorded opponent knockdowns, and reports all result-method labels without
  guessing finish categories. On the Mac it verified 8,551 fights and 17,102
  participant-stat rows, with 3,655 recorded knockdowns, 3,139 fighter-fight
  appearances with an opponent-recorded knockdown, and 1,536 distinct fighters
  with at least one. Repeated runs produced identical SHA-256
  `d4d5adecd15c2f08aacd38a32f00fdb58eec591688495699fb30cec2aae09556`.
  The Cito probe of the reviewed UFC 311 bout returned HTTP 403 with provider
  code `HISTORY_WINDOW_EXCEEDED`. This confirms the current key cannot read
  that bout's round records. No historical round coverage was established.
  The final Mac check passed 204 tests and Ruff after an import-order fix.
  No model features or scores changed.
- Merged the audit in PR #8 after the Mac passed 204 tests and Ruff at
  `ec580ff`. The Cito historical-access limit is a confirmed source finding.
- Started a separate raw Cito round collector. It accepts explicit bout IDs,
  a local ID list, or the identified fight export, defaults to at most one
  *new* API call per run, and saves only successful nonempty round responses
  under ignored `data/raw/cito_rounds/`. Verified saved files are skipped on
  subsequent runs; malformed data and API errors stop the run. The collector
  includes a small recent-event/bout ID discovery probe. The Mac passed 213
  tests; Ruff found two exception-type issues in the discovery probe, fixed
  on the feature branch pending recheck. The live recent-event request
  succeeded and identified `cryptocom-ufc-331` on 2026-09-19 as a card with
  stats. Event-bout discovery and one real round collection remain untested.
  No round features or historical round coverage have been verified.
- The Mac then passed all 213 tests and Ruff at `d007d46`. A live event-bout
  listing for `cryptocom-ufc-331` returned completed bouts marked with stats.
  One free-plan collector request for `cryptocom-ufc-331-jsonapi-13` saved 10
  round rows; Git remained clean because the raw response is ignored. A local
  field-only audit found Alexandre Pantoja and Joshua Van each have rounds
  1 through 5, with a matching Cito bout ID and the expected raw field names.
  Round numbers and names are confirmed, but numeric normalization and
  reconciliation with bout totals remain pending on the Mac.
- Added an offline round export on the Cito acquisition branch to normalize
  cached records after checking IDs, fighter/round coverage, and strike
  arithmetic. On the Mac at `e5b4788`, 221 tests passed and one cached
  Pantoja–Van bout produced 10 normalized fighter-round rows with read-back
  verification. Ruff reported one `SIM117` style issue in a new test, corrected
  in the next branch commit. Independent bout-total reconciliation remains
  pending. No round-derived model features or revised scores have been
  produced.
- Added a one-bout totals probe on the acquisition branch. It is designed to
  cache the separate Cito `/bouts/{id}/stats` response and print safe field
  names for a later round-to-total audit. The Mac at `8027817` passed 227 tests
  and Ruff. The probe saved a real Pantoja–Van totals response containing
  `availability`, two `boutStats` rows, and ten `roundStats` rows. The raw and
  processed data remain ignored by Git; the working tree is clean.
- Added an offline consistency audit for one Cito bout. It compares the saved
  `/rounds` and `/stats` per-round values, then tests every per-fighter bout
  statistic against the sum of that fighter's rounds. Local synthetic checks
  passed. On the Mac at `a9897b1`, all 232 tests and Ruff passed. The real
  Pantoja–Van audit matched 10 round rows and two fighter fight-total rows
  across 22 numeric fields per fighter; the working tree remained clean.
  Both endpoints belong to Cito, so agreement alone cannot verify accuracy
  against a second provider. Neither historical round coverage nor model
  performance changed.

## Current Data Findings

The current historical dataset contains:

- 4,455 fighter-profile rows
- 4,448 unique fighter names
- 8,551 fight rows
- 2,647 distinct fighter-name labels in the fight table (earlier name-based audit)
- 2,648 distinct UPSET fighter IDs appearing in identified historical fights
- 1,801 fighter names present only in the profile table
- Historical fight coverage from 1994-03-11 through 2026-03-07
- All 17,102 fight-participant slots are linked to same-source fighter profiles
- 46 ambiguous slots required reviewed overrides; zero slots remain unresolved

Known data-quality concerns include:

- Reach is missing for approximately 43.5% of fighter profiles
- Stance is missing for approximately 19.1%
- DOB is missing for approximately 11.4%
- Some career-statistic zeros may represent unavailable data rather than legitimate zero values
- Control-time values appear structurally unavailable for early UFC events
- Fighter names are not globally unique
- The fight dataset contains fight-level totals rather than true round-level rows
- The historical dataset is already several months behind current UFC events

## Current Task

The accepted historical snapshot, identity linking, dated pre-fight totals,
original matchup export and first baseline were verified on the Mac. The
original test result remains 655 correct out of 1,260 decisive bouts
(51.98%). Its probabilities were slightly worse than a constant
training-prevalence comparison by log loss and Brier score. The already
examined original test period has **not** been rerun with new features.

Cito collection, round normalization and one Pantoja–Van totals reconciliation
are merged. Ten round rows and two fight-total rows agreed on 22 numeric fields
per fighter in that sample; broader historical round access and mapping
remain unverified. The provider's September 16 email supports one paid month
of historical acquisition and local retention. An actual paid historical
request has not been established. Do not treat round data as model inputs yet.

A separate frozen development evaluation and dated defensive-history export
have now run against the Mac's ignored historical data. The 8,551 matchups
produced 1,892 development validation rows (1,857 decisive, 35 combined
`Draw/NC`), and the defensive export produced 17,102 fighter rows. The
original nine-feature baseline's fold accuracies ranged from 51.72% to 54.12%.
At branch commit `3af4212`, the Mac passed 245 tests and Ruff and ran a
same-bout defensive comparison. Both models used the same 1,857 decisive
validation fights, with 35 combined `Draw/NC` exclusions. Accuracy improved
from 53.04% (985 correct) to 57.46% (1,067 correct), a 4.42-point gain.
Log loss improved from 0.69062 to 0.68159; accuracy and log loss improved in
all four calendar folds. A date-cluster bootstrap for the paired accuracy
difference gave an approximate 95% interval of +1.75 to +6.86 points.
These are development results, not a new unbiased test or live accuracy.
Repeated fighters, the later historical snapshot and model selection still
limit uncertainty claims. The Mac at `ef2e3af` passed 246 tests and Ruff;
the independent audit matched all 17,102 defensive row identities, dates and
strictly earlier fight counts. Its 44 independently recalculated sampled rows
across 41 fighters all matched. PR #10 was merged into `main`.
See `docs/EVALUATION_CONTRACT.md`.

The first exploratory defensive group run kept 1,857 decisive validation
bouts and 35 Draw/NC exclusions. Adding only striking to the nine-feature
baseline reached 1,029 correct (55.41%); adding only finish losses reached
1,007 (54.23%). Full defense remained 1,067 (57.46%). Dropping grappling
from full defense left accuracy unchanged at 1,067 and slightly improved
log loss (0.68159 to 0.68138). Dropping knockdowns raised accuracy to
1,077 (58.00%) but worsened log loss to 0.68235. These are exploratory
same-fold results and do not establish the best model for future fights.
The Mac passed 249 tests. Ruff found one test import-order error, corrected
on the diagnostic branch. The Mac then reran Ruff, all 249 tests, and the
diagnostic at `228a8ba`, confirming the accepted input hashes and a clean
working tree. Striking alone improved correct-bout counts in all four folds;
other group effects varied by year. In 2022, removing striking from full
defense improved accuracy by 11 bouts, illustrating correlated feature effects.
PR #11 was merged into `main` after the Mac verification. The Mac synced
`main` to merge commit `e8a0d08` with a clean working tree.

The outcome/activity candidate ran on the Mac at `7f4cde9`. Ruff and all 257
tests passed; 17,102 dated history rows exported and independently matched
earlier identified fights. The matchups and defensive source hashes matched
the accepted exports, 1,857 decisive validation bouts and 35 Draw/NC rows
remained, and the branch was clean. Adding four outcome/activity differences
to the original baseline gave 1,055 correct (56.81%), versus 985 (53.04%)
for the baseline. Adding them to full defense gave 1,053 correct (56.70%),
versus 1,067 (57.46%) for full defense alone. The latter combination slightly
improved log loss (0.68159 to 0.68083), but lost 20 correct bouts in partial
2023 even as it gained eight in 2022. These are already examined development
folds; no model has been promoted. See `docs/EVALUATION_CONTRACT.md` for the
definition, per-fold counts and study limits.

PR #12 merged the audited outcome/activity experiment into `main` at
`3385ebb`. PR #13 merged the prospective archive prototype at `3d2af42`
after the Mac passed Ruff and all 260 tests on `6246578`, with a clean
working tree. The three reported datetime style errors were corrected before
that final check.

The archive records supplied pre-event forecasts with schedule evidence,
model bytes/specification, feature inputs, reviewed fighter links, hashes and
a local UTC timestamp. It has not generated or archived a real prospective
prediction. Current fight/stat coverage, reviewed provider links, a trained
and replay-verified model, an external pre-event timestamp and later outcome
scoring remain necessary. See `docs/PROSPECTIVE_EVALUATION.md`.

Ayaan requested a pause after this milestone, then a full handoff and a deeper
modeling plan. The September 24 review found that recent performance weighting,
opponent ratings, actual control dominance, target/position style features,
physical matchup features and boosted trees remain unimplemented. These are
specific research opportunities; the current scores do not establish a
performance ceiling or a path guaranteed to reach 75%. No paid Cito purchase
or new modeling run occurred during the review.

See `docs/MODELING_RESEARCH_PLAN.md` for the feature inventory, bounded
experiment order, Cito purchase pilot and evaluation requirements. This plan
supersedes the earlier ordering of proposed next steps; it does not change
the preserved experiment definitions or claim any new score.

## Recommended Next Steps

The Mac completed the first Elo/boosted-tree run at `ddba4ab`: 17,102 rating
rows independently replayed and matched, 1,857 decisive development bouts,
35 Draw/NC exclusions, and saved reference probabilities preserved. Adding
Elo to defense achieved 1,073 correct (57.78%) versus full defense's 1,067 (57.46%).
Its six-pick gain was uneven by fold (-12, +4, +23, -9), and the paired
accuracy interval was [-1.51, +2.15] percentage points. Boosted defense + Elo
had the lowest pooled log loss/Brier (0.674022/0.240889) but seven fewer
correct picks than full defense (1,060; 57.08%). No model was promoted.
The existing exploratory 58.00% accuracy result was not exceeded. See
`docs/ELO_EXPERIMENT.md` for the full printed score ledger. The supplied
manifest and predictions passed a matching SHA-256 check and cover all 1,892
validation bouts. The symmetry diagnostic found that swapping fighter order
changes the selected winner on 164/1,857 defense + Elo predictions and
418/1,857 boosted defense + Elo predictions. The existing canonical
UUID orientation makes the historical experiment reproducible, but these
fitted models need an order-consistent procedure before use in a public
matchup interface. Direct Elo has no conflicting picks after excluding
exact 0.5 ties. Mac Ruff passed and the complete terminal log confirms
288 pytest tests passed in 14.12s. The assistant environment separately
passed 288 tests and 16 subtests. PR #15 is draft for research review.

The next requested implementation is complete on `feature/symmetric-recent-form`:
a separate, independently audited 365-day weighted-performance export, fixed
earlier-population shrinkage, actual paired control margin, mirrored training
with half weight per orientation, and complementary inference. Six new
logistic/boosted candidates isolate symmetry, Elo and recent performance;
all six old forward/reverse prediction series are preserved. The source
statistics must also reproduce the accepted matchup/defense features. The
assistant environment passed Ruff and 313 tests plus 16 subtests. See
`docs/RECENT_FORM_EXPERIMENT.md` for the fixed design, Mac results and
interpretation.
The first Mac run at `3cb9f18` passed Ruff but hit the same boosted-training
error in five pytest cases (308 passed; two failed; three setup errors) with
scikit-learn 1.9.1. It never reached the export or comparison. A follow-up
restricts boosting to columns actually observed in the fold's training rows.
On the Mac at `4bc2941`, Ruff and all 313 tests passed. The Mac exported and
independently audited all 17,102 recent rows, with strictly earlier
population priors and all numeric fields recomputed. The comparison covered
1,857 decisive bouts plus 35 Draw/NC exclusions and exactly preserved the
six saved reference probability series.

The symmetric logistic defense + Elo + recent candidate has the lowest pooled
log loss/Brier: **0.666020/0.236867**, versus symmetric defense + Elo's
0.677363/0.241769. Its matched paired log-loss difference is -0.011342,
with a date-bootstrap 95% interval [-0.019443, -0.003091]. This direction
holds in all four development windows. Correct picks are 1,071/1,857
(57.67%), versus the matched model's 1,075 (57.89%) and saved full defense's
1,067 (57.46%). Paired accuracy intervals include zero. All six new variants
have zero final fighter-swap probability error and no conflicting picks.
These are repeatedly examined development folds; intervals are unadjusted
for multiple comparisons. No model was promoted. The newly uploaded manifest
and all 1,892 predictions were inspected: saved prediction/reference hashes
and all six original probability series match, and all 47 score sets across
12 variants plus the paired bootstrap reproduce from the rows. Recent logistic
AUC is 0.628908 versus its comparator's 0.605321; log-loss gains hold across
both history and both experience groups, with 42 double-debut bouts yielding
exact 0.5 ties. The ten-bin calibration error is worse (0.0352 versus 0.0074),
despite lower log loss and Brier. The source-replay audit is reported as passed
in the Mac manifest; the original historical files were not uploaded for an
independent source replay in this environment. The manifest counts 1,279
source bouts after the August 19, 2023 development end date. Freeze any
candidate and calibration policy before scoring later-date fights.

1. Review PR #15 as a documented experiment with completed Mac checks. Its
   historical score must not be treated as a validated order-independent
   matchup model.
2. Inspect the saved `recent_form_v1` manifest and row-level predictions for
   reliability, history/missingness/division slices and hashes. Preserve the
   exact research snapshot, then evaluate genuinely later bouts before any
   model selection or release. Keep log loss and accuracy visible separately.
3. Continue with available physical context and matchup interactions after
   the temporal and symmetry checks; measure each family.
4. If Ayaan buys Cito Pro, first validate a limited historical coverage pilot
   and the account's actual archive entitlement. The September 16 provider
   email already supports one-month acquisition and local retention; pricing
   and terms still disagree on the public historical window.
5. Repair the completed-fight/stat gap after March 2026 and review provider
   identities. Establish timestamped odds coverage for a separate market
   benchmark and optional market-assisted candidate.
6. Freeze a model release, verify probability replay, capture externally dated
   prospective forecasts, then score outcomes separately. No new model was
   promoted by the handoff review.

## Blockers

The historical snapshot ends on 2026-03-07. Complete reviewed current data,
a serialized/replay-verified model and actual pre-event evidence are absent.
Historical Cito round access and timestamped odds coverage have not been
established on the user's account. These block live-performance claims;
opponent-strength and recent-performance research can proceed with existing
historical files.
