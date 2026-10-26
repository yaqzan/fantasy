import { useEffect, useState } from 'react';

// A tab's view state (stats timeframe, week, punts, filters...), kept per league in localStorage
// under fantasy.view.<league>.<tab>, so switching leagues and back lands where you left each tab.
// Only what the user picked is stored: until then `defaults` apply (and may change, e.g. the
// league's default timeframe once its season starts). `sanitize(picked)` drops stored values the
// league no longer has (a removed category, a week that isn't in the schedule).
const read = (key) => {
  try { return JSON.parse(localStorage.getItem(key)) || {}; } catch (e) { return {}; }
};

export default function useLeagueViewState(leagueId, tab, defaults, sanitize = (picked) => picked) {
  const key = `fantasy.view.${leagueId}.${tab}`;
  const [picked, setPicked] = useState(() => sanitize(read(key)));
  useEffect(() => {
    try { localStorage.setItem(key, JSON.stringify(picked)); } catch (e) { /* storage blocked */ }
  }, [key, picked]);
  const set = (patch) => setPicked(prev => ({ ...prev, ...(typeof patch === 'function' ? patch({ ...defaults, ...prev }) : patch) }));
  return [{ ...defaults, ...picked }, set];
}

// The stats choices every tab offers. 'projected' is THE projection: the model moved by this season's preseason
// games and then by his real games, with extra weight on the last 10 (backend inseason.py). The rest are plain averages.
// The NBA season now running, as the backend labels it ('2026-27'; the season starts in October).
export const seasonLabel = () => {
  const d = new Date();
  const y = d.getMonth() >= 8 ? d.getFullYear() : d.getFullYear() - 1;
  return `${y}-${String((y + 1) % 100).padStart(2, '0')}`;
};

export const statOptions = () => [
  ['projected', `${seasonLabel()} Running Projection`], ['season', 'Season Average'], ['10', 'Last 10 Games'], ['5', 'Last 5 Games'],
];

// Drops a stored stats choice the league can't offer any more.
export const validStat = (config, options) => (picked) => {
  const out = { ...picked };
  if (out.statType && !statOptions(config, options).some(([value]) => value === out.statType)) delete out.statType;
  return out;
};
