# Cortes Acosta vs Walker card update · November 8, 2026

The local viewer on port 8768 serves all 14 bouts from November 7. Cito returned
28 fighter totals and 68 fighter-round rows, and the totals reconciled against
the rounds. Johnny Walker won by TKO at 2:27 of round 3. Cito recorded Walker
landing 51 of 77 significant strikes and Cortes Acosta landing 40 of 89.
[Official UFC card](https://www.ufc.com/event/ufc-fight-night-november-07-2026) ·
[UFC main-card recap](https://jp.ufc.com/news/ufc-fight-night-cortes-acosta-vs-walker-results)

Eleven reviewed provider links recovered seven earlier bouts from the saved
archive. Five profiles, 21 bouts and 42 fighter-stat rows were added. The
previous 4,471 fighter rows, 8,871 fight rows and 17,742 stat rows were
preserved exactly. The new database has 4,476 profiles and 8,892 bouts.
The reviewed recent archive now contains 341 included bouts and 77 pending.

The October audit found two statistical rows for each of the 60 October
bouts already included in the preceding database. Both rows for every bout
contain significant-strike attempts and control time. The October 31 card
also reconciled its totals against 64 fighter-round rows.
[October 31 import](MAINTENANCE_2026_11_03.md) ·
[Cito free plan](https://docs.citoapi.com/free-ufc-api/)

The raw Cito responses are in `data/raw/cito_walker_2026_11_08_v1`.
The dated importer records the reviewed identities and bout evidence.
The new database is in `data/processed/research_2026_11_08_reviewed_v1`.
The striking preview and ratings were rebuilt against it, and v4 passed its
existing serving gate. Staging and the live viewer verified both sides of
every new bout, profile search, earlier and later cutoffs, comparison,
striking, portrait delivery and pending coverage.

Restart from `~/Projects/upset` with `./Start\ UPSET.command`.
To roll back after stopping the running viewer, use
`UPSET_DATA_RELEASE=nov06 ./Start\ UPSET.command`. The earlier launcher and
release check logs are in `backups/walker-card-2026-11-08.TrL5xI`.

The Wi-Fi viewer on port 8769 is a separate process. After a card update,
check both running viewers and restart any listener that still serves the
previous database. The site footer shows the latest bout date for the
database that served the page. The November 8 Wi-Fi restart was verified on
its existing address with Walker’s win at the top of his history.
