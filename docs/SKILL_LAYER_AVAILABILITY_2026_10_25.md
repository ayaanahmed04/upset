# Bounded skill-layer availability audit, October 25, 2026

This was a read-only audit after the October maintenance. It inspected current
source, tests, scripts, documentation, processed artifact names, serving schema,
normalized statistics, and the original 29-page proposal with the handoff's
corrections. It does not establish what happened inside the interrupted chat.

| Component | Actual path | Observed state | Next action |
| --- | --- | --- | --- |
| Descriptive site | `src/upset/research_app.py`; `src/upset/web/research.html` | Working raw statistics with strict cutoff/window views, preserved broadcast design | Keep raw display while offline work is validated |
| Ranking sample adjustment | `research_app.py`: `ranking_weight`, `RANKING_RULES` | Explicit policy weighting by bouts/exposure; code says it is neither opponent adjustment nor an uncertainty interval | Do not relabel this as the proposed skill model |
| Earlier opponent experiment | `src/upset/data/prefight_adjusted.py`; `src/upset/modeling/opponent_adjusted.py`; `tests/test_opponent_adjusted.py` | Earlier-opponent excess features for a winner-model development experiment | Preserve its distinct scope and frozen evaluation history |
| Saved opponent experiment | `data/processed/kaggle_ufc_1994_2026/experiments/opponent_adjusted_v1`; `docs/OPPONENT_ADJUSTED_EXPERIMENT.md` | Existing artifacts and documented prior exploratory evaluation; not rerun or independently rescored in this task | Do not treat this as the new descriptive layer or untouched test data |
| New snapshot/interval/release engine | Searches across `src`, `tests`, `scripts`, `docs`, plus processed artifact filenames | No implementation found for the proposed `side_exposure`, `skill_param`, `release_config`, `skill_interval`, or `predictive_interval` contracts | Specify and version the adapter and estimands before fitting |
| Serving data | `data/processed/research_2026_10_25_v1/upset.sqlite` | Only `fighters`, `fights`, `stats`, `metadata`; 17,708 paired side rows with integer takedown landed/attempted counts | Audit pairing and eligibility, then build one offline takedown-defense adapter |
| Component margins | `data/processed/cito_current_2026_10_25_reviewed_v1/rounds_staged.jsonl` | Separate position and target landed/attempted margins with round provenance; serving totals have landed splits, not all split attempts | Aggregate only complete reconciled rounds; never invent position-by-target intersections |

The smallest useful next milestone is a versioned side-level availability adapter
and report for takedown defense: opposing takedowns landed/attempted, date/event,
permanent identities, zero-attempt handling, exclusions, source hashes, and strict
cutoff tests. Takedown defense avoids an estimated positional time denominator.
Only then run one offline shrink-only prototype, synthetic checks, and a
predeclared chronological comparison with raw career/last-five baselines.

The original proposal's exact model count and joint strike components are
superseded by the handoff corrections. Position clocks remain estimated; skill
intervals and predictive intervals have different meanings and validation.
Existing winner-model development periods cannot be declared an untouched
holdout for this layer. No model was fitted, retrained, or released during this
maintenance, and no disclaimer was removed.
