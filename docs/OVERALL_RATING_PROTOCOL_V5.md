# UPSET Rating v5 · protocol and results (November 10, 2026)

UPSET Rating v5 replaces the v4 display as the launcher default. It keeps the
60–99 number, gives that number a fixed meaning in fight terms, adds EA-style
stars and attributes, and pairs it with a separate win-probability forecast.
v4 remains available with `UPSET_RATING_VERSION=v4 ./Start\ UPSET.command`.

## What the number means

* **80 is the median UFC fighter active in the two years before the snapshot.**
* **Every 5 points doubles the odds between two established fighters.** An 85
  is about a 2-to-1 favorite over an 80; a 90 about 4-to-1; a 95 about 8-to-1.
  This is the same idea as chess Elo, where 400 points means 10-to-1.
* The scale is clamped to 60–99. One active fighter sits at the cap.

The points-per-unit constant comes from the model, not taste:
`points_per_unit = 5 × typical_g / ln 2 = 6.545`. Here `typical_g = 0.907` is
the median uncertainty discount across 2019+ fights. The training calibration
slope was 0.93 (test 0.98, 2025–26 1.08), so no extra calibration factor is
applied.

Checked against every UFC fight since 2019, using the integer ratings from before
each fight:

| Rating gap | Fights | Model said | Higher-rated won | 5-point rule |
| --- | --- | --- | --- | --- |
| 0–2 | 1,290 | 54.9% | 55.0% | 53.5% |
| 3–5 | 1,122 | 62.6% | 60.5% | 63.5% |
| 6–9 | 348 | 71.8% | 75.0% | 73.9% |
| 10–14 | 51 | 81.1% | 78.4% | 84.1% |

## Stars and tiers

Stars group the scale as the EA UFC games do. Cut-offs were set once from the
active roster (813 fighters since November 7, 2024) and are frozen in the
manifest:

| Stars | Score | Tier | Active fighters |
| --- | --- | --- | --- |
| 5 | 92+ | Champion level | 15 |
| 4.5 | 88–91 | Title contender | 55 |
| 4 | 85–87 | Ranked caliber | 81 |
| 3.5 | 81–84 | Fringe contender | 216 |
| 3 | 78–80 | Solid UFC level | 174 |
| 2.5 | 75–77 | Below UFC average | 171 |
| 2 | under 75 | Lower tier | 101 |

## How it is built

Strength is on a log-odds scale: `strength = results + β · skills`.

* **Skills**: the v4 opponent-adjusted striking, wrestling and grappling profiles
  (inverse-normal of each part's raw score). The three parts are weighted 0.87,
  0.45 and 0.20, which came from a logistic fit on 2010–2018 fights only. β = 1.1.
* **Results**: a Glicko-style rating updated after each decisive fight.
  Finishes and unanimous decisions count fully, split and majority decisions
  count 0.6, and other decisive results 0.5. Uncertainty starts at 0.4 and grows
  0.03 per year of inactivity.
* All fights on one date are predicted before any rating from that date changes.

The dialog shows the split as points: `80 + skills points + results points ≈ score`.

## Rules every served number obeys

Each rule is checked when the snapshot is built and again every time the site loads it:

1. The number changes only after a recorded decisive UFC fight.
2. A win never lowers it and a loss never raises it. There were 611 holds and
   0 wrong-direction updates.
3. **Pass rule:** right after a fight, the winner is rated at least as high as
   the fighter they beat. 703 meet-in-the-middle adjustments were made and 0
   violations remain. Across the 155 title fights since 2019, the winner was
   never below the loser after the fight; v4 had 7 such cases.
4. Later results can carry a fighter past someone who beat them. Eleven such
   current pairs exist (1–3 points each), for example Jean Silva 87 and Arnold
   Allen 88.

A two-year **head-to-head lock** was tested and rejected. It would have kept B
below A while A stayed unbeaten after beating B, but it made 2010–2018
predictions worse (log loss 0.6667 → 0.6724). The site shows head-to-head
results next to the numbers instead. The option remains in `build_v5.py --h2h-lock`.

## The forecast

The matchup forecast uses the same machinery without the pass rule or holds
(β = 1.3, starting uncertainty 0.2), so it is free to be purely predictive. It
was the best 2010–2018 configuration in the research grid. The rating and the
forecast can disagree. When they do, the comparison page explains why.

## Walk-forward results

Settings were chosen on 2010–2018 and every fight since 2019 was scored once.
Both fighters needed a previous decisive UFC fight and a v4 profile.

| Model | 2019+ log loss | 2019+ accuracy | 2025–26 log loss | 2025–26 accuracy |
| --- | --- | --- | --- | --- |
| **v5 forecast** | **0.6596** | **60.0%** | **0.6460** | **63.9%** |
| v5 rating (rules applied) | 0.6652 | 59.1% | 0.6578 | 62.3% |
| v4 (declared slope) | 0.6658 | 59.7% | 0.6564 | 61.9% |
| Elo K=64, 2-year decay | 0.6784 | 57.5% | 0.6753 | 59.0% |
| Results only (no skills) | 0.6856 | 55.2% | 0.6841 | 54.7% |

3,177 fights since 2019; 804 since 2025.

When the integer ratings differed, the higher-rated fighter won 60.1% of 2,813
fights since 2019.

**Market check.** The comparison used 277 fights from 2025–26 with archived
no-vig BetOnline.ag prices from 1–7 days before the event:

| Model | Log loss | Favorite won |
| --- | --- | --- |
| Market | 0.6139 | 70.0% |
| v5 forecast | 0.6293 | 66.4% |
| v5 rating | 0.6421 | 67.2% |
| v4 | 0.6439 | 65.0% |

The market is still better, and the site says so wherever the forecast appears.

## Known limits

* Layoffs, age, weight changes, injuries and short notice are not modeled. The
  forecast flags fighters inactive for more than two years.
* Fighters with fewer than four UFC fights are marked provisional. The likely
  range (one standard deviation of the results component) is usually ±3–4 points.
* Ratings compare fighters across divisions, like a pound-for-pound list.
  Forecasts are meant for real matchups.
* Ties at the top are common because elite fighters are genuinely close on this
  scale (e.g. Topuria, Oliveira and Gaethje are all 93).
* The rating uses reviewed outcome amendments as currently known. This hindsight
  is the same as in v4.

## Files

* Snapshot: `data/processed/overall_rating_v5_2026_11_10_reviewed_v3/` contains
  `ratings.jsonl`, `forecasts.jsonl`, `evaluation.json` and `manifest.json`. The
  manifest holds the input and output hashes, scale and stars.
* Code: `src/upset/ratings/build_v5.py`, `serving_v5.py`, `v5_research.py` and
  `v5_diagnose.py`. The Upset Tracker uses `src/upset/data/viewer_upsets_v5.py`.
  The tests are in `tests/test_rating_v5.py`.
* Research runs: `data/processed/rating_v5_research_2026_11_10_v1/` and `_v2/`
  (grid, summary, diagnostics). Discarded build attempts are in
  `data/processed/_v5_build_attempts/`.

Rebuild:

```zsh
PYTHONPATH=src .venv/bin/python -m upset.ratings.build_v5 \
  --database data/processed/research_2026_11_10_reviewed_v3/upset.sqlite \
  --v4 data/processed/overall_rating_v4_2026_11_10_reviewed_v3 \
  --research data/processed/rating_v5_research_2026_11_10_v2 \
  --market data/processed/rating_results_benchmark_2026_11_10_v2/predictions.jsonl \
  --output data/processed/overall_rating_v5_<new suffix>
```

## Research notes

* **EA UFC 4/5** rate fighters with 1–5 stars overall plus stand-up, grappling
  and health stars. Attributes are updated after real events. v5 borrows the
  stars and the "attributes under one headline" layout.
* **NBA 2K** builds an overall from many attributes through position-specific
  formulas. v5 instead learns the weights from which profiles actually won fights.
* **FightMatrix** uses an Elo/Glicko hybrid in which ratings do not fall as fast
  as they rise. v5's holds and pass rule are a stricter, auditable version of
  that idea.
* **Glicko and Whole-History Rating** supply the uncertainty and the
  odds-doubling scale.

## Revision 5.1 · earned display (November 11, 2026)

**Problem.** In 5.0, a fighter's stats counted in full from their first UFC fight. Ty Miller
(2-0 with very dominant numbers) showed 88, above Alexandre Pantoja (87), who held the
flyweight title for years.

**What was tested first.** Two statistical fixes were tried on the forecast, choosing
settings on 2010–2018 fights only:
* Shrinking short-record stats toward average.
* Adding extra uncertainty for short records.

Neither helped prediction. Shrinking made it worse (2010–2018 log loss 0.6625 → 0.6631 at
the mildest setting). Early stats do predict well, so the forecast is unchanged.

**What changed (display rule, not a prediction claim).** The displayed number must be
earned. Until a fighter's 5th UFC fight with stats, the skills part counts n/5 of its weight:
1/5 after one fight, 2/5 after two, and so on. Predictions inside the model still use the
full skills term. "Provisional" now means fewer than 5 UFC fights.

Selected examples (5.0 → 5.1):

| Fighter | UFC fights | 5.0 | 5.1 |
| --- | --- | --- | --- |
| Ty Miller | 2 | 88 | 83 |
| Tommy McMillen | 3 | 90 | 87 |
| Yousri Belgaroui | 3 | 89 | 86 |
| Alexandre Pantoja | 19 | 87 | 88 |
| Josh Hokit | 4 | 89 | 89 |

The top of the list is unchanged.

**Cost, stated plainly.** The displayed number is a slightly worse predictor:
* 2019+ log loss rose from 0.6655 to 0.6702. That is still better than Elo with decay
  (0.6784), and the serving gate checks this.
* The higher-rated fighter's record since 2019 fell from 60.1% to 59.1%.
* The forecast, which makes the win percentages, is unchanged: 0.6596 log loss, 60.0%
  accuracy since 2019.

All rules still hold: 0 wrong-direction updates, 0 pass-rule violations, and 0 title
winners below the loser after the fight.

Files:
* Snapshot: `data/processed/overall_rating_v5_1_2026_11_10_reviewed_v3/` (manifest `revision: "5.1"`).
* Build: `build_v5.py --display-ramp 5`.
* Research grids: `src/upset/ratings/v5_shrink_research.py` and
  `data/processed/rating_v5_research_2026_11_11_shrink/`.

The launcher's `v5` now points to 5.1. The 5.0 snapshot stays on disk but no longer passes
its own code-hash check, because `build_v5.py` changed. Use `UPSET_RATING_VERSION=v4` to
roll back.
