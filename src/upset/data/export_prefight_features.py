"""Export pre-fight metrics derived from dated fighter snapshots."""

import json
from dataclasses import fields
from pathlib import Path
from tempfile import TemporaryDirectory

from upset.data.prefight import PreFightSnapshot
from upset.data.prefight_features import build_prefight_features


def export_prefight_features(snapshot_path: Path, output_path: Path) -> int:
    """Validate every snapshot before publishing a verified metrics file."""
    if snapshot_path.resolve() == output_path.resolve():
        raise ValueError("Output must not overwrite the snapshot input.")

    expected = {field.name for field in fields(PreFightSnapshot)}
    snapshots = []
    with snapshot_path.open(encoding="utf-8") as source:
        for line_number, line in enumerate(source, start=1):
            try:
                record = json.loads(line)
                if not isinstance(record, dict) or set(record) != expected:
                    raise ValueError("fields do not match the snapshot model")
                snapshots.append(PreFightSnapshot(**record))
            except (TypeError, ValueError) as error:
                raise ValueError(
                    f"Invalid snapshot at line {line_number}: {error}"
                ) from error

    # Each historical bout must still have both participants and one date.
    bouts: dict[str, list[PreFightSnapshot]] = {}
    for snapshot in snapshots:
        bouts.setdefault(snapshot.source_bout_id, []).append(snapshot)
    for bout_id, participants in bouts.items():
        if (
            len(participants) != 2
            or participants[0].event_date != participants[1].event_date
        ):
            raise ValueError(f"Expected two snapshots on one date for bout: {bout_id}")

    records = [feature.as_record() for feature in build_prefight_features(snapshots)]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(
        dir=output_path.parent, prefix=".upset-features-"
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
            raise ValueError("Pre-fight feature read-back verification failed.")
        temporary.replace(output_path)
    return len(records)


def main() -> None:
    directory = Path("data/processed/kaggle_ufc_1994_2026/prefight")
    output = directory / "fighter_features.jsonl"
    count = export_prefight_features(directory / "prefight_stats.jsonl", output)
    print(f"Pre-fight fighter feature rows: {count}")
    print("Read-back verification: passed")
    print(f"Saved to: {output}")


if __name__ == "__main__":
    main()
