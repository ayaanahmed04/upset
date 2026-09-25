"""Rebuild matchup inputs at a date using completed bouts strictly before it."""

from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from itertools import groupby
from math import fsum, log1p

from upset.data.identify_historical import IdentifiedFight, IdentifiedFightStats
from upset.data.identity import validate_upset_fighter_id
from upset.data.prefight import _History as OffensiveLedger
from upset.data.prefight_defense import FINISH_LOSS_METHODS
from upset.data.prefight_defense import _History as DefensiveLedger
from upset.data.prefight_features import build_prefight_features
from upset.data.prefight_ratings import INITIAL_RATING, K_FACTOR, elo_probability
from upset.data.prefight_recent import (
    HALF_LIFE_DAYS,
    RATE_SPECS,
    TOTAL_FIELDS,
    _observation,
    _rates,
)
from upset.modeling.defense_ablation import DEFENSE_FIELDS
from upset.modeling.frozen_replay import COLUMNS
from upset.modeling.recent_form import EXPOSURES


@dataclass(frozen=True)
class ScheduledMatchup:
    source_bout_id: str
    event_date: str
    fighter_a_id: str
    fighter_b_id: str


def _completed(fights, stats):
    by_key = {}
    for record in stats:
        row = record.stats
        key = (row.source, row.source_bout_id, row.source_fighter_id)
        if key in by_key:
            raise ValueError(f"Duplicate completed-fight statistics: {key}")
        by_key[key] = record
    consumed = set()
    seen = set()
    pair_dates = set()
    paired = []
    for item in fights:
        fight = item.fight
        key = (fight.source, fight.source_bout_id)
        if (key in seen or not all(isinstance(x, str) and x for x in key)
                or item.upset_fighter_1_id == item.upset_fighter_2_id):
            raise ValueError(f"Duplicate or invalid completed fight: {key}")
        seen.add(key)
        _date(fight.event_date)
        ids = fight.source_fighter_1_id, fight.source_fighter_2_id
        keys = tuple((fight.source, fight.source_bout_id, x) for x in ids)
        if ids[0] == ids[1] or any(k not in by_key for k in keys):
            raise ValueError(f"Missing completed-fight participant stats: {key}")
        first, second = (by_key[k] for k in keys)
        if (first.upset_fighter_id != item.upset_fighter_1_id
                or second.upset_fighter_id != item.upset_fighter_2_id
                or first.stats.fight_duration_seconds != second.stats.fight_duration_seconds):
            raise ValueError(f"Conflicting completed-fight pair: {key}")
        if fight.source_winner_label == "Draw/NC":
            if fight.winner_name is not None:
                raise ValueError(f"Draw/NC has named winner: {key}")
            winner = None
        else:
            names = (fight.fighter_1_name, fight.fighter_2_name)
            if fight.winner_name != fight.source_winner_label or names.count(
                fight.winner_name
            ) != 1:
                raise ValueError(f"Unresolved completed winner: {key}")
            winner = names.index(fight.winner_name)
        pair_date = (fight.event_date, *sorted((item.upset_fighter_1_id,
                                               item.upset_fighter_2_id)))
        if pair_date in pair_dates:
            raise ValueError(f"Cross-provider or same-date duplicate bout: {key}")
        pair_dates.add(pair_date)
        consumed.update(keys)
        paired.append((item, first, second, winner))
    if consumed != set(by_key) or not paired:
        raise ValueError("Unexpected statistics or empty completed history.")
    return sorted(paired, key=lambda x: (x[0].fight.event_date,
                                        x[0].fight.source, x[0].fight.source_bout_id))


def _date(value: str) -> date:
    try:
        parsed = date.fromisoformat(value)
        if parsed.isoformat() != value:
            raise ValueError("Noncanonical date")
    except (TypeError, ValueError) as error:
        raise ValueError(f"Invalid scheduled/completed date: {value!r}") from error
    return parsed


def build_asof_features(
    fights: list[IdentifiedFight], stats: list[IdentifiedFightStats],
    matchups: list[ScheduledMatchup],
) -> dict[str, dict[str, float | int | None]]:
    """Snapshot all same-date requests before updating any result on that day.

    Completed fights can come from multiple linked providers; their bout IDs
    are always identified by (provider, ID), with a cross-source pair audit.
    """
    completed = _completed(fights, stats)
    requests = defaultdict(list)
    observed = set()
    for row in matchups:
        if not isinstance(row.source_bout_id, str) or not row.source_bout_id or (
            row.source_bout_id in observed
        ):
            raise ValueError("Duplicate or empty scheduled bout ID.")
        observed.add(row.source_bout_id)
        _date(row.event_date)
        for fighter_id in (row.fighter_a_id, row.fighter_b_id):
            validate_upset_fighter_id(fighter_id)
        if row.fighter_a_id >= row.fighter_b_id:
            raise ValueError("Scheduled fighter IDs must be canonical UUID order.")
        requests[row.event_date].append(row)
    if not requests:
        raise ValueError("At least one dated matchup is needed.")

    offense = defaultdict(OffensiveLedger)
    defense = defaultdict(DefensiveLedger)
    ratings = defaultdict(lambda: INITIAL_RATING)
    recent = defaultdict(lambda: dict.fromkeys(TOTAL_FIELDS, 0.0))
    recent_date = {}
    population = dict.fromkeys(TOTAL_FIELDS, 0)
    predictions = {}
    completed_by_day = {day: list(group) for day, group in groupby(
        completed, key=lambda item: item[0].fight.event_date
    )}
    for day in sorted(set(completed_by_day) | set(requests)):
        current_date = _date(day)

        def snapshot(fighter_id, bout_id, *, day=day, current_date=current_date):
            original = offense[fighter_id].snapshot(bout_id, day, fighter_id)
            base = build_prefight_features([original])[0]
            defended = defense[fighter_id].snapshot(bout_id, day, fighter_id)
            totals = recent[fighter_id]
            if fighter_id in recent_date:
                lag = (current_date - recent_date[fighter_id]).days
                totals = {name: value * 2 ** (-lag / HALF_LIFE_DAYS)
                          for name, value in totals.items()}
            smooth = _rates(totals, population)[1]
            if offense[fighter_id].fights != defense[fighter_id].fights:
                raise ValueError("Offensive and defensive bout counts differ.")
            return base, defended, totals, smooth, ratings[fighter_id]

        for row in requests[day]:
            a = snapshot(row.fighter_a_id, row.source_bout_id)
            b = snapshot(row.fighter_b_id, row.source_bout_id)
            record = {}
            for name in (
                "prior_fights", "prior_fight_seconds", "sig_strikes_landed_per_minute",
                "sig_strikes_accuracy", "takedowns_landed_per_15_minutes",
                "takedown_accuracy", "knockdowns_per_15_minutes",
                "submission_attempts_per_15_minutes", "control_observed_fraction",
            ):
                x, y = getattr(a[0], name), getattr(b[0], name)
                record[name + "_diff"] = x - y if x is not None and y is not None else None
            for name in DEFENSE_FIELDS:
                x, y = getattr(a[1], name), getattr(b[1], name)
                record[name + "_diff"] = x - y if x is not None and y is not None else None
            record["elo_rating_diff"] = a[4] - b[4]
            for name in RATE_SPECS:
                x, y = a[3][name], b[3][name]
                record["recent_" + name + "_diff"] = (
                    x - y if x is not None and y is not None else None
                )
            for field in EXPOSURES:
                x, y = log1p(a[2][field]), log1p(b[2][field])
                record[f"recent_log_{field}_diff"] = x - y
                record[f"recent_log_{field}_sum"] = x + y
            if set(record) != set(COLUMNS):
                raise ValueError("Generated feature schema differs from frozen model.")
            predictions[row.source_bout_id] = record

        changes = defaultdict(list)
        for item, first, second, winner in completed_by_day.get(day, []):
            ids = item.upset_fighter_1_id, item.upset_fighter_2_id
            p = elo_probability(ratings[ids[0]], ratings[ids[1]])
            if winner is not None:
                delta = K_FACTOR * (int(winner == 0) - p)
                changes[ids[0]].append(delta)
                changes[ids[1]].append(-delta)
            finish = FINISH_LOSS_METHODS.get(item.fight.result_method)
            for side, own, other in ((0, first, second), (1, second, first)):
                fighter_id = ids[side]
                # These counts affect later dates; never a request from today.
                offense[fighter_id].add(own)
                defense[fighter_id].add(
                    own, other,
                    finish if winner is not None and winner != side else None,
                )
                if fighter_id in recent_date:
                    lag = (current_date - recent_date[fighter_id]).days
                    factor = 2 ** (-lag / HALF_LIFE_DAYS)
                    recent[fighter_id] = {
                        name: value * factor for name, value in recent[fighter_id].items()
                    }
                recent_date[fighter_id] = current_date
                observation = _observation(own.stats, other.stats)
                for name, value in observation.items():
                    recent[fighter_id][name] += value
                    population[name] += value
        for fighter_id, updates in changes.items():
            ratings[fighter_id] += fsum(updates)
    return predictions
