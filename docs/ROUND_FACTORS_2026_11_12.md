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

## Round by round panel (built 2026-11-13)

Fighter pages now show a "Round by round" card under the skill profile:

- a headline type, given only when the fighter is in the top or bottom 10% of the 512 UFC
  fighters active since 2023 with 15+ rounds: Round collector, Gets stronger late, Fast starter,
  Needs it standing, Strikes through the grappling. Otherwise it says Builds as it goes, Starts
  fast or Steady pace. Under 10 rounds it says "Still early" and shows no averages;
- three tiles: rounds won, strikes thrown per minute by round (round 1 against later rounds,
  with a small bar per round), and strikes thrown per minute in free rounds against wrestled
  rounds. Each tile is tagged only when the fighter is in the top or bottom 10%;
- the last six fights, round by round: won, lost or even on the round score, with the finish
  marked. Hovering over a round shows its strikes, takedowns, control and knockdowns.

Built by `src/upset/data/round_profiles.py` into `data/published/rounds/rounds_2026_11_13_v1/`
(rounds.json + manifest.json, checked against the database on load). Served at `/api/rounds?id=`
when the app is started with `--round-profiles`. Front end: block `12-round-profile.html`.
Like the skill profile, it is hidden for past dates, because it is built from every recorded round.
Tests: `tests/test_round_profiles.py`.

## Learned round scoring (2026-11-14)

Script: `src/upset/ratings/round_scoring.py` · Model: `data/processed/round_scoring_2026_11_14_v1/model.json` ·
Tests: `tests/test_round_scoring.py`

Round winners are not in our data: Cito has the stats per round and, for 294 recent decisions, each
judge's total (857 cards). The first panel used a hand-picked score. This replaces it with a logistic
score fitted to 4,024 decisions, treating the round winners as hidden (EM): the label is the judge's
round count where we have it, and the official winner otherwise. 10-8 cards and deductions are left out.

Out of sample (5 folds, split by fight):

| | Hand-picked | Learned | Two real judges |
|---|---|---|---|
| Picks the official decision winner (4,024 decisions) | 83.3% | 84.9% | |
| Same on the 294 recent decisions with judge totals | 81.0% | 86.1% | |
| Same round count as a judge (857 cards) | 58.9% | 63.4% | 66.5% |
| Within one round of the judge | 92.5% | 93.6% | |

On cards a judge scored entirely for one fighter, every round's winner is known: the model's clear
calls (65%+ either way) were right 93% of the time, its close calls 60%. The site therefore shows
rounds under 65% as "close" instead of forcing a winner, and "rounds won" is the expected number.

Round profiles were rebuilt with it: `data/published/rounds/rounds_2026_11_14_v2/`.

Next step for accuracy: official round-by-round scorecards (for example the UFCalendar scorecards API),
which would replace the estimate for every decision and give far better training labels.

## Skill profile changes (2026-11-14)

`src/upset/data/skills_view.py`: three skills now blend related measurements from the multi-skill model
instead of one narrow stat. Knockout power = knockdowns + KO/TKO wins; submission threat = attempts +
submission wins; durability = not being stopped + not being dropped. "Fights most like" now compares
what fighters do (offense weighted most, clinch and ground striking included) together with their
skill scores, and prefers the same weight class.
