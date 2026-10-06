"""Freeze the accepted research recipe, or record its replayable forecasts."""

import argparse
import subprocess
from pathlib import Path

from upset.modeling.frozen_replay import freeze_model, record_generated_forecasts


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="action", required=True)
    freeze = commands.add_parser("freeze")
    base = Path("data/processed/kaggle_ufc_1994_2026")
    for name, path in {
        "matchups": base / "prefight/matchups.jsonl",
        "defense": base / "prefight/defensive_history_v2.jsonl",
        "ratings": base / "prefight/rating_history_v1.jsonl",
        "recent": base / "prefight/recent_history_v1.jsonl",
        "fights": base / "identified/fights_identified.jsonl",
        "stats": base / "identified/fight_stats_identified.jsonl",
        "registry": Path("data/mappings/fighter_registry.json"),
        "reference": base / "experiments/recent_form_v1",
        "output": base / "models/symmetric_recent_elo_v1",
    }.items():
        freeze.add_argument("--" + name, type=Path, default=path)
    record = commands.add_parser("record")
    record.add_argument("--schedule", type=Path, required=True)
    record.add_argument("--features", type=Path, required=True)
    record.add_argument("--frozen", type=Path, default=base / "models/symmetric_recent_elo_v1")
    record.add_argument("--registry", type=Path,
                        default=Path("data/mappings/fighter_registry.json"))
    record.add_argument("--output-root", type=Path,
                        default=Path("data/processed/prospective"))
    args = parser.parse_args()
    try:
        if args.action == "freeze":
            commit = subprocess.run(
                ["git", "rev-parse", "HEAD"], check=True, capture_output=True,
                text=True,
            ).stdout.strip()
            if subprocess.run(
                ["git", "status", "--porcelain", "--untracked-files=all"],
                check=True, capture_output=True, text=True,
            ).stdout.strip():
                parser.error("Commit project changes before freezing the model.")
            inputs = {
                "matchups": args.matchups,
                "defensive_history": args.defense,
                "rating_history": args.ratings,
                "recent_history": args.recent,
                "identified_fights": args.fights,
                "identified_stats": args.stats,
                "registry": args.registry,
            }
            report = freeze_model(inputs, args.reference, args.output, commit)
            print(f"Frozen research recipe: {args.output}")
            print(f"Training bouts: {report['training_bouts']}")
            print(f"Model SHA-256: {report['model_sha256']}")
        else:
            batch = record_generated_forecasts(
                args.schedule, args.features, args.frozen,
                args.registry, args.output_root,
            )
            print(f"Recorded replay-verified forecasts: {batch}")
            print("Externally timestamp the batch hashes before scheduled bouts.")
    except (ValueError, OSError) as error:
        parser.error(str(error))


if __name__ == "__main__":
    main()
