# Ranking removal and first defense prototype, October 26, 2026

## Site change

Removed the leaderboard page, its clickable percentile links, percentile badges,
percentile bars, the sample-adjusted ranking backend, and `/api/rankings`.
The two leaderboard JS/CSS files were deleted after backup. Both broadcast and
the optional editorial design now show recorded values with their units.
Fighter records, histories, comparison values, strike maps, portraits, titles,
cutoffs, windows, and the featured Moicano/Nolan matchup remain available.
No replacement ranking or adjusted statistic is displayed.

Backup: `backups/remove-rankings-20261026-154107-095200` contains the original
files and pre-change Git diff. The existing viewer was restarted with the same
October 24 database, broadcast mode, roster, and port 8767. Its command/log are
in this backup. The fighter page was reloaded and visually checked without
ranking controls. The removed API is covered by regression tests.

## Offline dataset

`src/upset/skill/takedown_defense.py` exports a read-only, manifest-verified
adapter to `data/processed/td_defense_adapter_2026_10_26_v1`.

- 8,854 accepted fights, 17,708 paired fighter-side observations, strictly before October 26.
- 11,536 observations with positive opposing takedown attempts.
- 6,172 zero-attempt observations: observed defense stays unavailable, not 100%.
- No missing or invalid takedown counts in these accepted serving rows. This is an audit of the accepted canonical rows, not a new validation of every original historical source measurement.
- 522 rows have unknown/nonstandard divisions; their prior baseline falls back to earlier all-division data.
- Opponent counts define the denominator; no positional-time estimate is used.
- Permanent IDs, event IDs/date grouping, source/provider IDs, URLs, database hash, and source-row hashes are retained.

Original serving database SHA-256 remains
`5f33dfb636701bf1126e7bd5fee1539173bc2009219db27c4d393055b6bdc9bd`.
The dataset and original local files are preserved.

## Prototype and development result

The protocol in `docs/TAKEDOWN_DEFENSE_PROTOCOL_V1.md` was written before the
first evaluation. `src/upset/skill/shrink_defense.py` implements that protocol.
Predictions for an entire date are produced before any outcomes from that date
update histories or population baselines. Raw last-five uses five recorded
bouts, including zero-attempt bouts; it does not quietly search farther back
for five fights with attempts.

Tuning on 2012-2018 selected 25 prior attempts from {5, 10, 25, 50, 100}.
That strength was then frozen for 2019+ development evaluation. The population
baseline and individual histories update only with earlier dates.

| Common-support development cohort | Sides | Attempts |
| --- | ---: | ---: |
| All three methods available | 4,197 | 18,876 |
| At least 3 prior bouts and 10 prior attempts | 2,758 | 12,661 |

Mean conditional binomial negative log likelihood per side-bout, lower is better:

| Method | All comparable sides | Established sample |
| --- | ---: | ---: |
| Raw career | 3.8119 | 1.6234 |
| Raw last-five | 4.7035 | 2.6945 |
| Sample-size adjusted | 1.4115 | 1.4345 |

On the established sample, adjusted minus raw-career score was -0.1889
(95% calendar-date cluster bootstrap interval -0.2539 to -0.1372); adjusted
minus raw-last-five was -1.2600 (-1.5595 to -1.0096). Bootstrap resampled 333
whole date clusters, 1,000 replicates, fixed seed 20261026. These are intervals
for score differences, not uncertainty ranges for a fighter's skill.

Interpret this cautiously. Raw career had 505 exact 0%/100% estimates and raw
last-five had 681 on the full comparable cohort. Their errors can receive very
large log penalties under the predeclared 1e-6 scoring clip. Much of the gain
comes from avoiding those extremes; this is not evidence of opponent-quality
adjustment. A useful next challenger is a simple fixed smoothing baseline,
with its own protocol declared before examining its score.

The wider development period has 7,860 side rows, including 2,860 zero-attempt
outcomes, 817 rows with no earlier recorded bouts, and 1,272 with no earlier
attempt exposure. Coverage counts and cold-start adjusted-only scores are
reported separately. Primary comparisons exclude rows without all baseline
estimates rather than giving the adjusted method an easier cohort.

Year/division summaries, cold-start coverage, individual predictions, paired
bootstrap results and protocol/code/input hashes are in
`data/processed/td_defense_prototype_2026_10_26_v1/report.json` and
`predictions.jsonl`. Subgroup slices are descriptive; thin groups are not release
approvals. No broad novelty, winner-accuracy, or calibration claim follows.

2019+ overlaps earlier project work and is labeled **development**, not an
untouched holdout. This prototype conditions on recorded opposing attempts and
observed bout division; it does not forecast future attempts, duration, or a
winner. It does not implement opponent adjustment, skill/predictive intervals,
full calibration/reliability gates, or a public release. `public_release` and
`opponent_adjusted` are both false. The public page remains raw.

## Verification and reproduction

The new tests cover paired identity corruption, defensive/opposing denominators,
missing/invalid counts, zero attempts, exclusive cutoff, read-only exports,
source tampering, immutable outputs, known adjustment arithmetic, same-day and
future leakage, last-five membership, future-independent parameter selection,
finite extreme scores, and deterministic date-cluster bootstrap behavior.
Independent SQL checks reconstructed all prior counts and career/last-five
rates for 214 predictions across eras/fighters; all matched. Adapter/prototype
input hashes and the original database hash were rechecked unchanged.

New-file Ruff checks and JavaScript rendering checks passed. The viewer tests
passed (22), and the adapter/prototype tests passed (14). Full regression-suite
results are recorded in the accompanying verification JSON after completion.

Existing outputs are immutable. Use new output directory names when repeating:

```bash
cd ~/Projects/upset
source .venv/bin/activate
python -m upset.skill.takedown_defense \
  --database data/processed/research_2026_10_25_v1/upset.sqlite \
  --before 2026-10-26 \
  --output data/processed/<new-adapter-directory>
python -m upset.skill.shrink_defense \
  --adapter data/processed/<new-adapter-directory> \
  --protocol docs/TAKEDOWN_DEFENSE_PROTOCOL_V1.md \
  --output data/processed/<new-prototype-directory>
```

The next milestone is a preregistered comparison with fixed smoothing baselines,
then predictive calibration and stabilization/reliability checks. Opponent
adjustment remains a separate subsequent model, not a label for this prototype.
