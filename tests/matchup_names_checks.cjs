/* Run with: node tests/matchup_names_checks.cjs */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const html = fs.readFileSync(path.join(__dirname, '../src/upset/web/research.html'), 'utf8');
const script = html.match(/<script>([\s\S]*?)<\/script>/)[1];
new vm.Script(script); // Check the complete page, as well as the isolated renderer.
const start = script.indexOf('function matchupNameLines(');
const end = script.indexOf('function totRow(', start);
const context = vm.createContext({
  assert,
  document: {querySelectorAll: () => context.headings || []},
  getComputedStyle: node => ({fontSize: node.style.fontSize || '34px'}),
  h: (tag, attrs, ...children) => ({tag, attrs, children: children.flat()}),
  avatar: () => ({tag: 'portrait'}), statusBadges: () => ({tag: 'badges'}),
  recordText: () => '1–0', streakText: () => 'W1',
  go: route => { context.destination = route; },
});
vm.runInContext(script.slice(start, end), context);
vm.runInContext(`
  const names=['Jon Jones','Dustin Poirier','Charles Oliveira','Max Holloway',
               'Khabib Nurmagomedov','Rafael dos Anjos','Jung Chan-Sung',
               'Alexander Gustafsson','Zhang Weili','Buakaw'];
  for(const name of names){
    const parts=matchupNameLines(name);
    assert.equal(parts.join(' '),name,'the full name and word order must be preserved');
    assert.equal(parts.length,name.includes(' ')?2:1);
    for(const side of ['red','blue']){
      const result=corner({id:'fighter',name,summary:{}},side);
      const info=result.children[1],button=info.children[1].children[0];
      assert.equal(info.attrs.class,'corner-info');
      assert.equal(button.attrs['aria-label'],name);
      assert.equal(button.children.map(line=>line.attrs.text).join(''),name);
      button.attrs.onclick();
      assert.equal(destination,'#/fighter/fighter');
    }
  }
  assert.deepEqual(matchupNameLines('Jon Jones'),['Jon','Jones']);
  assert.deepEqual(matchupNameLines('Dustin Poirier'),['Dustin','Poirier']);
  assert.deepEqual(matchupNameLines('Rafael dos Anjos'),['Rafael','dos Anjos']);
`, context);

// Simulate measured font widths and native integer scrollWidth rounding.
// Both corners must fit, share a size, and grow back after a wider resize.
function measuredHeading(width, name) {
  const heading = {
    clientWidth: width,
    style: {fontSize: '', removeProperty() { this.fontSize = ''; }},
    querySelectorAll: () => name.split('|').map(line => ({
      get scrollWidth() {
        return Math.ceil(Math.max(heading.clientWidth, line.length * parseFloat(heading.style.fontSize || '34px') * .7));
      },
    })),
  };
  return heading;
}
context.headings = [measuredHeading(270, 'JON|JONES'), measuredHeading(270, 'KHABIB|NURMAGOMEDOV')];
for (const width of [270, 140, 210, 400]) {
  context.headings.forEach(heading => { heading.clientWidth = width; });
  vm.runInContext('fitMatchupNames()', context);
  assert.equal(context.headings[0].style.fontSize, context.headings[1].style.fontSize);
  for (const heading of context.headings) {
    assert.ok(parseFloat(heading.style.fontSize) > 0);
    assert.ok(parseFloat(heading.style.fontSize) <= 34);
    for (const line of heading.querySelectorAll('.name-line')) assert.ok(line.scrollWidth <= width);
  }
}
assert.equal(context.headings[0].style.fontSize, '34px', 'widening must restore the CSS font size');
context.headings = [];
vm.runInContext('fitMatchupNames()', context); // Other routes have no matchup headings.
console.log('Matchup name checks passed: preserved names, both corners, shared fitting, shrink/grow on resize, accessible labels and profile links.');
