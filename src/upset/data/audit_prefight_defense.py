"""Independently compare saved defensive histories with earlier source bouts."""

import json
from bisect import bisect_left
from collections import defaultdict
from dataclasses import fields
from datetime import date
from pathlib import Path

from upset.data.export_prefight import read_identified
from upset.data.identify_historical import IdentifiedFight, IdentifiedFightStats
from upset.data.models import Fight, FightStats
from upset.data.prefight_defense import DefensiveHistory

TOTAL_FIELDS = (
    "prior_fight_seconds",
    "prior_sig_strikes_absorbed",
    "prior_opponent_sig_strikes_attempted",
    "prior_takedowns_conceded",
    "prior_opponent_takedowns_attempted",
    "prior_knockdowns_conceded",
    "prior_bouts_with_knockdown_conceded",
    "prior_ko_tko_losses",
    "prior_submission_losses",
)


def _read_defensive_rows(path: Path) -> dict[tuple[str, str], DefensiveHistory]:
    expected = {item.name for item in fields(DefensiveHistory)}
    rows = {}
    with path.open(encoding="utf-8") as source:
        for line in source:
            record = json.loads(line)
            if not isinstance(record, dict) or set(record) != expected:
                raise ValueError("Incorrect defensive export schema.")
            row = DefensiveHistory(**record)
            key = row.source_bout_id, row.upset_fighter_id
            if key in rows:
                raise ValueError(f"Duplicate defensive row: {key}")
            rows[key] = row
    return rows


def audit_prefight_defense(
    fights: list[IdentifiedFight],
    stats: list[IdentifiedFightStats],
    rows: dict[tuple[str, str], DefensiveHistory],
) -> dict:
    """Check every prior count and a deterministic sample of raw source sums.

    Each sampled target is recomputed by scanning its fighter's earlier bouts,
    rather than using the export's date-by-date accumulating state.
    """
    if not fights or not stats or not rows:
        raise ValueError("The source fights, statistics and output are required.")
    by_stat = {}
    for record in stats:
        key = record.stats.source_bout_id, record.stats.source_fighter_id
        if key in by_stat:
            raise ValueError(f"Duplicate fighter statistics: {key}")
        by_stat[key] = record

    # (date, bout, own source stats, opponent source stats, own name)
    by_fighter: dict[str, list[tuple]] = defaultdict(list)
    expected = set()
    used_stats = set()
    seen_bouts = set()
    for identified in fights:
        fight = identified.fight
        if fight.source_bout_id in seen_bouts:
            raise ValueError(f"Duplicate fight: {fight.source_bout_id}")
        seen_bouts.add(fight.source_bout_id)
        date.fromisoformat(fight.event_date)
        ids = fight.source_fighter_1_id, fight.source_fighter_2_id
        keys = (fight.source_bout_id, ids[0]), (fight.source_bout_id, ids[1])
        if any(key not in by_stat for key in keys):
            raise ValueError(f"Missing statistics: {fight.source_bout_id}")
        a, b = (by_stat[key] for key in keys)
        if (
            a.upset_fighter_id != identified.upset_fighter_1_id
            or b.upset_fighter_id != identified.upset_fighter_2_id
        ):
            raise ValueError(f"Source identity mismatch: {fight.source_bout_id}")
        used_stats.update(keys)
        for fighter_id, own, other, own_name in (
            (identified.upset_fighter_1_id, a, b, fight.fighter_1_name),
            (identified.upset_fighter_2_id, b, a, fight.fighter_2_name),
        ):
            key = fight.source_bout_id, fighter_id
            if key in expected:
                raise ValueError(f"Duplicate fighter appearance: {key}")
            expected.add(key)
            by_fighter[fighter_id].append(
                (fight.event_date, fight, own.stats, other.stats, own_name)
            )
    if expected != set(rows) or used_stats != set(by_stat):
        raise ValueError("Source and defensive export coverage differ.")

    dates = {}
    for fighter_id, appearances in by_fighter.items():
        appearances.sort(key=lambda item: (item[0], item[1].source_bout_id))
        dates[fighter_id] = [item[0] for item in appearances]
    for row in rows.values():
        appearances = by_fighter[row.upset_fighter_id]
        if not any(
            item[0] == row.event_date and item[1].source_bout_id == row.source_bout_id
            for item in appearances
        ):
            raise ValueError(f"Fight and defensive date differ: {row.source_bout_id}")
        strictly_earlier = bisect_left(dates[row.upset_fighter_id], row.event_date)
        if row.prior_fights != strictly_earlier:
            raise ValueError(f"Incorrect strictly-earlier count: {row.source_bout_id}")

    ordered = sorted(
        rows.values(), key=lambda row: (
            row.event_date, row.source_bout_id, row.upset_fighter_id
        )
    )
    # Select evenly across history and deliberately include high exposure,
    # first appearances and observed finish/knockdown histories.
    selected = {
        (ordered[index].source_bout_id, ordered[index].upset_fighter_id)
        for index in (
            (len(ordered) - 1) * step // 29 for step in range(30)
        )
    }
    for condition in (
        lambda row: row.prior_fights == 0,
        lambda row: row.prior_fights >= 20,
        lambda row: row.prior_knockdowns_conceded > 0,
        lambda row: row.prior_ko_tko_losses > 0,
        lambda row: row.prior_submission_losses > 0,
    ):
        matching = [row for row in ordered if condition(row)]
        for row in (matching[:2] + matching[-2:]):
            selected.add((row.source_bout_id, row.upset_fighter_id))

    for key in sorted(selected):
        row = rows[key]
        earlier = (
            item for item in by_fighter[row.upset_fighter_id]
            if item[0] < row.event_date
        )
        totals = {name: 0 for name in TOTAL_FIELDS}
        for _, fight, own, opponent, own_name in earlier:
            totals["prior_fight_seconds"] += own.fight_duration_seconds
            totals["prior_sig_strikes_absorbed"] += opponent.sig_strikes_landed
            totals["prior_opponent_sig_strikes_attempted"] += (
                opponent.sig_strikes_attempted
            )
            totals["prior_takedowns_conceded"] += opponent.takedowns_landed
            totals["prior_opponent_takedowns_attempted"] += opponent.takedowns_attempted
            totals["prior_knockdowns_conceded"] += opponent.knockdowns
            totals["prior_bouts_with_knockdown_conceded"] += opponent.knockdowns > 0
            if (
                fight.source_winner_label != "Draw/NC"
                and fight.winner_name is not None
                and fight.winner_name != own_name
            ):
                if fight.result_method == "KO/TKO":
                    totals["prior_ko_tko_losses"] += 1
                elif fight.result_method == "Submission":
                    totals["prior_submission_losses"] += 1
        for name, expected_value in totals.items():
            if getattr(row, name) != expected_value:
                raise ValueError(f"Incorrect {name}: {key}")
    return {
        "all_defensive_rows_count_checked": len(rows),
        "all_rows_match_source_fights_and_dates": True,
        "sampled_rows_all_source_totals_checked": len(selected),
        "sampled_fighters": len({fighter_id for _, fighter_id in selected}),
        "comparison": "matched",
    }


def main() -> None:
    base = Path("data/processed/kaggle_ufc_1994_2026")
    identified = base / "identified"
    fights = read_identified(
        identified / "fights_identified.jsonl", Fight, IdentifiedFight,
        ("upset_fighter_1_id", "upset_fighter_2_id"),
    )
    stats = read_identified(
        identified / "fight_stats_identified.jsonl", FightStats,
        IdentifiedFightStats, ("upset_fighter_id",),
    )
    rows = _read_defensive_rows(base / "prefight" / "defensive_history_v2.jsonl")
    print(json.dumps(audit_prefight_defense(fights, stats, rows), indent=2))


if __name__ == "__main__":
    main()
