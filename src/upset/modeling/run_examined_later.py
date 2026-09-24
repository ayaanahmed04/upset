"""Freeze forecasts, then score the examined 2023+ historical period."""

import argparse
import json
import subprocess
from pathlib import Path

from upset.modeling.examined_later import export_forecasts, score_forecasts


def _committed_code(parser: argparse.ArgumentParser) -> str:
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], check=True, capture_output=True, text=True
    ).stdout.strip()
    status = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=all"],
        check=True, capture_output=True, text=True,
    ).stdout
    if status.strip():
        parser.error("Commit tracked and untracked changes before this experiment.")
    return commit


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("forecast", "score"))
    base = Path("data/processed/kaggle_ufc_1994_2026")
    defaults = {
        "matchups": base / "prefight/matchups.jsonl",
        "defense": base / "prefight/defensive_history_v2.jsonl",
        "ratings": base / "prefight/rating_history_v1.jsonl",
        "recent": base / "prefight/recent_history_v1.jsonl",
        "fights": base / "identified/fights_identified.jsonl",
        "stats": base / "identified/fight_stats_identified.jsonl",
        "registry": Path("data/mappings/fighter_registry.json"),
        "reference": base / "experiments/recent_form_v1",
        "output": base / "experiments/examined_later_v1",
    }
    for name, path in defaults.items():
        parser.add_argument("--" + name, type=Path, default=path)
    args = parser.parse_args()
    commit = _committed_code(parser)
    try:
        if args.action == "forecast":
            report = export_forecasts(
                {
                    "matchups": args.matchups,
                    "defensive_history": args.defense,
                    "rating_history": args.ratings,
                    "recent_history": args.recent,
                    "identified_fights": args.fights,
                    "identified_stats": args.stats,
                    "registry": args.registry,
                },
                args.reference,
                args.output,
                commit,
            )
            print(f"Saved {report['forecast_bouts']} outcome-free forecasts")
            print(f"Forecast SHA-256: {report['forecasts_sha256']}")
            print("Scoring is separate; no outcomes or metrics saved in forecasts.")
        else:
            saved = json.loads(
                (args.output / "manifest.json").read_text(encoding="utf-8")
            )
            if saved.get("code_commit") != commit:
                parser.error("Checkout the original forecast code commit before scoring.")
            report = score_forecasts(
                args.output, args.matchups, args.fights, args.reference
            )
            print(f"Saved complete report: {args.output / 'scored/manifest.json'}")
            print(
                f"Examined period: {report['validation_bouts']} total; "
                f"{report['decisive_bouts']} decisive; "
                f"{report['draw_nc_exclusions']} Draw/NC excluded"
            )
            for name, score in report["pooled"].items():
                print(
                    f"{name}: {score['correct_bouts']}/{score['decisive_bouts']} "
                    f"({score['accuracy']:.2%}); log loss {score['log_loss']:.6f}; "
                    f"Brier {score['brier_score']:.6f}; AUC {score['roc_auc']:.6f}"
                )
            delta = report["paired"]["delta_recent_minus_comparator"]
            interval = report["paired"]["date_cluster_bootstrap_95_percent"]
            print(
                f"Recent minus comparator log loss {delta['log_loss']:+.6f} "
                f"(date-bootstrap 95% {interval['log_loss_delta']})"
            )
            for name, values in report["calibration"].items():
                print(
                    f"{name}: ten-bin ECE "
                    f"{values['ten_bin_expected_calibration_error']:.4f}"
                )
            print("Previously examined historical period; no model promotion.")
    except (ValueError, OSError) as error:
        parser.error(str(error))


if __name__ == "__main__":
    main()
