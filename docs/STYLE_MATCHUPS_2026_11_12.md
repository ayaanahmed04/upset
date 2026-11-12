# Style matchups research · November 12, 2026

Script: `src/upset/ratings/style_matchup_research.py`
Output: `data/processed/style_research_2026_11_12_v1/report.json`

Each fighter's style profile is built only from their UFC fights before each bout (takedown pressure,
takedown defense, control share, striking at range, volume, knockdowns), with small samples pulled
toward the league average. Labels use cut-offs set on 2010-2018: grappler = top 30% takedown pressure
(5.0+ attempts per 15 min); striker = bottom 40% (3.5 or fewer) and above-median share of strikes at
distance; mixed = the rest.

## Does it improve the forecast? (fit 2010-2018, scored on the 3,177-fight record set since 2019)

| Added to forecast 5.2 | Log loss | Favorite won | Change (95% interval) |
| --- | --- | --- | --- |
| none (5.2) | 0.6423 | 62.7% | — |
| takedown matchup | 0.6417 | 62.5% | −0.0006 (−0.0013 to +0.0002) |
| grappler vs striker | 0.6420 | 62.7% | −0.0002 (−0.0007 to +0.0003) |
| power vs chin | 0.6426 | 62.6% | +0.0003 (−0.0001 to +0.0008) |
| all three | 0.6421 | 62.6% | −0.0002 (−0.0011 to +0.0009) |

No style term improves predictions reliably. The rating's skill part already uses takedown and
striking stats, so most of what a style says is already in the forecast.

## How style pairings went, 2010 onward (eligible fights, different styles)

| Pairing | Fights | First style won | Forecast expected | Difference (95%) |
| --- | --- | --- | --- | --- |
| grappler vs mixed | 1,177 | 55.0% | 52.1% | +2.9 pts (+0.0 to +5.7) |
| grappler vs striker | 941 | 56.1% | 54.0% | +2.1 pts (−1.1 to +5.3) |
| mixed vs striker | 1,458 | 53.6% | 52.5% | +1.1 pts (−1.4 to +3.7) |

Grapplers win slightly more often than even the forecast expects, but the edge is small and not
steady enough to help predict new fights. Decision: not added to the forecast. Style labels and
"record against each style" could still be shown on profiles as description, not prediction.
