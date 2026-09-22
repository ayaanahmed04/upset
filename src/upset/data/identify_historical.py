"""Attach permanent UPSET identities to linked historical records."""

from dataclasses import asdict, dataclass

from upset.data.export_identity_registry import HISTORICAL_PROVIDER, HISTORICAL_SOURCE
from upset.data.identity import FighterRegistry, validate_upset_fighter_id
from upset.data.models import Fight, Fighter, FightStats


@dataclass(frozen=True)
class IdentifiedFighter:
    profile: Fighter
    upset_fighter_id: str

    def __post_init__(self) -> None:
        validate_upset_fighter_id(self.upset_fighter_id)

    def as_record(self) -> dict:
        return {**asdict(self.profile), "upset_fighter_id": self.upset_fighter_id}


@dataclass(frozen=True)
class IdentifiedFight:
    fight: Fight
    upset_fighter_1_id: str
    upset_fighter_2_id: str

    def __post_init__(self) -> None:
        validate_upset_fighter_id(self.upset_fighter_1_id)
        validate_upset_fighter_id(self.upset_fighter_2_id)

    def as_record(self) -> dict:
        return {
            **asdict(self.fight),
            "upset_fighter_1_id": self.upset_fighter_1_id,
            "upset_fighter_2_id": self.upset_fighter_2_id,
        }


@dataclass(frozen=True)
class IdentifiedFightStats:
    stats: FightStats
    upset_fighter_id: str

    def __post_init__(self) -> None:
        validate_upset_fighter_id(self.upset_fighter_id)

    def as_record(self) -> dict:
        return {**asdict(self.stats), "upset_fighter_id": self.upset_fighter_id}


@dataclass(frozen=True)
class IdentifiedHistoricalData:
    profiles: tuple[IdentifiedFighter, ...]
    fights: tuple[IdentifiedFight, ...]
    fight_stats: tuple[IdentifiedFightStats, ...]


def identify_historical_data(
    profiles: list[Fighter],
    fights: list[Fight],
    fight_stats: list[FightStats],
    registry: FighterRegistry,
) -> IdentifiedHistoricalData:
    """Resolve every source ID, and reject incomplete or conflicting inputs."""
    if not profiles or not fights or not fight_stats:
        raise ValueError("Historical profiles, fights, and stats must all be nonempty.")

    # These source IDs were extracted from UFCStats URLs. Cito IDs, including
    # coincidentally equal strings, must never be used to resolve them.
    links = {
        (link.provider, link.provider_fighter_id): link.upset_fighter_id
        for link in registry.provider_links
    }

    def require_id(source: str, source_fighter_id: str | None) -> str:
        if source != HISTORICAL_SOURCE:
            raise ValueError(f"Unexpected historical source: {source!r}")
        if not isinstance(source_fighter_id, str) or not source_fighter_id:
            raise ValueError("Historical fighter ID is missing or invalid.")
        try:
            return links[(HISTORICAL_PROVIDER, source_fighter_id)]
        except KeyError as error:
            raise ValueError(
                f"Missing {HISTORICAL_PROVIDER} registry link: {source_fighter_id}"
            ) from error

    profile_ids: dict[str, str] = {}
    identified_profiles = []
    for profile in profiles:
        source_id = profile.source_fighter_id
        upset_id = require_id(profile.source, source_id)
        if source_id in profile_ids:
            raise ValueError(f"Duplicate historical profile: {source_id}")
        profile_ids[source_id] = upset_id
        identified_profiles.append(IdentifiedFighter(profile, upset_id))

    fights_by_id: dict[str, IdentifiedFight] = {}
    identified_fights = []
    expected_stats: set[tuple[str, str]] = set()
    for fight in fights:
        if fight.source != HISTORICAL_SOURCE:
            raise ValueError(f"Unexpected historical source: {fight.source!r}")
        if not isinstance(fight.source_bout_id, str) or not fight.source_bout_id:
            raise ValueError("Historical fight ID is missing or invalid.")
        if fight.source_bout_id in fights_by_id:
            raise ValueError(f"Duplicate historical fight: {fight.source_bout_id}")

        source_ids = (fight.source_fighter_1_id, fight.source_fighter_2_id)
        upset_ids = tuple(
            require_id(fight.source, source_id) for source_id in source_ids
        )
        for source_id, upset_id in zip(source_ids, upset_ids, strict=True):
            if profile_ids.get(source_id) != upset_id:
                raise ValueError(
                    f"Fight participant has no matching profile: {source_id}"
                )
        if upset_ids[0] == upset_ids[1]:
            raise ValueError(
                f"Fight has the same identity on both sides: {fight.source_bout_id}"
            )

        identified = IdentifiedFight(fight, *upset_ids)
        identified_fights.append(identified)
        fights_by_id[fight.source_bout_id] = identified
        expected_stats.update(
            (fight.source_bout_id, source_id) for source_id in source_ids
        )

    seen_stats: set[tuple[str, str]] = set()
    identified_stats = []
    for stats in fight_stats:
        upset_id = require_id(stats.source, stats.source_fighter_id)
        key = (stats.source_bout_id, stats.source_fighter_id)
        if key in seen_stats:
            raise ValueError(f"Duplicate historical fight statistics: {key}")
        seen_stats.add(key)
        if key not in expected_stats:
            raise ValueError(f"Stats do not match a fight participant: {key}")
        fight = fights_by_id[stats.source_bout_id]
        side = 1 if fight.fight.source_fighter_1_id == stats.source_fighter_id else 2
        if upset_id != getattr(fight, f"upset_fighter_{side}_id"):
            raise ValueError(f"Fight and statistics identities differ: {key}")
        identified_stats.append(IdentifiedFightStats(stats, upset_id))

    if seen_stats != expected_stats:
        missing = sorted(expected_stats - seen_stats)
        raise ValueError(f"Missing fighter-fight statistics: {missing[:5]}")

    return IdentifiedHistoricalData(
        tuple(identified_profiles), tuple(identified_fights), tuple(identified_stats)
    )
