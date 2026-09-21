"""Validate and export historical fighter profiles as JSON Lines."""

import csv
import json
from dataclasses import asdict
from pathlib import Path
from tempfile import TemporaryDirectory

from upset.data.normalization import normalize_kaggle_fighter


def export_historical_profiles(
    input_path: Path,
    output_path: Path,
) -> int:
    """Export all valid profiles, or fail without replacing the output."""

    if input_path.resolve() == output_path.resolve():
        raise ValueError("Output must not overwrite the input file.")

    if output_path.suffix != ".jsonl":
        raise ValueError("Output must use the .jsonl extension.")

    records = []
    seen_ids = set()
    errors = []

    with input_path.open(encoding="utf-8-sig", newline="") as source_file:
        reader = csv.DictReader(source_file)

        for record_number, raw_row in enumerate(reader, start=1):
            try:
                fighter = normalize_kaggle_fighter(raw_row)

                # Shared names are allowed; shared source IDs are not.
                if fighter.source_fighter_id in seen_ids:
                    raise ValueError(
                        f"Duplicate profile ID: {fighter.source_fighter_id}"
                    )

            except (KeyError, TypeError, ValueError) as error:
                errors.append(f"Record {record_number}: {error}")
            else:
                records.append(asdict(fighter))
                seen_ids.add(fighter.source_fighter_id)

    if errors:
        details = "\n".join(errors[:5])
        raise ValueError(
            f"Profile validation failed.\n"
            f"Accepted: {len(records)}\n"
            f"Rejected: {len(errors)}\n"
            f"First errors:\n{details}"
        )

    if not records:
        raise ValueError("The input CSV contains no profile records.")

    # Only create output after every profile has passed validation.
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with TemporaryDirectory(
        dir=output_path.parent,
        prefix=".upset-profiles-",
    ) as temporary_directory:
        temporary_path = Path(temporary_directory) / "fighters.jsonl"

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

        # Verify every saved record before replacing the final file.
        with temporary_path.open(encoding="utf-8") as saved_file:
            restored_records = [
                json.loads(line) for line in saved_file
            ]

        if restored_records != records:
            raise ValueError("Saved profiles do not match validated records.")

        temporary_path.replace(output_path)

    return len(records)


def main() -> None:
    """Export profiles when run from the project folder."""

    input_path = Path(
        "data/raw/kaggle_ufc_1994_2026/ufc_fighters_final.csv"
    )
    output_path = Path(
        "data/processed/kaggle_ufc_1994_2026/fighters.jsonl"
    )

    count = export_historical_profiles(input_path, output_path)

    print(f"Exported profiles: {count}")
    print("Rejected records: 0")
    print("Read-back verification: passed")
    print(f"Saved to: {output_path}")


if __name__ == "__main__":
    main()