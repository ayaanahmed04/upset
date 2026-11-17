# November 10 viewer update

The `nov10` launcher release adds the October 3 UFC 332 fight between King Green
and Esteban Ribovics. Ribovics won by TKO at 4:08 of round one. The saved Cito
totals reconcile with both round rows. Green landed 27 of 49 significant
strikes and Ribovics landed 35 of 71. The review linked Green’s alternate
provider ID to his existing profile. It preserved all 4,476 profiles, 8,892
previous fights and 17,784 previous statistics rows. The new archive contains
8,893 fights, including 342 reviewed recent fights. Another 76 await review.
The newest recorded fight date remains November 7.
[Official UFC result](https://www.ufc.com/index.php/video/160794)

The dated importer is `scripts/import_green_ribovics_2026_10_03.py`. It reads the
original UFC 332 capture and the November 8 archive. The new reviewed archive,
database, rating versions and striking preview have the suffix
`2026_11_10_reviewed_v1`. The v3 candidate has the suffix
`2026_11_10_candidate_v1`. All rating versions were replayed with their
existing rules, and the striking preview uses the existing rolling study.
The rating and striking snapshots include fights strictly before November 8.

The broadcast viewer distinguishes no-contests from draws, keeps date and stats
window in the URL, and saves explicitly selected matchup slots in that browser.
It shows both matchup striking histories on the same scale. Dots represent
fights under one minute. Their recorded rates remain available in the chart
tooltips.

The launcher defaults to `nov10`. Stop the running process on the relevant port
before restarting it. For the November 8 data release, run
`UPSET_DATA_RELEASE=nov08 ./Start\ UPSET.command`. For the Wi-Fi viewer also
set `UPSET_BIND_HOST=192.168.4.75 UPSET_PORT=8769` or use the Mac’s current
Wi-Fi address. Confirm both ports independently.

The pre-update launcher and exact copies of the edited source files are in
`backups/site-review-2026-11-10.UAT6FW`. The launcher copy is
`launcher-before.command`. The source archive is `source-before.tar` and the
rating test copy is `rating_ui_checks-before.cjs`. Inspect the archive before
restoring files to avoid overwriting later work.
