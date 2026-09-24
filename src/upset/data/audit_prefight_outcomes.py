"""Recompute every saved outcome history from earlier identified fights."""

import json
from collections import defaultdict
from dataclasses import asdict
from datetime import date
from pathlib import Path

from upset.data.export_prefight import read_identified
from upset.data.identify_historical import IdentifiedFight
from upset.data.models import Fight
from upset.data.prefight_outcomes import OutcomeHistory, read_outcome_history


def audit_prefight_outcomes(
    fights: list[IdentifiedFight],
    rows: dict[tuple[str, str], OutcomeHistory],
) -> dict:
    """Scan source histories per row, with no exporter accumulator reused."""
    if not fights or not rows:
        raise ValueError("Source fights and outcome rows are required.")
    appearances: dict[str, list[tuple[date, str, bool | None]]] = defaultdict(list)
    targets: dict[tuple[str, str], date] = {}
    seen_bouts = set()
    for identified in fights:
        fight = identified.fight
        bout = fight.source_bout_id
        if bout in seen_bouts or not bout:
            raise ValueError(f"Duplicate or missing source fight: {bout}")
        seen_bouts.add(bout)
        day = date.fromisoformat(fight.event_date)
        if day.isoformat() != fight.event_date:
            raise ValueError(f"Noncanonical source date: {bout}")
        if fight.source_winner_label == "Draw/NC":
            if fight.winner_name is not None:
                raise ValueError(f"Invalid ambiguous winner: {bout}")
            winner = None
        else:
            names = fight.fighter_1_name, fight.fighter_2_name
            if (fight.winner_name != fight.source_winner_label
                    or names.count(fight.winner_name) != 1):
                raise ValueError(f"Invalid decisive winner: {bout}")
            winner = names.index(fight.winner_name)
        ids = identified.upset_fighter_1_id, identified.upset_fighter_2_id
        if ids[0] == ids[1]:
            raise ValueError(f"Identical fighter IDs: {bout}")
        for side, fighter_id in enumerate(ids):
            key = bout, fighter_id
            if key in targets:
                raise ValueError(f"Duplicate source appearance: {key}")
            targets[key] = day
            appearances[fighter_id].append((
                day, bout, None if winner is None else winner == side
            ))
    if set(targets) != set(rows):
        raise ValueError("Source and outcome history coverage differ.")

    for key, day in targets.items():
        row = rows[key]
        if row.event_date != day.isoformat():
            raise ValueError(f"Incorrect outcome history date: {key}")
        previous = [(seen_day, result)
                    for seen_day, _, result in appearances[key[1]]
                    if seen_day < day]
        wins = sum(result is True for _, result in previous)
        losses = sum(result is False for _, result in previous)
        recent = [(seen_day, result) for seen_day, result in previous
                  if 0 < (day - seen_day).days <= 365]
        decisive = wins + losses
        expected = {
            "prior_fights": len(previous),
            "prior_decisive_fights": decisive,
            "prior_wins": wins,
            "prior_losses": losses,
            "prior_win_rate": wins / decisive if decisive else None,
            "prior_365_day_wins": sum(r is True for _, r in recent),
            "prior_365_day_losses": sum(r is False for _, r in recent),
            "days_since_last_bout": (
                (day - max(d for d, _ in previous)).days if previous else None
            ),
        }
        saved = asdict(row)
        for name, value in expected.items():
            if saved[name] != value:
                raise ValueError(f"Incorrect {name}: {key}")
    return {
        "all_outcome_rows_checked": len(rows),
        "all_rows_match_earlier_source_outcomes_and_dates": True,
        "comparison": "matched",
    }


def main() -> None:
    base = Path("data/processed/kaggle_ufc_1994_2026")
    source = base / "identified" / "fights_identified.jsonl"
    output = base / "prefight" / "outcome_history_v1.jsonl"
    fights = read_identified(
        source, Fight, IdentifiedFight,
        ("upset_fighter_1_id", "upset_fighter_2_id"),
    )
    print(json.dumps(audit_prefight_outcomes(
        fights, read_outcome_history(output)
    ), indent=2))


if __name__ == "__main__":
    main()
