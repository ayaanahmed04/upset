# Homepage search and copy — October 6, 2026 UTC

Ayaan supplied `search-upgrade.md`, `search-upgrade-part2.md`, desktop and mobile
screenshots and a GIF. Both parts are integrated into the current broadcast
site, retaining the warm palette, square panels, creator biography and previous
mobile viewport fixes.

- The homepage headline ends with red `UPSET`, replacing `ONE PLACE.`.
- The subtitle is lowercase: `look up any fighter, analyze their stats, compare
  them head to head.` It uses Black Ops One, loaded with the existing Google
  Fonts stylesheet; only that subtitle changes typeface.
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
