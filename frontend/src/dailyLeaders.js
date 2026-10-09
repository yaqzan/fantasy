// Daily Leaders helpers: what a stat line shows in a category's column, how strongly it is tinted,
// and which rows each owner filter keeps.

// Box-score columns for points leagues (their only category is FPTS).
export const BOX_COLUMNS = [
  { key: 'PTS', label: 'PTS' }, { key: 'REB', label: 'REB' }, { key: 'AST', label: 'AST' },
  { key: 'STL', label: 'STL' }, { key: 'BLK', label: 'BLK' }, { key: 'FG3M', label: '3PM' },
  { key: 'FG', label: 'FG' }, { key: 'FT', label: 'FT' }, { key: 'TOV', label: 'TO' },
];

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

export const OWNER_FILTERS = [['all', 'All'], ['pickups', 'Pickups'], ['free', 'Available'], ['mine', 'My team']];

// A free agent with a positive signal: ahead of his per-minute pace, well over his usual minutes
// while at least half an SD ahead of pace (extra minutes alone flagged a quarter of preseason
// free agents), or on a hot last-10 streak.
export const isPickup = (p) => p.owner === 'free'
  && (p.pace_signal === 'up' || (p.minutes_up && (p.pace ?? 0) >= 0.5) || p.streak === 'hot');

export const keepRow = (filter, p) => filter === 'all' || (filter === 'pickups' ? isPickup(p) : p.owner === filter);

// Pickups read best by pace; every other view by tonight's value (the server's order).
export const sortRows = (filter, rows) => (filter === 'pickups'
  ? [...rows].sort((a, b) => (b.pace ?? -99) - (a.pace ?? -99)) : rows);
