# Cached current bouts through the frozen prediction pipeline

The full Mac run subsequently completed: 248 replayed bouts, 245 decisive,
153 correct picks (62.44898%), Brier 0.23349349142122194 and log loss
0.6586190997662509. All three uploaded output hashes match; all metrics were
independently reproduced from predictions. The reported historical audit
matched all rows at zero error. See `CITO_MATCHUP_IDENTITIES.md` for verification
limits and the next two reviewed identity links. The implementation/testing
and initial pending-run notes below describe the original delivery.

The current identity integration succeeded on Ayaan's Mac: 248 identified
current bouts, 91 excluded bouts and 98 unresolved provider fighters. The
updated private viewer contains 8,799 bouts and 17,598 fighter-stat rows.

`python -m upset.modeling.run_current_replay` connects the existing accepted
current stage to the frozen 36-feature model. It first reruns the historical
feature audit, checks the accepted model SHA-256 and its seven original source
hashes, verifies current exports/registry/stage hashes, and compares every
staged fight/stat against the canonical current records. It builds a pre-date
snapshot for each already completed identified bout, recomputes the frozen
probability and checks fighter-order symmetry. It never retrains the model,
changes the interface, imports records into the live forecast archive or
makes API requests.

This is a retrospective pipeline diagnostic, not a prospective prediction
claim or a new holdout. Results for this period were already observed. The
identity-linked subset is selected, omitted bouts affect the rolling history,
and historical acquisition times cannot be reconstructed from the current
captures. Diagnostic accuracy, log loss and Brier do not establish future
accuracy. Draws/NCs remain in history and are excluded from binary metrics.
The frozen historical labels remain as trained; later reviewed amendments
are not backdated into the replay.

## Missing history

The uploaded `upset_identity_review_v2.zip` was checked offline against its
registry and canonical/identified cohort:

- 248 linked current bouts and 91 excluded current bouts.
- 11 replay bouts have a directly missing earlier bout for a participant.
- 237 replay bouts occur after an omitted cohort bout; population smoothing
  can therefore differ, even when neither participant has a direct gap.
- The first omitted cohort bout date is March 14, 2026.

These are counts of dependencies, not measurements of the size or direction
of probability changes. Elo can also propagate omissions through later
opponents. A missing-direct-history count of zero does not certify source
coverage. Unknown identities are never treated as confirmed debutants.

`identity_priorities.jsonl` ranks unresolved provider IDs by how many linked
replay bouts directly depend on their omitted fights, then by blocked bouts.
It proposes review order, not identity links. The first priorities in this
cohort include Tyrell Fortune, Mark Vologdin, Felipe Franco, Christian Edwards,
Shanelle Dyer and Marcio Barbosa. Independent evidence remains necessary before
accepting a link or creating a new permanent identity.

## Run on the Mac

After applying the replay patch:

```bash
cd ~/Projects/upset
source .venv/bin/activate
python -m upset.modeling.run_current_replay
```

The default inputs use `cito_current_identity_v2`, its registry, the original
historical registry and the existing `models/symmetric_recent_elo_v1` artifact.
The latter must have SHA-256
`55bf4a6f363c9c45bd3db008b74faab5927318b6614836e440024f52d9c8894c`.
Do not refit a replacement to satisfy a missing artifact error.

The immutable `data/processed/current_replay_v1` directory contains:

- `features.jsonl`: strictly pre-date model inputs, with no outcomes.
- `predictions.jsonl`: retrospective probabilities, observed labels and gaps.
- `identity_priorities.jsonl`: actionable unresolved-identity review order.
- `manifest.json`: source/code hashes, symmetry/audit guarantees and diagnostic metrics.

Identical runs reuse the verified output. Changed inputs/code require a new
`--output` directory. Python source hashes and working-tree state are recorded;
ongoing HTML/CSS editing does not block the run. The CLI can run while the
viewer is serving in another terminal. It does not modify the viewer database.

The full historical audit and actual frozen probabilities require Ayaan's Mac:
the assistant has the uploaded current cohort, but not the full historical
feature files or actual model artifact. Local tests exercise timing, omission
reporting, source/hash integrity and output reuse with fixtures. No full-cohort
probability result has yet been claimed.

Next: inspect the actual replay and prioritize identity/coverage work, then
prepare a reviewed upcoming schedule and externally timestamp real pre-event
forecasts. The round archive can support a separate later experiment, without
holding up this existing-model integration.
