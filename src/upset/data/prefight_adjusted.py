"""Earlier-opponent-adjusted striking and takedown histories."""

import json
from collections import defaultdict
from dataclasses import asdict, dataclass, fields
from datetime import date
from itertools import groupby
from math import isfinite
from pathlib import Path

from upset.data.identity import validate_upset_fighter_id
from upset.data.prefight_recent import paired_sources

# The opponent rates were computed *before* the bout in which they are used.
HALF_LIFE_DAYS = 365
PRIOR_SECONDS = 900
SPECS = {
    # Actual landed count, opponent's pre-bout conceded rate, unit seconds.
    "sig_excess_per_minute": ("sig_strikes_landed", "sig_absorbed_per_minute", 60),
    "td_excess_per_15": ("takedowns_landed", "td_conceded_per_15", 900),
}


@dataclass(frozen=True)
class AdjustedHistory:
    source_bout_id: str
    event_date: str
    upset_fighter_id: str
    prior_fights: int
    weighted_excess: dict[str, float]
    weighted_seconds: dict[str, float]
    features: dict[str, float]

    def as_record(self) -> dict:
        return asdict(self)


def build_adjusted_history(fights, stats, recent) -> tuple[AdjustedHistory, ...]:
    observations = paired_sources(fights, stats)
    expected = {(bout, fighter_id) for bout, _, fighter_id, _, _ in observations}
    if not observations or set(recent) != expected:
        raise ValueError("Recent history and source participant keys differ.")
    totals = defaultdict(lambda: dict.fromkeys(SPECS, 0.0))
    exposures = defaultdict(lambda: dict.fromkeys(SPECS, 0.0))
    counts = defaultdict(int)
    last_date = {}
    results = []
    for day, group in groupby(observations, key=lambda record: record[1]):
        daily = list(group)
        today = date.fromisoformat(day)
        daily_prior = {
            fighter_id: counts[fighter_id] for fighter_id in {r[2] for r in daily}
        }
        for fighter_id in sorted({r[2] for r in daily}):
            if fighter_id in last_date:
                factor = 2 ** (-(today - last_date[fighter_id]).days / HALF_LIFE_DAYS)
                totals[fighter_id] = {
                    name: value * factor for name, value in totals[fighter_id].items()
                }
                exposures[fighter_id] = {
                    name: value * factor
                    for name, value in exposures[fighter_id].items()
                }
            last_date[fighter_id] = today
        for bout, _, fighter_id, _, _ in daily:
            results.append(
                AdjustedHistory(
                    source_bout_id=bout,
                    event_date=day,
                    upset_fighter_id=fighter_id,
                    prior_fights=daily_prior[fighter_id],
                    weighted_excess=dict(totals[fighter_id]),
                    weighted_seconds=dict(exposures[fighter_id]),
                    features={
                        name: unit
                        * totals[fighter_id][name]
                        / (exposures[fighter_id][name] + PRIOR_SECONDS)
                        for name, (_, _, unit) in SPECS.items()
                    },
                )
            )
        # Update only after every participant on this date was snapshotted.
        for bout, _, fighter_id, own, _ in daily:
            counts[fighter_id] += 1
            opponent_id = next(
                r[2] for r in daily if r[0] == bout and r[2] != fighter_id
            )
            opponent = recent[bout, opponent_id]
            self_row = recent[bout, fighter_id]
            if (
                opponent.event_date != day
                or opponent.upset_fighter_id != opponent_id
                or self_row.event_date != day
                or opponent.source_bout_id != bout
                or self_row.source_bout_id != bout
                or self_row.upset_fighter_id != fighter_id
                or self_row.prior_fights != daily_prior[fighter_id]
                or opponent.prior_fights != daily_prior[opponent_id]
            ):
                raise ValueError(f"Opponent's pre-bout snapshot differs: {bout}")
            duration = own.fight_duration_seconds
            for name, (landed, opponent_rate, unit) in SPECS.items():
                expectation = opponent.features[opponent_rate]
                if expectation is None:
                    continue
                if not isfinite(expectation) or expectation < 0:
                    raise ValueError(f"Invalid earlier opponent rate: {bout}")
                totals[fighter_id][name] += (
                    getattr(own, landed) - expectation * duration / unit
                )
                exposures[fighter_id][name] += duration
    return tuple(results)


def validate_adjusted_row(row: AdjustedHistory) -> None:
    validate_upset_fighter_id(row.upset_fighter_id)
    if not isinstance(row.source_bout_id, str) or not row.source_bout_id:
        raise ValueError("Missing opponent-adjusted bout ID.")
    if date.fromisoformat(row.event_date).isoformat() != row.event_date:
        raise ValueError("Invalid opponent-adjusted date.")
    if type(row.prior_fights) is not int or row.prior_fights < 0:
        raise ValueError("Invalid opponent-adjusted prior count.")
    for mapping, nonnegative in (
        (row.weighted_excess, False),
        (row.weighted_seconds, True),
        (row.features, False),
    ):
        if not isinstance(mapping, dict) or set(mapping) != set(SPECS):
            raise ValueError("Unexpected opponent-adjusted fields.")
        for value in mapping.values():
            if type(value) not in (float, int) or not isfinite(value):
                raise ValueError("Invalid opponent-adjusted numeric value.")
            if nonnegative and value < 0:
                raise ValueError("Negative adjusted exposure.")


def read_adjusted_history(path: Path) -> dict[tuple[str, str], AdjustedHistory]:
    result = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        record = json.loads(line)
        if not isinstance(record, dict) or set(record) != {
            field.name for field in fields(AdjustedHistory)
        }:
            raise ValueError("Unexpected opponent-adjusted schema.")
        row = AdjustedHistory(**record)
        validate_adjusted_row(row)
        key = row.source_bout_id, row.upset_fighter_id
        if key in result:
            raise ValueError("Duplicate opponent-adjusted history.")
        result[key] = row
    if not result:
        raise ValueError("Opponent-adjusted history is empty.")
    return result
