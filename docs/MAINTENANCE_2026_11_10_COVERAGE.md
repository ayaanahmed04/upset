# November 10 coverage and viewer release

The `nov10-coverage` launcher release uses the reviewed v3 database and archive. It has 4,526 fighter profiles, 8,968 fights with paired stats, and 17,936 fighter stats rows. The latest recorded event remains November 7, 2026. The final pass added 60 fights and 130 reconciled rounds. Across both coverage passes, 75 fights were added and 417 of 418 captured recent bouts are reviewed. The final pass preserved all 4,493 prior profiles, 8,908 fights, and 17,816 stats rows.

The remaining pending bout is Stephanie Luciano vs Marina Spasić at UFC Belgrade. The UFC reports a submission at 3:30 of round one. The captured totals and round data end at 3:20. The event page exposes the discrepancy and links the official scorecard. The dated evidence and 55 identity decisions are in `data/mappings/cito_2026_11_10_coverage_completion.json`. The Chilean welterweight Victor Valenzuela was linked to his existing profile using the dated Max Griffin result and athlete measurements. The other same-name profile remains separate. [UFC Belgrade scorecards](https://www.ufc.com/news/ufc-belgrade-official-scorecards) · [Victor Valenzuela](https://www.ufc.com/athlete/victor-valenzuela-0)

The eight official UFC 1 results are in `data/processed/ufc1_results_2026_11_10_v2`. They count toward reviewed UFC records and appear in fight history. Paired stats and ratings require separate recorded evidence. Royce Gracie's reviewed UFC record is 11–1–1. His cutoff before November 13, 1993 shows the three UFC 1 wins. [UFC 1 event](https://www.ufc.com/event/ufc-1)

## Viewer features

- Events includes the verified 13-bout UFC 334 schedule, the countdown, 33 recent captured cards, and UFC 1. Fight pages show paired totals and rounds where available.
- Time Machine has four dated presets. A pre-fight link excludes bouts on the event date. Direct links preserve the cutoff and selected stats window. Matchups have Open Graph metadata and a downloadable 1200 × 630 card. Legacy hash URLs remain usable.
- Profiles and matchup tables show 29 dated professional MMA records, covering all UFC 334 fighters and three additional profiles. Earlier cutoffs hide the November 10 snapshot. [UFC 334 preview](https://www.ufc.com/news/fight-fight-preview-polymarket-ufc-334-gane-vs-hokit) · [UFC Brazil fighter records](https://www.ufc.com.br/news/conheca-lutadores-brasileiros-ufc-334)
- Matchup keys show sample minutes, pre-fight opponent grade coverage, striking pace, takedown attempts, and defense counts for the selected window.
- Upset Tracker found 532 wins from the lower grade in 1,416 eligible decisive bouts. Both fighters require five recorded UFC bouts and a grade updated within 730 days. It shows biggest gaps, latest results, repeat winners over the final 365 days of the archive, and close experimental grades on the scheduled card.

## Release and recovery

The reproducible import commands use versioned output folders and their associated rule files.

```sh
.venv/bin/python scripts/import_reviewed_coverage_2026_11_10.py
.venv/bin/python scripts/import_reviewed_coverage_2026_11_10_v3.py
```

The second command builds the new registry, archive, and SQLite database. Rating versions v1 through v4 and the striking preview were rebuilt against that database with the existing November 8 exclusive cutoff and serving gates. The launcher retains the matched November 10 portrait roster. Pro records were rebound to the verified new database hash and checked against each linked fighter's UFC counts. UFC 1 was rebuilt from its reviewed result file. Build and launch logs are in `backups/coverage-events-2026-11-10.ZLLfpe`.

The Mac and Wi-Fi viewers passed independent checks for all 75 added bouts, both fighters' stats, the pending result, UFC 1, pro records, historical cutoffs, PNG downloads, and the tracker. The Python suite passed 832 tests and 16 subtests. All three JavaScript suites passed.

For the previous paired-data release with pro records and UFC 1, run `UPSET_DATA_RELEASE=nov10-records ./Start\ UPSET.command`. For the Wi-Fi viewer set `UPSET_BIND_HOST=192.168.4.75 UPSET_PORT=8769` or substitute the Mac's current Wi-Fi address. The Mac viewer uses port 8768. Stop only the identified process on the target port before relaunching. The pre-release source backup is `backups/coverage-events-2026-11-10.ZLLfpe/before-complete-coverage.tar`. Inspect its contents before restoring files.

## Frozen UFC 334 forecast

The prospective ledger at `data/processed/rating_prospective_ufc334_2026_11_10_v2` contains 12 forecasts for the 13 scheduled bouts. The extension preserved the original ten probabilities and timestamps. The results-only baseline study and the frozen predictions are independent of the viewer grade tracker. Settlement uses the verified result database after the event and writes a fresh report.

```sh
.venv/bin/python -m upset.ratings.settle_forecasts \
  --ledger data/processed/rating_prospective_ufc334_2026_11_10_v2 \
  --database path/to/verified/post-event/upset.sqlite \
  --output data/processed/rating_settlement_ufc334
```
