/* Dated title status comes from the API. Portraits never infer it from wins. */
function championPortrait(r, cls, matchupBadge) {
  const titles = r.championships && r.championships.titles || [];
  const portrait = avatar(r, cls);
  const frame = matchupBadge ? h('div', {class:'rating-portrait-wrap'}, portrait, matchupBadge) : portrait;
  if (!titles.length) return frame;
  const stack = h('div', {class:'champion-portrait'});
  const belts = h('div', {class:'champion-belts'});
  for (const title of titles) {
    const description = title.division + ' ' + title.label.toLowerCase();
    const belt = h('img', {
      class:'champion-belt', src:title.belt_url,
      alt:r.name + ' — ' + description,
      title:description + ' · Verified ' + title.verified_at,
      width:2169, height:725, decoding:'async'
    });
    belt.onerror = () => { belt.hidden = true; };
    belts.append(belt);
  }
  if (matchupBadge) stack.append(frame, belts);
  else stack.append(belts, frame);
  return stack;
}

function championBadges(r) {
  const status = r.championships;
  if (!status) return [];
  const titles = status.titles || [];
  const badges = titles.map(title => h('span', {
    class:'badge champion-status',
    title:title.division + ' · ' + title.label + ' · Verified ' + title.verified_at +
      '. Title status is independent of the L3/L5/L10 stat window.',
    text:title.division + ' ' + title.label
  }));
  if (!titles.length && status.pending_review && status.pending_divisions.includes(r.summary.division)) {
    badges.push(h('span', {class:'badge',text:'Title status under review',
      title:'A new or amended championship result needs verification.'}));
  }
  return badges;
}
