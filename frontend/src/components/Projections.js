import React, { useState, useEffect, useCallback } from 'react';
import { getTeamProjections, setTeamAdjustment, getPlayerProjections, setPlayerAdjustment, errorMessage } from '../services/api';

const inputClass = 'px-2 py-1 bg-gray-700 border border-gray-600 rounded text-white text-sm w-20 text-right focus:outline-none focus:ring-2 focus:ring-nba-orange';
const SOURCE_NAMES = {
  vegas_consensus: 'Vegas', espn_summer_forecast: 'ESPN panel', bleacher_report: 'Bleacher', si_staff: 'SI',
  sportingnews_noh: 'Sporting News', espn: 'ESPN', fantasypros: 'FantasyPros', cbs: 'CBS', fanscout: 'FanScout',
  rotowire: 'RotoWire', rookie_survey: 'Rookie survey', model: 'Our model',
};
const LINE_STATS = [['gp', 'GP', 0], ['min', 'MIN', 1], ['pts', 'PTS', 1], ['reb', 'REB', 1], ['ast', 'AST', 1],
  ['fg3m', '3PM', 1], ['stl', 'STL', 1], ['blk', 'BLK', 1], ['tov', 'TOV', 1]];
const sourceName = (key) => SOURCE_NAMES[key] || key;
const fmt = (v, digits) => (v === null || v === undefined ? '-' : Number(v).toFixed(digits));

// Team wins: every source, the accuracy-weighted index, and the owner's adjustment on top.
const TeamWins = () => {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [drafts, setDrafts] = useState({});

  const load = useCallback(() => {
    getTeamProjections().then(setData).catch(e => setError(errorMessage(e)));
  }, []);
  useEffect(() => { load(); }, [load]);

  const save = async (team) => {
    if (!(team in drafts)) return;
    try {
      await setTeamAdjustment(team, drafts[team] === '' ? 0 : parseFloat(drafts[team]));
      setDrafts(prev => { const next = { ...prev }; delete next[team]; return next; });
      load();
    } catch (e) {
      setError(errorMessage(e));
    }
  };

  if (error) return <div className="p-3 rounded bg-red-900/40 border border-red-700 text-red-200 text-sm">{error}</div>;
  if (!data) return <div className="text-gray-400 text-sm py-6">Loading team projections...</div>;
  const teams = [...data.teams].sort((a, b) => (b.final ?? 0) - (a.final ?? 0));
  return (
    <div>
      <p className="text-sm text-gray-400 mb-3">
        Projected {data.season} wins. The index weights each source by how accurate it was in past seasons
        ({data.sources.filter(s => s.weight > 0).map(s => `${sourceName(s.key)} ${Math.round(s.weight * 100)}%`).join(', ')};
        sources without a track record are shown but not counted). Your adjustment is added on top and feeds the
        Wins category and every game's win chance. Once the season starts, real records take over over about 20 games.
      </p>
      <div className="overflow-x-auto bg-gray-800 rounded-lg shadow-xl">
        <table className="min-w-full">
          <thead>
            <tr>
              <th className="table-header text-left">Team</th>
              {data.sources.map(s => <th key={s.key} className="table-header text-center">{sourceName(s.key)}</th>)}
              <th className="table-header text-center" title="Accuracy-weighted average of the sources">Index</th>
              <th className="table-header text-center" title="Lowest and highest source">Range</th>
              <th className="table-header text-center" title="Your +/- wins">Adjust</th>
              <th className="table-header text-center">Final</th>
              <th className="table-header text-center">Last season</th>
            </tr>
          </thead>
          <tbody className="bg-gray-800 divide-y divide-gray-700">
            {teams.map(t => (
              <tr key={t.team} className="hover:bg-gray-700">
                <td className="table-cell text-white font-medium">{t.team}</td>
                {data.sources.map(s => (
                  <td key={s.key} className={`table-cell text-center ${s.weight > 0 ? 'text-gray-200' : 'text-gray-500'}`}>
                    {fmt(t.sources[s.key], 1)}
                  </td>
                ))}
                <td className="table-cell text-center text-white">{fmt(t.index, 1)}</td>
                <td className="table-cell text-center text-gray-400">{t.low !== null ? `${fmt(t.low, 0)}-${fmt(t.high, 0)}` : '-'}</td>
                <td className="table-cell text-center">
                  <input
                    type="number" step="0.5" className={inputClass}
                    value={t.team in drafts ? drafts[t.team] : (t.adjustment || '')}
                    placeholder="0"
                    onChange={(e) => setDrafts(prev => ({ ...prev, [t.team]: e.target.value }))}
                    onBlur={() => save(t.team)}
                    onKeyDown={(e) => { if (e.key === 'Enter') save(t.team); }}
                  />
                </td>
                <td className={`table-cell text-center font-semibold ${t.adjustment ? 'text-nba-orange' : 'text-white'}`}>{fmt(t.final, 1)}</td>
                <td className="table-cell text-center text-gray-400">{t.last_record ? `${t.last_record[0]}-${t.last_record[1]}` : '-'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
};

// Players: the blended line, each source's line, and the owner's adjustment.
const PlayerLines = () => {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [search, setSearch] = useState('');
  const [open, setOpen] = useState(null);
  const [drafts, setDrafts] = useState({});

  const load = useCallback((q) => {
    getPlayerProjections(q).then(setData).catch(e => setError(errorMessage(e)));
  }, []);
  useEffect(() => {
    const timer = setTimeout(() => load(search), 250);
    return () => clearTimeout(timer);
  }, [search, load]);

  const save = async (player) => {
    const draft = drafts[player.id];
    if (!draft) return;
    const pct = draft.pct !== undefined ? draft.pct : (player.adjustment ? Math.round((player.adjustment.production - 1) * 100) : 0);
    const games = draft.games !== undefined ? draft.games : (player.adjustment?.games ?? '');
    try {
      await setPlayerAdjustment(player.id, 1 + (parseFloat(pct || 0) / 100), games === '' ? null : parseFloat(games));
      setDrafts(prev => { const next = { ...prev }; delete next[player.id]; return next; });
      load(search);
    } catch (e) {
      setError(errorMessage(e));
    }
  };

  const edit = (id, field, value) => setDrafts(prev => ({ ...prev, [id]: { ...prev[id], [field]: value } }));

  return (
    <div>
      <p className="text-sm text-gray-400 mb-3">
        Each player's line is the experts' average blended with our model (more expert weight for rookies and young
        players, more model for veterans and players who changed teams). Rank and $ are this league's. Adjust
        production (all counting stats and minutes, in %) or games if you see it differently. Click a player to compare sources.
      </p>
      <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search a player"
             className="mb-3 px-3 py-1.5 bg-gray-700 border border-gray-600 rounded-md text-white text-sm w-64" />
      {error && <div className="mb-3 p-3 rounded bg-red-900/40 border border-red-700 text-red-200 text-sm">{error}</div>}
      {!data ? <div className="text-gray-400 text-sm py-6">Loading player projections...</div> : (
        <div className="overflow-x-auto bg-gray-800 rounded-lg shadow-xl">
          <table className="min-w-full">
            <thead>
              <tr>
                <th className="table-header text-center">#</th>
                <th className="table-header text-left">Player</th>
                {LINE_STATS.map(([k, label]) => <th key={k} className="table-header text-center">{label}</th>)}
                <th className="table-header text-center">$</th>
                <th className="table-header text-center" title="Production +/- %">Prod %</th>
                <th className="table-header text-center" title="Replace projected games">Games</th>
              </tr>
            </thead>
            <tbody className="bg-gray-800 divide-y divide-gray-700">
              {data.players.map(p => (
                <React.Fragment key={p.id}>
                  <tr className={`hover:bg-gray-700 ${p.adjustment ? 'bg-nba-orange/5' : ''}`}>
                    <td className="table-cell text-center text-gray-300">{p.rank}</td>
                    <td className="table-cell cursor-pointer" onClick={() => setOpen(open === p.id ? null : p.id)}>
                      <div className="font-medium text-white">{p.name}</div>
                      <div className="text-xs text-gray-400">{p.team} · {p.position} · {p.type} · {Object.keys(p.sources).length} sources</div>
                    </td>
                    {LINE_STATS.map(([k, , d]) => <td key={k} className="table-cell text-center text-gray-200">{fmt(p.line[k], d)}</td>)}
                    <td className="table-cell text-center text-green-400 font-semibold">${p.auction_value}</td>
                    <td className="table-cell text-center">
                      <input type="number" step="1" className={inputClass} placeholder="0"
                             value={drafts[p.id]?.pct ?? (p.adjustment ? Math.round((p.adjustment.production - 1) * 100) : '')}
                             onChange={(e) => edit(p.id, 'pct', e.target.value)}
                             onBlur={() => save(p)} onKeyDown={(e) => { if (e.key === 'Enter') save(p); }} />
                    </td>
                    <td className="table-cell text-center">
                      <input type="number" step="1" className={inputClass} placeholder={fmt(p.line.gp, 0)}
                             value={drafts[p.id]?.games ?? (p.adjustment?.games ?? '')}
                             onChange={(e) => edit(p.id, 'games', e.target.value)}
                             onBlur={() => save(p)} onKeyDown={(e) => { if (e.key === 'Enter') save(p); }} />
                    </td>
                  </tr>
                  {open === p.id && (
                    <tr className="bg-gray-900/60">
                      <td></td>
                      <td className="table-cell text-xs text-gray-400" colSpan={1}>Sources (per game)</td>
                      <td colSpan={LINE_STATS.length + 3} className="table-cell">
                        <table className="text-xs">
                          <tbody>
                            {Object.entries(p.sources).map(([source, line]) => (
                              <tr key={source}>
                                <td className="pr-4 text-gray-300">{sourceName(source)}</td>
                                {LINE_STATS.map(([k, label, d]) => (
                                  <td key={k} className="px-2 text-gray-400">{label} {fmt(line[k], d)}</td>
                                ))}
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </td>
                    </tr>
                  )}
                </React.Fragment>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
};

const Projections = () => {
  const [view, setView] = useState('teams');
  return (
    <div className="p-6">
      <h2 className="text-2xl font-bold text-white mb-4">Projections</h2>
      <div className="flex gap-2 mb-4">
        {[['teams', 'Team wins'], ['players', 'Players']].map(([key, label]) => (
          <button key={key} onClick={() => setView(key)}
                  className={`px-3 py-1.5 rounded text-sm ${view === key ? 'bg-nba-orange text-white' : 'bg-gray-700 text-gray-300 hover:bg-gray-600'}`}>
            {label}
          </button>
        ))}
      </div>
      {view === 'teams' ? <TeamWins /> : <PlayerLines />}
    </div>
  );
};

export default Projections;
