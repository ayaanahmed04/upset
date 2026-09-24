"""Record or verify supplied pre-event forecasts; do not fit a model."""

import argparse
import json
from pathlib import Path

from upset.modeling.prospective_archive import (
    record_forecast_batch,
    verify_forecast_batch,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    record = commands.add_parser("record")
    record.add_argument("--schedule", type=Path, required=True)
    record.add_argument("--forecasts", type=Path, required=True)
    record.add_argument("--model-spec", type=Path, required=True)
    record.add_argument("--model-artifact", type=Path, required=True)
    record.add_argument(
        "--registry", type=Path, default=Path("data/mappings/fighter_registry.json")
    )
    record.add_argument(
        "--output-root", type=Path, default=Path("data/processed/prospective")
    )
    verify = commands.add_parser("verify")
    verify.add_argument("batch", type=Path)
    args = parser.parse_args()
    if args.command == "record":
        batch = record_forecast_batch(
            args.schedule, args.forecasts, args.model_spec,
            args.model_artifact, args.registry, args.output_root,
        )
        print(f"Saved locked prospective batch: {batch}")
        print(json.dumps(verify_forecast_batch(batch), indent=2))
    else:
        print(json.dumps(verify_forecast_batch(args.batch), indent=2))


if __name__ == "__main__":
    main()
