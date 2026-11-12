# Frozen baseline and future-only evaluator — October 26, 2026

**Implemented, frozen and verified; future evaluation is pending.** The
opponent pilot did not justify a larger backfill, so this milestone protects
the retained reference from further tuning on repeatedly inspected years.
No new model was fitted or released.

The fixed block is October 27, 2026 inclusive through October 27, 2027 exclusive.
The freeze was created at 17:56:11 UTC on October 26, before that block opened.
Its seed contains 17,708 sides through October 24 from the existing serving
snapshot, excluding dates on/after October 26. Today's checked status has zero
future sides and no computed scores. This is not a validation pass.

## What is fixed

The candidate remains the earlier global-mean shrink25 estimate, with fixed
beta-binomial bout concentration 5. References are raw career, raw last-five
and the same global25 mean under a binomial count law. The code predicts all
sides on a date before updating any history from that date. Counts are
conditional on actual opposing attempts; no opportunity forecast, opponent
adjustment, latent skill interval or winner probability is produced.

The freeze binds source dependencies, configuration, protocol, installed
versions, input hashes and an exact seed copy. A separate archive retains
copies of all 11 frozen source/protocol dependencies. Current frozen files
must stay unchanged for this evaluator; modifying one causes verification to
refuse. New development must use distinct files/artifacts rather than silently
changing this experiment.

The future adapter may have a new serving-database hash, but must preserve all
seed measurements, identities, dates and provenance. Added old-history or gap-day
records, revised counts, deletions, duplicates and broken pairs are rejected.
This freezes a known research cohort, not a claim that its historical coverage
is complete; the previously excluded bouts remain outside it.

Finalization refuses before October 27, 2027 UTC, before reading future outcome
rows. At the end it additionally requires a full-block adapter and a saved
completeness review tied to that adapter's exact hash, with zero unresolved
eligible bouts and a reviewer/evidence note. Hash preservation cannot establish
that every future bout was acquired. No real completeness attestation has been
invented, and no data acquisition or automation has been scheduled.

## Interpretation remains conservative

The full [prospective protocol](TAKEDOWN_DEFENSE_PROSPECTIVE_PROTOCOL_V1.md)
fixes support, proper scores, calibration, paired date/fighter dependence checks
and subgroup rules. Overall interpretation requires 500 primary sides / 20
dates; subgroup interpretation requires 100 sides / 20 dates. A thin high-attempt
group blocks a pass. If the fixed one-year block is too small, the result is
inconclusive; its dates will not be extended after inspecting results.

Even passing these future baseline checks cannot release a skill rating.
Reliability thresholds, skill intervals, opponent adjustment and the displayed
window estimator remain separate uncompleted requirements. public_release is
always false in this evaluator. Rankings remain removed and the website stays raw.

## Verification and artifacts

111 relevant tests passed, including 22 new tests for pre-block freezing,
early-scoring refusal, unchanged histories, source/config tampering, date
batching, zero-attempt handling, completeness review and synthetic end-to-end
finalization. Ruff and `git diff --check` passed. Numerical/reference and
preservation checks are saved in
`data/processed/td_defense_prospective_verification_2026_10_26.json`.

- Code: `src/upset/skill/defense_prospective.py`.
- Freeze: `data/processed/td_defense_prospective_freeze_2026_10_26_v1/`.
- Source copies: `data/processed/td_defense_prospective_sources_2026_10_26_v1/`.
- Today's status: `data/processed/td_defense_prospective_status_2026_10_26_v1/status.json`.

Read status with the existing or a newly reviewed adapter:

```bash
cd ~/Projects/upset
source .venv/bin/activate
python -m upset.skill.defense_prospective status \
  --freeze data/processed/td_defense_prospective_freeze_2026_10_26_v1 \
  --adapter data/processed/td_defense_adapter_2026_10_26_v1
```

When the block has closed, the separate `finalize` subcommand takes `--freeze`,
`--adapter`, `--attestation` and a new `--output` directory. It deliberately
cannot run now. No future evidence exists in the current snapshot. Existing
files, serving database, site and prior study artifacts were preserved; no
package installation, server restart, commit or push was performed.
