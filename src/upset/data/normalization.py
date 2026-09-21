import re
from datetime import date

from upset.data.models import Event, Fight, Fighter, FightStats, RoundStats


def parse_landed_attempted(value: str) -> tuple[int, int]:
    """Convert a value like '7 of 27' into (7, 27)."""
    landed, attempted = value.split(" of ")

    return int(landed), int(attempted)


def parse_control_time(value: str) -> int:
    """Convert a control-time value like '1:13' into total seconds."""
    minutes, seconds = value.split(":")

    return int(minutes) * 60 + int(seconds)

def _optional_float(value: object) -> float | None:
    """Convert a value to float, while preserving missing values."""
    if value is None or value == "":
        return None

    return float(value)

def normalize_cito_fighter(raw_fighter: dict) -> Fighter:
    """Convert one Cito fighter record into UPSET's Fighter model."""

    return Fighter(
        source="cito",
        source_fighter_id=raw_fighter["id"],
        source_fighter_slug=raw_fighter["slug"],
        name=raw_fighter["name"],
        height_inches=_optional_float(raw_fighter.get("heightInches")),
        weight_lbs=_optional_float(raw_fighter.get("weightLbs")),
        reach_inches=_optional_float(raw_fighter.get("reachInches")),
        stance=raw_fighter.get("stance"),
        division=raw_fighter.get("division"),
        status=raw_fighter.get("status"),
        champion_status=raw_fighter.get("championStatus"),
    )

def normalize_cito_event(raw_event: dict) -> Event:
    """Convert one Cito event record into UPSET's Event model."""

    return Event(
        source="cito",
        source_event_id=str(raw_event["id"]),
        source_event_slug=raw_event["slug"],
        title=raw_event["title"],
        event_date=raw_event["eventDate"],
        has_stats=raw_event.get("hasStats"),
    )

def normalize_cito_round(raw_round: dict) -> RoundStats:
    """Convert one Cito round-stat record into UPSET's normalized format."""

    sig_landed, sig_attempted = parse_landed_attempted(
        raw_round["significantStrikes"]
    )
    total_landed, total_attempted = parse_landed_attempted(
        raw_round["totalStrikes"]
    )
    td_landed, td_attempted = parse_landed_attempted(
        raw_round["takedowns"]
    )

    head_landed, head_attempted = parse_landed_attempted(raw_round["head"])
    body_landed, body_attempted = parse_landed_attempted(raw_round["body"])
    leg_landed, leg_attempted = parse_landed_attempted(raw_round["leg"])

    distance_landed, distance_attempted = parse_landed_attempted(
        raw_round["distance"]
    )
    clinch_landed, clinch_attempted = parse_landed_attempted(
        raw_round["clinch"]
    )
    ground_landed, ground_attempted = parse_landed_attempted(
        raw_round["ground"]
    )

    return RoundStats(
        source="cito",
        source_round_stat_id=raw_round["id"],
        source_bout_id=raw_round["boutId"],
        source_fighter_slug=raw_round["fighterSlug"],
        fighter_name=raw_round["fighterName"],
        round_number=raw_round["round"],
        knockdowns=raw_round["knockdowns"],
        sig_strikes_landed=sig_landed,
        sig_strikes_attempted=sig_attempted,
        total_strikes_landed=total_landed,
        total_strikes_attempted=total_attempted,
        takedowns_landed=td_landed,
        takedowns_attempted=td_attempted,
        submission_attempts=raw_round["submissionAttempts"],
        reversals=raw_round["reversals"],
        control_seconds=parse_control_time(raw_round["controlTime"]),
        head_landed=head_landed,
        head_attempted=head_attempted,
        body_landed=body_landed,
        body_attempted=body_attempted,
        leg_landed=leg_landed,
        leg_attempted=leg_attempted,
        distance_landed=distance_landed,
        distance_attempted=distance_attempted,
        clinch_landed=clinch_landed,
        clinch_attempted=clinch_attempted,
        ground_landed=ground_landed,
        ground_attempted=ground_attempted,
        source_last_synced_at=raw_round.get("lastSyncedAt"),
    )

def normalize_cito_fight(
    raw_bout: dict,
    *,
    event: Event | None = None,
) -> Fight:
    """Convert one Cito bout into UPSET's Fight model."""

    fighters = raw_bout["fighters"]

    # Stop if the source record does not describe two participants.
    if len(fighters) != 2:
        raise ValueError("Expected exactly two fighters in a Cito bout.")

    # Keep Cito's list order. Fighter 1 does not necessarily mean red corner.
    fighter_1, fighter_2 = fighters

    # Identify the winner by matching the slug, not by assuming list order.
    winner_name = None
    winner_slug = raw_bout.get("winnerFighterSlug")

    if winner_slug:
        matching_fighters = [
            fighter
            for fighter in fighters
            if fighter["fighterSlug"] == winner_slug
        ]

        if len(matching_fighters) != 1:
            raise ValueError(
                "Winner slug must match exactly one fighter in the bout."
            )

        winner_name = matching_fighters[0]["fighterName"]

    # Only attach an event when its provider and slug match this bout.
    source_event_id = None

    if event is not None:
        if (
            event.source != "cito"
            or event.source_event_slug != raw_bout["eventSlug"]
        ):
            raise ValueError("Event does not match this Cito bout.")

        source_event_id = event.source_event_id

    # Missing IDs remain None; they must not become the text "None".
    fighter_1_id = fighter_1.get("fighterId")
    fighter_2_id = fighter_2.get("fighterId")
    result_round = raw_bout.get("resultRound")

    return Fight(
        source="cito",
        source_bout_id=str(raw_bout["id"]),
        fighter_1_name=fighter_1["fighterName"],
        fighter_2_name=fighter_2["fighterName"],
        source_event_id=source_event_id,
        source_fighter_1_id=(
            str(fighter_1_id) if fighter_1_id is not None else None
        ),
        source_fighter_2_id=(
            str(fighter_2_id) if fighter_2_id is not None else None
        ),
        winner_name=winner_name,
        result_method=raw_bout.get("method"),
        result_round=(
            int(result_round) if result_round is not None else None
        ),
        result_time=raw_bout.get("resultTime"),
        weight_class=raw_bout.get("weightClass"),
    )

def normalize_kaggle_fight(raw_fight: dict) -> Fight:
    """Convert one Silva historical fight row into UPSET's Fight model."""

    # Require actual text instead of silently converting missing data
    # into strings such as "nan" or "None".
    text_fields = (
        "Fight_URL",
        "Fighter_1",
        "Fighter_2",
        "Winner",
        "Weight_Class",
        "Method",
        "End_Time",
        "Event_Date",
    )
    values = {}

    for field in text_fields:
        value = raw_fight[field]

        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{field} must contain non-empty text.")

        values[field] = value.strip()

    # Extract the UFCStats fight identifier from the reference URL.
    # This only reads the URL text; it does not visit the website.
    url_match = re.fullmatch(
        r"https?://(?:www\.)?ufcstats\.com/fight-details/([0-9a-f]{16})/?",
        values["Fight_URL"],
    )

    if url_match is None:
        raise ValueError("Unrecognized UFCStats fight URL.")

    fighter_1 = values["Fighter_1"]
    fighter_2 = values["Fighter_2"]
    winner_label = values["Winner"]

    if winner_label == "Draw/NC":
        winner_name = None
    elif winner_label in (fighter_1, fighter_2):
        winner_name = winner_label
    else:
        raise ValueError("Winner must match a participant or be 'Draw/NC'.")

    # Validate the date and store it in YYYY-MM-DD format.
    event_date = date.fromisoformat(values["Event_Date"]).isoformat()

    # Reject fractional or non-positive rounds instead of truncating them.
    round_value = raw_fight["End_Round"]

    if isinstance(round_value, bool):
        raise TypeError("End_Round must be a positive whole number.")

    round_number = float(round_value)

    if not round_number.is_integer() or round_number < 1:
        raise ValueError("End_Round must be a positive whole number.")

    return Fight(
        source="kaggle_ufc_1994_2026",
        source_bout_id=url_match.group(1),
        fighter_1_name=fighter_1,
        fighter_2_name=fighter_2,
        winner_name=winner_name,
        result_method=values["Method"],
        result_round=int(round_number),
        result_time=values["End_Time"],
        weight_class=values["Weight_Class"],
        event_date=event_date,
        source_url=values["Fight_URL"],
        source_winner_label=winner_label,
    )

def parse_kaggle_measurement(
    value: str | None,
    *,
    field: str,
) -> float | None:
    """Convert a historical Height, Weight, or Reach into a number."""

    # Each pattern describes the source format we accept.
    patterns = {
        "Height": r"""([0-9]+)'\s*([0-9]+)" """.strip(),
        "Weight": r"([0-9]+(?:\.[0-9]+)?)\s+lbs\.",
        "Reach": r'([0-9]+(?:\.[0-9]+)?)"',
    }

    if field not in patterns:
        raise ValueError(f"Unsupported measurement field: {field}")

    if value is None:
        return None

    if not isinstance(value, str):
        raise TypeError(f"{field} must be text or None.")

    text = value.strip()

    # Missing measurements stay missing.
    if not text:
        return None

    match = re.fullmatch(patterns[field], text)

    if match is None:
        raise ValueError(f"Unrecognized {field} format: {value!r}")

    if field == "Height":
        feet = int(match.group(1))
        inches = int(match.group(2))

        if inches >= 12:
            raise ValueError("Height's inches component must be below 12.")

        measurement = float(feet * 12 + inches)
    else:
        measurement = float(match.group(1))

    if measurement <= 0:
        raise ValueError(f"{field} must be greater than zero.")

    return measurement

def normalize_kaggle_fighter(raw_fighter: dict) -> Fighter:
    """Convert one historical profile into UPSET's Fighter model."""

    # A profile must have both a name and a source URL.
    required_text = {}

    for field in ("Fighter_Name", "Fighter_URL"):
        value = raw_fighter[field]

        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{field} must contain non-empty text.")

        required_text[field] = value.strip()

    source_url = required_text["Fighter_URL"]

    # Extract the identifier from the URL without visiting the website.
    url_match = re.fullmatch(
        r"https?://(?:www\.)?ufcstats\.com/fighter-details/([0-9a-f]{16})/?",
        source_url,
    )

    if url_match is None:
        raise ValueError("Unrecognized UFCStats fighter URL.")

    # These columns must exist, but their values may be missing.
    optional_text = {}

    for field in ("Stance", "DOB"):
        value = raw_fighter[field]

        if value is None:
            optional_text[field] = None
        elif isinstance(value, str):
            optional_text[field] = value.strip() or None
        else:
            raise TypeError(f"{field} must be text or None.")

    # Require YYYY-MM-DD and validate that the date actually exists.
    birth_date = optional_text["DOB"]

    if birth_date is not None:
        if re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", birth_date) is None:
            raise ValueError("DOB must use YYYY-MM-DD.")

        birth_date = date.fromisoformat(birth_date).isoformat()

    return Fighter(
        source="kaggle_ufc_1994_2026",
        source_fighter_id=url_match.group(1),
        source_fighter_slug=None,
        name=required_text["Fighter_Name"],
        height_inches=parse_kaggle_measurement(
            raw_fighter["Height"],
            field="Height",
        ),
        weight_lbs=parse_kaggle_measurement(
            raw_fighter["Weight"],
            field="Weight",
        ),
        reach_inches=parse_kaggle_measurement(
            raw_fighter["Reach"],
            field="Reach",
        ),
        stance=optional_text["Stance"],
        date_of_birth=birth_date,
        source_url=source_url,
    )
_HISTORICAL_CONTROL_TIME_START = date(1999, 7, 16)


def _parse_nonnegative_int(value: object, *, field: str) -> int:
    """Convert a source value into a non-negative whole number."""

    if isinstance(value, bool):
        raise TypeError(f"{field} must be a non-negative whole number.")

    try:
        number = float(value)
    except (TypeError, ValueError) as error:
        raise TypeError(
            f"{field} must be a non-negative whole number."
        ) from error

    if not number.is_integer() or number < 0:
        raise ValueError(f"{field} must be a non-negative whole number.")

    return int(number)


def normalize_kaggle_fight_stats(
    raw_fight: dict,
    linked_fight: Fight,
) -> tuple[FightStats, FightStats]:
    """Convert one historical fight row into two fighter-stat records."""

    # Reuse the existing fight normalizer to validate the row's identity,
    # participant names, result, event date, and UFCStats fight URL.
    raw_identity = normalize_kaggle_fight(raw_fight)

    raw_key = (
        raw_identity.source,
        raw_identity.source_bout_id,
        raw_identity.fighter_1_name,
        raw_identity.fighter_2_name,
        raw_identity.event_date,
    )
    linked_key = (
        linked_fight.source,
        linked_fight.source_bout_id,
        linked_fight.fighter_1_name,
        linked_fight.fighter_2_name,
        linked_fight.event_date,
    )

    if linked_key != raw_key:
        raise ValueError("Linked fight does not match the historical row.")

    fighter_1_id = linked_fight.source_fighter_1_id
    fighter_2_id = linked_fight.source_fighter_2_id

    if fighter_1_id is None or fighter_2_id is None:
        raise ValueError("Historical fight must have both fighter IDs.")

    if fighter_1_id == fighter_2_id:
        raise ValueError("Fight participants must have different fighter IDs.")

    duration = _parse_nonnegative_int(
        raw_fight["Total_Fight_Time_Sec"],
        field="Total_Fight_Time_Sec",
    )

    if duration == 0:
        raise ValueError("Total_Fight_Time_Sec must be greater than zero.")

    time_format = raw_fight["Time_Format"]

    if not isinstance(time_format, str) or not time_format.strip():
        raise ValueError("Time_Format must contain non-empty text.")

    event_date = date.fromisoformat(raw_identity.event_date)
    records = []

    for side, fighter_id in (
        (1, fighter_1_id),
        (2, fighter_2_id),
    ):
        prefix = f"F{side}_"

        knockdowns = _parse_nonnegative_int(
            raw_fight[prefix + "KD"],
            field=prefix + "KD",
        )
        sig_landed = _parse_nonnegative_int(
            raw_fight[prefix + "Sig_Landed"],
            field=prefix + "Sig_Landed",
        )
        sig_attempted = _parse_nonnegative_int(
            raw_fight[prefix + "Sig_Att"],
            field=prefix + "Sig_Att",
        )
        takedowns_landed = _parse_nonnegative_int(
            raw_fight[prefix + "TD_Landed"],
            field=prefix + "TD_Landed",
        )
        takedowns_attempted = _parse_nonnegative_int(
            raw_fight[prefix + "TD_Att"],
            field=prefix + "TD_Att",
        )
        submission_attempts = _parse_nonnegative_int(
            raw_fight[prefix + "Sub_Att"],
            field=prefix + "Sub_Att",
        )
        raw_control_seconds = _parse_nonnegative_int(
            raw_fight[prefix + "Ctrl_Sec"],
            field=prefix + "Ctrl_Sec",
        )

        head_landed = _parse_nonnegative_int(
            raw_fight[prefix + "Head"],
            field=prefix + "Head",
        )
        body_landed = _parse_nonnegative_int(
            raw_fight[prefix + "Body"],
            field=prefix + "Body",
        )
        leg_landed = _parse_nonnegative_int(
            raw_fight[prefix + "Leg"],
            field=prefix + "Leg",
        )

        distance_landed = _parse_nonnegative_int(
            raw_fight[prefix + "Distance"],
            field=prefix + "Distance",
        )
        clinch_landed = _parse_nonnegative_int(
            raw_fight[prefix + "Clinch"],
            field=prefix + "Clinch",
        )
        ground_landed = _parse_nonnegative_int(
            raw_fight[prefix + "Ground"],
            field=prefix + "Ground",
        )

        if sig_landed > sig_attempted:
            raise ValueError(
                f"{prefix}Sig_Landed cannot exceed {prefix}Sig_Att."
            )

        if takedowns_landed > takedowns_attempted:
            raise ValueError(
                f"{prefix}TD_Landed cannot exceed {prefix}TD_Att."
            )

        target_total = head_landed + body_landed + leg_landed

        if target_total != sig_landed:
            raise ValueError(
                f"{prefix} target totals must equal significant strikes landed."
            )

        position_total = (
            distance_landed
            + clinch_landed
            + ground_landed
        )

        if position_total != sig_landed:
            raise ValueError(
                f"{prefix} position totals must equal "
                "significant strikes landed."
            )

        # Before UFC 21, a source zero means control time was unavailable.
        # A nonzero value would remain preserved if the source ever supplied one.
        if (
            event_date < _HISTORICAL_CONTROL_TIME_START
            and raw_control_seconds == 0
        ):
            control_seconds = None
        else:
            control_seconds = raw_control_seconds

        records.append(
            FightStats(
                source=raw_identity.source,
                source_bout_id=raw_identity.source_bout_id,
                source_fighter_id=fighter_id,
                fight_duration_seconds=duration,
                source_time_format=time_format.strip(),
                knockdowns=knockdowns,
                sig_strikes_landed=sig_landed,
                sig_strikes_attempted=sig_attempted,
                takedowns_landed=takedowns_landed,
                takedowns_attempted=takedowns_attempted,
                submission_attempts=submission_attempts,
                control_seconds=control_seconds,
                head_landed=head_landed,
                body_landed=body_landed,
                leg_landed=leg_landed,
                distance_landed=distance_landed,
                clinch_landed=clinch_landed,
                ground_landed=ground_landed,
            )
        )

    return records[0], records[1]