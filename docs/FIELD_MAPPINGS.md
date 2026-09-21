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

## Repeatable Exports

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
