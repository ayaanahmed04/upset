# UPSET Field Mappings and Export Contract

This document describes how source data is translated into UPSET's current
canonical data models.

It documents implemented behavior only. Future internal identifiers,
historical fight-stat normalization, feature engineering, and machine-learning
datasets are intentionally outside this document's scope.

## Canonical Models

The canonical dataclasses are defined in `src/upset/data/models.py`:

- `Fighter`: provider-independent fighter identity and profile information
- `Event`: provider-independent UFC event information
- `Fight`: provider-independent fight identity and result information
- `RoundStats`: statistics for one fighter in one round
- `FightStats`: one fighter's statistics across one complete fight

"Provider-independent" means downstream UPSET code can use consistent field
names. It does not mean the current identifiers are shared across providers.

## Source and Identifier Rules

Every canonical record stores a `source` value identifying the dataset or
provider that supplied it.

Current source values:

- `kaggle_ufc_1994_2026`
- `cito`

Fields such as `source_fighter_id`, `source_event_id`, and `source_bout_id`
remain provider-specific. For example, the fighter IDs extracted from the
historical dataset's UFCStats URLs are not permanent UPSET-owned fighter IDs.

UPSET-owned internal IDs and cross-provider identity mappings have not yet been
designed.

Fighter names are display labels, not unique identifiers. Different fighters
can share the same name, and a fighter's name can change or be formatted
differently across providers.

## Historical Kaggle Fighter Mappings

Input:

`data/raw/kaggle_ufc_1994_2026/ufc_fighters_final.csv`

One input row represents one source fighter profile.

| Raw column     | Canonical `Fighter` field | Conversion or current behavior                                                 |
| -------------- | ------------------------- | ------------------------------------------------------------------------------ |
| `Fighter_URL`  | `source_fighter_id`       | Extract the 16-character UFCStats fighter ID from the URL.                     |
| `Fighter_URL`  | `source_url`              | Preserve the complete source URL.                                              |
| —              | `source`                  | Set to `kaggle_ufc_1994_2026`.                                                 |
| —              | `source_fighter_slug`     | Set to `None`; this source does not supply a separate slug.                    |
| `Fighter_Name` | `name`                    | Trim surrounding whitespace and require non-empty text.                        |
| `Height`       | `height_inches`           | Convert feet and inches, such as `5' 11"`, into total inches as a `float`.     |
| `Weight`       | `weight_lbs`              | Remove the `lbs.` suffix and store pounds as a `float`.                        |
| `Reach`        | `reach_inches`            | Remove the inch symbol and store inches as a `float`.                          |
| `Stance`       | `stance`                  | Trim text; an empty value becomes `None`.                                      |
| `DOB`          | `date_of_birth`           | Validate and preserve an ISO `YYYY-MM-DD` date; an empty value becomes `None`. |
| —              | `division`                | Set to `None`; it is not supplied by the normalized historical profile.        |
| —              | `status`                  | Set to `None`.                                                                 |
| —              | `champion_status`         | Set to `None`.                                                                 |

### Historical career aggregates not currently mapped

The following fighter columns are intentionally excluded from `Fighter`:

| Raw column | Current status |
| ---------- | -------------- |
| `Wins`     | Not mapped     |
| `Losses`   | Not mapped     |
| `Draws`    | Not mapped     |
| `SLpM`     | Not mapped     |
| `Str_Acc`  | Not mapped     |
| `SApM`     | Not mapped     |
| `Str_Def`  | Not mapped     |
| `TD_Avg`   | Not mapped     |
| `TD_Acc`   | Not mapped     |
| `TD_Def`   | Not mapped     |
| `Sub_Avg`  | Not mapped     |

These values are current career aggregates from the source snapshot. They are
not known to represent a fighter's record or performance as of each historical
fight date. Treating them as pre-fight facts would leak future information into
machine-learning features.

Future work must construct dated, leakage-safe fighter statistics using only
fights that occurred before the prediction date.

### Historical fighter missing values

Missing profile measurements remain `None`; they are not converted to zero.

Verified missing counts:

- Height: 318
- Weight: 86
- Reach: 1,940
- Stance: 849
- Date of birth: 506

Extreme values that pass the documented source format are preserved. For
example, Emmanuel Yarbrough's source-reported 770-pound profile weight is not
silently deleted or capped.

## Historical Kaggle Fight Mappings

Input:

`data/raw/kaggle_ufc_1994_2026/ufc_gold_dataset_final.csv`

One input row represents one fight. Its statistics are fight-level totals, not
individual round records.

### Fight identity and result fields

| Raw column                       | Canonical `Fight` field | Conversion or current behavior                                                   |
| -------------------------------- | ----------------------- | -------------------------------------------------------------------------------- |
| `Fight_URL`                      | `source_bout_id`        | Extract the 16-character UFCStats fight ID from the URL.                         |
| `Fight_URL`                      | `source_url`            | Preserve the complete source URL.                                                |
| —                                | `source`                | Set to `kaggle_ufc_1994_2026`.                                                   |
| `Fighter_1`                      | `fighter_1_name`        | Trim and require non-empty text.                                                 |
| `Fighter_2`                      | `fighter_2_name`        | Trim and require non-empty text.                                                 |
| `Fighter_1` plus profile linking | `source_fighter_1_id`   | Populated later by the historical identity-linking step.                         |
| `Fighter_2` plus profile linking | `source_fighter_2_id`   | Populated later by the historical identity-linking step.                         |
| `Winner`                         | `source_winner_label`   | Preserve the original source label.                                              |
| `Winner`                         | `winner_name`           | Preserve a participant's name when it matches exactly; use `None` for `Draw/NC`. |
| `Method`                         | `result_method`         | Preserve trimmed source text.                                                    |
| `End_Round`                      | `result_round`          | Require a positive whole number and store it as an `int`.                        |
| `End_Time`                       | `result_time`           | Preserve the source's round-time text.                                           |
| `Weight_Class`                   | `weight_class`          | Preserve trimmed source text.                                                    |
| `Event_Date`                     | `event_date`            | Validate and store an ISO `YYYY-MM-DD` date.                                     |
| —                                | `source_event_id`       | Remains `None`; a historical event entity is not yet linked.                     |

### Combined `Draw/NC` outcomes

The historical source combines draws and no contests under the single label
`Draw/NC`.

The snapshot contains 151 such records. UPSET preserves:

- `source_winner_label="Draw/NC"`
- `winner_name=None`

UPSET does not guess whether an individual record was a draw or no contest from
the method text alone.

### Historical fight-stat mappings

One historical fight row produces two canonical `FightStats` records: one for
each linked fighter.

The combination of `source`, `source_bout_id`, and `source_fighter_id`
uniquely identifies one fighter's statistical performance in one fight.

#### Shared fight fields

| Raw source             | Canonical `FightStats` field | Conversion or behavior                                                        |
| ---------------------- | ---------------------------- | ----------------------------------------------------------------------------- |
| —                      | `source`                     | Set to `kaggle_ufc_1994_2026`.                                                |
| `Fight_URL`            | `source_bout_id`             | Use the validated 16-character UFCStats fight ID.                             |
| Linked fighter profile | `source_fighter_id`          | Use the reviewed source fighter ID attached by the identity-linking pipeline. |
| `Total_Fight_Time_Sec` | `fight_duration_seconds`     | Require a positive whole number.                                              |
| `Time_Format`          | `source_time_format`         | Require and preserve non-empty source text.                                   |

#### Participant-stat fields

For each row, `F1_` columns produce the first fighter's record and `F2_`
columns produce the second fighter's record.

| Raw suffix   | Canonical `FightStats` field |
| ------------ | ---------------------------- |
| `KD`         | `knockdowns`                 |
| `Sig_Landed` | `sig_strikes_landed`         |
| `Sig_Att`    | `sig_strikes_attempted`      |
| `TD_Landed`  | `takedowns_landed`           |
| `TD_Att`     | `takedowns_attempted`        |
| `Sub_Att`    | `submission_attempts`        |
| `Ctrl_Sec`   | `control_seconds`            |
| `Head`       | `head_landed`                |
| `Body`       | `body_landed`                |
| `Leg`        | `leg_landed`                 |
| `Distance`   | `distance_landed`            |
| `Clinch`     | `clinch_landed`              |
| `Ground`     | `ground_landed`              |

All statistic values must be non-negative whole numbers. Significant strikes
landed cannot exceed significant strikes attempted, and takedowns landed
cannot exceed takedowns attempted.

The audit confirmed across all 17,102 fighter appearances that:

- `Head + Body + Leg = Sig_Landed`
- `Distance + Clinch + Ground = Sig_Landed`

These are two breakdowns of the same landed significant strikes. They must not
be added together.

The historical source does not provide total-strike counts, reversals,
target-specific attempts, position-specific attempts, or true round-level
statistics. Those fields are not invented during normalization.

### Durability source audit

Run `python -m upset.data.audit_durability_sources` after the identified
fight and fight-stat exports. It requires exactly two identified statistics
records for each fight and checks each source fighter ID against its UPSET
identity. It reports all original result-method strings verbatim; this is
needed before defining a KO/TKO or submission-loss feature. For each fighter,
the *opponent's* recorded KD count is the fighter's recorded knockdowns
conceded. The report counts positive opponent KD appearances and distinct
fighter IDs with at least one recorded knockdown conceded. It does not yet
publish pre-fight features or retrain the baseline.

The full historical audit reported 8,551 fights, 17,102 fighter-fight rows,
3,655 scored knockdowns, 3,139 fighter-fight rows with at least one opponent
knockdown, and 1,536 distinct fighters with at least one recorded knockdown
conceded. The greatest aggregate recorded for one fighter was 12. The source
method distribution was: KO/TKO 2,688; Submission 1,655; Decision - Unanimous
3,083; Decision - Split 815; Decision - Majority 98; TKO - Doctor's Stoppage
97; Overturned 58; Could Not Continue 32; DQ 23; Other 2. There were 151
combined Draw/NC winner labels. These method totals count all bouts and are
not yet a validated tally of fighters who lost by a given method.

The historical fight-level totals contain no real round rows. To inspect
one known Cito bout, run `python -m upset.data.probe_cito_rounds` with the
local Cito key in `CITO_API_KEY` or `.env`. This makes one API request and
prints the response field names and row counts, not the key or full records.
The reviewed UFC 311 bout returned HTTP 403 and code
`HISTORY_WINDOW_EXCEEDED`, so no historical round-row shape was observed.
On an error the probe prints only the HTTP
status and provider error type/code when present; it omits the response
message, records, and key. This specific 403 is the key's historical access
window, rather than a rate limit (429). Access and coverage must be confirmed
before ingestion.
Provider round records need verified historical coverage and fighter links
before they can be joined to the historical cohort. Raw Cito profile totals
must not be used as past-at-date prediction features.

### Local round acquisition (source records only)

Use a completed recent bout ID from Cito's documented recent-event and
event-bouts endpoints. Run `python -m upset.data.probe_cito_recent` to list
recent event slugs and dates, then
`python -m upset.data.probe_cito_recent --event EVENT_SLUG` to list that
event's bout IDs and status flags. Both commands show limited identifiers,
not complete provider records or the API key; an unknown listing shape stops
without guessing. Fetch a single completed bout with stats using
`python -m upset.data.collect_cito_rounds --bout-id BOUT_ID`. The local
`CITO_API_KEY` or `.env` is used; no key is written into the output.
Alternatively pass `--bout-ids-file PATH` with one ID per line. After access
and coverage are established, `--identified-fights PATH` can read IDs from
the existing identified historical JSONL. Do not start that historical
collection under the current key: older rounds return
`HISTORY_WINDOW_EXCEEDED`.

The command defaults to one *new* request per run (`--limit 1`) and a
seven-second pause between new calls (`--delay 7`) to stay below Cito's
free-plan limit of ten requests per minute. A higher-tier plan may use an
explicit shorter delay within its documented limits. Each successfully validated
response is saved as one JSON file in ignored `data/raw/cito_rounds/`, with
the Cito source and requested bout ID. Cached files are read and validated
before being skipped, so a stopped run can resume. A failed, empty, or
unrecognized response is never cached as complete; API errors stop the run
with status and safe error labels only. A saved provider response is not yet
a normalized `RoundStats` record or a reviewed fighter identity link. The
current accepted list shapes are `data` as a list or one list under
`data.rounds`, `rows`, `items`, `results`, or `stats`; adapt this only after
inspecting a real response. Raw data stays local and out of Git.

The live `cryptocom-ufc-331-jsonapi-13` sample returned 10 rows: Alexandre
Pantoja and Joshua Van each have one row for rounds 1 through 5. The row field
names match the existing Cito `RoundStats` mapping below. This checks the
sample's shape and fighter/round coverage. The Mac then normalized all ten
records and validated the per-round strike arithmetic, but their sums still
need to be checked against fight totals.

### Offline round export

Run `python -m upset.data.export_cito_rounds` after saving recent round files.
It reads cached files in `data/raw/cito_rounds/` without making API calls and
writes `data/processed/cito/round_stats.jsonl`. Override locations with
`--input-dir` and `--output`. Each exported row is one Cito fighter in one
round, with Cito IDs and slugs; it does not yet contain a reviewed UPSET fighter
ID or pre-fight snapshot. Both folders are ignored by Git.

The exporter checks saved source/bout IDs, numeric values, strike breakdowns,
two fighters per bout, unique fighter/round and provider row IDs, and matching
consecutive round sets. It rejects all output if any cached bout fails, writes
in stable order, and verifies a temporary file before replacing the prior
export. These checks do not establish that the round sums match Cito's bout
totals or the separate historical Kaggle cohort.

To inspect Cito's separately requested fight-total response for the same bout, run
`python -m upset.data.probe_cito_totals --bout-id BOUT_ID`. This requests the
documented `/bouts/{id}/stats` endpoint once, preserves the response in
ignored `data/raw/cito_totals/BOUT_ID.json`, and prints only field names and
shape. Repeated runs validate the cached file without another request. The
live Pantoja–Van response has `data.availability`, two `data.boutStats` rows
(one per fighter), and ten `data.roundStats` rows (one per fighter per round).
The bout rows have the same Cito stat field names as the rounds, except that
they have no `round` field.

With both cached inputs present, run
`python -m upset.data.audit_cito_round_totals --bout-id BOUT_ID`. This offline
check matches each fighter and round between the two separately saved Cito
responses, compares all numeric round-stat fields, and sums each fighter's
rounds to compare with that fighter's `boutStats`. It stops on missing fighters,
rounds, or nonmatching counts, showing a short numeric mismatch summary.
This is a **Cito internal consistency check**, not independent verification
from a second provider. A successful result cannot establish historical round
coverage, licensing rights, or improved predictive performance. Fight totals
and current-bout rounds must never be used as that bout's pre-fight features.

## Cito Fighter Mappings

One Cito fighter record maps to one canonical `Fighter`.

| Cito field       | Canonical `Fighter` field | Conversion or current behavior                                       |
| ---------------- | ------------------------- | -------------------------------------------------------------------- |
| `id`             | `source_fighter_id`       | Preserve the provider ID.                                            |
| `slug`           | `source_fighter_slug`     | Preserve the provider slug.                                          |
| `name`           | `name`                    | Preserve provider text.                                              |
| `heightInches`   | `height_inches`           | Convert a present value to `float`; missing or empty becomes `None`. |
| `weightLbs`      | `weight_lbs`              | Convert a present value to `float`; missing or empty becomes `None`. |
| `reachInches`    | `reach_inches`            | Convert a present value to `float`; missing or empty becomes `None`. |
| `stance`         | `stance`                  | Preserve the optional provider value.                                |
| `division`       | `division`                | Preserve the optional provider value.                                |
| `status`         | `status`                  | Preserve the optional provider value.                                |
| `championStatus` | `champion_status`         | Preserve the optional provider value.                                |
| —                | `source`                  | Set to `cito`.                                                       |
| —                | `date_of_birth`           | Currently `None`; not populated by this normalization function.      |
| —                | `source_url`              | Currently `None`.                                                    |

## Cito Event Mappings

One Cito event record maps to one canonical `Event`.

| Cito field  | Canonical `Event` field | Conversion or current behavior       |
| ----------- | ----------------------- | ------------------------------------ |
| `id`        | `source_event_id`       | Convert to `str`.                    |
| `slug`      | `source_event_slug`     | Preserve the provider slug.          |
| `title`     | `title`                 | Preserve provider text.              |
| `eventDate` | `event_date`            | Preserve the provider's date text.   |
| `hasStats`  | `has_stats`             | Preserve the optional Boolean value. |
| —           | `source`                | Set to `cito`.                       |

## Cito Fight Mappings

One Cito bout record maps to one canonical `Fight`.

| Cito field                          | Canonical `Fight` field | Conversion or current behavior                                        |
| ----------------------------------- | ----------------------- | --------------------------------------------------------------------- |
| `id`                                | `source_bout_id`        | Convert to `str`.                                                     |
| `fighters[0].fighterName`           | `fighter_1_name`        | Preserve Cito's participant-list order.                               |
| `fighters[1].fighterName`           | `fighter_2_name`        | Preserve Cito's participant-list order.                               |
| `fighters[0].fighterId`             | `source_fighter_1_id`   | Convert a present ID to `str`; missing remains `None`.                |
| `fighters[1].fighterId`             | `source_fighter_2_id`   | Convert a present ID to `str`; missing remains `None`.                |
| `eventSlug` plus a supplied `Event` | `source_event_id`       | Attach the event ID only after the provider and event slug match.     |
| `winnerFighterSlug`                 | `winner_name`           | Find the one participant whose slug matches the winner slug.          |
| `method`                            | `result_method`         | Preserve the optional provider value.                                 |
| `resultRound`                       | `result_round`          | Convert a present value to `int`.                                     |
| `resultTime`                        | `result_time`           | Preserve the optional provider value.                                 |
| `weightClass`                       | `weight_class`          | Preserve the optional provider value.                                 |
| —                                   | `source`                | Set to `cito`.                                                        |
| —                                   | `event_date`            | Currently `None` on the fight; the date exists on the linked `Event`. |
| —                                   | `source_url`            | Currently `None`.                                                     |
| —                                   | `source_winner_label`   | Currently `None`.                                                     |

Cito's participant-list order is preserved. `fighter_1` is not assumed to mean
the red corner.

A Cito bout must contain exactly two fighters. If a winner slug is present, it
must match exactly one participant. A supplied event must have source `cito`
and a slug matching the bout's `eventSlug`.

## Cito Round-Stat Mappings

One Cito round-stat record represents one fighter in one round.

| Cito field           | Canonical `RoundStats` field                      | Conversion or current behavior                  |
| -------------------- | ------------------------------------------------- | ----------------------------------------------- |
| `id`                 | `source_round_stat_id`                            | Preserve the provider round-stat ID.            |
| `boutId`             | `source_bout_id`                                  | Preserve the associated provider bout ID.       |
| `fighterSlug`        | `source_fighter_slug`                             | Preserve the provider fighter slug.             |
| `fighterName`        | `fighter_name`                                    | Preserve provider text.                         |
| `round`              | `round_number`                                    | Preserve the round number.                      |
| `knockdowns`         | `knockdowns`                                      | Preserve the integer count.                     |
| `significantStrikes` | `sig_strikes_landed`, `sig_strikes_attempted`     | Split text such as `7 of 27` into two integers. |
| `totalStrikes`       | `total_strikes_landed`, `total_strikes_attempted` | Split landed and attempted values.              |
| `takedowns`          | `takedowns_landed`, `takedowns_attempted`         | Split landed and attempted values.              |
| `submissionAttempts` | `submission_attempts`                             | Preserve the integer count.                     |
| `reversals`          | `reversals`                                       | Preserve the integer count.                     |
| `controlTime`        | `control_seconds`                                 | Convert `M:SS` text into total seconds.         |
| `head`               | `head_landed`, `head_attempted`                   | Split landed and attempted values.              |
| `body`               | `body_landed`, `body_attempted`                   | Split landed and attempted values.              |
| `leg`                | `leg_landed`, `leg_attempted`                     | Split landed and attempted values.              |
| `distance`           | `distance_landed`, `distance_attempted`           | Split landed and attempted values.              |
| `clinch`             | `clinch_landed`, `clinch_attempted`               | Split landed and attempted values.              |
| `ground`             | `ground_landed`, `ground_attempted`               | Split landed and attempted values.              |
| `lastSyncedAt`       | `source_last_synced_at`                           | Preserve the optional provider timestamp.       |
| —                    | `source`                                          | Set to `cito`.                                  |

Head, body, and leg are breakdowns of significant strikes by target. Distance,
clinch, and ground are breakdowns of significant strikes by position. They
must not be added to significant-strike totals as if they were separate
additional strikes.

## Dataset Grain

Dataset grain means what one row represents.

| Dataset or model    | One row represents                                               |
| ------------------- | ---------------------------------------------------------------- |
| Kaggle fighter CSV  | One source fighter profile                                       |
| Kaggle fight CSV    | One complete fight with both participants and fight-level totals |
| Canonical `Fighter` | One provider-specific fighter profile                            |
| Canonical `Event`   | One provider-specific UFC event                                  |
| Canonical `Fight`   | One provider-specific fight                                      |
| Cito `RoundStats`   | One fighter's statistics in one round                            |

| Canonical `FightStats` | One fighter's totals across one complete fight |

| `FighterIdentity` | One real-world fighter identity |
| `FighterProviderLink` | One provider fighter profile linked to one UPSET identity |

The Kaggle fight totals and Cito round records must remain distinguishable.
They cannot be combined as though they have the same level of detail.

## Units and Formats

| Field type                  | Canonical format                                                     |
| --------------------------- | -------------------------------------------------------------------- |
| Height                      | Total inches as `float`                                              |
| Reach                       | Inches as `float`                                                    |
| Weight                      | Pounds as `float`                                                    |
| Control time                | Total seconds as `int`                                               |
| Dates                       | ISO `YYYY-MM-DD` text when validated by UPSET                        |
| Result time                 | Source round-time text, generally `M:SS`                             |
| Landed/attempted statistics | Separate integer fields                                              |
| Round numbers               | Positive integers for historical results                             |
| Provider identifiers        | Text identifiers where normalized as declared by the canonical model |
| Missing optional values     | Python `None`, serialized to JSON `null`                             |

## Missing-Value and Coverage Rules

- Missing values remain missing; they are not automatically converted to zero.
- The strings `"None"` and `"nan"` must not be created from missing IDs or text.
- Historical raw files remain unchanged.
- Invalid required text, malformed identifiers, invalid dates, and unsupported
  numeric formats cause validation to fail.
- Historical career-statistic zeros may represent unavailable coverage and
  require further investigation.
- Historical control-time data appears structurally unavailable before UFC 21.
- UFC 20 on 1999-05-07 has no control-time signal in any fight.
- UFC 21 on 1999-07-16 is the first strong coverage boundary.
- Historical fight-stat normalization converts a zero control value before
  UFC 21 on 1999-07-16 into `None`.
- A nonzero pre-UFC-21 control value would be preserved if one were supplied.
- On and after 1999-07-16, zero remains a recorded zero.
- In the accepted snapshot, 360 fighter-fight control values become missing
  and 2,667 recorded zero-control values remain zero.
  transformation.
- The historical snapshot is frozen and is not a live current-events source.

## Historical Fighter Identity Linking

The historical fight CSV initially supplies participant names without fighter
profile IDs.

The linking pipeline:

1. Groups historical profiles by source and fighter name.
2. Automatically links a participant only when exactly one same-source profile
   candidate exists.
3. Requires an explicit reviewed override when a name has multiple candidates.
4. Fails instead of guessing when a participant is missing or ambiguous.

Verified linking results:

- Fights: 8,551
- Participant slots: 17,102
- Unique same-source matches: 17,056
- Ambiguous slots requiring overrides: 46
- Unresolved slots after linking: 0

The reviewed overrides are stored in:

`data/mappings/kaggle_fighter_overrides.json`

Each override identifies a specific fight and participant side and records the
selected source fighter ID, fighter name, event date, opponent, and review
evidence. The mapping is version-controlled because fighter names alone are
not reliable identifiers.

## UPSET Fighter Identity Registry

UPSET identities are stored separately from provider-specific `Fighter`
profiles.

The historical normalized profile field `source_fighter_id` contains the
fighter's UFCStats identifier. The identity-registry exporter creates a
provider link with:

| Registry field        | Historical source                                       |
| --------------------- | ------------------------------------------------------- |
| `provider`            | Constant `"ufcstats"`                                   |
| `provider_fighter_id` | Normalized `source_fighter_id`                          |
| `upset_fighter_id`    | Permanent UPSET-generated UUID4                         |
| `evidence`            | Description of the normalized historical profile import |

Each identity contains:

| Identity field     | Meaning                               |
| ------------------ | ------------------------------------- |
| `upset_fighter_id` | Permanent canonical lowercase UUID4   |
| `display_name`     | Editable human-readable fighter label |

Registry rules:

- Display names are not unique identifiers.
- Two identities may share the same display name.
- One provider profile may link to only one UPSET identity.
- Multiple provider profiles may link to the same identity.
- Every provider link must reference an existing identity.
- Existing UUIDs are preserved when the registry is rebuilt.
- New UUIDs are generated only for previously unseen provider fighter IDs.
- Existing identities and links are retained even if a later source snapshot
  omits a previously known profile.

The registry uses schema version `1` and is stored at:

`data/mappings/fighter_registry.json`

The accepted historical registry contains:

- 4,455 identities
- 4,455 UFCStats provider links
- 4,455 unique UPSET UUIDs
- 4,455 unique provider keys
- 4,448 unique display names
- Seven duplicate-name groups representing distinct people

## Reviewed Cito Provider Links

The version-controlled `data/mappings/cito_fighter_reviews.json` stores each
reviewed `(cito_fighter_id, ufcstats_fighter_id)` pair and a written evidence
trail. The exporter `python -m upset.data.export_reviewed_cito_links` looks up
the already-linked UFCStats ID, attaches the Cito provider ID to the same
permanent UPSET UUID, and safely saves the registry. Names do not serve as
join keys. Invalid or conflicting reviews abort before replacing the registry.

The first mapping identifies Islam Makhachev. The Cito fighter profile and
fight history were checked against the UFCStats fighter profile and the shared
UFC 311 fight ID `daef1691c7d6b1e4`. The sources differ on reach by 0.5 inch;
the review records that difference. After this mapping, the registry has 4,455
identities and 4,456 provider links (4,455 UFCStats, one Cito).

## Historical Identity-Enriched Exports

Run `python -m upset.data.export_identified` after the profile, linked-fight,
fight-statistics, and identity-registry exports. The new files are in
`data/processed/kaggle_ufc_1994_2026/identified/`:

| Source file | Identified file | Added fields |
| --- | --- | --- |
| `fighters.jsonl` | `fighters_identified.jsonl` | `upset_fighter_id` |
| `fights_linked.jsonl` | `fights_identified.jsonl` | `upset_fighter_1_id`, `upset_fighter_2_id` |
| `fight_stats.jsonl` | `fight_stats_identified.jsonl` | `upset_fighter_id` |

The identified records preserve all source fields. Each UFCStats fighter ID
is resolved using the `(ufcstats, source_fighter_id)` registry link. All fights
must have two distinct registered profiles and exactly two matching stat
records. Extra registry identities are allowed because some fighters have no
historical fight in this snapshot. The exporter validates the entire input
set and verifies all output files before publishing the files.

## Dated Pre-Fight Fighter-Stat Snapshots

Run `python -m upset.data.export_prefight` after the identified export. It
reads `fights_identified.jsonl` and `fight_stats_identified.jsonl` and writes
`data/processed/kaggle_ufc_1994_2026/prefight/prefight_stats.jsonl`.
There is one row per `(source_bout_id, upset_fighter_id)`. The full export on
the Mac produced 17,102 rows from 8,551 fights. A second export produced the
same SHA-256 checksum:
`046b10deb6fe676097a99d499962f74dc1afb4791871fad16e6f414d5c62fc8a`.
An independent date-order audit checked every snapshot's prior fight count
against fights with strictly earlier dates and passed. The first event date
was 1994-03-11.

`event_date` is the target fight's date, and all `prior_*` fields summarize
only fights on strictly earlier dates. Both fighters receive a row even when
they have zero prior fights. Multiple fights on one date are excluded from one
another's snapshots. Totals include prior fight seconds, significant strikes
landed/attempted, takedowns landed/attempted, knockdowns, and submission
attempts. `prior_control_observed_fights` counts fights that actually recorded
control time; `prior_control_seconds` is `null` before any observed control
value and otherwise sums only observed values, including zero.

The exporter rejects missing, duplicate, or mismatched identified stats and
invalid dates before replacing the output file. These are dated historical
snapshots; rates are derived in a separate feature export. Strength of
schedule and other more complex features are future work. No current career
aggregates enter them.

## First Pre-Fight Fighter Features

Run `python -m upset.data.export_prefight_features` after the dated snapshot
export. It reads `prefight/prefight_stats.jsonl` and writes
`prefight/fighter_features.jsonl`, with one row for each fighter in each fight.
Both files use the same source bout ID, event date, and permanent fighter ID.
The full-data export on the Mac produced 17,102 rows. A second run produced
the same SHA-256 checksum:
`bf52fd0dd78065b5cfba7fe6ec13c3f36d7d12051343fb964b79eb6b2d00d664`.
An independent full-data audit matched all row keys, dates, history counts,
and seven rate calculations to their input snapshots. It found 2,699 rows
with zero earlier fights. This counts fight-participant rows, not distinct
fighters. An audit of the identified fight rows found 2,647 distinct name
labels and 2,648 distinct UPSET fighter IDs. Among the latter, 38 IDs appear
more than once on their first recorded fight date, contributing 51 additional
zero-prior-fight rows: `2,648 + 51 = 2,699`. Sampled repeats on 1994-03-11
include Patrick Smith and Royce Gracie on the UFC 2 tournament card. This
same-date exclusion is conservative because these source rows have no trusted
within-day ordering; it should not be interpreted as typical modern UFC
scheduling.

| Field | Calculation from prior totals |
| --- | --- |
| `sig_strikes_landed_per_minute` | `60 * prior_sig_strikes_landed / prior_fight_seconds` |
| `sig_strikes_accuracy` | `prior_sig_strikes_landed / prior_sig_strikes_attempted` |
| `takedowns_landed_per_15_minutes` | `900 * prior_takedowns_landed / prior_fight_seconds` |
| `takedown_accuracy` | `prior_takedowns_landed / prior_takedowns_attempted` |
| `knockdowns_per_15_minutes` | `900 * prior_knockdowns / prior_fight_seconds` |
| `submission_attempts_per_15_minutes` | `900 * prior_submission_attempts / prior_fight_seconds` |
| `control_observed_fraction` | `prior_control_observed_fights / prior_fights` |

Every division returns `null` when its denominator is zero. For example, a
fighter with no prior fights has `null` rates; a fighter with recorded fight
time and zero significant-strike attempts has a zero landed-strike pace and
`null` strike accuracy. `prior_fights` and `prior_fight_seconds` remain in the
output to show sample size. Control coverage is not a control-time pace; fight
time limited to bouts with observed control is unavailable in this snapshot.
The exporter requires two distinct snapshots on one date for every bout,
validates the input, and verifies a temporary JSONL file before replacing the
final output. No current fight result enters these formulas.

## Historical Matchups and Training Targets

Run `python -m upset.data.export_matchups` after the identified fights and
pre-fight fighter feature exports. Inputs are
`identified/fights_identified.jsonl` and
`prefight/fighter_features.jsonl`; output is
`prefight/matchups.jsonl`, with exactly one row per source bout. The full-data
export on the Mac produced 8,551 rows: 8,400 decisive binary targets and 151
combined `Draw/NC` labels with null targets. An independent audit compared
every row's IDs, date, nine differences, and label with its identified fight
and both fighter features. A second export produced the same SHA-256 checksum:
`02daa2db24fa80e318ea007127b712e5af1dfa017cf326f7aebbf49c2470146b`.

`fighter_a_id` and `fighter_b_id` sort the permanent UUIDs, regardless of
source side or winner. `feature_differences` contains only the nine pre-fight
numeric fields from `INPUT_FIELDS` in `matchups.py`, each named
`<field>_diff` and calculated as A minus B. If either fighter's field is
missing, its difference is `null`. Identifiers and the fight result are kept
outside this feature mapping.

| Outcome source | `target_a_win` | `training_exclusion_reason` |
| --- | --- | --- |
| Fighter A wins | `1` | `null` |
| Fighter B wins | `0` | `null` |
| `Draw/NC` | `null` | `ambiguous_draw_or_no_contest` |

The original `source_winner_label` is retained for inspection. A decisive
winner name must match exactly one participant before it can be mapped to an
UPSET fighter ID. The exporter verifies two matched, distinct fighter feature
rows per fight, matching event dates, all input rows used, a valid outcome,
and the written JSONL before replacing an older output. Model fitting,
imputation, class balance analysis, and chronological splits are handled in
the separate baseline command below.

## First Chronological Prediction Baseline

Run `python -m upset.modeling.run_baseline` after the verified matchup export.
The default input is `prefight/matchups.jsonl`; `--input PATH` can select an
equivalent export. The command prints a JSON report and does not save a model
or modify the processed data. Reported metrics depend on the local historical
data. The Mac full-data run passed its independent count and date audit, and
two identical reports had SHA-256
`a707b96f68146c3ddde4690b42810587c173c237051d4c8f74af66c40587b1df`.

| Period | Event dates | Bouts | Decisive | Draw/NC | Model accuracy | Model ROC AUC |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| Train | 1994-03-11 to 2021-03-06 | 5,989 | 5,881 | 108 | 0.5479 | 0.5735 |
| Validation | 2021-03-13 to 2023-08-19 | 1,283 | 1,259 | 24 | 0.5274 | 0.5561 |
| Test | 2023-08-26 to 2026-03-07 | 1,279 | 1,260 | 19 | 0.5198 | 0.5351 |

On the test period, model log loss was 0.69328 versus 0.69319 for the
training-prevalence comparison; model Brier score was 0.25008 versus 0.25002.
Lower is better for both. The model's higher test accuracy (0.5198 versus
0.4881 for the comparison) does not offset its slightly worse probability
scores. These measurements show a weak initial historical benchmark, not
validated performance for upcoming fights.

The input reader requires the exact matchup schema, all nine
`<field>_diff` keys, valid dated rows and target values, and one row per bout.
Each event date belongs to only one of train, validation, or test. Split
boundaries approximate 70/15/15 of *all* bout rows, including the ambiguous
rows; each period separately reports the number of excluded `Draw/NC` rows.
Only decisive rows contribute to model fitting and binary metrics. The model
input is the nine pre-fight differences; source IDs, date, winner text,
target, and exclusion reason are excluded from the input matrix.

Within the model pipeline, median filling, missingness indicators, and
standard scaling are fitted only using decisive training rows. The same
fitted transforms and logistic regression model are applied to later periods.
The JSON report gives per-period dates, counts, fighter A/B win balance,
missing inputs, and four binary metrics. It also evaluates a fixed-probability
comparison using fighter A's win rate in training. ROC AUC is `null` when a
period contains only one class. Do not treat the test period as a tuning set.

## Repeatable Exports

### Fighter identity registry

Command:

```bash
python -m upset.data.export_identity_registry
```

### Reviewed Cito fighter links

Command:

```bash
python -m upset.data.export_reviewed_cito_links
```

### Historical fights

Command:

```bash
python -m upset.data.export_historical
```

### Historical fighter-fight statistics

Command:

```bash
python -m upset.data.export_fight_stats
```

### Historical records with UPSET fighter IDs

Command:

```bash
python -m upset.data.export_identified
```

### Dated pre-fight fighter statistics

Command:

```bash
python -m upset.data.export_prefight
```

### Pre-fight fighter features

Command:

```bash
python -m upset.data.export_prefight_features
```

### Historical matchup rows and binary targets

Command:

```bash
python -m upset.data.export_matchups
```

### First chronological baseline

Command:

```bash
python -m upset.modeling.run_baseline
```
