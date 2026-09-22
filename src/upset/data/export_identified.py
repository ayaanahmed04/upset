"""Export historical records with permanent UPSET fighter identities."""

import json
from dataclasses import fields
from pathlib import Path
from tempfile import TemporaryDirectory

from upset.data.identify_historical import identify_historical_data
from upset.data.identity import load_fighter_registry
from upset.data.models import Fight, Fighter, FightStats


def _read_records(path: Path, record_type: type) -> list:
    """Read every JSONL row into its existing normalized source model."""
    records = []
    expected_fields = {field.name for field in fields(record_type)}
    with path.open(encoding="utf-8") as source_file:
        for line_number, line in enumerate(source_file, start=1):
            try:
                record = json.loads(line)
                if not isinstance(record, dict) or set(record) != expected_fields:
                    raise ValueError("record fields do not match the source model")
                records.append(record_type(**record))
            except (ValueError, TypeError) as error:
                raise ValueError(
                    f"Invalid {path.name} record at line {line_number}: {error}"
                ) from error
    return records


def _write_verified(path: Path, records: list[dict]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as output_file:
        for record in records:
            output_file.write(
                json.dumps(record, ensure_ascii=False, allow_nan=False) + "\n"
            )

    with path.open(encoding="utf-8") as saved_file:
        restored = [json.loads(line) for line in saved_file]
    if restored != records:
        raise ValueError(f"Read-back verification failed: {path.name}")


def export_identified_historical(
    profiles_path: Path,
    fights_path: Path,
    fight_stats_path: Path,
    registry_path: Path,
    output_dir: Path,
) -> tuple[int, int, int]:
    """Validate all three inputs and publish verified identity-enriched files."""
    filenames = (
        "fighters_identified.jsonl",
        "fights_identified.jsonl",
        "fight_stats_identified.jsonl",
    )
    input_paths = (profiles_path, fights_path, fight_stats_path, registry_path)
    output_paths = tuple(output_dir / filename for filename in filenames)
    if any(
        output_path.resolve() in {input_path.resolve() for input_path in input_paths}
        for output_path in output_paths
    ):
        raise ValueError("Output must not overwrite an input file.")

    registry = load_fighter_registry(registry_path)
    profiles = _read_records(profiles_path, Fighter)
    fights = _read_records(fights_path, Fight)
    fight_stats = _read_records(fight_stats_path, FightStats)
    identified = identify_historical_data(profiles, fights, fight_stats, registry)

    batches = (
        [record.as_record() for record in identified.profiles],
        [record.as_record() for record in identified.fights],
        [record.as_record() for record in identified.fight_stats],
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=output_dir, prefix=".upset-identified-") as directory:
        temporary_paths = tuple(Path(directory) / filename for filename in filenames)
        for path, records in zip(temporary_paths, batches, strict=True):
            _write_verified(path, records)
        for temporary_path, output_path in zip(
            temporary_paths, output_paths, strict=True
        ):
            temporary_path.replace(output_path)

    return tuple(len(batch) for batch in batches)


def main() -> None:
    processed = Path("data/processed/kaggle_ufc_1994_2026")
    counts = export_identified_historical(
        profiles_path=processed / "fighters.jsonl",
        fights_path=processed / "fights_linked.jsonl",
        fight_stats_path=processed / "fight_stats.jsonl",
        registry_path=Path("data/mappings/fighter_registry.json"),
        output_dir=processed / "identified",
    )
    print(f"Identified profiles: {counts[0]}")
    print(f"Identified fights: {counts[1]}")
    print(f"Identified fighter-fight statistics: {counts[2]}")
    print("Unresolved mappings: 0")
    print("Read-back verification: passed")
    print(f"Saved to: {processed / 'identified'}")


if __name__ == "__main__":
    main()
