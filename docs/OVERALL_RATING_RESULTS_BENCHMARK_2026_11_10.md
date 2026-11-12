# UPSET rating benchmark · November 10, 2026

Experimental v4 performed better than the two results-only models over the
full matched history. Plain Elo performed better on recent title bouts, where
there were only 33 matched results. Keep v4 as the live grade and track all
three approaches on upcoming cards.

## Walk-forward results

All models saw the same 3,171 decisive UFC fights from January 2019 through
November 7, 2026. Both fighters had a prior v4 state. Each yearly probability
fit used earlier years, and each rating used fights strictly before the bout
date. Accuracy gives ties half credit. Lower log loss and Brier scores are
better. [Walk-forward evaluation](https://otexts.com/fpptr/tscv.html)

| Model | Log loss | Brier | Ordering accuracy |
| --- | ---: | ---: | ---: |
| v4 raw score, annual calibration | 0.6652 | 0.2364 | 59.8% |
| v4 raw score, original calibration | 0.6653 | 0.2364 | 59.8% |
| Elo 64 with inactivity decay | 0.6753 | 0.2412 | 57.6% |
| Elo 32 | 0.6863 | 0.2466 | 54.8% |
| Even probability | 0.6931 | 0.2500 | 50.0% |

The displayed integer v4 badge had 59.4% ordering accuracy with half credit
for 192 ties. The archive had another 726 decisive bouts with a missing prior
v4 grade and 72 draws, no-contests or otherwise non-decisive bouts. The sample
and selection history make this a retrospective comparison.

For the 787 matched 2025–26 fights, log loss was 0.6531 for v4 with annual
calibration, 0.6698 for Elo 64 with decay and 0.6833 for Elo 32.

## Title fights and the review cases

On 33 matched known title bouts since January 2025, Elo 32 had log loss
0.6633, compared with 0.6959 for recalibrated v4 and 0.6997 for Elo 64 with
decay. The Elo 32 minus v4 event-date bootstrap interval was −0.095 to
+0.024, so the title-fight sample leaves substantial uncertainty.

Among 38 known decisive title results in this period, the winner was below
the loser in v4 after the bout date in 7 cases, with 3 ties. At the end of the
archive, the winner was below the loser in 10 cases, with 1 tie. Six title
winners were below the loser at the end of the archive in each Elo model.
Later fights can change an end-of-archive comparison.

| Result | Winner–loser v4 before | After fight date | Latest archived |
| --- | --- | --- | --- |
| Gaethje def. Topuria | 88–96 | 89–94 | 89–94 |
| Strickland def. Chimaev | 90–97 | 91–97 | 91–97 |
| Yan def. Dvalishvili, Oct 24 | 94–97 | 94–95 | 94–95 |
| Topuria def. Oliveira | 95–96 | 96–94 | 94–97 |
| Morales def. Brady | 91–96 | 93–95 | 93–96 |

The v4 win/loss holds prevent a winner from dropping or a loser from rising
after a decisive date. They can leave a pre-fight ordering in place after an
upset. These cases support showing the recorded result alongside the badge
and tracking whether a more responsive model improves forecasts over time.

## Market comparison

277 matched bouts had an unambiguous BetOnline.ag quote recorded before the
event date, including 85 in 2025 and 192 in 2026. On these bouts, the no-vig
market estimate had log loss 0.6139 and Brier score 0.2120. Recalibrated v4
had 0.6421 and 0.2250. The paired log-loss interval for market minus v4 was
−0.071 to +0.015. The prices were recorded one to seven calendar days before
the event. Exact closing timestamps are unavailable in this archive.
[Public odds archive](https://www.kaggle.com/datasets/jerzyszocik/ufc-betting-odds-daily-dataset)

## UFC 334 prospective ledger

The saved card has 13 scheduled pairings. Ten have prior linked UFC history
for both fighters and received frozen research probabilities. The other
three are listed with their coverage status. The ledger also captures the
prices displayed on the official event page, where present, with the
observation date. The saved numbers are conditional on a decisive result.
After UFC 334, join by actual participants, record changed pairings or
non-decisive results, and score the eligible outcomes against the frozen
probabilities. [Official event card](https://www.ufc.com/event/ufc-334) ·
[November 10 card update](https://www.ufc.com/news/updates-polymarket-ufc-334-gane-vs-hokit)

## Reproduction

The protocol is in `docs/OVERALL_RATING_RESULTS_BASELINE_PROTOCOL_2026_11_10.md`.
Run `python -m upset.ratings.results_benchmark --help` for the database,
snapshot, registry, odds archive and protocol inputs. The benchmark’s
`summary.json`, `cases.json` and per-bout `predictions.jsonl` are in
`data/processed/rating_results_benchmark_2026_11_10_v2`. The frozen ledger
is in `data/processed/rating_prospective_ufc334_2026_11_10_v1`. The manifests
bind inputs and outputs by SHA-256.
