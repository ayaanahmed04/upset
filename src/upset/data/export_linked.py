"""Export historical fights with resolved fighter profile IDs."""

import json
from dataclasses import asdict
from pathlib import Path
from tempfile import TemporaryDirectory

from upset.data.linking import link_historical_fights
from upset.data.models import Fight, Fighter


def export_linked_fights(
    fights_path: Path,
    profiles_path: Path,
    mappings_path: Path,
    output_path: Path,
) -> int:
    """Load, link, verify, and save fights without modifying inputs."""

    input_paths = (fights_path, profiles_path, mappings_path)

    if output_path.resolve() in {path.resolve() for path in input_paths}:
        raise ValueError("Output must not overwrite an input file.")

    if output_path.suffix != ".jsonl":
        raise ValueError("Output must use the .jsonl extension.")

    with fights_path.open(encoding="utf-8") as source_file:
        fights = [Fight(**json.loads(line)) for line in source_file]

    with profiles_path.open(encoding="utf-8") as source_file:
        profiles = [Fighter(**json.loads(line)) for line in source_file]

    with mappings_path.open(encoding="utf-8") as source_file:
        mapping_document = json.load(source_file)

    if not fights or not profiles:
        raise ValueError("Fight and profile datasets must not be empty.")

    if (
        type(mapping_document["schema_version"]) is not int
        or mapping_document["schema_version"] != 1
    ):
        raise ValueError("Unsupported mapping version.")

    expected_source = "kaggle_ufc_1994_2026"

    if mapping_document["source"] != expected_source:
        raise ValueError("Unexpected mapping source.")

    overrides = mapping_document["overrides"]

    if not isinstance(overrides, list):
        raise TypeError("Mapping overrides must be a list.")

    if (
        any(fight.source != expected_source for fight in fights)
        or any(profile.source != expected_source for profile in profiles)
        or any(row["source"] != expected_source for row in overrides)
    ):
        raise ValueError("All inputs must belong to the historical snapshot.")

    # The linker rejects unresolved participants and invalid mappings.
    linked_fights = link_historical_fights(fights, profiles, overrides)
    records = [asdict(fight) for fight in linked_fights]

    output_path.parent.mkdir(parents=True, exist_ok=True)

    with TemporaryDirectory(
        dir=output_path.parent,
        prefix=".upset-linked-",
    ) as temporary_directory:
        temporary_path = Path(temporary_directory) / "fights_linked.jsonl"

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

        with temporary_path.open(encoding="utf-8") as saved_file:
            restored_records = [
                json.loads(line) for line in saved_file
            ]

        if restored_records != records:
            raise ValueError("Saved fights do not match linked records.")

        temporary_path.replace(output_path)

    return len(records)


def main() -> None:
    """Export linked fights when run from the project folder."""

    processed_directory = Path("data/processed/kaggle_ufc_1994_2026")
    output_path = processed_directory / "fights_linked.jsonl"

    count = export_linked_fights(
        fights_path=processed_directory / "fights.jsonl",
        profiles_path=processed_directory / "fighters.jsonl",
        mappings_path=Path("data/mappings/kaggle_fighter_overrides.json"),
        output_path=output_path,
    )

    print(f"Exported linked fights: {count}")
    print(f"Linked participant slots: {count * 2}")
    print("Unresolved slots: 0")
    print("Read-back verification: passed")
    print(f"Saved to: {output_path}")


if __name__ == "__main__":
    main()