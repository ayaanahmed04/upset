# Betting market odds in UPSET

Built by `src/upset/data/build_market_odds.py` into `data/processed/market_odds_2026_11_10_v3/`
from the UFC Betting Odds Daily archive (Kaggle, recorded as CC0; copy downloaded 2026-11-10,
`data/raw/ufc_market_odds_2026_11_10_v1/kaggle-odds.zip`). Bound to the reviewed v3 database by hash.

## What a price is

* 2010-2024 (and early 2025): one archived pre-fight moneyline per bout, matched by UFCStats fight ID
  (or both fighters' names). These rows were added to the archive later, so they carry no capture time.
* Mid-2025 on: the median, across 20+ sportsbooks, of each book's margin-free chance from the last
  daily snapshot before fight day. If only a fight-day snapshot exists it is used when taken before
  16:00 UTC (before any US card) and labelled "fight-day consensus".
* Each match is checked against both fighters' names; spelling variants are accepted only when the
  UFCStats fight ID already ties the row to the bout.

Coverage: 6,752 of 7,724 UFC fights since 2010 (87%). Fights before 2010 are not in the archive.

## Does mixing the market with the UPSET forecast help?

Fit on 2010-2018 (logit mix of market and forecast), scored on 2019-2026 fights it never saw:

```
{"all": {"market": {"bouts": 3306, "log_loss": 0.6068, "accuracy": 0.6724}, "upset_forecast": {"bouts": 3306, "log_loss": 0.6613, "accuracy": 0.5959}, "market_plus_upset": {"bouts": 3306, "log_loss": 0.6062, "accuracy": 0.6732}}, "newer fighters (<3 decided UFC fights)": {"market": {"bouts": 1547, "log_loss": 0.5986, "accuracy": 0.6755}, "upset_forecast": {"bouts": 1547, "log_loss": 0.664, "accuracy": 0.5934}, "market_plus_upset": {"bouts": 1547, "log_loss": 0.5981, "accuracy": 0.6765}}, "established fighters": {"market": {"bouts": 1759, "log_loss": 0.6141, "accuracy": 0.6697}, "upset_forecast": {"bouts": 1759, "log_loss": 0.659, "accuracy": 0.5981}, "market_plus_upset": {"bouts": 1759, "log_loss": 0.6132, "accuracy": 0.6703}}}
```

The market alone is far better than the UPSET forecast (log loss 0.607 vs 0.661). Adding the forecast
to the market improves log loss by about 0.0006: real but tiny. So the site uses the market to define
upsets, shows the UPSET forecast next to it, and keeps the rating itself built from results only.

## Upset Tracker

An upset is a decided fight the market's underdog won with under a 45% chance (about +120 or longer).
1,780 upsets in 6,742 decided, priced fights; the UPSET forecast had already favored the winner in 441.
`--market-odds` turns this on; without it the tracker falls back to the forecast-based version.
