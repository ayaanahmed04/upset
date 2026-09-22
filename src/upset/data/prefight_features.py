"""Calculate pre-fight metrics from dated fighter history snapshots."""

from dataclasses import asdict, dataclass
from datetime import date

from upset.data.identity import validate_upset_fighter_id
from upset.data.prefight import PreFightSnapshot


@dataclass(frozen=True)
class PreFightFeatures:
    """Rates from earlier fight totals for one upcoming fight participant."""

    source_bout_id: str
    event_date: str
    upset_fighter_id: str
    prior_fights: int
    prior_fight_seconds: int
    sig_strikes_landed_per_minute: float | None
    sig_strikes_accuracy: float | None
    takedowns_landed_per_15_minutes: float | None
    takedown_accuracy: float | None
    knockdowns_per_15_minutes: float | None
    submission_attempts_per_15_minutes: float | None
    control_observed_fraction: float | None

    def as_record(self) -> dict:
        return asdict(self)


def _ratio(numerator: int, denominator: int) -> float | None:
    """An unknown denominator produces missing data, never an invented zero."""
    return numerator / denominator if denominator > 0 else None


def _per_minutes(count: int, seconds: int, window_minutes: int) -> float | None:
    value = _ratio(count, seconds)
    return value * 60 * window_minutes if value is not None else None


def _validate_snapshot(snapshot: PreFightSnapshot) -> None:
    if not isinstance(snapshot.source_bout_id, str) or not snapshot.source_bout_id:
        raise ValueError("Pre-fight snapshot needs a source bout ID.")
    validate_upset_fighter_id(snapshot.upset_fighter_id)
    try:
        parsed = date.fromisoformat(snapshot.event_date)
        if parsed.isoformat() != snapshot.event_date:
            raise ValueError("noncanonical date")
    except (TypeError, ValueError) as error:
        raise ValueError(f"Invalid snapshot date: {snapshot.event_date}") from error

    counts = (
        "prior_fights",
        "prior_fight_seconds",
        "prior_sig_strikes_landed",
        "prior_sig_strikes_attempted",
        "prior_takedowns_landed",
        "prior_takedowns_attempted",
        "prior_knockdowns",
        "prior_submission_attempts",
        "prior_control_observed_fights",
    )
    for field in counts:
        value = getattr(snapshot, field)
        if type(value) is not int or value < 0:
            raise ValueError(f"Invalid {field}: {value!r}")
    if snapshot.prior_sig_strikes_landed > snapshot.prior_sig_strikes_attempted:
        raise ValueError("Landed significant strikes exceed attempts.")
    if snapshot.prior_takedowns_landed > snapshot.prior_takedowns_attempted:
        raise ValueError("Landed takedowns exceed attempts.")
    if snapshot.prior_control_observed_fights > snapshot.prior_fights:
        raise ValueError("Observed control fights exceed prior fights.")
    if snapshot.prior_control_observed_fights == 0:
        if snapshot.prior_control_seconds is not None:
            raise ValueError("Control seconds require observed control fights.")
    elif (
        type(snapshot.prior_control_seconds) is not int
        or snapshot.prior_control_seconds < 0
    ):
        raise ValueError("Observed control seconds must be nonnegative.")
    if snapshot.prior_fights == 0 and any(
        getattr(snapshot, field) for field in counts[1:]
    ):
        raise ValueError("A first fight cannot have prior performance totals.")


def build_prefight_features(
    snapshots: list[PreFightSnapshot],
) -> tuple[PreFightFeatures, ...]:
    """Derive rates without re-reading current or future fight results."""
    if not snapshots:
        raise ValueError("Pre-fight snapshots must be nonempty.")

    seen: set[tuple[str, str]] = set()
    features = []
    for snapshot in snapshots:
        _validate_snapshot(snapshot)
        key = (snapshot.source_bout_id, snapshot.upset_fighter_id)
        if key in seen:
            raise ValueError(f"Duplicate pre-fight snapshot: {key}")
        seen.add(key)

        seconds = snapshot.prior_fight_seconds
        features.append(
            PreFightFeatures(
                source_bout_id=snapshot.source_bout_id,
                event_date=snapshot.event_date,
                upset_fighter_id=snapshot.upset_fighter_id,
                prior_fights=snapshot.prior_fights,
                prior_fight_seconds=seconds,
                sig_strikes_landed_per_minute=_per_minutes(
                    snapshot.prior_sig_strikes_landed, seconds, 1
                ),
                sig_strikes_accuracy=_ratio(
                    snapshot.prior_sig_strikes_landed,
                    snapshot.prior_sig_strikes_attempted,
                ),
                takedowns_landed_per_15_minutes=_per_minutes(
                    snapshot.prior_takedowns_landed, seconds, 15
                ),
                takedown_accuracy=_ratio(
                    snapshot.prior_takedowns_landed,
                    snapshot.prior_takedowns_attempted,
                ),
                knockdowns_per_15_minutes=_per_minutes(
                    snapshot.prior_knockdowns, seconds, 15
                ),
                submission_attempts_per_15_minutes=_per_minutes(
                    snapshot.prior_submission_attempts, seconds, 15
                ),
                control_observed_fraction=_ratio(
                    snapshot.prior_control_observed_fights, snapshot.prior_fights
                ),
            )
        )

    return tuple(
        sorted(
            features,
            key=lambda item: (
                item.event_date,
                item.source_bout_id,
                item.upset_fighter_id,
            ),
        )
    )
