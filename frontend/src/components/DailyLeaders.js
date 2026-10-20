import React, { useState, useEffect, useCallback, useRef } from 'react';
import { getDailyLeaders, errorMessage } from '../services/api';
import useLeagueViewState from '../useLeagueViewState';
import { PlayerName } from './PlayerCard';
import { BOX_COLUMNS, OWNER_FILTERS, orderColumns, paceMark, valueClass, fptsClass, paceDeltaClass, inGame, toggleGame, cellText, zTint, keepRow, orderGames, sortRows, defaultSort, paceRanks, worstDrag } from '../dailyLeaders';

// Every stat line of a day, live, ranked by the selected league's scoring (points leagues: their
// fantasy points; category leagues: summed per-category z, see daily_leaders.py). My players are
// highlighted, other teams' dimmed, free agents plain. The server refetches ESPN at most every
// a minute while games are on (a background poller, page open or not); the page re-asks when new data can exist.
const shiftDate = (iso, days) => {
  const d = new Date(`${iso}T12:00:00`);
  d.setDate(d.getDate() + days);
  return d.toISOString().slice(0, 10);
};
// Month grid that picks on tap (the native date dialog needs an OK press on phones).
// Days outside min..max (the season) are greyed and dead.
const pad2 = (n) => String(n).padStart(2, '0');
const DatePopover = ({ value, today, min, max, onPick, onClose }) => {
  const [ym, setYm] = useState(() => {
    const [y, m] = (value || today || new Date().toISOString().slice(0, 10)).split('-').map(Number);
    return { y, m: m - 1 };
  });
  useEffect(() => {
    const onKey = (e) => { if (e.key === 'Escape') onClose(); };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [onClose]);
  const first = new Date(Date.UTC(ym.y, ym.m, 1));
  const lead = first.getUTCDay();
  const count = new Date(Date.UTC(ym.y, ym.m + 1, 0)).getUTCDate();
  const iso = (d) => `${ym.y}-${pad2(ym.m + 1)}-${pad2(d)}`;
  const step = (n) => setYm(({ y, m }) => { const t = new Date(Date.UTC(y, m + n, 1)); return { y: t.getUTCFullYear(), m: t.getUTCMonth() }; });
  const monthKey = `${ym.y}-${pad2(ym.m + 1)}`;
  const canPrev = !min || monthKey > min.slice(0, 7);
  const canNext = !max || monthKey < max.slice(0, 7);
  const cells = [...Array(lead).fill(null), ...Array.from({ length: count }, (_, i) => i + 1)];
  return (
    <>
      <div className="fixed inset-0 z-40" onClick={onClose} />
      <div className="absolute left-1/2 -translate-x-1/2 top-full mt-1 z-50 w-72 max-w-[92vw] rounded-lg bg-gray-800 border border-gray-600 shadow-2xl p-2" role="dialog" aria-label="Pick a date">
        <div className="flex items-center justify-between mb-1">
          <button onClick={() => step(-1)} disabled={!canPrev} aria-label="Previous month"
                  className="w-11 h-11 text-lg text-gray-300 hover:text-white disabled:opacity-30">‹</button>
          <span className="text-sm font-medium text-white">
            {first.toLocaleDateString('en-US', { month: 'long', year: 'numeric', timeZone: 'UTC' })}
          </span>
          <button onClick={() => step(1)} disabled={!canNext} aria-label="Next month"
                  className="w-11 h-11 text-lg text-gray-300 hover:text-white disabled:opacity-30">›</button>
        </div>
        <div className="grid grid-cols-7 text-center text-[11px] text-gray-400 mb-1">
          {['S', 'M', 'T', 'W', 'T', 'F', 'S'].map((d, i) => <span key={i}>{d}</span>)}
        </div>
        <div className="grid grid-cols-7 gap-y-0.5">
          {cells.map((d, i) => {
            if (!d) return <span key={i} />;
            const v = iso(d);
            const off = (min && v < min) || (max && v > max);
            return (
              <button key={i} disabled={off} onClick={() => onPick(v)}
                      className={`h-10 rounded-full text-sm tabular-nums touch-manipulation ${
                        v === value ? 'bg-nba-orange text-onaccent font-semibold'
                          : off ? 'text-gray-600'
                          : `hover:bg-gray-700 ${v === today ? 'text-nba-orange font-semibold' : 'text-white'}`}`}>{d}</button>
            );
          })}
        </div>
      </div>
    </>
  );
};
const clock = (iso) => (iso ? new Date(iso).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' }) : '');

const GameChip = ({ game, selected, dimmed, onToggle }) => {
  const [away, home] = [game.teams.find(t => !t.home), game.teams.find(t => t.home)];
  const scored = game.state !== 'pre';
  const side = (t) => (
    <span className={`flex justify-between gap-2 ${game.state === 'post' && !t.winner ? 'text-gray-400' : 'text-white'}`}>
      <span>{t.abbr}</span>{scored && <span className="tabular-nums">{t.score}</span>}
    </span>
  );
  return (
    <button onClick={onToggle} aria-pressed={selected} title={selected ? 'Show every game' : 'Show only this game'}
            className={`shrink-0 text-left rounded px-1.5 py-0.5 text-[11px] leading-tight min-w-[4.5rem] sm:text-xs sm:px-2 sm:py-1 sm:min-w-[5.5rem] border transition-opacity ${
              selected ? 'bg-gray-700 border-nba-orange ring-1 ring-nba-orange'
                : `bg-gray-800 ${game.state === 'in' ? 'border-gray-500' : 'border-gray-700'}`
            } ${dimmed ? 'opacity-50' : game.state === 'post' ? 'opacity-75' : ''}`}>
      {side(away)}{side(home)}
      <div className={`mt-0.5 flex items-center gap-1 ${game.state === 'in' ? 'text-red-400' : 'text-gray-400'}`}>
        <span className={`shrink-0 w-[7px] h-[7px] rounded-full ${game.state === 'pre' ? 'border-[1.5px] border-gray-400' : game.state === 'in' ? 'bg-red-500' : 'bg-gray-500'}`} />
        <span className="truncate">{game.state === 'pre' ? clock(game.start) : game.detail}</span>
      </div>
    </button>
  );
};

// Where his game stands, in the sub-line under the name: four quarter pips (the current one
// pulses red while he is on the floor, plain grey on the bench) and the clock; a finished game
// shows only the muted result. Overtime: all four filled, clock says OT.
const GameProgress = ({ p }) => {
  if (p.dnp) {
    return <span className="shrink-0 px-1 rounded border border-dashed border-gray-500 text-[10px] font-semibold text-gray-400"
                 title={p.dnp_reason || 'Did not play'}>DNP</span>;
  }
  if (p.game_state === 'post') {
    return p.game_result ? <span className="text-gray-500 tabular-nums" title="Final score">{p.game_result}</span> : null;
  }
  if (p.game_state !== 'in' || !p.game_period) return null;
  const q = p.game_period;
  const on = p.on_court;
  return (
    <span className="flex items-center gap-1 shrink-0" title={on ? 'On the floor' : on === false ? 'On the bench' : undefined}>
      <span className="flex gap-px">
        {[1, 2, 3, 4].map(i => (
          <i key={i} className={`block w-[7px] sm:w-[9px] h-[5px] rounded-[1px] ${
            i < q || q > 4 ? 'bg-gray-400' : i === q ? (on ? 'bg-red-500 animate-pulse' : 'bg-gray-400') : 'bg-gray-600'}`} />
        ))}
      </span>
      <span className={`tabular-nums ${on ? 'text-red-400 font-semibold' : ''}`}>{q > 4 ? 'OT ' : ''}{p.game_clock}</span>
    </span>
  );
};

const DailyLeaders = ({ config }) => {
  const points = config?.capabilities?.scoring === 'points';
  const [{ owner: savedOwner, sort: pickedSort }, setView] = useLeagueViewState(config?.league?.id, 'daily', { owner: 'all' });
  const ownerFilter = savedOwner === 'pickups' ? 'free' : savedOwner; // the old Pickups chip is Available now
  const [day, setDay] = useState(null);      // null = the server's default (today once games tip)
  const [gameId, setGameId] = useState(null); // a tapped scoreboard: only its players
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState(null);
  const timer = useRef(null);

  const [justChecked, setJustChecked] = useState(false); // a manual refresh that found nothing newer
  const fetchedAt = useRef(null);
  const load = useCallback(async (refresh = false) => {
    try {
      refresh ? setRefreshing(true) : setLoading(true);
      const fresh = await getDailyLeaders(day, refresh);
      if (refresh && fresh.fetched_at === fetchedAt.current) {
        setJustChecked(true);
        setTimeout(() => setJustChecked(false), 4000);
      }
      fetchedAt.current = fresh.fetched_at;
      setData(fresh);
      setError(null);
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [day]);

  useEffect(() => { load(); }, [load]);
  useEffect(() => { setGameId(null); }, [day]);

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
  const [minDay, maxDay] = data?.season_range || [];
  // Tap the date for the native calendar (min/max keep it inside the season); hold it for today.
  const [pickerOpen, setPickerOpen] = useState(false);
  const holdTimer = useRef(null);
  const held = useRef(false);
  const endHold = () => clearTimeout(holdTimer.current);
  const startHold = () => {
    held.current = false;
    holdTimer.current = setTimeout(() => {
      held.current = true;
      if (data) setDay(data.today);
    }, 450);
  };
  const columns = orderColumns(points ? BOX_COLUMNS : (data?.categories || config?.categories || []).map(c => ({ key: c.key, label: c.label, name: c.name })));
  const sort = pickedSort || defaultSort(data?.preseason);
  const game = (data?.games || []).find(g => g.id === gameId) || null;
  const pool = (data?.players || []).filter(p => inGame(game, p));
  const rows = sortRows(ownerFilter, pool.filter(p => keepRow(ownerFilter, p)), sort);
  const byPace = sort === 'pace';
  const ranks = byPace ? paceRanks(pool) : null;
  const counts = pool.reduce((acc, p) => ({ ...acc, [p.owner]: (acc[p.owner] || 0) + 1 }), {});

  const signed = (v) => (points ? v.toFixed(1) : `${v > 0 ? '+' : ''}${v.toFixed(1)}`);
  const status = data && (
    <span className="text-gray-400 text-[11px] sm:text-xs flex items-center gap-1.5 whitespace-nowrap">
      {data.live && <span className="inline-block w-2 h-2 rounded-full bg-red-500 animate-pulse" />}
      {data.next_refresh_at
        ? <>{clock(data.fetched_at)}<span className="hidden sm:inline"> · next {clock(data.next_refresh_at)}</span></>
        : data.games.length ? 'Final' : 'No games'}
      {data.next_refresh_at && (
        <button onClick={() => load(true)} disabled={refreshing} aria-label="Refresh"
                className="text-nba-orange disabled:opacity-50 px-1" title="Refetch now (the server fetches at most once a minute, so a second click soon after changes nothing)">
          {refreshing ? '…' : justChecked ? <span className="text-gray-400 text-[11px]">Up to date</span> : '↻'}
        </button>
      )}
    </span>
  );

  // Phones: one pinned column carries rank, name, team, minutes and owner; the score is pinned
  // next to it, so the category cells scroll under both. Dimming is on the cell contents: an
  // opacity on the row would let scrolled cells show through the pinned ones.
  // Phone widths fill a 400px screen with player + Val + five stat columns (PTS REB A-TO STL BLK); the
  // rest scroll. Val fits only the number: the pace arrow sits in the cell's corner on phones.
  // Points leagues: FPTS is the primary column in every sort (wider, bold; pace goes under it in Pace
  // order), paid for by narrower stat columns, which hold plain 1-2 digit counts there:
  // 166 + 48 + 5 x 32 = 374px, against 166 + 38 + 5 x 36 = 384px for categories.
  const INLINE_GAMES = 6;
  const inlineBoard = (data?.games?.length || 0) > 0 && data.games.length <= INLINE_GAMES;
  const scoreboard = (
    <div className="flex gap-1.5 overflow-x-auto thin-scrollbar">
      {orderGames(data?.games || []).map(g => (
        <GameChip key={g.id} game={g} selected={g.id === gameId} dimmed={gameId !== null && g.id !== gameId}
                  onToggle={() => setGameId(id => toggleGame(id, g.id))} />
      ))}
    </div>
  );
  const PLAYER_W ='w-[10.375rem] min-w-[10.375rem] max-w-[10.375rem] sm:w-60 sm:min-w-[15rem] sm:max-w-[15rem]';
  const VALUE_W = points
    ? 'w-[3rem] min-w-[3rem] max-w-[3rem] sm:w-20 sm:min-w-[5rem] sm:max-w-none left-[10.375rem] sm:left-60'
    : 'w-[2.375rem] min-w-[2.375rem] max-w-[2.375rem] sm:w-16 sm:min-w-[4rem] sm:max-w-none left-[10.375rem] sm:left-60';
  const STAT_W = points ? 'min-w-[2rem] px-0.5 sm:min-w-0 sm:px-2' : 'min-w-[2.25rem] px-0.5 sm:min-w-0 sm:px-2';
  return (
    <div className="py-2 sm:px-2 sm:py-1">
      {/* Phones: date stepper, the three owner chips (tap the lit one to go back to everything)
          and the sort toggle share ONE row (`contents` flattens the two sm: rows into it).
          Status text and Today link are desktop-only: on a phone the date turns orange on
          today, and tapping the date from another day jumps back to today.
          Desktop: the same pieces plus the scoreboard share one wrapping row; with more games than
          INLINE_GAMES the scoreboard drops to its own scrolling row below instead. */}
      <div className="flex items-center justify-between gap-0.5 mb-2 sm:flex sm:flex-wrap sm:justify-start sm:gap-x-3 sm:gap-y-1 sm:mb-1.5 sm:min-h-[60px]">
      <div className="contents">
        <h2 className="hidden sm:block text-lg font-bold text-white">Daily Leaders</h2>
        <div className="relative shrink-0 flex items-center bg-gray-700 border border-gray-600 rounded-md text-sm">
          <button onClick={() => shown && (!minDay || shown > minDay) && setDay(shiftDate(shown, -1))}
                  className="px-3 sm:px-3 py-2.5 min-w-[2.75rem] text-gray-300 hover:text-white rounded-l-md touch-manipulation" aria-label="Previous day">‹</button>
          {/* Tap: the calendar, limited to the season (preseason to playoffs). Hold: back to today.
              The transparent date input sits ON the label and takes the tap itself (a real touch
              on the input opens the picker on phones; showPicker() covers desktop). */}
          <div className="relative flex items-center"
               title={data && shown !== data.today ? 'Tap: pick a date. Hold: back to today' : 'Tap: pick a date'}>
          <span className={`py-2.5 font-medium min-w-[4.75rem] sm:min-w-[6.5rem] text-center select-none ${
                    data && shown === data.today ? 'text-nba-orange sm:text-white' : 'text-white'}`}>
            {shown ? (() => {
              const d = new Date(`${shown}T12:00:00`);
              return <>
                <span className="sm:hidden">{d.toLocaleDateString('en-US', { weekday: 'short' })} {d.getDate()}</span>
                <span className="hidden sm:inline">{d.toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric' })}</span>
              </>;
            })() : '…'}
          </span>
          <button aria-label="Pick a date" aria-expanded={pickerOpen}
                  onClick={() => { if (held.current) { held.current = false; return; } setPickerOpen(o => !o); }}
                  onPointerDown={startHold} onPointerUp={endHold} onPointerLeave={endHold} onPointerCancel={endHold}
                  onContextMenu={(e) => e.preventDefault()}
                  className="absolute inset-0 w-full h-full cursor-pointer touch-manipulation" />
          {pickerOpen && shown && (
            <DatePopover value={shown} today={data?.today} min={minDay} max={maxDay}
                         onPick={(v) => { setDay(v); setPickerOpen(false); }} onClose={() => setPickerOpen(false)} />
          )}
          </div>
          <button onClick={() => shown && (!maxDay || shown < maxDay) && setDay(shiftDate(shown, 1))}
                  className="px-3 sm:px-3 py-2.5 min-w-[2.75rem] text-gray-300 hover:text-white rounded-r-md touch-manipulation" aria-label="Next day">›</button>
        </div>
        {data && shown !== data.today && (
          <button onClick={() => setDay(data.today)} className="hidden sm:block text-xs text-nba-orange px-1">Today</button>
        )}
        <span className="hidden sm:block sm:order-last sm:ml-auto">{status}</span>
      </div>

      <div className="contents">
        {OWNER_FILTERS.map(([key, label, short]) => (
          <button key={key} onClick={() => setView({ owner: ownerFilter === key ? 'all' : key })}
                  aria-pressed={ownerFilter === key}
                  className={`shrink-0 px-1.5 sm:px-2.5 py-1 rounded-full border text-xs font-medium ${key === 'all' ? 'hidden sm:block' : ''} ${ownerFilter === key
                    ? 'bg-nba-orange text-onaccent border-nba-orange' : 'border-gray-600 text-gray-300 hover:text-white'}`}>
            <span className="sm:hidden">{short}</span><span className="hidden sm:inline">{label}</span>{key !== 'all' && counts[key] ? <span className="hidden sm:inline opacity-70"> {counts[key]}</span> : ''}
          </button>
        ))}
        <div className="shrink-0 flex rounded-full border border-gray-600 text-xs overflow-hidden"
             title="Best: what he put up tonight in this league's scoring. Pace: how far ahead of his own per-minute norm.">
          {[['val', 'Best'], ['pace', 'Pace']].map(([key, label]) => (
            <button key={key} onClick={() => setView({ sort: key })}
                    className={`px-2 sm:px-2.5 py-1 ${sort === key ? 'bg-gray-600 text-white' : 'text-gray-400'}`}>{label}</button>
          ))}
        </div>
      </div>
      {inlineBoard && <div className="hidden sm:flex sm:flex-1 sm:min-w-0">{scoreboard}</div>}
      </div>

      {(data?.espn_folded?.folded > 0 || data?.stats_refresh) && (
        <div className="text-[11px] sm:text-xs text-gray-400 mb-2 sm:mb-1">
          Season averages: {data.espn_folded?.folded > 0 ? 'include tonight (ESPN)' : 'not updated yet'}
          {data.stats_refresh && <> · official NBA {data.stats_refresh.done
            ? (['refreshed', 'already refreshed'].includes(data.stats_refresh.last) ? 'confirmed' : data.stats_refresh.last)
            : data.stats_refresh.running ? 'updating…' : 'pending'}</>}
        </div>
      )}

      {data?.games?.length > 0 && (
        <div className={`${inlineBoard ? 'sm:hidden' : ''} flex gap-1.5 overflow-x-auto pb-1 mb-2 sm:mb-1.5`}>{scoreboard}</div>
      )}

      {error && <div className="text-red-400 text-sm mb-2">{error}</div>}

      {loading && !data ? (
        <div className="flex justify-center py-8">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-nba-orange" />
        </div>
      ) : rows.length === 0 ? (
        <div className="text-center py-8 text-gray-400">
          {data?.games?.length && data.games.every(g => g.state === 'pre')
            ? `No game has tipped yet (first at ${clock(orderGames(data.games)[0].start)})`
            : 'No stat lines'}
        </div>
      ) : (
        <div className={`overflow-x-auto bg-gray-800 rounded-lg shadow-xl ${loading ? 'opacity-60' : ''}`}>
          <table className="min-w-full text-xs sm:text-sm">
            <thead>
              <tr>
                <th className={`table-header sticky left-0 z-20 px-2 ${PLAYER_W}`}>Player</th>
                <th className={`table-header sticky z-20 text-center px-0.5 tracking-normal sm:tracking-wider border-r border-gray-700 ${VALUE_W}`}
                    title={points ? `This league's fantasy points${byPace ? '; under it, SDs ahead of his own per-minute norm (the order)' : ''}`
                      : byPace ? 'SDs ahead of his own per-minute norm'
                      : "Summed category z: how far this game moved a week's matchup, category by category"}>
                  {points ? 'FPTS' : byPace ? 'Pace' : 'Best'}
                </th>
                {columns.map(c => <th key={c.key} title={c.name} className={`table-header text-center whitespace-nowrap tracking-normal sm:tracking-wider ${STAT_W}`}>{c.label}</th>)}
              </tr>
            </thead>
            <tbody>
              {rows.map(p => {
                const mine = p.owner === 'mine';
                const fade = p.owner === 'taken' ? 'opacity-40' : '';
                const bg = mine ? 'bg-row-mine' : 'bg-gray-800 group-hover:bg-row-hover';
                const drag = points ? null : worstDrag(p, columns);
                return (
                  <tr key={p.espn_id} className="group border-t border-gray-700">
                    <td className={`sticky left-0 z-10 px-2 py-1.5 ${PLAYER_W} ${bg} ${mine ? 'shadow-[inset_3px_0_0_rgb(var(--mine))]' : ''}`}>
                      <div className={`flex items-center gap-1.5 ${fade}`}>
                        <div className="w-5 shrink-0 flex flex-col items-center gap-0.5">
                          <span className="text-gray-500 tabular-nums text-[11px] leading-none">{p.dnp ? '–' : ranks ? ranks[p.espn_id] : p.rank}</span>
                          {p.owner === 'taken' && (
                            <span className="w-4 h-4 rounded-full border border-gray-500 text-[9px] leading-[14px] text-center font-semibold text-gray-300"
                                  title={p.owner_person ? `${p.owner_person} (${p.owner_name})` : p.owner_name}>
                              {(p.owner_person || p.owner_name || '?')[0].toUpperCase()}
                            </span>
                          )}
                        </div>
                        <div className="min-w-0 flex-1">
                          <div className="flex items-center gap-1 min-w-0">
                            <PlayerName id={p.player_id} name={p.name} className={`font-medium truncate min-w-0 ${mine ? 'text-mine' : p.vs_me ? 'text-opp' : 'text-white'}`} />
                            {p.streak && <span className="shrink-0 text-[11px]" title={p.streak === 'hot' ? 'Last 10 games well above his season' : 'Last 10 games well below his season'}>{p.streak === 'hot' ? '🔥' : '🧊'}</span>}
                          </div>
                          <div className="text-[11px] text-gray-400 flex items-center gap-1 whitespace-nowrap overflow-hidden">
                            <span>{p.team}<span className="hidden sm:inline"> vs {p.opp}</span> · </span>
                            <span className={p.minutes_up ? 'text-green-400 font-semibold' : ''}
                                  title={p.min_usual ? `Usual ${p.min_usual} min` : undefined}>{p.dnp ? 0 : p.MIN}<span className="sm:hidden">m</span><span className="hidden sm:inline"> mins</span></span>
                            <GameProgress p={p} />
                            {drag && <span className="text-red-400 font-semibold" title={`${drag.label} cost ${drag.z} z`}>−{drag.label}</span>}
                          </div>
                        </div>
                      </div>
                    </td>
                    <td className={`sticky z-10 text-center px-0.5 tabular-nums whitespace-nowrap border-r border-gray-700 ${VALUE_W} ${bg} ${
                      points ? 'text-[13px] sm:text-base font-bold' : 'text-[11px] sm:text-sm font-semibold'}`}>
                      {points ? (p.dnp ? <span className={`${fade} text-gray-500`}>–</span> : (
                        <span className={`${fade} ${fptsClass(p.value_z)}`}>
                          {signed(p.value)}
                          {byPace ? (
                            <span className={`block leading-none text-[10px] sm:text-xs font-semibold ${paceDeltaClass(p.pace)}`}
                                  title="SDs ahead of his own per-minute norm">
                              {p.pace == null ? '–' : `${p.pace > 0 ? '+' : ''}${p.pace.toFixed(1)}`}
                            </span>
                          ) : (() => {
                            const mark = paceMark(p, points);
                            return mark && <span className={`absolute top-1 right-0.5 leading-none text-[9px] sm:static sm:text-[10px] sm:ml-0.5 ${mark.cls}`} title={mark.title}>{mark.glyph}</span>;
                          })()}
                        </span>
                      )) : byPace ? (
                        <span className={`${fade} ${p.pace >= 1.5 ? 'text-sky-400' : p.pace <= -1.5 ? 'text-amber-400' : 'text-white'}`}
                              title={`Best ${signed(p.value)}`}>
                          {p.pace == null ? '–' : `${p.pace > 0 ? '+' : ''}${p.pace.toFixed(1)}`}
                        </span>
                      ) : p.dnp ? <span className={`${fade} text-gray-500`}>–</span> : <span className={`${fade} ${valueClass(p.value, points)}`}>
                        {signed(p.value)}
                        {(() => {
                          const mark = paceMark(p, points);
                          return mark && <span className={`absolute top-1 right-0.5 leading-none text-[9px] sm:static sm:text-[10px] sm:ml-0.5 ${mark.cls}`} title={mark.title}>{mark.glyph}</span>;
                        })()}
                      </span>}
                    </td>
                    {columns.map(c => {
                      // My rows: the tint is a translucent layer over the yellow, so both show.
                      const tint = zTint(p.z?.[c.key]);
                      return (
                        <td key={c.key}
                            className={`text-center tabular-nums whitespace-nowrap ${STAT_W} text-gray-200 ${mine ? 'bg-row-mine relative' : tint}`}
                            title={p.z?.[c.key] != null ? `z ${p.z[c.key] > 0 ? '+' : ''}${p.z[c.key]}` : undefined}>
                          {mine && tint && <span className={`absolute inset-0 ${tint}`} />}
                          <span className={`${fade} ${mine ? `relative ${tint.includes('text-white') ? 'text-white' : ''}` : ''}`}>{p.dnp ? '–' : cellText(c.key, p)}</span>
                        </td>
                      );
                    })}
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
