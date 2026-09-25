"""Run the fixed opponent-adjusted study on accepted development folds."""

import argparse
import subprocess
from pathlib import Path

from upset.modeling.opponent_adjusted import (
    CANDIDATE,
    REFERENCE,
    export_opponent_adjusted,
)


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
        "reference": base / "experiments/recent_form_v1",
        "output": base / "experiments/opponent_adjusted_v1",
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
        parser.error("Commit project changes before running this experiment.")
    try:
        report = export_opponent_adjusted(
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
        f"Adjusted rows independently audited: {report['adjusted_audit']['all_adjusted_rows_checked']}"
    )
    print("All 12 accepted reference probability series: preserved exactly")
    print("Matched logistic refit: within 1e-12 in every fold")
    print(
        f"Decisive bouts: {report['decisive_bouts']}; Draw/NC excluded: {report['draw_nc_exclusions']}"
    )
    for label, scores in [
        ("POOLED", report["pooled"]),
        *((fold["name"], fold["scores"]) for fold in report["folds"]),
    ]:
        print(f"\n{label}")
        print(
            f"{'Variant':44} {'Correct':>9} {'Accuracy':>9} {'Log loss':>10} {'Brier':>10}"
        )
        for name in (REFERENCE, CANDIDATE):
            score = scores[name]
            count = f"{score['correct_bouts']}/{score['decisive_bouts']}"
            print(
                f"{name:44} {count:>9} {score['accuracy']:>8.2%} "
                f"{score['log_loss']:>10.6f} {score['brier_score']:>10.6f}"
            )
    print("\nPaired new-minus-reference differences (accuracy in percentage points)")
    for name, pair in report["paired_comparison"].items():
        interval = pair["date_cluster_bootstrap_95_percent"]
        a, b = interval["accuracy_delta"]
        lo, hi = interval["log_loss_delta"]
        print(
            f"{name}: accuracy {100 * pair['delta']['accuracy']:+.2f} "
            f"[{100 * a:+.2f}, {100 * b:+.2f}]; "
            f"log loss {pair['delta']['log_loss']:+.6f} [{lo:+.6f}, {hi:+.6f}]"
        )
    print("\nTen-bin ECE (descriptive; lower is better)")
    for name in (REFERENCE, CANDIDATE):
        print(f"{name}: {report['ten_bin_ece'][name]:.6f}")
    print(
        "\nExploratory development only; dates after 2023-08-19 not scored; no model promoted."
    )
    print("AUC, subgroups, symmetry, reliability bins and hashes are in the manifest.")


if __name__ == "__main__":
    main()
