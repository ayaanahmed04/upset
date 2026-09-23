"""Compare cached Cito round rows to its separate fighter fight totals."""

import argparse
import json
from dataclasses import fields
from pathlib import Path

from upset.data.collect_cito_rounds import validate_bout_ids
from upset.data.export_cito_rounds import (
    read_cito_round_bout,
    validate_cito_counts,
)
from upset.data.models import RoundStats
from upset.data.normalization import normalize_cito_round
from upset.data.probe_cito_totals import _read_cache

_NON_STAT_FIELDS = {
    "source", "source_round_stat_id", "source_bout_id", "source_fighter_slug",
    "fighter_name", "round_number", "source_last_synced_at",
}
STAT_FIELDS = tuple(field.name for field in fields(RoundStats)
                    if field.name not in _NON_STAT_FIELDS)


def _normalize_stats(raw: dict, bout_id: str, *, total: bool) -> RoundStats:
    """Parse the same Cito stat fields for rounds and fight totals."""
    if total and "round" in raw:
        raise ValueError("Bout-total row unexpectedly contains a round number.")
    try:
        # The canonical parser requires a round. One is used here only to
        # parse bout-total counts; this temporary row is never exported.
        row = normalize_cito_round({**raw, "round": 1} if total else raw)
        validate_cito_counts(row)
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError(f"Invalid Cito stat row: {type(error).__name__}") from error
    if (
        row.source_bout_id != bout_id
        or not isinstance(row.source_fighter_slug, str)
        or not row.source_fighter_slug.strip()
        or not isinstance(row.fighter_name, str)
        or not row.fighter_name.strip()
    ):
        raise ValueError("Cito stat row has a missing or mismatched identity.")
    return row


def _by_fighter_round(rows: list[RoundStats]) -> dict[tuple[str, int], RoundStats]:
    indexed = {}
    for row in rows:
        key = (row.source_fighter_slug, row.round_number)
        if key in indexed:
            raise ValueError("Duplicate fighter and round in Cito stats.")
        indexed[key] = row
    return indexed


def audit_bout(
    bout_id: str, rounds_dir: Path, totals_dir: Path
) -> dict:
    """Require exact round agreement and all numeric fight totals to add up."""
    validate_bout_ids([bout_id])
    rounds = read_cito_round_bout(rounds_dir / f"{bout_id}.json")
    payload = _read_cache(totals_dir / f"{bout_id}.json", bout_id)
    data = payload["data"]
    if not isinstance(data, dict) or set(data) != {
        "availability", "boutStats", "roundStats"
    }:
        raise ValueError("Unexpected Cito totals data shape.")
    bout_stats = data["boutStats"]
    embedded = data["roundStats"]
    if (
        not isinstance(bout_stats, list)
        or len(bout_stats) != 2
        or not isinstance(embedded, list)
        or len(embedded) != len(rounds)
        or any(not isinstance(row, dict) for row in bout_stats + embedded)
    ):
        raise ValueError("Cito totals lack two fighters or complete round rows.")

    embedded_rows = [
        _normalize_stats(row, bout_id, total=False) for row in embedded
    ]
    saved_by_round = _by_fighter_round(rounds)
    embedded_by_round = _by_fighter_round(embedded_rows)
    if set(saved_by_round) != set(embedded_by_round):
        raise ValueError("Round endpoint and totals endpoint have different rounds.")

    discrepancies = []
    for (fighter, number), saved in sorted(saved_by_round.items()):
        comparison = embedded_by_round[(fighter, number)]
        if saved.fighter_name != comparison.fighter_name:
            raise ValueError("Fighter names differ between Cito endpoints.")
        for field in STAT_FIELDS:
            if getattr(saved, field) != getattr(comparison, field):
                discrepancies.append(
                    f"{fighter} round {number} {field}: "
                    f"round endpoint {getattr(saved, field)}, "
                    f"totals endpoint {getattr(comparison, field)}"
                )

    totals = [_normalize_stats(row, bout_id, total=True) for row in bout_stats]
    by_fighter = {row.source_fighter_slug: row for row in totals}
    if len(by_fighter) != 2 or set(by_fighter) != {
        row.source_fighter_slug for row in rounds
    }:
        raise ValueError("Fight totals do not identify both round participants.")
    for fighter, total in sorted(by_fighter.items()):
        participants = [
            row for row in rounds if row.source_fighter_slug == fighter
        ]
        if any(row.fighter_name != total.fighter_name for row in participants):
            raise ValueError("Fight-total and round fighter names differ.")
        for field in STAT_FIELDS:
            calculated = sum(getattr(row, field) for row in participants)
            actual = getattr(total, field)
            if calculated != actual:
                discrepancies.append(
                    f"{fighter} {field}: round sum {calculated}, "
                    f"fight total {actual}"
                )
    if discrepancies:
        examples = "; ".join(discrepancies[:5])
        raise ValueError(
            f"Cito round-to-total mismatches ({len(discrepancies)}): {examples}"
        )
    return {
        "bout_id": bout_id,
        "fighters": sorted(by_fighter),
        "round_rows": len(rounds),
        "fight_total_rows": len(totals),
        "fields_per_fighter_compared": len(STAT_FIELDS),
        "comparison": "matched",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bout-id", required=True)
    parser.add_argument("--rounds-dir", type=Path, default=Path("data/raw/cito_rounds"))
    parser.add_argument("--totals-dir", type=Path, default=Path("data/raw/cito_totals"))
    args = parser.parse_args()
    try:
        report = audit_bout(args.bout_id, args.rounds_dir, args.totals_dir)
    except ValueError as error:
        raise SystemExit(str(error)) from None
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
