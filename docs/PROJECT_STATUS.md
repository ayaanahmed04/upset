# UPSET Project Status

**Last updated:** September 21, 2026

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
- Provider-independent internal data model planned
- Raw source data remains immutable
- Fighter names will not be used as permanent unique identifiers
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
- Established the four core UPSET canonical entities: `Fighter`, `Event`, `Fight`, and `RoundStats`
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

## Current Data Findings

The current historical dataset contains:

- 4,455 fighter-profile rows
- 4,448 unique fighter names
- 8,551 fight rows
- 2,647 unique fighters appearing in the fight table
- 1,801 fighter names present only in the profile table
- Historical fight coverage from 1994-03-11 through 2026-03-07

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

Historical fight identity and result export is implemented. The repeatable
command reads the raw CSV, validates and normalizes its records, and saves
8,551 fights as JSON Lines under data/processed/.

The saved data was read back and matched the normalized records exactly.
All 36 automated tests passed. Raw and processed datasets remain ignored
by Git; the code needed to rebuild the export is version-controlled.

Historical fighter profiles and fight-level statistics have not yet been
normalized. Field-mapping documentation remains outstanding.

Next, document the existing mappings and export workflow, then inspect
historical fighter-profile fields before implementing their normalization.

## Next Steps

1. Document the verified Cito and Kaggle field mappings, identifier
   differences, and known limitations, including the combined Draw/NC
   label and unavailable historical fighter and event IDs.

2. Document the historical export command, JSON Lines output, validation
   behavior, and requirement to run from the project root.

3. Normalize the historical fighter-profile dataset. Preserve source
   profile identifiers and keep current career statistics separate
   from fighter identity information.

4. Design UPSET-owned internal IDs and provider-ID mappings. Connect
   historical fights to fighter profiles while explicitly flagging
   ambiguous name matches instead of guessing.

5. Define and normalize historical fight-level statistics alongside
   Cito round-level statistics. Keep their levels of detail distinct
   and prevent double-counting.

6. Apply and document the working rule for structurally unavailable
   early control time in processed statistics. Preserve raw data and
   distinguish missing values from genuine zeros.

7. Extend outcome handling to distinguish scheduled, cancelled, drawn,
   and no-contest fights when the source supports that distinction.
   Preserve ambiguity when it does not.

8. Build dated or pre-fight fighter-stat snapshots. Do not treat
   current career totals, division, weight, or champion status as
   historical facts.

9. Create initial pre-fight features using only information available
   before each fight, with explicit checks against future-data leakage.

10. Train and evaluate a simple baseline model using chronological
    training and evaluation splits and a documented policy for
    ambiguous outcomes and unresolved fighter identities.

11. Revisit UFCalendar before implementing automated current-data
    updates for the public application.

## Blockers

No major blockers.

Known data-quality issues are being documented and will be handled through normalization and validation rather than by modifying raw source files.
