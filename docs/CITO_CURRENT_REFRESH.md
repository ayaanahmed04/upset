# Refresh later cards and update the local research snapshot

## Confirmed Mac refresh, October 5

The refresh runner completed on the Mac at code commit
`2cc6aff88ecf89f600d577ab06dd3cb751cbb7df` with a clean worktree. The supplied
review ZIP contains all 17 inventory pages, the UFC 332 raw card, normalized
current records, replay outputs and serving database manifest. All 17 page
hashes and 13 current/replay output hashes match. The fresh inventory has 812
entries. Twenty API requests captured the inventory and one later UFC card;
the September 29 DWCS episode is an explicit other-competition exclusion.

All 14 October 3 bouts were independently normalized against the saved source
totals and 50 round rows, matching the exported records. Nine have previously
reviewed identity links and enter the replay; five await identity review. Prior
canonical records and registry bytes are preserved. There are now 353 canonical
current bouts, 259 identified bouts, 94 excluded bouts and 101 unresolved
provider identities. The new card has no normalization findings. Independent
calendar completeness remains unverified.

Recomputed retrospective metrics exactly match the manifest: 160/255 decisive
picks correct (62.745098%), Brier 0.23427651402475907 and log loss
0.6603623470136253. All 250 prior probabilities are unchanged. The nine newly
replayed decisive bouts contribute six correct picks. Ten replay bouts have
directly missing participant history, and 248 follow omitted cohort bouts.
The Mac historical audit again reports zero reconstruction error. No model
was retrained and no new prospective evidence was produced.

The serving manifest reports 8,810 bouts, 17,620 stat rows, 4,455 profiles,
and latest bout October 3. Database SHA-256:
`99c39b3cb976cae41bb4bfc592d16926c9d2487f26566bce91e9edc0a84d0587`.
The database bytes were not included in this review ZIP, so this hash was not
independently checked here. The server verifies the hash at startup. Use
`data/processed/research_refresh_v1/upset.sqlite` to show this new snapshot.
An existing viewer bound to research_v2 still shows 8,799 bouts until restarted.

The broadcast redesign was independently integrated and delivered as
`upset-site-redesign.patch`; its application and fresh rendered appearance on
the Mac have not yet been confirmed. User has requested a pause after review
to discuss design flaws. Do not initiate another acquisition/model change
before that discussion.

## Confirmed October 5 checkpoint

The Mac matchup identity integration and second replay succeeded. All ten
identity-export output hashes and three replay output hashes match the uploaded
files; replay input bindings match the current identity v3 export. Independently
recomputed metrics match: 154/246 decisive picks correct (62.601626%), Brier
0.2336715796014347 and log loss 0.6589607728889539. There are 250 replayed bouts,
89 excluded canonical bouts, 96 unresolved provider identities and nine replay
bouts with directly missing participant history.

Compared with the first replay, all 248 common bouts retain their picks.
Probabilities changed for 190 common bouts; the maximum absolute change was
0.060128573059797685. The new Mark Vologdin/John Castaneda bout is a draw and
does not enter the binary score. The new Marcio Barbosa/Dennis Buzukja bout is
a correct decisive pick. The accuracy increase is therefore a cohort change,
not improved picks on the shared cohort. Canonical fights, totals and bout
provenance are byte-identical to current identity v2. The Mac historical audit
again reports zero reconstruction error. Actual frozen parameter bytes and
full historical feature files have not been uploaded for an independent rerun.

Sources still end September 26. Do not make a live forecast from an outdated
source cutoff or treat this retrospective score as prospective evidence.

## Refresh implementation

`refresh_cito_current.py` captures a new inventory in a separate dated root.
It reuses saved pages and card components on interruption, reports each new
request/card, counts failed requests, and verifies hashes before reuse. It
refuses an occupied archive root, changed date range or future through-date.
The inventory pagination uses the established collector, normally about 17
listing requests for the existing archive size; older card responses are not
downloaded again. Only UFC candidates within the requested later date range
are fetched, at up to three requests per card. The existing seven-second pace
is retained. False `hasStats` flags do not suppress these cards. DWCS and Road
to UFC entries remain explicit exclusions from this UFC history refresh.

`export_cito_refresh.py` validates event IDs/dates, endpoint agreement, paired
totals and every observed round sum using the existing current normalization.
Malformed bouts and failed cards remain in `review.json`; they cannot enter
the accepted history. New fighters remain unresolved until reviewed. Prior
canonical records, registry links and identity evidence carry forward. A new
identified subset, replay and serving database use new output directories.
Independent calendar coverage remains unverified and no model is retrained.
Neither module modifies the HTML or running viewer.

## One run on the Mac

Download `upset-current-refresh.patch` into Downloads first. Use a new terminal
if the existing terminal is running the viewer. The key is loaded from the
existing local environment; do not paste it into chat.

The runner performs all four steps below and opens the review ZIP in Finder:

```bash
cd ~/Projects/upset
if [ ! -f scripts/run_cito_current_refresh.sh ]; then
  git am --3way ~/Downloads/upset-current-refresh.patch
fi
caffeinate -di bash scripts/run_cito_current_refresh.sh
```

For reference, these are the operations contained in the runner:

```bash
bash <<'SH'
set -e
cd ~/Projects/upset
source .venv/bin/activate

if [ ! -f src/upset/data/export_cito_refresh.py ]; then
  git am --3way ~/Downloads/upset-current-refresh.patch
fi

caffeinate -di python -m upset.data.refresh_cito_current \
  --root data/raw/cito_refresh_2026_10_05_v1 \
  --from-date 2026-09-27 --through-date 2026-10-05 \
  --max-pages 50 --max-cards 20 --retry-failed

python -m upset.data.export_cito_refresh \
  --refresh data/raw/cito_refresh_2026_10_05_v1 \
  --output data/processed/cito_current_refresh_v1

python -m upset.modeling.run_current_replay \
  --current data/processed/cito_current_refresh_v1 \
  --registry data/processed/cito_current_refresh_v1/fighter_registry.json \
  --output data/processed/current_replay_v3

python -m upset.data.build_research_db \
  --current data/processed/cito_current_refresh_v1 \
  --registry data/processed/cito_current_refresh_v1/fighter_registry.json \
  --output data/processed/research_refresh_v1

zip -q -r data/processed/upset_current_refresh_review_v1.zip \
  data/raw/cito_refresh_2026_10_05_v1 \
  data/processed/cito_current_refresh_v1 \
  data/processed/current_replay_v3 \
  data/processed/research_refresh_v1/manifest.json

open -R data/processed/upset_current_refresh_review_v1.zip
SH
```

This normally takes a few minutes, depending on provider response times and
how many later cards are listed. Saved components are reused on resume. If a
failed card is repaired after an export already exists, give normalization,
replay and database new output names; completed exports are immutable.
The ZIP contains the fresh source responses and resulting current records,
predictions and database manifest, not another copy of the entire old archive.

To view the new database alongside the existing viewer, in a separate terminal:

```bash
cd ~/Projects/upset
source .venv/bin/activate
python -m upset.research_app \
  --database data/processed/research_refresh_v1/upset.sqlite --port 8766
```

Open http://127.0.0.1:8766. It serves the same editable
`src/upset/web/research.html`. The original viewer on port 8765 continues to use
its old database until restarted with a new database path.

Next after inspecting the refresh: review remaining identity gaps in batches,
reconcile the upcoming schedule and freeze externally dated prefight forecasts.
New round/trend feature experiments can proceed as a separate preregistered
comparison; the current replay score is not evidence for changing the model.
