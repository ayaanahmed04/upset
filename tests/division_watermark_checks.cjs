/* Run with: node tests/division_watermark_checks.cjs */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const html = fs.readFileSync(path.join(__dirname, '../src/upset/web/research.html'), 'utf8');
const script = html.match(/<script>([\s\S]*?)<\/script>/)[1];
new vm.Script(script);
const start = script.indexOf('function fitDivisionWatermark(');
const end = script.indexOf('function tiles(', start);
const context = vm.createContext({
  assert,
  document: {querySelector: () => context.watermark || null},
  getComputedStyle: node => ({fontSize: node.style.fontSize || String(node.baseSize)}),
  h: (tag, attrs, ...children) => ({tag, attrs, children: children.flat().filter(Boolean)}),
  avatar: () => ({tag: 'portrait'}), statusBadges: () => ({tag: 'badges'}),
  recordText: () => '1–0', streakText: () => 'W1', feet: () => null, inMatchup: () => false,
});
vm.runInContext(script.slice(start, end), context);
const divisions = ['Flyweight', 'Bantamweight', 'Featherweight', 'Lightweight', 'Welterweight',
  'Middleweight', 'Light Heavyweight', 'Heavyweight', "Women's Strawweight", "Women's Flyweight",
  "Women's Bantamweight", "Women's Featherweight", 'Catch Weight', 'Open Weight'];
for (const division of divisions) {
  context.division = division;
  vm.runInContext(`
    const card=heroCard({id:'fighter',name:'Fighter',profile:{},summary:{division},history:[]});
    const mark=card.children.find(child=>child.attrs?.class==='division-watermark');
    assert.equal(mark.attrs.text,division);
    assert.equal(mark.attrs['aria-hidden'],'true','decorative text must not repeat the accessible division badge');
  `, vm.createContext({...context, division}));
  context.watermark = {
    baseSize: 100, clientWidth: 1200,
    style: {fontSize: '', removeProperty() { this.fontSize = ''; }},
    get scrollWidth() {
      return Math.ceil(Math.max(this.clientWidth, division.length * parseFloat(this.style.fontSize || this.baseSize) * .75));
    },
  };
  for (const width of [1200, 500, 280, 200, 1800]) {
    context.watermark.clientWidth = width;
    vm.runInContext('fitDivisionWatermark()', context);
    assert.ok(context.watermark.scrollWidth <= width, `${division} must fit a ${width}px label area`);
    assert.ok(parseFloat(context.watermark.style.fontSize || '100') <= 100);
  }
  assert.equal(context.watermark.style.fontSize, '', 'widening must restore the CSS size');
}
context.watermark = null;
vm.runInContext('fitDivisionWatermark()', context); // Home and matchup pages have no watermark.
console.log('Division watermark checks passed: full labels, decorative accessibility, narrow/wide fitting and resize recovery.');
