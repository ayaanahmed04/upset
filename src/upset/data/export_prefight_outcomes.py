"""Export prior UFC outcomes and activity without altering existing histories."""

import json
from pathlib import Path
from tempfile import TemporaryDirectory

from upset.data.export_prefight import read_identified
from upset.data.identify_historical import IdentifiedFight
from upset.data.models import Fight
from upset.data.prefight_outcomes import build_outcome_history


def export_prefight_outcomes(fights_path: Path, output_path: Path) -> int:
    if output_path.resolve() == fights_path.resolve():
        raise ValueError("Output must not replace the identified fights.")
    fights = read_identified(
        fights_path, Fight, IdentifiedFight,
        ("upset_fighter_1_id", "upset_fighter_2_id"),
    )
    rows = [item.as_record() for item in build_outcome_history(fights)]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=output_path.parent, prefix=".upset-outcomes-") as tmp:
        staged = Path(tmp) / output_path.name
        with staged.open("w", encoding="utf-8", newline="\n") as stream:
            for row in rows:
                stream.write(json.dumps(row, allow_nan=False) + "\n")
        with staged.open(encoding="utf-8") as check:
            if [json.loads(line) for line in check] != rows:
                raise ValueError("Outcome history read-back failed.")
        staged.replace(output_path)
    return len(rows)


def main() -> None:
    base = Path("data/processed/kaggle_ufc_1994_2026")
    source = base / "identified" / "fights_identified.jsonl"
    output = base / "prefight" / "outcome_history_v1.jsonl"
    count = export_prefight_outcomes(source, output)
    print(f"Pre-fight outcome history rows: {count}")
    print("Read-back verification: passed")
    print(f"Saved to: {output}")


if __name__ == "__main__":
    main()
