# Published picks and the track record

UPSET publishes its forecast for each UFC card *before* the first fight and grades it afterwards.
The site shows the result on `/record` (Track Record), and every event page with published picks
shows a "picks locked" banner.

## Files

`data/published/picks/<event slug>/`

| File | Written | Purpose |
| --- | --- | --- |
| `picks.json` | once, before the card | The forecast for every bout that has one, plus the betting-market reference at the time. Never edited. |
| `manifest.json` | once, with `picks.json` | SHA-256 fingerprint of `picks.json` and the freeze time. |
| `graded.json` | after the card | Results, log loss, market comparison. `--regrade` keeps the old file as `graded-<time>.json`. |

The server checks the fingerprint every time it reads a card. A changed `picks.json` is shown
as failing its check and is not counted.

Anyone can verify a card: download `picks.json` from the Track Record page and run
`shasum -a 256 ufc-334-picks.json`. The output must equal the fingerprint on the page.
Committing the folder to Git (and pushing) adds an independent public timestamp.

## Weekly routine

Before the card (any time after the schedule is final, before the first fight):

```
.venv/bin/python -m upset.predictions.published_picks freeze --slug ufc-334 \
  --api http://127.0.0.1:8768 \
  --market data/raw/ufc_market_odds_2026_11_10_v1/kaggle-odds.zip \
  --rating-snapshot data/processed/overall_rating_v5_1_2026_11_10_reviewed_v3
```

The tool refuses to overwrite a published card or to freeze a card that has started.
Use the newest odds download for `--market`; it is optional.

After the card, once a new reviewed database includes its results:

```
.venv/bin/python -m upset.predictions.published_picks grade --slug ufc-334 \
  --database data/processed/research_<new release>/upset.sqlite
```

Bouts are matched by both fighters' IDs, so late replacements and cancellations are marked
"Not held" and are not graded. Draws and no contests are "No result".

## Rules (shown on the site)

* The pick is the fighter UPSET gave the higher chance.
* Right or wrong is counted on decided fights only.
* Log loss scores the probability itself (lower is better; always saying 50% scores 0.693).
* The market column is the no-vig BetOnline.ag moneyline (Pinnacle if BetOnline is missing) from
  the UFC Betting Odds Daily archive, latest price before the freeze. It is for comparison only.

## First card

UFC 334 (Nov 14, 2026) was frozen on 2026-11-11 at 19:21:20 UTC with 12 picks.
Fingerprint: `95d627d1e584ddb392d51a4bdc2dc429f288736a281953f6a7f64091e285509a`.

## Re-locking a card before it starts

A card can be locked again before its first fight, for example after a forecast revision. The earlier
lock is never edited or deleted: the new lock goes in its own folder and names the old one.

```
python -m upset.predictions.published_picks freeze --api http://127.0.0.1:8768 --slug ufc-334 \
  --folder ufc-334-r2 --supersedes ufc-334 \
  --market data/raw/ufc_market_odds_2026_11_10_v1/kaggle-odds.zip \
  --rating-snapshot data/processed/overall_rating_v5_1_2026_11_10_reviewed_v3 \
  --forecast-adjustment data/processed/forecast_adjustment_2026_11_12_v1
```

The new picks.json records the replaced lock's fingerprint inside itself, so the link is covered by the
new fingerprint. The track record counts the card once (the new lock), and shows the replaced lock with
its time, fingerprint and a download link. A graded lock cannot be replaced, and a card that has started
cannot be locked at all. Grade the new folder: `grade --slug ufc-334-r2 --database ...`.

UFC 334 was re-locked on 2026-11-14 at 06:25 UTC with forecast 5.2 (fingerprint
`8b092776b9e8b7c9541daf9528f03617f15f0081a94f03853b0a4be4b096f6ad`). It replaces the 2026-11-11 lock
made with forecast 5.1 (`95d627d1e584ddb392d51a4bdc2dc429f288736a281953f6a7f64091e285509a`), kept in
`data/published/picks/ufc-334/`.
