# UPSET Project Status

**Last updated:** September 22, 2026

**Current phase:** Phase 1 — Data Foundation

**Current development day:** Day 3/4

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
- Confirmed all 2,647 unique fighters appearing in fight rows have a matching fighter-profile name
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
  count, and seven rate calculations to its pre-fight snapshot. It found 2,699
  rows with zero earlier fights.

## Current Data Findings

The current historical dataset contains:

- 4,455 fighter-profile rows
- 4,448 unique fighter names
- 8,551 fight rows
- 2,647 unique fighters appearing in the fight table
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

The dated pre-fight snapshot and initial descriptive feature exports have both
been verified on the full 8,551-fight history on the Mac. They produce 17,102
fighter rows each. Both stages read only prior fight statistics. The raw
historical dataset remains uncommitted to GitHub.

The first reviewed cross-provider fighter link is merged into `main`. The
registry still contains 4,455 permanent identities; Islam Makhachev's existing
UPSET UUID has both a UFCStats link and one reviewed Cito link.

## Next Steps

1. Extend outcome handling when a source can distinguish scheduled, cancelled,
   drawn, and no-contest fights.

2. Extend the feature set for durability, recent form, and strength of
   schedule after reviewing which history and outcome fields reliably support
   them. Define training targets and matchup rows without using future data.

3. Train and evaluate a baseline model with chronological data splits and a
   documented policy for ambiguous outcomes.

4. Revisit UFCalendar before implementing automated current-data updates for
   the public application.

## Blockers

No major blockers.

Known data-quality issues are being documented and will be handled through normalization and validation rather than by modifying raw source files.
