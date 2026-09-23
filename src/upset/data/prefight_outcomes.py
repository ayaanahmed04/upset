"""Dated UFC outcome and activity histories for identified fighters."""

import json
from dataclasses import asdict, dataclass, fields
from datetime import date
from itertools import groupby
from math import isclose, isfinite
from pathlib import Path

from upset.data.export_identity_registry import HISTORICAL_SOURCE
from upset.data.identify_historical import IdentifiedFight
from upset.data.identity import validate_upset_fighter_id

RECENT_DAYS = 365


@dataclass(frozen=True)
class OutcomeHistory:
    source_bout_id: str
    event_date: str
    upset_fighter_id: str
    prior_fights: int
    prior_decisive_fights: int
    prior_wins: int
    prior_losses: int
    prior_win_rate: float | None
    prior_365_day_wins: int
    prior_365_day_losses: int
    days_since_last_bout: int | None

    def as_record(self) -> dict:
        return asdict(self)


def _winner_side(identified: IdentifiedFight) -> int | None:
    fight = identified.fight
    if fight.source_winner_label == "Draw/NC":
        if fight.winner_name is not None:
            raise ValueError(f"Draw/NC has named winner: {fight.source_bout_id}")
        return None
    names = fight.fighter_1_name, fight.fighter_2_name
    if (fight.winner_name != fight.source_winner_label
            or names.count(fight.winner_name) != 1):
        raise ValueError(f"Unresolved decisive winner: {fight.source_bout_id}")
    return names.index(fight.winner_name)


def build_outcome_history(
    fights: list[IdentifiedFight],
) -> tuple[OutcomeHistory, ...]:
    """Snapshot each whole date before adding that date's fight outcomes."""
    if not fights:
        raise ValueError("Identified fights must be nonempty.")
    seen = set()
    validated = []
    for identified in fights:
        fight = identified.fight
        bout = fight.source_bout_id
        if fight.source != HISTORICAL_SOURCE or not bout or bout in seen:
            raise ValueError(f"Unexpected or duplicate fight: {bout}")
        seen.add(bout)
        try:
            day = date.fromisoformat(fight.event_date)
            if day.isoformat() != fight.event_date:
                raise ValueError("Noncanonical date")
        except (TypeError, ValueError) as error:
            raise ValueError(f"Invalid event date: {bout}") from error
        ids = identified.upset_fighter_1_id, identified.upset_fighter_2_id
        for fighter_id in ids:
            validate_upset_fighter_id(fighter_id)
        if (ids[0] == ids[1] or not fight.source_fighter_1_id
                or not fight.source_fighter_2_id
                or fight.source_fighter_1_id == fight.source_fighter_2_id):
            raise ValueError(f"Invalid participants: {bout}")
        validated.append((day, identified, _winner_side(identified)))

    appearances: dict[str, list[tuple[date, bool | None]]] = {}
    rows = []
    ordered = sorted(validated, key=lambda x: (x[0], x[1].fight.source_bout_id))
    for day, group in groupby(ordered, key=lambda x: x[0]):
        daily = list(group)
        for _, identified, _ in daily:
            for fighter_id in (
                identified.upset_fighter_1_id,
                identified.upset_fighter_2_id,
            ):
                prior = appearances.get(fighter_id, [])
                wins = sum(result is True for _, result in prior)
                losses = sum(result is False for _, result in prior)
                recent = [(previous, result) for previous, result in prior
                          if 0 < (day - previous).days <= RECENT_DAYS]
                decisive = wins + losses
                rows.append(OutcomeHistory(
                    source_bout_id=identified.fight.source_bout_id,
                    event_date=day.isoformat(),
                    upset_fighter_id=fighter_id,
                    prior_fights=len(prior),
                    prior_decisive_fights=decisive,
                    prior_wins=wins,
                    prior_losses=losses,
                    prior_win_rate=wins / decisive if decisive else None,
                    prior_365_day_wins=sum(r is True for _, r in recent),
                    prior_365_day_losses=sum(r is False for _, r in recent),
                    days_since_last_bout=(day - prior[-1][0]).days if prior else None,
                ))
        for _, identified, winner in daily:
            for index, fighter_id in enumerate((
                identified.upset_fighter_1_id,
                identified.upset_fighter_2_id,
            )):
                appearances.setdefault(fighter_id, []).append((
                    day, None if winner is None else winner == index
                ))
    return tuple(rows)


def read_outcome_history(path: Path) -> dict[tuple[str, str], OutcomeHistory]:
    """Validate the saved schema, counts, rates, and unique fighter-bout keys."""
    expected = {item.name for item in fields(OutcomeHistory)}
    rows = {}
    with path.open(encoding="utf-8") as source:
        for number, line in enumerate(source, 1):
            try:
                raw = json.loads(line)
                if not isinstance(raw, dict) or set(raw) != expected:
                    raise ValueError("Outcome fields do not match schema")
                row = OutcomeHistory(**raw)
                validate_upset_fighter_id(row.upset_fighter_id)
                if not isinstance(row.source_bout_id, str) or not row.source_bout_id:
                    raise ValueError("Missing bout ID")
                if date.fromisoformat(row.event_date).isoformat() != row.event_date:
                    raise ValueError("Noncanonical event date")
                counts = (
                    "prior_fights", "prior_decisive_fights", "prior_wins",
                    "prior_losses", "prior_365_day_wins", "prior_365_day_losses",
                )
                if any(type(getattr(row, name)) is not int
                       or getattr(row, name) < 0 for name in counts):
                    raise ValueError("Invalid outcome count")
                if (row.prior_decisive_fights != row.prior_wins + row.prior_losses
                        or row.prior_decisive_fights > row.prior_fights
                        or row.prior_365_day_wins > row.prior_wins
                        or row.prior_365_day_losses > row.prior_losses):
                    raise ValueError("Inconsistent outcome counts")
                if row.prior_decisive_fights:
                    if (type(row.prior_win_rate) not in (int, float)
                            or not isfinite(row.prior_win_rate)
                            or not isclose(row.prior_win_rate,
                                           row.prior_wins / row.prior_decisive_fights,
                                           rel_tol=1e-12, abs_tol=1e-12)):
                        raise ValueError("Inconsistent prior win rate")
                elif row.prior_win_rate is not None:
                    raise ValueError("Undefined prior win rate")
                if (row.prior_fights == 0 and row.days_since_last_bout is not None
                        or row.prior_fights > 0 and (
                            type(row.days_since_last_bout) is not int
                            or row.days_since_last_bout <= 0)):
                    raise ValueError("Invalid last bout interval")
                key = row.source_bout_id, row.upset_fighter_id
                if key in rows:
                    raise ValueError("Duplicate outcome row")
                rows[key] = row
            except (TypeError, ValueError) as error:
                raise ValueError(
                    f"Invalid outcome history at line {number}: {error}"
                ) from error
    if not rows:
        raise ValueError("Outcome history is empty.")
    return rows
