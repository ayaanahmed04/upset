# UPSET checkpoint — November 3, 2026

The local product now serves 8,866 bouts through October 31, with 4,469 fighter
profiles and 298 installed portrait assets. The homepage features Waldo Cortes
Acosta vs Johnny Walker. All 12 bouts from the recent card were added with exact
prior-row preservation. See [maintenance and run instructions](MAINTENANCE_2026_11_03.md).

The first significant-striking milestone is complete: a versioned paired-count
adapter and chronological accuracy prototype, run on the retained October 24
snapshot with a declared October 26 cutoff. The candidate improved development
point scores against all fixed references, including simple Jeffreys smoothing
and the earlier global mean. Its selected 500-attempt prior is at the top of the
declared grid; this does not establish an optimal or validated skill rating.
See [results and limitations](STRIKING_ACCURACY_2026_11_03.md) and the unchanged
[declared v1 protocol](STRIKING_ACCURACY_PROTOCOL_V1.md).

Next development milestone: a separately declared striking validation study for
predictive dispersion/calibration, repeatability and subgroup behavior. Any new
tuning experiment must be separate from v1 and honestly labeled development.
Opponent adjustment, validated skill intervals, serving snapshots/windows and
release gates remain unfinished. The current site remains raw; rankings remain
removed. No adjusted skill rating or winner forecast was released.

The frozen takedown-defense experiment, seed and all dependency hashes remain
unchanged and valid. Its October 2027 finalization date does not block striking
or product development. The newly imported October 31 outcomes were not used to
tune or score either frozen defense or this fixed striking v1 study.

Data limitations remain explicit: 89 prior current bouts stay withheld, newly
reviewed identities do not trigger an automatic backfill, and independent
whole-calendar coverage is unverified. Five new profiles have unavailable
demographics rather than invented values. Johnny Walker's portrait was absent
from the supplied archive, so the existing initials fallback remains.

Checks: 88 relevant Python tests passed (including 37 new striking/import
tests), existing JavaScript UI checks, targeted Ruff and whitespace checks,
24 real-card date-cutoff checks, browser homepage/comparison verification,
database preservation checks and frozen dependency verification.
