import React, { useEffect, useMemo, useRef, useState } from 'react';
import { analyze, getPickups, errorMessage } from '../services/api';
import useLeagueViewState, { statOptions, validStat } from '../useLeagueViewState';
import { WeekSelect, defaultWeekStart, validWeek, selectClass, shortDate, weekdayLetter, weekDays } from '../weeks';

const pct = (x) => `${Math.round(x * 100)}%`;
const signed = (x, digits = 2) => `${x > 0 ? '+' : x < 0 ? '-' : ''}${Math.abs(x).toFixed(digits)}`;
const plays = (n) => (Number.isInteger(n) ? n : n.toFixed(1));
const chanceClass = (chance) => chance == null ? 'text-gray-200' : chance > 0.55 ? 'text-emerald-300' : chance < 0.45 ? 'text-red-300' : 'text-gray-200';
const deltaClass = (x) => x > 0.0005 ? 'text-green-400' : x < -0.0005 ? 'text-red-400' : 'text-gray-500';
const tagFor = (chance) => chance == null ? null : chance >= 0.75 ? ['safe', 'bg-green-900 text-green-200'] : chance <= 0.3 ? ['long shot', 'bg-red-900 text-red-200']
  : chance > 0.4 && chance < 0.6 ? ['swing', 'bg-amber-900 text-amber-200'] : null;

// Chance of winning the week: a points league has one category (its chance is the week's); otherwise
// the chance of winning more than half of the categories (Poisson-binomial on the category chances).
const weekChance = (side, points) => {
  if (!side) return null;
  const chances = Object.values(side.categories).map(c => c.chance);
  if (!chances.length || chances.some(c => c == null)) return null;
  if (points) return chances[0];
  let dist = [1];
  chances.forEach(p => {
    const next = new Array(dist.length + 1).fill(0);
    dist.forEach((v, i) => { next[i] += v * (1 - p); next[i + 1] += v * p; });
    dist = next;
  });
  return dist.slice(Math.floor(chances.length / 2) + 1).reduce((a, b) => a + b, 0);
};
const gamesCounted = (players) => plays(+(players || []).reduce((sum, p) => sum + p.plays, 0).toFixed(1));
const lastName = (name) => name.split(' ').slice(-1)[0];

// A player's week as one dot per day: lit where his team plays.
const DayDots = ({ days, played, lit = 'bg-nba-orange' }) => (
  <span className="inline-flex gap-0.5" role="img"
    aria-label={`Plays ${days.filter(d => played.includes(d)).map(shortDate).join(', ') || 'no days'}`}>
    {days.map(day => (
      <span key={day} title={`${shortDate(day)}${played.includes(day) ? ': plays' : ''}`}
        className={`w-4 text-center text-[9px] leading-4 rounded-sm ${played.includes(day) ? `${lit} text-onaccent` : 'bg-gray-700 text-gray-500'}`}>
        {weekdayLetter(day).slice(0, 1)}
      </span>
    ))}
  </span>
);

const RosterTable = ({ title, players, days, nameClass, dropName, addName }) => (
  <div className="min-w-0">
    <h4 className={`text-sm font-semibold mb-1 ${nameClass}`}>{title}</h4>
    <div className="text-xs space-y-0.5">
      {players.map(p => (
        <div key={p.name} className={`flex items-center justify-between gap-2 ${p.plays ? '' : 'opacity-50'}`}>
          <span className="truncate text-gray-200">
            {p.name}{p.name === addName && <span className="ml-1 text-green-400">add</span>}
            <span className="text-gray-500"> {p.positions.join('/')}</span>
            {p.injured && <span className="text-red-400"> INJ</span>}
          </span>
          <span className="flex items-center gap-1.5 shrink-0">
            <DayDots days={days} played={p.days || []} lit={nameClass === 'text-opp' ? 'bg-opp' : 'bg-nba-orange'} />
            <span className="w-8 text-right text-gray-400" title="Expected games he counts for / games his team plays">{plays(p.plays)}/{p.games}</span>
          </span>
        </div>
      ))}
      {dropName && <div className="text-red-400 line-through opacity-70">{dropName}</div>}
    </div>
  </div>
);

// Lineup Optimizer = the pickup desk (owner picked design C, 2026-10-26): the claim leads. Left, the
// week's candidates (Weekly Pickups' model) with filters; right, the one you're looking at beside the
// best pick and your roster as it is, category by category; the matchup and both rosters fold below.
// Every number comes from lineup_optimizer.py: previews are /analyze what-ifs, not client maths.
const LineupOptimizer = ({ config, onEditLeague }) => {
  const league = config.league;
  const weeks = league?.weeks || [];
  const points = config.capabilities?.scoring === 'points';
  const meta = Object.fromEntries((config.categories || []).map(c => [c.key, c]));
  const slots = league?.settings?.roster?.active;
  const rosterSize = league?.settings?.roster?.size;
  // Open days only exist with daily lineups: a weekly lineup's starters play every game.
  const openSlots = league?.settings?.roster?.daily_lineups ? slots : null;
  const [view, setView] = useLeagueViewState(league?.id, 'lineup', {
    week: defaultWeekStart(weeks), statType: config.default_stat_type || 'projected',
  }, (picked) => validWeek(weeks)(validStat(config)(picked)));
  const [data, setData] = useState(null);
  const [candidates, setCandidates] = useState([]);
  const [selected, setSelected] = useState(null);     // a candidate name, or the manual pick's
  const [manual, setManual] = useState(null);         // {name, drop}: a free agent outside the top candidates
  const [previews, setPreviews] = useState({});       // 'add|drop' -> the what-if side
  const [filter, setFilter] = useState({ games: false, cat: '', pos: '' });
  const [search, setSearch] = useState('');
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);
  const [reload, setReload] = useState(0);
  const asked = useRef(new Set());

  useEffect(() => {
    let cancelled = false;
    setLoading(true); setError(null); setData(null); setCandidates([]); setSelected(null); setManual(null);
    setPreviews({}); asked.current = new Set();
    Promise.all([analyze(view.week, view.statType), getPickups(view.week, view.statType).catch(() => null)])
      .then(([matchup, pickups]) => {
        if (cancelled) return;
        setData(matchup);
        const list = pickups?.candidates || [];
        setCandidates(list);
        setSelected(list[0]?.name || null);
      })
      .catch(err => { if (!cancelled) setError(errorMessage(err)); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [view.week, view.statType, reload]);

  const best = candidates[0] || null;
  const pick = manual && manual.name === selected ? manual : candidates.find(c => c.name === selected) || null;
  const keyOf = (c) => `${c.name}|${c.drop || ''}`;

  // The best pick and the one being looked at are scored as real what-ifs, once each.
  useEffect(() => {
    if (!data) return undefined;
    let cancelled = false;
    [best, pick].filter(Boolean).forEach(c => {
      const key = keyOf(c);
      if (asked.current.has(key)) return;
      asked.current.add(key);
      analyze(view.week, view.statType, { adds: [c.name], drops: c.drop ? [c.drop] : [] })
        .then(result => {
          if (cancelled) return;
          if (result.what_if?.error) { asked.current.delete(key); setError(result.what_if.error); return; }
          setPreviews(prev => ({ ...prev, [key]: result.what_if }));
        })
        .catch(err => { asked.current.delete(key); if (!cancelled) setError(errorMessage(err)); });
    });
    return () => { cancelled = true; };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data, best?.name, pick?.name, pick?.drop, view.week, view.statType]);

  const days = data ? weekDays(data.week_start, data.week_end) : [];
  const opponentLabel = data?.opponent === 'league average' ? 'League avg' : data?.opponent;
  const hasOpponent = !!data?.opponent;
  const claims = data?.claims_per_week || config.capabilities?.claims_per_week || 1;
  const bestSide = best ? previews[keyOf(best)] : null;
  const pickSide = pick ? previews[keyOf(pick)] : null;
  const same = !pick || !best || pick.name === best.name;
  const baseChance = weekChance(data?.current, points);

  const positions = useMemo(() => [...new Set(candidates.flatMap(c => c.positions))].sort(), [candidates]);
  const shown = candidates.filter(c => (!filter.games || c.games >= 4)
    && (!filter.cat || (c.chance_changes[filter.cat] || 0) >= 0.02)
    && (!filter.pos || c.positions.includes(filter.pos)));
  const matches = search ? (data?.free_agents || []).filter(p => p.toLowerCase().includes(search.toLowerCase())).slice(0, 6) : [];
  const droppable = data ? data.roster.filter(p => !data.undroppable.includes(p)) : [];

  const choose = (name) => { setSelected(name); };
  const chooseManual = (name) => {
    setManual({ name, drop: best?.drop || droppable[droppable.length - 1] || null, positions: [], games: 0, manual: true });
    setSelected(name); setSearch('');
  };

  const format = (key, value) => {
    const m = meta[key] || {};
    if (value == null) return '-';
    return m.percent ? value.toFixed(3) : (key === 'WIN%' || key === 'TECH') ? value.toFixed(2) : value.toFixed(value >= 100 ? 0 : 1);
  };
  const cats = data ? Object.keys(data.current.categories) : [];
  const theirGames = (data?.opponent_players || []).reduce((s, p) => s + p.plays, 0);

  // Players with a game each day, for you without the drop (the open days are where a pickup streams) and for them.
  const perDay = (players) => days.map(day => players.filter(p => (p.days || []).includes(day)).length);
  const withoutDrop = data ? data.current.players.filter(p => !(pick?.drop && p.name === pick.drop)) : [];

  const pickPlayers = pickSide?.players.find(p => p.name === pick?.name);
  const pickDays = pick?.days || pickPlayers?.days || [];

  return (
    <div className="bg-gray-800 rounded-lg shadow-xl p-3 sm:p-6">
      <div className="flex flex-wrap items-center gap-3 sm:gap-4 mb-4">
        <h2 className="text-2xl font-bold text-nba-orange mr-2 sm:mr-4">Lineup Optimizer</h2>
        <WeekSelect weeks={weeks} value={view.week} onChange={(week) => setView({ week })} />
        <div className="flex items-center space-x-2">
          <span className="text-sm text-gray-300">Stats:</span>
          <select value={view.statType} onChange={(e) => setView({ statType: e.target.value })} className={selectClass}>
            {statOptions(config).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
          </select>
        </div>
        <button onClick={() => setReload(n => n + 1)} className="btn-secondary text-sm">Refresh</button>
      </div>

      {error && (
        <div className="mb-4 p-3 rounded bg-red-900/40 border border-red-700 text-red-200 text-sm flex items-center justify-between gap-2">
          <span>{error}</span>
          {onEditLeague && <button onClick={onEditLeague} className="btn-secondary text-xs shrink-0">League settings</button>}
        </div>
      )}
      {loading && !data && <div className="py-8 flex justify-center"><div className="animate-spin rounded-full h-8 w-8 border-b-2 border-nba-orange"></div></div>}

      {data && (
        <>
          <div className="bg-gray-700 rounded-lg border border-gray-600 p-3 sm:p-4 mb-4">
            <div className="grid grid-cols-[1fr_auto_1fr] items-center gap-2 sm:gap-4">
              <div>
                <div className="text-sm font-semibold text-mine">You</div>
                {points ? (
                  <div className="text-2xl sm:text-3xl font-bold text-mine">{data.current.categories.FPTS?.mine.toFixed(0)}</div>
                ) : (
                  <div className="text-2xl sm:text-3xl font-bold text-mine">{data.current.expected != null ? data.current.expected.toFixed(1) : '-'}</div>
                )}
                <div className="text-xs text-gray-400">{points ? 'projected points' : 'categories expected'}</div>
              </div>
              <div className="text-center">
                {baseChance != null ? (
                  <>
                    <div className="text-xs uppercase tracking-wide text-gray-400">Win the week</div>
                    <div className={`text-xl sm:text-2xl font-bold ${chanceClass(baseChance)}`}>{pct(baseChance)}</div>
                  </>
                ) : <div className="text-xs text-gray-400 max-w-[8rem]">Opponent TBD: your projected week only</div>}
              </div>
              <div className="text-right">
                <div className="text-sm font-semibold text-opp truncate">{hasOpponent ? opponentLabel : 'Opponent'}</div>
                {hasOpponent && (points ? (
                  <div className="text-2xl sm:text-3xl font-bold text-opp">{data.current.categories.FPTS?.theirs?.toFixed(0)}</div>
                ) : (
                  <div className="text-2xl sm:text-3xl font-bold text-opp">{(Object.keys(data.current.categories).length - data.current.expected).toFixed(1)}</div>
                ))}
                <div className="text-xs text-gray-400">{hasOpponent ? (points ? 'projected points' : 'categories expected') : ''}</div>
              </div>
            </div>
            <p className="text-xs text-gray-400 mt-3 pt-2 border-t border-gray-600">
              {shortDate(data.week_start)} to {shortDate(data.week_end)} ({data.days} days)
              {data.opponent === 'league average' && ` · the league's average team${data.scheduled_opponent ? ` (${data.scheduled_opponent} has no roster yet)` : ''}`}
              {!data.scheduled_opponent && ' · no opponent in the schedule for this week'}
              {' · '}Games counted <span className="text-gray-200">{plays(+gamesCounted(data.current).toFixed(1))}</span>
              {data.opponent_players && <> vs <span className="text-gray-200">{plays(+theirGames.toFixed(1))}</span></>}
              {' · '}<span className="text-gray-200">{data.claims_left ?? claims}</span> of {claims} claim{claims === 1 ? '' : 's'} left
              {slots ? ` · ${slots} active slots` : ''}
            </p>
          </div>

          {/* Layout A's category tug-of-war: bar = my chance of winning the category, with the selected pickup applied */}
          <div className="bg-gray-700 rounded-lg border border-gray-600 p-3 sm:p-4 mb-4">
            <div className="flex flex-wrap items-baseline justify-between gap-2 mb-2">
              <h3 className="text-sm font-semibold text-gray-300">Categories{pickSide && pick ? <span className="font-normal text-gray-400"> · with {pick.name}</span> : ''}</h3>
              <span className="text-[11px] text-gray-500">Bar = your chance of winning it. Your total left, theirs right.</span>
            </div>
            <div className="space-y-1">
              {cats.map(k => {
                const base = data.current.categories[k];
                const row = (pickSide || data.current).categories[k];
                const chance = row.chance;
                const d = chance != null && pickSide ? chance - (base.chance ?? chance) : 0;
                const tag = chance != null && !points ? tagFor(chance) : null;
                return (
                  <div key={k} className="grid grid-cols-[3.25rem_1fr_2.5rem_1fr_3.25rem] sm:grid-cols-[4rem_1fr_3rem_1fr_6rem] items-center gap-1.5 sm:gap-2 text-xs sm:text-sm">
                    <span className="text-right text-gray-200">{format(k, row.mine)}</span>
                    <div className="relative h-4 bg-gray-800 rounded-sm" title={chance != null ? `${pct(chance)} to win ${meta[k]?.name || k}` : ''}>
                      {chance != null && <div className="absolute right-0 top-0 bottom-0 bg-nba-orange rounded-l-sm transition-[width]" style={{ width: `${chance * 100}%` }} />}
                      {chance != null && (
                        <span className="absolute left-1 top-0 text-[10px] leading-4 font-bold text-white drop-shadow">
                          {pct(chance)}{Math.abs(d) >= 0.005 && <span className={`ml-1 ${d > 0 ? 'text-green-300' : 'text-red-300'}`}>{d > 0 ? '+' : ''}{Math.round(d * 100)}</span>}
                        </span>
                      )}
                    </div>
                    <span className="text-center font-semibold text-white">{meta[k]?.label || k}</span>
                    <div className="h-4 bg-gray-800 rounded-sm">
                      {chance != null && <div className="h-full bg-opp rounded-r-sm transition-[width]" style={{ width: `${(1 - chance) * 100}%` }} />}
                    </div>
                    <span className="text-gray-300 flex items-center gap-1">
                      <span>{row.theirs != null ? format(k, row.theirs) : ''}</span>
                      {tag && <span className={`hidden sm:inline text-[9px] font-bold uppercase px-1 rounded ${tag[1]}`}>{tag[0]}</span>}
                    </span>
                  </div>
                );
              })}
            </div>
            {!points && (
              <p className="text-[11px] text-gray-500 mt-2">
                <span className="text-amber-300">swing</span> 40 to 60%: where a pickup matters · <span className="text-green-300">safe</span> 75%+ · <span className="text-red-300">long shot</span> under 30%
                {Object.keys(meta).some(k => meta[k]?.inverse) && ' · lower wins in turnover-style categories'}
              </p>
            )}
          </div>

          <div className="grid gap-4 lg:grid-cols-[minmax(0,22rem)_minmax(0,1fr)] items-start">
            {/* The candidates */}
            <div className="bg-gray-700 rounded-lg border border-gray-600 p-2 sm:p-3 min-w-0">
              <div className="flex flex-wrap gap-1.5 mb-2">
                <button onClick={() => setFilter(f => ({ ...f, games: !f.games }))} aria-pressed={filter.games}
                  className={`px-2.5 py-1 rounded-full text-xs border ${filter.games ? 'bg-nba-orange text-onaccent border-nba-orange' : 'border-gray-500 text-gray-200'}`}>4+ games</button>
                <select value={filter.pos} onChange={(e) => setFilter(f => ({ ...f, pos: e.target.value }))} aria-label="Position"
                  className="px-2 py-1 rounded-full text-xs bg-gray-700 border border-gray-500 text-gray-200">
                  <option value="">Any position</option>
                  {positions.map(p => <option key={p} value={p}>{p}</option>)}
                </select>
                <select value={filter.cat} onChange={(e) => setFilter(f => ({ ...f, cat: e.target.value }))} aria-label="Helps category"
                  className="px-2 py-1 rounded-full text-xs bg-gray-700 border border-gray-500 text-gray-200">
                  <option value="">Helps any</option>
                  {cats.map(k => <option key={k} value={k}>Helps {meta[k]?.label || k}</option>)}
                </select>
              </div>
              <div className="relative mb-2">
                <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Any free agent..."
                  className="w-full px-2 py-1 bg-gray-600 text-white text-xs rounded border border-gray-500" />
                {matches.length > 0 && (
                  <div className="absolute z-10 left-0 right-0 mt-0.5 bg-gray-800 border border-gray-500 rounded shadow-xl">
                    {matches.map(p => (
                      <div key={p} onClick={() => chooseManual(p)} className="px-2 py-1 text-xs text-white hover:bg-gray-600 cursor-pointer">{p}</div>
                    ))}
                  </div>
                )}
              </div>
              <div className="space-y-1.5 max-h-[34rem] overflow-y-auto">
                {manual && (
                  <button onClick={() => choose(manual.name)} aria-pressed={selected === manual.name}
                    className={`w-full text-left rounded-lg border p-2 ${selected === manual.name ? 'border-nba-orange bg-gray-600' : 'border-gray-600 bg-gray-800'}`}>
                    <span className="text-sm font-medium text-white">{manual.name}</span>
                    <span className="ml-2 text-xs text-gray-400">your search</span>
                  </button>
                )}
                {shown.map(c => {
                  const index = candidates.indexOf(c);
                  const on = selected === c.name;
                  return (
                    <button key={c.name} onClick={() => choose(c.name)} aria-pressed={on}
                      className={`w-full text-left rounded-lg border p-2 ${on ? 'border-nba-orange bg-gray-600' : 'border-gray-600 bg-gray-800 hover:border-gray-500'}`}>
                      <div className="flex items-baseline justify-between gap-2">
                        <span className="text-sm font-medium text-white truncate"><span className="text-gray-500 mr-1.5">{index + 1}</span>{c.name}</span>
                        <span className={`text-sm font-bold shrink-0 ${deltaClass(c.gain)}`}>{points ? `${c.gain > 0 ? '+' : ''}${Math.round(c.gain * 100)}%` : signed(c.gain)}</span>
                      </div>
                      <div className="flex flex-wrap items-center gap-x-2 gap-y-1 mt-1 text-xs text-gray-400">
                        <span>{c.team_abv} · {c.positions.join('/')}</span>
                        <span>{plays(c.plays)}/{c.games} games</span>
                        <DayDots days={days} played={c.days} />
                        {c.small_sample && <span className="text-amber-400" title="Small sample: his numbers come from only a few games">{c.gp} GP</span>}
                      </div>
                    </button>
                  );
                })}
                {!shown.length && !manual && <p className="text-xs text-gray-400 p-2">{candidates.length ? 'No candidate matches these filters.' : 'No pickup improves this week.'}</p>}
              </div>
              <p className="text-[11px] text-gray-500 mt-2">Ranked by {points ? 'the rise in your chance of winning the week' : 'extra categories you would expect to win'}, with the drop that suits each best.</p>
            </div>

            {/* The one being looked at */}
            <div className="space-y-4 min-w-0">
              {pick ? (
                <div className="bg-gray-700 rounded-lg border border-gray-600 p-3 sm:p-4">
                  <div className="flex flex-wrap items-baseline justify-between gap-2 mb-3">
                    <h3 className="text-lg font-bold text-white">{pick.name}
                      {!pick.manual && <span className="ml-2 text-xs font-normal text-gray-400">{pick.team_abv} · {pick.positions.join('/')}</span>}
                      {pick.name === best?.name && <span className="ml-2 text-[10px] font-bold uppercase px-1.5 py-0.5 rounded bg-green-900 text-green-200">best</span>}
                    </h3>
                    {pick.manual ? (
                      <label className="text-xs text-gray-300 flex items-center gap-1.5">Drop
                        <select value={pick.drop || ''} onChange={(e) => setManual(m => ({ ...m, drop: e.target.value || null }))} className={selectClass}>
                          <option value="">Open spot</option>
                          {droppable.map(p => <option key={p} value={p}>{p}</option>)}
                        </select>
                      </label>
                    ) : (
                      <span className="text-xs text-gray-300">Drop <span className="text-red-400 font-semibold">{pick.drop || 'open spot'}</span>
                        {pick.drop_score != null && pick.score != null && pick.drop_score - pick.score >= 10 &&
                          <span className="ml-1 text-amber-400" title={`Rated ${pick.drop_score} against ${pick.score}: a one-week gain for a long-term downgrade`}>downgrade</span>}
                      </span>
                    )}
                  </div>

                  <div className="overflow-x-auto">
                    <table className="w-full text-sm min-w-[22rem]">
                      <thead>
                        <tr className="text-xs text-gray-400">
                          <th className="text-left font-normal py-1">{points ? '' : 'Category'}</th>
                          {hasOpponent && <th className="text-right font-normal">You · {opponentLabel}</th>}
                          <th className="text-right font-normal">As is</th>
                          {best && <th className="text-right font-normal">{same ? 'With him' : 'Best pick'}</th>}
                          {!same && <th className="text-right font-normal">{pick.name.split(' ').slice(-1)[0]}</th>}
                        </tr>
                      </thead>
                      <tbody>
                        <tr className="border-t border-gray-600/40 font-semibold">
                          <td className="py-1 text-gray-300">{points ? 'Win the week' : 'Win the week · categories'}</td>
                          {hasOpponent && <td></td>}
                          <td className="text-right text-white">{baseChance != null ? pct(baseChance) : '-'}{!points && data.current.expected != null && <span className="text-gray-400 font-normal"> · {data.current.expected.toFixed(1)}</span>}</td>
                          {best && <td className="text-right text-white">{bestSide ? <>{pct(weekChance(bestSide, points))}{!points && <span className="text-gray-400 font-normal"> · {bestSide.expected.toFixed(1)}</span>}</> : '...'}</td>}
                          {!same && <td className="text-right text-white">{pickSide ? <>{pct(weekChance(pickSide, points))}{!points && <span className="text-gray-400 font-normal"> · {pickSide.expected.toFixed(1)}</span>}</> : '...'}</td>}
                        </tr>
                        {cats.map(k => {
                          const base = data.current.categories[k];
                          const cell = (side) => {
                            if (!side) return <span className="text-gray-500">...</span>;
                            const row = side.categories[k];
                            if (row.chance == null) return format(k, row.mine);
                            const d = row.chance - (base.chance ?? row.chance);
                            return <span className={chanceClass(row.chance)}>{pct(row.chance)}{Math.abs(d) >= 0.005 && <span className={`ml-1 text-xs ${deltaClass(d)}`}>{d > 0 ? '+' : ''}{Math.round(d * 100)}</span>}</span>;
                          };
                          const tag = tagFor(base.chance);
                          return (
                            <tr key={k} className="border-t border-gray-600/40">
                              <td className="py-1 text-gray-400">{meta[k]?.label || k}{!points && tag && <span className={`ml-1.5 text-[9px] font-bold uppercase px-1 rounded ${tag[1]}`}>{tag[0]}</span>}</td>
                              {hasOpponent && <td className="text-right text-xs text-gray-400">{format(k, base.mine)} · {format(k, base.theirs)}</td>}
                              <td className={`text-right ${chanceClass(base.chance)}`}>{base.chance != null ? pct(base.chance) : format(k, base.mine)}</td>
                              {best && <td className="text-right">{cell(bestSide)}</td>}
                              {!same && <td className="text-right">{cell(pickSide)}</td>}
                            </tr>
                          );
                        })}
                        <tr className="border-t border-gray-600/40">
                          <td className="py-1 text-gray-400">Games counted</td>
                          {hasOpponent && <td className="text-right text-xs text-gray-400">{plays(+gamesCounted(data.current).toFixed(1))} · {data.opponent_players ? plays(+theirGames.toFixed(1)) : '-'}</td>}
                          <td className="text-right text-gray-200">{plays(+gamesCounted(data.current).toFixed(1))}</td>
                          {best && <td className="text-right text-gray-200">{bestSide ? plays(+gamesCounted(bestSide).toFixed(1)) : '...'}</td>}
                          {!same && <td className="text-right text-gray-200">{pickSide ? plays(+gamesCounted(pickSide).toFixed(1)) : '...'}</td>}
                        </tr>
                      </tbody>
                    </table>
                  </div>
                  {!points && <p className="text-[11px] text-gray-500 mt-2"><span className="text-amber-300">swing</span> = 40 to 60% as is: where a pickup matters. Small numbers beside a chance are the change from your roster as it is.</p>}
                </div>
              ) : (
                !loading && <div className="bg-gray-700 rounded-lg border border-gray-600 p-4 text-sm text-gray-400">
                  {candidates.length ? 'Pick a free agent on the left.' : 'No free agent improves this week. Search one on the left to try him.'}
                </div>
              )}

              {pick && (
                <div className="bg-gray-700 rounded-lg border border-gray-600 p-3 sm:p-4">
                  <h4 className="text-sm font-semibold text-gray-300 mb-2">His days against your open days</h4>
                  <div className="overflow-x-auto">
                    <table className="text-xs min-w-[20rem] w-full">
                      <thead>
                        <tr className="text-gray-400">
                          <th className="text-left font-normal"></th>
                          {days.map(d => <th key={d} className="font-normal text-center" title={shortDate(d)}>{weekdayLetter(d)}</th>)}
                        </tr>
                      </thead>
                      <tbody>
                        <tr className="border-t border-gray-600/40">
                          <td className="py-1 text-gray-400 pr-2 whitespace-nowrap">Yours{pick.drop ? ` without ${pick.drop.split(' ').slice(-1)[0]}` : ''}</td>
                          {perDay(withoutDrop).map((n, i) => (
                            <td key={days[i]} className={`text-center ${slots && n < slots ? 'text-amber-300' : 'text-gray-200'}`} title={slots && n < slots ? 'Open slot: a pickup who plays this day adds a game' : ''}>{n}</td>
                          ))}
                        </tr>
                        <tr className="border-t border-gray-600/40">
                          <td className="py-1 text-white pr-2 whitespace-nowrap">{pick.name.split(' ').slice(-1)[0]}</td>
                          {days.map(d => {
                            const plays_ = pickDays.includes(d);
                            const open = slots && perDay(withoutDrop)[days.indexOf(d)] < slots;
                            return <td key={d} className="text-center">{plays_ ? <span className={open ? 'text-green-400 font-bold' : 'text-gray-400'}>{open ? 'fills' : 'full'}</span> : ''}</td>;
                          })}
                        </tr>
                        {data.opponent_players && (
                          <tr className="border-t border-gray-600/40">
                            <td className="py-1 text-opp pr-2 whitespace-nowrap">{opponentLabel}</td>
                            {perDay(data.opponent_players).map((n, i) => (
                              <td key={days[i]} className={`text-center ${slots && n < slots ? 'text-amber-300' : 'text-gray-200'}`}>{n}</td>
                            ))}
                          </tr>
                        )}
                      </tbody>
                    </table>
                  </div>
                  <p className="text-[11px] text-gray-500 mt-2">Players with a game each day{slots ? `; amber is under your ${slots} active slots, so a pickup who plays that day fills one` : ''}.</p>
                </div>
              )}

              <details className="bg-gray-700 rounded-lg border border-gray-600 p-3 sm:p-4">
                <summary className="cursor-pointer text-sm font-semibold text-gray-200">Matchup and both rosters</summary>
                <div className="grid gap-4 sm:grid-cols-2 mt-3">
                  <RosterTable title={pickSide && pick ? `Your roster with ${pick.name}` : 'Your roster'} players={(pickSide || data.current).players}
                    days={days} nameClass="text-mine" dropName={pickSide ? pick?.drop : null} addName={pickSide ? pick?.name : null} />
                  {data.opponent_players
                    ? <RosterTable title={opponentLabel} players={data.opponent_players} days={days} nameClass="text-opp" />
                    : <p className="text-xs text-gray-400">{hasOpponent ? 'No roster for the opponent yet.' : 'No opponent set for this week.'}</p>}
                </div>
                {data.il?.length > 0 && <p className="text-xs text-gray-500 mt-3">Injured list (no spot, no games): {data.il.join(', ')}</p>}
                <p className="text-xs text-gray-500 mt-2">
                  {config.league?.settings?.roster?.daily_lineups
                    ? 'Daily lineups: each day your best players who play and fit the starting slots count.'
                    : 'Weekly lineup: your best starters who fit the slots play every game.'}
                </p>
              </details>
            </div>
          </div>
        </>
      )}
    </div>
  );
};

export default LineupOptimizer;
