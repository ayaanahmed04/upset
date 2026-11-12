'use strict';

function commonCount(value){return typeof value==='number'&&Number.isFinite(value)&&value>=0?value:null;}
function commonClock(value){const n=commonCount(value);return n==null?'—':Math.floor(n/60)+':'+String(Math.floor(n%60)).padStart(2,'0');}
function commonAccuracy(landed,attempted){
  const a=commonCount(landed),b=commonCount(attempted);return a!=null&&b>0&&a<=b?a/b:null;
}
function commonMeetingStats(report,opponentId,meeting){
  const fight=report?.history?.find(row=>row.fight_id===meeting.fight_id&&row.opponent_id===opponentId&&row.date===meeting.date);
  if(!fight?.own||!fight.opponent_stats)return null;
  if((fight.own.upset_fighter_id&&fight.own.upset_fighter_id!==report.id)||
     (fight.opponent_stats.upset_fighter_id&&fight.opponent_stats.upset_fighter_id!==opponentId))return null;
  const own=fight.own,other=fight.opponent_stats,ownClock=commonCount(own.fight_duration_seconds),otherClock=commonCount(other.fight_duration_seconds);
  const clockConflict=ownClock!=null&&otherClock!=null&&ownClock!==otherClock;
  const seconds=ownClock>0&&!clockConflict?ownClock:null,minutes=seconds==null?null:seconds/60;
  const landed=commonCount(own.sig_strikes_landed),absorbed=commonCount(other.sig_strikes_landed);
  const controlOwn=commonCount(own.control_seconds),controlOther=commonCount(other.control_seconds);
  const invalidControl=(own.control_seconds!=null&&controlOwn==null)||(other.control_seconds!=null&&controlOther==null)||
    (seconds!=null&&((controlOwn!=null&&controlOwn>seconds)||(controlOther!=null&&controlOther>seconds)||
      (controlOwn!=null&&controlOther!=null&&controlOwn+controlOther>seconds)));
  return {fight,own,other,seconds,minutes,clockConflict,invalidControl,
    landed,absorbed,differential:landed!=null&&absorbed!=null?landed-absorbed:null,
    landed_rate:minutes!=null&&landed!=null?landed/minutes:null,
    absorbed_rate:minutes!=null&&absorbed!=null?absorbed/minutes:null,
    differential_rate:minutes!=null&&landed!=null&&absorbed!=null?(landed-absorbed)/minutes:null,
    own_control:invalidControl?null:controlOwn,other_control:invalidControl?null:controlOther};
}
function commonFightTable(stats,report,opponentName){
  const {own,other,minutes}=stats;
  const count=value=>commonCount(value)==null?'—':int(value);
  const attempts=(side,landed,attempted)=>count(side[landed])+' / '+count(side[attempted]);
  const rate=(side,key,scale=1)=>minutes!=null&&commonCount(side[key])!=null?fmt(side[key]*scale/minutes):'—';
  const rows=[
    ['Significant strikes (landed / attempted)',attempts(own,'sig_strikes_landed','sig_strikes_attempted'),attempts(other,'sig_strikes_landed','sig_strikes_attempted')],
    ['Striking accuracy',pct1(commonAccuracy(own.sig_strikes_landed,own.sig_strikes_attempted)),pct1(commonAccuracy(other.sig_strikes_landed,other.sig_strikes_attempted))],
    ['Significant strikes landed / min',rate(own,'sig_strikes_landed'),rate(other,'sig_strikes_landed')],
    ['Knockdowns',count(own.knockdowns),count(other.knockdowns)],
    ['Takedowns (landed / attempted)',attempts(own,'takedowns_landed','takedowns_attempted'),attempts(other,'takedowns_landed','takedowns_attempted')],
    ['Takedown accuracy',pct1(commonAccuracy(own.takedowns_landed,own.takedowns_attempted)),pct1(commonAccuracy(other.takedowns_landed,other.takedowns_attempted))],
    ['Takedowns / 15 min',rate(own,'takedowns_landed',15),rate(other,'takedowns_landed',15)],
    ['Submission attempts',count(own.submission_attempts),count(other.submission_attempts)],
    ['Recorded control time',commonClock(stats.own_control),commonClock(stats.other_control)],
    ...[['Head strikes landed','head_landed'],['Body strikes landed','body_landed'],['Leg strikes landed','leg_landed'],
      ['Distance strikes landed','distance_landed'],['Clinch strikes landed','clinch_landed'],['Ground strikes landed','ground_landed']]
      .map(([label,key])=>[label,count(own[key]),count(other[key])])];
  return h('div',{class:'co-table-scroll'},h('table',{class:'co-table'},
    h('caption',{class:'co-sr-only',text:report.name+' versus '+opponentName+' on '+niceDate(stats.fight.date)}),
    h('thead',null,h('tr',null,h('th',{scope:'col',text:'Statistic'}),h('th',{scope:'col',text:report.name}),h('th',{scope:'col',text:opponentName}))),
    h('tbody',null,rows.map(([label,a,b])=>h('tr',null,h('th',{scope:'row',text:label}),h('td',{text:a}),h('td',{text:b}))))));
}
function commonFightCard(res,item,side,index){
  // Names and array position never establish which fighter owns these stats.
  const report=typeof side.fighter_id==='string'?res.fighters.find(fighter=>fighter.id===side.fighter_id):null;
  const corner=report?res.fighters.indexOf(report):index;
  const label=report?.name||'Fighter unavailable',card=h('section',{class:'co-fighter '+(corner?'blue':'red'),
    'aria-label':label+' against '+item.opponent});
  const heading=h('div',{class:'co-fighter-heading'},avatar(report||{name:label},'mini'),h('b',{text:label}));
  card.append(heading);
  if(!side.meetings?.length){card.append(h('p',{class:'muted',text:'No meetings in this window.'}));return card;}
  const body=h('div',{class:'co-fight-body'});
  function show(meeting){
    const when=[niceDate(meeting.date),meeting.result_round?'R'+meeting.result_round:null,meeting.result_time].filter(Boolean).join(' · ');
    const result=h('div',{class:'co-result'},h('span',{class:'chip '+meeting.outcome,
      title:resultLabel(meeting),text:resultChip(meeting)}),
      h('div',null,h('b',{text:displayMethod(meeting)}),h('small',{text:when})));
    const stats=commonMeetingStats(report,item.opponent_id,meeting);
    body.replaceChildren(result);
    if(meeting.result_amended)body.append(h('p',{class:'co-note',text:'Reviewed result amendment'}));
    if(!stats){
      body.append(h('p',{class:'co-note',text:meeting.results_only?'Official result · paired fight statistics unavailable.':'Fight statistics unavailable for this meeting.'}));
      if(meeting.results_only)body.append(h('a',{class:'co-source',href:fightUrl(meeting.fight_id),text:'View official result →'}));
      return;
    }
    const {own,other}=stats,count=value=>commonCount(value)==null?'—':int(value);
    const made=side=>count(side.takedowns_landed)+' / '+count(side.takedowns_attempted);
    body.append(h('p',{class:'co-context',text:[stats.fight.weight_class,stats.seconds!=null?'Recorded length '+commonClock(stats.seconds):
      stats.clockConflict?'Recorded clocks disagree; rates unavailable.':'Clock unavailable; totals shown.'].filter(Boolean).join(' · ')}),
      h('div',{class:'co-overview'},
        h('div',null,h('small',{text:'Significant strikes'}),h('b',{text:count(stats.landed)+' / '+count(stats.absorbed)}),h('small',{text:'landed / absorbed'})),
        h('div',null,h('small',{text:'Knockdowns'}),h('b',{text:count(own.knockdowns)+' / '+count(other.knockdowns)}),h('small',{text:'scored / received'})),
        h('div',null,h('small',{text:'Takedowns'}),h('b',{text:made(own)}),h('small',{text:'made / attempted · opponent '+made(other)})),
        h('div',null,h('small',{text:'Control time'}),h('b',{text:commonClock(stats.own_control)}),h('small',{text:'opponent '+commonClock(stats.other_control)}))),
      h('div',{class:'co-rates'},
        h('div',null,h('small',{text:'Landed / min'}),h('b',{text:fmt(stats.landed_rate)})),
        h('div',null,h('small',{text:'Absorbed / min'}),h('b',{text:fmt(stats.absorbed_rate)})),
        h('div',null,h('small',{text:'Difference / min'}),h('b',{text:signed(stats.differential_rate)}))),
      h('details',{class:'co-full'},h('summary',{text:'Accuracy, totals & strike breakdown'}),commonFightTable(stats,report,item.opponent)));
    if(stats.invalidControl)body.append(h('p',{class:'co-note',text:'Control totals are inconsistent; control is unavailable for this display.'}));
    const source=stats.fight.source_url;
    const cito=typeof source==='string'&&source.startsWith('https://api.citoapi.com/');
    const event=source?.match(/^https:\/\/api\.citoapi\.com\/api\/v1\/ufc\/events\/(ufc-(?:3(?:2[7-9]|3[0-2])|freedom-250|fight-night-november-07-2026))\/bouts$/)?.[1];
    const publicSource=stats.fight.result_source_url||(event?'https://www.ufc.com/event/'+event:cito?null:source);
    if(typeof publicSource==='string'&&/^https?:\/\//i.test(publicSource))body.append(h('a',{class:'co-source',href:publicSource,target:'_blank',rel:'noopener noreferrer',text:'View fight source ↗'}));
    else if(cito)body.append(h('small',{class:'co-note',text:'Recorded statistics from Cito API.'}));
  }
  if(side.meetings.length>1){
    const selector=h('select',{'aria-label':'Choose '+label+' meeting with '+item.opponent});
    side.meetings.forEach((meeting,i)=>selector.append(h('option',{value:i,text:'#'+(i+1)+' · '+niceDate(meeting.date)+' · '+
      resultChip(meeting)+' · '+displayMethod(meeting)+(meeting.result_amended?' · amended':'')})));
    selector.value='0';selector.onchange=()=>show(side.meetings[Number(selector.value)]);
    card.append(h('label',{class:'co-meeting-select'},side.meetings.length+' meetings · choose fight',selector));
  }
  card.append(body);show(side.meetings[0]);return card;
}
function renderCommonOpponentStats(res){
  const section=h('section',{class:'card common-stats'},h('div',{class:'section-title'},h('h3',{text:'Common opponents'}),
    h('small',{text:windowLabel()+' · before '+niceDate(state.before)}))),shared=res.common_opponents;
  if(!shared){section.append(h('p',{class:'muted',text:'Restart the updated server to load shared opponents.'}));return section;}
  section.append(h('p',{class:'metric-note',text:'Each fighter’s card shows a separate fight against the same opponent. Compare the dates, fight lengths and rates alongside the totals. These performances are context, not a prediction. — means unavailable; 0 means a recorded zero.'}));
  if(!shared.length){section.append(h('p',{class:'muted',text:'No shared opponents recorded in both fighters’ selected windows. Pending identity links can leave histories incomplete.'}));return section;}
  const list=h('div',{class:'co-list'});
  function show(limit){list.replaceChildren(...shared.slice(0,limit).map(item=>h('article',{class:'co-matchup'},
    h('div',{class:'co-opponent'},h('span',{class:'eyebrow',text:'Shared opponent'}),h('button',{class:'opp',type:'button',
      text:item.opponent,onclick:()=>go('#/fighter/'+encodeURIComponent(item.opponent_id))})),
    h('div',{class:'co-fighters'},item.fighters.map((side,i)=>commonFightCard(res,item,side,i))))));}
  show(6);section.append(list);
  if(shared.length>6){const more=h('button',{class:'btn more',text:'Show all '+shared.length+' common opponents',onclick:()=>{show(shared.length);more.remove();}});section.append(more);}
  return section;
}

function previousMeetingPairs(res){
  const [a,b]=res.fighters;
  if(!a?.id||!b?.id||a.id===b.id)return [];
  const byFight=new Map();
  [a,b].forEach((report,index)=>{
    for(const row of reviewedHistory(report)){
      if(row.opponent_id!==res.fighters[1-index].id||typeof row.fight_id!=='string'||
         typeof row.date!=='string'||row.date>=state.before)continue;
      const pair=byFight.get(row.fight_id)||[null,null];
      if(!pair[index])pair[index]=row;
      byFight.set(row.fight_id,pair);
    }
  });
  return [...byFight].map(([id,records])=>{
    const reference=records[0]||records[1];
    const meetings=records.map(row=>{
      const sameDay=row?.date===reference.date;
      const outcome=sameDay?row.outcome:reference.outcome==='win'?'loss':reference.outcome==='loss'?'win':reference.outcome;
      const base=sameDay?row:reference;
      return {fight_id:id,date:reference.date,outcome,result_type:outcome==='other'?base.result_type:outcome,method:base.method,result_round:base.result_round,
        result_time:base.result_time,result_amended:!!base.reviewed_result,results_only:!!base.results_only};
    });
    return {fight_id:id,date:reference.date,meetings};
  }).sort((a,b)=>b.date.localeCompare(a.date)||b.fight_id.localeCompare(a.fight_id));
}
function previousMeetingSection(res){
  const pairs=previousMeetingPairs(res);
  if(!pairs.length)return null;
  const [a,b]=res.fighters,wins=pairs.filter(pair=>pair.meetings[0].outcome==='win').length,
    losses=pairs.filter(pair=>pair.meetings[0].outcome==='loss').length,
    nonDecisive=['draw','nc','other'].map(type=>{
      const count=pairs.filter(pair=>(pair.meetings[0].result_type||pair.meetings[0].outcome)===type).length;
      return count?' · '+count+' '+({draw:count===1?'draw':'draws',nc:'NC',other:'unclassified'})[type]:'';
    }).join('');
  const section=h('section',{class:'card common-stats co-previous'},
    h('div',{class:'section-title'},h('h3',{text:'Previous meetings'}),h('small',{text:pairs.length+' recorded '+(pairs.length===1?'fight':'fights')})),
    h('p',{class:'co-series',text:a.name+' '+wins+' wins · '+b.name+' '+losses+' wins'+nonDecisive}),
    h('p',{class:'co-note',text:'All recorded meetings strictly before '+niceDate(state.before)+', regardless of the selected stats window. Reviewed results are used.'}));
  const details=h('details',{class:'co-prior-details'},h('summary',{text:'View previous fights and detailed stats'})),body=h('div',{class:'co-fighters'});
  function show(pair){
    body.replaceChildren(...res.fighters.map((report,index)=>commonFightCard(res,
      {opponent_id:res.fighters[1-index].id,opponent:res.fighters[1-index].name},
      {fighter_id:report.id,meetings:[pair.meetings[index]]},index)));
  }
  if(pairs.length>1){
    const choice=h('select',{'aria-label':'Choose previous head-to-head meeting'});
    pairs.forEach((pair,index)=>choice.append(h('option',{value:index,text:'#'+(index+1)+' · '+niceDate(pair.date)+' · '+(pair.meetings[0].method||'Unknown method')})));
    choice.value='0';choice.onchange=()=>show(pairs[Number(choice.value)]);
    details.append(h('label',{class:'co-meeting-select'},'Both columns show the selected fight',choice));
  }
  details.append(body);section.append(details);show(pairs[0]);return section;
}
