from dataclasses import dataclass


@dataclass
class RoundStats:
    """Provider-independent statistics for one fighter in one round."""

    source: str
    source_round_stat_id: str
    source_bout_id: str
    source_fighter_slug: str

    fighter_name: str
    round_number: int

    knockdowns: int

    sig_strikes_landed: int
    sig_strikes_attempted: int

    total_strikes_landed: int
    total_strikes_attempted: int

    takedowns_landed: int
    takedowns_attempted: int

    submission_attempts: int
    reversals: int
    control_seconds: int

    head_landed: int
    head_attempted: int

    body_landed: int
    body_attempted: int

    leg_landed: int
    leg_attempted: int

    distance_landed: int
    distance_attempted: int

    clinch_landed: int
    clinch_attempted: int

    ground_landed: int
    ground_attempted: int

    source_last_synced_at: str | None = None

@dataclass
class Fighter:
    """Provider-independent fighter identity and profile information."""

    source: str
    source_fighter_id: str
    source_fighter_slug: str

    name: str

    height_inches: float | None = None
    weight_lbs: float | None = None
    reach_inches: float | None = None
    stance: str | None = None

    division: str | None = None
    status: str | None = None
    champion_status: str | None = None


@dataclass
class Event:
    """Provider-independent UFC event information."""

    source: str
    source_event_id: str
    source_event_slug: str

    title: str
    event_date: str

    has_stats: bool | None = None


@dataclass
class Fight:
    """Provider-independent information for one UFC fight."""

    source: str
    source_bout_id: str

    fighter_1_name: str
    fighter_2_name: str

    source_event_id: str | None = None
    source_fighter_1_id: str | None = None
    source_fighter_2_id: str | None = None

    winner_name: str | None = None
    result_method: str | None = None
    result_round: int | None = None
    result_time: str | None = None

    weight_class: str | None = None
    event_date: str | None = None
    source_url: str | None = None
    source_winner_label: str | None = None