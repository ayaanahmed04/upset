/* Definitions describe the research viewer, not the prediction model. */
function renderMethodology() {
  const paragraph = text => h('p', {text});
  const section = (title, ...body) => h('section', {class: 'card', style: 'margin-top:18px'},
    h('div', {class: 'section-title'}, h('h3', {text: title})), ...body);
  const latest = state.meta?.latest_bout;
  $('content').replaceChildren(
    h('article', {class: 'about-page'},
      h('a', {class: 'about-back', href: '#/', text: '← Back to UPSET'}),
      h('header', {class: 'about-heading'}, h('h1', {text: 'How the numbers work'})),
      paragraph('UPSET describes accepted UFC fight history. A higher number is not automatically an advantage, and the viewer does not currently publish win probabilities.'),
      section('Dates, windows and coverage',
        paragraph('Before is exclusive: only fights dated earlier than your chosen date count. Career uses all accepted fights before it; Last 3, 5 or 10 uses the most recent available fights, not necessarily a complete history. All fights on a cutoff date are excluded.'),
        paragraph('Results use currently reviewed amendments. Profile measurements come from a stored snapshot. An old cutoff does not reconstruct the information that was publicly available at that time.'),
        paragraph('Historical rows come from the normalized Kaggle archive; current accepted rows come from cached Cito responses and reviewed identities. Unresolved fighter links and unavailable bouts are excluded. The archive has not been independently certified as complete.'),
        paragraph(latest ? 'Latest accepted fight date in this database: '+niceDate(latest)+'. This is a coverage date, not a guarantee that every fight through it is included.' : 'See the homepage and Data provenance for the loaded database’s coverage.')),
      section('Rates and percentages',
        paragraph('Striking rates divide summed counts by summed actual fight minutes. Knockdowns, takedowns and submission attempts per 15 minutes multiply that rate by 15; short finishes contribute their actual duration. Accuracy divides landed by attempted, and defense is one minus the opponent’s landed divided by attempted. A zero denominator displays —.'),
        paragraph('Strike maps show the share of significant strikes landed by target and position. They do not measure time spent in those positions. Count-based knockdown ratios include selected bouts even if the clock is zero; time-based rates require positive duration.')),
      section('Division percentiles',
        paragraph('Peer fighters need at least three timed bouts and 15 minutes in the same window and cutoff. Division is the latest classified UFC bout before the cutoff. With fewer than 25 eligible fighters in that division, the pool falls back to all divisions. The actual scope is displayed.'),
        paragraph('A fighter’s window can contain earlier weight classes. Ties use a mid-rank percentile; lower absorption is shown as better. These are descriptive rankings, not active-roster rankings or opponent-adjusted ratings.')),
      section('Opponent records before each meeting',
        paragraph('For each selected fight, UPSET counts the opponent’s accepted wins, losses and other results dated strictly before that meeting. Neither the meeting itself nor other fights on that date count. Draws and no contests are shown, but excluded from win-rate denominators.'),
        paragraph('The headline is the arithmetic mean of opponent win percentages, one entry per meeting. Opponents with no prior decisive results are excluded from that mean, with their count displayed. A rematch contributes another entry using the opponent’s record at the later meeting.'),
        paragraph('The expandable list also shows the pooled record and its win percentage. Pooling weights opponents with longer records more heavily. Neither measure adjusts for the quality of those opponents’ opponents, and missing accepted history can distort it. Reviewed results may have been amended after the meeting date.')),
      section('Control shares',
        paragraph('Time in control = own credited control seconds / eligible fight seconds. Time being controlled uses the opponent’s credited seconds over that same denominator. Neither credited with control = the remaining seconds / eligible fight seconds.'),
        paragraph('Both fighters’ control totals must be present, nonnegative and sum to no more than the actual duration. Missing or inconsistent totals exclude the whole bout from these shares. The sample and observed minutes are shown. The remainder can include standing exchanges, clinch or ground time without credited control; it is not measured distance time.')),
      section('Power, durability and common opponents',
        paragraph('Knockdown efficiency = 100 × knockdowns scored / significant strikes landed. Knockdown absorption rate = 100 × opponent knockdowns / opponent significant strikes landed. These do not measure punch force or prove a fighter’s chin. KO/TKO loss counts include doctor stoppages; reviewed no contests do not count as losses.'),
        paragraph('Common opponents match persistent fighter identities, not display names. Every meeting within both fighters’ selected windows is retained, including rematches and reviewed results. Sharing an opponent does not imply who wins a new matchup.')),
      section('What comes next',
        paragraph('Round detail, event browsing and public forecasts are separate additions. A round-three versus round-one pace ratio would describe observed pace among fights reaching round three; it would not isolate cardio from tactics or opponent effects. Retrospective model replay scores are not a public prospective forecast track record.')))
  );
}
