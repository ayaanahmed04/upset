"""Save and independently audit a separate, deterministic Elo history."""

import argparse
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from upset.data.audit_prefight_ratings import audit_prefight_ratings
from upset.data.export_prefight import read_identified
from upset.data.identify_historical import IdentifiedFight
from upset.data.models import Fight
from upset.data.prefight_ratings import build_rating_history, read_rating_history


def export_prefight_ratings(fights_path: Path, output_path: Path) -> int:
    if output_path.resolve() == fights_path.resolve():
        raise ValueError("Output must not replace the identified fights.")
    fights = read_identified(
        fights_path,
        Fight,
        IdentifiedFight,
        ("upset_fighter_1_id", "upset_fighter_2_id"),
    )
    rows = build_rating_history(fights)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=output_path.parent, prefix=".upset-ratings-") as tmp:
        staged = Path(tmp) / output_path.name
        staged.write_text(
            "".join(
                json.dumps(row.as_record(), allow_nan=False, sort_keys=True) + "\n"
                for row in rows
            ),
            encoding="utf-8",
        )
        restored = read_rating_history(staged)
        if list(restored.values()) != list(rows):
            raise ValueError("Rating history read-back failed.")
        audit_prefight_ratings(fights, restored)
        if output_path.exists() and output_path.read_bytes() != staged.read_bytes():
            raise ValueError("Existing rating history differs; use a new output path.")
        staged.replace(output_path)
    return len(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    base = Path("data/processed/kaggle_ufc_1994_2026")
    parser.add_argument(
        "--fights", type=Path, default=base / "identified/fights_identified.jsonl"
    )
    parser.add_argument(
        "--output", type=Path, default=base / "prefight/rating_history_v1.jsonl"
    )
    args = parser.parse_args()
    count = export_prefight_ratings(args.fights, args.output)
    print(f"Pre-fight rating rows: {count}")
    print("Read-back and independent full replay: passed")
    print(f"Saved to: {args.output}")


if __name__ == "__main__":
    main()
