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
  h: (tag, attrs, ...children) => ({tag, attrs, children: children.flat()}),
  avatar: () => ({tag: 'portrait'}), statusBadges: () => ({tag: 'badges'}),
  recordText: () => '1–0', streakText: () => 'W1',
  go: route => { context.destination = route; },
});
vm.runInContext(script.slice(start, end), context);
vm.runInContext(`
  const names=['Jon Jones','Dustin Poirier','Charles Oliveira','Max Holloway',
               'Rafael dos Anjos','Jung Chan-Sung','Alexander Gustafsson','Zhang Weili','Buakaw'];
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
console.log('Matchup name checks passed: balanced lines, preserved names, both corners, accessible labels and profile links.');
