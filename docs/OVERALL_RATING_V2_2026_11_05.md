# UPSET Experimental v2 — local release, November 5, 2026

UPSET’s local viewer uses [Experimental v2](OVERALL_RATING_PROTOCOL_V2.md). A
badge summarizes recorded UFC results and performances on a 60–99 scale. It
does not estimate a fighter’s chance of winning. The source database and the
separate recorded statistics are unchanged. The latest recorded card in this
snapshot is October 31, 2026.

## What changed

- Striking now credits recorded KO/TKO wins, alongside the existing KO/TKO
  loss input. KO/TKO wins account for 10% of the Striking part. The résumé
  contribution is now 50% of the overall calculation, up from 25%.
- After a date with only wins, the badge can rise or stay put. After a date
  with only losses, it can fall or stay put. If the rule holds a badge, the
  panel shows the calculated grade and explains the hold. The underlying
  components can still move either way. Mixed and nondecisive dates are exempt.
- A newly earned 99 requires an unrounded 99 at the top curve anchor. The
  viewer keeps the compact octagons and shows the fight result, selected
  recorded stats, and how the score maps to UFC snapshots through 2018.

Gaethje’s recorded June 14 win over Topuria produced **84 → 83 in v1** and
**88 → 89 in v2**. Under v1, Résumé added 0.273 to the combined score, but
Striking cost 0.291 and Wrestling and Grappling together cost 0.320. That
0.338 decline crossed a rounding boundary on the historical curve. UPSET
records a fourth-round KO/TKO at 5:00, 91–97 in significant strikes landed,
and 0 of 5 takedowns for Gaethje. The data does not establish how the stoppage
came about. In v2, the combined score rose from 86.10 to 86.51 and mapped to
89 without a hold. Topuria’s v2 badge moved **98 → 97** on the same date.

## What the comparison says

On the **same 3,149 decisive historical fights** from 2019 to before October
26, 2026, probability log loss was **0.66375 in v1** and **0.66533 in v2**
(lower is better). The difference was +0.00157, within the declared +0.010
preview limit. The whole-date bootstrap interval was −0.00056 to +0.00364;
Brier score also moved slightly higher, from 0.23570 to 0.23646. On the same
**2,828 fights** where both versions had unequal pre-fight grades, the higher
badge picked the winner **1,705 times in v1 and 1,706 in v2**. Using their own
eligible fights, v1 was 1,794/2,984 (60.1%), v2 was 1,770/2,951 (60.0%), and
v2 without holds was 1,775/2,956 (60.0%). These are development results on
already inspected data. They support trying the badge locally; they don't
show improved prediction on new fights.

| Badge behavior, full history from 2019 through Oct 31 | v1 | v2 without holds | v2 |
| --- | ---: | ---: | ---: |
| Wins that lowered the badge, of 3,506 | 363 | 109 | 0 |
| Losses that raised the badge, of 3,425 | 214 | 46 | 0 |
| Badge moves of exactly five, of 6,931 | 1,405 | 1,309 | 1,325 |
| Actual five-point limit applications, of 6,931 | 859 | 719 | 734 |
| Exactly five with at least 10 prior bouts, of 2,175 | 240 | 218 | 224 |
| Actual limit applications with at least 10 prior bouts, of 2,175 | 100 | 91 | 94 |
| Different fighters displaying 99 | 9 | 1 | 1 |

V2 held 116 win updates and 50 loss updates. It showed one 99, earned by
Khabib Nurmagomedov, with zero held 99s in that window. Across all 7,884
post-fight states in that window, v1 had 818 in the 60s, 3,738 in the 70s,
2,873 in the 80s, and 455 at 90+. V2 had 889, 3,499, 2,921, and 575,
respectively. That means fewer 99s even as more states reached the 90s.

Volatility is still visible. The fixed curve runs from 89 to 94 over just two
percentile points (95th to 97th), so a small percentile movement there can
produce several grade points. Actual limit use fell from 12.4% to 10.6%,
while changes of exactly five remained common at 19.1% in v2. A five-point
change does not always mean the limit clipped it. The cap and curve anchors
were left in place for this comparison.

The earlier review’s 322/3,131, 43/231, 143/2,428 and 1,119/5,559 were
reproduced on its narrower cohort, which requires a later qualifying fight
in the earlier exported evidence. On the full history, 53 of 263 wins by
fighters with a prior badge of 90+ lowered the v1 badge. The full counts above
include the last update even when a fighter has no next fight in the export.

## Run or roll back locally

Double-click `Start UPSET.command` in the UPSET project, or run:

```zsh
cd ~/Projects/upset
./Start\ UPSET.command
```

Open [UPSET](http://127.0.0.1:8768) and reload an already-open tab. Leave the
terminal running. The launcher reuses the dated snapshot when available and
falls back to v1 if the v2 snapshot cannot be verified. Stop the current local
server before starting a second copy. To choose v1 explicitly:

```zsh
cd ~/Projects/upset
UPSET_RATING_VERSION=v1 ./Start\ UPSET.command
```

The v1 review files and verified snapshot are preserved. For outside review,
attach the [v2 review ZIP](share/UPSET-Rating-Review-v2-2026-11-05.zip) and ask the reviewer to start with
`START_HERE.md`. It contains the declared rules, named evidence and an
offline verifier. Future fight results are the next independent check.
