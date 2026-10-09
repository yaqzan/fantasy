// Daily Leaders helpers: what a stat line shows in a category's column, how strongly it is tinted,
// and which rows each owner filter keeps.

// Box-score columns for points leagues (their only category is FPTS).
export const BOX_COLUMNS = [
  { key: 'PTS', label: 'PTS' }, { key: 'REB', label: 'REB' }, { key: 'AST', label: 'AST' },
  { key: 'STL', label: 'STL' }, { key: 'BLK', label: 'BLK' }, { key: 'FG3M', label: '3PM' },
  { key: 'FG', label: 'FG' }, { key: 'FT', label: 'FT' }, { key: 'TOV', label: 'TO' },
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

// [key, label, phone label]
export const OWNER_FILTERS = [['all', 'All', 'All'], ['pickups', 'Pickups', 'Pickups'], ['free', 'Available', 'Free'], ['mine', 'My team', 'Mine']];

// A free agent with a positive signal: ahead of his per-minute pace, well over his usual minutes
// while at least half an SD ahead of pace (extra minutes alone flagged a quarter of preseason
// free agents), or on a hot last-10 streak. Preseason: pace only, and only for rotation players
// (projected 15+ minutes); a deep reserve beating other reserves in the fourth quarter isn't one.
export const PRESEASON_ROTATION_MIN = 15;
// Never a night that hurt you (negative value; points leagues have no zero line).
export const isPickup = (p) => p.owner === 'free' && !(p.value < 0 && p.z && Object.keys(p.z).length) && (p.preseason
  ? p.pace_signal === 'up' && (p.min_usual ?? 0) >= PRESEASON_ROTATION_MIN
  : p.pace_signal === 'up' || (p.minutes_up && (p.pace ?? 0) >= 0.5) || p.streak === 'hot');

export const keepRow = (filter, p) => filter === 'all' || (filter === 'pickups' ? isPickup(p) : p.owner === filter);

// Sort by tonight's value (the server's order) or by pace. Pickups always read by pace.
export const sortRows = (filter, rows, sort = 'val') => (filter === 'pickups' || sort === 'pace'
  ? [...rows].sort((a, b) => (b.pace ?? -99) - (a.pace ?? -99)) : rows);

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
