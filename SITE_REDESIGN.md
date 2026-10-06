# UPSET site redesign

Latest accepted checkpoint: `docs/HANDOFF_2026_10_05_FINAL.md`. Original broadcast
design retained; Ayaan creator bio and square controls added. Earlier pending
Mac notes below describe the initial integration, not the final checkpoint.

The fighter research site has been redesigned in a fight-night broadcast style. It uses
the vertical UPSET logo and a blood-red accent.

## Run it

```
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -e .

python -m upset.research_app \
  --database data/processed/research_v2/upset.sqlite
```

Open http://127.0.0.1:8765. The headline font (Russo One) loads from Google Fonts, so
it needs an internet connection. Without one, it falls back to a system font.

Optional: add `--roster path/to/roster.json` to show ACTIVE badges and fighter
photos. The file format is described in `src/upset/web/ROSTER.md`.

If the original viewer is still running on port 8765, start this version in a
new terminal with `--port 8766` and open http://127.0.0.1:8766. The new HTML needs
the new server API; refreshing an old running server is insufficient.

## Changed files

| File | What changed |
|---|---|
| `src/upset/web/research.html` | Rebuilt the front end: home page, fighter page, matchup page and mobile layout |
| `src/upset/research_app.py` | New API fields, division percentiles, optional roster, and a `/assets/` route |
| `src/upset/web/assets/upset-vertical.png` | Vertical logo with the fist in blood red, on a transparent background |
| `src/upset/web/assets/favicon.png` | Fist icon for the browser tab |
| `src/upset/web/assets/grunge.jpg` | Worn texture used on fighter names and headlines |
| `src/upset/web/ROSTER.md` | Format for the optional roster file |
| `pyproject.toml` | Package data now includes `web/*.md` and `web/assets/*` |

Nothing in the data pipeline, the modeling code or the database changed.

## What the site shows

- **Home:** "Every fighter. Every fight. One place." with archive counts and a featured matchup.
- **Fighter page:**
  - Record, streak and last-10 results.
  - Tale of the tape: height and reach in feet and inches, weight in lb and kg, age at the cutoff date.
  - Division percentile bars for striking and grappling.
  - Strike map, finish methods, a fight-by-fight striking chart and full fight history.
- **Matchup page:** red and blue corners, a tale of the tape with reach and height edges, and head to head. Each head-to-head stat shows the raw number, its unit and the fighter's division percentile.
- **Controls:**
  - Last 3, 5 or 10 fights, or Career.
  - A "Before" date that counts only fights strictly before it.
  - Search ranked by number of UFC fights.
  - Shareable links: `#/fighter/<id>` and `#/compare/<a>/<b>`.

## API additions

All existing response fields are unchanged. I checked this against the previous version
on 456 real-data fighter/date/window combinations: 38 fighters, four windows,
and three cutoff dates. Every existing response value matched exactly.

- **`/api/fighter` and `/api/compare`:**
  - `summary`: UFC record, streak, first and last fight, division, title fights, age at cutoff.
  - `percentiles`: each stat ranked against same-division fighters with at least 3 timed fights and 15 minutes in the same window and cutoff. The first request for a given cutoff and window takes about 1 second; after that it is cached.
  - `roster`: present only when you start the server with `--roster`.
  - New stats in `metrics`: submission attempts per 15 minutes, strikes landed by target and by position, results by method.
  - Each history entry adds method group, round, time, weight class, division and a title-fight flag.
- **`/api/fighters`:** results are ranked by number of recorded fights and include division and last fight date.

## Integration review, October 5

Only the changed site files were merged into the current project. The complete
ZIP includes an older source snapshot and should not replace the latest
pipeline. Source exports, frozen models and database contents are unchanged.

The uploaded actual research_v2 database was independently hashed and read:
4,455 profiles, 8,799 bouts, 17,598 stats rows; SHA-256
`52d9463d2ae764650af578b37f63c19b6512ea000284415eb1e44e9d8516df56`.
This database still has 248 current identified bouts. The later matchup
integration/replay uses 250; a new database build is needed to reflect that
cohort in the viewer. The current-card refresh runner handles that separately.

Corrections during integration:

- Even-size percentile pools use the average of the two middle values as the
  median. Ties use midrank percentiles rather than a strict "better than" claim.
- The footer explicitly states the all-divisions fallback when fewer than 25
  fighters qualify in a division. The scope is also visible beside each rank.
- Optional roster status is withheld before its observation date, and expires
  after 62 days. This check is enforced in the API as well as the interface.
- Roster JSON shape/date and image/asset routes are validated.

Validation: 495 tests plus 16 subtests pass; Ruff clean. Real-data initial
Career percentile calculation took approximately 0.66 seconds in this
environment; the repeated same-date/window calculation was cached. This is an
observed timing, not a latency guarantee.

The supplied desktop/home/fighter/matchup and mobile renders were inspected.
The cloud browser cannot open this workspace's localhost server, so a fresh
rendered browser interaction check was not completed here. API tests cover
the new ranks, roster date limits and asset serving. Verify the rendered
search, date/window controls and mobile layout on the Mac using the command
above. Optional portraits and active status require an evidence-backed roster;
the default remains monograms and unknown contract status.
