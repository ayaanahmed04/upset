"""Run the fixed chronological baseline on the locally exported matchups."""

import argparse
import json
from pathlib import Path

from upset.modeling.baseline import evaluate_baseline, read_matchups


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        type=Path,
        default=Path("data/processed/kaggle_ufc_1994_2026/prefight/matchups.jsonl"),
        help="Path to verified historical matchup JSONL",
    )
    args = parser.parse_args()
    print(json.dumps(evaluate_baseline(read_matchups(args.input)), indent=2))


if __name__ == "__main__":
    main()
