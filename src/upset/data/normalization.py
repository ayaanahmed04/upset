def parse_landed_attempted(value: str) -> tuple[int, int]:
    """Convert a value like '7 of 27' into (7, 27)."""
    landed, attempted = value.split(" of ")

    return int(landed), int(attempted)


def parse_control_time(value: str) -> int:
    """Convert a control-time value like '1:13' into total seconds."""
    minutes, seconds = value.split(":")

    return int(minutes) * 60 + int(seconds)

def normalize_cito_round(raw_round: dict) -> dict:
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

    return {
        "source": "cito",
        "source_round_stat_id": raw_round["id"],
        "source_bout_id": raw_round["boutId"],
        "source_fighter_slug": raw_round["fighterSlug"],
        "fighter_name": raw_round["fighterName"],
        "round_number": raw_round["round"],
        "knockdowns": raw_round["knockdowns"],
        "sig_strikes_landed": sig_landed,
        "sig_strikes_attempted": sig_attempted,
        "total_strikes_landed": total_landed,
        "total_strikes_attempted": total_attempted,
        "takedowns_landed": td_landed,
        "takedowns_attempted": td_attempted,
        "submission_attempts": raw_round["submissionAttempts"],
        "reversals": raw_round["reversals"],
        "control_seconds": parse_control_time(raw_round["controlTime"]),
        "head_landed": head_landed,
        "head_attempted": head_attempted,
        "body_landed": body_landed,
        "body_attempted": body_attempted,
        "leg_landed": leg_landed,
        "leg_attempted": leg_attempted,
        "distance_landed": distance_landed,
        "distance_attempted": distance_attempted,
        "clinch_landed": clinch_landed,
        "clinch_attempted": clinch_attempted,
        "ground_landed": ground_landed,
        "ground_attempted": ground_attempted,
        "source_last_synced_at": raw_round.get("lastSyncedAt"),
    }