"""Build fighter history snapshots using only dates before each fight."""

from dataclasses import asdict, dataclass
from datetime import date
from itertools import groupby

from upset.data.export_identity_registry import HISTORICAL_SOURCE
from upset.data.identify_historical import IdentifiedFight, IdentifiedFightStats


@dataclass(frozen=True)
class PreFightSnapshot:
    """One fighter's known fight-stat history before an event date."""

    source_bout_id: str
    event_date: str
    upset_fighter_id: str
    prior_fights: int
    prior_fight_seconds: int
    prior_sig_strikes_landed: int
    prior_sig_strikes_attempted: int
    prior_takedowns_landed: int
    prior_takedowns_attempted: int
    prior_knockdowns: int
    prior_submission_attempts: int
    prior_control_observed_fights: int
    prior_control_seconds: int | None

    def as_record(self) -> dict:
        return asdict(self)


@dataclass
class _History:
    fights: int = 0
    fight_seconds: int = 0
    sig_strikes_landed: int = 0
    sig_strikes_attempted: int = 0
    takedowns_landed: int = 0
    takedowns_attempted: int = 0
    knockdowns: int = 0
    submission_attempts: int = 0
    control_observed_fights: int = 0
    control_seconds: int = 0

    def snapshot(
        self, bout_id: str, event_date: str, fighter_id: str
    ) -> PreFightSnapshot:
        return PreFightSnapshot(
            source_bout_id=bout_id,
            event_date=event_date,
            upset_fighter_id=fighter_id,
            prior_fights=self.fights,
            prior_fight_seconds=self.fight_seconds,
            prior_sig_strikes_landed=self.sig_strikes_landed,
            prior_sig_strikes_attempted=self.sig_strikes_attempted,
            prior_takedowns_landed=self.takedowns_landed,
            prior_takedowns_attempted=self.takedowns_attempted,
            prior_knockdowns=self.knockdowns,
            prior_submission_attempts=self.submission_attempts,
            prior_control_observed_fights=self.control_observed_fights,
            prior_control_seconds=(
                self.control_seconds if self.control_observed_fights else None
            ),
        )

    def add(self, record: IdentifiedFightStats) -> None:
        stats = record.stats
        self.fights += 1
        self.fight_seconds += stats.fight_duration_seconds
        self.sig_strikes_landed += stats.sig_strikes_landed
        self.sig_strikes_attempted += stats.sig_strikes_attempted
        self.takedowns_landed += stats.takedowns_landed
        self.takedowns_attempted += stats.takedowns_attempted
        self.knockdowns += stats.knockdowns
        self.submission_attempts += stats.submission_attempts
        if stats.control_seconds is not None:
            self.control_observed_fights += 1
            self.control_seconds += stats.control_seconds


def build_prefight_snapshots(
    fights: list[IdentifiedFight],
    fight_stats: list[IdentifiedFightStats],
) -> tuple[PreFightSnapshot, ...]:
    """Use strictly earlier dates; fight order within a day is unknown."""
    if not fights or not fight_stats:
        raise ValueError("Identified fights and statistics must be nonempty.")

    expected: dict[tuple[str, str], str] = {}
    seen_bouts: set[str] = set()
    for identified in fights:
        fight = identified.fight
        if fight.source != HISTORICAL_SOURCE:
            raise ValueError(f"Unexpected fight source: {fight.source}")
        if not fight.source_bout_id or fight.source_bout_id in seen_bouts:
            raise ValueError(f"Missing or duplicate fight ID: {fight.source_bout_id}")
        seen_bouts.add(fight.source_bout_id)
        try:
            parsed_date = date.fromisoformat(fight.event_date)
            if parsed_date.isoformat() != fight.event_date:
                raise ValueError("noncanonical date")
        except (TypeError, ValueError) as error:
            raise ValueError(
                f"Invalid event date for fight {fight.source_bout_id}: {fight.event_date}"
            ) from error
        if identified.upset_fighter_1_id == identified.upset_fighter_2_id:
            raise ValueError(
                f"Both fight participants have the same identity: {fight.source_bout_id}"
            )
        for source_id, upset_id in (
            (fight.source_fighter_1_id, identified.upset_fighter_1_id),
            (fight.source_fighter_2_id, identified.upset_fighter_2_id),
        ):
            if not source_id:
                raise ValueError(
                    f"Fight participant ID is missing: {fight.source_bout_id}"
                )
            key = (fight.source_bout_id, source_id)
            if key in expected:
                raise ValueError(f"Duplicate fight participant: {key}")
            expected[key] = upset_id

    stats_by_key: dict[tuple[str, str], IdentifiedFightStats] = {}
    count_fields = (
        "fight_duration_seconds",
        "sig_strikes_landed",
        "sig_strikes_attempted",
        "takedowns_landed",
        "takedowns_attempted",
        "knockdowns",
        "submission_attempts",
        "control_seconds",
    )
    for record in fight_stats:
        stats = record.stats
        if stats.source != HISTORICAL_SOURCE:
            raise ValueError(f"Unexpected statistics source: {stats.source}")
        key = (stats.source_bout_id, stats.source_fighter_id)
        if key in stats_by_key or key not in expected:
            raise ValueError(f"Duplicate or unexpected fight statistics: {key}")
        if expected[key] != record.upset_fighter_id:
            raise ValueError(f"Fight and statistics identities differ: {key}")
        for field in count_fields:
            value = getattr(stats, field)
            if value is not None and (type(value) is not int or value < 0):
                raise ValueError(f"Invalid {field} for {key}: {value!r}")
            if value is None and field != "control_seconds":
                raise ValueError(f"Missing {field} for {key}")
        stats_by_key[key] = record
    if stats_by_key.keys() != expected.keys():
        raise ValueError(
            f"Missing fight statistics: {list(expected.keys() - stats_by_key.keys())[:5]}"
        )

    history: dict[str, _History] = {}
    snapshots = []
    ordered = sorted(
        fights, key=lambda item: (item.fight.event_date, item.fight.source_bout_id)
    )
    for day, group in groupby(ordered, key=lambda item: item.fight.event_date):
        daily = list(group)
        # Take every snapshot before adding any result from this day.
        for identified in daily:
            fight = identified.fight
            for fighter_id in (
                identified.upset_fighter_1_id,
                identified.upset_fighter_2_id,
            ):
                snapshots.append(
                    history.get(fighter_id, _History()).snapshot(
                        fight.source_bout_id, day, fighter_id
                    )
                )
        for identified in daily:
            fight = identified.fight
            for source_id, fighter_id in (
                (fight.source_fighter_1_id, identified.upset_fighter_1_id),
                (fight.source_fighter_2_id, identified.upset_fighter_2_id),
            ):
                history.setdefault(fighter_id, _History()).add(
                    stats_by_key[(fight.source_bout_id, source_id)]
                )

    return tuple(snapshots)
