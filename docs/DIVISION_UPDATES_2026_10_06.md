# Division and profile update policy — October 6, 2026 UTC

## Observed problem and correction

Both June bouts were already accepted in research_rahiki_v1: Pereira/Gane at
Heavyweight and Topuria/Gaethje at Lightweight. The profile summary used the
most common division over the last five classified fights, keeping their old
divisions despite correctly recorded newer bouts. Search used the latest bout,
creating contradictory labels in different parts of the same site.

The shared latest_classified_division rule now uses the newest classified
accepted UFC bout strictly before the exclusive Before date. It works for
every fighter, not just two name overrides. The result is independent of
L3/L5/L10/Career: those controls choose the metric window, not the fighter's
division assignment. A later catchweight/unclassified bout preserves the last
known classified division. Conflicting divisions on the same newest date are
unresolved, because the data cannot establish intra-day fight order.

summary.division_date and division_basis expose that evidence. Header/tooltips
describe a last recorded division, not a current live roster assignment.
Search accepts an optional exclusive before cutoff; the broadcast client
sends it for both typed queries and the homepage feature. Search fight counts,
last-bout dates and division assignments obey it. Legacy calls with no cutoff
continue using all records. Percentile pools use the identical assignment.

Career and last-N metrics still include all selected fights, including earlier
divisions. Peer pools compare the same metrics across fighters assigned by
their latest classified bout; these are not division-only performance stats.
The footer explains this scope. A future division performance filter would be
separate work. No stats, registry, database or model were rewritten here.

## Title metadata checked during this review

The June 14 bout rows also omit Title from their division labels. Official
UFC evidence establishes that Pereira/Gane was an interim Heavyweight title
bout and Topuria/Gaethje a Lightweight title bout. Add exact dated-participant
metadata overlays using provider bout IDs 5727d5be8c373346 and 7208e40818401e88,
with evidence shown in Data provenance. Counts in this saved cohort become
Pereira 9 and Topuria 4. The two previously reviewed UFC 328 overlays remain.
This is four evidenced corrections, not an exhaustive title metadata audit.

Primary evidence checked October 6 UTC:

- https://www.ufc.com/athlete/alex-pereira
- https://www.ufc.com/news/official-weigh-results-ufc-freedom-250
- https://www.ufc.com/news/ufc-freedom-250-results-highlights-interviews

## Remaining stale profile fields

The frozen profile measurements are still a snapshot. Pereira's stored weight
is 205 lb; correcting his division does not establish a current weight.
Both profile and matchup tape labels now say Profile weight. Heights/reaches,
stance, weight, contract status and advertised division need individually
dated/source-backed observations when refreshed. No demographic values were
invented or mass-overwritten.

Intended next infrastructure:

1. Collect and retain dated profile observations linked by verified provider
   ID/permanent UPSET ID, without overwriting the frozen model inputs.
2. Review contradictory/unknown observations and retain field-level source,
   observation time and effective date when available.
3. Use eligible observations on research pages while making their dates clear.
   Present-day facts must not silently appear as historical facts.
4. Run the incremental event update after every card, with identity/coverage
   checks. New accepted bouts automatically update last-recorded divisions.

A fighter announcing a move before their first fight in the new class needs
that separate dated roster/profile observation. The last-bout rule alone cannot
capture an announcement. Automated profile refresh and a replacement post-Cito
collector are not implemented by this patch. Saved data continues offline;
new facts still need a source. Identity gaps can still leave latest bouts out.

## Validation and Mac installation

31 focused research tests pass, including latest-vs-majority, exclusive cutoff,
window independence, catchweight, same-day ambiguity, search consistency and
peer pool grouping. Existing UI and hero search checks pass. Actual saved DB
checks show Pereira Heavyweight and Topuria Lightweight at October 4; before
their moves they display Light Heavyweight and Featherweight, respectively.
Database SHA-256 unchanged after verification; model untouched.

The delivered ZIP includes API/metadata patch, complete latest HTML, installer
and this README. It retains the requested lower single-profile Power &
Durability placement and comparison layout. The installer preflights patch
applicability, saves prior HTML/backend/metadata, checks both profiles and
restarts the same research_rahiki_v1 SQLite on port 8767. Stop the old server
first. No database rebuild, API requests or new paid subscription required.
Visual inspection of this specific update and Mac execution await Ayaan.

Rollback: stop the viewer and restore the three files from the backup directory
printed by the installer, then launch against the same SQLite. No snapshots
should be deleted, rewritten or reset.
