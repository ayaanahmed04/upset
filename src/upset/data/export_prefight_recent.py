"""Export and independently audit dated recent-performance histories."""

import argparse
import json
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory

from upset.data.audit_prefight_recent import audit_prefight_recent, read_recent_sources
from upset.data.prefight_recent import build_recent_history, read_recent_history


def export_prefight_recent(
    fights_path: Path, stats_path: Path, output_path: Path
) -> int:
    inputs = (fights_path, stats_path)
    if len({p.resolve() for p in (*inputs, output_path)}) != 3:
        raise ValueError("Recent export input and output paths must be distinct.")
    hashes = [sha256(p.read_bytes()).hexdigest() for p in inputs]
    fights, stats = read_recent_sources(fights_path, stats_path)
    rows = build_recent_history(fights, stats)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=output_path.parent, prefix=".upset-recent-") as tmp:
        staged = Path(tmp) / "recent.jsonl"
        staged.write_text(
            "".join(
                json.dumps(row.as_record(), allow_nan=False, sort_keys=True) + "\n"
                for row in rows
            ),
            encoding="utf-8",
        )
        restored = read_recent_history(staged)
        if list(restored.values()) != list(rows):
            raise ValueError("Recent-history read-back failed.")
        audit_prefight_recent(fights, stats, restored)
        if hashes != [sha256(p.read_bytes()).hexdigest() for p in inputs]:
            raise ValueError("Recent-history source changed during export.")
        if output_path.exists() and output_path.read_bytes() != staged.read_bytes():
            raise ValueError("Existing recent history differs; use a new output path.")
        staged.replace(output_path)
    return len(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    base = Path("data/processed/kaggle_ufc_1994_2026")
    parser.add_argument(
        "--fights", type=Path, default=base / "identified/fights_identified.jsonl"
    )
    parser.add_argument(
        "--stats", type=Path, default=base / "identified/fight_stats_identified.jsonl"
    )
    parser.add_argument(
        "--output", type=Path, default=base / "prefight/recent_history_v1.jsonl"
    )
    args = parser.parse_args()
    count = export_prefight_recent(args.fights, args.stats, args.output)
    print(f"Pre-fight recent-performance rows: {count}")
    print("Read-back and independent full source recomputation: passed")
    print(f"Saved to: {args.output}")


if __name__ == "__main__":
    main()
