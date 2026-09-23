"""Run the frozen development baseline without changing the original report."""

import argparse
import json
import subprocess
from pathlib import Path

from upset.modeling.evaluation import export_development_evaluation


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--matchups", type=Path,
        default=Path("data/processed/kaggle_ufc_1994_2026/prefight/matchups.jsonl"),
    )
    parser.add_argument(
        "--registry", type=Path, default=Path("data/mappings/fighter_registry.json")
    )
    parser.add_argument(
        "--output", type=Path,
        default=Path("data/processed/kaggle_ufc_1994_2026/experiments/development_v1"),
    )
    args = parser.parse_args()
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], check=True, capture_output=True, text=True
    ).stdout.strip()
    for args_to_check in (["git", "diff", "--quiet"],
                          ["git", "diff", "--cached", "--quiet"]):
        if subprocess.run(args_to_check, check=False).returncode:
            parser.error("Commit tracked changes before producing a code revision.")
    report = export_development_evaluation(
        args.matchups, args.registry, args.output, commit
    )
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
