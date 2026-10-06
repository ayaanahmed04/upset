// Editorial edition. Display-only changes; the research API and metric keys remain stable.

'use strict';
/* ================= helpers ================= */
const $ = id => document.getElementById(id);
const NS = 'http://www.w3.org/2000/svg';

function h(tag, attrs, ...kids) {
  const n = document.createElement(tag);
  if (attrs)
    for (const [k, v] of Object.entries(attrs)) {
      if (v == null || v === false) continue;
      if (k === 'class') n.className = v;
      else if (k === 'text') n.textContent = v;
      else if (k === 'style') n.style.cssText = v;
      else if (k.startsWith('on')) n[k] = v;
      else n.setAttribute(k, v === true ? '' : v);
    }
  for (const c of kids.flat()) {
    if (c == null || c === false) continue;
    n.append(c instanceof Node ? c : document.createTextNode(String(c)));
  }
  return n;
}

function s(tag, attrs, ...kids) {
  const n = document.createElementNS(NS, tag);
  if (attrs)
    for (const [k, v] of Object.entries(attrs))
      if (v != null) n.setAttribute(k, v);
  for (const c of kids.flat())
    if (c != null) n.append(c instanceof Node ? c : document.createTextNode(String(c)));
  return n;
}
const fmt = (x, d = 2) => x == null ? '—' : Number(x).toFixed(d);
// Keep the API's per-15-minute fields stable and convert only their displayed units.
const perFive = x => fmt(x == null ? null : x / 3);
const pct = x => x == null ? '—' : (x * 100).toFixed(0) + '%';
const pct1 = x => x == null ? '—' : (x * 100).toFixed(1) + '%';
const signed = (x, d = 2) => x == null ? '—' : (x > 0 ? '+' : '') + Number(x).toFixed(d);
const int = x => x == null ? '—' : Number(x).toLocaleString();

function feet(inches) {
  if (inches == null) return null;
  const t = Math.round(inches);
  return Math.floor(t / 12) + '′' + (t % 12) + '″';
}

function ordinal(n) {
  n = Math.round(n);
  const v = n % 100;
  return n + (['th', 'st', 'nd', 'rd'][(v - 20) % 10] || ['th', 'st', 'nd', 'rd'][v] || 'th');
}

function initials(name) {
  const p = name.replace(/[^\p{L}\s'-]/gu, '').split(/\s+/).filter(Boolean);
  return ((p[0] || '?')[0] + (p.length > 1 ? p[p.length - 1][0] : '')).toUpperCase();
}

function niceDate(iso) {
  if (!iso) return '—';
  const d = new Date(iso + 'T12:00:00Z');
  return d.toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
    timeZone: 'UTC'
  });
}

function monthsBetween(a, b) {
  const x = new Date(a + 'T12:00:00Z'),
    y = new Date(b + 'T12:00:00Z');
  return (y.getUTCFullYear() - x.getUTCFullYear()) * 12 + (y.getUTCMonth() - x.getUTCMonth());
}

function ago(iso, ref) {
  if (!iso) return null;
  const m = monthsBetween(iso, ref);
  if (m < 1) return 'this month';
  if (m < 24) return m + ' mo ago';
  return Math.floor(m / 12) + ' yrs ago';
}
async function api(url) {
  const r = await fetch(url);
  const v = await r.json();
  if (!r.ok) throw new Error(v.error || 'Could not load records');
  return v;
}
const state = {
  window: '0',
  before: '',
  meta: null,
  matchup: [null, null],
  view: null
};

function params() {
  return '&before=' + encodeURIComponent(state.before) + '&window=' + state.window;
}

function windowLabel() {
  return state.window === '0' ? 'Career (all UFC fights)' : 'Last ' + state.window + ' fights';
}

/* ================= metric catalog ================= */
const METRICS = [{
  group: 'Striking',
  key: 'sig_landed_per_minute',
  unit: 'strikes / min',
  label: 'Sig. strikes landed / min',
  f: fmt
}, {
  group: 'Striking',
  key: 'sig_absorbed_per_minute',
  unit: 'strikes / min',
  label: 'Sig. strikes absorbed / min',
  f: fmt,
  lower: true
}, {
  group: 'Striking',
  key: 'sig_differential_per_minute',
  unit: 'strikes / min',
  label: 'Striking differential / min',
  f: x => signed(x)
}, {
  group: 'Striking',
  key: 'striking_accuracy',
  unit: 'of attempts landed',
  label: 'Striking accuracy',
  f: pct1
}, {
  group: 'Striking',
  key: 'striking_defense',
  unit: 'of strikes avoided',
  label: 'Striking defense',
  f: pct1
}, {
  group: 'Striking',
  key: 'knockdowns_per_15_minutes',
  unit: 'per 5 min',
  label: 'Knockdowns / 5 min',
  f: perFive
}, {
  group: 'Grappling',
  key: 'takedowns_per_15_minutes',
  unit: 'per 5 min',
  label: 'Takedowns / 5 min',
  f: perFive
}, {
  group: 'Grappling',
  key: 'takedown_accuracy',
  unit: 'of attempts landed',
  label: 'Takedown accuracy',
  f: pct1
}, {
  group: 'Grappling',
  key: 'takedown_defense',
  unit: 'of attempts stopped',
  label: 'Takedown defense',
  f: pct1
}, {
  group: 'Grappling',
  key: 'submission_attempts_per_15_minutes',
  unit: 'per 5 min',
  label: 'Sub attempts / 5 min',
  f: perFive
}, {
  group: 'Grappling',
  key: 'control_margin_seconds_per_minute',
  unit: 'sec / min',
  label: 'Control margin, sec / min',
  f: x => signed(x, 1)
}, ];
/* percentile oriented so higher = better for the fighter */
function goodPct(r, m) {
  const p = r.percentiles && r.percentiles.eligible && r.percentiles.values[m.key];
  if (!p) return null;
  return m.lower ? 100 - p.percentile : p.percentile;
}

/* ================= avatar & badges ================= */
function avatar(r, cls) {
  const img = r.roster && r.roster.image_url;
  const n = h('div', {
    class: 'avatar ' + (img ? '' : 'no-photo ') + (cls || ''),
    'aria-hidden': 'true',
    title: img && r.roster.image_credit ? r.roster.image_credit : null
  });
  if (img) {
    const i = h('img', {
      src: img,
      alt: '',
      loading: 'lazy'
    });
    i.onerror = () => {
      n.classList.add('no-photo');
      i.remove();
    };
    n.append(i);
  }
  // Names carry the identity when there is no credited photo.
  return n;
}

function statusBadges(r) {
  const out = [],
    sm = r.summary,
    ref = state.before;
  if (sm.division) out.push(h('span', {
    class: 'badge accent',
    text: sm.division
  }));
  /* Contract status is a present-day fact: only show it when the cutoff is near the roster date. */
  const rosterCurrent = r.roster && r.roster.status_current === true;
  if (rosterCurrent && r.roster.status === 'active') out.push(h('span', {
    class: 'badge active',
    title: 'On the UFC roster per ' + (r.roster.source || 'roster file') + ' as of ' + r.roster
      .as_of,
    text: 'Active'
  }));
  else if (rosterCurrent && r.roster.status) out.push(h('span', {
    class: 'badge',
    text: r.roster.status
  }));
  if (sm.last_bout) out.push(h('span', {
    class: 'badge',
    text: 'Last fight ' + ago(sm.last_bout, ref)
  }));
  if (sm.title_bouts) out.push(h('span', {
    class: 'badge',
    text: sm.title_bouts + ' title ' + (sm.title_bouts === 1 ? 'fight' : 'fights')
  }));
  return h('div', {
    class: 'badges'
  }, out);
}

function recordText(c) {
  return c.win + '–' + c.loss + (c.other ? '–' + c.other : '');
}

function streakText(st) {
  if (!st.outcome || !st.count) return '—';
  return (st.outcome === 'win' ? 'W' : st.outcome === 'loss' ? 'L' : 'D/NC ') + st.count;
}

function formStrip(history, n) {
  const items = history.slice(0, n).reverse();
  return h('div', {
    class: 'form',
    'aria-label': 'Recent results, oldest to newest'
  }, items.map(r => h('span', {
    class: 'chip ' + r.outcome,
    title: niceDate(r.date) + ' · ' + r.opponent + ' · ' + (r.method || ''),
    text: r.outcome === 'win' ? 'W' : r.outcome === 'loss' ? 'L' : '–'
  })));
}

/* ================= tooltip ================= */
const tip = $('tip');

function showTip(e, build) {
  tip.replaceChildren(...build());
  tip.classList.add('on');
  moveTip(e);
}

function moveTip(e) {
  const b = e.target.getBoundingClientRect ? e.target.getBoundingClientRect() : null;
  let x = e.clientX,
    y = e.clientY;
  if (x == null && b) {
    x = b.left + b.width / 2;
    y = b.top;
  }
  const w = tip.offsetWidth,
    hh = tip.offsetHeight;
  let left = x + 14,
    top = y - hh - 12;
  if (left + w > innerWidth - 8) left = x - w - 14;
  if (top < 8) top = y + 16;
  tip.style.left = left + 'px';
  tip.style.top = top + 'px';
}

function hideTip() {
  tip.classList.remove('on');
}

function bindTip(node, build) {
  node.addEventListener('pointerenter', e => showTip(e, build));
  node.addEventListener('pointermove', moveTip);
  node.addEventListener('pointerleave', hideTip);
  node.addEventListener('focus', e => showTip(e, build));
  node.addEventListener('blur', hideTip);
}

/* ================= charts ================= */
function timeline(history) {
  const compact = innerWidth < 700,
    N = compact ? 10 : 20;
  const values = history.slice(0, N).reverse();
  if (!values.length) return h('p', {
    class: 'muted',
    text: 'No recorded fights before this date.'
  });
  const vals = values.map(v => v.sig_differential_per_minute || 0);
  const niceUp = x => {
    if (x <= 0) return 0;
    const e = Math.pow(10, Math.floor(Math.log10(x))),
      f = x / e;
    return (f <= 1 ? 1 : f <= 2 ? 2 : f <= 2.5 ? 2.5 : f <= 5 ? 5 : 10) * e;
  };
  let posT = niceUp(Math.max(0, ...vals)),
    negT = niceUp(-Math.min(0, ...vals));
  const W = compact ? 380 : 760,
    top = 14,
    plotH = compact ? 120 : 150,
    left = compact ? 34 : 40,
    right = 12,
    plotW = W - left - right;
  // Keep both endpoint labels at least 20 SVG units from zero on mixed-sign charts.
  // Padding the smaller side preserves one linear scale for every bar.
  if (posT && negT) {
    const minSide = niceUp(Math.max(posT, negT) * 20 / (plotH - 20));
    posT = Math.max(posT, minSide);
    negT = Math.max(negT, minSide);
  }
  const scale = plotH / (posT + negT || 1),
    base = top + posT * scale,
    bottom = base + negT * scale + 38,
    H = bottom + 28;
  const step = plotW / values.length,
    bw = Math.min(24, step * .62);
  const svg = s('svg', {
    viewBox: `0 0 ${W} ${H}`,
    role: 'img',
    'aria-label': 'Significant strike differential per minute in each of the last ' + values.length +
      ' fights, oldest to newest'
  });
  for (const t of new Set([posT, 0, -negT])) {
    if (t === 0 && (posT === 0 && negT === 0)) continue;
    const y = base - t * scale;
    svg.append(s('line', {
      x1: left,
      x2: W - right,
      y1: y,
      y2: y,
      stroke: t === 0 ? '#4a505c' : '#22262e',
      'stroke-width': 1
    }));
    svg.append(s('text', {
      x: left - 8,
      y: y + 4,
      'text-anchor': 'end',
      'font-size': 11,
      fill: '#7f8794',
      'font-family': 'Inter,system-ui'
    }, t > 0 ? '+' + t : t));
  }
  let lastYear = null,
    lastX = null;
  values.forEach((r, i) => {
    const v = r.sig_differential_per_minute,
      cx = left + step * i + step / 2,
      x = cx - bw / 2;
    const g = s('g', {
      tabindex: 0,
      role: 'img',
      'aria-label': `${niceDate(r.date)}, ${r.opponent}, ${r.outcome}, differential ${signed(v)} per minute`
    });
    const hit = s('rect', {
      class: 'hit',
      x: left + step * i,
      y: top - 6,
      width: step,
      height: bottom - top + 10
    });
    g.append(hit);
    if (v != null) {
      const hgt = Math.max(1.5, Math.abs(v) * scale),
        rad = Math.min(4, hgt);
      const d = v >= 0 ?
        `M${x},${base} V${base-hgt+rad} Q${x},${base-hgt} ${x+rad},${base-hgt} H${x+bw-rad} Q${x+bw},${base-hgt} ${x+bw},${base-hgt+rad} V${base} Z` :
        `M${x},${base} V${base+hgt-rad} Q${x},${base+hgt} ${x+rad},${base+hgt} H${x+bw-rad} Q${x+bw},${base+hgt} ${x+bw},${base+hgt-rad} V${base} Z`;
      g.append(s('path', {
        class: 'mark',
        d,
        fill: v >= 0 ? '#2a9d6f' : '#c1121f'
      }));
    }
    const col = r.outcome === 'win' ? '#2a9d6f' : r.outcome === 'loss' ? '#c1121f' : '#6b7280';
    g.append(s('rect', {
      x: cx - 10,
      y: bottom - 18,
      width: 20,
      height: 20,
      rx: 4,
      fill: col
    }));
    g.append(s('text', {
      x: cx,
      y: bottom - 4,
      'text-anchor': 'middle',
      'font-size': 11,
      'font-weight': 700,
      fill: '#fff',
      'font-family': 'Inter,system-ui'
    }, r.outcome === 'win' ? 'W' : r.outcome === 'loss' ? 'L' : '–'));
    const yr = r.date.slice(0, 4);
    if (yr !== lastYear && (lastX == null || cx - lastX >= (compact ? 34 : 40))) {
      svg.append(s('text', {
        x: cx,
        y: bottom + 22,
        'text-anchor': 'middle',
        'font-size': 11,
        fill: '#7f8794',
        'font-family': 'Inter,system-ui'
      }, yr));
      lastX = cx;
    }
    lastYear = yr;
    bindTip(g, () => [h('strong', {
      text: signed(v) + ' / min'
    }), h('div', {
      text: 'vs ' + r.opponent
    }), h('div', {
      class: 'r'
    }, h('span', {
      text: niceDate(r.date)
    }), h('b', {
      text: (r.outcome === 'win' ? 'Win' : r.outcome === 'loss' ? 'Loss' : 'Draw/NC')
    })), h('div', {
      class: 'r'
    }, h('span', {
      text: 'Method'
    }), h('b', {
      text: r.method || '—'
    })), h('div', {
      class: 'r'
    }, h('span', {
      text: 'Sig. landed / absorbed'
    }), h('b', {
      text: r.own.sig_strikes_landed + ' / ' + r.opponent_stats.sig_strikes_landed
    }))]);
    svg.append(g);
  });
  return h('div', {
    class: 'chart'
  }, svg);
}

function strikeMap(m) {
  const t = m.sig_targets,
    total = t.head + t.body + t.leg;
  if (!total) return h('p', {
    class: 'muted',
    text: 'No significant strikes recorded in this window.'
  });
  const share = {
      head: t.head / total,
      body: t.body / total,
      leg: t.leg / total
    },
    mx = Math.max(share.head, share.body, share.leg);
  const op = k => (0.28 + 0.72 * share[k] / mx).toFixed(2);
  const fig = s('svg', {
      viewBox: '0 0 120 250',
      'aria-hidden': 'true'
    },
    s('circle', {
      cx: 60,
      cy: 26,
      r: 20,
      style: 'fill:var(--accent)',
      'fill-opacity': op('head')
    }),
    s('rect', {
      x: 53,
      y: 46,
      width: 14,
      height: 10,
      fill: '#2a2e38'
    }),
    s('rect', {
      x: 16,
      y: 60,
      width: 15,
      height: 72,
      rx: 7,
      fill: '#2a2e38'
    }), s('rect', {
      x: 89,
      y: 60,
      width: 15,
      height: 72,
      rx: 7,
      fill: '#2a2e38'
    }),
    s('rect', {
      x: 34,
      y: 56,
      width: 52,
      height: 84,
      rx: 14,
      style: 'fill:var(--accent)',
      'fill-opacity': op('body')
    }),
    s('rect', {
      x: 35,
      y: 144,
      width: 23,
      height: 100,
      rx: 10,
      style: 'fill:var(--accent)',
      'fill-opacity': op('leg')
    }), s('rect', {
      x: 62,
      y: 144,
      width: 23,
      height: 100,
      rx: 10,
      style: 'fill:var(--accent)',
      'fill-opacity': op('leg')
    }));
  const rows = ['head', 'body', 'leg'].map(k => h('div', {
    class: 'target'
  }, h('span', {
    class: 'k',
    text: k
  }), h('div', {
    class: 'bar'
  }, h('i', {
    style: `width:${(share[k]*100).toFixed(1)}%`
  })), h('span', {
    class: 'v',
    text: Math.round(share[k] * 100) + '%'
  }), h('small', {
    text: int(t[k]) + ' landed'
  })));
  const p = m.sig_positions,
    ptot = p.distance + p.clinch + p.ground;
  const cols = {
    distance: 'var(--pos-1)',
    clinch: 'var(--pos-2)',
    ground: 'var(--pos-3)'
  };
  const pos = ptot ? h('div', null, h('div', {
      class: 'eyebrow',
      style: 'margin-top:22px',
      text: 'Where they land'
    }),
    h('div', {
      class: 'stack'
    }, ['distance', 'clinch', 'ground'].map(k => {
      const i = h('i', {
        style: `width:${p[k]/ptot*100}%;background:${cols[k]}`,
        tabindex: 0
      });
      bindTip(i, () => [h('strong', {
        text: Math.round(p[k] / ptot * 100) + '%'
      }), h('div', {
        text: k[0].toUpperCase() + k.slice(1) + ' · ' + int(p[k]) + ' landed'
      })]);
      return i;
    })),
    h('div', {
      class: 'legend'
    }, ['distance', 'clinch', 'ground'].map(k => h('span', null, h('i', {
      style: 'background:' + cols[k]
    }), k[0].toUpperCase() + k.slice(1) + ' ', h('b', {
      text: Math.round(p[k] / ptot * 100) + '%'
    }))))) : null;
  return h('div', null, h('div', {
    class: 'strikemap'
  }, fig, h('div', {
    class: 'targets'
  }, rows)), pos);
}

const METHOD_KEYS = [
  ['ko', 'KO/TKO', 'var(--ko)'],
  ['sub', 'Submission', 'var(--sub)'],
  ['dec', 'Decision', 'var(--dec)'],
  ['other', 'Other', 'var(--oth)']
];

function methods(m) {
  const rb = m.results_by_method,
    rows = [];
  for (const [outcome, label] of [
      ['win', 'Wins'],
      ['loss', 'Losses']
    ]) {
    const c = rb[outcome],
      tot = METHOD_KEYS.reduce((a, [k]) => a + c[k], 0);
    const stack = h('div', {
      class: 'stack'
    });
    if (tot)
      for (const [k, name, col] of METHOD_KEYS) {
        if (!c[k]) continue;
        const share = c[k] / tot;
        const i = h('i', {
          style: `width:${share*100}%;background:${col}`,
          tabindex: 0
        });
        if (share >= .09) i.textContent = c[k];
        bindTip(i, () => [h('strong', {
          text: c[k] + ' ' + (c[k] === 1 ? outcome : label.toLowerCase())
        }), h('div', {
          text: name + ' · ' + Math.round(share * 100) + '%'
        })]);
        stack.append(i);
      }
    else stack.append(h('i', {
      style: 'width:100%;background:var(--surface-3)'
    }));
    rows.push(h('div', {
      class: 'method-row'
    }, h('span', {
      class: 'k',
      text: label
    }), stack, h('span', {
      class: 'n',
      text: tot
    })));
  }
  const w = rb.win,
    wt = w.ko + w.sub + w.dec + w.other,
    fin = wt ? (w.ko + w.sub) / wt : null;
  return h('div', null,
    h('div', {
      style: 'display:flex;align-items:baseline;gap:10px;margin-bottom:6px'
    }, h('span', {
      class: 'finish',
      text: fin == null ? '—' : Math.round(fin * 100) + '%'
    }), h('span', {
      class: 'muted',
      text: 'of wins by finish'
    })),
    rows, h('div', {
      class: 'legend',
      style: 'margin-top:10px'
    }, METHOD_KEYS.map(([k, name, col]) => h('span', null, h('i', {
      style: 'background:' + col
    }), name))));
}

function meters(r, group) {
  const P = r.percentiles || {};
  return h('div', {
    class: 'meters'
  }, METRICS.filter(m => m.group === group).map(m => {
    const v = r.metrics[m.key],
      gp = goodPct(r, m),
      info = P.eligible && P.values[m.key];
    const track = h('div', {
      class: 'track' + (gp == null ? ' none' : '')
    });
    if (gp != null) {
      track.append(h('div', {
        class: 'fill',
        style: `width:${Math.max(1.5,gp)}%`
      }));
      track.append(h('div', {
        class: 'med',
        style: 'left:50%',
        title: 'Division median'
      }));
    }
    const node = h('div', {
        class: 'meter',
        tabindex: 0
      }, h('span', {
        class: 'lbl',
        text: m.label
      }),
      h('span', {
        class: 'val'
      }, m.f(v), gp != null ? h('small', {
        class: 'pct' + (gp >= 90 ? ' elite' : ''),
        text: ordinal(gp) + ' pct'
      }) : null), track);
    if (info) bindTip(node, () => [h('strong', {
      text: m.f(v)
    }), h('div', {
      text: m.label
    }), h('div', {
      class: 'r'
    }, h('span', {
      text: P.scope + ' median'
    }), h('b', {
      text: m.f(info.median)
    })), h('div', {
      class: 'r'
    }, h('span', {
      text: 'Percentile rank'
    }), h('b', {
      text: Math.round(gp) + '% · ' + info.pool + ' fighters'
    }))].concat(m.lower ? [h('div', {
      text: 'Lower is better here.'
    })] : []));
    return node;
  }));
}

/* ================= fighter page ================= */
function fitDivisionWatermark() {
  const node = document.querySelector('.division-watermark');
  if (!node) return;
  node.style.removeProperty('font-size');
  const size = parseFloat(getComputedStyle(node).fontSize),
    width = node.clientWidth,
    needed = node.scrollWidth;
  if (width > 0 && needed > width) node.style.fontSize = Math.floor(size * Math.max(0, width - 2) /
    needed * 100) / 100 + 'px';
}

function tapeItem(label, value, extra) {
  return h('div', null, h('span', {
    text: label
  }), h('b', null, value ?? '—', extra ? h('em', {
    text: extra
  }) : null));
}

function heroCard(r) {
  const p = r.profile,
    sm = r.summary;
  const add = h('button', {
    class: 'btn primary',
    onclick: () => addToMatchup(r)
  }, inMatchup(r.id) ? '✓ In matchup' : '+ Add to matchup');
  return h('section', {
      class: 'card hero',
      'data-division': sm.division || ''
    },
    sm.division ? h('span', {
      class: 'division-watermark',
      'aria-hidden': 'true',
      text: sm.division
    }) : null,
    avatar(r, 'portrait'),
    h('div', null, statusBadges(r), h('h1', {
        class: 'fname distressed',
        text: r.name
      }),
      h('div', {
          class: 'record'
        },
        h('div', {
          class: 'big'
        }, recordText(sm.career), h('small', {
          text: 'UFC record'
        })),
        h('div', {
          class: 'big'
        }, streakText(sm.streak), h('small', {
          text: 'Streak'
        })),
        r.history.length ? h('div', null, h('div', {
          class: 'eyebrow',
          style: 'margin-bottom:8px',
          text: 'Last ' + Math.min(10, r.history.length)
        }), formStrip(r.history, 10)) : null),
      h('div', {
          class: 'tape'
        },
        tapeItem('Height', feet(p.height_inches), p.height_inches != null ? Math.round(p
          .height_inches) + ' in' : null),
        tapeItem('Reach', p.reach_inches != null ? Math.round(p.reach_inches) + ' in' : null, feet(p
          .reach_inches)),
        tapeItem('Weight', p.weight_lbs != null ? Math.round(p.weight_lbs) + ' lb' : null, p
          .weight_lbs != null ? Math.round(p.weight_lbs * 0.4536) + ' kg' : null),
        tapeItem('Age', sm.age), tapeItem('Stance', p.stance)),
      h('div', {
        class: 'hero-actions'
      }, add)));
}

function tiles(r) {
  const m = r.metrics;
  const T = [
    ['Sig. strikes landed / min', 'sig_landed_per_minute', fmt(m.sig_landed_per_minute)],
    ['Striking differential / min', 'sig_differential_per_minute', signed(m
      .sig_differential_per_minute)],
    ['Takedown defense', 'takedown_defense', pct(m.takedown_defense)],
    ['Knockdowns / 5 min', 'knockdowns_per_15_minutes', perFive(m.knockdowns_per_15_minutes)]
  ];
  return h('div', {
    class: 'tiles'
  }, T.map(([label, key, val]) => {
    const mm = METRICS.find(x => x.key === key),
      gp = goodPct(r, mm);
    return h('div', {
      class: 'tile'
    }, h('div', {
      class: 'lbl',
      text: label
    }), h('div', {
      class: 'num',
      text: val
    }), h('div', {
      class: 'rank'
    }, gp == null ? 'No division rank in this window' : [gp >= 90 ? h('b', {
      text: 'Top ' + Math.max(1, Math.round(100 - gp)) + '%'
    }) : ordinal(gp) + ' percentile', ' · ' + r.percentiles.scope]));
  }));
}

function historyList(r, limit) {
  const list = h('div', {
    class: 'history'
  });
  list.append(h('div', {
    class: 'hrow head'
  }, h('span', {
    text: 'Date'
  }), h('span', {
    text: ''
  }), h('span', {
    text: 'Opponent'
  }), h('span', {
    class: 'meth-col',
    text: 'Method'
  }), h('span', {
    class: 'ss-col',
    text: 'Sig. landed / absorbed'
  })));
  const rows = limit ? r.history.slice(0, limit) : r.history;
  for (const f of rows) {
    const own = f.own.sig_strikes_landed,
      opp = f.opponent_stats.sig_strikes_landed,
      tot = own + opp || 1;
    const when = [f.result_round ? 'R' + f.result_round : null, f.result_time].filter(Boolean).join(
      ' · ');
    list.append(h('div', {
        class: 'hrow'
      },
      h('span', {
        class: 'date',
        text: niceDate(f.date)
      }),
      h('span', {
        class: 'chip ' + f.outcome,
        title: f.outcome,
        text: f.outcome === 'win' ? 'W' : f.outcome === 'loss' ? 'L' : '–'
      }),
      h('span', null, h('button', {
        class: 'opp',
        onclick: () => go('#/fighter/' + f.opponent_id),
        text: f.opponent
      }), f.title_bout ? h('span', {
        class: 'title-tag',
        text: 'TITLE'
      }) : null, h('span', {
        class: 'sub',
        text: (f.weight_class || '').replace(/ Bout$/, '')
      })),
      h('span', {
        class: 'meth meth-col'
      }, h('b', {
        text: f.method || '—'
      }), h('span', {
        class: 'sub',
        text: when
      })),
      h('span', {
        class: 'ss ss-col'
      }, own + ' / ' + opp, h('span', {
        class: 'sbar'
      }, h('i', {
        style: `width:${own/tot*100}%;background:var(--win)`
      }), h('i', {
        style: `width:${opp/tot*100}%;background:var(--surface-3)`
      })))));
    if (f.reviewed_result) list.append(h('div', {
      class: 'amend',
      text: 'Result amended: ' + (f.reviewed_result.reason || f.method) +
        '. Originally recorded as ' + (f.frozen_result.source_winner_label || 'unknown') +
        '; date the amendment took effect is unknown.'
    }));
  }
  return list;
}

function windowNote(r) {
  const m = r.metrics;
  return h('div', {
    class: 'window-note'
  }, h('span', {
    class: 'eyebrow',
    text: 'Measuring'
  }), h('span', null, h('b', {
    text: windowLabel()
  }), ' before ' + niceDate(state.before) + ' · ', h('b', {
    text: m.bouts + (m.bouts === 1 ? ' fight' : ' fights')
  }), ', ' + fmt(m.minutes, 0) + ' minutes · window record ', h('b', {
    text: m.wins + '–' + m.losses + (m.other_results ? '–' + m.other_results : '')
  })));
}

function renderFighter(r) {
  const c = $('content');
  const P = r.percentiles || {};
  const rankNote = P.eligible ?
    `Bar = percentile among ${P.pool_fighters} ${P.scope==='All divisions'?'fighters':P.scope.toLowerCase()+'s'} in the same window · tick = median` :
    (P.reason || 'Not enough fights in this window for a ranking.');
  const showAll = r.history.length <= 12;
  const hist = h('div', null, historyList(r, showAll ? 0 : 12));
  const more = showAll ? null : h('button', {
    class: 'btn more',
    onclick: () => {
      hist.replaceChildren(historyList(r, 0));
      more.remove();
    },
    text: 'Show all ' + r.history.length + ' fights'
  });
  const has = r.metrics.bouts > 0,
    any = r.history.length > 0;
  c.replaceChildren(...[
    heroCard(r), windowNote(r),
    has ? tiles(r) : h('div', {
      class: 'card empty',
      text: any ? 'No fights in this window.' :
        'No UFC fights with recorded stats before this date. This is a profile-only entry.'
    }),
    h('div', {
      class: 'spacer'
    }),
    r.metrics.bouts ? h('div', {
        class: 'grid g2'
      },
      h('section', {
        class: 'card'
      }, h('div', {
        class: 'section-title'
      }, h('h3', {
        text: 'Striking'
      }), h('small', {
        text: rankNote
      })), meters(r, 'Striking')),
      h('section', {
        class: 'card'
      }, h('div', {
        class: 'section-title'
      }, h('h3', {
        text: 'Grappling'
      }), h('small', {
        text: r.metrics.control_observed_bouts + ' of ' + r.metrics.bouts +
          ' fights have control time'
      })), meters(r, 'Grappling'))) : null,
    h('div', {
      class: 'spacer'
    }),
    r.metrics.bouts ? h('div', {
        class: 'grid g2'
      },
      h('section', {
        class: 'card'
      }, h('div', {
        class: 'section-title'
      }, h('h3', {
        text: 'Strike map'
      }), h('small', {
        text: 'Significant strikes landed, by target'
      })), strikeMap(r.metrics)),
      h('section', {
        class: 'card'
      }, h('div', {
        class: 'section-title'
      }, h('h3', {
        text: 'How fights end'
      }), h('small', {
        text: windowLabel()
      })), methods(r.metrics))) : null,
    h('div', {
      class: 'spacer'
    }),
    any ? h('section', {
      class: 'card'
    }, h('div', {
      class: 'section-title'
    }, h('h3', {
      text: 'Fight-by-fight striking'
    }), h('small', {
      text: 'Sig. strikes landed minus absorbed, per minute · last ' + Math.min(innerWidth <
        700 ? 10 : 20, r.history.length) + ' fights · hover or tap a bar'
    })), timeline(r.history)) : null,
    any ? h('div', {
      class: 'spacer'
    }) : null,
    any ? h('section', {
      class: 'card'
    }, h('div', {
      class: 'section-title'
    }, h('h3', {
      text: 'Fight history'
    }), h('small', {
      text: r.history.length + ' UFC fights before ' + niceDate(state.before)
    })), hist, more) : null,
    provenance([r])
  ].filter(Boolean));
  fitDivisionWatermark();
}

function provenance(reports) {
  return h('details', {
    class: 'prov'
  }, h('summary', {
    text: 'Data provenance'
  }), reports.map(r => h('p', null, h('b', {
    text: r.name + ': '
  }), 'source ID ' + r.profile.source_fighter_id + ' · ', r.profile.source_url ? h('a', {
    href: r.profile.source_url,
    target: '_blank',
    rel: 'noopener',
    text: 'source profile'
  }) : 'no source URL', ' · measurements from profile snapshot' + (r.roster && r.roster.as_of ?
    ' · roster as of ' + r.roster.as_of : '') + (r.roster && r.roster.image_credit ?
    ' · image: ' + r.roster.image_credit : ''))));
}

/* ================= compare page ================= */
function matchupNameLines(name) {
  const words = name.trim().split(/\s+/);
  if (words.length < 2) return words;
  // Balance visual word groups without assuming where a surname starts.
  let split = 1,
    best = Infinity;
  for (let i = 1; i < words.length; i++) {
    const diff = Math.abs(words.slice(0, i).join(' ').length - words.slice(i).join(' ').length);
    if (diff < best) {
      best = diff;
      split = i;
    }
  }
  return [words.slice(0, split).join(' '), words.slice(split).join(' ')];
}

function fitMatchupNames() {
  const headings = [...document.querySelectorAll('.faceoff .fname')];
  if (!headings.length) return;
  // Measure at the CSS size, then give both fighters the same fitted size.
  // Repeating this after a resize must also let the type grow back to normal.
  headings.forEach(node => node.style.removeProperty('font-size'));
  const base = Math.min(...headings.map(node => parseFloat(getComputedStyle(node).fontSize)));
  const ratio = Math.min(1, ...headings.map(node => {
    const width = node.clientWidth,
      needed = Math.max(...[...node.querySelectorAll('.name-line')].map(line => line.scrollWidth));
    return width > 0 && needed > width ? Math.max(0, width - 2) / needed : 1;
  }));
  const size = Math.floor(base * ratio * 100) / 100;
  headings.forEach(node => node.style.fontSize = size + 'px');
}

function corner(r, side) {
  const sm = r.summary;
  return h('div', {
      class: 'corner ' + side
    }, avatar(r, 'portrait ' + side),
    h('div', {
        class: 'corner-info'
      }, h('div', {
        class: 'corner-label',
        text: side === 'red' ? 'Red corner' : 'Blue corner'
      }),
      h('h2', {
        class: 'fname'
      }, h('button', {
        class: 'opp',
        'aria-label': r.name,
        onclick: () => go('#/fighter/' + r.id)
      }, matchupNameLines(r.name).map((line, i) => h('span', {
        class: 'name-line distressed',
        text: (i ? ' ' : '') + line
      })))),
      h('div', {
        class: 'rec',
        text: recordText(sm.career) + '  ·  ' + streakText(sm.streak)
      }), h('div', {
        style: 'height:10px'
      }), statusBadges(r)));
}

function totRow(label, a, b, opts = {}) {
  const {
    better,
    fmtA,
    fmtB,
    note
  } = opts;
  const edge = better == null ? 0 : better(a, b);
  const L = h('div', {
    class: 'l'
  }, h('span', {
    class: 'v' + (edge > 0 ? ' edge' : '')
  }, edge > 0 ? h('span', {
    class: 'edge-mark'
  }) : null, fmtA ?? (a ?? '—')));
  const R = h('div', {
    class: 'r'
  }, h('span', {
    class: 'v' + (edge < 0 ? ' edge' : '')
  }, fmtB ?? (b ?? '—'), edge < 0 ? h('span', {
    class: 'edge-mark'
  }) : null));
  return h('div', {
    class: 'row'
  }, L, h('div', {
    class: 'c'
  }, label, note ? h('div', {
    style: 'text-transform:none;letter-spacing:0;font-weight:500;margin-top:3px',
    text: note
  }) : null), R);
}
const higher = (a, b) => a == null || b == null || a === b ? 0 : (a > b ? 1 : -1);

function taleOfTape(A, B) {
  const pa = A.profile,
    pb = B.profile;
  const diff = (x, y, u) => x != null && y != null && Math.round(x) !== Math.round(y) ? (Math.abs(Math
    .round(x) - Math.round(y)) + ' ' + u + ' edge') : null;
  return h('div', {
      class: 'tot'
    },
    totRow('UFC record', null, null, {
      fmtA: recordText(A.summary.career),
      fmtB: recordText(B.summary.career)
    }),
    totRow('Last 5', null, null, {
      fmtA: h('span', {
        style: 'display:inline-flex'
      }, formStrip(A.history, 5)),
      fmtB: h('span', {
        style: 'display:inline-flex'
      }, formStrip(B.history, 5))
    }),
    totRow('Streak', null, null, {
      fmtA: streakText(A.summary.streak),
      fmtB: streakText(B.summary.streak)
    }),
    totRow('Age', A.summary.age, B.summary.age),
    totRow('Height', pa.height_inches, pb.height_inches, {
      better: higher,
      fmtA: feet(pa.height_inches) || '—',
      fmtB: feet(pb.height_inches) || '—',
      note: diff(pa.height_inches, pb.height_inches, 'in')
    }),
    totRow('Reach', pa.reach_inches, pb.reach_inches, {
      better: higher,
      fmtA: pa.reach_inches != null ? Math.round(pa.reach_inches) + '″' : '—',
      fmtB: pb.reach_inches != null ? Math.round(pb.reach_inches) + '″' : '—',
      note: diff(pa.reach_inches, pb.reach_inches, 'in')
    }),
    totRow('Weight', null, null, {
      fmtA: pa.weight_lbs != null ? Math.round(pa.weight_lbs) + ' lb' : '—',
      fmtB: pb.weight_lbs != null ? Math.round(pb.weight_lbs) + ' lb' : '—'
    }),
    totRow('Stance', pa.stance, pb.stance),
    totRow('Division', A.summary.division, B.summary.division),
    totRow('UFC fights', A.available_bouts, B.available_bouts),
    totRow('Title fights', A.summary.title_bouts, B.summary.title_bouts),
    totRow('Last fight', null, null, {
      fmtA: ago(A.summary.last_bout, state.before) || '—',
      fmtB: ago(B.summary.last_bout, state.before) || '—'
    }));
}

function duel(A, B) {
  const box = h('div', {
    class: 'duel'
  });
  let group = null;
  for (const m of METRICS) {
    if (m.group !== group) {
      group = m.group;
      box.append(h('div', {
        class: 'group-label',
        text: group
      }));
    }
    const a = A.metrics[m.key],
      b = B.metrics[m.key];
    const edge = a == null || b == null || a === b ? 0 : ((m.lower ? a < b : a > b) ? 1 : -1);
    const ga = goodPct(A, m),
      gb = goodPct(B, m);
    const row = h('div', {
        class: 'drow',
        tabindex: 0
      },
      h('div', {
        class: 'vc l'
      }, h('span', {
        class: 'v' + (edge > 0 ? ' edge' : '')
      }, edge > 0 ? h('span', {
        class: 'edge-mark',
        style: 'border-right:7px solid var(--red);margin-right:6px'
      }) : null, m.f(a)), h('small', {
        class: 'u',
        text: m.unit
      }), ga != null ? h('small', {
        class: 'p' + (ga >= 90 ? ' elite' : ''),
        text: ordinal(ga) + ' pct'
      }) : null),
      h('div', {
        class: 'mid'
      }, h('div', {
        class: 'name',
        text: m.label
      }), h('div', {
        class: 'bars'
      }, h('div', {
        class: 'lb'
      }, ga != null ? h('i', {
        style: `width:${Math.max(2,ga)}%`
      }) : null), h('div', {
        class: 'rb'
      }, gb != null ? h('i', {
        style: `width:${Math.max(2,gb)}%`
      }) : null))),
      h('div', {
        class: 'vc'
      }, h('span', {
        class: 'v' + (edge < 0 ? ' edge' : '')
      }, m.f(b), edge < 0 ? h('span', {
        class: 'edge-mark',
        style: 'border-left:7px solid var(--blue);margin-left:6px'
      }) : null), h('small', {
        class: 'u',
        text: m.unit
      }), gb != null ? h('small', {
        class: 'p' + (gb >= 90 ? ' elite' : ''),
        text: ordinal(gb) + ' pct'
      }) : null));
    bindTip(row, () => [h('div', {
      text: m.label + (m.lower ? ' (lower is better)' : '')
    }), h('div', {
      class: 'r'
    }, h('span', {
      text: A.name
    }), h('b', {
      text: m.f(a) + (ga != null ? ' · ' + ordinal(ga) + ' pct' : '')
    })), h('div', {
      class: 'r'
    }, h('span', {
      text: B.name
    }), h('b', {
      text: m.f(b) + (gb != null ? ' · ' + ordinal(gb) + ' pct' : '')
    }))]);
    box.append(row);
  }
  return box;
}

function renderCompare(res) {
  const [A, B] = res.fighters, c = $('content');
  const scopeNote = (r) => r.percentiles && r.percentiles.eligible ? r.percentiles.scope : 'unranked';
  c.replaceChildren(...[
    h('section', {
      class: 'card faceoff'
    }, corner(A, 'red'), h('div', {
      class: 'bigvs'
    }, h('span', {
      class: 'distressed',
      text: 'VS'
    })), corner(B, 'blue')),
    windowNoteCompare(A, B),
    h('div', {
        class: 'grid g2'
      },
      h('section', {
        class: 'card'
      }, h('div', {
        class: 'section-title'
      }, h('h3', {
        text: 'Tale of the tape'
      }), h('small', {
        text: 'Profile snapshot · age at cutoff'
      })), taleOfTape(A, B)),
      h('section', {
          class: 'card'
        }, h('div', {
          class: 'section-title'
        }, h('h3', {
          text: 'Head to head'
        }), h('small', {
          text: 'Same cutoff, same window'
        })),
        h('div', {
          class: 'key'
        }, h('span', null, h('i', {
          style: 'background:var(--red)'
        }), A.name), h('span', null, B.name, h('i', {
          style: 'background:var(--blue)'
        }))),
        h('p', {
          class: 'meta-line',
          style: 'margin:6px 0 8px',
          text: 'Bar length = percentile within each fighter’s own division (' + scopeNote(A) + (
              scopeNote(A) === scopeNote(B) ? '' : ' / ' + scopeNote(B)) +
            '); longer is better. Arrow marks the better raw number.'
        }),
        duel(A, B))),
    h('div', {
      class: 'spacer'
    }),
    h('div', {
      class: 'grid g2'
    }, [A, B].map((r, i) => h('section', {
      class: 'card'
    }, h('div', {
      class: 'section-title'
    }, h('h3', null, h('span', {
      style: `display:inline-block;width:10px;height:10px;border-radius:2px;margin-right:10px;vertical-align:3px;background:var(--${i?'blue':'red'})`
    }), r.name), h('small', {
      text: 'Strike map'
    })), r.metrics.bouts ? strikeMap(r.metrics) : h('p', {
      class: 'muted',
      text: 'No fights in window.'
    })))),
    h('div', {
      class: 'spacer'
    }),
    h('div', {
      class: 'grid g2'
    }, [A, B].map((r, i) => h('section', {
      class: 'card'
    }, h('div', {
      class: 'section-title'
    }, h('h3', null, h('span', {
      style: `display:inline-block;width:10px;height:10px;border-radius:2px;margin-right:10px;vertical-align:3px;background:var(--${i?'blue':'red'})`
    }), r.name), h('small', {
      text: 'How fights end'
    })), methods(r.metrics)))),
    h('div', {
      class: 'spacer'
    }),
    ...[A, B].map((r, i) => h('section', {
      class: 'card',
      style: 'margin-bottom:18px'
    }, h('div', {
      class: 'section-title'
    }, h('h3', null, h('span', {
      style: `display:inline-block;width:10px;height:10px;border-radius:2px;margin-right:10px;vertical-align:3px;background:var(--${i?'blue':'red'})`
    }), r.name + ' · fight by fight'), h('small', {
      text: 'Sig. strike differential per minute, last ' + Math.min(innerWidth < 700 ? 10 :
        20, r.history.length)
    })), timeline(r.history))),
    h('p', {
      class: 'muted',
      style: 'font-size:13px',
      text: 'Descriptive comparison of recorded UFC fights. Numbers are not adjusted for opponent quality and do not predict a winner.'
    }),
    provenance([A, B])
  ].filter(Boolean));
  fitMatchupNames();
}
const fights = n => n + (n === 1 ? ' fight' : ' fights');

function windowNoteCompare(A, B) {
  const small = [A, B].filter(r => r.metrics.bouts < 3).map(r => r.name);
  return h('div', {
    class: 'window-note'
  }, h('span', {
    class: 'eyebrow',
    text: 'Measuring'
  }), h('span', null, h('b', {
    text: windowLabel()
  }), ' before ' + niceDate(state.before) + ' · ' + A.name + ' ', h('b', {
    text: fights(A.metrics.bouts)
  }), ' · ' + B.name + ' ', h('b', {
    text: fights(B.metrics.bouts)
  })), small.length ? h('span', {
    class: 'badge',
    style: 'color:#f3cf7e',
    text: 'Small sample: ' + small.join(', ')
  }) : null);
}

/* ================= home ================= */
const PICKS = ['Charles Oliveira', 'Max Holloway']; /* featured matchup */
async function renderHome() {
  const m = state.meta,
    c = $('content');
  const archiveLine = m ?
    int(m.total_bouts) + ' recorded bouts · ' + m.earliest_bout.slice(0, 4) + '–' + m.latest_bout
    .slice(0, 4) :
    'The recorded UFC archive';
  c.replaceChildren(
    h('section', {
        class: 'editorial-lead'
      },
      h('div', {
          class: 'lead-copy'
        },
        h('div', {
          class: 'issue-line'
        }, h('span', {
          text: 'UPSET / Fighter research'
        }), h('span', {
          text: 'Local edition'
        })),
        h('h1', null, 'Know the', h('br'), h('em', {
          text: 'matchup.'
        })),
        h('p', {
          class: 'lead-deck',
          text: 'A closer look at the fighters, before you pick a side.'
        }),
        h('button', {
          class: 'text-link',
          onclick: () => $('search').focus(),
          text: 'Find a fighter ↗'
        }),
        h('div', {
          class: 'archive-line',
          text: archiveLine
        })),
      h('aside', {
          class: 'field-note'
        },
        h('div', {
          class: 'note-number',
          'aria-hidden': 'true',
          text: '05:00'
        }),
        h('h2', {
          text: 'One round. Same clock.'
        }),
        h('p', {
          text: 'A three-round fight and a five-round fight need a common measure. Knockdowns, takedowns and submission attempts here use five minutes of actual fight time.'
        }),
        h('p', {
          class: 'note-bottom',
          text: 'Compare the numbers. Bring your own verdict.'
        }))),
    h('section', {
        class: 'fight-poster',
        id: 'feature',
        'aria-label': 'Matchup study'
      },
      h('p', {
        text: 'Loading the matchup study…'
      })),
    h('section', {
        class: 'reading-line'
      },
      h('h2', {
        text: 'The record, in context.'
      }),
      h('p', {
        text: 'Career gives you the full picture. Switch to the last 3, 5 or 10 fights to see a smaller slice. Every page uses the date you choose.'
      }))
  );
  const found = {};
  await Promise.all(PICKS.map(async name => {
    try {
      const matches = await api('/api/fighters?q=' + encodeURIComponent(name));
      const hit = matches.find(x => x.name === name && x.recorded_bouts);
      if (hit) found[name] = hit;
    } catch {
      /* The search control still works if a featured name is unavailable. */ }
  }));
  // A filter or search may navigate away before these requests complete.
  const feature = $('feature');
  if (!feature || state.view !== 'home') return;
  const a = found['Charles Oliveira'],
    b = found['Max Holloway'];
  if (!a || !b) {
    feature.remove();
    return;
  }
  feature.replaceChildren(
    h('div', {
      class: 'poster-top'
    }, h('span', {
      text: '01 / Matchup study'
    }), h('span', {
      text: 'Stats, not a forecast'
    })),
    h('div', {
        class: 'poster-names'
      },
      h('div', {
        class: 'poster-name'
      }, h('span', {
        text: 'Charles'
      }), h('strong', {
        text: 'Oliveira'
      })),
      h('div', {
        class: 'poster-vs',
        text: 'vs'
      }),
      h('div', {
        class: 'poster-name blue-name'
      }, h('span', {
        text: 'Max'
      }), h('strong', {
        text: 'Holloway'
      }))),
    h('div', {
        class: 'poster-bottom'
      },
      h('p', {
        text: 'Striking. Grappling. The fights behind the averages.'
      }),
      h('button', {
        class: 'btn paper',
        onclick: () => go('#/compare/' + a.id + '/' + b.id),
        text: 'Open the matchup →'
      }))
  );
}

/* ================= matchup tray ================= */
function inMatchup(id) {
  return state.matchup.some(x => x && x.id === id);
}

function addToMatchup(r) {
  if (inMatchup(r.id)) return;
  const i = state.matchup[0] ? 1 : 0;
  state.matchup[i] = {
    id: r.id,
    name: r.name
  };
  renderTray();
  if (state.matchup[0] && state.matchup[1]) go('#/compare/' + state.matchup[0].id + '/' + state.matchup[
    1].id);
  else route();
}

function renderTray() {
  const any = state.matchup.some(Boolean);
  $('tray').classList.toggle('show', any);
  state.matchup.forEach((f, i) => {
    const slot = $('slot' + i);
    slot.className = 'slot' + (f ? '' : ' is-empty');
    const children = [h('i', {
      style: 'background:var(--' + (i ? 'blue' : 'red') + ')'
    }), h('span', {
      text: f ? f.name : (i ? 'Blue corner' : 'Red corner')
    })];
    if (f) children.push(h('button', {
      'aria-label': 'Remove ' + f.name,
      onclick: () => {
        state.matchup[i] = null;
        renderTray();
        if (state.view === 'compare') go('#/fighter/' + (state.matchup[1 - i] || f).id);
        else route();
      },
      text: '×'
    }));
    slot.replaceChildren(...children);
  });
  const [a, b] = state.matchup, parts = location.hash.replace(/^#\/?/, '').split('/');
  const complete = !!(a && b),
    viewing = complete && parts[0] === 'compare' && parts[1] === a.id && parts[2] === b.id;
  $('go').disabled = !complete;
  $('go').hidden = !complete || viewing;
}
$('go').onclick = () => {
  if (!$('go').disabled) go('#/compare/' + state.matchup[0].id + '/' + state.matchup[1].id);
};

/* ================= routing ================= */
function go(hash) {
  if (location.hash === hash) route();
  else location.hash = hash;
}
let version = 0;
async function route() {
  const v = ++version,
    parts = location.hash.replace(/^#\/?/, '').split('/');
  renderTray();
  $('error').textContent = '';
  hideTip();
  try {
    if (parts[0] === 'about') {
      state.view = 'about';
      renderAbout();
      document.title = 'Ayaan Ahmed · UPSET';
    } else if (parts[0] === 'fighter' && parts[1]) {
      state.view = 'fighter';
      $('main').classList.add('loading');
      const r = await api('/api/fighter?id=' + encodeURIComponent(parts[1]) + params());
      if (v !== version) return;
      renderFighter(r);
      document.title = r.name + ' · UPSET';
    } else if (parts[0] === 'compare' && parts[1] && parts[2]) {
      state.view = 'compare';
      $('main').classList.add('loading');
      const r = await api('/api/compare?a=' + encodeURIComponent(parts[1]) + '&b=' +
        encodeURIComponent(parts[2]) + params());
      if (v !== version) return;
      state.matchup = r.fighters.map(f => ({
        id: f.id,
        name: f.name
      }));
      renderTray();
      renderCompare(r);
      document.title = r.fighters.map(f => f.name).join(' vs ') + ' · UPSET';
    } else {
      state.view = 'home';
      await renderHome();
      if (v !== version) return;
      document.title = 'UPSET · Fighter research';
    }
    if (state.lastHash !== location.hash) scrollTo({
      top: 0
    });
    state.lastHash = location.hash;
  } catch (e) {
    if (v === version) $('error').textContent = e.message;
  } finally {
    if (v === version) $('main').classList.remove('loading');
  }
}
addEventListener('hashchange', route);
// Refit when the viewport changes or the actual display font finishes loading.
function fitResearchLabels() {
  fitMatchupNames();
  fitDivisionWatermark();
}
const labelFitObserver = new ResizeObserver(() => requestAnimationFrame(fitResearchLabels));
labelFitObserver.observe($('content'));
document.fonts.ready.then(fitResearchLabels);
document.fonts.addEventListener('loadingdone', fitResearchLabels);

/* ================= search ================= */
let timer = null,
  searchVersion = 0,
  hl = -1;
const input = $('search'),
  dd = $('dropdown');

function closeDD() {
  dd.classList.remove('open');
  input.parentElement.setAttribute('aria-expanded', 'false');
  hl = -1;
}
input.addEventListener('input', () => {
  clearTimeout(timer);
  const sv = ++searchVersion;
  timer = setTimeout(async () => {
    const q = input.value.trim();
    if (!q) {
      closeDD();
      return;
    }
    try {
      const matches = await api('/api/fighters?q=' + encodeURIComponent(q));
      if (sv !== searchVersion) return;
      dd.replaceChildren();
      hl = -1;
      if (!matches.length) dd.append(h('div', {
        class: 'opt',
        style: 'cursor:default'
      }, h('small', {
        text: 'No fighter matches “' + q + '”.'
      })));
      for (const r of matches) {
        const meta = r.recorded_bouts ? [r.division, r.recorded_bouts + ' UFC ' + (r
            .recorded_bouts === 1 ? 'fight' : 'fights'), r.last_bout ? 'last ' + r.last_bout
          .slice(0, 4) : null
        ].filter(Boolean).join(' · ') : 'Profile only · no UFC fights with stats';
        dd.append(h('button', {
          class: 'opt' + (r.recorded_bouts ? '' : ' dim'),
          role: 'option',
          onclick: () => {
            closeDD();
            input.value = '';
            input.blur();
            go('#/fighter/' + r.id);
          }
        }, h('div', null, h('b', {
          text: r.name
        }), h('small', {
          text: meta
        }))));
      }
      dd.classList.add('open');
      input.parentElement.setAttribute('aria-expanded', 'true');
    } catch (e) {
      $('error').textContent = e.message;
    }
  }, 160);
});
input.addEventListener('keydown', e => {
  const opts = [...dd.querySelectorAll('button.opt')];
  if (!opts.length) return;
  if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
    e.preventDefault();
    hl = (hl + (e.key === 'ArrowDown' ? 1 : -1) + opts.length) % opts.length;
    opts.forEach((o, i) => o.classList.toggle('hl', i === hl));
    opts[hl].scrollIntoView({
      block: 'nearest'
    });
  } else if (e.key === 'Enter') {
    (opts[hl] || opts[0]).click();
  } else if (e.key === 'Escape') closeDD();
});
document.addEventListener('click', e => {
  if (!e.target.closest('.search-wrap')) closeDD();
});
addEventListener('keydown', e => {
  if (e.key === '/' && document.activeElement !== input && !/INPUT|SELECT|TEXTAREA/.test(document
      .activeElement.tagName)) {
    e.preventDefault();
    input.focus();
  }
});

/* ================= filters ================= */
$('window').addEventListener('click', e => {
  const b = e.target.closest('button');
  if (!b) return;
  state.window = b.dataset.w;
  [...$('window').children].forEach(x => x.setAttribute('aria-pressed', x === b));
  if (state.view !== 'home') route();
});
$('before').addEventListener('change', () => {
  if (!$('before').value) return;
  state.before = $('before').value;
  if (state.view !== 'home') route();
});

/* ================= boot ================= */
api('/api/meta').then(m => {
  state.meta = m;
  const d = new Date(m.latest_bout + 'T12:00:00Z');
  d.setUTCDate(d.getUTCDate() + 1);
  state.before = d.toISOString().slice(0, 10);
  $('before').value = state.before;
  $('before').max = state.before;
  $('coverage').textContent = int(m.fighters) + ' profiles · ' + int(m.total_bouts) + ' bouts · ' + m
    .earliest_bout.slice(0, 4) + '–' + niceDate(m.latest_bout) + '.';
  $('coverage-detail').textContent = m.excluded_current_bouts +
    ' recent bouts are held back until fighter identities are confirmed.';
  renderTray();
  route();
}).catch(e => {
  $('error').textContent = e.message;
});
