"""Independent v1 rating replay, recomputing every saved numeric field."""

import argparse
import json
from collections import defaultdict
from datetime import date
from math import exp, fsum, isclose, log
from pathlib import Path

from upset.data.export_prefight import read_identified
from upset.data.identify_historical import IdentifiedFight
from upset.data.models import Fight
from upset.data.prefight_ratings import RatingHistory, read_rating_history


def audit_prefight_ratings(
    fights: list[IdentifiedFight],
    rows: dict[tuple[str, str], RatingHistory],
) -> dict:
    """Replay a per-fighter ledger, not the exporter's daily accumulator.

    Constants and expectation arithmetic are deliberately independent of the
    builder. Each row uses only ledger entries with a strictly earlier date.
    """
    if not fights or not rows:
        raise ValueError("Source fights and rating rows are required.")
    ledger: dict[str, list[tuple[str, float, bool]]] = defaultdict(list)
    seen_bouts, checked = set(), set()
    for identified in sorted(
        fights, key=lambda f: (f.fight.event_date, f.fight.source_bout_id)
    ):
        fight = identified.fight
        bout, day = fight.source_bout_id, fight.event_date
        if fight.source != "kaggle_ufc_1994_2026" or not bout or bout in seen_bouts:
            raise ValueError(f"Unexpected or duplicate source fight: {bout}")
        seen_bouts.add(bout)
        if date.fromisoformat(day).isoformat() != day:
            raise ValueError(f"Noncanonical source date: {bout}")
        ids = identified.upset_fighter_1_id, identified.upset_fighter_2_id
        if (
            ids[0] == ids[1]
            or not fight.source_fighter_1_id
            or not fight.source_fighter_2_id
            or fight.source_fighter_1_id == fight.source_fighter_2_id
        ):
            raise ValueError(f"Invalid source participants: {bout}")
        if fight.source_winner_label == "Draw/NC":
            if fight.winner_name is not None:
                raise ValueError(f"Contradictory Draw/NC winner: {bout}")
            winner_id = None
        else:
            names = [fight.fighter_1_name, fight.fighter_2_name]
            if (
                not isinstance(fight.winner_name, str)
                or fight.winner_name != fight.source_winner_label
                or names.count(fight.winner_name) != 1
            ):
                raise ValueError(f"Unresolved source winner: {bout}")
            winner_id = ids[names.index(fight.winner_name)]
        histories = [[item for item in ledger[i] if item[0] < day] for i in ids]
        ratings = [1500.0 + fsum(item[1] for item in prior) for prior in histories]
        # Equivalent natural-exponential form, without the builder helper.
        scaled = (ratings[0] - ratings[1]) * log(10) / 400.0
        small = exp(-abs(scaled))
        probability = 1 / (1 + small) if scaled >= 0 else small / (1 + small)
        for side, fighter_id in enumerate(ids):
            key = bout, fighter_id
            if key not in rows:
                raise ValueError(f"Missing rating row: {key}")
            row = rows[key]
            exact = {
                "source_bout_id": bout,
                "event_date": day,
                "upset_fighter_id": fighter_id,
                "opponent_id": ids[1 - side],
                "prior_fights": len(histories[side]),
                "prior_decisive_fights": sum(item[2] for item in histories[side]),
            }
            for field, expected in exact.items():
                if getattr(row, field) != expected:
                    raise ValueError(f"Incorrect {field}: {key}")
            for field, expected in (
                ("rating", ratings[side]),
                ("opponent_rating", ratings[1 - side]),
                ("elo_probability", probability if side == 0 else 1 - probability),
            ):
                tolerance = 1e-9 if field != "elo_probability" else 1e-12
                if not isclose(
                    getattr(row, field), expected, rel_tol=0, abs_tol=tolerance
                ):
                    raise ValueError(f"Incorrect {field}: {key}")
            checked.add(key)
        change = (
            0.0
            if winner_id is None
            else 32.0 * (int(winner_id == ids[0]) - probability)
        )
        ledger[ids[0]].append((day, change, winner_id is not None))
        ledger[ids[1]].append((day, -change, winner_id is not None))
    if set(rows) != checked:
        raise ValueError("Source and rating history coverage differ.")
    return {
        "all_rating_rows_checked": len(checked),
        "all_numeric_fields_recomputed": True,
        "strictly_earlier_dates_only": True,
        "comparison": "matched",
        "rating_absolute_tolerance": 1e-9,
        "probability_absolute_tolerance": 1e-12,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    base = Path("data/processed/kaggle_ufc_1994_2026")
    parser.add_argument(
        "--fights", type=Path, default=base / "identified/fights_identified.jsonl"
    )
    parser.add_argument(
        "--ratings", type=Path, default=base / "prefight/rating_history_v1.jsonl"
    )
    args = parser.parse_args()
    fights = read_identified(
        args.fights,
        Fight,
        IdentifiedFight,
        ("upset_fighter_1_id", "upset_fighter_2_id"),
    )
    print(
        json.dumps(
            audit_prefight_ratings(fights, read_rating_history(args.ratings)), indent=2
        )
    )


if __name__ == "__main__":
    main()
