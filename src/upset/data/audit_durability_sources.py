"""Audit historical knockdowns and finish-method labels before feature design."""

import json
from collections import Counter
from pathlib import Path

from upset.data.export_identity_registry import HISTORICAL_SOURCE
from upset.data.export_prefight import read_identified
from upset.data.identify_historical import IdentifiedFight, IdentifiedFightStats
from upset.data.models import Fight, FightStats


def audit_durability_sources(
    fights: list[IdentifiedFight], stats: list[IdentifiedFightStats]
) -> dict:
    """Require paired records; report observed values without guessing KO labels."""
    if not fights or not stats:
        raise ValueError("Identified fights and statistics must be nonempty.")

    by_key: dict[tuple[str, str], IdentifiedFightStats] = {}
    for record in stats:
        source = record.stats
        key = source.source_bout_id, source.source_fighter_id
        if source.source != HISTORICAL_SOURCE or key in by_key:
            raise ValueError(f"Unexpected or duplicate fight statistics: {key}")
        if type(source.knockdowns) is not int or source.knockdowns < 0:
            raise ValueError(f"Invalid knockdown count: {key}")
        by_key[key] = record

    used = set()
    bouts = set()
    methods = Counter()
    knockdowns = 0
    appearances_with_opponent_knockdown = 0
    conceded_by_fighter = Counter()
    ambiguous = 0
    for identified in fights:
        fight = identified.fight
        bout_id = fight.source_bout_id
        if fight.source != HISTORICAL_SOURCE or not bout_id or bout_id in bouts:
            raise ValueError(f"Unexpected or duplicate fight: {bout_id}")
        bouts.add(bout_id)
        first_id, second_id = fight.source_fighter_1_id, fight.source_fighter_2_id
        if not first_id or not second_id or first_id == second_id:
            raise ValueError(f"Invalid participants: {bout_id}")
        keys = (bout_id, first_id), (bout_id, second_id)
        if any(key not in by_key for key in keys):
            raise ValueError(f"Missing fight statistics: {bout_id}")
        first, second = (by_key[key] for key in keys)
        if (
            first.upset_fighter_id != identified.upset_fighter_1_id
            or second.upset_fighter_id != identified.upset_fighter_2_id
        ):
            raise ValueError(f"Fighter identities differ: {bout_id}")
        used.update(keys)

        # A fighter's opponent's recorded KD count is their own conceded KD
        # count. The two numbers must never be assigned to the same fighter.
        knockdowns += first.stats.knockdowns + second.stats.knockdowns
        appearances_with_opponent_knockdown += (first.stats.knockdowns > 0) + (
            second.stats.knockdowns > 0
        )
        conceded_by_fighter[identified.upset_fighter_1_id] += second.stats.knockdowns
        conceded_by_fighter[identified.upset_fighter_2_id] += first.stats.knockdowns
        methods[fight.result_method or "<missing>"] += 1
        ambiguous += fight.source_winner_label == "Draw/NC"

    if used != set(by_key):
        raise ValueError("Unexpected fight statistics outside the identified fights.")
    return {
        "fights": len(fights),
        "fighter_fight_rows": len(stats),
        "combined_draw_nc": ambiguous,
        "recorded_knockdowns": knockdowns,
        "fighter_fight_rows_with_opponent_recorded_knockdown": (
            appearances_with_opponent_knockdown
        ),
        "fighters_with_recorded_knockdowns_conceded": sum(
            value > 0 for value in conceded_by_fighter.values()
        ),
        "max_recorded_knockdowns_conceded_by_one_fighter": max(
            conceded_by_fighter.values(), default=0
        ),
        "method_labels": dict(sorted(methods.items())),
    }


def main() -> None:
    base = Path("data/processed/kaggle_ufc_1994_2026/identified")
    fights = read_identified(
        base / "fights_identified.jsonl",
        Fight,
        IdentifiedFight,
        ("upset_fighter_1_id", "upset_fighter_2_id"),
    )
    stats = read_identified(
        base / "fight_stats_identified.jsonl",
        FightStats,
        IdentifiedFightStats,
        ("upset_fighter_id",),
    )
    print(json.dumps(audit_durability_sources(fights, stats), indent=2))


if __name__ == "__main__":
    main()
