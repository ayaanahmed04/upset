"""Plot the frozen v4 selection and known calibration limitation."""

import argparse
import json
from pathlib import Path

import matplotlib

matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np


def render(report_path, output):
    if output.suffix.lower() != '.png':
        raise ValueError('Use a PNG output path.')
    report = json.loads(report_path.read_text())
    candidates = report['training']['candidates']
    exponents = [0., .5, 1.]
    best = [min((r for r in candidates if r['gamma'] == g), key=lambda r: r['mean_predictive_nll']) for g in exponents]
    counts = [sum(r['bootstrap_selections'] for r in candidates if r['gamma'] == g) for g in exponents]
    plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 10,
                         'axes.spines.top': False, 'axes.spines.right': False})
    fig, axes = plt.subplots(1, 3, figsize=(15, 5.8), gridspec_kw={'width_ratios': [1.1, 1, 1.05]})
    fig.suptitle('Attempt-count scaling was not selected; keep the previous model as the reference',
                 x=.035, y=.98, ha='left', fontsize=16, fontweight='bold')
    fig.text(.035, .92, '18 predeclared candidates · 2012-2018 selection only · unchanged means and website',
             fontsize=10, color='#586173')
    y = np.arange(3)
    scores = [r['mean_predictive_nll'] for r in best]
    axes[0].scatter(scores, y, color=['#167d76', '#abb7c6', '#abb7c6'], s=55)
    axes[0].set_yticks(y, ['No scaling: gamma=0', 'Square root: gamma=0.5', 'Linear: gamma=1'])
    axes[0].invert_yaxis()
    axes[0].set_ylim(2.6, -.6)
    axes[0].set_xlim(min(scores)-.003, max(scores)+.004)
    axes[0].set_xlabel('Training predictive NLL (lower is better)')
    axes[0].set_title('Training prefers no scaling', loc='left', fontsize=11, pad=14)
    for xx, yy, candidate in zip(scores, y, best, strict=True):
        axes[0].text(xx, yy+.22, f'{xx:.4f} (c={candidate["c"]})', ha='center', fontsize=9)
    axes[1].barh(y, np.array(counts)/10, color=['#167d76', '#abb7c6', '#abb7c6'], height=.58)
    axes[1].set_yticks(y, ['gamma=0', 'gamma=0.5', 'gamma=1'])
    axes[1].invert_yaxis()
    axes[1].set_xlim(0, 105)
    axes[1].set_xlabel('Selection in training bootstrap resamples (%)')
    axes[1].set_title('Selection uncertainty is recorded', loc='left', fontsize=11, pad=14)
    for yy, value in zip(y, counts, strict=True):
        axes[1].text(value/10+2, yy, f'{value}/1000', va='center', fontsize=9)
    summary = report['subgroups']['actual_attempts']['10+']['families']
    stats = [summary[m]['levels']['0.9']['randomized_pit_coverage'] for m in
             ['global_bout_variability', 'attempt_scaled_variability']]
    means = np.array([s['mean']*100 for s in stats])
    low = np.array([s['interval_95'][0]*100 for s in stats])
    high = np.array([s['interval_95'][1]*100 for s in stats])
    axes[2].axvspan(87, 93, color='#dbe9e4', alpha=.85)
    axes[2].axvline(90, color='#557368', ls='--', lw=1)
    axes[2].errorbar(means, [0, 1], xerr=[means-low, high-means], fmt='o', color='#a75f27', capsize=4)
    axes[2].set_yticks([0, 1], ['Frozen v3', 'Selected v4'])
    axes[2].set_ylim(1.6, -.6)
    axes[2].set_xlim(84, 99)
    axes[2].set_xlabel('90% PIT check in 10+ attempt bouts (%)')
    axes[2].set_title('Known high-attempt issue remains', loc='left', fontsize=11, pad=14)
    for i, value in enumerate(means):
        axes[2].text(value, i+.22, f'{value:.1f}%', ha='center', fontsize=9)
    fig.subplots_adjust(left=.16, right=.985, top=.79, bottom=.31, wspace=.8)
    fig.text(.035, .11, 'Bootstrap selection frequencies are not posterior probabilities. Calibration band: 87-93%; error bars: 95% date-cluster intervals.',
             fontsize=9, color='#586173')
    fig.text(.035, .065, '2019+ is repeatedly inspected development data. No alternative was chosen because it looked better on those later outcomes; no public release.',
             fontsize=9, color='#586173')
    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output, dpi=180, facecolor='white')
    plt.close(fig)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    render(args.report, args.output)
