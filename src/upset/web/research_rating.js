/* UPSET rating presentation. Fictional examples never become fighter ratings. */
(function (root, factory) {
  const api = factory(root);
  if (typeof module === 'object' && module.exports) module.exports = api;
  root.UPSETRating = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function (root) {
  'use strict';
  let serial = 0;
  function el(tag, attrs = {}, ...children) {
    const node = root.document.createElement(tag);
    for (const [key, value] of Object.entries(attrs)) {
      if (key === 'text') node.textContent = value;
      else if (key === 'class') node.className = value;
      else node.setAttribute(key, value);
    }
    for (const child of children.flat()) if (child != null) node.append(typeof child === 'string' ? root.document.createTextNode(child) : child);
    return node;
  }
  function svg(tag, attrs, ...children) {
    const node = root.document.createElementNS('http://www.w3.org/2000/svg', tag);
    for (const [key, value] of Object.entries(attrs)) node.setAttribute(key, value);
    node.append(...children);
    return node;
  }
  function toggle(button, panel, scrollOnOpen = false) {
    button.setAttribute('aria-controls', panel.id);
    button.setAttribute('aria-expanded', 'false');
    panel.hidden = true;
    button.addEventListener('click', () => {
      panel.hidden = !panel.hidden;
      button.setAttribute('aria-expanded', String(!panel.hidden));
      if (!panel.hidden && scrollOnOpen) panel.scrollIntoView?.({block: 'start'});
    });
  }
  const signed = value => value > 0 ? '+' + value : String(value);
  const rounded = value => Number.isInteger(value) ? String(value) : value.toFixed(1);
  const ordinal = value => value + ((value % 100 >= 11 && value % 100 <= 13) ? 'th' : ({1: 'st', 2: 'nd', 3: 'rd'}[value % 10] || 'th'));
  const LIVE_VERSIONS = new Map([
    ['upset_rating_experimental_v1', 'v1'],
    ['upset_rating_experimental_v2', 'v2'],
    ['upset_rating_experimental_v3', 'v3'],
    ['upset_rating_experimental_v4', 'v4'],
  ]);
  const finite = value => typeof value === 'number' && Number.isFinite(value);
  const grade = value => Number.isInteger(value) && value >= 60 && value <= 99;
  const holdResult = reason => reason === 'held_after_win' ? 'win' : reason === 'held_after_loss' ? 'loss' : null;
  const changeClass = change => change > 0 ? ' is-up' : change < 0 ? ' is-down' : '';
  function validProtectedUpdate(rating) {
    const unheld = rating.unheld_score, reason = rating.outcome_hold;
    if (rating.model.resume_weight !== .5 || !grade(unheld) ||
        unheld !== rating.curve_score + rating.small_history_adjustment + rating.change_adjustment) return false;
    if (reason == null) return unheld === rating.score;
    const outcome = holdResult(reason);
    return outcome !== null && rating.change === 0 && rating.previous_score === rating.score &&
      Array.isArray(rating.last_outcomes) && rating.last_outcomes.length > 0 &&
      rating.last_outcomes.every(result => result === outcome) &&
      (outcome === 'win' ? unheld < rating.score : unheld > rating.score);
  }
  function availableRating(report) {
    const rating = report.rating, keys = ['striking', 'wrestling', 'grappling', 'resume'];
    return !!rating && rating.status === 'available' && LIVE_VERSIONS.has(rating.version) &&
      rating.experimental === true && rating.validated === false &&
      grade(rating.score) &&
      Array.isArray(rating.parts) && rating.parts.length === 4 &&
      new Set(rating.parts.map(part => part.key)).size === 4 &&
      rating.parts.every(part => keys.includes(part.key) && finite(part.score) && part.score >= 60 && part.score <= 99 &&
        finite(part.raw_score) && part.raw_score >= 0 && part.raw_score <= 100 &&
        typeof part.label === 'string' && part.label.trim() && part.metrics && typeof part.metrics === 'object' && !Array.isArray(part.metrics)) &&
      rating.model && finite(rating.model.resume_weight) && rating.model.resume_weight >= 0 && rating.model.resume_weight <= 1 &&
      Array.isArray(rating.model.skill_weights) && rating.model.skill_weights.join(',') === '0.5,0.3,0.2' &&
      finite(rating.raw_combined) && finite(rating.skills_combined) && Array.isArray(rating.history) &&
      Number.isInteger(rating.bouts) && rating.bouts > 0 && Number.isInteger(rating.peak) && rating.peak >= rating.score && rating.peak <= 99 &&
      grade(rating.curve_score) &&
      finite(rating.curve_percentile) && rating.curve_percentile >= 0 && rating.curve_percentile <= 1 &&
      Number.isInteger(rating.small_history_adjustment) && Number.isInteger(rating.change_adjustment) &&
      (LIVE_VERSIONS.get(rating.version) === 'v1' || validProtectedUpdate(rating));
  }
  const INPUT_LABELS = {
    sig_landed_per_minute: 'Significant strikes landed / min', sig_absorbed_per_minute: 'Significant strikes absorbed / min',
    sig_differential_per_minute: 'Significant-strike difference / min', striking_accuracy: 'Striking accuracy',
    striking_defense: 'Striking defense', knockdowns_per_15_minutes: 'Knockdowns scored / 15 min',
    knockdowns_received_per_15_minutes: 'Knockdowns received / 15 min', ko_losses_per_bout: 'KO/TKO losses / bout',
    ko_wins_per_bout: 'KO/TKO wins / bout',
    takedowns_per_15_minutes: 'Takedowns landed / 15 min', takedown_accuracy: 'Takedown accuracy',
    takedown_defense: 'Takedown defense', control_share: 'Recorded control share',
    submission_attempts_per_15_minutes: 'Submission attempts / 15 min', submission_wins_per_bout: 'Submission wins / bout',
    submission_losses_per_opponent_attempt: 'Submission losses / opposing attempt',
    ground_strike_differential_per_minute: 'Ground-strike difference / min', elo: 'Chronological Elo',
  };
  function inputValue(key, value) {
    if (value == null || !finite(value)) return 'Not available';
    if (['striking_accuracy', 'striking_defense', 'takedown_accuracy', 'takedown_defense', 'control_share'].includes(key)) return (100 * value).toFixed(1) + '%';
    return key === 'elo' ? value.toFixed(1) : value.toFixed(2);
  }
  function ring(data, matchup) {
    const has = data.score != null;
    const provisional = data.bouts > 0 && data.bouts < 4;
    const tier = has ? Math.floor(data.score / 10) * 10 : null;
    const button = el('button', {type: 'button', class: 'rating-ring' + (has ? ' rating-tier-' + tier : ' rating-unrated') + (provisional ? ' is-provisional' : '') + (matchup ? ' is-matchup' : ''),
      'aria-label': has ? 'UPSET rating ' + data.score + ' out of 99. Show four-part breakdown' : 'No UPSET rating yet'});
    const points = '66,18 134,18 182,66 182,134 134,182 66,182 18,134 18,66';
    const circle = svg('polygon', {points, pathLength: 99, class: 'rating-ring-fill',
      'stroke-dasharray': has ? data.score + ' 99' : '0 99'});
    const graphic = svg('svg', {viewBox: '0 0 200 200', 'aria-hidden': 'true'});
    if (provisional) {
      const maskId = 'rating-dash-mask-' + (++serial);
      graphic.append(svg('defs', {}, svg('mask', {id: maskId},
        svg('polygon', {points, pathLength: 99, fill: 'none', stroke: 'white', 'stroke-width': 12, 'stroke-dasharray': '1 1'}))));
      circle.setAttribute('mask', 'url(#' + maskId + ')');
    }
    graphic.append(svg('polygon', {points, pathLength: 99, class: 'rating-ring-track'}), circle);
    button.append(graphic,
      el('span', {class: 'rating-ring-center', 'aria-hidden': 'true'},
        el('span', {class: 'rating-score distressed', text: has ? String(data.score) : '—'}),
        el('span', {class: 'rating-scale', text: has ? 'OUT OF 99' : 'NOT RATED'})));
    if (!has) button.disabled = true;
    return button;
  }
  function sparkline(history) {
    if (!history.length) return null;
    const scores = history.map(item => item.score), lo = Math.min(...scores) - 2, hi = Math.max(...scores) + 2;
    const x = i => 8 + i * 264 / Math.max(1, scores.length - 1);
    const y = value => 59 - (value - lo) / (hi - lo) * 48;
    const points = scores.map((value, i) => x(i) + ',' + y(value)).join(' ');
    return svg('svg', {class: 'rating-sparkline', viewBox: '0 0 280 72', role: 'img',
      'aria-label': 'Sample rating history: ' + scores.join(', ')},
      svg('line', {x1: 8, y1: 63, x2: 272, y2: 63, class: 'rating-sparkline-baseline'}),
      svg('polyline', {points, class: 'rating-sparkline-line'}),
      svg('circle', {cx: x(scores.length - 1), cy: y(scores.at(-1)), r: 4, class: 'rating-sparkline-end'}));
  }
  const historyDate = new Intl.DateTimeFormat('en-US', {month: 'short', day: 'numeric', year: 'numeric', timeZone: 'UTC'});
  const historyMonth = new Intl.DateTimeFormat('en-US', {month: 'short', year: 'numeric', timeZone: 'UTC'});
  function fightLabel(fight, includeMethod = false) {
    const result = fight.result_type || fight.outcome;
    const prefix = {win: 'Won vs. ', loss: 'Lost to ', nc: 'No contest vs. ', draw: 'Drew with ', other: 'Result vs. '}[result] || 'Vs. ';
    return prefix + fight.opponent + (includeMethod && fight.method && !['nc', 'draw'].includes(result) ? ' · ' + fight.method : '');
  }
  function ratingHistoryChart(history, fightsByDate, peak) {
    const points = history.filter(row => grade(row.score) && Number.isFinite(Date.parse(row.date)))
      .map(row => ({...row, time: Date.parse(row.date)}));
    if (!points.length) return null;
    const first = points[0], latest = points.at(-1), timespan = latest.time - first.time;
    const scores = points.map(point => point.score);
    const low = Math.max(60, Math.floor((Math.min(...scores) - 1) / 5) * 5);
    const high = Math.min(99, Math.max(low + 10, Math.ceil((peak + 1) / 5) * 5));
    const floor = Math.min(low, high - 10);
    const x = point => timespan ? 100 * (point.time - first.time) / timespan : 50;
    const y = value => 100 * (high - value) / (high - floor);
    const path = 'M ' + x(first) + ' ' + y(first.score) + points.slice(1)
      .map(point => ' H ' + x(point) + ' V ' + y(point.score)).join('');
    const axis = el('div', {class: 'rating-chart-y', 'aria-hidden': 'true'});
    const plot = el('div', {class: 'rating-chart-plot'});
    for (const tick of [high, Math.round((high + floor) / 2), floor]) {
      const position = 'top:' + y(tick) + '%';
      axis.append(el('span', {style: position, text: String(tick)}));
      plot.append(el('i', {class: 'rating-chart-gridline', style: position, 'aria-hidden': 'true'}));
    }
    plot.append(svg('svg', {viewBox: '0 0 100 100', preserveAspectRatio: 'none', 'aria-hidden': 'true'},
      svg('path', {d: path, class: 'rating-chart-line', 'vector-effect': 'non-scaling-stroke'})));
    const dateAxis = el('div', {class: 'rating-chart-x', 'aria-hidden': 'true'});
    if (!timespan) dateAxis.append(el('span', {class: 'rating-chart-mid', text: historyMonth.format(first.time)}));
    else {
      dateAxis.append(el('span', {text: historyMonth.format(first.time)}));
      if (timespan > 366 * 86400000) dateAxis.append(el('span', {class: 'rating-chart-mid',
        text: historyMonth.format((first.time + latest.time) / 2)}));
      dateAxis.append(el('span', {text: historyMonth.format(latest.time)}));
    }
    const detail = el('div', {class: 'rating-chart-detail', 'aria-live': 'polite', 'aria-atomic': 'true'});
    const older = el('button', {type: 'button', 'aria-label': 'Previous rating update', text: '‹'});
    const newer = el('button', {type: 'button', 'aria-label': 'Next rating update', text: '›'});
    let selected = points.length - 1;
    const markers = points.map((point, i) => {
      const fights = fightsByDate.get(point.date) || [];
      const label = historyDate.format(point.time) + ' · Rating ' + point.score +
        (fights.length === 1 ? ' · ' + fightLabel(fights[0]) : '');
      const marker = el('button', {type: 'button', class: 'rating-chart-point' + (point.score === peak ? ' is-peak' : ''),
        style: 'left:' + x(point) + '%;top:' + y(point.score) + '%', title: label,
        'aria-label': label, 'aria-pressed': 'false', tabindex: '-1'});
      marker.addEventListener('click', () => select(i));
      marker.addEventListener('keydown', event => {
        if (event.key !== 'ArrowLeft' && event.key !== 'ArrowRight') return;
        event.preventDefault();
        select(i + (event.key === 'ArrowLeft' ? -1 : 1));
        markers[selected].focus();
      });
      plot.append(marker);
      return marker;
    });
    function select(index) {
      if (index < 0 || index >= points.length) return;
      markers[selected].setAttribute('aria-pressed', 'false');
      markers[selected].setAttribute('tabindex', '-1');
      selected = index;
      markers[selected].setAttribute('aria-pressed', 'true');
      markers[selected].setAttribute('tabindex', '0');
      const point = points[index], hold = holdResult(point.outcome_hold);
      const fights = fightsByDate.get(point.date) || [];
      const labels = [historyDate.format(point.time), point.score === peak ? 'Career peak' : null,
        point === latest ? 'Latest update' : null].filter(Boolean);
      const movement = hold ? 'Held after ' + hold : point.change == null ? 'First rating' :
        point.change === 0 ? 'No change' : signed(point.change) + (Math.abs(point.change) === 1 ? ' point' : ' points');
      detail.replaceChildren(
        el('div', {class: 'rating-chart-detail-head'}, el('span', {text: labels.join(' · ')}),
          el('strong', {text: 'Rating ' + point.score + ' · ' + movement})),
        el('p', {text: fights.length ? fights.map(fight => fightLabel(fight, true)).join(' / ') : 'Recorded rating update'}));
      older.disabled = index === 0;
      newer.disabled = index === points.length - 1;
    }
    older.addEventListener('click', () => select(selected - 1));
    newer.addEventListener('click', () => select(selected + 1));
    select(selected);
    return el('div', {class: 'rating-chart', role: 'group', 'aria-label': 'Displayed rating by fight date'},
      el('div', {class: 'rating-chart-axes'}, axis, plot, dateAxis),
      el('div', {class: 'rating-chart-controls'}, detail,
        points.length > 1 ? el('div', {class: 'rating-chart-nav'}, older, newer) : null));
  }
  function card(data, options = {}) {
    const uid = 'rating-' + (++serial), has = data.score != null;
    const provisional = data.bouts > 0 && data.bouts < 4;
    const section = el('section', {class: 'rating-card' + (has ? ' rating-tier-' + Math.floor(data.score / 10) * 10 : '') + (options.matchup ? ' rating-matchup' : ''), 'aria-label': 'Sample UPSET rating for ' + data.name});
    const breakdown = el('div', {class: 'rating-breakdown', id: uid + '-breakdown'});
    const info = el('div', {class: 'rating-info-panel', id: uid + '-info'});
    const dial = ring(data, options.matchup);
    toggle(dial, breakdown);
    const infoButton = el('button', {type: 'button', class: 'rating-info-button', 'aria-label': 'How this sample rating is calculated', text: 'i'});
    toggle(infoButton, info);
    const badges = el('div', {class: 'rating-badges'}, el('span', {class: 'rating-label', text: 'UPSET RATING'}),
      el('span', {class: 'rating-sample-badge', text: 'SAMPLE'}), infoButton);
    if (provisional) badges.append(el('span', {class: 'rating-provisional', text: 'Provisional'}));
    const copy = el('div', {class: 'rating-identity'}, badges,
      el('h2', {class: 'rating-name', text: data.name}),
      el('p', {class: 'rating-subtitle', text: data.division + ' · ' + data.record + ' UFC'}));
    if (has) {
      copy.append(el('p', {class: 'rating-change ' + (data.delta < 0 ? 'is-down' : 'is-up'),
        text: (data.delta < 0 ? '↘ ' : '↗ ') + signed(data.delta) + ' after last fight'}),
      el('p', {class: 'rating-last-result', text: data.lastResult}),
      el('button', {type: 'button', class: 'rating-breakdown-link', text: 'Explore the four parts ↓'}));
      copy.children[copy.children.length - 1].addEventListener('click', () => dial.click());
    } else copy.append(el('p', {class: 'rating-last-result', text: 'Rated after first UFC fight'}));
    const trend = el('div', {class: 'rating-trend'},
      el('div', {class: 'rating-trend-head'}, el('span', {class: 'rating-label', text: 'CAREER TREND'}),
        el('span', {class: 'rating-peak', text: has ? 'Peak ' + data.peak : 'No history yet'})),
      sparkline(data.history),
      el('p', {class: 'rating-history-note', text: has ? 'Illustrative fight-by-fight history' : 'A debut has no assigned score.'}));
    section.append(el('div', {class: 'rating-card-top'}, dial, copy, trend));
    if (has) {
      breakdown.append(el('div', {class: 'rating-panel-heading'}, el('h3', {text: 'Behind the number'}),
        el('span', {text: 'Select a part to see its sample stats'})));
      const buttons = el('div', {class: 'rating-parts'}), raw = el('div', {class: 'rating-raw-panel', id: uid + '-raw'});
      let selected = null;
      for (const part of data.parts) {
        const shownPart = Math.round(part.score);
        const button = el('button', {type: 'button', class: 'rating-part rating-tier-' + Math.floor(shownPart / 10) * 10, 'aria-expanded': 'false', 'aria-controls': raw.id},
          el('span', {class: 'rating-part-head'}, el('span', {text: part.label}), el('b', {text: String(shownPart)})),
          el('span', {class: 'rating-bar', 'aria-hidden': 'true'}, el('span', {style: 'width:' + (shownPart / 99 * 100) + '%'})),
          el('span', {class: 'rating-part-caption', text: part.key === 'resume' ? 'Who they have beaten' : 'Explore sample stats →'}));
        button.addEventListener('click', () => {
          if (selected === button && !raw.hidden) {
            raw.hidden = true; button.setAttribute('aria-expanded', 'false'); selected = null; return;
          }
          for (const other of buttons.children) other.setAttribute('aria-expanded', String(other === button));
          selected = button; raw.hidden = false;
          raw.replaceChildren(el('h4', {text: part.label + ' · sample inputs'}), el('p', {text: part.description}),
            el('div', {class: 'rating-raw-table'}, ...part.raw.map(row => el('div', {class: 'rating-raw-row'},
              el('span', {text: row.label}), el('b', {text: row.value}),
              el('span', {text: row.percentile == null ? 'Not available' : ordinal(row.percentile) + ' division percentile'})))));
        });
        buttons.append(button);
      }
      raw.hidden = true;
      breakdown.append(buttons, raw);
      const history = el('div', {class: 'rating-history-list'}, el('h4', {text: 'Sample fight history'}));
      for (const item of data.history.slice(-5).reverse()) history.append(el('div', {class: 'rating-history-row'},
        el('span', {text: item.label}), el('span', {text: item.outcome + ' · opponent ' + item.opponentScore}),
        el('span', {class: 'rating-history-chip' + changeClass(item.change), text: (item.change < 0 ? '↘ ' : '↗ ') + signed(item.change)}),
        el('b', {text: String(item.score)})));
      breakdown.append(history);
    }
    if (has) {
      const skillParts = data.parts.filter(part => part.key !== 'resume').map(part => part.score).sort((a, b) => b - a);
      const skills = .5 * skillParts[0] + .3 * skillParts[1] + .2 * skillParts[2];
      const resume = data.parts.find(part => part.key === 'resume').score;
      info.append(el('h3', {text: 'How the example is built'}),
        el('p', {text: 'A proposed overall rating from 60 to 99. This is a design example, not a measured fighter score or a win probability.'}),
        el('div', {class: 'rating-formula'},
          el('div', {}, el('span', {text: 'Skills blend'}), el('b', {text: '50% best + 30% second + 20% third'})),
          el('div', {}, el('span', {text: 'Overall blend'}), el('b', {text: '50% résumé + 50% skills'})),
          el('div', {}, el('span', {text: 'Sample calculation'}), el('b', {text: rounded(resume) + ' × 50% + ' + rounded(skills) + ' × 50% = ' + data.curve.combined.toFixed(1)}))),
        el('p', {class: 'rating-curve-step', text: 'Combined ' + data.curve.combined.toFixed(1) + ' → ' + data.curve.percentileLabel + ' → ' + data.score}),
        el('p', {text: 'The final step uses an illustrative display curve. The real curve and weights still require validation; the four parts do not simply average to the displayed number.'}),
        el('p', {text: 'Provisional means fewer than 4 recorded UFC fights. A dashed ring marks the smaller record. A fighter without a recorded UFC fight has no number.'}),
        el('p', {text: 'Proposed updates follow fights, with no age or inactivity penalty. Earlier ratings must use only earlier fights.'}),
        el('div', {class: 'rating-track-record'}, el('b', {text: 'Prediction track record: not established'}),
          el('span', {text: 'No win-rate claim is available for this proposed rating.'})));
    } else info.append(el('h3', {text: 'No rating before a UFC debut'}),
      el('p', {text: 'The design assigns no default score to a debut fighter. Real fighter ratings will appear once the rating model is ready.'}));
    section.append(breakdown, info);
    return section;
  }
  function legend() {
    return el('div', {class: 'rating-legend', 'aria-label': 'Rating color scale'},
      ...[[90, '90+'], [80, '80–89'], [70, '70–79'], [60, '60–69']].map(([tier, label]) =>
        el('span', {class: 'rating-tier-' + tier}, el('i', {'aria-hidden': 'true'}), label)));
  }
  function recordedDisclosure(report) {
    const metrics = report.metrics || {}, disclosure = el('details', {class: 'rating-method-details'},
      el('summary', {text: 'Original recorded stats · ' + (report.window ? 'last ' + report.window + ' fights' : 'career')}),
      el('p', {text: 'These are the recorded values in the selected page window before ' + report.before + '. The overall rating uses its full pre-date history and stays the same when the measurement window changes.'}));
    for (const key of ['sig_landed_per_minute', 'striking_accuracy', 'striking_defense', 'takedowns_per_15_minutes',
      'takedown_accuracy', 'takedown_defense', 'submission_attempts_per_15_minutes']) disclosure.append(
      el('div', {class: 'rating-live-stat'}, el('span', {text: INPUT_LABELS[key]}), el('b', {text: inputValue(key, metrics[key])})));
    return disclosure;
  }
  function referencePosition(percentile) {
    const reference = 'UFC rating snapshots through 2018';
    if (percentile === 0) return 'below all ' + reference;
    if (percentile === 1) return 'above all ' + reference;
    const shown = Math.round(100 * percentile);
    if (shown === 0) return 'below the 1st percentile of ' + reference;
    if (shown === 100) return 'above the 99th percentile of ' + reference;
    return 'about the ' + ordinal(shown) + ' percentile of ' + reference;
  }
  function experimentalCard(report, options) {
    const rating = report.rating, uid = 'rating-live-' + (++serial), weight = rating.model.resume_weight;
    const version = LIVE_VERSIONS.get(rating.version), upperScale = version === 'v3' || version === 'v4', hasHolds = version !== 'v1';
    const hold = hasHolds ? holdResult(rating.outcome_hold) : null;
    const section = el('section', {class: 'rating-card rating-tier-' + Math.floor(rating.score / 10) * 10,
      'aria-label': 'Experimental ' + version + ' UPSET rating for ' + report.name});
    const dial = ring({score: rating.score, bouts: rating.bouts}, options.matchup);
    const breakdown = el('div', {class: 'rating-breakdown', id: uid + '-parts'});
    toggle(dial, breakdown); breakdown.hidden = false; dial.setAttribute('aria-expanded', 'true');
    const method = el('div', {class: 'rating-info-panel', id: uid + '-method'});
    const methodButton = el('button', {type: 'button', class: 'rating-info-button', 'aria-label': 'How this experimental rating is calculated', text: 'i'});
    toggle(methodButton, method, true);
    const badges = el('div', {class: 'rating-badges'}, el('span', {class: 'rating-label', text: 'UPSET RATING'}),
      el('span', {class: 'rating-experimental-badge', text: 'Experimental ' + version}), methodButton);
    if (rating.provisional) badges.append(el('span', {class: 'rating-provisional', text: 'Provisional'}));
    const lastResults = Array.isArray(rating.last_results) ? rating.last_results : [];
    const latest = lastResults.length === 1 ? lastResults[0] : null;
    const resultWord = latest && ({win: 'win', loss: 'loss', nc: 'no contest', draw: 'draw', other: 'non-decisive result'}[latest.result_type || latest.outcome]);
    const direction = rating.change < 0 ? '↘ ' : rating.change > 0 ? '↗ ' : '';
    const outcome = hold || resultWord;
    const lastChange = rating.change == null ? 'First recorded rating' : (hold ? 'Held' : direction + signed(rating.change)) +
      (outcome ? ' after ' + outcome + (latest && latest.opponent ? ' vs. ' + latest.opponent : '') : ' after last recorded fight') +
      (Number.isInteger(rating.previous_score) ? ' · ' + rating.previous_score + ' → ' + rating.score : '');
    const copy = el('div', {class: 'rating-identity'}, badges,
      el('p', {class: 'rating-subtitle', text: (rating.division || 'Unclassified division') + ' · ' + rating.bouts + ' recorded UFC fights'}),
      el('p', {class: 'rating-change' + changeClass(rating.change), text: lastChange}));
    if (typeof rating.last_fight_summary === 'string' && rating.last_fight_summary.trim()) copy.append(
      el('p', {class: 'rating-last-fight-summary', text: rating.last_fight_summary}));
    if (latest?.result_type === 'nc') copy.append(el('p', {class: 'rating-hold-explanation',
      text: 'This bout added no win or loss. Its recorded performance still updates the rating’s skill inputs.'}));
    const changes = Array.isArray(rating.part_changes) ? rating.part_changes : [];
    const comparable = changes.length === 4 && changes.every(part => finite(part.previous) && finite(part.current) && finite(part.change));
    if (comparable) {
      copy.append(el('div', {class: 'rating-part-change-row'}, ...changes.map(part => {
        const shownChange = Math.round(part.change * 10) / 10;
        return el('span', {text: part.label + ' ' + (shownChange > 0 ? '+' : '') + shownChange.toFixed(1)});
      })));
      if (!hasHolds && rating.change < 0 && latest && latest.outcome === 'win') {
        const oldSkills = changes.filter(part => part.key !== 'resume').map(part => part.previous).sort((a, b) => b - a);
        const newSkills = changes.filter(part => part.key !== 'resume').map(part => part.current).sort((a, b) => b - a);
        const resumeChange = changes.find(part => part.key === 'resume');
        const skillContribution = (newSkills.reduce((sum, value, i) => sum + value * [.5, .3, .2][i], 0) -
          oldSkills.reduce((sum, value, i) => sum + value * [.5, .3, .2][i], 0)) * (1 - weight);
        const resumeContribution = resumeChange ? resumeChange.change * weight : 0;
        if (resumeContribution > 0 && skillContribution < 0 && skillContribution + resumeContribution < 0) copy.append(
          el('p', {class: 'rating-win-explanation', text: 'The win raised résumé, but the skills drop outweighed that gain.'}));
        else copy.append(el('p', {class: 'rating-win-explanation', text: 'A win does not guarantee a higher overall rating. The blend, historical curve and protective adjustments below show how this update was calculated.'}));
      }
    } else copy.append(el('p', {class: 'rating-part-change-row', text: rating.change == null ?
      'First rating · no earlier component scores to compare.' : 'Component-change details are unavailable in this snapshot.'}));
    if (hold && !upperScale) copy.append(el('p', {class: 'rating-hold-explanation', text:
      'The calculated grade after the usual limits was ' + rating.unheld_score + '. The badge stayed at ' + rating.score +
      ' because ' + (hold === 'win' ? 'a win cannot lower it.' : 'a loss cannot raise it.')}));
    if (upperScale && (hold || rating.small_history_adjustment || rating.change_adjustment)) {
      const reasons = [];
      if (rating.small_history_adjustment) reasons.push('early career cap');
      if (rating.change_adjustment) reasons.push('five-point change limit');
      if (hold) reasons.push('held after ' + hold);
      copy.append(el('p', {class: 'rating-hold-explanation', text:
        'Model grade ' + rating.curve_score + ' · Displayed ' + rating.score + ' (' + reasons.join(', ') + ').'}));
    }
    const assessed = upperScale ? 'Last recorded UFC fight ' + rating.event_date : 'Updated after ' + rating.event_date;
    copy.append(el('p', {class: 'rating-last-result', text: 'Peak ' + rating.peak + ' · ' + assessed}));
    if (upperScale && rating.rating_is_stale) copy.append(el('p', {class: 'rating-last-fight-summary', text:
      'Historical UFC rating · This fight was more than two years before the selected date.'}));
    section.append(el('div', {class: 'rating-card-top'}, dial, copy));
    breakdown.append(el('div', {class: 'rating-panel-heading'}, el('h3', {text: 'Behind the number'}),
      el('span', {text: 'Select a part to explore its model inputs'})));
    const buttons = el('div', {class: 'rating-parts'}), raw = el('div', {class: 'rating-raw-panel', id: uid + '-inputs'});
    raw.hidden = true;
    let selected = null;
    for (const part of rating.parts) {
      const shownPart = Math.round(part.score);
      const button = el('button', {type: 'button', class: 'rating-part rating-tier-' + Math.floor(shownPart / 10) * 10,
        'aria-expanded': 'false', 'aria-controls': raw.id},
        el('span', {class: 'rating-part-head'}, el('span', {text: part.label}), el('b', {text: String(shownPart)})),
        el('span', {class: 'rating-bar', 'aria-hidden': 'true'}, el('span', {style: 'width:' + (shownPart / 99 * 100) + '%'})),
        el('span', {class: 'rating-part-caption', text: 'Explore model inputs →'}));
      button.addEventListener('click', () => {
        const close = selected === button && !raw.hidden;
        for (const other of buttons.children) other.setAttribute('aria-expanded', String(!close && other === button));
        selected = close ? null : button; raw.hidden = close;
        if (!close && part.key === 'resume') {
          const wins = Array.isArray(rating.best_wins) ? rating.best_wins : [];
          const winList = el('div', {class: 'rating-best-wins'});
          for (const win of wins) winList.append(el('div', {class: 'rating-best-win'},
            el('b', {text: win.opponent || 'Recorded opponent'}),
            el('span', {class: 'rating-opponent-grade', text: 'Pre-fight grade: ' + (Number.isInteger(win.opponent_rating) ? win.opponent_rating : 'Not rated')}),
            el('small', {text: (win.date || '') + (win.method ? ' · ' + win.method : '')})));
          if (!wins.length) winList.append(el('p', {text: 'No wins with a rated opponent are available in this snapshot.'}));
          raw.replaceChildren(el('h4', {text: 'Résumé · strongest rated wins'}),
            el('p', {class: 'rating-model-precision', text: 'Unrounded component score: ' + part.score.toFixed(2)}),
            el('p', {text: 'Opponent grades are their pre-fight grades under this rating version, not their current grades. Historical grades are retrospective applications of the fixed model.'}), winList,
            el('details', {class: 'rating-method-details'}, el('summary', {text: 'Résumé model inputs'}),
              ...Object.entries(part.metrics).map(([key, value]) => el('div', {class: 'rating-live-stat'},
                el('span', {text: INPUT_LABELS[key] || key.replaceAll('_', ' ')}), el('b', {text: inputValue(key, value)})))));
        } else if (!close) raw.replaceChildren(el('h4', {text: part.label + ' · recent-weighted model inputs'}),
            el('p', {class: 'rating-model-precision', text: 'Unrounded component score: ' + part.score.toFixed(2)}),
            el('p', {text: 'These recency-weighted observations feed the opponent-baseline adjustment and exposure shrinkage. They are not recorded career totals or measured division percentiles.'}),
            el('div', {class: 'rating-raw-table'}, ...Object.entries(part.metrics).map(([key, value]) => el('div', {class: 'rating-live-stat'},
              el('span', {text: INPUT_LABELS[key] || key.replaceAll('_', ' ')}), el('b', {text: inputValue(key, value)})))));
      });
      buttons.append(button);
    }
    const pctWeight = value => (value * 100).toFixed(0) + '%';
    const unheldStep = hold && rating.unheld_score !== rating.curve_score ? ' → ' + rating.unheld_score + ' after limits' : '';
    const gradeStep = hold ? ' → curve ' + rating.curve_score + unheldStep + ' → held at ' + rating.score :
      rating.curve_score === rating.score ? ' → overall ' + rating.score :
        ' → curve ' + rating.curve_score + ' → displayed ' + rating.score;
    const conversion = upperScale ? ' → model grade ' + rating.curve_score +
      (rating.curve_score === rating.score ? '' : ' → displayed ' + rating.score) :
      ' → ' + referencePosition(rating.curve_percentile) + gradeStep;
    breakdown.append(buttons,
      el('p', {class: 'rating-visible-conversion', text: 'Combined ' + rating.raw_combined.toFixed(2) + conversion}),
      el('p', {class: 'rating-conversion-note', text: pctWeight(weight) + ' résumé + ' + pctWeight(1 - weight) +
        ' skills. Skill weights are 50%, 30% and 20% from strongest to weakest. The calculation uses unrounded scores, then puts the overall on a historical grading scale.' +
        (rating.small_history_adjustment || rating.change_adjustment ? ' Applied adjustments include limited history (' + signed(rating.small_history_adjustment) + ') and the per-date change limit (' + signed(rating.change_adjustment) + ').' : '')}), raw);
    const recordMount = el('div', {class: 'rating-track-record-slot'});
    breakdown.append(recordMount);
    const history = Array.isArray(rating.history) ? rating.history : [];
    const fightsByDate = new Map();
    for (const fight of report.history || []) {
      if (!fight.opponent) continue;
      if (!fightsByDate.has(fight.date)) fightsByDate.set(fight.date, []);
      fightsByDate.get(fight.date).push(fight);
    }
    breakdown.append(el('div', {class: 'rating-trend rating-live-trend'}, el('div', {class: 'rating-trend-head'},
      el('span', {class: 'rating-label', text: 'RATING HISTORY'}), el('span', {class: 'rating-peak', text: 'Peak ' + rating.peak})),
      ratingHistoryChart(history, fightsByDate, rating.peak),
      el('p', {class: 'rating-history-note', text: 'Ratings change after recorded fight dates. UFC history before ' + rating.before + '.'})));
    const historyList = el('div', {class: 'rating-history-list'}, el('h4', {text: 'Recent rating changes'}));
    for (const row of history.slice(-8).reverse()) {
      const rowHold = hasHolds ? holdResult(row.outcome_hold) : null;
      const fights = fightsByDate.get(row.date) || [];
      const result = fights.length === 1 ? fightLabel(fights[0]) : fights.length > 1 ? fights.length + ' fights on this date' : 'After recorded fight';
      const explanation = fights.length === 1 && fights[0].result_type === 'nc'
        ? 'Recorded performance can change the grade after a no contest.' : null;
      historyList.append(el('div', {class: 'rating-history-row', ...(explanation ? {title: explanation} : {})},
        el('span', {text: row.date}), el('span', {text: (rowHold ? 'Held after ' + rowHold + ' · ' : row.change == null ? 'First rating · ' : '') + result}),
        el('span', {class: 'rating-history-chip' + changeClass(row.change), text: row.change == null ? '—' : signed(row.change)}),
        el('b', {text: String(row.score)})));
    }
    breakdown.append(historyList, recordedDisclosure(report));
    const resumePart = rating.parts.find(part => part.key === 'resume');
    const percentile = (rating.curve_percentile * 100).toFixed(2) + 'th historical reference percentile';
    method.append(el('h3', {text: 'How Experimental ' + version + ' is calculated'}),
      el('p', {text: 'An experimental 60–99 performance index, not a win probability or a confidence range. Its opponent-baseline adjustments are a research prototype, not validated latent skill.'}),
      el('div', {class: 'rating-formula'},
        el('div', {}, el('span', {text: 'Skills blend'}), el('b', {text: '50% best + 30% second + 20% third'})),
        el('div', {}, el('span', {text: hasHolds ? 'Fixed overall blend' : 'Learned overall blend'}), el('b', {text: pctWeight(weight) + ' résumé + ' + pctWeight(1 - weight) + ' skills'})),
        el('div', {}, el('span', {text: 'Combined score'}), el('b', {text: rating.raw_combined.toFixed(2)})),
        el('div', {}, el('span', {text: 'Résumé / skills inputs'}), el('b', {text: resumePart.score.toFixed(2) + ' / ' + rating.skills_combined.toFixed(2)}))),
      el('p', {class: 'rating-curve-step', text: 'Combined ' + rating.raw_combined.toFixed(2) + (upperScale ? conversion : ' → ' + percentile + ' → curve score ' + rating.curve_score)}),
      el('p', {text: 'Historical reference frozen before ' + (rating.display_curve && rating.display_curve.reference_before || '2019-01-01') + '. The percentile counts fighter-date scores below the combined score and half of the ties. The blend uses unrounded component values.'}),
      el('p', {text: hasHolds ? 'The fixed 50/50 blend gives results and measured skills equal weight. Each component uses the 60–99 scale.' :
        'The résumé/skills weight was selected on earlier years, with training before ' + (rating.model.training_before || '2019-01-01') + '. Each component is a research index placed on the 60–99 scale, not a measured division percentile.'}),
      el('div', {class: 'rating-formula'},
        el('div', {}, el('span', {text: 'Limited-history adjustment'}), el('b', {text: signed(rating.small_history_adjustment || 0)})),
        el('div', {}, el('span', {text: 'Per-date change adjustment'}), el('b', {text: signed(rating.change_adjustment || 0)})),
        hold ? el('div', {}, el('span', {text: 'Grade before outcome hold'}), el('b', {text: String(rating.unheld_score)})) : null,
        el('div', {}, el('span', {text: 'Displayed rating'}), el('b', {text: String(rating.score)}))),
      el('p', {text: 'Fewer than five UFC fights caps the displayed rating at 88. Fewer than four is Provisional. After the first rating, each date-batch change is limited to five points. These are product guardrails, not statistical reliability thresholds.'}),
      el('p', {text: 'Updates use only earlier recorded bouts and stay fixed between a fighter’s fights. The L3/L5/L10 selector changes recorded stats, not this full-history rating. No inactivity or age penalty is applied.'}));
    if (hasHolds) method.append(
      el('p', {text: 'Striking gives KO/TKO wins credit relative to the opponent’s earlier stoppage-loss rate.'}),
      el('p', {text: 'On dates with only wins, a calculated decrease holds the badge at its previous grade. On dates with only losses, a calculated increase does the same. The underlying model scores still update.'}),
      el('p', {text: upperScale ? (version === 'v4' ?
        'Above 89, the higher grades gradually require bigger gains in the combined score. ' :
        'Grades 95 through 99 are evenly spaced. ') +
        'A new 99 requires reaching the average of the three highest qualifying fighter peaks before 2019.' :
        'A new 99 requires an unrounded grade of 99 and placement at or above the 99.99th historical percentile.'}));
    else method.append(el('p', {text: 'A win raises résumé, but the overall can still fall if the skill contribution drops more. This index combines performance and results; it is not simply a win/loss points table.'}));
    const record = rating.track_record || {};
    const measured = Number.isInteger(record.wins) && Number.isInteger(record.total) && record.total > 0 &&
      record.wins >= 0 && record.wins <= record.total && finite(record.accuracy) && Math.abs(record.accuracy - record.wins / record.total) < 1e-8;
    const trackRecord = el('div', {class: 'rating-track-record'}, el('b', {text: measured ?
      'The higher displayed rating won ' + (100 * record.accuracy).toFixed(1) + '% of ' + record.total.toLocaleString('en-US') + ' evaluated fights.' : 'Higher-rating track record unavailable.'}),
      el('span', {text: 'Historical development evidence from ' + (record.from_date || '2019-01-01') +
        (record.before_exclusive ? ' to before ' + record.before_exclusive : '') + '; not fresh future validation.'}),
      el('span', {text: 'Ties excluded: ' + (record.ties_excluded == null ? 'not reported' : record.ties_excluded) + ' · Unavailable/debut exclusions: ' +
        (record.unavailable_excluded == null ? 'not reported' : record.unavailable_excluded)}));
    recordMount.append(trackRecord);
    method.append(el('p', {text: rating.evaluation_label || 'Already-inspected historical development evidence; not protected future validation.'}));
    section.append(breakdown, method);
    return section;
  }
  function openDetails(data, options) {
    const sample = options.sample === true;
    const dialog = el('dialog', {class: 'rating-detail-dialog', 'aria-label': 'UPSET rating details for ' + data.name});
    const close = el('button', {type: 'button', class: 'rating-dialog-close', 'aria-label': 'Close rating details', text: '×'});
    const dismiss = () => { if (dialog.close) dialog.close(); dialog.remove(); };
    close.addEventListener('click', dismiss);
    dialog.addEventListener('close', () => dialog.remove());
    dialog.append(el('div', {class: 'rating-dialog-heading'}, el('div', {},
      el('span', {class: 'rating-label', text: 'UPSET RATING / BREAKDOWN'}),
      el('h2', {text: data.name})), close));
    if (sample) {
      dialog.append(el('p', {class: 'rating-dialog-notice', text: 'Fictional design example · all scores and percentiles below are illustrative.'}));
      const expanded = card(data, options);
      if (data.score != null) {
        const breakdown = expanded.querySelector('.rating-breakdown');
        breakdown.hidden = false;
        expanded.querySelector('.rating-ring').setAttribute('aria-expanded', 'true');
        breakdown.append(expanded.querySelector('.rating-trend'));
      }
      dialog.append(expanded);
    } else if (availableRating(data)) {
      dialog.append(experimentalCard(data, options));
    } else {
      const metrics = data.metrics || {};
      const num = (value, suffix = '') => value == null ? 'Not available' : Number(value).toFixed(2) + suffix;
      const pct = value => value == null ? 'Not available' : (100 * value).toFixed(1) + '%';
      const unavailableMessage = data.rating && data.rating.message || 'In development · no overall rating has been assigned.';
      const snapshotMissing = data.rating && ['no_history', 'unsupported_cutoff'].includes(data.rating.status);
      dialog.append(el('p', {class: 'rating-dialog-notice', text: unavailableMessage}),
        el('p', {class: 'rating-dialog-explanation', text: snapshotMissing ?
          'No experimental overall rating is available for this fighter at the selected cutoff. The recorded stats below remain available independently of rating coverage.' :
          'The four-part overall rating is unavailable in this view. It combines skills with résumé, the strength of opposition. The recorded stats below are not rating scores.'}));
      const parts = [
        ['Striking', 'Effectiveness and defense on the feet.', [['Strikes landed / min', num(metrics.sig_landed_per_minute)], ['Striking accuracy', pct(metrics.striking_accuracy)], ['Striking defense', pct(metrics.striking_defense)]]],
        ['Wrestling', 'Takedowns, takedown defense and control.', [['Takedowns / 15 min', num(metrics.takedowns_per_15_minutes)], ['Takedown accuracy', pct(metrics.takedown_accuracy)], ['Takedown defense', pct(metrics.takedown_defense)]]],
        ['Grappling', 'Submission threat and effectiveness on the ground.', [['Submission attempts / 15 min', num(metrics.submission_attempts_per_15_minutes)]]],
        ['Résumé', 'Who the fighter has beaten, using earlier opponent ratings.', [['Opponent-adjusted résumé', 'Not rated yet']]]];
      const list = el('div', {class: 'rating-live-parts'});
      for (const [name, description, rows] of parts) list.append(el('details', {}, el('summary', {text: name + ' · not rated yet'}),
        el('p', {text: description}), ...rows.map(([label, value]) => el('div', {class: 'rating-live-stat'}, el('span', {text: label}), el('b', {text: value})))));
      dialog.append(el('p', {class: 'rating-label', text: 'RECORDED STATS · ' + (data.window ? 'LAST ' + data.window + ' FIGHTS' : 'CAREER') + ' · BEFORE ' + (data.before || 'SELECTED DATE')}), list,
        el('details', {class: 'rating-method-details'}, el('summary', {text: 'How the proposed rating would work'}),
          el('p', {text: 'Skills: 50% strongest, 30% second and 20% third. ' +
            (data.rating && data.rating.model && finite(data.rating.model.resume_weight) ?
              'This snapshot’s overall blend uses ' + (100 * data.rating.model.resume_weight).toFixed(0) + '% résumé and ' + (100 * (1 - data.rating.model.resume_weight)).toFixed(0) + '% skills, followed by a fixed display curve.' :
              'The design starts with 50% skills and 50% résumé; final versioned weights require a fitted model.')}),
          el('p', {text: 'The model must account for opponent quality, division, recent fights and limited history. A provisional badge would mark fewer than four UFC fights. A debut has no score.'}),
          el('p', {text: 'A rating is not a win percentage. Its value on later fights has not been established.'})),
        el('a', {class: 'rating-back', href: '#/rating-preview', text: 'Try the interactive sample ratings ↗'}));
      dialog.querySelector('a').addEventListener('click', dismiss);
    }
    dialog.append(legend());
    root.document.body.append(dialog);
    if (dialog.showModal) dialog.showModal();
    else dialog.setAttribute('open', '');
    return dialog;
  }
  function badge(data, options = {}) {
    const sample = options.sample === true;
    const live = !sample && availableRating(data);
    const version = live ? LIVE_VERSIONS.get(data.rating.version) : null;
    const summary = sample ? data : {name: data.name, score: live ? data.rating.score : null,
      bouts: data.rating ? (data.rating.bouts ?? data.rating.recorded_bouts) : (data.history || []).length};
    const button = ring(summary, options.matchup);
    const stale = (version === 'v3' || version === 'v4') && data.rating.rating_is_stale;
    const ageLabel = stale ? ' · Historical UFC rating from ' + data.rating.event_date : '';
    const capped = live && data.rating.small_history_adjustment < 0;
    const capLabel = capped ? ' · Capped for fewer than five UFC fights' : '';
    button.className += ' rating-badge-compact';
    button.disabled = false;
    button.setAttribute('aria-haspopup', 'dialog');
    if (live) button.className += ' is-experimental';
    button.setAttribute('aria-label', (live ? 'Experimental ' + version + ' ' : '') + 'UPSET rating for ' + data.name + ': ' + (summary.score == null ? 'not rated yet' : summary.score + ' on a 60 to 99 scale') + capLabel + ageLabel + (live ? '. Experimental index, not a win probability.' : '.') + ' Open breakdown');
    button.setAttribute('title', summary.score == null ? 'UPSET rating unavailable · click for details' :
      (live ? 'Experimental ' + version + ' · not a win probability · ' : 'UPSET rating ') + summary.score + capLabel + ageLabel + ' · click for breakdown');
    const staleYear = stale ? data.rating.event_date.slice(0, 4) : null;
    button.querySelector('.rating-scale').textContent = staleYear || (live ? 'EXP ' + version.toUpperCase() : 'UPSET');
    button.addEventListener('click', () => openDetails(data, options));
    return button;
  }
  function unavailable(report) {
    return el('section', {class: 'rating-unavailable', 'aria-label': 'UPSET rating in development'},
      el('span', {class: 'rating-pending-mark', 'aria-hidden': 'true', text: '—'}),
      el('div', {}, el('div', {class: 'rating-label', text: 'UPSET RATING'}),
        el('p', {text: 'In development · no overall rating assigned'})),
      el('a', {href: '#/rating-preview', text: 'Explore the design ↗'}));
  }
  function preview() {
    const examples = root.UPSETRatingExamples || [];
    const page = el('article', {class: 'rating-design-page'},
      el('a', {class: 'rating-back', href: '#/', text: '← Back to fighter research'}),
      el('header', {class: 'rating-design-heading'}, el('p', {class: 'eyebrow', text: 'UPSET LAB / DESIGN STUDY 01'}),
        el('h1', {class: 'distressed', text: 'UPSET rating'}),
        el('p', {text: 'A small badge beside the portrait. Click it for the full story.'})),
      el('div', {class: 'rating-preview-notice'}, el('b', {text: 'Design preview · fictional examples'}),
        el('span', {text: 'These fictional scores, histories and percentiles demonstrate the design. Real fighter pages use a separate, calculated experimental rating.'})));
    const choices = el('div', {class: 'rating-example-choices', role: 'group', 'aria-label': 'Sample fighter scenarios'});
    const mount = el('div', {class: 'rating-example-mount', 'aria-live': 'polite'});
    function portrait(data, matchup) {
      return el('div', {class: 'rating-sample-fighter'},
        el('div', {class: 'rating-sample-portrait-row'},
          el('div', {class: 'rating-sample-portrait', 'aria-label': 'Illustrative fighter portrait'},
            svg('svg', {viewBox: '0 0 90 108', 'aria-hidden': 'true'},
              svg('circle', {cx:45,cy:33,r:17}),svg('path', {d:'M12 108V89Q12 58 45 58Q78 58 78 89V108Z'}))),
          badge(data, {sample:true, matchup})),
        el('div', {class: 'rating-sample-identity'}, el('h2', {text:data.name}), el('p', {text:data.division+' · '+data.record+' UFC'})));
    }
    const select = index => {
      for (let i = 0; i < choices.children.length; i++) choices.children[i].setAttribute('aria-pressed', String(i === index));
      mount.replaceChildren(el('section', {class:'rating-compact-demo'},el('p',{class:'rating-label',text:'FIGHTER PROFILE'}),portrait(examples[index],false)),
        el('section',{class:'rating-compact-demo'},el('p',{class:'rating-label',text:'HEAD TO HEAD'}),
          el('div',{class:'rating-sample-matchup'},portrait(examples[index],true),el('span',{class:'rating-sample-vs',text:'VS'}),portrait(examples[index===0?1:0],true))));
    };
    examples.forEach((data, i) => {
      const button = el('button', {type: 'button', text: data.label, 'aria-pressed': String(i === 0)});
      button.addEventListener('click', () => select(i)); choices.append(button);
    });
    page.append(el('div', {class: 'rating-example-toolbar'}, choices), mount, legend());
    if (examples.length) select(0);
    return page;
  }
  return {card, preview, unavailable, badge};
});
