"""Verify cached Cito rounds and export provider-specific canonical rows."""

import json
from dataclasses import asdict, fields
from pathlib import Path
from tempfile import TemporaryDirectory

from upset.data.collect_cito_rounds import (
    round_row_count,
    validate_bout_ids,
    validate_row_bout_ids,
)
from upset.data.models import RoundStats
from upset.data.normalization import normalize_cito_round

DEFAULT_INPUT = Path("data/raw/cito_rounds")
DEFAULT_OUTPUT = Path("data/processed/cito/round_stats.jsonl")

_PAIRS = (
    ("sig_strikes_landed", "sig_strikes_attempted"),
    ("total_strikes_landed", "total_strikes_attempted"),
    ("takedowns_landed", "takedowns_attempted"),
    ("head_landed", "head_attempted"),
    ("body_landed", "body_attempted"),
    ("leg_landed", "leg_attempted"),
    ("distance_landed", "distance_attempted"),
    ("clinch_landed", "clinch_attempted"),
    ("ground_landed", "ground_attempted"),
)


def validate_cito_counts(row: RoundStats) -> None:
    for field in fields(row):
        value = getattr(row, field.name)
        if field.name in {
            "source", "source_round_stat_id", "source_bout_id",
            "source_fighter_slug", "fighter_name", "source_last_synced_at",
        }:
            continue
        if type(value) is not int or value < 0:
            raise ValueError(f"Invalid nonnegative integer: {field.name}")
    if row.round_number == 0:
        raise ValueError("Round numbers must start at one.")
    for landed, attempted in _PAIRS:
        if getattr(row, landed) > getattr(row, attempted):
            raise ValueError(f"Landed exceeds attempted: {landed}")
    if (
        row.sig_strikes_landed > row.total_strikes_landed
        or row.sig_strikes_attempted > row.total_strikes_attempted
    ):
        raise ValueError("Significant strikes exceed total strikes.")
    for label, parts in (
        ("target", ("head", "body", "leg")),
        ("position", ("distance", "clinch", "ground")),
    ):
        for suffix in ("landed", "attempted"):
            if sum(getattr(row, f"{part}_{suffix}") for part in parts) != getattr(
                row, f"sig_strikes_{suffix}"
            ):
                raise ValueError(
                    f"{label} breakdown differs from sig strikes: {suffix}"
                )


def read_cito_round_bout(path: Path) -> list[RoundStats]:
    bout_id = validate_bout_ids([path.stem])[0]
    try:
        saved = json.loads(path.read_text(encoding="utf-8"))
        if (
            not isinstance(saved, dict)
            or saved.get("source") != "cito"
            or saved.get("source_bout_id") != bout_id
        ):
            raise ValueError("Cached source or bout ID does not match the filename.")
        payload = saved.get("response")
        round_row_count(payload)
        validate_row_bout_ids(payload, bout_id)
        data = payload["data"]
        if isinstance(data, list):
            raw_rows = data
        else:
            raw_rows = next(
                data[key]
                for key in ("rounds", "rows", "items", "results", "stats")
                if isinstance(data.get(key), list)
            )
        rows = []
        for index, raw in enumerate(raw_rows, start=1):
            try:
                row = normalize_cito_round(raw)
                if (
                    row.source_bout_id != bout_id
                    or not all(
                        isinstance(value, str) and value.strip()
                        for value in (
                            row.source_round_stat_id, row.source_fighter_slug,
                            row.fighter_name,
                        )
                    )
                    or (
                        row.source_last_synced_at is not None
                        and not isinstance(row.source_last_synced_at, str)
                    )
                ):
                    raise ValueError("Round identifiers or name are invalid.")
                validate_cito_counts(row)
            except (KeyError, TypeError, ValueError) as error:
                raise ValueError(
                    f"Invalid row {index}: {type(error).__name__}"
                ) from error
            rows.append(row)
    except (OSError, UnicodeError, TypeError, ValueError) as error:
        raise ValueError(f"Invalid Cito round file: {path.name}: {error}") from error

    fighters: dict[str, tuple[str, set[int]]] = {}
    seen_ids = set()
    seen_pairs = set()
    for row in rows:
        pair = (row.source_fighter_slug, row.round_number)
        if row.source_round_stat_id in seen_ids or pair in seen_pairs:
            raise ValueError(f"Duplicate round ID or fighter/round: {path.name}")
        seen_ids.add(row.source_round_stat_id)
        seen_pairs.add(pair)
        if row.source_fighter_slug not in fighters:
            fighters[row.source_fighter_slug] = (row.fighter_name, set())
        name, rounds = fighters[row.source_fighter_slug]
        if name != row.fighter_name:
            raise ValueError(f"Fighter name changes within bout: {path.name}")
        rounds.add(row.round_number)
    if len(fighters) != 2:
        raise ValueError(f"Expected exactly two fighters in {path.name}")
    round_sets = [rounds for _, rounds in fighters.values()]
    if round_sets[0] != round_sets[1] or round_sets[0] != set(
        range(1, max(round_sets[0]) + 1)
    ):
        raise ValueError(f"Incomplete or nonconsecutive rounds: {path.name}")
    return rows


def export_cito_rounds(input_dir: Path, output_path: Path) -> tuple[int, int]:
    """Require valid, complete bouts; publish deterministic JSONL atomically."""
    if output_path.suffix != ".jsonl":
        raise ValueError("Output must use the .jsonl extension.")
    paths = sorted(input_dir.glob("*.json"))
    if not paths:
        raise ValueError("No cached Cito round files were found.")
    rows = []
    seen_ids = set()
    for path in paths:
        for row in read_cito_round_bout(path):
            if row.source_round_stat_id in seen_ids:
                raise ValueError("Round-stat ID reused across bouts.")
            seen_ids.add(row.source_round_stat_id)
            rows.append(row)
    rows.sort(key=lambda row: (
        row.source_bout_id, row.round_number, row.source_fighter_slug
    ))
    records = [asdict(row) for row in rows]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(
        dir=output_path.parent, prefix=".upset-cito-rounds-"
    ) as folder:
        temporary = Path(folder) / output_path.name
        with temporary.open("w", encoding="utf-8", newline="\n") as saved:
            for record in records:
                saved.write(json.dumps(
                    record, ensure_ascii=False, allow_nan=False, sort_keys=True
                ) + "\n")
        with temporary.open(encoding="utf-8") as saved:
            if [json.loads(line) for line in saved] != records:
                raise ValueError("Cito round export read-back verification failed.")
        temporary.replace(output_path)
    return len(paths), len(rows)


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    bouts, rounds = export_cito_rounds(args.input_dir, args.output)
    print(f"Verified Cito bouts: {bouts}")
    print(f"Normalized fighter-round rows: {rounds}")
    print("Read-back verification: passed")
    print(f"Saved to: {args.output}")


if __name__ == "__main__":
    main()
