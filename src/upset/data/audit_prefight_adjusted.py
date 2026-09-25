"""Independently recompute adjusted histories from earlier bout observations."""

from collections import defaultdict
from datetime import date
from math import exp, fsum, isclose, log

from upset.data.prefight_adjusted import validate_adjusted_row
from upset.data.prefight_recent import paired_sources


def audit_prefight_adjusted(fights, stats, recent, rows) -> dict:
    """Replay direct past-bout weights; do not use the incremental builder."""
    observations = paired_sources(fights, stats)
    by_bout = {
        (bout, fighter_id): (day, own) for bout, day, fighter_id, own, _ in observations
    }
    pair_ids = defaultdict(list)
    for bout, _, fighter_id, _, _ in observations:
        pair_ids[bout].append(fighter_id)
    expected = set(by_bout)
    if set(rows) != expected or set(recent) != expected:
        raise ValueError("Adjusted/recent/source participant coverage differs.")
    prior = defaultdict(list)
    checked = set()
    for bout, day, fighter_id, own, opponent in observations:
        key = bout, fighter_id
        row = rows[key]
        validate_adjusted_row(row)
        if (
            row.source_bout_id != bout
            or row.event_date != day
            or row.upset_fighter_id != fighter_id
        ):
            raise ValueError(f"Incorrect adjusted identity/date: {key}")
        # Rebuild against the independent ledger of earlier source bouts, not
        # a rolling total or the candidate's saved values.
        earlier = [entry for entry in prior[fighter_id] if entry[0] < day]
        if row.prior_fights != len(earlier):
            raise ValueError(f"Incorrect adjusted prior count: {key}")
        excess, seconds, values = {}, {}, {}
        for family, field, opponent_field, unit in (
            (
                "sig_excess_per_minute",
                "sig_strikes_landed",
                "sig_absorbed_per_minute",
                60,
            ),
            ("td_excess_per_15", "takedowns_landed", "td_conceded_per_15", 900),
        ):
            usable = []
            for past_day, past_bout, past_opponent in earlier:
                prior_opponent = recent[past_bout, past_opponent]
                observed_day, source = by_bout[past_bout, fighter_id]
                if (
                    prior_opponent.event_date != past_day
                    or observed_day != past_day
                    or prior_opponent.source_bout_id != past_bout
                    or prior_opponent.upset_fighter_id != past_opponent
                ):
                    raise ValueError(f"Earlier opponent snapshot differs: {past_bout}")
                expected_rate = prior_opponent.features[opponent_field]
                if expected_rate is None:
                    continue
                weight = exp(
                    -log(2)
                    * (date.fromisoformat(day) - date.fromisoformat(past_day)).days
                    / 365
                )
                duration = source.fight_duration_seconds
                usable.append(
                    (
                        weight
                        * (getattr(source, field) - expected_rate * duration / unit),
                        weight * duration,
                    )
                )
            excess[family] = fsum(part[0] for part in usable)
            seconds[family] = fsum(part[1] for part in usable)
            values[family] = unit * excess[family] / (seconds[family] + 900)
        for field, expected_values in (
            ("weighted_excess", excess),
            ("weighted_seconds", seconds),
            ("features", values),
        ):
            for family, wanted in expected_values.items():
                if not isclose(
                    getattr(row, field)[family], wanted, rel_tol=1e-12, abs_tol=1e-8
                ):
                    raise ValueError(f"Incorrect adjusted {field}/{family}: {key}")
        checked.add(key)
        other_id = next(
            opposite for opposite in pair_ids[bout] if opposite != fighter_id
        )
        prior[fighter_id].append((day, bout, other_id))
    return {
        "all_adjusted_rows_checked": len(checked),
        "all_numeric_fields_recomputed": True,
        "strictly_earlier_dates_only": True,
        "comparison": "matched",
        "absolute_tolerance": 1e-8,
        "relative_tolerance": 1e-12,
    }
