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
