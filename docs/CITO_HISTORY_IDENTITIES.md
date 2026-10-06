# Three reviewed history-backed fighter links

The saved history responses identify Harry Hardwick, Shem Rock and Abdul
Rakhman Yakhyaev in already frozen historical bouts. Each was checked against
the historical opponent, an existing opponent provider link, exact event date,
win/loss, method, round and clock. The individual provider/profile IDs are
allowlisted in `integrate_cito_history_identities.py`; names alone do not add
links. This establishes identity separately from round-stat completeness.

The workflow verifies the current export and original profile review hashes,
including all saved responses, then checks the allowlisted evidence against
the actual frozen historical fights and supplementary registry. It produces
a new registry overlay and restages the current accepted cohort. Original
exports, registry, historical result labels, model and interface are untouched.

```bash
python -m upset.data.integrate_cito_history_identities
python -m upset.data.build_research_db \
  --current data/processed/cito_current_identity_v2 \
  --registry data/processed/cito_current_identity_v2/fighter_registry.json \
  --output data/processed/research_v2
python -m upset.research_app --database data/processed/research_v2/upset.sqlite
```

Confirmed local result: three new links, 248 identified current bouts, 91 bouts
awaiting identity review and 98 unresolved provider fighters. Harry's linked
identity does not yet admit his current bout because his opponent remains
unlinked. The expanded viewer should have 8,799 bouts and 17,598 stat rows.
The Mac terminal and uploaded v2 export confirm these full-build counts; all
ten export output hashes match. The database manifest reports SHA-256
`52d9463d2ae764650af578b37f63c19b6512ea000284415eb1e44e9d8516df56`.
The database itself was not uploaded and was not independently reread here.
The real uploaded three history records passed the evidence
check here using their uploaded historical records and a scratch reconstruction
of the three known opponent links from verified bridge proposals. This is not
a rerun of the full private integration. Six focused tests cover integration,
database compatibility, preserved sources, missing rounds, conflicting clocks,
methods, identities, repeated evidence and altered hashes.

All operations are offline and immutable/reusable. No source DOB is inferred,
no additional round records are created, and no model is trained. Other
namesakes and new provider IDs remain unresolved. The historic round gaps
still require separate evidence.
