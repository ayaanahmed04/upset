"""Plot the preserved chronological pilot report without refitting models."""

import argparse
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError("Use a new figure path.")
    report = json.loads(args.report.read_text())
    primary = report["development_2018"]["primary"]
    colors = {"global25": "#177b73", "defense_only": "#73869c", "opponent": "#ad6025", "raw_career": "#a5aeb8"}
    models = ("global25", "defense_only", "opponent", "raw_career")
    labels = ("Global shrink25", "Defense only", "Opponent adjusted", "Raw career")
    plt.rcParams.update({"font.size": 11, "axes.spines.top": False, "axes.spines.right": False})
    fig, axes = plt.subplots(1, 2, figsize=(13.5, 5.8), gridspec_kw={"width_ratios": [1, 1.3]})
    fig.subplots_adjust(left=.16, right=.98, top=.74, bottom=.29, wspace=.55)
    fig.text(.04, .94, "Opponent adjustment did not clear the pilot's proceed gate", fontsize=18, weight="bold")
    fig.text(.04, .88, f"2018 development diagnostic · {primary['side_bouts']} matched sides · {primary['date_clusters']} dates · annual snapshots", color="#586779")
    ax = axes[0]
    for y, (model, label) in enumerate(zip(models, labels, strict=True)):
        score = primary["models"][model]["mean_predictive_nll"]
        ax.scatter(score, y, color=colors[model], s=60, zorder=3)
        ax.annotate(f"{score:.5f}", (score, y), xytext=(8, -4), textcoords="offset points")
    ax.set_yticks(range(4), labels)
    ax.invert_yaxis()
    ax.set_ylim(3.5, -.5)
    ax.set_xlim(1.285, 1.80)
    ax.set_xlabel("Mean predictive NLL (lower is better)")
    ax.set_title("Global shrinkage has the lowest observed NLL", fontsize=11, pad=17)
    ax = axes[1]
    schemes = (("date_bootstrap", -.13, "#177b73", "Date bootstrap"),
               ("fighter_sensitivity", .13, "#73869c", "Fighter-weight sensitivity"))
    for i, reference in enumerate(("global25", "defense_only")):
        for scheme, shift, color, label in schemes:
            summary = primary["opponent_minus_reference"][reference]["nll"][scheme]
            mean = summary["mean"]
            low, high = summary["interval_95"]
            ax.errorbar(mean, i+shift, xerr=np.array([[mean-low], [high-mean]]),
                        fmt="o", color=color, capsize=4, label=label if i == 0 else None)
    ax.axvline(0, color="#9aa4b0", linestyle="--", linewidth=1)
    ax.set_yticks([0, 1], ["Opponent − shrink25", "Opponent − defense only"])
    ax.set_ylim(1.5, -.5)
    ax.set_xlabel("Paired NLL difference with 95% intervals")
    ax.set_title("Neither comparison shows a clear improvement", fontsize=11, pad=17)
    ax.legend(frameon=False, loc="upper right", fontsize=9)
    fig.text(.04, .15, "Penalties selected on 2012–2017: 4 for both models. Both paired NLL intervals include zero.", color="#586779", fontsize=10)
    fig.text(.04, .095, "Calibration is inconclusive on 381 primary sides (<500 required). Previously inspected development data; no public release.", color="#586779", fontsize=10)
    fig.text(.04, .045, "The earlier numerical failures and stopping-tolerance amendment are preserved. No larger backfill was run.", color="#586779", fontsize=10)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(args.output, dpi=180, facecolor="white")
    plt.close(fig)


if __name__ == "__main__":
    main()
