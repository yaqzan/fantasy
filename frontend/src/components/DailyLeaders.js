import React, { useState, useEffect, useCallback, useRef } from 'react';
import { getDailyLeaders, errorMessage } from '../services/api';
import useLeagueViewState from '../useLeagueViewState';
import { BOX_COLUMNS, OWNER_FILTERS, cellText, zTint, keepRow } from '../dailyLeaders';

// Every stat line of a day, live, ranked by the selected league's scoring (points leagues: their
// fantasy points; category leagues: summed per-category z, see daily_leaders.py). My players are
// highlighted, other teams' dimmed, free agents plain. The server refetches ESPN at most every
// 10 minutes (a background poller, page open or not); the page re-asks when new data can exist.
const shiftDate = (iso, days) => {
  const d = new Date(`${iso}T12:00:00`);
  d.setDate(d.getDate() + days);
  return d.toISOString().slice(0, 10);
};
const clock = (iso) => (iso ? new Date(iso).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' }) : '');

const GameChip = ({ game }) => {
  const [away, home] = [game.teams.find(t => !t.home), game.teams.find(t => t.home)];
  const scored = game.state !== 'pre';
  const side = (t) => (
    <span className={`flex justify-between gap-2 ${game.state === 'post' && !t.winner ? 'text-gray-400' : 'text-white'}`}>
      <span>{t.abbr}</span>{scored && <span className="tabular-nums">{t.score}</span>}
    </span>
  );
  return (
    <div className="shrink-0 bg-gray-800 border border-gray-700 rounded-md px-2 py-1 text-xs min-w-[5.5rem]">
      {side(away)}{side(home)}
      <div className={`mt-0.5 ${game.state === 'in' ? 'text-red-400' : 'text-gray-400'}`}>
        {game.state === 'pre' ? clock(game.start) : game.detail}
      </div>
    </div>
  );
};

const DailyLeaders = ({ config }) => {
  const points = config?.capabilities?.scoring === 'points';
  const [{ owner: ownerFilter }, setView] = useLeagueViewState(config?.league?.id, 'daily', { owner: 'all' });
  const [day, setDay] = useState(null);      // null = the server's default (today once games tip)
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState(null);
  const timer = useRef(null);

  const load = useCallback(async (refresh = false) => {
    try {
      refresh ? setRefreshing(true) : setLoading(true);
      setData(await getDailyLeaders(day, refresh));
      setError(null);
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [day]);

  useEffect(() => { load(); }, [load]);

  // While games are unfinished, ask again just after the server's next refetch (at least a
  // minute apart); skipped while the browser tab is hidden, caught up when it shows again.
  useEffect(() => {
    clearTimeout(timer.current);
    if (!data?.next_refresh_at) return undefined;
    const wait = Math.max(60_000, new Date(data.next_refresh_at) - Date.now() + 10_000);
    timer.current = setTimeout(() => { if (!document.hidden) load(); }, wait);
    const onShow = () => { if (!document.hidden && Date.now() > new Date(data.next_refresh_at)) load(); };
    document.addEventListener('visibilitychange', onShow);
    return () => { clearTimeout(timer.current); document.removeEventListener('visibilitychange', onShow); };
  }, [data, load]);

  const shown = data?.date || day;
  const columns = points ? BOX_COLUMNS : (data?.categories || config?.categories || []).map(c => ({ key: c.key, label: c.label }));
  const rows = (data?.players || []).filter(p => keepRow(ownerFilter, p));
  const counts = (data?.players || []).reduce((acc, p) => ({ ...acc, [p.owner]: (acc[p.owner] || 0) + 1 }), {});

  return (
    <div className="py-2 sm:p-6">
      <div className="flex flex-wrap items-center gap-3 mb-3">
        <h2 className="text-xl sm:text-2xl font-bold text-white mr-auto">Daily Leaders</h2>
        <div className="flex items-center bg-gray-700 border border-gray-600 rounded-md">
          <button onClick={() => shown && setDay(shiftDate(shown, -1))}
                  className="px-3 py-2 text-gray-300 hover:text-white hover:bg-gray-600 rounded-l-md" title="Previous day">←</button>
          <span className="px-3 py-2 text-white font-medium min-w-[8.5rem] text-center">
            {shown ? new Date(`${shown}T12:00:00`).toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric' }) : '…'}
          </span>
          <button onClick={() => shown && setDay(shiftDate(shown, 1))}
                  className="px-3 py-2 text-gray-300 hover:text-white hover:bg-gray-600 rounded-r-md" title="Next day">→</button>
        </div>
        {data && shown !== data.today && (
          <button onClick={() => setDay(data.today)} className="btn-secondary py-2">Today</button>
        )}
      </div>

      <div className="flex flex-wrap items-center gap-x-4 gap-y-2 mb-3 text-sm">
        <div className="flex gap-1">
          {OWNER_FILTERS.map(([key, label]) => (
            <button key={key} onClick={() => setView({ owner: key })}
                    className={`px-3 py-1 rounded-full border text-xs font-medium ${ownerFilter === key
                      ? 'bg-nba-orange text-onaccent border-nba-orange' : 'border-gray-600 text-gray-300 hover:text-white'}`}>
              {label}{key !== 'all' && counts[key] ? ` ${counts[key]}` : ''}
            </button>
          ))}
        </div>
        {data && (
          <span className="text-gray-400 text-xs flex items-center gap-2">
            {data.live && <span className="inline-block w-2 h-2 rounded-full bg-red-500 animate-pulse" />}
            {data.next_refresh_at
              ? <>Updated {clock(data.fetched_at)} · next {clock(data.next_refresh_at)}</>
              : data.games.length ? 'All games final' : 'No games'}
            {data.next_refresh_at && (
              <button onClick={() => load(true)} disabled={refreshing}
                      className="text-nba-orange hover:underline disabled:opacity-50" title="Refetch now (at most every 2 minutes)">
                {refreshing ? 'Refreshing…' : 'Refresh'}
              </button>
            )}
          </span>
        )}
      </div>

      {data?.games?.length > 0 && (
        <div className="flex gap-2 overflow-x-auto pb-2 mb-3">
          {data.games.map(g => <GameChip key={g.id} game={g} />)}
        </div>
      )}

      {error && <div className="text-red-400 text-sm mb-3">{error}</div>}

      {loading && !data ? (
        <div className="flex justify-center py-8">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-nba-orange" />
        </div>
      ) : rows.length === 0 ? (
        <div className="text-center py-8 text-gray-400">
          {data?.games?.length && data.games.every(g => g.state === 'pre')
            ? `No game has tipped yet (first at ${clock(data.games[0].start)})`
            : 'No stat lines'}
        </div>
      ) : (
        <div className={`overflow-x-auto bg-gray-800 rounded-lg shadow-xl ${loading ? 'opacity-60' : ''}`}>
          <table className="min-w-full">
            <thead>
              <tr>
                <th className="table-header text-center w-10">#</th>
                <th className="table-header sticky left-0 z-10">Player</th>
                <th className="table-header text-center">Owner</th>
                <th className="table-header text-center">MIN</th>
                {columns.map(c => <th key={c.key} className="table-header text-center">{c.label}</th>)}
                <th className="table-header text-center" title={points ? "This league's fantasy points"
                  : 'Summed category z: how far this game moved a week\'s matchup, category by category'}>
                  {points ? 'FPTS' : 'Value'}
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-700">
              {rows.map(p => {
                const mine = p.owner === 'mine';
                return (
                  <tr key={p.espn_id}
                      className={`${mine ? 'bg-row-mine' : 'hover:bg-gray-700'} ${p.owner === 'taken' ? 'opacity-40' : ''}`}>
                    <td className="table-cell text-center text-gray-400 tabular-nums">{p.rank}</td>
                    <td className={`table-cell sticky left-0 ${mine ? 'bg-row-mine border-l-2 border-nba-orange' : 'bg-gray-800'}`}>
                      <div className={`font-medium ${mine ? 'text-nba-orange' : 'text-white'}`}>{p.name}</div>
                      <div className="text-xs text-gray-400 flex items-center gap-1">
                        {p.game_state === 'in' && <span className="w-1.5 h-1.5 rounded-full bg-red-500" title="Playing now" />}
                        {p.team} vs {p.opp}
                      </div>
                    </td>
                    <td className="table-cell text-center text-xs" title={p.owner_name || 'Free agent'}>
                      {p.owner === 'free' ? <span className="text-gray-500">FA</span>
                        : <span className={mine ? 'text-nba-orange font-semibold' : 'text-gray-300'}>{p.owner_abv}</span>}
                    </td>
                    <td className="table-cell text-center tabular-nums">{p.MIN}</td>
                    {columns.map(c => (
                      <td key={c.key} className={`table-cell text-center tabular-nums ${points ? '' : zTint(p.z?.[c.key])}`}
                          title={!points && p.z?.[c.key] != null ? `z ${p.z[c.key] > 0 ? '+' : ''}${p.z[c.key]}` : undefined}>
                        {cellText(c.key, p)}
                      </td>
                    ))}
                    <td className="table-cell text-center font-semibold text-white tabular-nums">
                      {points ? p.value.toFixed(1) : `${p.value > 0 ? '+' : ''}${p.value.toFixed(1)}`}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
};

export default DailyLeaders;
