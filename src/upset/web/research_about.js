/* Shared creator page for the broadcast and editorial editions. */
function renderAbout() {
  $('content').replaceChildren(
    h('article', {class: 'about-page', 'aria-labelledby': 'about-name'},
      h('a', {class: 'about-back', href: '#/', text: '← Back to UPSET'}),
      h('header', {class: 'about-heading'},
        h('p', {class: 'about-label', text: 'The person behind UPSET'}),
        h('h1', {id: 'about-name', text: 'Ayaan Ahmed'})),
      h('p', {class: 'about-intro', text:
        'I’m a recent Computer Science graduate with a strong interest in data, software development, and the sport of mixed martial arts.'}),
      h('p', null, 'I created ', h('strong', {text: 'UPSET'}),
        ' because I felt MMA fans deserved a better way to explore the sport through data. The platform is designed to let fans look up fighters, explore detailed career and performance statistics, and compare fighters head-to-head in a way that is easy to view and meaningful.'),
      h('p', {text:
        'Beyond being a fan project, UPSET is my attempt to help push MMA analytics toward the level of statistical depth and accessibility that already exists in major professional sports such as basketball, baseball, and football. MMA, more specifically UFC, has decades of fights, thousands of athletes, and an enormous amount of performance data, but much of that information is still difficult for the average fan to explore or put into context.'}),
      h('p', {text:
        'My goal is to use my background in computer science, data analysis, and machine learning to turn that information into something useful—whether that means understanding how a fighter has evolved, comparing two athletes beyond their win-loss records, identifying trends across the sport, or eventually building models that can better understand matchup outcomes.'}),
      h('p', {text:
        'UPSET started from my own curiosity as a UFC fan, but I want it to grow into a serious MMA research and analytics platform for anyone who wants to understand the sport at a deeper level.'}))
  );
}
