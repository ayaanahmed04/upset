# Situational factors research · November 12, 2026

Script: `src/upset/ratings/situational_research.py` · Output: `data/processed/situational_research_2026_11_12_v2/report.json`

Ideas taken from how fight analysts break down matchups, each built from earlier fights only, added to
forecast 5.2, fit on 2010-2018 and scored on the 3,177-fight record set since 2019. Because that set has
been used before, a factor must improve the 95% interval *and* both halves (2019-2022, 2023 on).

| Factor | Log loss change (95%) | 2019-22 / 2023+ | Passes |
| --- | --- | --- | --- |
| Style splits: record vs the opponent's style, beyond the forecast | −0.0002 (−0.0003 to +0.0001) | −0.0003 / 0.0000 | No |
| Staying down once taken down × opponent's takedown pressure | −0.0003 (−0.0019 to +0.0016) | −0.0016 / +0.0008 | No |
| Prior KO/TKO losses | +0.0002 | +0.0006 / −0.0001 | No |
| Knockdowns absorbed (career) | +0.0006 | +0.0010 / +0.0002 | No |
| UFC minutes (mileage) | +0.0002 | −0.0009 / +0.0011 | No |
| Southpaw vs orthodox | +0.0001 | +0.0004 / −0.0002 | No |
| Reach difference (+0.018 logit per inch) | −0.0010 (−0.0021 to 0.0000) | −0.0012 / −0.0008 | Borderline: re-test on new cards |
| Grappler vs striker at the Apex (small cage) | not fittable on 2010-18 (Apex opened 2020) | — | — |

Apex check, 2020 on (grappler vs striker, won vs forecast expected): Apex +2.6 pts (194 fights, −4.4 to +9.7);
arenas +1.3 pts (309 fights, −4.2 to +6.9). Direction matches the small-cage idea; far too few fights to tell.

Conclusion: nothing added to the forecast. The rating's results and skill terms already absorb most of what these
summaries capture. The analyst factors that matter most (positional habits, fence behaviour, cardio decay, weight
cuts, camp news) need data UPSET doesn't have: round-by-round and positional stats, or a dated news/weigh-in log.
