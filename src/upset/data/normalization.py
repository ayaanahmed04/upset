from upset.data.models import Event, Fight, Fighter, RoundStats


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