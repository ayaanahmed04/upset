"""Run the fixed symmetry/recent-performance study on the preserved cohort."""

import argparse
import subprocess
from pathlib import Path

from upset.modeling.recent_form import NEW_VARIANTS, export_recent_form


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    base = Path("data/processed/kaggle_ufc_1994_2026")
    for name, default in {
        "matchups": base / "prefight/matchups.jsonl",
        "defense": base / "prefight/defensive_history_v2.jsonl",
        "ratings": base / "prefight/rating_history_v1.jsonl",
        "recent": base / "prefight/recent_history_v1.jsonl",
        "fights": base / "identified/fights_identified.jsonl",
        "stats": base / "identified/fight_stats_identified.jsonl",
        "registry": Path("data/mappings/fighter_registry.json"),
        "reference": base / "experiments/elo_comparison_v1",
        "output": base / "experiments/recent_form_v1",
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
        report = export_recent_form(
            args.matchups,
            args.defense,
            args.ratings,
            args.recent,
            args.fights,
            args.stats,
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
        f"Recent rows independently audited: {report['recent_audit']['all_recent_rows_checked']}"
    )
    print(
        f"Decisive bouts: {report['decisive_bouts']}; Draw/NC excluded: {report['draw_nc_exclusions']}"
    )
    print("All six original Elo-study forward/reverse probabilities: preserved exactly")
    for label, scores in [
        ("POOLED", report["pooled"]),
        *((fold["name"], fold["scores"]) for fold in report["folds"]),
    ]:
        print(f"\n{label}")
        print(
            f"{'Variant':38} {'Correct':>9} {'Accuracy':>9} {'Log loss':>10} {'Brier':>10}"
        )
        for name, score in scores.items():
            count = f"{score['correct_bouts']}/{score['decisive_bouts']}"
            print(
                f"{name:38} {count:>9} {score['accuracy']:>8.2%} "
                f"{score['log_loss']:>10.6f} {score['brier_score']:>10.6f}"
            )
    print(
        "\nPaired differences: accuracy in percentage points; log loss lower is better"
    )
    for name, pair in report["paired_comparisons"].items():
        interval = pair["date_cluster_bootstrap_95_percent"]
        a, b = interval["accuracy_delta"]
        lo, hi = interval["log_loss_delta"]
        print(
            f"{name}: accuracy {100 * pair['delta']['accuracy']:+.2f} "
            f"[{100 * a:+.2f}, {100 * b:+.2f}]; "
            f"log loss {pair['delta']['log_loss']:+.6f} [{lo:+.6f}, {hi:+.6f}]"
        )
    print("\nFinal probability symmetry (raw diagnostics are also saved)")
    for name in NEW_VARIANTS:
        diagnostic = report["symmetry"][name]
        print(
            f"{name}: max error {diagnostic['maximum_absolute_error']:.3g}; "
            f"conflicting picks {diagnostic['conflicting_winner_picks']}; "
            f"exact ties {diagnostic['exact_forward_ties']}"
        )
    print("\nExploratory development results; no model promoted.")
    print(
        "AUC, reliability bins, history/missingness/division slices and hashes are in the manifest."
    )


if __name__ == "__main__":
    main()
