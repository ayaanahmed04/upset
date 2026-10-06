/* Run with node tests/hero_search_checks.cjs.
 * Exercise live search adoption and async search behavior without a database.
 */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const html = fs.readFileSync(path.join(__dirname, '../src/upset/web/research.html'), 'utf8');
let context;
class Node {
  constructor(tag = '#text', text = '') {
    this.tag = tag; this.tagName = tag.toUpperCase(); this.text = String(text);
    this.children = []; this.attributes = {}; this.listeners = {}; this.className = '';
    this.value = ''; this.parentElement = null;
    this.style = {setProperty() {}, removeProperty() {}};
    this.classList = {
      contains: name => this.className.split(/\s+/).includes(name),
      toggle: (name, on) => {
        const names = new Set(this.className.split(/\s+/).filter(Boolean));
        if (on) names.add(name); else names.delete(name);
        this.className = [...names].join(' ');
      },
      add: name => this.classList.toggle(name, true),
      remove: name => this.classList.toggle(name, false),
    };
  }
  setAttribute(k, v) { this.attributes[k] = String(v); if (k === 'id') this.id = String(v); }
  removeAttribute(k) { delete this.attributes[k]; }
  remove() {
    if (this.parentElement) {
      this.parentElement.children = this.parentElement.children.filter(n => n !== this);
      this.parentElement = null;
    }
  }
  append(...children) {
    for (let child of children) {
      if (!(child instanceof Node)) child = new Node('#text', child);
      child.remove(); child.parentElement = this; this.children.push(child);
    }
  }
  replaceChildren(...children) {
    for (const child of [...this.children]) child.remove();
    this.text = ''; this.append(...children);
  }
  set textContent(value) { this.replaceChildren(); this.text = String(value); }
  get textContent() { return this.text + this.children.map(n => n.textContent).join(''); }
  addEventListener(type, callback) { (this.listeners[type] ||= []).push(callback); }
  fire(type, event = {}) { for (const fn of this.listeners[type] || []) fn(event); }
  querySelectorAll(selector) {
    const matches = [];
    for (const node of this.children) {
      if (selector === 'button.opt' && node.tag === 'button' && node.classList.contains('opt')) matches.push(node);
      matches.push(...node.querySelectorAll(selector));
    }
    return matches;
  }
  getBoundingClientRect() { return {bottom: 220}; }
  scrollIntoView() {}
  click() { if (this.onclick) this.onclick(); }
  focus() { context.document.activeElement = this; this.fire('focus'); }
  blur() { context.document.activeElement = body; this.fire('blur'); }
}
const body = new Node('body');
function node(id) { const n = new Node('div'); n.setAttribute('id', id); return n; }
const header = node('headerSlot'), wrap = node('searchWrap'), shell = node('shell');
const input = node('search'), dd = node('dropdown'), content = node('content');
input.tagName = 'INPUT';
shell.append(input); wrap.append(shell, dd); header.append(wrap);
body.append(header, content, node('main'), node('error'));
function find(id, root = body) {
  if (root.id === id) return root;
  for (const child of root.children) { const hit = find(id, child); if (hit) return hit; }
  return null;
}
const timers = new Map(); let timerID = 0;
const motion = {matches: false, addEventListener() {}};
context = vm.createContext({
  Node, document: {
    activeElement: body, hidden: false, getElementById: find,
    createElement: tag => new Node(tag), createElementNS: (_, tag) => new Node(tag),
    createTextNode: text => new Node('#text', text), addEventListener() {},
  },
  location: {hash: '#/'}, window: {visualViewport: null}, innerHeight: 800,
  matchMedia: query => query.includes('reduced-motion') ? motion : {matches: true},
  setTimeout: (fn, delay) => { const id = ++timerID; timers.set(id, {fn, delay}); return id; },
  clearTimeout: id => timers.delete(id), addEventListener() {}, scrollTo() {},
  renderTray() {}, hideTip() {},
  renderFighter: r => content.replaceChildren(new Node('div', r.name)),
  renderCompare: () => content.replaceChildren(new Node('div', 'Comparison')),
});
function section(start, end) {
  const a = html.indexOf(start), b = html.indexOf(end, a);
  assert.ok(a >= 0 && b > a, 'source section exists');
  return html.slice(a, b);
}
vm.runInContext(section('const $=id=>', '/* ================= metric catalog'), context);
vm.runInContext(section('/* ================= search placement', '/* ================= routing'), context);
vm.runInContext(section('/* ================= search =================', '/* ================= filters'), context);
vm.runInContext(section('const PICKS=', '/* ================= matchup tray'), context);
vm.runInContext(fs.readFileSync(path.join(__dirname, '../src/upset/web/research_about.js'), 'utf8'), context);
vm.runInContext(section('function go(hash)', "addEventListener('hashchange',route);"), context);
context.api = async url => url.startsWith('/api/fighter?') ? {name: 'Fighter profile'} : [];
function debounce() {
  const entry = [...timers].find(([, value]) => value.delay === 160);
  assert.ok(entry, 'search was scheduled'); timers.delete(entry[0]); return entry[1].fn();
}
const key = name => input.fire('keydown', {key: name, preventDefault() {}});
(async () => {
  vm.runInContext("state.meta={fighters:4455,total_bouts:8799,earliest_bout:'1994-03-11',latest_bout:'2026-09-26'}", context);
  const listeners = input.listeners.input.length;
  await context.route();
  assert.equal(wrap.parentElement.id, 'heroSlot'); assert.ok(wrap.classList.contains('big'));
  assert.ok(content.textContent.includes('Every fight. UPSET.'));
  assert.ok(content.textContent.includes('look up any fighter, analyze their stats, compare them head to head.'));
  await context.route(); // Home-to-home previously risked deleting the live input.
  assert.equal(find('search'), input); assert.equal(input.listeners.input.length, listeners);
  context.location.hash = '#/about'; await context.route();
  assert.equal(wrap.parentElement, header); assert.ok(!wrap.classList.contains('big'));
  assert.ok(content.textContent.includes('Ayaan Ahmed'));
  context.location.hash = '#/fighter/a'; await context.route();
  assert.equal(wrap.parentElement, header); assert.equal(content.textContent, 'Fighter profile');
  context.api = async url => url.startsWith('/api/compare?') ? {fighters: [{id: 'a', name: 'Alpha'}, {id: 'b', name: 'Beta'}]} : [];
  context.location.hash = '#/compare/a/b'; await context.route();
  assert.equal(wrap.parentElement, header); assert.equal(content.textContent, 'Comparison');
  context.location.hash = '#/'; await context.route();
  assert.equal(wrap.parentElement.id, 'heroSlot'); assert.equal(find('search'), input);

  // Moving to a new route cancels a response already in flight.
  let resolve;
  context.api = () => new Promise(done => { resolve = done; });
  input.value = 'old'; input.fire('input'); const pending = debounce();
  context.placeSearch('header'); resolve([{id: 'old', name: 'Old result', recorded_bouts: 1}]);
  await pending; assert.ok(!dd.classList.contains('open'));

  // Empty-state Escape, reverse navigation and selected-option announcements.
  context.api = async () => [];
  input.value = 'none'; input.fire('input'); await debounce();
  assert.ok(dd.classList.contains('open')); key('Escape');
  assert.ok(!dd.classList.contains('open')); assert.equal(wrap.attributes['aria-expanded'], 'false');
  context.api = async () => [{id: 'a', name: 'Alpha', recorded_bouts: 3}, {id: 'b', name: 'Beta', recorded_bouts: 4}];
  input.value = 'a'; input.fire('input'); await debounce(); key('ArrowUp');
  assert.equal(input.attributes['aria-activedescendant'], 'fighter-option-1');
  assert.equal(dd.children[1].attributes['aria-selected'], 'true');
  key('Enter'); assert.equal(context.location.hash, '#/fighter/b');
  assert.equal(input.value, ''); assert.ok(!wrap.classList.contains('has-query'));

  input.focus(); assert.ok(![...timers.values()].some(t => t.delay === 2400));
  input.value = 'my own query'; context.animateSearchExample(); assert.equal(input.value, 'my own query');
  input.value = ''; input.blur(); motion.matches = true; context.resumeSearchExamples();
  assert.equal(input.placeholder, 'Search any UFC fighter'); assert.equal(timers.size, 0);
  console.log('Hero search checks passed: home rerender, About/profile navigation, one live input, stale responses, keyboard selection and reduced motion.');
})().catch(error => { console.error(error); process.exitCode = 1; });
