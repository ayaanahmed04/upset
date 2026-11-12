const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const html = fs.readFileSync(path.join(__dirname, '../src/upset/web/research.html'), 'utf8');
class Node {
  constructor(tag = '#text', text = '') { this.tag = tag; this.children = []; this.text = String(text); this.style = {}; }
  append(...children) { this.children.push(...children.map(c => c instanceof Node ? c : new Node('#text', c))); }
  set textContent(value) { this.text = String(value); this.children = []; }
  get textContent() { return this.text + this.children.map(c => c.textContent).join(''); }
  setAttribute(key, value) { this[key] = String(value); }
}
const context = vm.createContext({ assert, Node, document: {
  createElement: tag => new Node(tag), createTextNode: text => new Node('#text', text),
  createElementNS: (_, tag) => new Node(tag), getElementById: () => null,
}});
const start = html.indexOf('const $=id=>');
vm.runInContext(html.slice(start, html.indexOf('/* ================= metric catalog', start)), context);
const previewStart = html.indexOf('function experimentalStriking(r)');
vm.runInContext(html.slice(previewStart, html.indexOf('function renderFighter(r)', previewStart)), context);
vm.runInContext(`
  assert.equal(experimentalStriking({}), null, 'preview must stay absent when the server flag is off');
  const report = {experimental_striking: {status:'available', estimate:.47, raw_accuracy:.52, bouts:10, attempts:200}};
  const original = JSON.stringify(report);
  const text = experimentalStriking(report).textContent;
  assert.ok(text.includes('How often their strikes land'));
  assert.ok(text.includes('UPSET estimate · experimental'));
  assert.ok(text.includes('Explore UPSET’s experimental estimate'));
  assert.ok(text.includes('What is this for?'));
  assert.ok(text.includes('47.0%') && text.includes('52.0%'));
  assert.ok(text.includes('Recorded in UFC fights'));
  assert.ok(text.includes('About 52 landed out of 100 attempts'));
  assert.ok(text.includes('About 47 landed out of 100 attempts'));
  assert.ok(text.includes('not chances of winning'));
  assert.ok(text.includes('With fewer attempts on record, the UFC average has more influence'));
  assert.ok(text.includes('Opponent quality is not included yet'));
  assert.ok(text.indexOf('Recorded in UFC fights') < text.indexOf('UPSET estimate'));
  const details = experimentalStriking(report).children.find(node => node.tag === 'details');
  assert.ok(details && !details.open, 'experimental research stays collapsed by default');
  assert.equal(JSON.stringify(report), original);
  const unavailable = experimentalStriking({experimental_striking:{status:'career_only',message:'Switch to Career'}});
  assert.ok(unavailable.textContent.includes('Switch to Career'));
  assert.ok(!unavailable.textContent.includes('%'));
`, context);
console.log('Experimental UI checks passed: labels, separate raw values, hidden intervals, career-only and flag-off states.');
