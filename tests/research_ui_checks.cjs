/* Run with: node tests/research_ui_checks.cjs
 * Execute the shipped rendering functions with native DOM string conversion,
 * without a browser, external packages, or the research database.
 */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const html = fs.readFileSync(path.join(__dirname, '../src/upset/web/research.html'), 'utf8');

class Node {
  constructor(tag = '#text', text = '') {
    this.tag = tag;
    this.children = [];
    this.attributes = {};
    this.style = {};
    this.className = '';
    this.text = String(text);
    this.classList = {toggle: (name, on) => {
      const classes = new Set(this.className.split(/\s+/).filter(Boolean));
      if (on) classes.add(name); else classes.delete(name);
      this.className = [...classes].join(' ');
    }};
  }
  append(...children) {
    this.children.push(...children.map(child => child instanceof Node ? child : new Node('#text', child)));
  }
  replaceChildren(...children) { this.children = []; this.text = ''; this.append(...children); }
  set textContent(value) { this.children = []; this.text = String(value); }
  get textContent() { return this.text + this.children.map(child => child.textContent).join(''); }
  setAttribute(key, value) { this.attributes[key] = String(value); }
  addEventListener() {}
}
const nodes = Object.fromEntries(['tray', 'slot0', 'slot1', 'go'].map(id => [id, new Node('div')]));
const context = vm.createContext({
  assert, nodes, Node, innerWidth: 1200, location: {hash: '#/fighter/a'},
  document: {
    getElementById: id => nodes[id],
    createElement: tag => new Node(tag),
    createElementNS: (_, tag) => new Node(tag),
    createTextNode: text => new Node('#text', text),
  },
  bindTip(node, build) { node.tipBuilder = build; },
  go(hash) { context.destination = hash; }, route() {},
});
function section(start, end) { return html.slice(html.indexOf(start), html.indexOf(end, html.indexOf(start))); }
vm.runInContext(section('const $=id=>', '/* ================= metric catalog'), context);
vm.runInContext(section('function timeline(history)', 'function strikeMap(m)'), context);
vm.runInContext(section('function renderTray()', '/* ================= routing'), context);
vm.runInContext(section('const METRICS=[', '/* ================= avatar'), context);
vm.runInContext(section('function meters(r,group)', '/* ================= fighter page'), context);
vm.runInContext(section('function tiles(r)', 'function historyList('), context);
vm.runInContext(section('function duel(A,B)', 'function renderCompare('), context);

vm.runInContext(`
  const a={id:'a',name:'Charles Oliveira'},b={id:'b',name:'Max Holloway'};
  for(const removed of [0,1]){
    state.matchup=[a,b];state.view='compare';renderTray();
    nodes['slot'+removed].children.find(n=>n.tag==='button').onclick();
    const vacant=nodes['slot'+removed];
    assert.equal(vacant.textContent,removed?'Blue corner':'Red corner');
    assert.equal(vacant.children.length,2);
    assert.ok(!vacant.className.split(' ').includes('empty'),'page empty-state styles must not apply to a chip');
    assert.equal(nodes['slot'+(1-removed)].textContent,(removed?a:b).name+'×');
    assert.equal(nodes.go.disabled,true);
  }
  state.matchup=[null,null];renderTray();
  assert.ok(!nodes.tray.className.includes('show'));
  state.matchup=[a,b];renderTray();
  assert.equal(nodes.go.disabled,false);
  assert.equal(nodes.go.hidden,false,'a saved pair remains accessible from a fighter profile');
  nodes.go.onclick();assert.equal(destination,'#/compare/a/b');
  location.hash='#/compare/a/b';renderTray();
  assert.equal(nodes.go.hidden,true,'the current matchup does not need a second compare action');
  for(const hash of ['#/fighter/a','#/','#/compare/c/d']){
    location.hash=hash;renderTray();assert.equal(nodes.go.hidden,false);
  }
  state.matchup=[a,null];renderTray();
  assert.equal(nodes.go.hidden,true,'incomplete pairs do not show a dead action');
  for(const width of [390,1200]){
    innerWidth=width;
    for(const values of [[10,-.5],[.5,-10],[.01,-.001],[1,0],[0,-1],[0,0]]){
      const history=values.map((value,i)=>({date:'2026-01-0'+(i+1),opponent:'Opponent',outcome:'win',sig_differential_per_minute:value}));
      const svg=timeline(history).children[0];
      const labels=svg.children.filter(n=>n.tag==='text'&&n.attributes['text-anchor']==='end');
      const ys=labels.map(n=>Number(n.attributes.y)).sort((a,b)=>a-b);
      assert.equal(new Set(labels.map(n=>n.textContent)).size,labels.length,'each axis label appears only once');
      for(let i=1;i<ys.length;i++)assert.ok(ys[i]-ys[i-1]>=19.99,'axis labels must remain separated');
      // Both signs use the same units per pixel; padding must not distort the bars.
      if(values[0]>0&&values[1]<0){
        const ticks=labels.map(n=>({value:Number(n.textContent),y:Number(n.attributes.y)-4}));
        const zero=ticks.find(n=>n.value===0),pos=ticks.find(n=>n.value>0),neg=ticks.find(n=>n.value<0);
        assert.ok(Math.abs((zero.y-pos.y)/pos.value-(neg.y-zero.y)/-neg.value)<1e-6);
      }
    }
  }
`, context);

vm.runInContext(`
  {
    const rateKeys=['knockdowns_per_15_minutes','takedowns_per_15_minutes','submission_attempts_per_15_minutes'];
    const report={name:'Fighter',metrics:Object.fromEntries(METRICS.map(m=>[m.key,3])),
      percentiles:{eligible:true,scope:'Lightweight',values:Object.fromEntries(METRICS.map(m=>[m.key,{percentile:80,median:.9,pool:30}]))}};
    const other={...report,name:'Opponent',metrics:{...report.metrics,...Object.fromEntries(rateKeys.map(key=>[key,6]))}};
    const snapshot=JSON.stringify([report,other]);
    function descendants(node){return[node,...node.children.flatMap(descendants)];}
    for(const key of rateKeys){
      const metric=METRICS.find(m=>m.key===key);
      assert.equal(metric.f(3),'1.00'); // 3 events / 15 minutes = 1 event / 5 minutes.
      assert.equal(metric.f(0),'0.00');
      assert.equal(metric.f(null),'—');
      assert.equal(metric.unit,'per 5 min');
      assert.equal(goodPct(report,metric),80,'display conversion must preserve percentile rank');
      const meter=meters(report,metric.group).children.find(n=>n.children[0].textContent===metric.label);
      assert.equal(meter.children[1].children[0].textContent,'1.00');
      const tooltip=meter.tipBuilder();
      assert.equal(tooltip[2].children[1].textContent,'0.30','division medians use the same display units');
    }
    const tile=tiles(report).children.find(n=>n.children[0].textContent==='Knockdowns / 5 min');
    assert.equal(tile.children[1].textContent,'1.00');
    const comparison=duel(report,other);
    for(const key of rateKeys){
      const metric=METRICS.find(m=>m.key===key);
      const row=comparison.children.find(n=>n.className==='drow'&&n.children[1].children[0].textContent===metric.label);
      assert.equal(row.children[0].children[0].textContent,'1.00');
      assert.equal(row.children[2].children[0].textContent,'2.00');
      assert.ok(descendants(row).filter(n=>n.className==='u').every(n=>n.textContent==='per 5 min'));
      assert.equal(row.tipBuilder()[1].children[1].textContent,'1.00 · 80th pct');
    }
    assert.equal(JSON.stringify([report,other]),snapshot,'UI rendering must not mutate source rates or ranks');
  }
`, context);

// The topbar and tray wraps are sibling stacking contexts in the same header.
// A high dropdown z-index alone cannot raise it above the tray's context.
const css = html.slice(html.indexOf('<style>') + 7, html.indexOf('</style>'));
function baseRules(selector) {
  return css.slice(0, css.indexOf('@media(max-width:1000px)')).split('}')
    .filter(rule => rule.slice(0, rule.indexOf('{')).trim() === selector)
    .map(rule => rule.slice(rule.indexOf('{') + 1)).join(';');
}
function zIndex(selector) { return Number(baseRules(selector).match(/(?:^|;)z-index:(\d+)/)[1]); }
assert.ok(zIndex('.topbar') > zIndex('.wrap'), 'search must paint above the later tray wrap');
assert.ok(zIndex('.search-wrap') > 0, 'dropdown must paint above sibling header controls');
assert.match(baseRules('#go[hidden]'), /display:none/, 'hidden must win over the button display rule');
console.log('UI checks passed: tray navigation, per-5-minute cards/comparison/tooltips/medians, preserved ranks, empty corners, search stacking and chart spacing.');
