/* Exercise the shipped rating component without external DOM packages.
 * Run: node tests/rating_ui_checks.cjs
 */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

class Node {
  constructor(tag = '#text', text = '') {
    this.tagName = tag.toUpperCase();
    this.tag = tag;
    this.children = [];
    this.attributes = {};
    this.dataset = {};
    this.style = {setProperty(name, value) { this[name] = String(value); }};
    this.listeners = {};
    this.text = String(text);
    this.hidden = false;
    this.className = '';
    this.classList = {
      contains: name => this.className.split(/\s+/).includes(name),
      add: (...names) => { this.className = [...new Set([...this.className.split(/\s+/).filter(Boolean), ...names])].join(' '); },
      remove: (...names) => { this.className = this.className.split(/\s+/).filter(name => !names.includes(name)).join(' '); },
      toggle: (name, force) => {
        const on = force === undefined ? !this.classList.contains(name) : force;
        if (on) this.classList.add(name); else this.classList.remove(name);
        return on;
      },
    };
  }
  append(...children) {
    for (const child of children.flat(Infinity)) {
      if (child == null || child === false) continue;
      const node = child instanceof Node ? child : new Node('#text', child);
      node.parentNode = this;
      this.children.push(node);
    }
  }
  appendChild(child) { this.append(child); return child; }
  replaceChildren(...children) { this.children = []; this.text = ''; this.append(...children); }
  set textContent(value) { this.text = String(value); this.children = []; }
  get textContent() { return this.text + this.children.map(child => child.textContent).join(''); }
  setAttribute(name, value) {
    this.attributes[name] = String(value);
    if (name === 'class') this.className = String(value);
    if (name === 'id') this.id = String(value);
    if (name === 'hidden') this.hidden = true;
    if (name.startsWith('data-')) this.dataset[name.slice(5).replace(/-([a-z])/g, (_, c) => c.toUpperCase())] = String(value);
  }
  getAttribute(name) { return name === 'class' ? this.className : this.attributes[name] ?? null; }
  removeAttribute(name) { delete this.attributes[name]; if (name === 'hidden') this.hidden = false; }
  addEventListener(name, listener) { (this.listeners[name] ||= []).push(listener); }
  showModal() { this.open = true; this.setAttribute('open', ''); }
  close() {
    this.open = false;
    this.removeAttribute('open');
    for (const listener of this.listeners.close || []) listener({target: this});
  }
  remove() {
    if (this.parentNode) this.parentNode.children = this.parentNode.children.filter(child => child !== this);
    this.parentNode = null;
  }
  focus() { this.focused = true; }
  click() {
    if (this.disabled) return;
    const event = {target: this, currentTarget: this, preventDefault() {}, stopPropagation() {}};
    this.onclick?.(event);
    for (const listener of this.listeners.click || []) listener(event);
  }
  matches(selector) {
    const attribute = selector.match(/\[([^=\]]+)(?:=['"]?([^'"\]]+)['"]?)?\]/);
    if (attribute && (this.getAttribute(attribute[1]) === null || attribute[2] && this.getAttribute(attribute[1]) !== attribute[2])) return false;
    const id = selector.match(/#([\w-]+)/);
    if (id && this.id !== id[1]) return false;
    const classes = [...selector.matchAll(/\.([\w-]+)/g)].map(match => match[1]);
    if (classes.some(name => !this.classList.contains(name))) return false;
    const tag = selector.match(/^[\w-]+/);
    return !tag || this.tag === tag[0];
  }
  querySelectorAll(selector) {
    return walk(this).slice(1).filter(node => selector.split(',').some(part => node.matches(part.trim())));
  }
  querySelector(selector) { return this.querySelectorAll(selector)[0] || null; }
}
function walk(node) { return [node, ...node.children.flatMap(walk)]; }
function find(root, predicate, message) {
  const found = walk(root).find(predicate);
  assert.ok(found, message);
  return found;
}

const context = vm.createContext({
  console, Node, document: {
    body: new Node('body'),
    documentElement: new Node('html'),
    createElement: tag => new Node(tag),
    createElementNS: (_, tag) => new Node(tag),
    createTextNode: text => new Node('#text', text),
    createDocumentFragment: () => new Node('#fragment'),
  },
});
context.window = context;
for (const file of ['research_rating_examples.js', 'research_rating.js']) {
  vm.runInContext(fs.readFileSync(path.join(__dirname, '../src/upset/web', file), 'utf8'), context);
}

// Component assertions follow the public, data-driven browser API.
const examples = context.UPSETRatingExamples;
assert.ok(Object.isFrozen(examples), 'fictional fixture list is fixed');
assert.deepEqual(Array.from(examples, example => example.id), ['champion', 'prospect', 'provisional', 'debut']);
const untouched = JSON.stringify(examples);
for (const example of examples) {
  assert.match(example.name, /^Sample /, 'fixtures must not impersonate actual fighters');
  if (!example.bouts) {
    assert.equal(example.score, null);
    assert.equal(example.parts.length, 0);
    assert.equal(example.history.length, 0);
    continue;
  }
  assert.ok(Number.isInteger(example.score) && example.score >= 60 && example.score <= 99);
  assert.equal(example.parts.length, 4);
  const skills = example.parts.filter(part => part.key !== 'resume').map(part => part.score).sort((a, b) => b - a);
  const resume = example.parts.find(part => part.key === 'resume').score;
  const combined = .5 * (.5 * skills[0] + .3 * skills[1] + .2 * skills[2]) + .5 * resume;
  assert.ok(Math.abs(combined - example.curve.combined) < 1e-9, 'illustrative weights and combined score must agree');
  assert.equal(example.curve.display, example.score);
  assert.ok(example.bouts >= 5 || example.score <= 88, 'examples should respect the limited-history display guard');
  assert.equal(example.history.at(-1).score, example.score);
  assert.ok(example.history.every(point => Math.abs(point.change) <= 5));
}

const rating = context.UPSETRating;
assert.ok(rating && typeof rating.card === 'function' && typeof rating.preview === 'function' && typeof rating.unavailable === 'function');
for (const example of examples) {
  const card = rating.card(example);
  const ring = find(card, node => node.classList.contains('rating-ring'), 'ring exists');
  const score = find(card, node => node.classList.contains('rating-score'), 'number uses its own display element');
  const breakdown = find(card, node => node.classList.contains('rating-breakdown'), 'breakdown exists');
  const infoButton = find(card, node => node.classList.contains('rating-info-button'), 'method disclosure exists');
  const info = find(card, node => node.classList.contains('rating-info-panel'), 'method panel exists');
  assert.ok(card.textContent.includes('SAMPLE'), 'illustrative scores must be marked as sample data');
  assert.equal(ring.getAttribute('aria-controls'), breakdown.id);
  assert.equal(infoButton.getAttribute('aria-controls'), info.id);
  assert.equal(ring.getAttribute('aria-expanded'), 'false');
  assert.equal(infoButton.getAttribute('aria-expanded'), 'false');
  assert.equal(breakdown.hidden, true);
  assert.equal(info.hidden, true);
  infoButton.click();
  assert.equal(info.hidden, false);
  assert.equal(infoButton.getAttribute('aria-expanded'), 'true');
  infoButton.click();
  assert.equal(info.hidden, true);
  assert.equal(infoButton.getAttribute('aria-expanded'), 'false');
  const provisional = example.bouts > 0 && example.bouts < 4;
  assert.equal(ring.classList.contains('is-provisional'), provisional, 'fewer than four bouts, not four bouts, is provisional');
  if (example.score == null) {
    assert.equal(score.textContent, '—', 'a debut must not inherit a default score');
    assert.equal(ring.disabled, true);
    assert.ok(card.textContent.includes('Rated after first UFC fight'));
    assert.equal(walk(card).filter(node => node.classList.contains('rating-part')).length, 0);
    continue;
  }
  assert.equal(score.textContent, String(example.score));
  assert.ok(!score.textContent.includes('%'), 'overall is a 60–99 rating, not a win percentage');
  assert.ok(ring.getAttribute('aria-label').includes('out of 99'));
  assert.ok(info.textContent.includes('not a measured fighter score or a win probability'));
  assert.ok(info.textContent.includes('50% résumé + 50% skills'));
  assert.ok(info.textContent.includes('Combined ' + example.curve.combined.toFixed(1)));
  assert.ok(info.textContent.includes('Prediction track record: not established'));
  assert.ok(!info.textContent.includes('57–58%'), 'a prior model result cannot become this rating’s track record');
  ring.click();
  assert.equal(breakdown.hidden, false);
  assert.equal(ring.getAttribute('aria-expanded'), 'true');
  const parts = walk(card).filter(node => node.classList.contains('rating-part'));
  const raw = find(card, node => node.classList.contains('rating-raw-panel'), 'part-level inputs panel exists');
  assert.equal(parts.length, 4);
  assert.equal(raw.hidden, true);
  for (let index = 0; index < parts.length; index++) {
    const button = parts[index], part = example.parts[index];
    button.click();
    assert.equal(raw.hidden, false);
    assert.equal(button.getAttribute('aria-expanded'), 'true');
    assert.equal(button.getAttribute('aria-controls'), raw.id);
    assert.ok(raw.textContent.includes(part.label + ' · sample inputs'));
    for (const row of part.raw) {
      assert.ok(raw.textContent.includes(row.label));
      assert.ok(raw.textContent.includes(row.value));
      if (row.percentile == null) assert.ok(raw.textContent.includes('Not available'));
      else assert.ok(raw.textContent.includes(String(row.percentile)), 'available division percentile remains visible');
    }
    for (const other of parts.filter(other => other !== button)) assert.equal(other.getAttribute('aria-expanded'), 'false');
    button.click();
    assert.equal(raw.hidden, true);
    assert.equal(button.getAttribute('aria-expanded'), 'false');
  }
  ring.click();
  assert.equal(breakdown.hidden, true);
  assert.equal(ring.getAttribute('aria-expanded'), 'false');
  const comparison = rating.card(example, {matchup: true});
  assert.ok(comparison.classList.contains('rating-matchup'));
  const matchupShape = find(comparison, node => node.classList.contains('rating-ring'));
  assert.ok(matchupShape.classList.contains('is-matchup'), 'comparison presentation retains its compact matchup context');
  assert.ok(!matchupShape.classList.contains('is-neutral'), 'latest requested rating tiers keep their color in matchup views');
}

const preview = rating.preview();
assert.ok(preview.textContent.includes('Design preview · fictional examples'));
assert.ok(preview.textContent.includes('Real fighter pages use a separate, calculated experimental rating'));
const choices = find(preview, node => node.classList.contains('rating-example-choices'));
const mount = find(preview, node => node.classList.contains('rating-example-mount'));
assert.equal(choices.children.length, examples.length);
for (let index = 0; index < examples.length; index++) {
  choices.children[index].click();
  assert.ok(mount.textContent.includes(examples[index].name));
  for (let other = 0; other < examples.length; other++) assert.equal(choices.children[other].getAttribute('aria-pressed'), String(other === index));
}
choices.children[0].click();
assert.equal(walk(mount).filter(node => node.classList.contains('rating-compact-demo')).length, 2);
assert.equal(walk(mount).filter(node => node.classList.contains('rating-badge-compact')).length, 3, 'profile and both head-to-head fighters receive compact badges');
assert.equal(walk(mount).filter(node => node.classList.contains('rating-card')).length, 0, 'expanded rating content must not consume the profile or matchup layout');
assert.equal(walk(mount).filter(node => node.classList.contains('is-matchup')).length, 2);

for (const [scoreValue, tier] of [[60,60],[69,60],[70,70],[79,70],[80,80],[89,80],[90,90],[99,90]]) {
  const sample = {...examples[0], score: scoreValue};
  for (const matchup of [false, true]) {
    const badge = rating.badge(sample, {sample: true, matchup});
    assert.ok(badge.classList.contains('rating-badge-compact'));
    assert.ok(badge.classList.contains('rating-tier-' + tier), 'tier threshold is consistent in profiles and comparisons');
    assert.equal(badge.classList.contains('is-matchup'), matchup);
    const score = find(badge, node => node.classList.contains('rating-score'));
    assert.equal(score.textContent, String(scoreValue));
    const shape = find(badge, node => node.classList.contains('rating-ring-fill'));
    assert.equal(shape.tag, 'polygon', 'the user requested an octagon, not a circular ring');
    assert.equal(shape.getAttribute('points').trim().split(/\s+/).length, 8, 'rating outline has eight vertices');
    assert.equal(shape.getAttribute('pathLength'), '99');
    assert.equal(shape.getAttribute('stroke-dasharray'), scoreValue + ' 99');
    assert.equal(badge.getAttribute('aria-haspopup'), 'dialog');
    assert.equal(walk(badge).filter(node => node.tag === 'dialog').length, 0);
    assert.equal(walk(badge).filter(node => node.classList.contains('rating-breakdown')).length, 0, 'deep content is mounted only after opening');
  }
}

const body = context.document.body;
const sampleBadge = rating.badge(examples[0], {sample: true});
assert.equal(body.children.length, 0);
sampleBadge.click();
const sampleDialog = find(body, node => node.tag === 'dialog');
assert.ok(sampleDialog.open);
assert.ok(sampleDialog.classList.contains('rating-detail-dialog'));
assert.ok(sampleDialog.textContent.includes('Fictional design example'));
assert.ok(sampleDialog.textContent.includes(examples[0].name));
assert.equal(find(sampleDialog, node => node.classList.contains('rating-breakdown')).hidden, false);
assert.equal(walk(sampleDialog).filter(node => node.classList.contains('rating-part')).length, 4);
find(sampleDialog, node => node.getAttribute('aria-label') === 'Close rating details').click();
assert.equal(body.children.length, 0, 'close button dismisses and removes the dialog');

const liveReport = {name: 'Actual fighter', score: 99, parts: examples[0].parts,
  before: '2026-11-04', window: 3, history: [{}, {}, {}],
  rating: {status: 'not_available', recorded_bouts: 3, score: 96},
  metrics: {sig_landed_per_minute: 4.2, striking_accuracy: .4, striking_defense: .6}};
for (const matchup of [false, true]) {
  const badge = rating.badge(liveReport, {matchup});
  assert.equal(find(badge, node => node.classList.contains('rating-score')).textContent, '—', 'stray top-level or API scores must never become assigned real-fighter ratings');
  assert.ok(badge.classList.contains('rating-unrated'));
  assert.ok(!badge.className.includes('rating-tier-'));
  assert.equal(badge.disabled, false, 'unrated badges still explain the rating');
  badge.click();
  const dialog = find(body, node => node.tag === 'dialog');
  assert.ok(dialog.open);
  assert.ok(dialog.textContent.includes('no overall rating has been assigned'));
  assert.ok(dialog.textContent.includes('LAST 3 FIGHTS'));
  assert.ok(dialog.textContent.includes('BEFORE 2026-11-04'));
  assert.ok(dialog.textContent.includes('40.0%'), 'real modal exposes the selected recorded stat');
  assert.equal(walk(dialog).filter(node => node.classList.contains('rating-score')).length, 0);
  assert.equal(walk(dialog).filter(node => node.classList.contains('rating-part')).length, 0, 'fictional skill scores cannot leak into actual fighter details');
  assert.equal(walk(dialog).filter(node => node.tag === 'details').length, 5, 'four actual-stat disclosures and a method disclosure are available');
  dialog.close();
  assert.equal(body.children.length, 0, 'native close/Escape path removes its dialog');
}

for (const report of [{name: 'Actual fighter', rating: {status: 'not_available', score: null}},
                      {name: 'Actual debut', history: [], rating: {status: 'not_available', score: null}}]) {
  const unavailable = rating.unavailable(report);
  assert.ok(unavailable.textContent.includes('In development'));
  assert.ok(unavailable.textContent.includes('no overall rating assigned'));
  assert.equal(walk(unavailable).filter(node => node.classList.contains('rating-score')).length, 0);
  const link = find(unavailable, node => node.tag === 'a', 'unavailable profiles link to the sample preview');
  assert.equal(link.getAttribute('href'), '#/rating-preview');
  for (const example of examples) assert.ok(!unavailable.textContent.includes(example.name));
}

// Only the bound, known experimental API contract can supply a real number.
const availableReport = {
  name: 'Live test fighter', before: '2026-11-04', window: 3,
  history: [{}, {}, {}],
  metrics: {sig_landed_per_minute: 4.2, striking_accuracy: .4, striking_defense: .6},
  rating: {
    status: 'available', version: 'upset_rating_experimental_v1', experimental: true, validated: false,
    before: '2026-11-04', data_through: '2026-10-31', event_date: '2026-06-14',
    bouts: 3, provisional: true, division: 'Lightweight', score: 85, peak: 85, change: 5,
    raw_combined: 84.7775, skills_combined: 82.97, curve_score: 98, curve_percentile: .995,
    small_history_adjustment: -10, change_adjustment: -3,
    previous_score: 80,
    part_changes: [
      {key: 'striking', label: 'Striking', previous: 84.5, current: 85.5, change: 1},
      {key: 'wrestling', label: 'Wrestling', previous: 81.4, current: 82.4, change: 1},
      {key: 'grappling', label: 'Grappling', previous: 76.5, current: 77.5, change: 1},
      {key: 'resume', label: 'Résumé', previous: 89.2, current: 90.2, change: 1},
    ],
    last_results: [{date: '2026-06-14', outcome: 'win', opponent: 'Previous opponent', method: 'Decision - Unanimous'}],
    best_wins: [{date: '2025-01-01', opponent: 'Strong earlier opponent', opponent_rating: 94, method: 'KO/TKO', fight_id: 'earlier-fight'}],
    parts: [
      {key: 'striking', label: 'Striking', score: 85.5, raw_score: (85.5 - 60) / .39,
        metrics: {sig_landed_per_minute: 4.918, striking_accuracy: .55}},
      {key: 'wrestling', label: 'Wrestling', score: 82.4, raw_score: (82.4 - 60) / .39,
        metrics: {takedown_defense: .8, control_share: null}},
      {key: 'grappling', label: 'Grappling', score: 77.5, raw_score: (77.5 - 60) / .39,
        metrics: {submission_attempts_per_15_minutes: .4}},
      {key: 'resume', label: 'Résumé', score: 90.2, raw_score: (90.2 - 60) / .39, metrics: {elo: 1660}},
    ],
    history: [{date: '2024-01-01', score: 75, change: null},
      {date: '2025-01-01', score: 80, change: 5}, {date: '2026-06-14', score: 85, change: 5}],
    model: {resume_weight: .25, skill_weights: [.5, .3, .2], training_before: '2019-01-01'},
    display_curve: {reference_before: '2019-01-01'},
    track_record: {wins: 1794, total: 2984, accuracy: 1794 / 2984, from_date: '2019-01-01',
      before_exclusive: '2026-10-26', ties_excluded: 165, unavailable_excluded: 709},
    evaluation_label: 'Previously inspected historical development data; not protected future validation.',
  },
};
const availableOriginal = JSON.stringify(availableReport);
for (const matchup of [false, true]) {
  const liveBadge = rating.badge(availableReport, {matchup});
  assert.equal(find(liveBadge, node => node.classList.contains('rating-score')).textContent, '85');
  assert.ok(liveBadge.classList.contains('rating-tier-80'));
  assert.ok(liveBadge.classList.contains('is-experimental'));
  assert.ok(liveBadge.classList.contains('is-provisional'));
  assert.equal(find(liveBadge, node => node.classList.contains('rating-scale')).textContent, 'EXP V1');
  assert.ok(liveBadge.getAttribute('aria-label').includes('Experimental v1'));
  assert.ok(liveBadge.getAttribute('title').includes('not a win probability'));
  liveBadge.click();
  const dialog = find(body, node => node.tag === 'dialog');
  assert.ok(dialog.textContent.includes('Experimental v1'));
  assert.ok(!dialog.textContent.includes('SAMPLE') && !dialog.textContent.includes('Fictional') && !dialog.textContent.includes('illustrative'), 'real ratings need real, experimental copy');
  const parts = walk(dialog).filter(node => node.classList.contains('rating-part'));
  assert.equal(parts.length, 4);
  assert.deepEqual(parts.map(node => find(node, child => child.tag === 'b').textContent), ['86', '82', '78', '90'], 'part tiles are whole numbers');
  assert.equal(walk(dialog).filter(node => node.classList.contains('rating-name')).length, 0, 'the dialog header already supplies the fighter name');
  assert.equal(walk(dialog).filter(node => node.classList.contains('rating-dialog-notice')).length, 0, 'the real dialog must not repeat its Experimental badge in a red notice');
  assert.ok(dialog.textContent.includes('+5 after win vs. Previous opponent · 80 → 85'));
  const changes = find(dialog, node => node.classList.contains('rating-part-change-row'));
  assert.ok(changes.textContent.includes('Striking +1.0') && changes.textContent.includes('Résumé +1.0'));
  const conversion = find(dialog, node => node.classList.contains('rating-visible-conversion'));
  assert.ok(conversion.textContent.includes('Combined 84.78 → above the 99th percentile of UFC rating snapshots through 2018 → curve 98 → displayed 85'));
  assert.equal(conversion.parentNode.classList.contains('rating-breakdown'), true, 'curve conversion is visible directly below the four tiles');
  const visibleNote = find(dialog, node => node.classList.contains('rating-conversion-note'));
  assert.ok(visibleNote.textContent.includes('25% résumé + 75% skills') && visibleNote.textContent.includes('historical grading scale'));
  assert.ok(visibleNote.textContent.includes('limited history (-10) and the per-date change limit (-3)'));
  const visibleTrack = find(dialog, node => node.classList.contains('rating-track-record'));
  assert.ok(visibleTrack.textContent.includes('60.1% of 2,984 evaluated fights'));
  assert.equal(find(dialog, node => node.classList.contains('rating-breakdown')).hidden, false);
  parts[0].click();
  const raw = find(dialog, node => node.classList.contains('rating-raw-panel'));
  assert.ok(raw.textContent.includes('recent-weighted model inputs'));
  assert.ok(raw.textContent.includes('4.92') && raw.textContent.includes('55.0%'));
  assert.ok(raw.textContent.includes('Unrounded component score: 85.50'));
  assert.ok(!raw.textContent.includes('th division percentile'), 'model inputs cannot invent observed percentile ranks');
  parts[1].click();
  assert.ok(raw.textContent.includes('Not available'), 'missing control remains unavailable');
  assert.ok(parts[3].textContent.includes('Explore model inputs →'), 'résumé uses the same interactive cue as the other parts');
  parts[3].click();
  assert.ok(raw.textContent.includes('Résumé · strongest rated wins'));
  assert.ok(raw.textContent.includes('Strong earlier opponent') && raw.textContent.includes('Pre-fight grade: 94'));
  assert.ok(raw.textContent.includes('their pre-fight grades under this rating version, not their current grades'));
  assert.ok(raw.textContent.includes('Unrounded component score: 90.20'));
  assert.ok(dialog.textContent.includes('Original recorded stats · last 3 fights'));
  assert.ok(dialog.textContent.includes('4.20') && dialog.textContent.includes('40.0%'), 'original recorded stats stay distinct from weighted inputs');
  const infoButton = find(dialog, node => node.getAttribute('aria-label') === 'How this experimental rating is calculated');
  infoButton.click();
  const info = find(dialog, node => node.classList.contains('rating-info-panel'));
  assert.equal(info.hidden, false);
  assert.ok(info.textContent.includes('25% résumé + 75% skills'), 'learned weights cannot retain the example’s fixed 50/50 copy');
  assert.ok(info.textContent.includes('84.78') && info.textContent.includes('curve score 98'));
  assert.ok(info.textContent.includes('99.50th historical reference percentile'));
  assert.ok(info.textContent.includes('Limited-history adjustment-10') && info.textContent.includes('Per-date change adjustment-3'));
  assert.ok(info.textContent.includes('Displayed rating85'));
  assert.ok(info.textContent.includes('2019-01-01'));
  assert.ok(dialog.textContent.includes('60.1% of 2,984 evaluated fights'));
  assert.ok(dialog.textContent.includes('Ties excluded: 165') && dialog.textContent.includes('709'));
  assert.ok(dialog.textContent.includes('not fresh future validation'));
  assert.ok(info.textContent.includes('not a measured division percentile'));
  dialog.close();
}
assert.equal(JSON.stringify(availableReport), availableOriginal, 'real rating rendering cannot mutate the served snapshot');

const negativeWin = JSON.parse(availableOriginal);
Object.assign(negativeWin.rating, {bouts: 10, provisional: false, score: 84, peak: 85, previous_score: 85,
  change: -1, curve_score: 84, curve_percentile: .8, small_history_adjustment: 0, change_adjustment: 0});
negativeWin.rating.part_changes = negativeWin.rating.parts.map(part => ({key: part.key, label: part.label,
  previous: part.score + (part.key === 'resume' ? -1 : 1), current: part.score, change: part.key === 'resume' ? 1 : -1}));
negativeWin.rating.history = [{date: '2025-01-01', score: 85, change: null}, {date: '2026-06-14', score: 84, change: -1}];
rating.badge(negativeWin).click();
let explainedDialog = find(body, node => node.tag === 'dialog');
assert.ok(explainedDialog.textContent.includes('-1 after win vs. Previous opponent · 85 → 84'));
assert.match(find(explainedDialog, node => node.classList.contains('rating-win-explanation')).textContent, /win raised résumé.*skills drop/);
assert.ok(find(explainedDialog, node => node.classList.contains('rating-part-change-row')).textContent.includes('Résumé +1.0'));
explainedDialog.close();
const lossUpdate = JSON.parse(JSON.stringify(negativeWin));
lossUpdate.rating.last_results[0].outcome = 'loss';
rating.badge(lossUpdate).click();
explainedDialog = find(body, node => node.tag === 'dialog');
assert.ok(explainedDialog.textContent.includes('-1 after loss vs. Previous opponent'));
assert.equal(walk(explainedDialog).filter(node => node.classList.contains('rating-win-explanation')).length, 0, 'a recorded loss must not be described as a win');
explainedDialog.close();
const firstRating = JSON.parse(availableOriginal);
Object.assign(firstRating.rating, {change: null, previous_score: null,
  part_changes: firstRating.rating.parts.map(part => ({key: part.key, label: part.label, previous: null, current: part.score, change: null}))});
rating.badge(firstRating).click();
explainedDialog = find(body, node => node.tag === 'dialog');
const firstChanges = find(explainedDialog, node => node.classList.contains('rating-part-change-row'));
assert.ok(firstChanges.textContent.includes('First rating · no earlier component scores to compare.'));
assert.ok(!firstChanges.textContent.includes('+0.0'), 'missing previous components must not become zero changes');
explainedDialog.close();
const roundedTier = JSON.parse(availableOriginal);
roundedTier.rating.parts[0].score = 89.6;
rating.badge(roundedTier).click();
explainedDialog = find(body, node => node.tag === 'dialog');
const roundedTile = walk(explainedDialog).find(node => node.classList.contains('rating-part'));
assert.equal(find(roundedTile, node => node.tag === 'b').textContent, '90');
assert.ok(roundedTile.classList.contains('rating-tier-90'), 'rounded 90 must use the 90+ red grade color');
const roundedBar = find(roundedTile, node => node.classList.contains('rating-bar'));
assert.equal(roundedBar.children[0].getAttribute('style'), 'width:' + (90 / 99 * 100) + '%');
roundedTile.click();
assert.ok(find(explainedDialog, node => node.classList.contains('rating-raw-panel')).textContent.includes('Unrounded component score: 89.60'));
explainedDialog.close();

const heldWin = JSON.parse(availableOriginal);
Object.assign(heldWin.rating, {
  version: 'upset_rating_experimental_v2', bouts: 10, provisional: false,
  score: 84, peak: 84, previous_score: 84, change: 0,
  raw_combined: 84.29, curve_score: 83, curve_percentile: .778,
  small_history_adjustment: 0, change_adjustment: 0, unheld_score: 83,
  outcome_hold: 'held_after_win', last_outcomes: ['win'],
  last_fight_summary: 'Won by KO/TKO. Recorded significant strikes: 91–97; takedowns: 0 of 5.',
});
heldWin.rating.model.resume_weight = .5;
heldWin.rating.parts[0].metrics.ko_wins_per_bout = .2;
heldWin.rating.history = [{date: '2025-01-01', score: 84, change: null, unheld_score: 84, outcome_hold: null},
  {date: '2026-06-14', score: 84, change: 0, unheld_score: 83, outcome_hold: 'held_after_win'}];
const v2Original = JSON.stringify(heldWin);
for (const matchup of [false, true]) {
  const badge = rating.badge(heldWin, {matchup});
  assert.equal(find(badge, node => node.classList.contains('rating-score')).textContent, '84');
  assert.equal(find(badge, node => node.classList.contains('rating-scale')).textContent, 'EXP V2');
  assert.ok(badge.getAttribute('aria-label').includes('Experimental v2'));
  assert.ok(badge.getAttribute('title').includes('Experimental v2'));
  badge.click();
  const dialog = find(body, node => node.tag === 'dialog');
  assert.ok(dialog.textContent.includes('Experimental v2'));
  assert.ok(!dialog.textContent.includes('Experimental v1'));
  assert.ok(dialog.textContent.includes('Held after win vs. Previous opponent · 84 → 84'));
  assert.ok(dialog.textContent.includes('The calculated grade after the usual limits was 83. The badge stayed at 84'));
  assert.equal(find(dialog, node => node.classList.contains('rating-last-fight-summary')).textContent, heldWin.rating.last_fight_summary);
  assert.equal(walk(dialog).filter(node => node.classList.contains('rating-win-explanation')).length, 0);
  assert.ok(find(dialog, node => node.classList.contains('rating-visible-conversion')).textContent.includes(
    'Combined 84.29 → about the 78th percentile of UFC rating snapshots through 2018 → curve 83 → held at 84'));
  const row = find(dialog, node => node.classList.contains('rating-history-row'));
  assert.ok(row.textContent.includes('Held after win'));
  const chip = find(row, node => node.classList.contains('rating-history-chip'));
  assert.equal(chip.textContent, '0');
  assert.ok(!chip.classList.contains('is-up') && !chip.classList.contains('is-down'));
  find(dialog, node => node.classList.contains('rating-part')).click();
  assert.ok(find(dialog, node => node.classList.contains('rating-raw-panel')).textContent.includes('KO/TKO wins / bout0.20'));
  find(dialog, node => node.getAttribute('aria-label') === 'How this experimental rating is calculated').click();
  const method = find(dialog, node => node.classList.contains('rating-info-panel'));
  assert.ok(method.textContent.includes('Grade before outcome hold83') && method.textContent.includes('Displayed rating84'));
  assert.ok(method.textContent.includes('Fixed overall blend50% résumé + 50% skills'));
  assert.ok(method.textContent.includes('A new 99 requires an unrounded grade of 99'));
  assert.ok(method.textContent.includes('The underlying model scores still update'));
  dialog.close();
}
assert.equal(JSON.stringify(heldWin), v2Original, 'rendering preserves v2 hold metadata');

const heldLoss = JSON.parse(v2Original);
Object.assign(heldLoss.rating, {
  outcome_hold: 'held_after_loss', last_outcomes: ['loss'],
  curve_score: 92, curve_percentile: .975, change_adjustment: -3, unheld_score: 89,
  last_fight_summary: null,
});
heldLoss.rating.last_results[0].outcome = 'loss';
rating.badge(heldLoss).click();
explainedDialog = find(body, node => node.tag === 'dialog');
assert.ok(explainedDialog.textContent.includes('Held after loss vs. Previous opponent'));
assert.ok(explainedDialog.textContent.includes('curve 92 → 89 after limits → held at 84'));
assert.ok(explainedDialog.textContent.includes('a loss cannot raise it'));
explainedDialog.close();

const noHold = JSON.parse(v2Original);
Object.assign(noHold.rating, {outcome_hold: null, unheld_score: 83, score: 83, change: -1,
  last_outcomes: ['win', 'loss'], last_results: []});
rating.badge(noHold).click();
explainedDialog = find(body, node => node.tag === 'dialog');
assert.ok(explainedDialog.textContent.includes('→ overall 83'));
assert.equal(walk(explainedDialog).filter(node => node.classList.contains('rating-hold-explanation')).length, 0);
explainedDialog.close();

const historicalV3 = JSON.parse(v2Original);
Object.assign(historicalV3.rating, {
  version: 'upset_rating_experimental_v3', event_date: '2024-06-08', rating_is_stale: true,
  score: 75, peak: 87, previous_score: 80, change: -5,
  raw_combined: 77.07, curve_score: 64, change_adjustment: 11, unheld_score: 75,
  outcome_hold: null, last_outcomes: ['loss'], last_results: [],
});
for (const matchup of [false, true]) {
  const badge = rating.badge(historicalV3, {matchup});
  assert.equal(find(badge, node => node.classList.contains('rating-scale')).textContent, '2024');
  assert.ok(badge.getAttribute('aria-label').includes('Historical UFC rating from 2024-06-08'));
  badge.click();
  const dialog = find(body, node => node.tag === 'dialog');
  assert.ok(dialog.textContent.includes('Model grade 64 · Displayed 75 (five-point change limit)'));
  assert.ok(dialog.textContent.includes('Last recorded UFC fight 2024-06-08'));
  dialog.close();
}

const historicalV4 = {...historicalV3, rating: {...historicalV3.rating, version: 'upset_rating_experimental_v4'}};
const v4Badge = rating.badge(historicalV4, {matchup: true});
assert.equal(find(v4Badge, node => node.classList.contains('rating-scale')).textContent, '2024');
assert.match(v4Badge.getAttribute('aria-label'), /Experimental v4.*75 on a 60 to 99 scale/);
v4Badge.click();
const v4Dialog = find(body, node => node.tag === 'dialog');
assert.ok(v4Dialog.textContent.includes('Experimental v4'));
assert.ok(v4Dialog.textContent.includes('Model grade 64 · Displayed 75 (five-point change limit)'));
assert.ok(v4Dialog.textContent.includes('the higher grades gradually require bigger gains'));
v4Dialog.close();

for (const [key, value] of [['outcome_hold', 'unrecognized'], ['outcome_hold', null], ['unheld_score', 82],
  ['unheld_score', '83'], ['previous_score', 83], ['change', -1], ['last_outcomes', ['win', 'loss']]]) {
  const invalid = {...heldWin, rating: {...heldWin.rating, [key]: value}};
  assert.equal(find(rating.badge(invalid), node => node.classList.contains('rating-score')).textContent, '—', 'invalid v2 update fails closed: ' + key);
}

for (const [key, value] of [['version', 'other_v1'], ['experimental', false], ['validated', true],
  ['score', 99.1], ['score', 100], ['score', NaN], ['status', 'unsupported_cutoff'], ['parts', availableReport.rating.parts.slice(0, 3)]]) {
  const invalid = {...availableReport, rating: {...availableReport.rating, [key]: value}};
  assert.equal(find(rating.badge(invalid), node => node.classList.contains('rating-score')).textContent, '—', 'invalid or unknown rating contracts must fail closed: ' + key);
}
for (const [status, message] of [['no_history', 'Rated after first recorded UFC fight.'],
  ['unsupported_cutoff', 'No experimental overall-rating snapshot is available for this date.']]) {
  const unavailableReport = {...availableReport, rating: {...availableReport.rating, status, score: null, message}};
  const badge = rating.badge(unavailableReport);
  assert.equal(find(badge, node => node.classList.contains('rating-score')).textContent, '—');
  badge.click();
  const dialog = find(body, node => node.tag === 'dialog');
  assert.ok(dialog.textContent.includes(message));
  assert.ok(dialog.textContent.includes('No experimental overall rating is available'));
  dialog.close();
}
assert.equal(JSON.stringify(examples), untouched, 'rendering and interactions must not mutate model inputs or fixtures');
console.log('Rating UI checks passed: compact octagons, rounded tiers, visible historical curve, v1/v2 contracts, outcome holds, résumé wins and unchanged fixtures.');
