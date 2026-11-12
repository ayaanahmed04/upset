# Fighter pictures update — November 3, 2026

Installed the supplied `AUpsetImages 3.zip` in `/Users/ayaanahmed/Projects/upset`.
It contains 298 PNG portraits: 101 additions and 197 byte-identical existing
portraits. All 101 new portraits have explicit permanent fighter IDs checked
against the identity registry, provider links, serving profiles and accepted
bouts. The images are copied unchanged; macOS metadata files are skipped.

The updated files are in `data/roster/media/`, `data/roster/roster.json`,
`data/roster/portrait_manifest.json` and `data/roster/portrait_import_report.json`.
Existing roster entries and roster status dates are preserved. No database
rebuild or dependency installation is needed in this existing checkout.

## Run the updated app

1. Open Terminal.
2. Paste the entire command below:

```bash
cd /Users/ayaanahmed/Projects/upset
caffeinate -i .venv/bin/python -m upset.research_app \
  --database data/processed/research_2026_11_03_v1/upset.sqlite \
  --design broadcast \
  --roster data/roster/roster.json \
  --port 8768
```

3. Open <http://127.0.0.1:8768> in your browser.
4. Press **Cmd+Shift+R** to reload the page and images.
5. Leave Terminal running. Press **Ctrl+C** in that Terminal to stop the app.
   Run the same command to start it again.

After the card update, both ports 8767 and 8768 serve the current database and
updated portraits. The app is already running; open the URL and refresh it.
For stopping a background viewer, follow `docs/MAINTENANCE_2026_11_03.md`. If
8768 is already in use and you want to leave it running, choose another unused
port (for example 8769) and use that port in the command and browser URL.

Keep the `--roster` option: it supplies the portrait links. Search by the app's
stored fighter names; nickname filenames do not change search behavior.

## Verification and identity notes

The importer's PNG validation checks passed for all 298 images. The HTTP
verification checks every portrait URL against the supplied ZIP and checks the
portrait URL in every newly linked fighter's API response. Results are recorded
in `data/roster/portrait_verification_2026_11_03.json`. The serving database and
fighter registry hashes are unchanged.

Three supplied nickname filenames were explicitly resolved to existing IDs:

- `kimbo-slice.png` → Kevin Ferguson ([UFC evidence](https://www.ufc.com/news/ufc-statement-passing-kimbo-slice)).
- `mirko-cro-cop.png` → Mirko Filipovic ([UFC evidence](https://www.ufc.com/news/mysterious-mirko-cro-cop)).
- `tank-abbott.png` → David Abbott ([UFC evidence](https://www.ufc.com/news/tank-abbott-imagines-competing-ultimate-fighter-ufc-fight-pass-read)).

Two unchanged older portraits, Gable Steveson and Salahdine Parnasse, retain
their prior registry mappings but their profiles are absent from the current
serving database. This image update preserves those assets without adding or
changing fight records. All 101 newly added portraits have serving profiles.

## Re-import this same image archive

The pictures are already installed. To repeat the import later with this exact
archive and reviewed manifest:

```bash
cd /Users/ayaanahmed/Projects/upset
.venv/bin/python scripts/import_fighter_portraits.py \
  --archive '/Users/ayaanahmed/Desktop/AUpsetImages 3.zip' \
  --manifest data/roster/portrait_manifest.json
```

Repeating an unchanged import makes no changes. New filenames in a future ZIP
need reviewed filename-to-ID mappings before they can appear on profiles.

## Restore the prior portrait collection

The importer saved the original files and checksums in
`data/processed/site_backups/portraits-20261103-222739-272715`.
To undo this portrait import, stop the viewer and run:

```bash
cd /Users/ayaanahmed/Projects/upset
.venv/bin/python data/processed/site_backups/portraits-20261103-222739-272715/restore.py \
  --project-root /Users/ayaanahmed/Projects/upset \
  --restore data/processed/site_backups/portraits-20261103-222739-272715
```

The restore refuses to overwrite files changed after this import. Restart the
viewer and refresh the browser after restoring.
