# Editorial design experiment — October 5, 2026

## Design decision

Ayaan rejected this experiment after reviewing it. The active design is the
original broadcast edition with the shared “Created by Ayaan Ahmed” footer and
creator bio page. Future visual changes should be made one at a time against
that baseline. All UI controls and panels should have square corners, including
the search field, date/window controls, buttons, badges and cards; this is not
limited to the selected-fighter chips. Keep the editorial experiment only as a reversible archive;
do not treat it as the preferred direction.

This is a separate, opt-in design. The broadcast site remains the default and
the broadcast layout is preserved. Both editions now include the requested
creator credit and a shared About page at `#/about`.

## Try it alongside the broadcast site

```bash
python -m upset.research_app \
  --database data/processed/research_v2/upset.sqlite \
  --design editorial --port 8767
```

Open http://127.0.0.1:8767. Leave the terminal running. Another terminal can
continue serving the original design on its existing port. To return to the
original, close the experimental tab or start the server without `--design`.
There is no database migration, network ingestion, or model change.

## Design and editable files

- `src/upset/web/research_editorial.html`: the page shell.
- `src/upset/web/research_base.css`: formatted research components and controls.
- `src/upset/web/research_editorial.css`: the new visual direction and responsive rules.
- `src/upset/web/research_editorial.js`: formatted rendering and interaction code.
- `src/upset/web/research_about.js`: Ayaan’s bio, shared between both editions.
- `src/upset/web/research_about.css`: creator-page and footer-credit styles.

The experiment uses warm paper against dark ink, open ruled sections, an
asymmetric home page and a diagonal red/blue matchup graphic. Initials portraits
are removed; optional credited roster photos remain supported. Archive counts
are a small byline rather than a row of oversized counters. Headings and labels
use less letter spacing and fewer uppercase captions. A five-minute clock note
explains the rate normalization without inventing a personal origin story.

The displayed metrics, cohort rules, controls, search ranking and date semantics
are inherited from the broadcast version. Its per-five-minute presentation and
name/label fitting fixes are preserved. The home-page async completion now also
checks that the user has not navigated away before replacing the feature.

Google Fonts remain an optional network resource, with system fallbacks. This
experiment does not add fighter headshots or new third-party image dependencies.

## Preserved baseline

Baseline commit: `da4d4d99fb4ccfe068514d0117a2924b4b3b2d61`.

Local Git tag: `upset-broadcast-2026-10-05`.

Original HTML SHA-256:
`a0621c2d2b94d027180c1a93e0081be4ce18cbd3e6a98e9dca3ef93e42c15693`.

`upset-broadcast-backup.zip` contains the original web directory, server,
packaging configuration and redesign notes, without databases or credentials.
Before applying the experiment on a different machine, also copy that machine's
current web directory, server and packaging file to a timestamped local folder.
This captures any local edits that are not part of the saved commit.

## Verification and preview limits

The focused server suite passes 23 tests. It verifies design selection, exact
default HTML, static asset content types, rejection of unknown/traversing paths,
and equal API responses across designs. The existing JavaScript behavioral
checks also pass when run against the formatted editorial renderer: rates,
medians, ranks, matchup tray actions, chart spacing, preserved names and label
fitting. Python lint, JavaScript syntax and patch whitespace checks pass.

The standalone `upset-editorial-preview.html` embeds actual Oliveira/Holloway
reports from the September 26 database snapshot for all four windows. Home,
fighter, matchup and creator sample pages work without the local server. Other fighters
and dates require the installed app; the preview labels that limitation.

The cloud browser rejects local-app and data-URL previews, so rendered desktop
and mobile screenshots were not verified in this environment. Open the preview
or the local server to review the visual result before choosing this edition.
