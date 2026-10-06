# Research context update — October 6, 2026 UTC

## Delivered first batch

The broadcast viewer adds opponent records before each selected meeting,
knockdowns received per 100 significant strikes absorbed, validated paired
control shares, and a linked How the numbers work page. Common opponents and
scored knockdowns per 100 significant strikes were already implemented.
Single-profile Power & durability stays directly above fight-by-fight striking.
The broadcast design, square controls, warm palette, creator page and hero search
remain. No paid requests, raw-data edits, SQLite rebuild or model change.

Opponent records use persistent identities and accepted UFC fights strictly
before each meeting. Exclude the fight itself, other fights on its date, and
future results. Draws/no contests remain visible but outside win-rate denominators.
The headline is the mean of per-opponent win percentages, one per meeting;
rematches receive their own dated record. No prior decisive history means an
unavailable rate, excluded from the mean with its count displayed. Details also
show the pooled record and weighted win fraction. All these are descriptive:
missing accepted history can distort them, and contemporary reviewed amendments
can change old records. They do not reconstruct what was known on a past date.

Control shares use positive-duration bouts where both control totals exist,
are nonnegative and sum to no more than duration. All three shares use the same
exposure. Missing/invalid pairs exclude the whole bout rather than counting zero
or clamping the residual. The residual is Neither credited with control, not
Time at distance: the source does not measure positional duration. Strike-position
counts cannot establish distance/clinch/ground time.

The methodology page distinguishes cutoff, window, frozen measurements, reviewed
outcomes, peer-pool assignment, metric denominators and source exclusions. It
shows the actual latest accepted fight date, not an invented last-refresh date.

## Competitive claims checked

FightingData already has cumulative striking charts with percentile bands,
round detail, common opponents, and published metric definitions. Its methodology
defines opponent records before the bout date; its fighter page explicitly labels
them at fight time. Calling them all-time/leaky or claiming it has no charts would
be wrong. UPSET has no demonstrated superior overall data accuracy or live
prediction performance. Visual preference does not establish these advantages.

Primary pages checked:

- https://fightingdata.com/methodology/
- https://fightingdata.com/fighters/mike-malott/
- https://fightingdata.com/compare/mike-malott-vs-joaquin-buckley/

## Next work, in order

1. Address remaining accepted-history gaps and implement dependable incremental
   event updates, including a post-Cito source. Do not treat missing bouts as losses
   or silently supply guessed identities.
2. Integrate verified historical/current round exports into the serving database
   with explicit availability, identity, duration and total-sum checks. Display
   expandable round detail first. Pace changes must account for partial rounds,
   sample size and selection of fights reaching later rounds; do not call the
   ratio a direct cardio measurement or infer round winners from striking counts.
3. Build event browsing, distinguishing retrospective views using reviewed data
   from forecasts actually frozen/published before the event.
4. Publish versioned forecasts with timestamps, complete coverage of all eligible
   bouts and a prospective performance record. Chronological backtests and existing
   retrospective replay stay separately labeled. Calibration, log loss, Brier and
   accuracy are different measures; never invent an observed 60%→59% claim.
5. Evaluate opponent-adjusted performance before presenting superiority claims.
   Style-group records need predeclared groups, exposure and uncertainty; they are
   not causal estimates. Consider branded export cards and Elo-defined upset wins
   after data/event workflows are dependable.

Pro records need a separate verified non-UFC source. Odds disagreement needs dated
odds, margin removal and prospective evaluation; it does not establish betting
value. None of these features is structurally impossible for a competitor to copy.

## Validation and installation

34 focused Python research tests cover boundary dates, same-day meetings, current
amendments, rematches, unequal mean-vs-pooled records, empty histories, null control,
invalid overlapping control and HTTP asset delivery. Node UI checks cover the
new cards and methodology in addition to existing search, tray and rate behavior.
Actual saved Pereira and Topuria profiles match all prior metric values; new
opponent context is calculated only for requested profiles, not percentile peers.
The saved SQLite hash is unchanged. This specific update has not been run on the
user's Mac or visually inspected in a real browser.

The ZIP contains two source patches: one after the division update and one from
the preceding fan-stat backend. Installer checks applicability before changing
files, preserves existing source and supplies restore.sh. It includes the division
fix and all four reviewed title corrections if the previous update was not installed.
The full bundled HTML embeds About CSS/JS and methodology JS for compatibility
with earlier installations. Existing original asset files are still required.

Stop the old server with Ctrl+C, then unzip and run the included install.sh.
It uses data/processed/research_rahiki_v1/upset.sqlite on port 8767. If an unsupported
backend differs, it stops before changing files. If installation verification fails,
it restores backed-up files. To revert later, stop the viewer and run the printed
backup/restore.sh, then restart the viewer using the same database.
