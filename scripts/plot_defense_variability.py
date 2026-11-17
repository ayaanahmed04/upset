"""Render the v3 diagnostic figure from the saved report; no model fitting."""

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
    primary = report['primary_common_support']
    plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 10,
                         'axes.spines.top': False, 'axes.spines.right': False})
    fig, axes = plt.subplots(1, 3, figsize=(15, 5.8),
                             gridspec_kw={'width_ratios': [1, 1.1, 1.2]})
    fig.suptitle('Fight variability improves predictions; high-attempt bouts remain too broad',
                 x=.035, y=.98, ha='left', fontsize=16, fontweight='bold')
    fig.text(.035, .92, '4,197 comparable fighter-side observations · frozen defense means · development evidence only',
             fontsize=10, color='#586173')
    names = ['Global binomial', 'Global posterior', 'Fight-varying model']
    families = ['global_binomial', 'global_stationary_posterior', 'global_bout_variability']
    values = [primary['families'][f]['mean_predictive_nll'] for f in families]
    y = np.arange(3)
    axes[0].barh(y, values, color=['#abb7c6', '#39669c', '#167d76'], height=.58)
    axes[0].invert_yaxis()
    axes[0].set_yticks(y, names)
    axes[0].set_xlim(0, 1.65)
    axes[0].set_xlabel('Predictive NLL per fighter-bout\n(lower is better)')
    axes[0].set_title('Predictive scores improve', loc='left', fontsize=11, pad=14)
    for yy, value in zip(y, values, strict=True):
        axes[0].text(value+.025, yy, f'{value:.4f}', va='center', fontsize=9)
    panels = [
        (1, [primary['families'][f] for f in families], names, 'Overall 90% check is in band'),
        (2, [report['subgroups']['actual_attempts'][k]['families']['global_bout_variability']
             for k in ['1', '2-3', '4-9', '10+']],
         ['1 attempt (n=1,070)', '2-3 attempts (n=1,190)',
          '4-9 attempts (n=1,486)', '10+ attempts (n=451)'],
         'High-attempt bouts miss the band'),
    ]
    for index, groups, labels, title in panels:
        ax = axes[index]
        stats = [g['levels']['0.9']['randomized_pit_coverage'] for g in groups]
        means = np.array([s['mean']*100 for s in stats])
        lows = np.array([s['interval_95'][0]*100 for s in stats])
        highs = np.array([s['interval_95'][1]*100 for s in stats])
        yy = np.arange(len(stats))
        ax.axvspan(87, 93, color='#dbe9e4', alpha=.85)
        ax.axvline(90, color='#557368', ls='--', lw=1)
        for i in range(len(stats)):
            color = '#a75f27' if index == 2 and i == 3 else '#167d76' if index == 2 or i == 2 else '#39669c'
            ax.errorbar([means[i]], [yy[i]], xerr=[[means[i]-lows[i]], [highs[i]-means[i]]],
                        fmt='o', capsize=4, color=color)
            ax.text(means[i], yy[i]+.22, f'{means[i]:.1f}%', ha='center', fontsize=9)
        ax.set_yticks(yy, labels)
        ax.set_ylim(len(stats)-.35, -.65)
        ax.set_xlim(79 if index == 1 else 84, 99)
        ax.set_xlabel('Discreteness-adjusted 90% calibration (%)')
        ax.set_title(title, loc='left', fontsize=11, pad=14)
    fig.subplots_adjust(left=.15, right=.985, top=.79, bottom=.31, wspace=.85)
    fig.text(.035, .11, 'Green bands: predeclared 87-93% diagnostic range. Error bars: 95% whole-date bootstrap intervals.',
             fontsize=9, color='#586173')
    fig.text(.035, .065, 'Calibration uses randomized PIT for integer counts. Defense-rate means are unchanged; the site remains raw with no rankings.',
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
