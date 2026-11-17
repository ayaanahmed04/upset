# Why Gaethje went from 84 to 83 after a win

**UPSET gave Gaethje credit for winning.** His Résumé improved. The overall
also weighs the skills it estimates from recorded performance, and those
components fell enough to outweigh the result credit. The combined score fell
by only 0.34 before grading; that crossed the rounding boundary between 84 and
83. It does not mean Gaethje fought badly or that his ability fell by exactly
one point.

This explains the saved **Experimental v1** calculation. The fight and
statistics below are the records UPSET used, not an independent verification
of the event or a judgment about how impressive the performance was.

## What the model counted

In UPSET's June 14, 2026 record, Gaethje defeated Ilia Topuria by KO/TKO in a
title bout. Topuria's **pre-fight** experimental grade was **97**, while his
later grade was 96. Gaethje's Résumé is driven by Elo, which uses Topuria's
underlying pre-fight Elo of 1655.20, rather than his displayed grade of 97.
Gaethje's Elo rose from **1623.41 to 1640.87**.

Experimental v1 does not add a separate bonus for winning a belt, beating an
undefeated opponent as such, or winning by KO. Opponent strength matters to
Elo. The measured skill features also account for what earlier opponents
usually allowed or produced, use more recent bouts more heavily, and pull
sparse observations toward a baseline. Those choices do not capture every
aspect of a performance, including the importance of a decisive finish.

Some of the recorded inputs for this fight:

| Recorded input | Gaethje | Topuria |
| --- | ---: | ---: |
| Significant strikes landed / attempted | 91 / 192 | 97 / 162 |
| Takedowns landed / attempted | 0 / 5 | 1 / 3 |
| Control time | 1:32 | 2:32 |
| Recorded knockdowns | 0 | 1 |

Wrestling had the largest drop in Gaethje's component scores. The largest
downward terms in that component's underlying calculation were takedown
accuracy and control share. These are changes after updating his earlier
history and comparison context; no one raw count alone determines the grade.

## The arithmetic

| Rating input | Before the fight | After the fight | Change |
| --- | ---: | ---: | ---: |
| Striking | 85.71 | 84.94 | −0.78 |
| Wrestling | 81.40 | 80.06 | −1.34 |
| Grappling | 80.27 | 80.12 | −0.16 |
| Résumé | 88.52 | 89.62 | +1.09 |
| Skills blend | 83.332 | 82.517 | −0.815 |
| Combined before grading | 84.630 | 84.292 | −0.338 |

The skills blend gives 50% to the strongest of the three skill components,
30% to the second and 20% to the third. Their order can change; after this
fight, Grappling narrowly passed Wrestling. The overall formula uses
**25% Résumé + 75% Skills**. With full precision:

- Résumé contributed **+0.273** to the change in the combined score.
- The skills blend contributed **−0.611**.
- Together, the combined score fell **−0.338**.

The historical grading curve then turned 84.630 and 84.292 into unrounded
display grades of about **84.24 and 83.49**. Rounding gives **84 and 83**.
Neither the small-history cap nor the per-fight-day change limit was applied.
The displayed 83 is an index on a 60–99 scale, not an 83% win chance.

## The real review question

**The calculation is correct under the current rules. Whether those rules
give the win enough credit is open to review.** If viewers expect the overall
badge to reward achievements such as a title win, this is a useful example of
the current design falling short of that expectation. The model is closer to
a blend of recent measured performance and results than a championship ladder.

The 25% Résumé blend performed best among the three weights tested on the
earlier selection years. Its average log loss was 0.671349 versus 0.671680 for
50% Résumé, a small gap of 0.000331. That is a reason to test the weight's
stability, not proof that the 25% choice is uniquely best. With the same
component changes, a 50/50 blend would give this fight a **+0.138** movement
*before grading*. This does not tell us the new badge number: a different
blend needs its own reference curve, dated replay and evaluation.

Useful questions for a reviewer:

1. Should the badge describe current measured skills, achievements, or a
   balance? Would separate Skills and Résumé scores be clearer?
2. How often does the current model lower the winner's rating after a win over
   a highly rated opponent? Are those examples defensible when reviewed blind?
3. Do finish credit, a different skill blend, or a stronger Résumé weight
   improve results on later fights without overreacting to short records?
4. Are the source inputs and the amount of credit given to a small number of
   takedown attempts reasonable? Does the model handle missing data and
   changing divisions fairly?

The saved historical development check is encouraging but limited: the
higher displayed grade was on the winner in **1,794 of 2,984** eligible,
non-tied comparisons (60.1%). That is a model-wide result, not Gaethje's win
rate, a matchup probability, or validation on genuinely new fights. The
technical report includes the separate matched comparison against Résumé alone
and reports subgroups where the blend performed worse.
