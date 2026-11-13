# Round-by-round factors (2026-11-12)

Script: `src/upset/ratings/round_research.py` · Tests: `tests/test_round_research.py` ·
Output: `data/processed/round_research_2026_11_12_v1/report.json`

## The data

Cito's archive stores every bout round by round (`roundStats` on each archived card), and the
archive bridge had already staged those rows (`data/processed/cito_archive_bridge_v2/round_stats_staged.jsonl`).
Recent cards come from `data/processed/cito_current_2026_11_10_reviewed_v3/rounds_staged.jsonl`.
No new API calls were needed.

| Check | Result |
|---|---|
| Bouts with round rows linked to a database fight | 8,939 |
| Rounds add up exactly to the fight totals (sig. strikes landed and thrown, takedowns, knockdowns) | **8,931** |
| Left out: missing a corner | 8 |
| Rows from bouts whose totals were never verified (not used) | 1,534 rows |
| Bouts used (2001 on, five-minute rounds) | 8,685 |
| Judges-style round score agrees with the official decision winner | 83.5% of 4,004 decisions |

League picture, 2010–2018: fighters throw 9.1 significant strikes a minute in rounds where they
are not wrestled, and 5.9 in rounds where the opponent lands a takedown or holds a minute of
control (about a third less).

## The test

Same protocol as the situational test: each factor is built only from earlier rounds, added to
forecast 5.2, fit on 2010–2018, scored once on the 3,177-fight record set since 2019, and must
have a 95% interval below zero and improve both 2019–2022 and 2023+.

| Model | Log loss | Change | 95% interval | 2019–22 | 2023+ | Passes |
|---|---|---|---|---|---|---|
| Forecast 5.2 | 0.6423 | | | | | |
| 1. Rounds won (judges-style score) | 0.6433 | +0.0010 | −0.0003 to +0.0022 | +0.0014 | +0.0005 | no |
| 2. Late-round edge | 0.6428 | +0.0005 | −0.0007 to +0.0020 | +0.0008 | +0.0002 | no |
| 3. Output fade (cardio) | 0.6426 | +0.0003 | −0.0004 to +0.0012 | +0.0005 | +0.0001 | no |
| 4. Wrestling against a striker (Fighter A / B) | 0.6427 | +0.0004 | −0.0004 to +0.0013 | +0.0008 | 0.0000 | no |
| All four | 0.6445 | +0.0022 | +0.0001 to +0.0045 | +0.0034 | +0.0010 | no (worse) |

None helps. The wrestling-against-a-striker factor points the right way (a fighter whose striking
dies when wrestled does worse against frequent wrestlers) but adds nothing the forecast does not
already know. Per-fighter splits rest on few late or wrestled rounds, so they are noisy, and who
wins rounds is already mostly reflected in who wins fights.

## What it is good for

The rows are clean and descriptive round profiles are real and interesting, for example:

- Ciryl Gane throws 9.8 significant strikes a minute in clean rounds and 2.5 in rounds where he is
  wrestled (39 rounds). Josh Hokit, his UFC 334 opponent, has only 7 UFC rounds.
- Islam Makhachev wins 92% of his completed rounds on the judges-style score (38 rounds).
- Max Holloway goes from 12.2 strikes a minute in round 1 to 15.3 afterwards.

Candidate site feature (not built): a "Round by round" panel on fighter pages with rounds won,
pace by round and output when wrestled.
