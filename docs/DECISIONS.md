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

UPSET's provider-independent data model will be organized around four core entities:

- `Fighter`
- `Event`
- `Fight`
- `RoundStats`

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
