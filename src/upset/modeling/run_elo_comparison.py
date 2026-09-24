"""Run six predeclared models on identical chronological development bouts."""

import argparse
import subprocess
from pathlib import Path

from upset.modeling.elo_comparison import export_elo_comparison


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    base = Path("data/processed/kaggle_ufc_1994_2026")
    for name, default in {
        "matchups": base / "prefight/matchups.jsonl",
        "defense": base / "prefight/defensive_history_v2.jsonl",
        "ratings": base / "prefight/rating_history_v1.jsonl",
        "fights": base / "identified/fights_identified.jsonl",
        "registry": Path("data/mappings/fighter_registry.json"),
        "reference": base / "experiments/defense_ablation_v1",
        "output": base / "experiments/elo_comparison_v1",
    }.items():
        parser.add_argument("--" + name, type=Path, default=default)
    args = parser.parse_args()
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], check=True, capture_output=True, text=True
    ).stdout.strip()
    status = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=all"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    if status.strip():
        parser.error(
            "Commit tracked and untracked project changes before this experiment."
        )
    try:
        report = export_elo_comparison(
            args.matchups,
            args.defense,
            args.ratings,
            args.fights,
            args.registry,
            args.reference,
            args.output,
            commit,
        )
    except (ValueError, OSError) as error:
        parser.error(str(error))
    print(f"Saved complete report: {args.output / 'manifest.json'}")
    print(f"Code commit: {report['code_commit']}")
    print(
        f"Rating rows independently audited: {report['rating_audit']['all_rating_rows_checked']}"
    )
    print(
        f"Decisive bouts: {report['decisive_bouts']}; Draw/NC excluded: {report['draw_nc_exclusions']}"
    )
    print("Saved baseline and full-defense probabilities: preserved")
    for label, scores in [
        ("POOLED", report["pooled"]),
        *((fold["name"], fold["scores"]) for fold in report["folds"]),
    ]:
        print(f"\n{label}")
        print(
            f"{'Variant':30} {'Correct':>9} {'Accuracy':>9} {'Log loss':>10} {'Brier':>10}"
        )
        for name, score in scores.items():
            count = f"{score['correct_bouts']}/{score['decisive_bouts']}"
            print(
                f"{name:30} {count:>9} {score['accuracy']:>8.2%} "
                f"{score['log_loss']:>10.6f} {score['brier_score']:>10.6f}"
            )
    print(
        "\nPaired accuracy differences (percentage points; date-bootstrap 95% interval)"
    )
    for name, pair in report["paired_comparisons"].items():
        lo, hi = pair["date_cluster_bootstrap_95_percent"]["accuracy_delta"]
        print(
            f"{name}: {100 * pair['delta']['accuracy']:+.2f} "
            f"[{100 * lo:+.2f}, {100 * hi:+.2f}]"
        )
    print("\nExploratory development results; no model promoted.")
    print(
        "AUC, probability intervals, subgroups, symmetry and reliability bins are in the manifest."
    )


if __name__ == "__main__":
    main()
