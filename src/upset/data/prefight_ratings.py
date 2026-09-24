"""Fixed v1 Elo snapshots from strictly earlier observed UFC dates."""

import json
from collections import defaultdict
from dataclasses import asdict, dataclass, fields
from datetime import date
from itertools import groupby
from math import fsum, isclose, isfinite
from pathlib import Path

from upset.data.export_identity_registry import HISTORICAL_SOURCE
from upset.data.identify_historical import IdentifiedFight
from upset.data.identity import validate_upset_fighter_id

INITIAL_RATING = 1500.0
RATING_SCALE = 400.0
K_FACTOR = 32.0


@dataclass(frozen=True)
class RatingHistory:
    source_bout_id: str
    event_date: str
    upset_fighter_id: str
    opponent_id: str
    prior_fights: int
    prior_decisive_fights: int
    rating: float
    opponent_rating: float
    elo_probability: float

    def as_record(self) -> dict:
        return asdict(self)


def elo_probability(rating: float, opponent_rating: float) -> float:
    """Stable base-10 Elo expectation; ratings are not win percentages."""
    difference = rating - opponent_rating
    small = 10.0 ** (-abs(difference) / RATING_SCALE)
    return 1 / (1 + small) if difference >= 0 else small / (1 + small)


def build_rating_history(fights: list[IdentifiedFight]) -> tuple[RatingHistory, ...]:
    if not fights:
        raise ValueError("Identified fights must be nonempty.")
    seen, validated = set(), []
    for identified in fights:
        fight = identified.fight
        bout = fight.source_bout_id
        if (
            fight.source != HISTORICAL_SOURCE
            or not isinstance(bout, str)
            or not bout
            or bout in seen
        ):
            raise ValueError(f"Unexpected or duplicate fight: {bout}")
        seen.add(bout)
        try:
            if date.fromisoformat(fight.event_date).isoformat() != fight.event_date:
                raise ValueError("Noncanonical date")
        except (TypeError, ValueError) as error:
            raise ValueError(f"Invalid event date: {bout}") from error
        ids = identified.upset_fighter_1_id, identified.upset_fighter_2_id
        source_ids = fight.source_fighter_1_id, fight.source_fighter_2_id
        for fighter_id in ids:
            validate_upset_fighter_id(fighter_id)
        if (
            ids[0] == ids[1]
            or source_ids[0] == source_ids[1]
            or any(not isinstance(i, str) or not i for i in source_ids)
        ):
            raise ValueError(f"Invalid participants: {bout}")
        names = fight.fighter_1_name, fight.fighter_2_name
        if fight.source_winner_label == "Draw/NC":
            if fight.winner_name is not None:
                raise ValueError(f"Draw/NC has a named winner: {bout}")
            winner = None
        elif (
            not isinstance(fight.winner_name, str)
            or fight.winner_name != fight.source_winner_label
            or names.count(fight.winner_name) != 1
        ):
            raise ValueError(f"Unresolved decisive winner: {bout}")
        else:
            winner = names.index(fight.winner_name)
        validated.append((identified, ids, winner))

    ratings: dict[str, float] = {}
    appearances, decisive = defaultdict(int), defaultdict(int)
    rows = []
    ordered = sorted(
        validated, key=lambda x: (x[0].fight.event_date, x[0].fight.source_bout_id)
    )
    for day, dated in groupby(ordered, key=lambda x: x[0].fight.event_date):
        changes: dict[str, list[float]] = defaultdict(list)
        counts, decisions = defaultdict(int), defaultdict(int)
        for identified, ids, winner in dated:
            # Ratings/counts remain frozen for this entire calendar date.
            a, b = (ratings.get(i, INITIAL_RATING) for i in ids)
            probability = elo_probability(a, b)
            for side, fighter_id in enumerate(ids):
                rows.append(
                    RatingHistory(
                        source_bout_id=identified.fight.source_bout_id,
                        event_date=day,
                        upset_fighter_id=fighter_id,
                        opponent_id=ids[1 - side],
                        prior_fights=appearances[fighter_id],
                        prior_decisive_fights=decisive[fighter_id],
                        rating=(a, b)[side],
                        opponent_rating=(b, a)[side],
                        elo_probability=probability if side == 0 else 1 - probability,
                    )
                )
                counts[fighter_id] += 1
                decisions[fighter_id] += int(winner is not None)
            if winner is not None:
                change = K_FACTOR * (int(winner == 0) - probability)
                changes[ids[0]].append(change)
                changes[ids[1]].append(-change)
        # Sum all same-day changes calculated from the pre-date snapshots.
        for fighter_id, count in counts.items():
            ratings[fighter_id] = ratings.get(fighter_id, INITIAL_RATING) + fsum(
                changes[fighter_id]
            )
            appearances[fighter_id] += count
            decisive[fighter_id] += decisions[fighter_id]
    return tuple(rows)


def read_rating_history(path: Path) -> dict[tuple[str, str], RatingHistory]:
    expected = {field.name for field in fields(RatingHistory)}
    rows = {}
    with path.open(encoding="utf-8") as source:
        for number, line in enumerate(source, 1):
            try:
                raw = json.loads(line)
                if not isinstance(raw, dict) or set(raw) != expected:
                    raise ValueError("Rating fields do not match schema")
                row = RatingHistory(**raw)
                for fighter_id in (row.upset_fighter_id, row.opponent_id):
                    validate_upset_fighter_id(fighter_id)
                if (
                    not isinstance(row.source_bout_id, str)
                    or not row.source_bout_id
                    or row.upset_fighter_id == row.opponent_id
                ):
                    raise ValueError("Invalid rating identity")
                if date.fromisoformat(row.event_date).isoformat() != row.event_date:
                    raise ValueError("Noncanonical rating date")
                if (
                    any(
                        type(v) is not int or v < 0
                        for v in (row.prior_fights, row.prior_decisive_fights)
                    )
                    or row.prior_decisive_fights > row.prior_fights
                ):
                    raise ValueError("Invalid rating counts")
                if any(
                    type(v) not in (int, float) or not isfinite(v)
                    for v in (row.rating, row.opponent_rating, row.elo_probability)
                ):
                    raise ValueError("Invalid rating number")
                if abs(row.rating - INITIAL_RATING) > (
                    K_FACTOR * row.prior_decisive_fights + 1e-9
                ):
                    raise ValueError("Rating exceeds its possible prior updates")
                if not 0 <= row.elo_probability <= 1 or not isclose(
                    row.elo_probability,
                    elo_probability(row.rating, row.opponent_rating),
                    rel_tol=0,
                    abs_tol=1e-12,
                ):
                    raise ValueError("Inconsistent Elo probability")
                key = row.source_bout_id, row.upset_fighter_id
                if key in rows:
                    raise ValueError("Duplicate rating row")
                rows[key] = row
            except (TypeError, ValueError) as error:
                raise ValueError(
                    f"Invalid rating history at line {number}: {error}"
                ) from error
    if not rows:
        raise ValueError("Rating history is empty.")
    return rows
