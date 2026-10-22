// Daily Leaders helpers: what a stat line shows in a category's column, how strongly it is tinted,
// and which rows each owner filter keeps.

// Box-score columns for points leagues (their only category is FPTS).
export const BOX_COLUMNS = [
  { key: 'PTS', label: 'PTS', name: 'Points' }, { key: 'REB', label: 'REB', name: 'Rebounds' }, { key: 'AST', label: 'AST', name: 'Assists' },
  { key: 'STL', label: 'STL', name: 'Steals' }, { key: 'BLK', label: 'BLK', name: 'Blocks' }, { key: 'FG3M', label: '3PM', name: 'Three-pointers made' },
  { key: 'FG', label: 'FG', name: 'Field goals made-attempted' }, { key: 'FT', label: 'FT', name: 'Free throws made-attempted' }, { key: 'TOV', label: 'TO', name: 'Turnovers' },
];

// The columns a phone shows without scrolling, in this order; a league without A-TO gets AST in
// its place. Every other column follows in the league's own order.
const FIRST_COLUMNS = ['PTS', 'REB', 'AST-TOV', 'AST', 'STL', 'BLK'];
export const orderColumns = (columns) => {
  const rank = (c) => { const i = FIRST_COLUMNS.indexOf(c.key); return i < 0 ? FIRST_COLUMNS.length : i; };
  return columns.map((c, i) => [c, i]).sort(([a, i], [b, j]) => rank(a) - rank(b) || i - j).map(([c]) => c);
};

const pct = (made, att) => (att ? (made / att).toFixed(3).replace(/^0/, '') : '-');

// The text a stat line shows under one column (a category key or a BOX_COLUMNS key).
export const cellText = (key, p) => {
  switch (key) {
    case 'FG': case 'FG%': return `${p.FGM}-${p.FGA}`;
    case 'FT': case 'FT%': return `${p.FTM}-${p.FTA}`;
    case 'TS%': return pct(p.PTS / 2, p.FGA + 0.44 * p.FTA);
    case 'EFG%': return pct(p.FGM + 0.5 * p.FG3M, p.FGA);
    case 'PPS': return p.FGA ? (p.PTS / p.FGA).toFixed(2) : '-';
    case 'AST-TOV': return p.AST - p.TOV;
    case 'NFT': return 2 * p.FTM - p.FTA;
    case 'WIN%': return p.W === null || p.W === undefined ? '…' : (p.W ? 'W' : 'L');
    case 'PLUS_MINUS': return p.PLUS_MINUS > 0 ? `+${p.PLUS_MINUS}` : p.PLUS_MINUS;
    default: return p[key] ?? '-';
  }
};

// Tint class for a category z (how far this game moved a week's matchup in that category):
// nothing inside half an SD, then three steps of green or red.
export const zTint = (z) => {
  if (z === null || z === undefined || Math.abs(z) < 0.5) return '';
  const a = Math.abs(z);
  if (z > 0) return a >= 2 ? 'bg-green-500/40 text-white' : a >= 1 ? 'bg-green-500/25' : 'bg-green-500/10';
  return a >= 2 ? 'bg-red-500/40 text-white' : a >= 1 ? 'bg-red-500/25' : 'bg-red-500/10';
};

// A Daily Leaders stat's aura: no cell fill, the value itself is tinted and, at the high end, glows. It is a
// gradient, not steps: the tint grows smoothly from AURA_FROM SD (barely) to AURA_FULL SD (full green/red; an ease-out curve, so a 1 SD stat is already over half tinted),
// the glow only fades in over the upper half of that range, and the weight firms up near the top.
// Returns null for an unremarkable stat, else { color, glow, weight } for an inline style.
const AURA_FROM = 0.4;
const AURA_FULL = 2.0;
export const zAura = (z) => {
  if (z === null || z === undefined || Math.abs(z) <= AURA_FROM) return null;
  const rgb = z > 0 ? '74,222,128' : '248,113,113';
  const t = Math.min(1, (Math.abs(z) - AURA_FROM) / (AURA_FULL - AURA_FROM));   // 0..1
  const glow = Math.max(0, (t - 0.5) / 0.5);                                   // 0 until the middle, then up
  return {
    color: `color-mix(in srgb, rgb(${rgb}) ${Math.round(Math.pow(t, 0.6) * 100)}%, currentColor)`,
    glow: glow > 0 ? `0 0 ${Math.round(4 + 9 * glow)}px rgba(${rgb},${(0.8 * glow).toFixed(2)})` : '',
    weight: t > 0.8 ? 600 : 500,
  };
};

// [key, label, phone label]
export const OWNER_FILTERS = [['all', 'All', 'All'], ['free', 'Available', 'Avail'],['mine', 'My team', 'Mine']];

// A free agent with a positive signal: ahead of his per-minute pace, well over his usual minutes
// while at least half an SD ahead of pace (extra minutes alone flagged a quarter of preseason
// free agents), or on a hot last-10 streak. Preseason: pace only, and only for rotation players
// (projected 15+ minutes); a deep reserve beating other reserves in the fourth quarter isn't one.
export const PRESEASON_ROTATION_MIN = 15;
// Never a night that hurt you (negative value; points leagues have no zero line).
export const isPickup = (p) => p.owner === 'free' && !(p.value < 0 && p.z && Object.keys(p.z).length) && (p.preseason
  ? p.pace_signal === 'up' && (p.min_usual ?? 0) >= PRESEASON_ROTATION_MIN
  : p.pace_signal === 'up' || (p.minutes_up && (p.pace ?? 0) >= 0.5) || p.streak === 'hot');

// Mine in ANY league (the server's mine_any), whichever league is selected; the owner filter and
// its counts use the same test so My team lists exactly the highlighted rows.
export const isMine = (p) => p.mine_any ?? p.owner === 'mine';
export const ownerKey = (p) => (isMine(p) ? 'mine' : p.owner);

// The saved owner pick is one key or several joined by commas ("free,mine"); 'all' or empty = no filter.
export const ownerKeys = (saved) => {
  const keys = String(saved || 'all').split(',').map(k => (k === 'pickups' ? 'free' : k)).filter(k => k && k !== 'all');
  return [...new Set(keys)];
};
export const toggleOwner = (saved, key) => {
  const keys = ownerKeys(saved);
  const next = keys.includes(key) ? keys.filter(k => k !== key) : [...keys, key];
  return next.length ? next.join(',') : 'all';
};

export const keepRow = (filter, p) => {
  if (filter === 'pickups') return isPickup(p);
  const keys = ownerKeys(filter);
  return !keys.length || keys.some(k => ownerKey(p) === k);
};

// Sort by Best, tonight's value in the league's scoring (the server's order), or by pace. Pickups
// always read by pace.
export const sortRows = (filter, rows, sort = 'val') => (filter === 'pickups' || sort === 'pace'
  ? [...rows].sort((a, b) => (b.pace ?? -99) - (a.pace ?? -99)) : rows);

// The rank shown in the pinned column follows the active sort: Best uses the server's rank, Pace
// ranks the whole slate (not just the filtered rows) by pace. {espn id: rank}.
export const paceRanks = (players) => Object.fromEntries(
  [...players].sort((a, b) => (b.pace ?? -99) - (a.pace ?? -99)).map((p, i) => [p.espn_id, i + 1]));

// The category that sank a night: the worst z at or under -2.5 (one technical, a 7-turnover game),
// so a 28-point line ranked under an 18-point one says why without scrolling to its column.
export const DRAG_Z = -2.5;
export const worstDrag = (p, columns) => {
  let worst = null;
  for (const c of columns) {
    const z = p.z?.[c.key];
    if (z != null && z <= DRAG_Z && (!worst || z < worst.z)) worst = { label: c.label, z };
  }
  return worst;
};

// Preseason starters sit the second half, so raw value favours reserves: sort by pace then,
// unless the user picked a sort.
export const defaultSort = (preseason) => (preseason ? 'pace' : 'val');

// Val's colour is how good the night was for the league (summed category z; points leagues have no
// zero line, so FPTS stays plain).
export const valueClass = (value, points) => {
  if (points) return 'text-white';
  if (value >= 3) return 'text-green-300';
  if (value >= 1) return 'text-green-400';
  if (value <= -3) return 'text-red-300';
  if (value <= -1) return 'text-red-400';
  return 'text-white';
};

// Points leagues: FPTS coloured by where the night sits in the day's rotation (value_z, SDs from the
// mean of 10+ minute lines), same steps as valueClass; plain until the server has enough lines.
export const fptsClass = (z) => {
  if (z == null) return 'text-white';
  if (z >= 2) return 'text-green-300';
  if (z >= 1) return 'text-green-400';
  if (z <= -2) return 'text-red-300';
  if (z <= -1) return 'text-red-400';
  return 'text-white';
};

// Pace delta under FPTS (or in its place on the Pace sort): sky ahead of his norm, amber behind,
// from half an SD; grey inside that.
export const paceDeltaClass = (pace) => (pace >= 0.5 ? 'text-sky-400' : pace <= -0.5 ? 'text-amber-400' : 'text-gray-400');

// The pace mark: how far ahead of (or behind) his own per-minute norm he is. Its own colours (sky up,
// amber down) so it never reads as the night's quality, which is Val's job; strength in three steps
// (faint, full, doubled); grey when it disagrees with the night (ahead of a low norm on a night
// that still hurt you). Preseason marks are hollow. null = no mark.
export const paceMark = (p, points) => {
  if (!p.pace_signal) return null;
  const up = p.pace_signal === 'up';
  const a = Math.abs(p.pace ?? 0);
  const one = up ? (p.preseason ? '△' : '▲') : (p.preseason ? '▽' : '▼');
  const disagrees = !points && (up ? p.value < 0 : p.value > 0);
  const colour = disagrees ? 'text-gray-500' : up ? 'text-sky-400' : 'text-amber-400';
  const pace = `${p.pace > 0 ? '+' : ''}${p.pace} SD ${up ? 'ahead of' : 'behind'} his per-minute norm`;
  return {
    glyph: a >= 3.5 ? one + one : one,
    cls: `${colour} ${a < 2.5 ? 'opacity-60' : ''}`,
    title: disagrees ? `${pace}, but a ${up ? 'weak' : 'good'} night for your league` : pace,
  };
};

// Tapping a game's scoreboard narrows the list to its two teams; tapping it again (or another
// game) clears or moves the filter.
export const inGame = (game, p) => !game || game.teams.some(t => t.abbr === p.team);
export const toggleGame = (selected, id) => (selected === id ? null : id);

// Scoreboard chip order: ongoing, upcoming, completed; earliest start first within each.
const STATE_ORDER = { in: 0, pre: 1, post: 2 };
export const orderGames = (games) => [...games].sort((a, b) =>
  (STATE_ORDER[a.state] ?? 3) - (STATE_ORDER[b.state] ?? 3) || String(a.start).localeCompare(String(b.start)));
