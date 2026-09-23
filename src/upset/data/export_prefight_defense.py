"""Export dated defensive history alongside the unchanged v1 feature export."""

import json
from pathlib import Path
from tempfile import TemporaryDirectory

from upset.data.export_prefight import read_identified
from upset.data.identify_historical import IdentifiedFight, IdentifiedFightStats
from upset.data.models import Fight, FightStats
from upset.data.prefight_defense import build_defensive_history


def export_prefight_defense(
    fights_path: Path, stats_path: Path, output_path: Path
) -> int:
    if output_path.resolve() in (fights_path.resolve(), stats_path.resolve()):
        raise ValueError("Output must not replace an identified input.")
    fights = read_identified(
        fights_path, Fight, IdentifiedFight,
        ("upset_fighter_1_id", "upset_fighter_2_id"),
    )
    stats = read_identified(
        stats_path, FightStats, IdentifiedFightStats, ("upset_fighter_id",)
    )
    rows = [snapshot.as_record() for snapshot in build_defensive_history(fights, stats)]

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=output_path.parent, prefix=".upset-defense-") as tmp:
        staged = Path(tmp) / output_path.name
        with staged.open("w", encoding="utf-8", newline="\n") as saved:
            for row in rows:
                saved.write(json.dumps(row, ensure_ascii=False, allow_nan=False)
                            + "\n")
        with staged.open(encoding="utf-8") as check:
            if [json.loads(line) for line in check] != rows:
                raise ValueError("Defensive history read-back failed.")
        staged.replace(output_path)
    return len(rows)


def main() -> None:
    base = Path("data/processed/kaggle_ufc_1994_2026")
    identified = base / "identified"
    output = base / "prefight" / "defensive_history_v2.jsonl"
    count = export_prefight_defense(
        identified / "fights_identified.jsonl",
        identified / "fight_stats_identified.jsonl",
        output,
    )
    print(f"Pre-fight defensive history rows: {count}")
    print("Read-back verification: passed")
    print(f"Saved to: {output}")


if __name__ == "__main__":
    main()
