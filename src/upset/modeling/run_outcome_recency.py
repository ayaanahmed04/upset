"""Evaluate dated UFC outcome and activity histories on frozen folds."""

import argparse
import json
import subprocess
from pathlib import Path

from upset.modeling.outcome_recency import export_outcome_comparison


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    base = Path("data/processed/kaggle_ufc_1994_2026")
    parser.add_argument(
        "--matchups", type=Path, default=base / "prefight" / "matchups.jsonl"
    )
    parser.add_argument(
        "--defense", type=Path,
        default=base / "prefight" / "defensive_history_v2.jsonl",
    )
    parser.add_argument(
        "--outcomes", type=Path,
        default=base / "prefight" / "outcome_history_v1.jsonl",
    )
    parser.add_argument(
        "--fights", type=Path,
        default=base / "identified" / "fights_identified.jsonl",
    )
    parser.add_argument(
        "--registry", type=Path, default=Path("data/mappings/fighter_registry.json")
    )
    parser.add_argument(
        "--output", type=Path, default=base / "experiments" / "outcome_recency_v1"
    )
    args = parser.parse_args()
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], check=True, capture_output=True, text=True
    ).stdout.strip()
    for check in (["git", "diff", "--quiet"],
                  ["git", "diff", "--cached", "--quiet"]):
        if subprocess.run(check, check=False).returncode:
            parser.error("Commit tracked changes before producing a code revision.")
    print(json.dumps(export_outcome_comparison(
        args.matchups, args.defense, args.outcomes, args.fights,
        args.registry, args.output, commit
    ), indent=2))


if __name__ == "__main__":
    main()
