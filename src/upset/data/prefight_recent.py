"""Dated, exposure-aware recent performance; no target-day observations."""

import json
from collections import defaultdict
from dataclasses import asdict, dataclass, fields
from datetime import date
from itertools import groupby
from math import isfinite
from pathlib import Path

from upset.data.identity import validate_upset_fighter_id
from upset.data.prefight_defense import build_defensive_history

HALF_LIFE_DAYS = 365
# numerator, denominator, unit multiplier, equivalent prior exposure, complement
RATE_SPECS = {
    "sig_landed_per_minute": ("sig_landed", "seconds", 60, 900, False),
    "sig_absorbed_per_minute": ("sig_absorbed", "seconds", 60, 900, False),
    "sig_accuracy": ("sig_landed", "sig_attempted", 1, 50, False),
    "sig_defense": ("sig_absorbed", "sig_attempted_against", 1, 50, True),
    "td_landed_per_15": ("td_landed", "seconds", 900, 900, False),
    "td_conceded_per_15": ("td_conceded", "seconds", 900, 900, False),
    "td_accuracy": ("td_landed", "td_attempted", 1, 5, False),
    "td_defense": ("td_conceded", "td_attempted_against", 1, 5, True),
    "kd_per_15": ("kd", "seconds", 900, 900, False),
    "kd_conceded_per_15": ("kd_conceded", "seconds", 900, 900, False),
    "sub_attempts_per_15": ("sub_attempts", "seconds", 900, 900, False),
    "control_margin": ("control_margin_seconds", "control_seconds", 1, 900, False),
}
TOTAL_FIELDS = (
    "appearances",
    "seconds",
    "sig_landed",
    "sig_absorbed",
    "sig_attempted",
    "sig_attempted_against",
    "td_landed",
    "td_conceded",
    "td_attempted",
    "td_attempted_against",
    "kd",
    "kd_conceded",
    "sub_attempts",
    "control_margin_seconds",
    "control_seconds",
)


@dataclass(frozen=True)
class RecentHistory:
    source_bout_id: str
    event_date: str
    upset_fighter_id: str
    prior_fights: int
    weighted_totals: dict[str, float]
    population_rates: dict[str, float | None]
    features: dict[str, float | None]

    def as_record(self) -> dict:
        return asdict(self)


def paired_sources(fights, stats) -> list:
    """Reuse established source/identity/pair validation, then pair raw rows."""
    build_defensive_history(fights, stats)
    indexed = {(s.stats.source_bout_id, s.upset_fighter_id): s.stats for s in stats}
    for row in stats:
        for name in ("submission_attempts", "control_seconds"):
            value = getattr(row.stats, name)
            if value is None and name == "control_seconds":
                continue
            if type(value) is not int or value < 0:
                raise ValueError(f"Invalid {name}: {row.stats.source_bout_id}")
    result = []
    for identified in sorted(
        fights, key=lambda f: (f.fight.event_date, f.fight.source_bout_id)
    ):
        bout, day = identified.fight.source_bout_id, identified.fight.event_date
        ids = identified.upset_fighter_1_id, identified.upset_fighter_2_id
        for side in (0, 1):
            result.append(
                (
                    bout,
                    day,
                    ids[side],
                    indexed[bout, ids[side]],
                    indexed[bout, ids[1 - side]],
                )
            )
    return result


def _observation(own, opponent) -> dict[str, int]:
    control_known = (
        own.control_seconds is not None and opponent.control_seconds is not None
    )
    return {
        "appearances": 1,
        "seconds": own.fight_duration_seconds,
        "sig_landed": own.sig_strikes_landed,
        "sig_absorbed": opponent.sig_strikes_landed,
        "sig_attempted": own.sig_strikes_attempted,
        "sig_attempted_against": opponent.sig_strikes_attempted,
        "td_landed": own.takedowns_landed,
        "td_conceded": opponent.takedowns_landed,
        "td_attempted": own.takedowns_attempted,
        "td_attempted_against": opponent.takedowns_attempted,
        "kd": own.knockdowns,
        "kd_conceded": opponent.knockdowns,
        "sub_attempts": own.submission_attempts,
        "control_margin_seconds": (
            own.control_seconds - opponent.control_seconds if control_known else 0
        ),
        "control_seconds": own.fight_duration_seconds if control_known else 0,
    }


def _rates(totals, population):
    priors, smoothed = {}, {}
    for name, (num, den, scale, strength, complement) in RATE_SPECS.items():
        pop_num = population[den] - population[num] if complement else population[num]
        priors[name] = pop_num * scale / population[den] if population[den] else None
        own_num = totals[den] - totals[num] if complement else totals[num]
        smoothed[name] = (
            (own_num * scale + strength * priors[name]) / (totals[den] + strength)
            if priors[name] is not None
            else None
        )
    return priors, smoothed


def build_recent_history(fights, stats) -> tuple[RecentHistory, ...]:
    observations = paired_sources(fights, stats)
    totals = defaultdict(lambda: dict.fromkeys(TOTAL_FIELDS, 0.0))
    counts, last_date = defaultdict(int), {}
    population = dict.fromkeys(TOTAL_FIELDS, 0)
    rows = []
    for day, batch in groupby(observations, key=lambda row: row[1]):
        daily = list(batch)
        # Decay once per participant/date. Snapshot everyone before any update.
        for fighter_id in sorted({r[2] for r in daily}):
            if fighter_id in last_date:
                days = (date.fromisoformat(day) - last_date[fighter_id]).days
                factor = 2 ** (-days / HALF_LIFE_DAYS)
                totals[fighter_id] = {
                    k: v * factor for k, v in totals[fighter_id].items()
                }
            last_date[fighter_id] = date.fromisoformat(day)
        for bout, _, fighter_id, _, _ in daily:
            prior, features = _rates(totals[fighter_id], population)
            rows.append(
                RecentHistory(
                    bout,
                    day,
                    fighter_id,
                    counts[fighter_id],
                    dict(totals[fighter_id]),
                    prior,
                    features,
                )
            )
        for _, _, fighter_id, own, opponent in daily:
            counts[fighter_id] += 1
            for name, value in _observation(own, opponent).items():
                totals[fighter_id][name] += value
                population[name] += value
    return tuple(rows)


def validate_recent_row(row: RecentHistory) -> None:
    validate_upset_fighter_id(row.upset_fighter_id)
    if not isinstance(row.source_bout_id, str) or not row.source_bout_id:
        raise ValueError("Missing recent-history bout ID.")
    if date.fromisoformat(row.event_date).isoformat() != row.event_date:
        raise ValueError("Invalid recent-history date.")
    if type(row.prior_fights) is not int or row.prior_fights < 0:
        raise ValueError("Invalid recent-history count.")
    for mapping, expected, nullable in (
        (row.weighted_totals, TOTAL_FIELDS, False),
        (row.population_rates, RATE_SPECS, True),
        (row.features, RATE_SPECS, True),
    ):
        if not isinstance(mapping, dict) or set(mapping) != set(expected):
            raise ValueError("Unexpected recent-history fields.")
        for name, value in mapping.items():
            if nullable and value is None:
                continue
            if type(value) not in (int, float) or not isfinite(value):
                raise ValueError(f"Invalid recent numeric value: {name}")
            if name not in ("control_margin", "control_margin_seconds") and value < 0:
                raise ValueError(f"Negative recent numeric value: {name}")


def read_recent_history(path: Path) -> dict[tuple[str, str], RecentHistory]:
    result = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        record = json.loads(line)
        if not isinstance(record, dict) or set(record) != {
            f.name for f in fields(RecentHistory)
        }:
            raise ValueError("Unexpected recent-history schema.")
        row = RecentHistory(**record)
        validate_recent_row(row)
        key = row.source_bout_id, row.upset_fighter_id
        if key in result:
            raise ValueError(f"Duplicate recent-history row: {key}")
        result[key] = row
    if not result:
        raise ValueError("Recent history is empty.")
    return result
