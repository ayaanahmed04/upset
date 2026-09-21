"""Read and validate historical fights before exporting them."""

import csv
import json
from dataclasses import asdict
from pathlib import Path
from tempfile import TemporaryDirectory

from upset.data.models import Fight
from upset.data.normalization import normalize_kaggle_fight


def load_historical_fights(input_path: Path) -> list[Fight]:
    """Load the raw CSV and return validated UPSET fight records."""

    fights: list[Fight] = []
    seen_ids: set[str] = set()
    errors: list[str] = []

    # utf-8-sig also handles CSVs with an invisible marker at the start.
    # newline="" lets Python's CSV reader handle line endings correctly.
    with input_path.open(encoding="utf-8-sig", newline="") as source_file:
        reader = csv.DictReader(source_file)

        # Record 1 is the first fight after the column headers.
        for record_number, raw_row in enumerate(reader, start=1):
            try:
                # Reuse the conversion rules we already built and tested.
                fight = normalize_kaggle_fight(raw_row)

                # Different rows must not represent the same source fight.
                if fight.source_bout_id in seen_ids:
                    raise ValueError(
                        f"Duplicate fight ID: {fight.source_bout_id}"
                    )

            except (KeyError, TypeError, ValueError) as error:
                errors.append(f"Record {record_number}: {error}")
            else:
                fights.append(fight)
                seen_ids.add(fight.source_bout_id)

    # Refuse to return a partial dataset if any record failed.
    if errors:
        details = "\n".join(errors[:5])
        raise ValueError(
            f"Historical data validation failed.\n"
            f"Accepted: {len(fights)}\n"
            f"Rejected: {len(errors)}\n"
            f"First errors:\n{details}"
        )

    # An empty file should not count as a successful conversion.
    if not fights:
        raise ValueError("The input CSV contains no fight records.")

    return fights

def export_historical_fights(
    input_path: Path,
    output_path: Path,
) -> int:
    """Validate historical fights, save JSON Lines, and return the count."""

    if input_path.resolve() == output_path.resolve():
        raise ValueError("Output must not overwrite the input file.")

    if output_path.suffix != ".jsonl":
        raise ValueError("Output must use the .jsonl extension.")

    # Finish all row validation before creating any output.
    fights = load_historical_fights(input_path)

    # Convert Fight objects into dictionaries that JSON can store.
    records = [asdict(fight) for fight in fights]

    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Write to a temporary location first. An interrupted write should
    # not replace an existing successful export with an incomplete file.
    with TemporaryDirectory(
        dir=output_path.parent,
        prefix=".upset-export-",
    ) as temporary_directory:
        temporary_path = Path(temporary_directory) / "fights.jsonl"

        with temporary_path.open(
            "w", encoding="utf-8", newline="\n"
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

        # Read the saved data back and compare every record.
        # This also checks that missing values and text IDs survived.
        with temporary_path.open(encoding="utf-8") as saved_file:
            restored_records = [
                json.loads(line) for line in saved_file
            ]

        if restored_records != records:
            raise ValueError("Saved data does not match validated records.")

        # Publish the completed file only after verification succeeds.
        temporary_path.replace(output_path)

    return len(records)


def main() -> None:
    """Export the historical snapshot when run from the project folder."""

    input_path = Path(
        "data/raw/kaggle_ufc_1994_2026/ufc_gold_dataset_final.csv"
    )
    output_path = Path(
        "data/processed/kaggle_ufc_1994_2026/fights.jsonl"
    )

    count = export_historical_fights(input_path, output_path)

    print(f"Exported fights: {count}")
    print("Rejected records: 0")
    print("Read-back verification: passed")
    print(f"Saved to: {output_path}")


if __name__ == "__main__":
    main()