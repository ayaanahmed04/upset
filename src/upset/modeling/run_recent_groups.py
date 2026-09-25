"""Run the pinned recent-performance group ablation on development fights."""

import argparse
import json
import subprocess
from pathlib import Path

from upset.modeling.recent_groups import export_recent_groups


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    base = Path("data/processed/kaggle_ufc_1994_2026")
    defaults = {
        "matchups": base / "prefight/matchups.jsonl",
        "defensive_history": base / "prefight/defensive_history_v2.jsonl",
        "rating_history": base / "prefight/rating_history_v1.jsonl",
        "recent_history": base / "prefight/recent_history_v1.jsonl",
        "identified_fights": base / "identified/fights_identified.jsonl",
        "identified_stats": base / "identified/fight_stats_identified.jsonl",
        "registry": Path("data/mappings/fighter_registry.json"),
    }
    for name, path in defaults.items():
        parser.add_argument("--" + name.replace("_", "-"), type=Path, default=path)
    parser.add_argument("--reference", type=Path,
                        default=base / "experiments/recent_form_v1")
    parser.add_argument("--output", type=Path,
                        default=base / "experiments/recent_groups_v1")
    args = parser.parse_args()
    status = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=all"], check=True,
        capture_output=True, text=True,
    ).stdout
    if status.strip():
        parser.error("Commit project changes before running the study.")
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], check=True, capture_output=True, text=True,
    ).stdout.strip()
    try:
        report = export_recent_groups(
            {name: getattr(args, name) for name in defaults}, args.reference,
            args.output, commit,
        )
    except (ValueError, OSError) as error:
        parser.error(str(error))
    print(f"Saved report: {args.output / 'manifest.json'}")
    print(f"Code commit: {report['code_commit']}")
    print(f"Development bouts: {report['validation_bouts']}; "
          f"Draw/NC excluded: {report['draw_nc_exclusions']}")
    print("Reference refit errors: " + json.dumps({
        f["name"]: f["matched_reference_refit_maximum_absolute_error"]
        for f in report["folds"]
    }))
    for name in report["variants"]:
        score = report["pooled"][name]
        print(f"{name}: {score['correct_bouts']}/{score['decisive_bouts']} "
              f"({score['accuracy']:.2%}), log loss {score['log_loss']:.6f}, "
              f"Brier {score['brier_score']:.6f}")
    for name, comparison in report["paired_comparisons"].items():
        delta = comparison["delta"]
        interval = comparison["date_cluster_bootstrap_95_percent"]
        print(f"{name}: accuracy {delta['accuracy']:+.2%} "
              f"{interval['accuracy_delta']}, "
              f"log loss {delta['log_loss']:+.6f} "
              f"{interval['log_loss_delta']}")
    print("Exploratory development only; no later-date results or model promotion.")


if __name__ == "__main__":
    main()
