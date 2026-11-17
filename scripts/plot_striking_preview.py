"""Static repair-study figure generated only from retained study reports."""

import json
from pathlib import Path

import matplotlib

matplotlib.use('Agg')
import matplotlib.pyplot as plt


def main():
    root = Path(__file__).resolve().parents[1]
    processed = root/'data/processed'
    fixed = json.loads((processed/'striking_adaptation_2026_11_04_v1/report.json').read_text())
    rolling = json.loads((processed/'striking_rolling_2026_11_04_v1/report.json').read_text())
    output = root/'docs/assets/striking_preview_2026_11_04_v1'
    output.mkdir(parents=True, exist_ok=True)
    labels = ['Original', 'Fixed correction', 'Rolling correction']
    scores = [rolling['point_scores']['sample_adjusted']['binomial_nll'],
              fixed['point_scores']['recent_calibrated']['binomial_nll'],
              rolling['point_scores']['recent_calibrated']['binomial_nll']]
    # Original bias is independently calculated from retained original predictions.
    predictions = [json.loads(line) for line in
                   (processed/'striking_rolling_2026_11_04_v1/predictions.jsonl').read_text().splitlines()]
    keys = {(r['fight_id'], r['fighter_id']) for r in
            map(json.loads, (processed/'striking_rolling_2026_11_04_v1/calibration_rows.jsonl').read_text().splitlines())}
    rows = [r for r in predictions if (r['fight_id'], r['fighter_id']) in keys]
    bias = 100*sum(r['attempts']*r['sample_adjusted']-r['landed'] for r in rows)/sum(r['attempts'] for r in rows)
    biases = [bias, fixed['decision']['mean_bias_percentage_points_predicted_minus_observed'],
              rolling['decision']['mean_bias_percentage_points_predicted_minus_observed']]
    colors = ['#697586', '#c5882f', '#188477']
    fig, axes = plt.subplots(1, 2, figsize=(10, 4.7), layout='constrained')
    fig.suptitle('Striking estimate: experimental preview progress', fontsize=15, weight='bold')
    axes[0].bar(labels, scores, color=colors)
    axes[0].set(ylabel='Binomial NLL per fighter-bout (lower is better)', ylim=(0, 5.2), title='Point score on the same 7,028 observations')
    for i, v in enumerate(scores):
        axes[0].text(i, v+.08, f'{v:.3f}', ha='center')
    axes[1].axhspan(-1, 1, alpha=.12, color='#188477', label='Separate preview bias gate')
    axes[1].axhline(0, color='#697586', linewidth=.8)
    axes[1].bar(labels, biases, color=colors)
    axes[1].set(ylabel='Predicted minus observed accuracy (percentage points)', ylim=(-2.5, 1.5), title='Attempt-weighted average accuracy gap')
    for i, v in enumerate(biases):
        axes[1].text(i, v+(.1 if v >= 0 else -.25), f'{v:+.2f} pp', ha='center')
    axes[1].legend(loc='upper left', frameon=False, fontsize=8)
    for ax in axes:
        ax.spines[['top', 'right']].set_visible(False)
        ax.tick_params(axis='x', labelsize=9)
    fig.supxlabel('Reused development evidence, 2019–Oct 24, 2026. Mean-only local preview; uncertainty checks still fail.', fontsize=9)
    for extension in ('png', 'pdf'):
        path = output/('preview_progress.'+extension)
        if path.exists():
            raise ValueError('Use a new figure output path.')
        fig.savefig(path, dpi=180)
    plt.close(fig)


if __name__ == '__main__':
    main()
