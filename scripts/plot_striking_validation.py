"""Plot a saved striking-validation report; no fitting or score selection."""

import argparse
import json
from pathlib import Path

import matplotlib

matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np


def coverage_panel(ax, summaries, names, title):
    ax.axvspan(87, 93, color='#e0eee8', zorder=0)
    ax.axvline(90, color='#638574', ls='--', lw=1)
    for i, summary in enumerate(summaries):
        stats = summary['levels']['0.9']['randomized_pit_coverage']
        mean = stats['mean'] * 100
        interval = stats['interval_95']
        color = '#186b92' if summary['levels']['0.9']['status'] == 'within_band_all_seeds' else '#b86235'
        if interval is not None:
            ax.plot(np.array(interval)*100, [i, i], color=color, lw=2)
        ax.scatter([mean], [i], c=color, s=35, zorder=3)
        ax.annotate(f'{mean:.1f}%', (mean, i), xytext=(0, 10), textcoords='offset points',
                    ha='center', fontsize=9)
    ax.set_yticks(range(len(names)), names)
    ax.set_ylim(len(names)-.35, -.6)
    values = [s['levels']['0.9']['randomized_pit_coverage']['mean']*100 for s in summaries]
    ax.set_xlim(max(0, min(values+[87])-8), min(100, max(values+[93])+5))
    ax.set_xlabel('Central 90% randomized-PIT coverage (%)')
    ax.set_title(title, loc='left', fontweight='bold', pad=17)


def render(report_path, output):
    if output.exists():
        raise ValueError('Use a new figure output directory.')
    report = json.loads(report_path.read_text())
    reference = report['tuning_2012_2018']['selected_simple_reference']
    keys = ['binomial:sample_adjusted', 'history_beta_binomial:sample_adjusted',
            'bout_beta_binomial:sample_adjusted', 'bout_beta_binomial:'+reference]
    names = ['Fixed mean / binomial', 'History uncertainty', 'Bout variation', 'Reference / bout variation']
    groups = [report['primary_predictive_distributions'][key] for key in keys]
    plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 10,
                         'axes.spines.top': False, 'axes.spines.right': False})
    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    fig.suptitle('Significant-strike accuracy: development validation',
                 x=.035, ha='left', y=.985, fontsize=17, fontweight='bold')
    fig.text(.035, .94, f"{report['coverage']['common_support']:,} comparable fighter-bouts · "
             'fixed k=500 means · 2019 onward, through October 24, 2026', color='#526072')
    values = [g['mean_predictive_nll'] for g in groups]
    ax = axes[0, 0]
    ax.barh(range(4), values, height=.55, color=['#abb8c5', '#7895ad', '#186b92', '#699b87'])
    ax.set_yticks(range(4), names)
    ax.invert_yaxis()
    ax.set_xlim(0, max(values)*1.2)
    ax.set_xlabel('Conditional predictive NLL per fighter-bout (lower is better)')
    ax.set_title('Predictive distributions', loc='left', fontweight='bold', pad=17)
    for i, value in enumerate(values):
        ax.text(value+max(values)*.02, i, f'{value:.3f}', va='center', fontsize=9)
    coverage_panel(axes[0, 1], groups, names, 'Overall count calibration')
    by_attempts = report['subgroups']['actual_attempts']
    order = [key for key in ('1-24', '25-49', '50-99', '100-199', '200+') if key in by_attempts]
    summaries = [by_attempts[key]['candidate_bout_calibration'] for key in order]
    labels = [f"{key} attempts (n={by_attempts[key]['point_scores']['side_bouts']:,})" for key in order]
    coverage_panel(axes[1, 0], summaries, labels, 'Bout model by actual attempts')
    ax = axes[1, 1]
    halves = [2, 3, 5, 8, 10]
    for metric, offset, color in [('pearson', -.12, '#186b92'), ('spearman', .12, '#699b87')]:
        xs, ys = [], []
        for position, half in enumerate(halves):
            summary = report['repeatability'][str(half)]['primary_100_attempts_per_half']
            value = summary[metric]['correlation']
            if value is None:
                continue
            x = position+offset
            xs.append(x)
            ys.append(value)
            interval = summary[metric]['fighter_bootstrap_95_interval']
            if interval is not None:
                ax.plot([x, x], interval, color=color, lw=1.7)
        ax.plot(xs, ys, 'o-', ms=4, color=color, label=metric.title(), lw=1)
    ax.set_xticks(range(len(halves)), [f"{half}\n(n={report['repeatability'][str(half)]['primary_100_attempts_per_half']['fighters']:,})"
                                     for half in halves], fontsize=9)
    ax.set_ylim(-.05, 1.0)
    ax.axhline(0, color='#b7bfc7', lw=1)
    ax.set_xlabel('Recorded bouts per half\nComplete counts; 100+ attempts in each half', fontsize=9)
    ax.set_ylabel('First-half versus second-half correlation')
    ax.set_title('Descriptive repeatability', loc='left', fontweight='bold', pad=17)
    ax.legend(frameon=False, loc='upper left')
    fig.text(.035, .075, 'Green band: declared 87–93% diagnostic range. Count-calibration error bars resample dates; correlation bars resample fighters.',
             color='#526072', fontsize=9)
    fig.text(.035, .043, 'Historical development evidence only. Conditional on actual attempts; no opponent adjustment or public skill release.',
             color='#526072', fontsize=9)
    fig.subplots_adjust(left=.22, right=.975, top=.87, bottom=.18, wspace=.82, hspace=.75)
    output.mkdir(parents=True)
    for extension in ('png', 'pdf'):
        fig.savefig(output/('validation_summary.'+extension), dpi=180, facecolor='white')
    plt.close(fig)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    render(args.report, args.output)
