# Homepage search and copy — October 6, 2026 UTC

Ayaan supplied `search-upgrade.md`, `search-upgrade-part2.md`, desktop and mobile
screenshots and a GIF. Both parts are integrated into the current broadcast
site, retaining the warm palette, square panels, creator biography and previous
mobile viewport fixes.

- The homepage headline ends with red `UPSET.`, replacing `ONE PLACE.`.
- The subtitle is lowercase: `look up any fighter, analyze their stats, compare
  them head to head.` It uses Black Ops One, loaded with the existing Google
  Fonts stylesheet; only that subtitle changes typeface. Its color is the same
  `--accent` red as UPSET.
- The large octagon-cut search sits beside the counters on desktop and under
  the headline on tablet/phone. It moves to the centered header on other pages.
- The existing search element is moved, not duplicated. It returns to the
  header before content replacement, including Home-to-Home rendering, to
  preserve the input, listeners and dropdown.
- The shell has a red border/glow on focus. The slash hint disappears on focus
  and when a query is entered. Pressing slash scrolls and focuses search.
- The idle placeholder cycles the eight fighter names in Part 1. It pauses
  while focused, while a query exists, when the page is hidden, or when reduced
  motion is requested. It never changes the query or calls the API itself.
- Search responses are invalidated on dismissal or navigation. Escape closes
  the empty-results state, Arrow Up initially selects the last option, and
  highlighted options expose their selected state to assistive technology.
- The dropdown remains outside the clipped shell. Main content stacks above
  the footer, and the mobile dropdown still fits the keyboard viewport.

The supplied patches targeted an older layout. Header grid assignments were
adapted to the live mobile layout, with empty slots removed and controls allowed
to wrap when their column cannot fit them. Dropdown top positioning remains
relative to the actual field height rather than a fixed pixel offset.

Validation: JavaScript syntax, new `hero_search_checks.cjs` (live input adoption,
Home rerender, About/profile/matchup navigation, late-response cancellation,
keyboard selection and reduced motion), and the existing UI/name/watermark
checks pass. Final browser appearance awaits Ayaan's installation review; no
rendered browser validation was available here. No backend, dataset or model
change is included.

Delivery: `upset-hero-search.html` contains About CSS/JS inline for compatibility
with the existing Mac server. Back up and replace only
`src/upset/web/research.html`, then reload the page. No server restart is needed.

## Follow-up alignment and copy

The 10:21 PM Chicago screenshot confirms the hero search, updated headline and
Black Ops One subtitle were installed on the Mac. Ayaan then requested a period
after UPSET, the same red for the subtitle, and a lower search field aligned with
the counter numbers. Those refinements are delivered in
`upset-home-aligned.html`. Desktop search aligns to the end of the hero row with
a 28px offset accounting for its label and helper text; tablet/mobile reset the
offset and retain the search-before-counters layout. Final alignment still needs
his visual review after replacement.

## Per-round wording

Before installing the alignment refinement, Ayaan requested “per round” instead
of “/ 5 min” and “per 5 min” for knockdowns, takedowns and submission attempts.
All broadcast profile cards, meters, matchup rows and tooltips now use that
wording. Values and percentile ranks are unchanged: the footer explicitly
defines a round as a five-minute equivalent based on actual fight time, including
early finishes. This is a label change, not averaging over recorded rounds.

The combined delivery is `upset-home-round-labels.html`. It includes the pending
UPSET period, red Black Ops One subtitle and desktop search alignment, so Ayaan
only needs to install this one replacement file.

## Final rate-label decision — October 6 UTC

After reviewing the installed site's screenshots, Ayaan selected per 15 minutes
for knockdowns, takedowns and submission attempts. The broadcast UI now formats
the original API values directly, using `/ 15 min` throughout cards, meters,
comparison rows, medians and tooltips. The five-minute division is removed.
Missing values remain missing; percentiles and underlying rates do not change.
The footer states that this is a rate over actual fight time, not per fight.
This supersedes the earlier per-round wording recorded above.

The October 5 22:55 Chicago screenshot shows the refreshed viewer's October 4
cutoff and Allen/Duncan feature matchup, confirming the switch from the older
September 27 serving cutoff. The latest per-15-minute HTML replacement awaits
Mac installation. HTML-only changes need a hard refresh, no database rebuild
or server restart. UI checks cover values, missingness, unchanged source/ranks,
medians and tooltip units; hero behavior checks also pass.
