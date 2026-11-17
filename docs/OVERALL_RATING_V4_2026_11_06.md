# UPSET Experimental v4: rating scale results

V4 changes the conversion from the combined score to the displayed rating.
The model, fight records, grade 90 and 99 thresholds, five-point limit, and
result-direction protections are the same as v3. The new thresholds spread
the low 90s apart and get progressively farther apart toward 99.

Michel Pereira's submission win over Ihor Potieria still raised his combined
score from 86.55 to 87.57. That increase now crosses three displayed grades
(89 → 92) instead of five (89 → 94). His latest saved rating is still 78.

| Retrospective check | V3 | V4 |
|---|---:|---:|
| Moves of four or more in 362 matched upper-band updates with modest underlying changes | 87 (24.0%) | 9 (2.5%) |
| All five-point moves, out of 6,939 decisive updates | 1,312 | 1,185 |
| Actual applications of the five-point limit in those updates | 729 | 642 |
| Higher badge won, same 2,954 untied fights | 1,772 (60.0%) | 1,772 (60.0%) |
| Fighters at 90+ among 703 with a linked bout since Jan 2025 | 58 | 56 |
| Fighters at 95+ among those 703 | 34 | 10 |
| Wrong-direction wins or losses | 0 | 0 |

The replay matched 17,661 fighter dates for 2,677 fighters. It reproduced
the saved v3 ratings and pre-fight comparison records, preserved every
underlying model field, and reproduced the v4 prefix ending before 2024.
Both versions have four distinct fighters who reached a displayed 99 in the
linked archive: Georges St-Pierre, Islam Makhachev, Jon Jones, and Khabib
Nurmagomedov. Makhachev's latest displayed 99 is held after a win; his
underlying model grade is 98.

| Fighter | Latest v3 badge | Latest v4 badge |
|---|---:|---:|
| Islam Makhachev | 99 | 99 |
| Charles Oliveira | 97 | 97 |
| Francis Ngannou (last UFC fight Jan 2022) | 96 | 94 |
| Ilia Topuria | 96 | 94 |
| Justin Gaethje | 89 | 89 |
| Michel Pereira | 78 | 78 |

The [predeclared protocol](OVERALL_RATING_PROTOCOL_V4.md) defines the cohort
and gates. The matching snapshot's `manifest.json` contains the exact
thresholds, and `evaluation.json` contains the counts and comparison details.
This evidence uses past fights; future prediction performance has not been
established by this replay.

## Run or roll back locally

From Terminal:

```zsh
cd ~/Projects/upset
./Start\ UPSET.command
```

Open <http://127.0.0.1:8768>. To switch back, stop the local viewer first,
then run `UPSET_RATING_VERSION=v3 ./Start\ UPSET.command`. Both versions use
the same verified database, recent archive, roster, and striking preview.
The prior source and launcher copies are in
`backups/rating-v4-2026-11-06.H4JlgH`. The verified v4 snapshot is
`data/processed/overall_rating_v4_2026_11_06_backfill_v2`.
