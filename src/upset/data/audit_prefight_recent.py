"""Independently recompute every recent feature from earlier source bouts."""

import argparse
import json
from collections import defaultdict
from datetime import date
from itertools import groupby
from math import exp, fsum, isclose, log
from pathlib import Path

from upset.data.export_prefight import read_identified
from upset.data.identify_historical import IdentifiedFight, IdentifiedFightStats
from upset.data.models import Fight, FightStats
from upset.data.prefight_defense import build_defensive_history
from upset.data.prefight_recent import read_recent_history, validate_recent_row


def read_recent_sources(fights_path, stats_path):
    return (
        read_identified(
            fights_path,
            Fight,
            IdentifiedFight,
            ("upset_fighter_1_id", "upset_fighter_2_id"),
        ),
        read_identified(
            stats_path, FightStats, IdentifiedFightStats, ("upset_fighter_id",)
        ),
    )


def audit_prefight_recent(fights, stats, rows) -> dict:
    """Use direct age weights over source ledgers, not the builder's recurrence.

    The numeric specification is intentionally repeated here so a builder
    change cannot silently change the expected audit result with it.
    """
    build_defensive_history(fights, stats)  # established pair/source validation
    by_source = {
        (s.stats.source_bout_id, s.stats.source_fighter_id): s.stats for s in stats
    }
    # Independent extraction, keyed by source participant rather than saved row.
    events = []
    for identified in sorted(
        fights, key=lambda f: (f.fight.event_date, f.fight.source_bout_id)
    ):
        fight = identified.fight
        participants = (
            (fight.source_fighter_1_id, identified.upset_fighter_1_id),
            (fight.source_fighter_2_id, identified.upset_fighter_2_id),
        )
        for side, (source_id, fighter_id) in enumerate(participants):
            own = by_source[fight.source_bout_id, source_id]
            other = by_source[fight.source_bout_id, participants[1 - side][0]]
            for value in (own.submission_attempts, own.control_seconds):
                if value is not None and (type(value) is not int or value < 0):
                    raise ValueError("Invalid source submission/control count.")
            if own.submission_attempts is None:
                raise ValueError("Missing source submission count.")
            observed = (
                own.control_seconds is not None and other.control_seconds is not None
            )
            numbers = {
                "appearances": 1,
                "seconds": own.fight_duration_seconds,
                "sig_landed": own.sig_strikes_landed,
                "sig_absorbed": other.sig_strikes_landed,
                "sig_attempted": own.sig_strikes_attempted,
                "sig_attempted_against": other.sig_strikes_attempted,
                "td_landed": own.takedowns_landed,
                "td_conceded": other.takedowns_landed,
                "td_attempted": own.takedowns_attempted,
                "td_attempted_against": other.takedowns_attempted,
                "kd": own.knockdowns,
                "kd_conceded": other.knockdowns,
                "sub_attempts": own.submission_attempts,
                "control_margin_seconds": own.control_seconds - other.control_seconds
                if observed
                else 0,
                "control_seconds": own.fight_duration_seconds if observed else 0,
            }
            events.append((fight.event_date, fight.source_bout_id, fighter_id, numbers))
    ledger, population = defaultdict(list), defaultdict(int)
    checked = set()
    # Same-date population priors are held fixed as well as personal history.
    for day, batch in groupby(events, key=lambda row: row[0]):
        daily = list(batch)
        for _, bout, fighter_id, numbers in daily:
            key = bout, fighter_id
            if key not in rows:
                raise ValueError(f"Missing recent-history row: {key}")
            row = rows[key]
            validate_recent_row(row)
            earlier = [(d, v) for d, v in ledger[fighter_id] if d < day]
            if (
                row.event_date != day
                or row.source_bout_id != bout
                or row.upset_fighter_id != fighter_id
                or row.prior_fights != len(earlier)
            ):
                raise ValueError(f"Recent identity/date/count mismatch: {key}")
            target_date = date.fromisoformat(day)
            weighted = {
                field: fsum(
                    v[field]
                    * exp(-log(2) * (target_date - date.fromisoformat(d)).days / 365)
                    for d, v in earlier
                )
                for field in numbers
            }

            # numerator, denominator, units, prior exposure; use failed attempts
            # explicitly for defense instead of the builder's complement flag.
            def measures(values):
                return {
                    "sig_landed_per_minute": (
                        values["sig_landed"],
                        values["seconds"],
                        60,
                        900,
                    ),
                    "sig_absorbed_per_minute": (
                        values["sig_absorbed"],
                        values["seconds"],
                        60,
                        900,
                    ),
                    "sig_accuracy": (
                        values["sig_landed"],
                        values["sig_attempted"],
                        1,
                        50,
                    ),
                    "sig_defense": (
                        values["sig_attempted_against"] - values["sig_absorbed"],
                        values["sig_attempted_against"],
                        1,
                        50,
                    ),
                    "td_landed_per_15": (
                        values["td_landed"],
                        values["seconds"],
                        900,
                        900,
                    ),
                    "td_conceded_per_15": (
                        values["td_conceded"],
                        values["seconds"],
                        900,
                        900,
                    ),
                    "td_accuracy": (values["td_landed"], values["td_attempted"], 1, 5),
                    "td_defense": (
                        values["td_attempted_against"] - values["td_conceded"],
                        values["td_attempted_against"],
                        1,
                        5,
                    ),
                    "kd_per_15": (values["kd"], values["seconds"], 900, 900),
                    "kd_conceded_per_15": (
                        values["kd_conceded"],
                        values["seconds"],
                        900,
                        900,
                    ),
                    "sub_attempts_per_15": (
                        values["sub_attempts"],
                        values["seconds"],
                        900,
                        900,
                    ),
                    "control_margin": (
                        values["control_margin_seconds"],
                        values["control_seconds"],
                        1,
                        900,
                    ),
                }

            priors = {
                name: n * scale / d if d else None
                for name, (n, d, scale, _) in measures(population).items()
            }
            features = {
                name: (n * scale + strength * priors[name]) / (d + strength)
                if priors[name] is not None
                else None
                for name, (n, d, scale, strength) in measures(weighted).items()
            }
            for field, expected in (
                ("weighted_totals", weighted),
                ("population_rates", priors),
                ("features", features),
            ):
                actual = getattr(row, field)
                for name, value in expected.items():
                    matches = (
                        actual[name] is None
                        if value is None
                        else (
                            actual[name] is not None
                            and isclose(
                                actual[name], value, rel_tol=1e-12, abs_tol=1e-8
                            )
                        )
                    )
                    if not matches:
                        raise ValueError(f"Incorrect recent {field}/{name}: {key}")
            checked.add(key)
        for _, _, fighter_id, numbers in daily:
            ledger[fighter_id].append((day, numbers))
            for name, value in numbers.items():
                population[name] += value
    if set(rows) != checked:
        raise ValueError("Source and recent-history coverage differ.")
    return {
        "all_recent_rows_checked": len(checked),
        "all_numeric_fields_recomputed": True,
        "strictly_earlier_dates_only": True,
        "population_priors_strictly_earlier": True,
        "comparison": "matched",
        "absolute_tolerance": 1e-8,
        "relative_tolerance": 1e-12,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    base = Path("data/processed/kaggle_ufc_1994_2026")
    parser.add_argument(
        "--fights", type=Path, default=base / "identified/fights_identified.jsonl"
    )
    parser.add_argument(
        "--stats", type=Path, default=base / "identified/fight_stats_identified.jsonl"
    )
    parser.add_argument(
        "--recent", type=Path, default=base / "prefight/recent_history_v1.jsonl"
    )
    args = parser.parse_args()
    fights, stats = read_recent_sources(args.fights, args.stats)
    print(
        json.dumps(
            audit_prefight_recent(fights, stats, read_recent_history(args.recent)),
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
