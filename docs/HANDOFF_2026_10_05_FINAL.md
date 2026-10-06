# UPSET — complete checkpoint and next-chat handoff

Prepared October 5, 2026, America/Chicago (October 6 UTC). Owner: **Ayaan Ahmed**.
Read this before making changes. It supersedes pending-state statements in the
older handoffs; those remain useful as evidence and history.

## 1. Immediate instructions to the next chat

Ayaan deliberately stopped this long conversation. Resume only when he is
ready. The accepted website is the **original broadcast design**, with his
creator biography and **rectangular UI controls/panels everywhere**. He rejected
the editorial makeover. Do not revive it, propose another wholesale redesign,
reacquire the archive, or rerun old experiments as an opening move.

First read this handoff and inspect the actual branch and local files. Explain
the state plainly. The next likely work is incremental design feedback, then
identity/coverage completion and genuine dated forecasts. Let Ayaan steer that
choice. A read-only research product already works; unfinished prediction
validation does not prevent using or improving the analytics interface.

Communication requirements:

- Give one complete installation message: one clearly named download, one
  copy/paste command block, exact URL and whether to stop/restart the server.
- Distinguish an installation file from a standalone preview. Do not send an
  API-dependent HTML file as though clicking it in ChatGPT runs the site.
- Make reversible backups before UI replacement. Preserve his own local edits.
- Keep him informed during sustained work; avoid loops of permission requests,
  repeated uploads, vague placeholders and instructions spread across messages.
- Do not claim to have changed his Mac, verified an installation, pushed a
  branch, read a database or rendered a page without actual evidence.
- Do not delegate to subagents unless he explicitly requests it.
- Do not alter raw responses, frozen historical labels or model coefficients
  as part of a website change.

## 2. Repositories and branch distinctions

GitHub repository: `https://github.com/ayaanahmed04/upset`.
Mac checkout: `~/Projects/upset`, editable Python package, `.venv`.
Last repeatedly reported Mac branch: `feature/asof-prefight-features`.
Numerous features reached that branch through cherry-picks and later mail
patches, so Mac commit IDs differ from assistant-source IDs.

Assistant source checkout used in this conversation:
`/workspace/scratch/9caae375a4d6/upset`.
Its working branch was `feature/cito-archive-collection`, with latest UI commit
`207de5fc64e966a2c298e3afa1e290b031fcfadf` before this handoff commit.
That local branch contains a consolidated stack much newer than the similarly
named published archive-collector branch. Before publication, remote
`feature/cito-archive-collection` was still
`f6779422297a76a562012f81124d4d2ddb14ef51`.

The publication target for this checkpoint is a **separate branch**:
`feature/upset-broadcast-handoff-2026-10-05`.
Direct Git push lacked credentials in this workspace. Publication therefore
uses the connected GitHub account to create a consolidated **source snapshot**
commit with main as its parent. It preserves the current files without moving
`main`, changing old feature branches or rewriting the Mac branch. The local
intermediate commit IDs and backup tags are not newly published by this route.
The final chat reply records the confirmed publication SHA. Verify that branch remotely when
resuming; this document cannot include the SHA of its own enclosing commit.

**Do not instruct Ayaan to blindly pull/merge this snapshot onto his Mac.**
Cherry-picked history, local design edits and bundled HTML make that unsafe as
a routine synchronization method. First inspect `git status -sb`, branch and
recent log, then compare changed files. A new read-only checkout is safer for
review. No merge to main or production deployment was requested.

Git ignores `data/raw/*`, `data/processed/*`, `.env*`, virtualenv/build/cache
files. Tracked `data/mappings/` contains reviewed identity evidence and registry
files, not the raw/processed provider archive. SQLite databases, paid responses,
model artifacts and private prediction outputs are not part of this push.

## 3. Where the phases stand

The actual `ROADMAP.md` uses these phases; development has overlapped them.

| Phase | Current position |
| --- | --- |
| 0 — Foundation | Python, Git, package, dependencies and test infrastructure established. |
| 1 — Data Foundation | Historical canonical data/identities and extensive Cito acquisition work; large archive retained, coverage and some identity gaps remain. |
| 2 — Advanced Analytics | Descriptive offense/defense, recent windows, control, breakdowns and division percentiles available. Broader power/cardio/durability ratings remain research ideas. |
| 3 — Machine Learning | Multiple historical studies, symmetric reference, frozen artifact and dated reconstruction implemented; current completed-bout replay works. Genuine prospective validation remains outstanding. |
| 4 — Product | Working private SQLite/API/local website, redesigned and iteratively fixed. Upcoming-fight product, production API/deployment and public launch are unfinished. |
| 5 — Expansion | Other promotions, market/betting tools, mobile and other sports deferred. |

We are moving ahead, not blocked waiting for all data to become perfect. The
unfinished items are measurable: identity links, independent coverage checks,
fresh forecasts and deployment scope. Do not equate a large archive or a good
retrospective score with those items being finished.

## 4. Data acquisition history — do not repeat this work

Historical development source is the accepted José Silva Kaggle UFC snapshot:
**4,455 profiles, 8,551 bouts, 17,102 paired fighter-stat rows**, March 11, 1994
through March 7, 2026. It is not an independently certified complete calendar.
Names are labels, never permanent identity keys. UPSET identities are UUIDs;
provider IDs are separate evidence-backed links. Seven name collisions and
46 ambiguous participant slots were resolved with reviewed evidence.

Cito Pro was purchased September 28 for **one paid period only**. Support quoted
$59/month; Ayaan often referred to $60. Renewal/cancellation state was not
verified here. Do not assume the exact renewal date, cancellation or another
month of funding. Check the dashboard if needed, without exposing his key.

The archive inventory captured **812 entries in 17 pages**. Inventory hash:
`65d4d3e73ea6eded330aa4918d8ce45d5a6ae899670904dd261cf1f66cd4b444`.
Original collection eventually captured 755 cards after retrying four failures.
One remaining failed Road to UFC event had an unexpected detail shape; twelve
future entries were deliberately unvisited. Initially 44 entries were skipped
because the provider said no stats.

Crucial discovery: **35 UFC cards marked `hasStats=false` actually returned
stats**. We probed them, cached the responses, then recovered the card/event
and bout components with 70 further requests. Final original archive:
**790 captured cards**, nine no-stat other-competition entries, one failed
other-competition detail and twelve then-future entries. Do not repeat those
requests or treat the provider flag as reliable.

Archive v4 audit:

- 8,909 listed bouts; 8,867 eligible completed stat-bearing bouts.
- 8,865 structurally complete and observed-field-reconciled bouts.
- 8,684 fully numerically reconciled bouts; 181 had unavailable fields.
- Twelve findings remained. Missing control is preserved as null, not zero.
- March 14, 2026: all 14 bouts structurally complete after reviewed aliases.
- June 6, 2026: all 12 bouts structurally complete.
- These checks do not prove independent event/bout calendar completeness.

The offline bridge staged **41,802 fighter-round rows** from 790 cards. The
first verified historical totals matched 8,531 accepted bouts. Scoped reviewed
aliases for Magomed Bibulatov/Bibulatov Magomed and Kai Kamaka/Kai Kamaka III
added seven. Exported historical rounds initially contained **8,538 bouts and
40,268 rows**, with 432 rows lacking control.

Targeted gap probes made **48 requests** (30 primary targets and fallbacks).
Most responses remained unavailable or required provider review; endlessly
repeating them is not a productive default. Offline reconciliation added two
historical bouts/eight rounds, reaching **8,540 historical bouts and 40,276
round rows**. **Eleven accepted historical bouts still lack verified rounds**.
They retain historical fight totals and can appear in the research viewer.
Two current bouts received totals derived from complete, reconciled rounds;
that derivation is explicitly recorded instead of pretending provider totals
were supplied.

Important source exceptions from support:

- `ufc-315` dated May 10, 2026 was a stray copy of the May 2025 card, no stats.
- July 18: numeric bout `12960` duplicates `9e525f939fba3e73` (Ezra Elliott).
- April 25: bout `84951374e4cdc679` repeats Rafa Garcia under two IDs with
  identical stats; do not double-count.
- UFC 326 March 7 US evening is March 8 UTC; keep source date semantics explicit.
- DWCS and Road to UFC may lack stats. Classification does not justify dropping
  an already accepted historical bout that needs a targeted exception review.
- Main/prelim positions and judges' scorecards were not uniformly complete.

Acquisition uses resumable caching, checksums and paced requests. A completed
inventory is deliberately immutable; the 'Inventory already complete' error
was protection, not a crash or data loss. Card recollection reports zero
attempts when already captured. `caffeinate -i` prevents idle system sleep but
does not keep the display on; `-di` was used later. The completed archive took
many hours because of request pacing and endpoint latency, not one unbounded
unlogged scrape. No collection is known to be running now.

## 5. Current cohort and identities

Initial post-snapshot normalization had **339 bouts, 678 stat rows, 1,534
round rows**, zero bout-validation issues: 337 provider totals reconciled with
rounds, two derived from complete rounds, four draw/NC bouts. Initially 245
bouts linked to existing UPSET identities, 94 excluded and 101 provider IDs
unresolved.

We collected **303/303 successful fighter-bundle responses** (profile, career
stats, history for 101 IDs). All response hashes were checked. The profiles
had **no source DOB and no UFCStats crosswalk**. Review created 43 candidate
records (18 conflicting evidence, 25 requiring review), not automatic links.
Thirteen profiles had findings; four had career aggregates below the already
captured current cohort (Shanelle Dyer, Mark Vologdin, Kurtis Campbell and
Victor Valenzuela). Do not substitute those aggregates for verified bout stats.
Victor's old Joe Boxer profile versus current Psicosis history is a specific
collision concern. No invented DOB from age or fuzzy-name identity merge.

Three explicitly reviewed historical identities were integrated offline:
248 identified bouts, 91 excluded, 98 unresolved. Two additional reviewed
dated public matchup links for **Mark Vologdin and Marcio Barbosa** then brought
the cohort to **250 identified bouts, 89 excluded, 96 unresolved**. Those
public observations were matchup identity evidence, not independent outcome
verification. Current source records and frozen original registry remain intact.

Latest completed refresh, October 5:

- Separate immutable raw root `data/raw/cito_refresh_2026_10_05_v1`.
- 812-entry new inventory, all 17 page hashes verified.
- Twenty API requests: inventory plus the October 3 UFC 332 card.
- Fourteen new canonical bouts and fifty round rows, all independently
  normalized/reconciled against the uploaded saved responses.
- Nine new bouts already had reviewed identities; five await review.
- Current totals: **353 canonical bouts, 259 identified, 94 excluded,
  101 unresolved provider identities**.
- September 29 DWCS was an explicit other-competition exclusion.
- Prior canonical records and registry preserved; no model retrained.

Relevant processed snapshots on the Mac:

| Path | Purpose |
| --- | --- |
| `data/processed/cito_current_archive_v1` | Original normalized 339-bout current archive. |
| `data/processed/cito_current_identity_v2` | Three reviewed historical links, 248 identified bouts. |
| `data/processed/cito_current_identity_v3` | Two additional matchup links, 250 identified bouts. |
| `data/processed/cito_current_refresh_v1` | October 3 append, 353 canonical/259 identified. |
| `data/processed/cito_historical_rounds_v1` | Accepted historical-round subset and result overlay. |
| `data/processed/cito_gap_reconciliation_v1` | Separate gap supplement. |
| `data/raw/cito_fighter_bundles_v1` | Already downloaded fighter evidence; do not collect again. |
| `data/processed/cito_fighter_review_v1` | Offline observations and unresolved proposals. |

Independent completed UFC calendar coverage still requires checking. A
`coverage_verified=false` manifest is an honest limit, not proof the data is
unusable. Unlinked fighters need evidence review, not necessarily new UUIDs;
some match historical profile-only identities. Use replay's priority queue to
work on identities that block bouts or cause missing prior history first.

## 6. Results, amendments and same-date bouts

Three reviewed current-result overlays are separate from frozen historical
training labels:

1. **Idiris–Osbourne**, February 21, 2026, `7ffdaa44fc8d111b`: overturned NC/no
   winner after a positive hydrochlorothiazide test. Ayaan supplied the Texas
   regulator explanation; other reviewed records corroborated overturning.
   Frozen Idiris win retained. Exact amendment effective date is unknown.
2. **Brundage–Abdul-Malik**, June 14, 2025, `08c04f18b0f58d71`: currently a
   majority draw, frozen source remains separately preserved.
3. **Bellato–Craig**, same date, `13e2ff8b3a122094`: NC. Source clocks disagree
   4:58 versus 4:59; reviewed display time stays unknown with both evidence
   values retained. Do not silently choose one.

The first serving build failed with 'Duplicate or unknown research fight
identity'. This was fixed by preserving distinct same-source same-date bouts:
Silveira/Sakuraba on December 21, 1997, source bout IDs `ec1bda9a4c2aab42` and
`2750ac5854e8b28b`. Duplicate IDs and cross-provider duplicate dated matchups
still fail. Do not reintroduce pair+date uniqueness across these valid records.

## 7. Model — what the accuracy actually means

The working research reference is a **36-feature symmetric recent + Elo
logistic model**. Mirrored training/symmetric inference enforce complement
probabilities when fighters swap. It is frozen, reproducible and not promoted
as a validated live predictor. Numeric JSON parameters are stored in the
existing filename `model.bin`; do not treat it as an arbitrary pickle.

Frozen model SHA-256:
`55bf4a6f363c9c45bd3db008b74faab5927318b6614836e440024f52d9c8894c`.
It was fit on **8,400 decisive historical bouts through March 7, 2026**.
The Mac's dated feature reconstruction matched **8,551 bouts, 17,102 fighter
rows and 36 columns with zero maximum absolute error**. Full private fit files
and frozen artifact bytes were not independently rerun in this workspace.

Completed current replays:

| Replay | Replayed / decisive | Correct | Accuracy | Log loss | Brier |
| --- | --- | --- | --- | --- | --- |
| `current_replay_v1` | 248 / 245 | 153 | 62.44898% | 0.65861910 | 0.23349349 |
| `current_replay_v2` | 250 / 246 | 154 | 62.60163% | 0.65896077 | 0.23367158 |
| `current_replay_v3` | 259 / 255 | 160 | 62.74510% | 0.66036235 | 0.23427651 |

These pooled metrics were independently recomputed from uploaded predictions.
They are **retrospective pipeline diagnostics**, selected linked cohorts, not
forecasts archived before those fights. The v1→v2 score increase came from a
new correctly picked Barbosa bout; the other added Vologdin bout was a draw.
All 248 common picks stayed the same, while 190 probabilities changed as the
added history propagated (maximum change 0.06012857). V2→v3 retained all 250
prior probabilities; nine new decisive bouts contributed six correct picks.

Latest replay flags: ten bouts have direct missing participant history; 248
follow omitted cohort bouts. Even no direct participant gap does not prove
complete features: population shrinkage priors and Elo can depend on missing
bouts indirectly. `source_availability_reconstructed=false` and
`prospective_evidence=false` remain accurate. Date filtering alone does not
prove a source value was available before a historical fight.

62.7% is encouraging for this diagnostic, but do not claim a validated 75%
model, profitable betting edge or improvement from the UI. An externally dated
market comparator and simple baselines are future evaluation work.

Historical studies already examined the development folds and the later
2023–March 2026 period. That later period is **not a fresh holdout**. The recent
model scored 784/1,260 (62.22%) there versus 767 (60.87%) for its comparator;
paired accuracy uncertainty included zero. The opponent-adjusted study added
six strike/takedown residual/exposure features: 1,094 versus 1,071 correct out
of 1,857, but log loss/Brier worsened. It was not takedown-only or a model
promotion. Repeated slicing of those folds is exploratory, not fresh evidence.

### Claude second opinion and remaining source discrepancy

Ayaan pasted Claude's independent recent-group review. It reported agreement
with the 1,857 decisive prediction rows, all twelve variants, reference
1,071/1,857 versus `add_takedowns` 1,095, exact symmetry, and group experiments
showing gains mainly where both fighters have history. Treat that pasted
review as a reported independent review, not a new rerun performed at shutdown.

Its observation that recent columns overlap career-rate families is checkable;
its claim that this establishes **why** the full model underperforms is too
strong. Correlation/conditioning and the impact of regularization still need
measurement. Statistical noise, repeated comparison selection and dependence
remain alternative explanations. Log loss, Brier and ten-bin ECE are different
quantities; better log loss does not necessarily give lower ECE. Cheap flip
sign tests ignore fighter/date dependence and repeated comparisons.

Proposed recent-minus-career 'trend' is not automatically independent of career
rate. With career retained, replacing recent with recent-minus-career is an
invertible linear reparameterization of the same two signals; a penalized model
may change because scaling/penalty geometry changes. It is not automatically
a genuinely new-information hypothesis or a fresh test on the same folds.
Specify a preregistered design and evaluation before treating it as progress.

**Important repository gap observed at shutdown:** this consolidated checkout
does NOT contain `src/upset/modeling/recent_groups.py` or
`run_recent_groups.py`, although the earlier conversation and Claude refer to
them. Do not invent their presence or rebuild them from memory. Locate the
original branch/files/outputs on the Mac or retained uploads if that experiment
is resumed. The existing recent-history builder here is
`src/upset/data/prefight_recent.py`, export `export_prefight_recent.py`.
Matchups are built in `matchups.py`/`export_matchups.py`; defensive history in
`prefight_defense.py`/`export_prefight_defense.py`. Claude originally requested
the actual groups module, these upstream builders and the group experiment's
`manifest.json`/`predictions.jsonl` to review definitions and calculations.

## 8. Serving database snapshots — do not confuse them

| Snapshot | Bouts / stat rows | Latest date | Status |
| --- | --- | --- | --- |
| `research_v1` | 8,796 / 17,592 | September 26 | First working 245-current-bout build. |
| `research_v2` | 8,799 / 17,598 | September 26 | 248-current-bout build; actual database uploaded and inspected. |
| `research_refresh_v1` | 8,810 / 17,620 | October 3 | 259-current-bout build; manifest reviewed, SQLite bytes not uploaded. |

All report 4,455 profiles. DB v2 SHA:
`52d9463d2ae764650af578b37f63c19b6512ea000284415eb1e44e9d8516df56`.
Refresh DB reported SHA:
`99c39b3cb976cae41bb4bfc592d16926c9d2487f26566bce91e9edc0a84d0587`.
The server verifies the accompanying manifest hash on startup. Do not claim
the refresh database's bytes were independently inspected here.

The latest visible Mac screenshot was **127.0.0.1:8767**, showing the original
broadcast site with **8,799** bouts and a September 26 endpoint: it was serving
`research_v2`, even though the newer refresh was built. An HTML replacement
does not switch databases. Restart with the refresh DB only if deliberately
updating the displayed cohort; no rebuild or acquisition is needed just for
that switch.

The actual v2 SQLite was available in this workspace at
`/workspace/scratch/34b858854736/site-redesign-full/upset-site/data/processed/research_v2/upset.sqlite`.
Transient paths may disappear between chats. GitHub does not contain it.
Do not ask for the entire paid archive just to inspect the UI. For a full local
run a collaborator needs source/assets, SQLite and its adjacent manifest,
Python/dependencies; for styling review HTML and assets suffice. API changes
also need `research_app.py`; packaging changes need `pyproject.toml`.

## 9. Accepted website and exact UI decisions

The external redesign arrived as `upset-site-complete.zip` and a changes-only
ZIP. **Only changed site files were integrated**; the complete ZIP contained an
older project snapshot and must not replace the current pipeline.

Accepted direction: fight-night broadcast, near-black surfaces, blood-red
accent, red/blue corners, vertical UPSET fist logo, Russo One headings and
grunge texture. Home still says 'Every fighter. Every fight. One place.' with
the three counters and featured Oliveira/Holloway matchup. This wording was
not changed after rejecting the editorial experiment.

Original redesign features retained:

- Career default; Last 3/5/10 controls and strict 'Before' cutoff.
- Ranked name search, keyboard arrows/Enter, `/` focus shortcut; profile-only
  fighters visibly have no recorded bouts.
- Fighter record/streak/history, tape measurements, division percentile bars,
  targets/positions strike maps, finishes and per-fight differential charts.
- Matchup raw values prominently shown, rank/unit beneath, reach/height edges,
  both fighters' breakdowns and low-sample flags.
- Hash routes `#/fighter/<id>`, `#/compare/<a>/<b>`, and now `#/about`.
- Source/coverage caveats in provenance/details/footer rather than technical
  wording dominating the fan-facing page.

Integration corrected percentile ties to midranks and even-sized medians to
the middle-pair average. Cohorts require at least three timed bouts and fifteen
minutes in the same cutoff/window. Pools under 25 use all divisions and say so.
'Absorbed' rankings are inverted. Historical physical profiles are frozen
source observations, not fully dated prefight measurements.

Optional roster/photos require an evidence-backed JSON file described in
`src/upset/web/ROSTER.md`. ACTIVE status is withheld before observation and
expires after 62 days, enforced in API and UI. No headshots or contract roster
were acquired. Google Fonts still loads externally with fallback; self-hosting
is an optional future improvement, not completed work.

Subsequent requested fixes, all in the accepted broadcast version:

1. Search dropdown stacks above selected fighter slots and other content.
2. Empty selected slots show a clean prompt, never 'Red corner null'.
3. Differential-chart zero tick duplication/close spacing fixed; mixed-sign
   plot spacing added.
4. Matchup names balanced over two aligned lines; both corners share adaptive
   fitting, preserve full names and resize when layout/fonts change.
5. Full division watermarks such as WOMEN'S FLYWEIGHT fit with consistent
   padding rather than clipping.
6. Redundant Compare button hidden when already viewing that pair. A complete
   pair elsewhere offers 'View matchup'; incomplete pair hides it. Two picks
   still automatically navigate to comparison.
7. Rare action rates display **per five minutes**, including knockdowns,
   takedowns and submission attempts. Existing API per-15 fields are divided
   by three in presentation, including tooltips and medians. Underlying totals,
   ranks and model features remain unchanged. This is exposure normalization,
   independent of a bout being scheduled for three or five rounds.
8. Footer 'Created by Ayaan Ahmed' links to his full biography page. Only the
   supplied copy's missing 'is' and useful—whether punctuation were corrected.
9. **All UI box/container corners square**: search input/dropdown, L3/L5/L10/
   Career buttons, date, selected fighters, remove buttons, CTAs, cards, badges,
   records, chart tooltips and mobile chip rule. `--radius:0px`. Small semantic
   corner/ACTIVE dots remain round; anatomical/SVG chart glyphs are not panels.

Ayaan asked for less 'AI-looking' styling; an optional paper/ink editorial
version was produced and explicitly rejected as worse. He wants future design
changes **one by one**. Keep the original colors/layout/type. That experimental
version remains archived in source, is not default and should not be offered
again without a new request.

## 10. Source files and installation artifacts

| Source file | Role |
| --- | --- |
| `src/upset/web/research.html` | Default broadcast markup, CSS and JavaScript. Ayaan's principal manual-edit file. |
| `src/upset/web/research_about.js` / `.css` | Shared creator biography renderer/styles in repo source. |
| `src/upset/research_app.py` | Read-only local HTTP API, calculations, assets, optional design/roster. |
| `src/upset/web/assets/` | Vertical logo, favicon, grunge. |
| `pyproject.toml` | Dependencies and packaged HTML/CSS/JS/assets. |
| `src/upset/web/research_editorial*`, `research_base.css` | Archived rejected optional design. |
| `SITE_REDESIGN.md`, `docs/SITE_EDITORIAL_PREVIEW.md` | Redesign/integration notes and accepted/rejected choice. |

The server binds to **127.0.0.1**, opens SQLite read-only, serves HTML freshly on
each GET and uses no-store. CSS/HTML replacement can be seen by hard refresh
without restarting; changed Python server code or a different DB needs restart.
Recent server supports `--design broadcast|editorial`, default broadcast.
Some Mac versions may not have that flag; omit it in general restart commands.

Latest installation download: **`upset-square-controls.html`**. It is the full
broadcast page with About CSS/JS **inlined**, compatible with the user's older
asset server. Intended destination: `~/Projects/upset/src/upset/web/research.html`.
It calls the local APIs and loads logo assets; **do not open it in ChatGPT's
file preview and expect the live app**. That earlier mistake caused an XML/JSON
error and missing logo; it did not establish damage to the Mac project.

Important source difference: repo `research.html` references shared About
modules, whereas the delivered replacement inlines them. Same behavior,
different file bytes. Do not apply future line patches assuming Ayaan's file
matches GitHub exactly. Read his installed file or make a backed-up deliberate
replacement. An old full-project ZIP must never override it.

Latest delivered installation instructions were:

```bash
bash <<'SH'
set -e
cd ~/Projects/upset
mkdir -p data/processed/site_backups
cp src/upset/web/research.html \
  "data/processed/site_backups/before_square_$(date +%Y%m%d_%H%M%S).html"
cp ~/Downloads/upset-square-controls.html src/upset/web/research.html
SH
```

Then Cmd+Shift+R on the already running site. **Application of this latest
all-square file is not yet confirmed.** Earlier screenshots confirm the
original broadcast return/bio and show the still-rounded header, which prompted
the correction. The previous `upset-broadcast-boxes.html` download initially
squared only selected fighter chips; old copies may remain in Downloads.
Use the newer filename, not an ambiguous duplicate.

Standalone preview: **`upset-original-preview.html`**. This is a separate
self-contained sample with embedded assets and real Oliveira/Holloway API
reports for all four windows from the September 26 snapshot. No fetch/API
calls. Its other-fighter/date limitation is labelled. It is for visual review,
**never install it as `research.html`**, or the live site would show fixed
sample data. It was updated to the same square corners and biography.

Preserved backup: **`upset-broadcast-backup.zip`**, source/assets/server/package
at original broadcast commit, no DB or credentials. Original local backup tags (not newly pushed by the snapshot publication):

- `upset-broadcast-2026-10-05` →
  `da4d4d99fb4ccfe068514d0117a2924b4b3b2d61`.
- `upset-broadcast-with-bio-2026-10-05` → `5e0b102`.
- Original HTML SHA:
  `a0621c2d2b94d027180c1a93e0081be4ce18cbd3e6a98e9dca3ef93e42c15693`.

Mac HTML backups from installation commands live in
`data/processed/site_backups/`. We cannot inspect them remotely. Never use
`git reset --hard`, `git clean`, wildcard restore, delete processed data or
force-push his branch as a shortcut to a visual revert.

## 11. Testing and honest limits

At the initial broadcast integration: **495 tests + 16 subtests**, Ruff clean,
456 exact legacy real-data response comparisons (38 fighters × four windows ×
three dates), asset packaging checks. DB v2 bytes were hashed and inspected.

At final handoff, freshly rerun:

- Focused research server/redesign/editorial suite: **23 passed**.
- `node tests/research_ui_checks.cjs`: passed.
- `node tests/matchup_names_checks.cjs`: passed.
- `node tests/division_watermark_checks.cjs`: passed.
- Git whitespace check: passed.

The all-square change was explicitly checked to be CSS-only: stripping the
first style block left the prior and current HTML identical. No model, API,
biography logic or metrics changed. Preview scripts passed Node syntax checks.
Do not describe the earlier 495-test run as freshly rerun for this handoff.

User-supplied screenshots were inspected, including actual localhost pages.
Fresh browser rendering in this cloud environment was blocked for localhost
and data URLs. We did not bypass that restriction or claim automated rendered
desktop/mobile visual QA. Behavioral/API checks are real; final appearance
is reviewed on Ayaan's Mac.

## 12. Cito email and project permission decision

Retain the original email Ayaan edited/sent: to `support@citoapi.com`, subject
'Confirm UFC historical stats access before I upgrade', four questions about
March 8–August 28 full stats, March 14/June 6 specifically, gaps and retention
after a single paid month. His edited email is authoritative if quoting it.

Ed's reply confirmed Pro full archive (90-day pricing line was a mistake),
specific card stats, the duplicates/exceptions above and personal noncommercial
retention after cancellation; no resale/redistribution. The whole-card stats
endpoint returns totals and rounds in one request. Dashboard Sandbox was
offered for checking prior to purchase; actual collection is already done.

A later reply reportedly allowed broad use, but Ayaan explicitly said to rely
on the earlier restrictive retention line. **That is the working project
decision**, recorded in `docs/CITO_PERMISSION_NOTES.md`: private analysis can
continue; public post-cancellation display/redistribution scope is unsettled.
Normalizing or calculating metrics does not automatically make underlying
licensed records unrestricted UPSET-owned data. Do not invent a 'processing
bypass' or equate paying $60 with ownership. This is a record of the chosen
project constraint, not a fresh legal opinion or a reason to obstruct private
engineering. No public deployment, external feed or credential sharing occurred.

## 13. Recommended next work when Ayaan returns

1. Confirm whether the latest square-controls installation was applied; inspect
   his current screenshot/file. Handle the next design change narrowly.
2. If he wants current data displayed, switch the running viewer from v2 to
   the already-built refresh DB. Do not reacquire/rebuild merely to change it.
3. Review high-priority unresolved identities in batches using saved evidence;
   create dated evidence rules, keep conflicts visible, emit new snapshots.
4. Finish an independent completed-event/bout calendar comparison. Keep the
   eleven historical round gaps documented instead of repeatedly probing the
   same unavailable endpoints. Work with existing totals where appropriate.
5. For predictions: review a real future schedule and exact identities; obtain
   necessary complete pre-event history, build strictly earlier features,
   verify probabilities from the frozen artifact, lock forecasts externally
   before actual starts, then score outcomes using a preregistered plan.
6. Treat new round/trend/physical feature studies as separate research work,
   with matched cohorts/proper probability losses and honest repeated-look
   limits. Do not chase 75% by repeatedly slicing already examined folds.
7. Production deployment, authentication/search/API design, public rights and
   operational updates are future product work, separate from this localhost
   preview. Keep one paid month's retention/renewal constraint visible.

Never rerun the fixed dated refresh script as a generic 'get current' command:
`scripts/run_cito_current_refresh.sh` is pinned to September 27–October 5 and
specific immutable roots. A new interval needs explicit new roots/settings.

## 14. Safe shutdown and restart on the Mac

In **each Terminal tab actually running the research server**, click the tab
and press **Ctrl+C** once. Wait for the normal shell prompt. A brief Python
KeyboardInterrupt is normal. The viewer is read-only; stopping it does not
delete the database or unsave source files. Closing only the browser does not
stop Python.

At the prompt, `deactivate` leaves `.venv`; `exit` closes that shell. Close the
browser's localhost tab/window normally. Save any open editor buffers first.
Do not close a tab running a different acquisition/export job without checking
what it is; no such job is known to be active at this checkpoint. If two local
servers were started on different ports, stop both in their respective tabs.

To reopen the **same last visually confirmed site/database** later:

```bash
cd ~/Projects/upset
source .venv/bin/activate
python -m upset.research_app \
  --database data/processed/research_v2/upset.sqlite --port 8767
```

Then open `http://127.0.0.1:8767`. Leave the server terminal running. There is
no download, migration, rebuild, provider request or Git operation needed just
to restart it. Switching to the October 3 snapshot instead is a deliberate
database-path change to `data/processed/research_refresh_v1/upset.sqlite`.

## 15. Suggested opening message for the next chat

> Continue UPSET from the attached HANDOFF_2026_10_05_FINAL.md. Read it fully,
> then inspect the GitHub checkpoint branch and my actual local state before
> suggesting commands. Keep the original broadcast design, Ayaan bio and all
> rectangular controls; no editorial makeover. Don't repeat archive capture or
> old model experiments. Give complete instructions in one message and preserve
> my edits/data. I'll tell you the next change I want.

Supporting source docs: `CITO_CURRENT_REFRESH.md`, `CURRENT_MODEL_REPLAY.md`,
`ASOF_PREFIGHT_FEATURES.md`, `FROZEN_PROSPECTIVE_MODEL.md`,
`CITO_PERMISSION_NOTES.md`, `LOCAL_RESEARCH_APP.md`, `SITE_REDESIGN.md`,
`SITE_EDITORIAL_PREVIEW.md` and older dated handoffs. Prefer this checkpoint's
confirmed state over their older pending notes.
