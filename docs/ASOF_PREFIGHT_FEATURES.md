# Building pre-event features from strictly earlier fights

The full historical model freeze succeeded on Ayaan's Mac: Ruff and all 351
tests passed; 8,400 decisive fights produced a saved artifact with SHA-256
`55bf4a6f363c9c45bd3db008b74faab5927318b6614836e440024f52d9c8894c`.
This is a *training artifact*, not a newly measured winner accuracy. Of the
8,551 source fights, 151 did not have an unambiguous named winner and were
excluded from binary training (their known statistics can still affect later
fighter history).

`build_asof_features` reconstructs the model's 36 ordered inputs from paired
identified fights and stats. It groups completed bouts and scheduled
requests by event **date**: first it snapshots every requested matchup,
then it updates fighters, opponent defense, Elo and recent-weighted history
with that date's results. A bout on the target date cannot contribute to
its own prediction, even if another bout on the card finished earlier. Each
completed record is identified by `(provider, bout ID)`, and duplicate
same-date fighter matchups across providers are refused. Distinct bout IDs
from the **same** historical provider on one date are retained: the accepted
historical builders counted both and froze their shared pre-date state. The
audit reports these same-provider pair groups with source bout IDs for manual
review. The completed results never appear in the exported feature file.

Before generating any future row, the `audit` CLI checks the pinned
`recent_form_v1` manifest and seven source hashes, rebuilds all **8,551**
historical matchup rows, and compares **all 36 columns** against the
previously accepted matchup, defensive, Elo and recent histories. This
separate replay computes rolling history directly from completed fight
stats and shares the existing rate definitions; it does not copy the saved
features. The original source histories already had their own independent
audits. On Ayaan's Mac the full audit **matched all 8,551 bouts, 17,102
fighter rows and 36 columns**, with maximum absolute error **0.0** and
reference manifest SHA-256
`9c5f6228ffb3028d010bc70a644e34be47591626443285fc50e5345107f49787`.
Ruff and 355 tests (plus 16 subtests) passed locally; Ayaan's earlier Mac run
passed Ruff and 354 tests before the additional regression test was added.

The sole reported same-provider, same-date pair is
`2750ac5854e8b28b` and `ec1bda9a4c2aab42` on 1997-12-21, between
Kazushi Sakuraba and Marcus Silveira. The repository's reviewed registry
links the reported fighter UUIDs to those names. [UFC's account of the event](https://www.ufc.com/news/best-nation-japan)
records two fights between them that night: a no contest followed by a
submission win for Sakuraba. The two distinct source bout IDs therefore
reflect actual separate fights, rather than a repeated import of one bout.
Both historical pre-fight snapshots use only information from dates before
the event; results from either bout affect subsequent dates. This audit
establishes agreement with the accepted historical inputs, **not** the
accuracy of future UFC predictions or the completeness of post-March data.

```bash
cd ~/Projects/upset
git fetch origin
git switch feature/asof-prefight-features
git pull --ff-only
source .venv/bin/activate
python -m ruff check . && python -m pytest &&
python -m upset.data.export_asof_features audit
```

`generate` additionally requires a source-linked future schedule, a
reviewed registry and at least one immutable completed-fight stage after
March 7, 2026. It checks each stage's manifest, output hashes, historical
hash, registry version and provider/date/count agreement. It then writes
`features.jsonl` (one row per scheduled bout with the 36 exact model
columns) and its hash manifest in an unoccupied directory. The existing
frozen replay command can take this feature file, but **do not record a
prospective claim** until the current provider has been checked for missing
events, bouts, and stats throughout the March-to-forecast gap. A stage is
explicitly partial; a correct feature formula cannot fix missing history.
Saved schedules and feature manifests need independent pre-event timestamp
evidence, and actual bout start times need subsequent review. The new model
artifact remains frozen at March 7; later *observed* fight stats can update
dated input features without retraining the model or leaking the scheduled
bout's outcome.

When the current data coverage is actually verified, the generation command
is:

```bash
python -m upset.data.export_asof_features generate \
  --schedule /path/to/reviewed_schedule.jsonl \
  --registry /path/to/updated_reviewed_registry.json \
  --stage /path/to/staged_completed_fights \
  --output data/processed/current/asof_batch_001
```

The default historical registry must still match the pinned reference. If
reviewed new provider links changed the working registry, pass the original
historical version with `--historical-registry`; use `--registry` for the
current version used by all supplied stages and the schedule. Duplicate
provider responses or unreviewed fighter IDs cause the run to stop.
