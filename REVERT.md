
## 2026-11-12 round-by-round factors
New files only: `src/upset/ratings/round_research.py`, `tests/test_round_research.py`,
`docs/ROUND_FACTORS_2026_11_12.md`, `data/processed/round_research_2026_11_12_v1/`.
Nothing on the site or in the forecast changed. To undo, remove those files.

## 2026-11-13 round-by-round panel and standard strike notation
- Round panel: remove it with `python3 backups/claude-refresh-2026-11-10/blocks/splice.py --remove round-profile`,
  and take the `--round-profiles` line out of `Start UPSET.command`. The backend route only answers when that flag is given.
  Earlier copies: `backups/claude-polish-2026-11-11/before-rounds-2026-11-13/`.
- Strike notation (compare page shared opponents and fight history): earlier copies are in
  `backups/claude-polish-2026-11-11/before-strike-format-2026-11-13/`.

## 2026-11-14 UFC 334 re-locked with forecast 5.2
New folder `data/published/picks/ufc-334-r2/` (the 5.1 lock in `ufc-334/` is untouched). Code copies before
the change: `backups/claude-polish-2026-11-11/before-relock-2026-11-14/`. To go back to the 5.1 lock, move
`ufc-334-r2` out of `data/published/picks/`; nothing else needs to change.

## 2026-11-14 learned round scoring, blended skills, colours, stars under the badge
Copies from before: `backups/claude-polish-2026-11-11/before-accuracy-2026-11-14/` and `before-hero-stars-2026-11-14/`.
To return to the hand-picked round score, point `--round-profiles` in `Start UPSET.command` back at
`data/published/rounds/rounds_2026_11_13_v1` and restore `round_profiles.py` (VERSION v1) from the copy.
