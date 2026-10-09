import React, { useState, useEffect, useCallback, useRef } from 'react';
import { getDailyLeaders, errorMessage } from '../services/api';
import useLeagueViewState from '../useLeagueViewState';
import { BOX_COLUMNS, OWNER_FILTERS, orderColumns, paceMark, valueClass, cellText, zTint, keepRow, isPickup, sortRows, defaultSort } from '../dailyLeaders';

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
    <div className="shrink-0 bg-gray-800 border border-gray-700 rounded px-1.5 py-0.5 text-[11px] leading-tight min-w-[4.5rem] sm:text-xs sm:px-2 sm:py-1 sm:min-w-[5.5rem]">
      {side(away)}{side(home)}
      <div className={`mt-0.5 truncate ${game.state === 'in' ? 'text-red-400' : 'text-gray-400'}`}>
        {game.state === 'pre' ? clock(game.start) : game.detail}
      </div>
    </div>
  );
};

const DailyLeaders = ({ config }) => {
  const points = config?.capabilities?.scoring === 'points';
  const [{ owner: ownerFilter, sort: pickedSort }, setView] = useLeagueViewState(config?.league?.id, 'daily', { owner: 'all' });
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
  const columns = orderColumns(points ? BOX_COLUMNS : (data?.categories || config?.categories || []).map(c => ({ key: c.key, label: c.label })));
  const sort = pickedSort || defaultSort(data?.preseason);
  const rows = sortRows(ownerFilter, (data?.players || []).filter(p => keepRow(ownerFilter, p)), sort);
  const counts = (data?.players || []).reduce((acc, p) => ({ ...acc, [p.owner]: (acc[p.owner] || 0) + 1 }),
                                              { pickups: (data?.players || []).filter(isPickup).length });

  const signed = (v) => (points ? v.toFixed(1) : `${v > 0 ? '+' : ''}${v.toFixed(1)}`);
  const status = data && (
    <span className="text-gray-400 text-[11px] sm:text-xs flex items-center gap-1.5 whitespace-nowrap">
      {data.live && <span className="inline-block w-2 h-2 rounded-full bg-red-500 animate-pulse" />}
      {data.next_refresh_at
        ? <>{clock(data.fetched_at)}<span className="hidden sm:inline"> · next {clock(data.next_refresh_at)}</span></>
        : data.games.length ? 'Final' : 'No games'}
      {data.next_refresh_at && (
        <button onClick={() => load(true)} disabled={refreshing} aria-label="Refresh"
                className="text-nba-orange disabled:opacity-50 px-1" title="Refetch now (at most every 2 minutes)">
          {refreshing ? '…' : '↻'}
        </button>
      )}
    </span>
  );

  // Phones: one pinned column carries rank, name, team, minutes and owner; the score is pinned
  // next to it, so the category cells scroll under both. Dimming is on the cell contents: an
  // opacity on the row would let scrolled cells show through the pinned ones.
  // Phone widths fit player + Val + five stat columns (PTS REB A-TO STL BLK) in 390px.
  const PLAYER_W = 'w-32 min-w-[8rem] max-w-[8rem] sm:w-60 sm:min-w-[15rem] sm:max-w-[15rem]';
  const VALUE_W = 'w-11 min-w-[2.75rem] max-w-[2.75rem] sm:w-16 sm:min-w-[4rem] sm:max-w-none left-32 sm:left-60';
  const STAT_W = 'min-w-[2.25rem] px-0.5 sm:min-w-0 sm:px-2';
  return (
    <div className="py-2 sm:p-6">
      <div className="flex items-center gap-2 mb-2 sm:mb-3">
        <h2 className="hidden sm:block text-2xl font-bold text-white mr-4">Daily Leaders</h2>
        <div className="flex items-center bg-gray-700 border border-gray-600 rounded-md text-sm">
          <button onClick={() => shown && setDay(shiftDate(shown, -1))}
                  className="px-2.5 py-1.5 text-gray-300 hover:text-white rounded-l-md" aria-label="Previous day">‹</button>
          <span className="py-1.5 text-white font-medium min-w-[6.5rem] text-center">
            {shown ? new Date(`${shown}T12:00:00`).toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric' }) : '…'}
          </span>
          <button onClick={() => shown && setDay(shiftDate(shown, 1))}
                  className="px-2.5 py-1.5 text-gray-300 hover:text-white rounded-r-md" aria-label="Next day">›</button>
        </div>
        {data && shown !== data.today && (
          <button onClick={() => setDay(data.today)} className="text-xs text-nba-orange px-1">Today</button>
        )}
        <span className="ml-auto">{status}</span>
      </div>

      <div className="flex gap-1 mb-2 sm:mb-3 overflow-x-auto">
        {OWNER_FILTERS.map(([key, label, short]) => (
          <button key={key} onClick={() => setView({ owner: key })}
                  className={`shrink-0 px-2 sm:px-2.5 py-1 rounded-full border text-xs font-medium ${ownerFilter === key
                    ? 'bg-nba-orange text-onaccent border-nba-orange' : 'border-gray-600 text-gray-300 hover:text-white'}`}>
            <span className="sm:hidden">{short}</span><span className="hidden sm:inline">{label}</span>{key !== 'all' && counts[key] ? <span className="opacity-70"> {counts[key]}</span> : ''}
          </button>
        ))}
        <div className="ml-auto shrink-0 flex rounded-full border border-gray-600 text-xs overflow-hidden"
             title="Val: what he put up tonight. Pace: how far ahead of his own per-minute norm.">
          {[['val', points ? 'FPTS' : 'Val'], ['pace', 'Pace']].map(([key, label]) => (
            <button key={key} onClick={() => setView({ sort: key })}
                    className={`px-2.5 py-1 ${sort === key ? 'bg-gray-600 text-white' : 'text-gray-400'}`}>{label}</button>
          ))}
        </div>
      </div>

      {data?.preseason && (
        <div className="text-[11px] sm:text-xs text-amber-300/90 mb-2">
          Preseason: starters sit second halves, so raw value favours reserves. Sorted by pace; no minutes flags
          {data.season_start && <> · regular season {new Date(`${data.season_start}T12:00:00`).toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric' })}</>}
        </div>
      )}

      {data?.stats_refresh && (
        <div className="text-[11px] sm:text-xs text-gray-400 mb-2">
          Season averages: {data.stats_refresh.done
            ? (data.stats_refresh.last === 'refreshed' || data.stats_refresh.last === 'already refreshed'
              ? 'updated with this night' : data.stats_refresh.last)
            : data.stats_refresh.running ? 'updating…' : `waiting on NBA stats (try ${data.stats_refresh.tries})`}
        </div>
      )}

      {data?.games?.length > 0 && (
        <div className="flex gap-1.5 overflow-x-auto pb-1 mb-2 sm:mb-3">
          {data.games.map(g => <GameChip key={g.id} game={g} />)}
        </div>
      )}

      {error && <div className="text-red-400 text-sm mb-2">{error}</div>}

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
          <table className="min-w-full text-xs sm:text-sm">
            <thead>
              <tr>
                <th className={`table-header sticky left-0 z-20 px-2 ${PLAYER_W}`}>Player</th>
                <th className={`table-header sticky z-20 text-center px-0.5 tracking-normal sm:tracking-wider border-r border-gray-700 ${VALUE_W}`}
                    title={points ? "This league's fantasy points"
                      : "Summed category z: how far this game moved a week's matchup, category by category"}>
                  {points ? 'FPTS' : 'Val'}
                </th>
                {columns.map(c => <th key={c.key} className={`table-header text-center whitespace-nowrap tracking-normal sm:tracking-wider ${STAT_W}`}>{c.label}</th>)}
              </tr>
            </thead>
            <tbody>
              {rows.map(p => {
                const mine = p.owner === 'mine';
                const fade = p.owner === 'taken' ? 'opacity-40' : '';
                const bg = mine ? 'bg-row-mine' : 'bg-gray-800 group-hover:bg-row-hover';
                return (
                  <tr key={p.espn_id} className="group border-t border-gray-700">
                    <td className={`sticky left-0 z-10 px-2 py-1.5 ${PLAYER_W} ${bg} ${mine ? 'shadow-[inset_3px_0_0_rgb(var(--accent))]' : ''}`}>
                      <div className={`flex items-baseline gap-1.5 ${fade}`}>
                        <span className="text-gray-500 tabular-nums text-[11px] w-5 shrink-0 text-right">{p.rank}</span>
                        <div className="min-w-0 flex-1">
                          <div className="flex items-center gap-1 min-w-0">
                            <span className={`font-medium truncate ${mine ? 'text-nba-orange' : 'text-white'}`} title={p.name}>{p.name}</span>
                            {p.streak && <span className="shrink-0 text-[11px]" title={p.streak === 'hot' ? 'Last 10 games well above his season' : 'Last 10 games well below his season'}>{p.streak === 'hot' ? '🔥' : '🧊'}</span>}
                          </div>
                          <div className="text-[11px] text-gray-400 flex items-center gap-1 whitespace-nowrap">
                            {p.game_state === 'in' && <span className="w-1.5 h-1.5 rounded-full bg-red-500 shrink-0" title="Playing now" />}
                            <span>{p.team}<span className="hidden sm:inline"> vs {p.opp}</span> · </span>
                            <span className={p.minutes_up ? 'text-green-400 font-semibold' : ''}
                                  title={p.min_usual ? `Usual ${p.min_usual} min` : undefined}>{p.MIN}m</span>
                            {p.owner !== 'free' && (
                              <span className={`ml-auto px-1 rounded text-[10px] font-semibold truncate ${mine ? 'bg-nba-orange text-onaccent' : 'bg-gray-700 text-gray-300'}`}
                                    title={p.owner_name}>{p.owner_abv}</span>
                            )}
                          </div>
                        </div>
                      </div>
                    </td>
                    <td className={`sticky z-10 text-center px-0.5 text-[11px] sm:text-sm font-semibold tabular-nums whitespace-nowrap border-r border-gray-700 ${VALUE_W} ${bg}`}>
                      <span className={`${fade} ${valueClass(p.value, points)}`}>
                        {signed(p.value)}
                        {(() => {
                          const mark = paceMark(p, points);
                          return mark && <span className={`text-[9px] sm:text-[10px] sm:ml-0.5 ${mark.cls}`} title={mark.title}>{mark.glyph}</span>;
                        })()}
                      </span>
                    </td>
                    {columns.map(c => (
                      <td key={c.key}
                          className={`text-center tabular-nums whitespace-nowrap ${STAT_W} text-gray-200 ${points || fade ? '' : zTint(p.z?.[c.key])} ${mine ? 'bg-row-mine' : ''}`}
                          title={!points && p.z?.[c.key] != null ? `z ${p.z[c.key] > 0 ? '+' : ''}${p.z[c.key]}` : undefined}>
                        <span className={fade}>{cellText(c.key, p)}</span>
                      </td>
                    ))}
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
