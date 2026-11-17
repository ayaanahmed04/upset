"""Plot matched development checks from the retained overall-rating artifact."""

import hashlib
import json
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import PercentFormatter


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    root = Path(__file__).resolve().parents[1]
    folder = root/"data/processed/overall_rating_2026_11_04_v1"
    manifest = json.loads((folder/"manifest.json").read_text())
    for name in ("evaluation.json", "development.jsonl"):
        if digest(folder/name) != manifest["output_sha256"][name]:
            raise ValueError("Retained rating artifact differs: " + name)
    report = json.loads((folder/"evaluation.json").read_text())
    rows = [json.loads(line) for line in (folder/"development.jsonl").read_text().splitlines()]
    if not len(rows) == report["support"]["matched_bouts"] == report["candidate"]["bouts"] == report["resume_only"]["bouts"] == 3149:
        raise ValueError("The two panels must use the same 3,149 matched bouts.")
    candidate, resume = report["candidate"], report["resume_only"]
    nll = [candidate["nll"], resume["nll"], report["coin_flip_nll"]]
    accuracies = [candidate["ordering_accuracy_with_half_ties"],
                  resume["ordering_accuracy_with_half_ties"], report["coin_flip_ordering_accuracy"]]
    ordering = {"candidate": [], "resume": []}
    for row in rows:
        winner_a = row["winner_id"] == row["fighter_ids"][0]
        candidate_edge = row["candidate_probability_a"]-.5
        resume_edge = row["parts"][0]["resume"]-row["parts"][1]["resume"]
        for key, edge in (("candidate", candidate_edge), ("resume", resume_edge)):
            ordering[key].append(.5 if edge == 0 else float((edge > 0) == winner_a))
    checks = [(np.mean([r["candidate_nll"] for r in rows]), nll[0]),
              (np.mean([r["resume_nll"] for r in rows]), nll[1]),
              (np.mean(ordering["candidate"]), accuracies[0]),
              (np.mean(ordering["resume"]), accuracies[1])]
    if not all(np.isclose(actual, expected, atol=1e-12, rtol=0) for actual, expected in checks):
        raise ValueError("Saved development rows do not reproduce evaluation summaries.")

    labels = ["Four-part\nprototype", "Résumé\nonly", "Coin-flip\nreference"]
    colors = ["#c1121f", "#697586", "#c8cdd4"]
    fig, axes = plt.subplots(1, 2, figsize=(11.2, 5.5))
    fig.subplots_adjust(left=.07, right=.98, top=.76, bottom=.25, wspace=.3)
    fig.suptitle("UPSET overall rating: development checks", fontsize=16, weight="bold", y=.95)
    fig.text(.5, .87, "The same 3,149 decisive bouts in both panels; both fighters have earlier UFC history",
             ha="center", fontsize=10, color="#414b59")
    axes[0].bar(labels, nll, color=colors, width=.65)
    axes[0].set(title="Probability log loss · lower is better", ylabel="Mean negative log likelihood", ylim=(0, .78))
    axes[1].bar(labels, accuracies, color=colors, width=.65)
    axes[1].set(title="Correct ordering · higher is better", ylabel="Accuracy, with half credit for ties", ylim=(0, 1))
    axes[1].yaxis.set_major_formatter(PercentFormatter(1))
    for i, value in enumerate(nll):
        axes[0].text(i, value+.018, f"{value:.5f}", ha="center", fontsize=11)
    for i, value in enumerate(accuracies):
        axes[1].text(i, value+.025, f"{100*value:.2f}%", ha="center", fontsize=11)
    for ax in axes:
        ax.set_axisbelow(True)
        ax.grid(axis="y", color="#e8ebef", linewidth=.7)
        ax.spines[["top", "right"]].set_visible(False)
        ax.spines[["left", "bottom"]].set_color("#a2aab5")
        ax.tick_params(axis="x", length=0, pad=10, labelsize=10)
        ax.tick_params(axis="y", labelsize=9)
        ax.title.set_fontsize(11)
    fig.text(.5, .07,
             "Already-inspected 2019–Oct 24, 2026 development data; not fresh future validation.\n"
             "Matched support excludes debut bouts. These panels evaluate the raw combined index, not the rounded display scores.",
             ha="center", va="center", fontsize=9, color="#414b59", linespacing=1.7)
    output = root/"docs/assets/overall_rating_2026_11_04_v1/development_checks.png"
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        raise ValueError("Use a new immutable figure output path.")
    fig.savefig(output, dpi=180, facecolor="white")
    plt.close(fig)
    print(output)


if __name__ == "__main__":
    main()
