# UPSET Project Status

**Last updated:** September 18, 2026

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

Cito fighter, event, fight, and round-stat normalization functions now exist.

Fight normalization and event linking have been checked using one sampled
Cito bout. Automated tests cover field mapping, fighter ordering, missing
values, invalid participant counts, an unmatched winner, and event matching.

Next, verify connections between normalized fights, fighter profiles, and
round-stat records using provider identifiers.

## Next Steps

1. Document the verified Cito bout-field mapping and known limitations,
   including fighter profile IDs versus participation-record IDs,
   event slugs versus event IDs, and missing winner information.

2. Verify connections between normalized fights and fighter profiles
   using Cito fighter IDs, and connect round-stat records using bout IDs
   and fighter slugs.

3. Define how UPSET represents scheduled, cancelled, drawn, and
   no-contest fights so a missing winner is not treated as a complete
   description of the outcome.

4. Design UPSET-owned internal IDs and mappings to provider identifiers.
   Resolve fighter-name collisions without assuming names are unique.

5. Map the historical Kaggle fight records into the canonical Fight
   representation, documenting unavailable fields and identity-linking
   limitations.

6. Define how historical fight-level statistics coexist with Cito
   round-level statistics without double-counting the same fight.

7. Build an initial processed historical dataset with source tracking
   and data-quality checks. Preserve raw files and handle structurally
   unavailable early control time as missing rather than genuine zero.

8. Define dated or pre-fight fighter-stat snapshots. Treat current
   career totals, division, weight, and champion status as potentially
   time-dependent rather than historical facts.

9. Build initial pre-fight features using only information available
   before each fight, and verify that future information cannot leak
   into those features.

10. Train and evaluate a simple baseline model using chronological
    training and evaluation splits.

11. Revisit UFCalendar as a possible current-data provider before
    building automated updates for the public application.

## Blockers

No major blockers.

Known data-quality issues are being documented and will be handled through normalization and validation rather than by modifying raw source files.
