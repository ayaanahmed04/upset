"""Defensive statistics observed strictly before each historical event date."""

from dataclasses import asdict, dataclass
from datetime import date
from itertools import groupby

from upset.data.export_identity_registry import HISTORICAL_SOURCE
from upset.data.identify_historical import IdentifiedFight, IdentifiedFightStats
from upset.data.identity import validate_upset_fighter_id

# An outcome label is used only when the winner is unambiguous. Other
# methods are preserved, never silently interpreted as a KO or submission.
FINISH_LOSS_METHODS = {"KO/TKO": "ko_tko", "Submission": "submission"}


@dataclass(frozen=True)
class DefensiveHistory:
    source_bout_id: str
    event_date: str
    upset_fighter_id: str
    prior_fights: int
    prior_fight_seconds: int
    prior_sig_strikes_absorbed: int
    prior_opponent_sig_strikes_attempted: int
    prior_takedowns_conceded: int
    prior_opponent_takedowns_attempted: int
    prior_knockdowns_conceded: int
    prior_bouts_with_knockdown_conceded: int
    prior_ko_tko_losses: int
    prior_submission_losses: int
    sig_strikes_absorbed_per_minute: float | None
    sig_strike_defense: float | None
    takedowns_conceded_per_15_minutes: float | None
    takedown_defense: float | None
    knockdowns_conceded_per_15_minutes: float | None

    def as_record(self) -> dict:
        return asdict(self)


@dataclass
class _History:
    fights: int = 0
    seconds: int = 0
    sig_absorbed: int = 0
    sig_attempted_against: int = 0
    takedowns_conceded: int = 0
    takedowns_attempted_against: int = 0
    knockdowns_conceded: int = 0
    bouts_with_knockdown: int = 0
    ko_tko_losses: int = 0
    submission_losses: int = 0

    def snapshot(self, bout_id: str, day: str, fighter_id: str) -> DefensiveHistory:
        def rate(count: int, seconds: int, multiplier: int) -> float | None:
            return count * multiplier / seconds if seconds else None

        def defense(landed: int, attempts: int) -> float | None:
            return 1 - landed / attempts if attempts else None

        return DefensiveHistory(
            source_bout_id=bout_id,
            event_date=day,
            upset_fighter_id=fighter_id,
            prior_fights=self.fights,
            prior_fight_seconds=self.seconds,
            prior_sig_strikes_absorbed=self.sig_absorbed,
            prior_opponent_sig_strikes_attempted=self.sig_attempted_against,
            prior_takedowns_conceded=self.takedowns_conceded,
            prior_opponent_takedowns_attempted=self.takedowns_attempted_against,
            prior_knockdowns_conceded=self.knockdowns_conceded,
            prior_bouts_with_knockdown_conceded=self.bouts_with_knockdown,
            prior_ko_tko_losses=self.ko_tko_losses,
            prior_submission_losses=self.submission_losses,
            sig_strikes_absorbed_per_minute=rate(self.sig_absorbed, self.seconds, 60),
            sig_strike_defense=defense(self.sig_absorbed, self.sig_attempted_against),
            takedowns_conceded_per_15_minutes=rate(
                self.takedowns_conceded, self.seconds, 900
            ),
            takedown_defense=defense(
                self.takedowns_conceded, self.takedowns_attempted_against
            ),
            knockdowns_conceded_per_15_minutes=rate(
                self.knockdowns_conceded, self.seconds, 900
            ),
        )

    def add(self, own: IdentifiedFightStats, opponent: IdentifiedFightStats,
            finish_loss: str | None) -> None:
        other = opponent.stats
        self.fights += 1
        self.seconds += own.stats.fight_duration_seconds
        self.sig_absorbed += other.sig_strikes_landed
        self.sig_attempted_against += other.sig_strikes_attempted
        self.takedowns_conceded += other.takedowns_landed
        self.takedowns_attempted_against += other.takedowns_attempted
        self.knockdowns_conceded += other.knockdowns
        self.bouts_with_knockdown += other.knockdowns > 0
        self.ko_tko_losses += finish_loss == "ko_tko"
        self.submission_losses += finish_loss == "submission"


def _validate_stats(record: IdentifiedFightStats) -> None:
    stats = record.stats
    validate_upset_fighter_id(record.upset_fighter_id)
    if stats.source != HISTORICAL_SOURCE or not stats.source_fighter_id:
        raise ValueError("Unexpected source or missing fighter ID in statistics.")
    for name in (
        "fight_duration_seconds", "sig_strikes_landed", "sig_strikes_attempted",
        "takedowns_landed", "takedowns_attempted", "knockdowns",
    ):
        value = getattr(stats, name)
        if type(value) is not int or value < 0:
            raise ValueError(f"Invalid {name}: {stats.source_bout_id}")
    if (stats.sig_strikes_landed > stats.sig_strikes_attempted
            or stats.takedowns_landed > stats.takedowns_attempted):
        raise ValueError(f"Landed exceeds attempts: {stats.source_bout_id}")


def build_defensive_history(
    fights: list[IdentifiedFight], fight_stats: list[IdentifiedFightStats]
) -> tuple[DefensiveHistory, ...]:
    """Pair opponents first, snapshot a whole date, then update all histories."""
    if not fights or not fight_stats:
        raise ValueError("Historical fights and statistics must be nonempty.")
    by_key: dict[tuple[str, str], IdentifiedFightStats] = {}
    for record in fight_stats:
        _validate_stats(record)
        key = record.stats.source_bout_id, record.stats.source_fighter_id
        if key in by_key:
            raise ValueError(f"Duplicate statistics: {key}")
        by_key[key] = record

    seen: set[str] = set()
    used: set[tuple[str, str]] = set()
    validated: list[tuple[IdentifiedFight, IdentifiedFightStats,
                          IdentifiedFightStats, str | None]] = []
    for identified in fights:
        fight = identified.fight
        bout_id = fight.source_bout_id
        if fight.source != HISTORICAL_SOURCE or not bout_id or bout_id in seen:
            raise ValueError(f"Unexpected or duplicate fight: {bout_id}")
        seen.add(bout_id)
        if not isinstance(fight.event_date, str):
            raise TypeError(f"Missing or invalid event date type: {bout_id}")
        try:
            if date.fromisoformat(fight.event_date).isoformat() != fight.event_date:
                raise ValueError("Noncanonical date")
        except ValueError as error:
            raise ValueError(f"Invalid event date: {bout_id}") from error
        ids = (fight.source_fighter_1_id, fight.source_fighter_2_id)
        if not all(ids) or ids[0] == ids[1]:
            raise ValueError(f"Invalid participants: {bout_id}")
        keys = (bout_id, ids[0]), (bout_id, ids[1])
        if any(key not in by_key for key in keys):
            raise ValueError(f"Missing paired statistics: {bout_id}")
        a, b = (by_key[key] for key in keys)
        if (a.upset_fighter_id != identified.upset_fighter_1_id
                or b.upset_fighter_id != identified.upset_fighter_2_id
                or a.upset_fighter_id == b.upset_fighter_id
                or a.stats.fight_duration_seconds != b.stats.fight_duration_seconds):
            raise ValueError(f"Participant identity or duration mismatch: {bout_id}")
        used.update(keys)

        if fight.source_winner_label == "Draw/NC":
            if fight.winner_name is not None:
                raise ValueError(f"Draw/NC has named winner: {bout_id}")
            winner_side = None
        else:
            names = (fight.fighter_1_name, fight.fighter_2_name)
            if (fight.winner_name != fight.source_winner_label
                    or names.count(fight.winner_name) != 1):
                raise ValueError(f"Unresolved decisive winner: {bout_id}")
            winner_side = names.index(fight.winner_name)
        finish_loss = (
            FINISH_LOSS_METHODS.get(fight.result_method)
            if winner_side is not None else None
        )
        validated.append((identified, a, b, finish_loss))

    if used != set(by_key):
        raise ValueError("Unexpected statistics outside historical fights.")
    histories: dict[str, _History] = {}
    snapshots = []
    ordered = sorted(
        validated, key=lambda item: (item[0].fight.event_date,
                                     item[0].fight.source_bout_id)
    )
    for day, group in groupby(ordered, key=lambda item: item[0].fight.event_date):
        daily = list(group)
        for identified, _, _, _ in daily:
            for fighter_id in (
                identified.upset_fighter_1_id, identified.upset_fighter_2_id
            ):
                snapshots.append(
                    histories.get(fighter_id, _History()).snapshot(
                        identified.fight.source_bout_id, day, fighter_id
                    )
                )
        for identified, a, b, finish_loss in daily:
            winner = identified.fight.winner_name
            for own, other, fighter_name in (
                (a, b, identified.fight.fighter_1_name),
                (b, a, identified.fight.fighter_2_name),
            ):
                histories.setdefault(own.upset_fighter_id, _History()).add(
                    own, other,
                    finish_loss if winner is not None and winner != fighter_name
                    else None,
                )
    return tuple(snapshots)
