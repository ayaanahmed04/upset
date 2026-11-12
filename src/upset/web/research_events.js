'use strict';

function eventHeader(title,description,back){
  return h('header',{class:'event-header'},
    back?h('a',{class:'event-back',href:back.href,text:back.text}):null,
    h('h1',{class:'distressed',text:title}),
    description?h('p',{text:description}):null);
}

function eventTitle(event){
  return event.headline?event.name+' · '+event.headline:event.name;
}

function eventArchiveCard(event){
  const coverage=event.reviewed_bouts+(event.status==='results_only'?' official results':' reviewed bouts')+
    (event.pending_bouts?' · '+event.pending_bouts+' awaiting review':'');
  const fightNight=event.name==='UFC Fight Night'&&event.headline;
  return h('a',{class:'event-archive-link',href:eventUrl(event.slug)},
    h('time',{dateTime:event.date,text:niceDate(event.date)}),
    h('span',{class:'event-archive-title'},h('strong',{text:fightNight?event.headline:eventTitle(event)}),
      h('small',{text:(fightNight?event.name+' · ':'')+coverage})),
    h('span',{class:'event-row-arrow','aria-hidden':'true',text:'↗'}));
}

function renderEvents(data){
  const scheduled=data.scheduled;
  const recent=data.archived.slice(0,8),older=data.archived.slice(8);
  $('content').replaceChildren(...[
    eventHeader('Events'),
    scheduled?h('section',{class:'card event-upcoming'},
      h('div',null,h('span',{class:'eyebrow',text:'Upcoming · '+niceDate(scheduled.date)}),
        h('h2',{text:eventTitle(scheduled)}),h('p',{text:scheduled.venue})),
      h('a',{class:'btn primary',href:eventUrl(scheduled.slug),text:'View full card →'})):null,
    state.meta?.share_routes?h('div',{class:'event-extra-links event-tools'},
      h('a',{class:'event-time-link',href:'/time-machine',text:'Time Machine →'}),
      state.meta.upset_tracker?h('a',{class:'event-time-link',href:'/upsets',text:'Upset Tracker →'}):null):null,
    h('section',{class:'event-archive'},
      h('h2',{text:'Recent results'}),
      recent.length?h('div',{class:'event-list'},recent.map(eventArchiveCard)):
        h('p',{class:'muted',text:'Recent cards are unavailable in this release.'}),
      older.length?h('details',{class:'archive-more'},h('summary',{text:'Show '+older.length+' older cards'}),
        h('div',{class:'event-list'},older.map(eventArchiveCard))):null),
    data.historical?.length?h('section',{class:'event-archive'},
      h('h2',{text:'Historical results'}),h('div',{class:'event-list'},data.historical.map(eventArchiveCard))):null
  ].filter(Boolean));
}

function eventCountdown(startsAt){
  const start=new Date(startsAt),stamp=new Intl.DateTimeFormat('en-US',{
    hour:'numeric',minute:'2-digit',timeZoneName:'short'
  }).format(start);
  const node=h('p',{class:'event-time'});
  function refresh(){
    const minutes=Math.max(0,Math.ceil((start-Date.now())/60000));
    const days=Math.floor(minutes/1440),hours=Math.floor(minutes%1440/60);
    const remaining=days?days+'d '+hours+'h':hours?hours+'h '+minutes%60+'m':minutes+'m';
    node.textContent=minutes?'Early prelims at '+stamp+' · Starts in '+remaining:'Scheduled start was '+stamp+' · Results pending';
    if(minutes)setTimeout(()=>{if(node.isConnected)refresh();},60000);
  }
  refresh();
  return node;
}

function comparisonUrl(fighters,date,fixedCutoff=false){
  if(!fighters.every(fighter=>fighter.id))return null;
  const cutoff=fixedCutoff||date<localToday()?'?before='+encodeURIComponent(date):'';
  return viewerUrl('/compare/'+fighters.map(fighter=>encodeURIComponent(fighter.id)).join('/')+cutoff);
}

async function drawTimeMachine(signal){
  let previous=state.lastTimeMachineFight||'';
  try{previous=previous||sessionStorage.getItem('upset.timeMachine.last')||'';}catch{}
  const fight=await api('/api/time-machine?exclude='+encodeURIComponent(previous),signal);
  if(fight&&!signal.aborted){
    state.lastTimeMachineFight=fight.id;
    try{sessionStorage.setItem('upset.timeMachine.last',fight.id);}catch{}
  }
  return fight;
}

function renderTimeMachine(fight,signal){
  const card=h('article',{class:'card time-preset time-draw','aria-live':'polite'});
  const status=h('p',{class:'muted',role:'status',hidden:true});
  const another=h('button',{class:'btn',type:'button',text:'Draw another fight',disabled:!fight,onclick:async()=>{
    another.disabled=true;
    status.hidden=true;
    try{
      const next=await drawTimeMachine(signal);
      if(signal.aborted)return;
      if(next)showFight(next);
      else{
        status.textContent='No other matchups are available in this release.';
        status.hidden=false;
        return;
      }
    }catch{
      if(signal.aborted)return;
      status.textContent='Could not draw a fight. Try again.';
      status.hidden=false;
    }
    another.disabled=false;
    another.focus({preventScroll:true});
  }});
  function showFight(bout){
    card.replaceChildren(...(bout?[
      h('span',{class:'eyebrow',text:bout.label+' · '+niceDate(bout.date)}),
      h('h2',null,h('span',{text:bout.fighters[0].name}),h('small',{text:'vs'}),h('span',{text:bout.fighters[1].name})),
      h('div',{class:'time-actions'},
        h('a',{class:'btn primary',href:comparisonUrl(bout.fighters,bout.date,true),text:'Pre-fight comparison'}),
        h('a',{class:'event-back',href:fightUrl(bout.id),text:'View result'}))
    ]:[h('p',{class:'muted',text:'No Time Machine matchups are available in this release.'})]));
  }
  showFight(fight);
  $('content').replaceChildren(
    eventHeader('Time Machine','Draw a UFC title fight or verified main event at random and see how the matchup looked going in.',
      {href:viewerUrl('/events'),text:'← All events'}),
    card,h('div',{class:'time-controls'},another,status));
}

function upsetResultRow(bout){
  const {winner,opponent}=bout;
  const side=(fighter,won)=>h('div',{class:'upset-side'+(won?' upset-winner':'')},
    h('strong',{class:'upset-grade','aria-label':'Pre-fight rating '+fighter.grade,text:fighter.grade}),
    h('div',null,boutName(fighter),won?h('small',{text:'Winner'}):null));
  return h('article',{class:'card upset-result'},
    h('div',{class:'upset-result-summary'},
      h('time',{dateTime:bout.date,text:niceDate(bout.date)}),
      h('span',{text:bout.gap+' rating points lower'})),
    h('div',{class:'upset-result-pair'},side(winner,true),h('span',{class:'upset-vs',text:'vs'}),side(opponent,false)),
    h('div',{class:'upset-result-foot'},
      h('span',{class:'muted',text:[bout.method?.replace('Decision - Unanimous','Unanimous decision').replace('Decision - Split','Split decision'),bout.title?'Title fight':null].filter(Boolean).join(' · ')}),
      h('div',{class:'event-extra-links'},
        h('a',{class:'event-back',href:comparisonUrl([winner,opponent],bout.date),text:'Pre-fight comparison'}),
        h('a',{class:'event-back',href:fightUrl(bout.id),text:'Fight details'}))));
}

function renderUpsets(data){
  const header=eventHeader('Upset Tracker','The fighter with the lower pre-fight UPSET rating won. See the result and the numbers each fighter brought in.',
    {href:viewerUrl('/events'),text:'← All events'});
  if(!data){
    $('content').replaceChildren(header,h('p',{class:'card',text:'The tracker is available with the verified experimental v4 rating.'}));
    return;
  }
  const results=h('div',{class:'upset-results',id:'upset-results'});
  const biggest=h('button',{type:'button',class:'btn',text:'Biggest rating gaps','aria-controls':'upset-results',onclick:()=>select(false)});
  const latest=h('button',{type:'button',class:'btn',text:'Most recent','aria-controls':'upset-results',onclick:()=>select(true)});
  const more=h('button',{type:'button',class:'btn upset-more',hidden:true});
  function select(recent){
    biggest.setAttribute('aria-pressed',String(!recent));
    latest.setAttribute('aria-pressed',String(recent));
    const bouts=recent?data.latest_upsets:data.biggest;
    results.replaceChildren(...(bouts.length?bouts.slice(0,6).map(upsetResultRow):[h('p',{class:'muted',text:'No eligible results in this release.'})]));
    more.hidden=bouts.length<=6;
    more.textContent='Show '+(bouts.length-6)+' more results';
    more.onclick=()=>{
      results.append(...bouts.slice(6).map(upsetResultRow));
      results.children[6].querySelector('a')?.focus();
      more.hidden=true;
    };
  }
  select(false);
  const upcoming=data.upcoming;
  $('content').replaceChildren(...[header,
    h('div',{class:'upset-guide'},
      h('p',null,h('strong',{text:'What’s the gap? '}),'If a fighter rated 69 beats someone rated 89, they won from 20 rating points lower. Ratings are experimental and use only fights before that bout.'),
      h('details',{class:'upset-method'},h('summary',{text:'Which fights count?'}),
        h('p',{text:'Both fighters need at least '+data.minimum_prior_bouts+' prior recorded UFC fights and a rating updated within the previous 730 days. The tracker counts decisive reviewed results where the winner had a lower rating.'}),
        h('p',{text:int(data.upset_count)+' such wins in '+int(data.eligible_bouts)+' eligible bouts, '+niceDate(data.first)+'–'+niceDate(data.latest)+'.'}))),
    h('div',{class:'upset-toggle',role:'group','aria-label':'Order results'},biggest,latest),results,more,
    h('details',{class:'card upset-repeat-section'},h('summary',null,h('strong',{text:'Fighters who did it more than once'})),
      h('p',{class:'muted',text:niceDate(data.recent_since)+'–'+niceDate(data.latest)}),
      data.repeat_winners.length?h('div',{class:'event-archive-grid'},data.repeat_winners.map(row=>
        h('article',{class:'upset-repeat'},boutName(row.fighter),
          h('p',{text:row.wins+' wins in '+row.opportunities+' eligible bouts as the lower-rated fighter'}),
          h('ul',null,row.recent_results.map(bout=>h('li',null,
            h('a',{class:'event-back',href:fightUrl(bout.id),text:bout.opponent.name}),
            ' · '+niceDate(bout.date)+' · '+bout.gap+' rating points lower')))))):
        h('p',{class:'muted',text:'No fighter has two qualifying wins in this period.'})),
    upcoming?.bouts.length?h('section',{class:'event-archive'},h('h2',{text:'Close ratings at '+upcoming.name}),
      h('p',{class:'muted',text:'Within '+data.close_gap+' rating points using fights before '+niceDate(upcoming.before)}),
      h('div',{class:'event-archive-grid'},upcoming.bouts.map(bout=>
        h('a',{class:'card time-preset time-link',href:comparisonUrl(bout.fighters,upcoming.before)},
          h('strong',{text:bout.fighters.map(fighter=>fighter.name).join(' vs ')}),
          h('small',{text:'Experimental ratings '+bout.fighters.map(fighter=>fighter.grade).join(' / ')})))),
      h('a',{class:'event-time-link',href:eventUrl(upcoming.slug),text:'View full card →'})):null
  ].filter(Boolean));
}

function boutName(fighter){
  return fighter.id?h('a',{class:'event-fighter',href:viewerUrl('/fighter/'+encodeURIComponent(fighter.id)),text:fighter.name})
    :h('span',{text:fighter.name});
}

function boutResult(bout){
  if(bout.status==='pending')return bout.discrepancy?'Result time under review':'Bout coverage pending';
  if(bout.status==='scheduled')return bout.rounds+' rounds';
  const method=bout.outcome==='draw'?'Draw':bout.outcome==='nc'?'No contest':bout.method||'Method unavailable';
  return [method,bout.round?'R'+bout.round:null,bout.time].filter(Boolean).join(' · ');
}

function eventBoutRow(bout,event){
  const compare=bout.status==='results_only'?null:comparisonUrl(bout.fighters,event.date);
  return h('article',{class:'card event-bout'},
    h('div',{class:'event-pair'},bout.fighters.map(fighter=>{
      const winner=bout.winner_id&&bout.winner_id===fighter.id;
      return h('div',{class:winner?'event-winner':null},boutName(fighter),winner?h('span',{class:'event-win',text:'WIN'}):null);
    })),
    h('div',{class:'event-bout-summary'},
      h('span',{text:bout.division||'Division unavailable'}),
      bout.title&&!bout.division?.includes('Title')?h('span',{class:'title-tag',text:'TITLE'}):null,
      h('strong',{text:boutResult(bout)}),
      bout.discrepancy?h('p',null,bout.discrepancy.reason,' ',h('a',{class:'event-back',href:bout.discrepancy.source_url,
        target:'_blank',rel:'noopener',text:'Official scorecard ↗'})):null,
      bout.grade_gap!=null?h('a',{class:'event-back grade-context',href:'/upsets',
        text:bout.grade_gap+'-point grade gap'}):null),
    h('div',{class:'event-bout-actions'},
      ['reviewed','results_only'].includes(bout.status)&&!event.detail?h('a',{class:'btn',href:fightUrl(bout.id),
        text:bout.status==='results_only'?'Official result':'Fight stats'}):null,
      compare?h('a',{class:'btn',href:compare,text:bout.status==='scheduled'?'Compare':'Pre-fight comparison'}):null));
}

function renderEvent(event){
  const scheduled=event.status==='scheduled';
  const groups=new Map();
  for(const bout of event.bouts){
    const group=bout.group||(bout.status==='reviewed'?'Reviewed results':'Awaiting review');
    if(!groups.has(group))groups.set(group,[]);
    groups.get(group).push(bout);
  }
  $('content').replaceChildren(
    eventHeader(eventTitle(event),[niceDate(event.date),event.venue].filter(Boolean).join(' · '),
      {href:viewerUrl('/events'),text:'← All events'}),
    h('div',{class:'event-context'},
      scheduled?eventCountdown(event.starts_at):h('p',{text:event.reviewed_bouts+(event.status==='results_only'?' official results · paired stats unavailable':' reviewed bouts')+
        (event.pending_bouts?' · '+event.pending_bouts+' awaiting review':'')}),
      event.source_url?h('a',{href:event.source_url,target:'_blank',rel:'noopener',text:'Official UFC card ↗'}):null),
    ...[...groups].map(([group,bouts])=>h('section',{class:'event-group'},
      h('h2',{text:group}),h('div',{class:'event-bout-list'},bouts.map(bout=>eventBoutRow(bout,event))))));
}

function fightClock(seconds){
  return seconds==null?'—':Math.floor(seconds/60)+':'+String(seconds%60).padStart(2,'0');
}

function attemptText(made,attempted){
  return made==null||attempted==null?'—':made+' / '+attempted;
}

function fightStatsTable(label,fighters,stats){
  const fields=[
    ['Significant strikes',side=>attemptText(side.sig_strikes_landed,side.sig_strikes_attempted)],
    ['Takedowns',side=>attemptText(side.takedowns_landed,side.takedowns_attempted)],
    ['Knockdowns',side=>side.knockdowns??'—'],
    ['Submission attempts',side=>side.submission_attempts??'—'],
    ['Control time',side=>fightClock(side.control_seconds)]
  ];
  return h('div',{class:'event-stats-scroll'},
    h('table',{class:'event-stats'},
      h('caption',{class:'co-sr-only',text:label}),
      h('thead',null,h('tr',null,h('th',{scope:'col',text:'Statistic'}),
        fighters.map(fighter=>h('th',{scope:'col',text:fighter.name})))),
      h('tbody',null,fields.map(([name,value])=>h('tr',null,h('th',{scope:'row',text:name}),
        stats.map(side=>h('td',{text:value(side)})))))));
}

function renderFight(fight){
  const back=fight.event?{href:eventUrl(fight.event.slug),text:'← '+eventTitle(fight.event)}:
    {href:viewerUrl('/events'),text:'← All events'};
  $('content').replaceChildren(
    eventHeader(fight.fighters.map(fighter=>fighter.name).join(' vs '),
      [niceDate(fight.date),fight.division].filter(Boolean).join(' · '),back),
    eventBoutRow(fight,{date:fight.date,detail:true}),
    !fight.totals?h('p',{class:'card event-totals',text:'Official result. Paired fight statistics are unavailable for this bout.'}):
    h('section',{class:'card event-totals'},
      h('h2',{text:'Fight totals'}),
      h('p',{class:'muted',text:'Recorded fight time '+fightClock(fight.totals[0].fight_duration_seconds)+' · Made / attempted where shown.'}),
      fightStatsTable('Fight totals',fight.fighters,fight.totals)),
    fight.totals?h('section',{class:'event-rounds'},h('h2',{text:'Round by round'}),
      fight.rounds.length?fight.rounds.map(round=>h('details',{class:'card event-round'},
        h('summary',{text:'Round '+round.round}),fightStatsTable('Round '+round.round,fight.fighters,round.stats))):
        h('p',{class:'muted',text:'Paired round statistics are unavailable for this fight.'})):null,
    h('div',{class:'event-context'},
      fight.amended?h('p',{text:'Result uses the reviewed amendment.'}):null,
      fight.source_url?h('a',{href:fight.source_url,target:'_blank',rel:'noopener',text:'View source ↗'}):null));
}
