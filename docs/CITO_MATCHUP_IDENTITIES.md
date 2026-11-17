# Two existing identities anchored to public dated matchups

The first full Mac current replay succeeded October 5, 2026. The uploaded
`upset_current_replay_v1.zip` has three valid output hashes. Accuracy, Brier and
log loss were independently recomputed from all saved decisive predictions:

| Diagnostic | Observed value |
| --- | --- |
| Identified replay bouts | 248 |
| Decisive bouts | 245 |
| Correct picks | 153 |
| Accuracy | 0.6244897959183674 |
| Brier | 0.23349349142122194 |
| Log loss | 0.6586190997662509 |

The uploaded source bindings match the previously verified current v2 export
and accepted model SHA-256. All 248 feature rows have the exact 36-column schema,
finite or null values, unique bout IDs and bounded probabilities. The Mac
historical audit reports agreement across all 8,551 fights, 17,102 fighter
rows and 36 columns, with maximum absolute error zero. The actual frozen
parameter bytes and full historical features were not uploaded; their entire
probability reconstruction was not independently rerun here.

This is retrospective evidence that the pipeline runs end to end, not a fresh
holdout or live forecast record. Ninety-one canonical current bouts were
excluded; 11 replay bouts had directly omitted prior participant history,
and 237 followed omitted bouts affecting population smoothing. Do not promote
a new model or claim 62.45% prospective accuracy from this selected cohort.

## Reviewed anchors

Public UFCStats profile and matchup observations retrieved October 5, 2026
identify two existing registry candidates by dated opponent and stable bout ID:

| Fighter | UFCStats fighter ID | April 18, 2026 opponent | Bout ID |
| --- | --- | --- | --- |
| Mark Vologdin | 0e6b611451a9a7d8 | John Castaneda | 552f7cdaf93e1055 |
| Marcio Barbosa | c85bad793cd14e28 | Dennis Buzukja | 678440bd8274a18e |

Primary sources:

- https://ufcstats.com/fighter-details/0e6b611451a9a7d8
- https://ufcstats.com/fight-details/552f7cdaf93e1055
- https://ufcstats.com/fighter-details/5fa2974cbd18e05c
- https://ufcstats.com/fighter-details/c85bad793cd14e28
- https://ufcstats.com/fight-details/678440bd8274a18e
- https://ufcstats.com/fighter-details/c4d039123e62f6a9

The search-indexed primary pages contain scheduled matchup records with the
same opponent/date/bout anchor. Direct page retrieval returned 502. These
observations establish identity correspondence, not independent verification
of completed results or statistics, and not source availability before the
bout. The cached pages' profile totals are not added to training data.

The original unresolved queues contain exactly one reviewed candidate for each
specified UFCStats ID. Saved Cito fighter histories independently within that
provider match the canonical bout ID, date, name and opponent. Both opponents
already have reviewed Cito-to-UPSET-to-UFCStats links. The integration verifies
these facts against hashes and the existing registry before linking. It does
not create identities, infer DOB, overwrite measurements or alter labels.

`integrate_cito_matchup_identities.py` is an explicit two-rule allowlist. It
preserves previous link evidence, frozen inputs and complete canonical source
files; it writes a new overlay and restages accepted bouts. Name candidates
alone cannot add links. Unreviewed aliases and other source gaps remain.

The real uploaded evidence passed the offline helper. Applying the two links
to the uploaded registry/canonical cohort predicts 250 identified bouts,
89 excluded bouts, 96 unresolved provider fighters and nine replay bouts with
directly omitted history. These are expected restaging results; the full Mac
integration and replay must confirm them. A changed diagnostic accuracy is
possible because new history changes later inputs; this is data reconciliation,
not a new model recipe.

```bash
python -m upset.data.integrate_cito_matchup_identities
python -m upset.modeling.run_current_replay \
  --current data/processed/cito_current_identity_v3 \
  --registry data/processed/cito_current_identity_v3/fighter_registry.json \
  --output data/processed/current_replay_v2
```

An optional new local serving snapshot can be built with `build_research_db`
using this same current directory and registry and a new `research_v3` output.
The running viewer and research_v2 remain untouched. All operations use saved
inputs with zero API calls. Both outputs reuse unchanged validated inputs and
reject altered source/output hashes. Future source coverage still needs review.
