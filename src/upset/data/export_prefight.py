"""Export time-safe fighter histories from the identified historical files."""

import json
from dataclasses import fields
from pathlib import Path
from tempfile import TemporaryDirectory

from upset.data.identify_historical import IdentifiedFight, IdentifiedFightStats
from upset.data.models import Fight, FightStats
from upset.data.prefight import build_prefight_snapshots


def read_identified(
    path: Path, model: type, wrapper: type, id_fields: tuple[str, ...]
) -> list:
    expected = {field.name for field in fields(model)} | set(id_fields)
    records = []
    with path.open(encoding="utf-8") as source:
        for line_number, line in enumerate(source, 1):
            try:
                data = json.loads(line)
                if not isinstance(data, dict) or set(data) != expected:
                    raise ValueError("fields do not match the identified model")
                record = wrapper(
                    model(**{key: data[key] for key in data if key not in id_fields}),
                    *(data[field] for field in id_fields),
                )
            except (TypeError, ValueError) as error:
                raise ValueError(
                    f"Invalid {path.name} record at line {line_number}: {error}"
                ) from error
            records.append(record)
    return records


def export_prefight_stats(
    fights_path: Path,
    stats_path: Path,
    output_path: Path,
) -> int:
    """Validate all input before atomically replacing one verified output file."""
    if output_path.resolve() in (fights_path.resolve(), stats_path.resolve()):
        raise ValueError("Output must not overwrite an input file.")
    fights = read_identified(
        fights_path,
        Fight,
        IdentifiedFight,
        ("upset_fighter_1_id", "upset_fighter_2_id"),
    )
    stats = read_identified(
        stats_path,
        FightStats,
        IdentifiedFightStats,
        ("upset_fighter_id",),
    )
    snapshots = build_prefight_snapshots(fights, stats)
    records = [snapshot.as_record() for snapshot in snapshots]

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(
        dir=output_path.parent, prefix=".upset-prefight-"
    ) as directory:
        temporary = Path(directory) / output_path.name
        with temporary.open("w", encoding="utf-8", newline="\n") as saved:
            for record in records:
                saved.write(
                    json.dumps(record, ensure_ascii=False, allow_nan=False) + "\n"
                )
        with temporary.open(encoding="utf-8") as saved:
            restored = [json.loads(line) for line in saved]
        if restored != records:
            raise ValueError("Pre-fight snapshot read-back verification failed.")
        temporary.replace(output_path)
    return len(records)


def main() -> None:
    processed = Path("data/processed/kaggle_ufc_1994_2026")
    identified = processed / "identified"
    output = processed / "prefight" / "prefight_stats.jsonl"
    count = export_prefight_stats(
        identified / "fights_identified.jsonl",
        identified / "fight_stats_identified.jsonl",
        output,
    )
    print(f"Pre-fight fighter snapshots: {count}")
    print("Read-back verification: passed")
    print(f"Saved to: {output}")


if __name__ == "__main__":
    main()
