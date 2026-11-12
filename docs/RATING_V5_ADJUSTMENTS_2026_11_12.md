# Forecast adjustments research · November 12, 2026

Script: `src/upset/ratings/v5_adjustments_research.py`
Output: `data/processed/rating_v5_research_2026_11_12_adjustments/report.json`

Each candidate is a small adjustment on top of the walk-forward v5.1 forecast
(`logit p = a·logit(forecast) + Σ b·feature`), fit on 2010-2018 decided UFC fights and scored once
on 3,972 fights from 2019 onward. Features are differences between the two fighters. 95% intervals
come from resampling event dates.

| Version | Log loss (2019+) | Favorite won | Change (95% interval) |
| --- | --- | --- | --- |
| v5.1 forecast | 0.6607 | 59.9% | — |
| + layoff (years out past the first) | 0.6616 | 59.7% | +0.0009 (+0.0003 to +0.0015) |
| + age (years past 32) | 0.6502 | 62.1% | −0.0105 (−0.0148 to −0.0068) |
| + age + market starting point | 0.6471 | 61.9% | −0.0136 (−0.0186 to −0.0089) |
| + age, heavier divisions separate, + starting point | **0.6464** | **62.0%** | −0.0143 (−0.0198 to −0.0089) |
| Betting market (same fights with a price) | 0.608 | 67.0% | — |

* **Layoffs alone don't predict losses** once the rating is known; fighters returning from long
  layoffs lose mainly because they are older. Only UFC fights are visible, so time spent fighting
  elsewhere looks like inactivity; that limit applies.
* **Age is the largest single gain so far.** Per year past 32: −0.116 logit for most divisions,
  −0.050 for heavyweight and light heavyweight (chosen on 2010-2018 training loss, 0.6536 vs 0.6542).
* **Market starting point (strict):** what the market knew at a fighter's UFC debut beyond the
  forecast, carried forward with weight 0.85 per fight (chosen on training years). The current
  fight's odds are never used. Gain is largest for fighters with 1-4 UFC fights.
* Established fighters (both with 5+ UFC fights) improve too: 0.6531 → 0.6322.
* For reference, also using the current fight's odds for debutants reaches 0.636; not proposed,
  because it copies the market.

UFC 334 (frozen picks unchanged): Harrison vs Nunes moves from 28/72 to 46/54; Gane vs Hokit from
57/43 to 47/53; Jim Miller vs McKinney from 46/54 to 19/81.

## Shipped as forecast revision 5.2 (Nov 12)

Built by `src/upset/ratings/build_forecast_adjustment.py` into `data/processed/forecast_adjustment_2026_11_12_v1/`
(weights: forecast 0.950, age −0.116/yr past 32, heavier divisions −0.050/yr, starting point 0.306, decay 0.85).
On the published record set: since 2019 (3,177 fights) 60.0% → 62.7% favorites won, log loss 0.660 → 0.642;
since 2025 (804) 63.9% → 65.2%, 0.646 → 0.628. The 60-99 rating is unchanged. Frozen UFC 334 picks keep v5.1.
