"""Join identified fights to their dated, pre-fight fighter features."""

from dataclasses import asdict, dataclass
from datetime import date
from math import isfinite

from upset.data.export_identity_registry import HISTORICAL_SOURCE
from upset.data.identify_historical import IdentifiedFight
from upset.data.identity import validate_upset_fighter_id
from upset.data.prefight_features import PreFightFeatures

# Only these fields can become model inputs. Fight results, fighter names,
# provider IDs, and today's career totals are never copied into this mapping.
INPUT_FIELDS = (
    "prior_fights",
    "prior_fight_seconds",
    "sig_strikes_landed_per_minute",
    "sig_strikes_accuracy",
    "takedowns_landed_per_15_minutes",
    "takedown_accuracy",
    "knockdowns_per_15_minutes",
    "submission_attempts_per_15_minutes",
    "control_observed_fraction",
)
FRACTION_FIELDS = (
    "sig_strikes_accuracy",
    "takedown_accuracy",
    "control_observed_fraction",
)
AMBIGUOUS_OUTCOME = "ambiguous_draw_or_no_contest"


@dataclass(frozen=True)
class MatchupRow:
    """A fight, its pre-fight inputs, and a separately recorded training label."""

    source_bout_id: str
    event_date: str
    fighter_a_id: str
    fighter_b_id: str
    feature_differences: dict[str, int | float | None]
    target_a_win: int | None
    training_exclusion_reason: str | None
    source_winner_label: str

    def as_record(self) -> dict:
        return asdict(self)


def _require_date(value: str | None, bout_id: str) -> None:
    try:
        if date.fromisoformat(value).isoformat() != value:
            raise ValueError("noncanonical date")
    except (TypeError, ValueError) as error:
        raise ValueError(f"Invalid date for bout {bout_id}: {value!r}") from error


def _validate_feature(row: PreFightFeatures) -> None:
    if not isinstance(row.source_bout_id, str) or not row.source_bout_id:
        raise ValueError("Feature row is missing its source bout ID.")
    _require_date(row.event_date, row.source_bout_id)
    validate_upset_fighter_id(row.upset_fighter_id)
    for field in INPUT_FIELDS:
        value = getattr(row, field)
        if field in ("prior_fights", "prior_fight_seconds"):
            if type(value) is not int or value < 0:
                raise ValueError(f"Invalid {field} for {row.source_bout_id}")
        elif value is not None:
            if type(value) not in (float, int) or not isfinite(value) or value < 0:
                raise ValueError(f"Invalid {field} for {row.source_bout_id}")
            if field in FRACTION_FIELDS and value > 1:
                raise ValueError(f"Invalid {field} for {row.source_bout_id}")
    if row.prior_fights == 0 and any(
        getattr(row, field) is not None for field in INPUT_FIELDS[2:]
    ):
        raise ValueError(f"First-fight rates must be missing: {row.source_bout_id}")
    if row.prior_fights == 0 and row.prior_fight_seconds != 0:
        raise ValueError(f"First-fight duration must be zero: {row.source_bout_id}")
    if row.prior_fights > 0 and row.control_observed_fraction is None:
        raise ValueError(f"Control coverage must be recorded: {row.source_bout_id}")
    if row.prior_fight_seconds == 0 and any(
        getattr(row, field) is not None
        for field in (
            "sig_strikes_landed_per_minute",
            "takedowns_landed_per_15_minutes",
            "knockdowns_per_15_minutes",
            "submission_attempts_per_15_minutes",
        )
    ):
        raise ValueError(f"Zero-duration pace must be missing: {row.source_bout_id}")


def _label(fight: IdentifiedFight, fighter_a_id: str) -> tuple[int | None, str | None]:
    source = fight.fight
    if source.source_winner_label == "Draw/NC":
        if source.winner_name is not None:
            raise ValueError(f"Contradictory Draw/NC winner: {source.source_bout_id}")
        return None, AMBIGUOUS_OUTCOME

    names = (source.fighter_1_name, source.fighter_2_name)
    if (
        not isinstance(source.winner_name, str)
        or source.winner_name != source.source_winner_label
        or names.count(source.winner_name) != 1
    ):
        raise ValueError(f"Unresolved fight winner: {source.source_bout_id}")
    winner_id = (
        fight.upset_fighter_1_id
        if source.winner_name == names[0]
        else fight.upset_fighter_2_id
    )
    return int(winner_id == fighter_a_id), None


def build_matchup_rows(
    fights: list[IdentifiedFight], features: list[PreFightFeatures]
) -> tuple[MatchupRow, ...]:
    """Require a complete, unambiguous pair of prior features for every bout."""
    if not fights or not features:
        raise ValueError("Identified fights and fighter features must be nonempty.")

    by_key: dict[tuple[str, str], PreFightFeatures] = {}
    for feature in features:
        _validate_feature(feature)
        key = feature.source_bout_id, feature.upset_fighter_id
        if key in by_key:
            raise ValueError(f"Duplicate pre-fight feature: {key}")
        by_key[key] = feature

    used: set[tuple[str, str]] = set()
    seen_bouts: set[str] = set()
    matchups = []
    for identified in fights:
        fight = identified.fight
        bout_id = fight.source_bout_id
        if (
            fight.source != HISTORICAL_SOURCE
            or not isinstance(bout_id, str)
            or not bout_id
        ):
            raise ValueError(f"Unexpected historical fight: {bout_id!r}")
        if bout_id in seen_bouts:
            raise ValueError(f"Duplicate historical bout: {bout_id}")
        seen_bouts.add(bout_id)
        _require_date(fight.event_date, bout_id)
        first, second = identified.upset_fighter_1_id, identified.upset_fighter_2_id
        validate_upset_fighter_id(first)
        validate_upset_fighter_id(second)
        if first == second:
            raise ValueError(f"Both participants have the same identity: {bout_id}")

        # UUID order is stable and unrelated to the source row or the winner.
        fighter_a_id, fighter_b_id = sorted((first, second))
        a_key, b_key = (bout_id, fighter_a_id), (bout_id, fighter_b_id)
        if a_key not in by_key or b_key not in by_key:
            raise ValueError(f"Missing participant feature for bout: {bout_id}")
        a, b = by_key[a_key], by_key[b_key]
        if a.event_date != fight.event_date or b.event_date != fight.event_date:
            raise ValueError(f"Fight and feature dates differ: {bout_id}")
        used.update((a_key, b_key))

        # Preserve missingness: a missing rate on either side gives no delta.
        differences = {
            f"{field}_diff": (
                getattr(a, field) - getattr(b, field)
                if getattr(a, field) is not None and getattr(b, field) is not None
                else None
            )
            for field in INPUT_FIELDS
        }
        target, exclusion = _label(identified, fighter_a_id)
        matchups.append(
            MatchupRow(
                source_bout_id=bout_id,
                event_date=fight.event_date,
                fighter_a_id=fighter_a_id,
                fighter_b_id=fighter_b_id,
                feature_differences=differences,
                target_a_win=target,
                training_exclusion_reason=exclusion,
                source_winner_label=fight.source_winner_label,
            )
        )

    if set(by_key) != used:
        raise ValueError(
            f"Unmatched fighter features: {sorted(set(by_key) - used)[:3]}"
        )
    return tuple(sorted(matchups, key=lambda row: (row.event_date, row.source_bout_id)))
