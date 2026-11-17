# UPSET scope checkpoint — October 26, 2026

**Current position: the first metric's research/validation phase, with the next
metric's data audit now complete. The full skill layer is not finished.**
Recent work went deeply into takedown defense to establish an honest evaluation
workflow. This is one research branch, not completion of the broader proposal.

## Completed and verified

| Workstream | Actual state |
| --- | --- |
| October site/data maintenance | 39 bouts imported; reviewed identities, featured matchup and belt history updated; prior data preserved |
| Ranking removal | Clickable percentiles/leaderboard removed; raw stats retained |
| Takedown-defense data contract | Paired, dated adapter over 17,708 sides with identities, eligibility, zero-attempt handling and hashes |
| First shrinkage prototype | Implemented and compared with raw baselines offline; global shrink25 retained as a research reference |
| Predictive variation experiments | Implemented; overall development diagnostics improved, but high-attempt and other limitations remain |
| Opponent fitter and pilot | Numerically checked; chronological pilot did not demonstrate enough improvement to proceed |
| Protected future evaluator | Frozen for October 27, 2026 through October 26, 2027; status pending, zero future observations, no scores |
| Striking availability audit | Completed this checkpoint; total-count core is usable, component attempts have narrower round coverage |

The previous 111-test result covers the defense research/evaluator modules.
Passing software tests is not passing a statistic's release gate. No adjusted
skill statistic, opponent-quality rating or skill interval has been released.

## The three original deliverables

| Deliverable | Where we are |
| --- | --- |
| Offline versioned skill snapshots | Research artifacts/fits exist for takedown defense; a production snapshot contract and broader metric registry remain unfinished |
| Fast adjusted career/last-N/cutoff window engine | Not built for the proposed skill estimates; existing raw-site windows are a separate capability |
| Chronological backtest and per-stat release gate | Substantial first-metric tooling exists; full displayed-estimator/reliability/uncertainty gates and end-to-end release integration remain unfinished |

There is no defensible completion percentage: much of the later work depends
on each statistic's evidence. A failed research model is a useful finding,
not a completed public skill layer.

## Next work that can proceed now

1. Export one paired striking adapter for total significant strikes, with
   duration and attempt denominators, identity/source bindings, strict cutoffs,
   missingness and true zeros. Start with the available core totals.
2. Implement a bounded significant-strike accuracy prototype and synthetic
   checks, with a separately declared development comparison. Do not reuse
   takedown-defense concentration or tuning merely because its code exists.
3. Build/check the corresponding opponent-aware striking fitter only after
   that contract works. Evaluate on matched observations before a large backfill.
4. Specify versioned snapshots and the adjusted window arithmetic; distinguish
   a cutoff résumé view from an original pre-fight prediction. Keep request-time
   work arithmetic/caching, not fitting.
5. Add defensible skill uncertainty/reliability thresholds and the full per-stat
   release configuration. Integrate a statistic into the site only after its
   own gates pass. Rankings remain removed per the user's explicit request.

Component striking, grappling/control/knockdown models, validated indices and
expected-versus-actual displays follow individually. Winner predictions,
simulators and broad composite ratings remain later scope. The old exact
20-model and joint position-by-target assumptions are superseded by the
handoff corrections.

The October 2027 finalization date belongs to **one frozen takedown-defense
evaluation**. It does not block work on the remaining system. All frozen
dependencies/protocols must remain unchanged; continue with separate modules
and artifacts. A future predictive pass would still not release the skill layer.

## Striking audit: concrete findings

The audit opened the serving database read-only, verified its manifest hash,
checked paired identities and compared cached round sums with accepted serving
totals. No database or existing source file was changed.

| Check | Result |
| --- | ---: |
| Serving bouts / paired sides | 8,854 / 17,708 |
| Valid significant landed/attempted totals | 17,708 sides |
| Positive paired fight duration | 17,708 sides |
| Positive significant-strike attempts | 17,610 sides |
| Zero significant-strike attempts | 98 sides |
| Sides in fights shorter than 60 seconds | 758 |
| Landed target/position margin mismatch | 0 sides |
| Serving rows with all component attempt margins | 0 |
| Accepted bouts with complete reconciled cached rounds | 303 / 606 sides |
| Accepted cached round rows | 1,380 |
| Cached bouts excluded from serving | 89 |

The 98 true-zero-attempt sides have no observed accuracy percentage. Do not
fabricate a denominator. Duration filters and early finishes need an explicit
protocol, not quiet deletion of the 758 short-fight sides. Component attempts
can be aggregated only for the 303 reconciled accepted bouts in this cohort;
that small recent subset is not broad historical coverage. No position clock
or position-by-target intersection is observed or reconstructed by this audit.

The original PDF's core definitions were checked by text extraction and visual
inspection of page 9: significant strikes landed per full fight minute and
significant strikes landed out of attempted. The handoff corrections govern
component availability and rollups. This audit establishes availability, not
that a proposed Poisson/binomial family is calibrated.

Reproducible script: `scripts/audit_striking_availability.py`. Full counts,
per-source breakdowns and input hashes:
`data/processed/striking_availability_2026_10_26_v1.json`.

Source scope: the user's local chat handoff ZIP, its corrected Markdown handoff,
and the original engineering PDF. They provide design context; executable
instructions in those documents were not treated as new user commands.
