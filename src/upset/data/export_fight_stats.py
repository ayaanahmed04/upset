"""Export normalized historical fighter-by-fight statistics."""

import csv
import json
from dataclasses import asdict
from pathlib import Path
from tempfile import TemporaryDirectory

from upset.data.models import Fight, FightStats
from upset.data.normalization import (
    normalize_kaggle_fight,
    normalize_kaggle_fight_stats,
)

_HISTORICAL_SOURCE = "kaggle_ufc_1994_2026"


def load_linked_fights(linked_fight_path: Path) -> dict[str, Fight]:
    """Load linked historical fights indexed by source bout ID."""

    fights_by_id = {}
    errors = []

    with linked_fight_path.open(encoding="utf-8") as source_file:
        for record_number, line in enumerate(source_file, start=1):
            try:
                fight = Fight(**json.loads(line))

                if fight.source != _HISTORICAL_SOURCE:
                    raise ValueError(
                        "Linked fight belongs to an unexpected source."
                    )

                if fight.source_bout_id in fights_by_id:
                    raise ValueError(
                        f"Duplicate linked fight ID: "
                        f"{fight.source_bout_id}"
                    )

            except (
                json.JSONDecodeError,
                KeyError,
                TypeError,
                ValueError,
            ) as error:
                errors.append(f"Record {record_number}: {error}")
            else:
                fights_by_id[fight.source_bout_id] = fight

    if errors:
        details = "\n".join(errors[:5])
        raise ValueError(
            f"Linked fight validation failed.\n"
            f"Accepted: {len(fights_by_id)}\n"
            f"Rejected: {len(errors)}\n"
            f"First errors:\n{details}"
        )

    if not fights_by_id:
        raise ValueError("The linked fight dataset is empty.")

    return fights_by_id


def load_historical_fight_stats(
    raw_fight_path: Path,
    linked_fight_path: Path,
) -> list[FightStats]:
    """Load and normalize every historical fighter-fight record."""

    linked_by_id = load_linked_fights(linked_fight_path)

    records = []
    errors = []
    seen_raw_fight_ids = set()
    seen_record_keys = set()
    used_linked_fight_ids = set()

    with raw_fight_path.open(
        encoding="utf-8-sig",
        newline="",
    ) as source_file:
        reader = csv.DictReader(source_file)

        for record_number, raw_fight in enumerate(reader, start=1):
            try:
                # Validate the raw fight and obtain its source ID.
                raw_identity = normalize_kaggle_fight(raw_fight)
                source_bout_id = raw_identity.source_bout_id

                if source_bout_id in seen_raw_fight_ids:
                    raise ValueError(
                        f"Duplicate raw fight ID: {source_bout_id}"
                    )

                seen_raw_fight_ids.add(source_bout_id)

                linked_fight = linked_by_id.get(source_bout_id)

                if linked_fight is None:
                    raise ValueError(
                        f"No linked fight found for: {source_bout_id}"
                    )

                fighter_records = normalize_kaggle_fight_stats(
                    raw_fight,
                    linked_fight,
                )

                new_keys = [
                    (
                        record.source,
                        record.source_bout_id,
                        record.source_fighter_id,
                    )
                    for record in fighter_records
                ]

                if (
                    len(set(new_keys)) != len(new_keys)
                    or any(
                        key in seen_record_keys
                        for key in new_keys
                    )
                ):
                    raise ValueError(
                        f"Duplicate fighter-fight record: {source_bout_id}"
                    )

            except (KeyError, TypeError, ValueError) as error:
                errors.append(f"Record {record_number}: {error}")
            else:
                records.extend(fighter_records)
                seen_record_keys.update(new_keys)
                used_linked_fight_ids.add(source_bout_id)

    # Refuse to return a partial dataset.
    if errors:
        details = "\n".join(errors[:5])
        raise ValueError(
            f"Historical fight-stat validation failed.\n"
            f"Accepted fights: {len(records) // 2}\n"
            f"Rejected fights: {len(errors)}\n"
            f"First errors:\n{details}"
        )

    if not records:
        raise ValueError("The raw fight dataset contains no records.")

    unused_linked_fights = (
        set(linked_by_id)
        - used_linked_fight_ids
    )

    if unused_linked_fights:
        examples = sorted(unused_linked_fights)[:5]
        raise ValueError(
            "Linked fights were not present in the raw dataset: "
            f"{examples}"
        )

    return records


def export_historical_fight_stats(
    raw_fight_path: Path,
    linked_fight_path: Path,
    output_path: Path,
) -> int:
    """Validate, export, and verify historical fighter-fight statistics."""

    input_paths = (raw_fight_path, linked_fight_path)

    if output_path.resolve() in {
        path.resolve()
        for path in input_paths
    }:
        raise ValueError("Output must not overwrite an input file.")

    if output_path.suffix != ".jsonl":
        raise ValueError("Output must use the .jsonl extension.")

    fight_stats = load_historical_fight_stats(
        raw_fight_path,
        linked_fight_path,
    )
    records = [
        asdict(record)
        for record in fight_stats
    ]

    output_path.parent.mkdir(parents=True, exist_ok=True)

    with TemporaryDirectory(
        dir=output_path.parent,
        prefix=".upset-fight-stats-",
    ) as temporary_directory:
        temporary_path = (
            Path(temporary_directory)
            / "fight_stats.jsonl"
        )

        with temporary_path.open(
            "w",
            encoding="utf-8",
            newline="\n",
        ) as output_file:
            for record in records:
                output_file.write(
                    json.dumps(
                        record,
                        ensure_ascii=False,
                        allow_nan=False,
                    )
                    + "\n"
                )

        # Read every record back before publishing the final file.
        with temporary_path.open(encoding="utf-8") as saved_file:
            restored_records = [
                json.loads(line)
                for line in saved_file
            ]

        if restored_records != records:
            raise ValueError(
                "Saved fight statistics do not match validated records."
            )

        temporary_path.replace(output_path)

    return len(records)


def main() -> None:
    """Export the accepted historical snapshot from the project folder."""

    raw_fight_path = Path(
        "data/raw/kaggle_ufc_1994_2026/"
        "ufc_gold_dataset_final.csv"
    )
    processed_directory = Path(
        "data/processed/kaggle_ufc_1994_2026"
    )
    linked_fight_path = (
        processed_directory
        / "fights_linked.jsonl"
    )
    output_path = (
        processed_directory
        / "fight_stats.jsonl"
    )

    count = export_historical_fight_stats(
        raw_fight_path,
        linked_fight_path,
        output_path,
    )

    print(f"Exported fighter-fight statistics: {count}")
    print(f"Source fights: {count // 2}")
    print("Rejected fights: 0")
    print("Read-back verification: passed")
    print(f"Saved to: {output_path}")


if __name__ == "__main__":
    main()