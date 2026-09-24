# Prospective prediction archive (prototype contract)

## What exists now

`python -m upset.modeling.run_prospective_archive` can **record** supplied
pre-event forecasts and **verify** saved batches. It does not train a model,
fetch a live card, infer fighter links, compute pre-fight features, or score
results. No real future prediction has been recorded yet. The latest accepted
historical source ends on 2026-03-07; updating its fights and statistics and
reviewing both new fighters' provider links is required before any useful
September 2026 forecast. One reviewed Cito fighter link is insufficient for a
full card. The defensive development comparison is still a candidate, not a
chosen live model.

The previous 2023-08-26+ test and the 2019/2021/2022/2023 development folds
were examined during model work. They cannot become fresh tests by rerunning
them. The prospective archive is intended to hold evidence from future events
whose outcomes were unknown when the forecasts were saved.

## Inputs to `record`

The command requires five distinct local files:

| File | Required contents |
| --- | --- |
| `--schedule` | JSONL with provider, source bout ID, both source fighter IDs, their reviewed UPSET UUIDs in canonical A/B order, scheduled start in UTC, observed-at time in UTC, and an HTTPS source URL. |
| `--forecasts` | JSONL with one row per scheduled bout: source bout ID, same UPSET IDs, probability of A winning, and the exact approved numeric A-minus-B pre-fight feature differences (or nulls). Winner/result fields are rejected. |
| `--model-spec` | JSON object with model name, 40-character training-code commit, training-through date, training-input SHA-256, model artifact SHA-256, and the ordered feature-column list. Only the four existing baseline/defense/outcome feature-set combinations are accepted. |
| `--model-artifact` | Nonempty trained model file whose bytes match the specification. The archive only copies and hashes this file; it never deserializes or executes it. |
| `--registry` | Valid committed fighter registry. The provider fighter IDs must already have reviewed links to the supplied permanent UPSET UUIDs. |

Schedule records must use canonical `YYYY-MM-DDTHH:MM:SSZ` timestamps. The
archive uses its local UTC clock at the moment of recording. A schedule
observation must be no more than 48 hours old and must precede recording; the
scheduled start must be **more than one hour later**. The model's stated
training-through date must precede the scheduled UTC date. These are
conservative input gates, not proof that the provider's scheduled start or
observed-at timestamp is accurate. A schedule change or earlier real start
can make an archived forecast ineligible for later prospective scoring.

There must be exactly one forecast for every scheduled bout. The feature
column names and order come from the supplied model specification; the
forecast file can include nulls, but cannot include labels or arbitrary
metadata as model inputs. Both the schedule and forecast file are checked for
duplicate or unmatched bouts. The source IDs are checked against reviewed
provider links in the copied fighter registry. Existing archived bouts cannot
be recorded again through this command, even with new probabilities.

## What the archive preserves

Under the ignored local `data/processed/prospective/` directory, one batch
contains byte-for-byte copies of `schedule.jsonl`, `forecasts.jsonl`,
`model.bin`, `model_spec.json`, `fighter_registry.json`, and a manifest. The
manifest stores its UTC recording time, provider/bout keys, and a SHA-256 of
every copied input. A lock serializes cooperative writers, and a complete
batch is staged and verified before its final directory appears. `verify`
checks hashes, schemas, provider identity links, and the saved pre-event
conditions without loading the model binary. It fails after a copied file is
changed or removed.

```bash
python -m upset.modeling.run_prospective_archive record \
  --schedule /path/to/reviewed_schedule.jsonl \
  --forecasts /path/to/frozen_forecasts.jsonl \
  --model-spec /path/to/model_spec.json \
  --model-artifact /path/to/model.bin

python -m upset.modeling.run_prospective_archive verify \
  data/processed/prospective/BATCH_DIRECTORY
```

The record command uses the actual system time; the optional injected clock
in the Python function exists for synthetic tests. A hash verifies bytes at
read-back, but **local files and the computer clock can be edited**. An
independent prospective performance claim needs a trustworthy external
pre-event timestamp, such as publishing the batch's hashes to a remote system
before the event, and later reconciling actual bout start times. A model hash
does not itself prove the submitted probabilities were computed by that
binary. A separate replay check for the actual trained model is still needed.

Do not store future results inside these batch files. A later scoring stage
should read a separately sourced, dated outcome file and report eligibility,
exclusions, score metrics, and the exact batch IDs without modifying saved
forecasts. New ingestion, model freezing and feature generation come first;
this archive is a tested storage gate awaiting those inputs.
