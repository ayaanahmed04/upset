# October 31 card and homepage update — November 3, 2026

The viewers on <http://127.0.0.1:8767> and <http://127.0.0.1:8768> now serve
`data/processed/research_2026_11_03_v1/upset.sqlite`. The homepage features
**Waldo Cortes Acosta vs Johnny Walker**, matching the
[official November 7 event](https://www.ufc.com/event/ufc-fight-night-november-07-2026).
The source change is the existing `PICKS` selection only. Overall professional
records supplied with the request were not substituted for the app's UFC-only
record calculations. Johnny Walker was not in the supplied portrait archive;
his comparison uses the existing initials fallback. Waldo's supplied portrait
is linked and serves successfully.

## Recent card

All 12 completed bouts from **Moicano vs Nolan, October 31, 2026** were added.
The database now has 4,469 profiles, 8,866 bouts and 17,732 fighter-stat rows.
All 4,464 prior fighter rows, 8,854 prior fight rows and 17,708 prior statistical
rows are preserved exactly. Five reviewed new identities are Farman Hasanov,
Dakota Hope, Theodor Berggren, Joe Kropschot and Lucia Szabová. Missing profile
measurements/DOBs remain null; no active status or portrait was invented.

The import retains the prior 89 excluded bouts. Newly reviewed provider links
do not automatically admit older excluded fights. Provider-inventory acquisition
is not independent whole-calendar coverage certification; coverage_verified
remains false. No winner model was fitted, replayed or changed.

Evidence:

- [Official UFC scorecards](https://www.ufc.com/news/ufc-fight-night-moicano-vs-nolan-official-scorecards).
- [Main-card results](https://www.ufc.com/news/ufc-fight-night-moicano-vs-nolan-results).
- [Preliminary results](https://www.ufc.com/index.php/news/ufc-fight-night-moicano-vs-nolan-prelim-results).
- Saved Cito event/bouts/stats responses and five profile/history bundles.

The new raw snapshot used four requests (one inventory page and three card
components). Ten additional requests captured the five new identities' profiles
and histories. Credentials were loaded from the existing local environment and
were not printed or saved in artifacts. No account/subscription changes occurred.

## Explicit source handling

- Two `TKO - Doctor's Stoppage` methods are normalized to the existing KO/TKO
  category, with original labels and review evidence retained separately.
- Four Zachary Reese stat rows use `Zach Reese` and lack slugs. An explicit
  provider-ID, bout-ID and source-row-ID rule supplies the known participant's
  slug. Numeric measurements and source IDs are unchanged; all round sums pass.
- Kropschot/Klein is retained as round 2 at 1:25, consistent with Cito's bout,
  fighter history and two recorded rounds. UFC's scorecard/prelim headings say
  round 3, while the prelim narrative describes the finish in round 2. That
  disagreement is documented in the review rules; no additional round was made up.

The initial generic refresh export is a staging artifact, not the serving
cohort: it rejected three bouts and would also have admitted four previously
excluded bouts when recalculating links. The reviewed import instead uses the
prior accepted cohort plus exactly the 12 reviewed new bouts.

## Artifacts and verification

- Acquisition: `data/raw/cito_refresh_2026_11_03_v1`.
- Identity evidence: `data/raw/cito_identity_review_2026_11_03_v1`.
- Explicit rules: `data/mappings/cito_2026_11_03_reviewed_card.json`.
- Offline importer: `scripts/import_recent_card.py`.
- Reviewed current cohort: `data/processed/cito_current_2026_11_03_reviewed_v1`.
- Serving database: `data/processed/research_2026_11_03_v1`.
- Live cutoff checks: `data/processed/maintenance_2026_11_03_live_checks.json`.
- Pre-edit source backup and viewer commands/logs: `backups/maintenance-20261103-card-feature-v1`.

All 12 bouts reconcile reported totals against all 64 observed fighter-round
rows. SQLite integrity, foreign keys and exact prior-row preservation passed.
All 24 participant cutoff checks exclude the card on October 31 and include it
on November 1. The featured comparison, Waldo portrait, Johnny fallback and
homepage passed API/browser checks. Browser verification showed 4,469 profiles,
8,866 bouts through October 31 and the requested matchup. Relevant tests total
88 passes, including 37 new striking/import tests; JavaScript UI, Ruff and Git
whitespace checks passed.

Only the two listener processes whose full commands, project working directories
and ports were verified were restarted. Their replacement commands and logs are
recorded in `viewer-processes.json` inside the backup. Frozen defense source,
protocols, seed and hashes remain valid. The separate striking prototype uses
the original October 24 snapshot, not this new card.

## Run or restart

The app is already running. Open <http://127.0.0.1:8768> and press **Cmd+Shift+R**.
For a future restart after stopping that viewer:

```bash
cd /Users/ayaanahmed/Projects/upset
caffeinate -i .venv/bin/python -m upset.research_app \
  --database data/processed/research_2026_11_03_v1/upset.sqlite \
  --design broadcast \
  --roster data/roster/roster.json \
  --port 8768
```

Leave Terminal open; Ctrl+C stops a foreground viewer. For a viewer started in
the background, inspect its listener before stopping it:

```bash
lsof -nP -iTCP:8768 -sTCP:LISTEN
```

Check the returned PID's command with `ps -p PID -o command=` and stop only the
verified UPSET viewer with `kill -INT PID`. PIDs change; never copy an old PID
from a document. If you want to leave it running, use `--port 8769` and open
<http://127.0.0.1:8769> instead.

To roll back the dataset, stop the viewer and use the same launch command with
`--database data/processed/research_2026_10_25_v1/upset.sqlite`. No championship
ledger change was needed for this card. To undo the homepage selection, replace
only the `PICKS` names with `Renato Moicano` and `Tom Nolan`; retain later source
changes. The previous HTML is also available in the backup for comparison.
