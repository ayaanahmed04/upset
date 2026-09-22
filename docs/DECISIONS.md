# UPSET Project Decisions

This document records important project decisions and the reasoning behind them.

## 001 — UFC-only for Version 1

UPSET will focus exclusively on UFC data during its first version.

Reason:

Limiting the initial scope makes the data model, analytics, and machine learning work manageable. The architecture may later support additional promotions and sports.

## 002 — Analytics First

UPSET will be presented primarily as an MMA analytics and research platform, not as a betting-picks product.

Reason:

Fight probabilities and betting-related analysis may eventually be useful features, but the broader analytics positioning better represents the product and the technical work behind it.

## 003 — Data Science and Machine Learning Focus

The project's primary technical focus is data science and machine learning while maintaining professional software engineering practices.

Reason:

UPSET should demonstrate ML and analytics ability while also showing that models can be incorporated into a real software product.

## 004 — Python 3.12

UPSET will use Python 3.12 for its data science, machine learning, and backend Python components.

Reason:

Python 3.12 is modern, supported, and has strong compatibility with the Python data science ecosystem.

## 005 — Private Repository During Initial Setup

The GitHub repository will remain private during the early foundation stage and will become public once the project has a presentable technical baseline.

Reason:

This allows data licensing, repository structure, secrets management, and initial engineering practices to be established before public release.

## 006 — Provider-Independent Data Model

UPSET will maintain its own normalized internal data model rather than coupling analytics and machine-learning code directly to one external provider's schema.

Reason:

Historical datasets, APIs, and future commercial providers may use different field names, identifiers, and structures. Normalizing them into UPSET-owned entities such as Fighter, Fight, Event, and RoundStats will allow data providers to be replaced or combined without requiring major changes to the analytics and machine-learning layers.

## 007 — Raw Data Is Immutable

Files stored in `data/raw/` will not be manually cleaned, edited, or corrected.

Reason:

Raw source files should remain reproducible representations of the data as acquired. Missing-value corrections, normalization, type conversion, identity reconciliation, and other transformations will occur in code and produce separate processed datasets.

## 008 — Fighter Names Are Not Unique Identifiers

UPSET will not use fighter names as permanent primary keys.

Reason:

The initial UFC dataset contains multiple distinct fighters who share the same name. These fighters have different source profiles and identities. UPSET will eventually use its own internal fighter identifier and maintain source-specific identifiers for reconciliation across data providers.

## 009 — Initial Historical Development Dataset

The José Silva UFC historical Kaggle dataset will be used as UPSET's initial historical development dataset.

Reason:

The dataset provides broad UFC fight coverage, fighter profiles, outcome data, and fight-level statistics suitable for exploratory analysis, feature engineering, historical backtesting, and baseline machine-learning development.

It is treated as a frozen historical snapshot rather than a live production source. Known limitations such as missing fighter attributes, structurally unavailable early control-time data, fighter-name collisions, and the absence of true round-level rows will be handled through validation and normalization rather than by modifying the raw files.

## 010 — Cito as an Experimental Current and Round-Stats Provider

Cito will be used during the data-foundation phase for API experimentation, current UFC data, provider-ID exploration, and round-level statistics.

Reason:

Initial testing confirmed that Cito provides structured fighter, event, bout, and true round-level data. Its schema provides useful source identifiers and fills gaps that the historical Kaggle dataset cannot cover.

UPSET will not couple its analytics or machine-learning layers directly to Cito. Cito data will pass through UPSET's provider-independent normalization layer, and important values will continue to be validated because structured API data can still contain inconsistencies.

## 011 — Canonical Core Data Entities

UPSET's provider-independent data model will be organized around five core entities:

- `Fighter`
- `Event`
- `Fight`
- `RoundStats`
- `FightStats`

Reason:

External providers use different schemas, identifiers, field names, and levels of statistical detail. UPSET-owned canonical entities provide a stable internal contract so analytics and machine-learning code do not depend directly on any one provider.

Provider-specific data will be transformed through normalization functions before entering these canonical representations.

## 012 — Separate Fighter Identity From Time-Varying Career Statistics

The canonical `Fighter` model will primarily represent fighter identity and relatively stable profile information. Time-dependent career statistics such as wins, losses, striking rates, takedown rates, and other cumulative metrics will not be treated as permanent fighter identity fields.

Reason:

Career statistics change over time. Combining current career aggregates directly with historical fight records could introduce future information into historical machine-learning features.

UPSET will later represent time-dependent fighter statistics using dated or pre-fight snapshots so historical models only use information that was available at the time of a fight.

## 013 — Preserve Ambiguous Historical Outcomes

The historical Kaggle snapshot uses the combined Winner label "Draw/NC"
for 151 fights. UPSET will preserve that label in source_winner_label
and set winner_name to None.

We will not infer a specific draw or no-contest outcome from the method
alone. These records remain in the historical dataset. Any exclusion
from binary win/loss model training will happen explicitly later.

Historical normalization also preserves Event_Date and Fight_URL.
Unavailable fighter IDs and event IDs remain unset rather than being
invented or assigned through ambiguous name matching.

## 014 — Repeatable Historical Fight Export Using JSON Lines

Normalized historical fights are saved as JSON Lines: one fight per line.
This format preserves explicit null values and string identifiers and
requires no additional Python dependencies.

The export reuses normalize_kaggle_fight() rather than duplicating its
conversion rules. Invalid records, duplicate fight IDs, and empty input
prevent export.

Output is written to a temporary file and read back for comparison with
the normalized records before replacing the final processed file.

Raw source data remains unchanged. Raw and processed datasets stay
ignored by Git; the conversion code and tests are version-controlled.

Run from the project root:

python -m upset.data.export_historical

Output:

data/processed/kaggle_ufc_1994_2026/fights.jsonl

## 015 — Historical Fighter Profiles and Source-Reported Measurements

Historical fighter profiles use the identifier extracted from Fighter_URL.
Names are retained as labels, not unique identifiers. Profiles with matching
names and different source IDs remain separate records.

Missing measurements, stance, and birth date remain None. Unavailable
source slugs remain None. Birth dates and source URLs are preserved.

Height is converted to inches, weight to pounds, and reach to inches.
These are source-reported profile measurements, not measurements tied to
a particular fight. Extreme values are investigated rather than
automatically deleted or replaced with guesses.

Current career aggregates are not copied into Fighter. All 4,455 profiles
are retained, including profiles without a matching fight in the snapshot.

Profiles are exported separately as JSON Lines using:

python -m upset.data.export_profiles

Fight-to-profile linking remains a separate task. Name collisions must
be explicitly resolved or flagged.

## 016 — Evidence-Backed Historical Fighter Identity Linking

Historical fight participants are linked to same-source fighter profiles using
source-specific profile IDs. A unique name match may be linked automatically,
but an ambiguous name requires an explicit reviewed override.

Each override is keyed by source, bout ID, and fighter side. It also records
the fighter name, event date, opponent, selected source fighter ID, evidence,
and review date. The version-controlled mapping is stored at:

data/mappings/kaggle_fighter_overrides.json

The linker validates the mapping against the fight and profile records and
fails when a participant is missing or ambiguous without an override. It also
rejects duplicate profiles, fights, or overrides; inconsistent evidence
fields; invalid candidate IDs; conflicting existing links; the same profile
on both sides of a fight; and unused overrides.

Reason:

Names are useful matching labels but are not identities. Requiring reviewed,
auditable exceptions for collisions makes historical linking deterministic
and prevents silent guesses.

For the accepted historical snapshot, 17,056 of 17,102 participant slots had
one profile candidate. The remaining 46 slots, covering five collided names,
were resolved from UFCStats profile histories by matching event date and
opponent. All 8,551 fights now have two linked participants and zero unresolved
slots.

The resulting IDs remain provider-specific source IDs. Permanent UPSET fighter
identities are attached in a later export using the reviewed registry.

Run the linked export from the project root:

python -m upset.data.export_linked

Output:

data/processed/kaggle_ufc_1994_2026/fights_linked.jsonl

## 017 — Historical Fight Statistics Use Fighter-by-Fight Grain

Historical fight statistics will use one canonical `FightStats` record for one
fighter across one complete fight.

Reason:

The accepted historical source stores both participants' totals in one row
using `F1_` and `F2_` columns. Splitting that row into two records gives each
performance a stable fighter ID and a consistent set of field names. This
supports fighter-history analysis and later pre-fight feature construction
without depending on participant side or fighter name.

Historical `FightStats` remains distinct from Cito `RoundStats`.
`FightStats` represents one fighter's totals across the complete fight, while
`RoundStats` represents one fighter in one round. The two grains must not be
combined or counted as though they represent the same records.

## 018 — Pre-UFC-21 Zero Control Time Is Missing

A historical zero control-time value before UFC 21 on 1999-07-16 will be
normalized to `None`.

Reason:

Every audited fight before UFC 21 reports zero control for both participants,
while all eight UFC 21 fights contain a control-time signal. This is strong
evidence of a source-coverage boundary rather than hundreds of confirmed
zero-control performances.

A nonzero value before the boundary would still be preserved. On and after the
boundary, zero remains zero because it can represent a real recorded result.
The immutable raw CSV retains its original values; the missingness rule is
applied only in normalized processed data.

## 019 — UPSET-Owned Fighter Identities Use Permanent UUID4 Values

Each real-world fighter receives one permanent UPSET-owned UUID4 identifier.

The identity is stored separately from provider-specific profiles:

- `FighterIdentity` stores the permanent `upset_fighter_id` and current
  `display_name`.
- `FighterProviderLink` connects one provider profile to an UPSET identity and
  records evidence for that connection.

Display names are labels rather than identity keys. A display name may be
intentionally replaced while the fighter keeps the same UPSET UUID. Different
fighters may also share the same display name.

Each `(provider, provider_fighter_id)` pair may link to only one UPSET identity.
Multiple provider profiles, such as UFCStats and Cito profiles, may eventually
link to the same identity when sufficient evidence exists.

Reason:

Provider identifiers belong to external systems and names are neither unique
nor permanent. UPSET needs an identifier that survives name corrections,
display-name changes, and the addition or replacement of data providers.

The version-controlled registry is stored at:

`data/mappings/fighter_registry.json`

The initial registry contains 4,455 permanent UPSET identities and 4,455
UFCStats provider links. It preserves all seven duplicate-name groups as
separate people.

The repeatable registry export is:

`python -m upset.data.export_identity_registry`

On later runs, existing UUIDs are preserved and UUIDs are generated only for
previously unseen UFCStats fighter IDs. The registry is validated, written
through a temporary file, and verified by reading it back before replacement.

## 020 — Attach Historical Identities After Source Linking

Historical source exports remain the input contracts for normalization and
source-level linking. A separate identified export reads the linked fights,
profiles, fighter-fight statistics, and permanent fighter registry. It adds
required UPSET UUIDs to three new JSONL files while retaining the original
provider IDs and source fields.

The historical dataset source is `kaggle_ufc_1994_2026`; its fighter IDs were
extracted from UFCStats URLs. Registry lookups therefore use the `ufcstats`
provider key. Fighter names and Cito IDs are never used for those lookups.

The identified export rejects unresolved IDs, duplicate source records,
participants without profiles, missing or extra fighter-fight statistics, and
fights that resolve both participants to one UPSET identity. It verifies all
three files before replacing the output files. It only reads the registry and
never generates or modifies permanent fighter IDs.

## 021 — Cross-Provider Fighter Links Require Review

A reviewed Cito fighter ID may be attached to an existing UFCStats identity
through `add_reviewed_cito_link`. The caller supplies both provider IDs and a
description of the evidence used to confirm they refer to the same person.
The function resolves the UFCStats ID through the existing registry, preserves
its UPSET UUID, and returns a new registry containing a Cito provider link.

The function rejects unknown UFCStats IDs, conflicting Cito assignments, and
attempts to silently change the evidence for an existing link. Repeating the
same reviewed assignment returns the existing registry. Names remain display
labels; they are never sufficient evidence for a cross-provider match.

The first reviewed mapping is Islam Makhachev. A fresh Cito profile supplied
fighter ID `2df4f188-a33e-463a-a66b-471cfa23e2a0`. Cito's fight history
and UFCStats both identify his January 18, 2025 UFC 311 win over Renato
Moicano as fight `daef1691c7d6b1e4`, by submission in round 1 at 4:05.
The 0.5-inch reach discrepancy is recorded in the evidence.

The reviewed pair and its source links are committed in
`data/mappings/cito_fighter_reviews.json`. Run
`python -m upset.data.export_reviewed_cito_links` to apply all reviewed pairs
to `fighter_registry.json`. The exporter reads and validates the entire review
document before saving through the registry's verified temporary-file path.
It preserves existing UUIDs and provider links; rerunning with the same
reviews makes no changes.

## 022 — Pre-Fight Statistics Use Strictly Earlier Event Dates

Historical pre-fight snapshots use the identified fight and fighter-fight
statistics exports. Each `(source_bout_id, upset_fighter_id)` gets one record
containing that fighter's cumulative fight counts and observed totals from
events dated strictly before the target fight. All fights on the same calendar
day receive snapshots before any result from that day enters the history.

Reason:

The historical snapshot has event dates but no trusted ordering within a day.
Using a same-day fight's statistics could leak information from a fight that
had not happened yet. Zero prior fights produce zero count totals; control
time is `null` until at least one earlier fight recorded that statistic.
Observed zero control is distinct from missing control. Source-reported
career aggregates, unknown win/draw distinctions, and per-round Cito records
are not inputs to this initial history export.

The repeatable exporter validates complete fighter-to-fight-stat matches and
publishes a verified JSONL file only after all input rows pass validation:

`python -m upset.data.export_prefight`

## 023 — Pre-Fight Rates Preserve Unknown Denominators

The first fighter feature layer transforms only saved pre-fight snapshot totals
into striking and grappling rates. Fight duration is the denominator for pace;
attempt counts are the denominator for success fractions. A zero denominator
produces `null`, not zero. The feature row also carries prior fight count and
total prior fight seconds so small histories remain visible.

Control-time coverage is reported as the fraction of prior fights with an
observed control value. No control-time pace is calculated: the snapshot
stores all prior fight seconds, but not seconds limited to bouts with observed
control. Dividing observed control by all fight time would systematically
understate older fighters' rates where the source did not record control.

These are descriptive features, not predictions or model targets. Outcomes,
defensive performance, recent form, and matchup differences need separate
reviewed contracts. No source's current career statistics enter this layer.

Run `python -m upset.data.export_prefight_features` after the snapshot export.
