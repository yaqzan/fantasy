import React, { useEffect, useMemo, useRef, useState } from 'react';
import { analyze, getPickups, errorMessage } from '../services/api';
import useLeagueViewState, { statOptions, validStat } from '../useLeagueViewState';
import { PlayerName } from './PlayerCard';
import { WeekSelect, defaultWeekStart, validWeek, selectClass, shortDate, weekdayLetter, weekDays } from '../weeks';
import { orderColumns } from '../dailyLeaders';

const pct = (x) => `${Math.round(x * 100)}%`;
const signed = (x, digits = 2) => `${x > 0 ? '+' : x < 0 ? '-' : ''}${Math.abs(x).toFixed(digits)}`;
const plays = (n) => (Number.isInteger(n) ? n : n.toFixed(1));
const deltaClass = (x) => x > 0.0005 ? 'text-green-400' : x < -0.0005 ? 'text-red-400' : 'text-gray-500';
const pointsDelta = (d) => `${d > 0 ? '+' : ''}${Math.round(d * 100)}`;   // a chance change in percentage points
// Who is favoured in a category: green 55%+, red 45% or less, grey between (a toss-up).
const lean = (chance) => chance == null ? 'even' : chance >= 0.55 ? 'win' : chance <= 0.45 ? 'lose' : 'even';
const chipClass = (chance) => ({ win: 'bg-green-900/70 text-green-300', lose: 'bg-red-900/70 text-red-300', even: 'bg-gray-600 text-gray-300' })[lean(chance)];

// A chance as a coloured chip: the colour is the whole message (green favoured, red against, grey toss-up).
const Chip = ({ chance, fallback = '-', bold, faded }) => (
  <span className={`inline-block min-w-[2.75rem] rounded text-center py-0.5 px-1 tabular-nums ${bold ? 'font-bold' : 'font-semibold'} ${chipClass(chance)} ${faded ? 'opacity-50' : ''}`}>
    {chance == null ? fallback : pct(chance)}
  </span>
);

// A pick's cell in the category grid: his chance chip and its change from Now (faded when little moves).
const Cell = ({ chance, base, fallback = '-', bold }) => {
  const d = chance != null && base != null ? chance - base : 0;
  return (
    <div className="flex items-center justify-center gap-1 border-t border-gray-600/40 pt-1">
      <Chip chance={chance} fallback={fallback} bold={bold} faded={Math.abs(d) < 0.02} />
      {Math.abs(d) >= 0.005 && <span className={`text-[10px] font-semibold tabular-nums ${deltaClass(d)}`}>{pointsDelta(d)}</span>}
    </div>
  );
};


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
// Games still to play over the week's total (played + still to come), as whole numbers: 25/36.
const gamesFraction = (players, played) => {
  const left = (players || []).reduce((sum, p) => sum + p.plays, 0);
  return { left: Math.round(left), total: Math.round(left + (played || 0)) };
};

// Under a side's score: its claims left and games still to play over the week's total.
const TeamFacts = ({ claims, perWeek, games, right }) => (
  <div className={`mt-1.5 flex flex-wrap gap-x-3 gap-y-0.5 text-xs text-gray-400 tabular-nums ${right ? 'justify-end' : ''}`}>
    {claims != null && <span title="Pickup claims left this week"><span className="font-semibold text-gray-100">{claims}</span>/{perWeek} claim{perWeek === 1 ? '' : 's'}</span>}
    <span title="Games still to play (expected) over the week's total"><span className="font-semibold text-gray-100">{games.left}</span>/{games.total} games</span>
  </div>
);

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

// A whole-card control that holds a PlayerName button: a div (a button can't nest in a button) that still tabs and presses.
const CardButton = ({ onClick, children, ...props }) => (
  <div role="button" tabIndex={0} onClick={onClick} {...props}
    onKeyDown={(e) => { if ((e.key === 'Enter' || e.key === ' ') && e.target === e.currentTarget) { e.preventDefault(); onClick(); } }}>
    {children}
  </div>
);

const RosterTable = ({ title, players: all, days, nameClass, lit, dropName, addName }) => {
  const players = all.filter(p => p.name !== dropName);   // shown struck through at the bottom instead
  return (
  <div className="min-w-0">
    <h4 className={`text-sm font-semibold mb-1 ${nameClass}`}>{title}</h4>
    <div className="text-xs space-y-0.5">
      {players.map(p => (
        <div key={p.name} className={`flex items-center justify-between gap-2 ${p.plays ? '' : 'opacity-50'}`}>
          <span className="truncate text-gray-200">
            <PlayerName name={p.name} />{p.name === addName && <span className="ml-1 text-green-400">add</span>}
            <span className="text-gray-500"> {p.positions.join('/')}</span>
            {p.injured && <span className="text-red-400"> INJ</span>}
          </span>
          <span className="flex items-center gap-1.5 shrink-0">
            <DayDots days={days} played={p.days || []} lit={lit} />
            <span className="w-8 text-right text-gray-400" title="Expected games he counts for / games his team plays">{plays(p.plays)}/{p.games}</span>
          </span>
        </div>
      ))}
      {dropName && <div className="text-red-400 line-through opacity-70"><PlayerName name={dropName} /></div>}
    </div>
  </div>
  );
};

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
  const daily = !!league?.settings?.roster?.daily_lineups;
  const openSlots = daily ? slots : null;
  const [view, setView] = useLeagueViewState(league?.id, 'lineup', {
    week: defaultWeekStart(weeks), statType: config.default_stat_type || 'projected',
  }, (picked) => validWeek(weeks)(validStat(config)(picked)));
  // No claims left this week: the page opens on next week instead (a pickup can only help then), and a note offers the
  // way back to this week's chances. The owner's own week choice always wins.
  // On a week's last day the default opens on next week (its lineups are set), but a claim you still hold can catch
  // today's games: open on this week then, with a note, and move on to next week only when no claim is left.
  const lastDay = (() => {
    const t = new Date();
    const today = `${t.getFullYear()}-${String(t.getMonth() + 1).padStart(2, '0')}-${String(t.getDate()).padStart(2, '0')}`;
    const i = weeks.findIndex(w => w.start <= today && today <= w.end);
    return i >= 0 && weeks[i].end === today && weeks[i + 1] && view.week === weeks[i + 1].start ? { current: weeks[i].start, next: weeks[i + 1].start, reason: 'last-day' } : null;
  })();
  const [weekOverride, setWeekOverride] = useState(lastDay?.current || null);   // a week start shown instead of view.week
  const [autoNote, setAutoNote] = useState(lastDay);       // {current, next, reason}: the week we left and the one we moved to
  const weekChosen = useRef(false);                         // the owner picked a week himself: never switch for him
  const autoTried = useRef(false);
  const activeWeek = weekOverride || view.week;
  const [data, setData] = useState(null);
  const [candidates, setCandidates] = useState([]);
  const [pickupsError, setPickupsError] = useState(null);   // why there are no candidates (e.g. every player undroppable)
  const [selected, setSelected] = useState(null);     // a candidate name, or the manual pick's
  const [manual, setManual] = useState(null);         // {name, drop}: a free agent outside the top candidates
  const [dayPick, setDayPick] = useState({});         // name -> the day the owner moved a pickup's claim to
  const [previews, setPreviews] = useState({});       // 'add|drop' -> the what-if side, or {error}
  const [filter, setFilter] = useState({ games: false, cat: '', pos: '' });
  const [search, setSearch] = useState('');
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);
  const [reload, setReload] = useState(0);
  const asked = useRef(new Set());
  const loaded = useRef(null);                         // the matchup the previews belong to (null while loading)

  useEffect(() => {
    let cancelled = false;
    let switched = false;   // moved on to another week: the next run owns the loading flag
    setLoading(true); setError(null); setData(null); setCandidates([]); setPickupsError(null); setSelected(null); setManual(null); setDayPick({});
    setPreviews({}); asked.current = new Set();
    Promise.all([analyze(activeWeek, view.statType), getPickups(activeWeek, view.statType).catch(err => ({ error: errorMessage(err) }))])
      .then(([matchup, pickups]) => {
        if (cancelled) return;
        if (matchup.claims_left === 0 && !weekChosen.current && !autoTried.current) {
          autoTried.current = true;
          const i = weeks.findIndex(w => w.start === activeWeek);
          if (i >= 0 && weeks[i + 1]) {
            setAutoNote({ current: activeWeek, next: weeks[i + 1].start, reason: 'no-claims' });
            setWeekOverride(weeks[i + 1].start);   // the effect runs again on the new week
            switched = true;
            return;
          }
        }
        loaded.current = matchup;
        setData(matchup);
        setPickupsError(pickups?.error || null);
        const list = pickups?.candidates || [];
        setCandidates(list);
        setSelected(list[0]?.name || null);
      })
      .catch(err => { if (!cancelled) setError(errorMessage(err)); })
      .finally(() => { if (!cancelled && !switched) setLoading(false); });
    return () => { cancelled = true; loaded.current = null; };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeWeek, view.statType, reload]);

  // A claim has a day (mid-week: the pickup plays from it, the drop until the day before); the ranking suggests one
  // and the owner can move it. Every pick carries its effective day.
  const withDay = (c) => c && dayPick[c.name] ? { ...c, day: dayPick[c.name] } : c;
  const best = withDay(candidates[0]) || null;
  const pick = withDay(manual && manual.name === selected ? manual : candidates.find(c => c.name === selected)) || null;
  const keyOf = (c) => `${c.name}|${c.drop || ''}|${c.day || ''}`;
  const pickIsBest = !!(pick && best && pick.name === best.name && (pick.drop || '') === (best.drop || ''));
  // The two picks set beside "Now": the best, then the one being looked at (the runner-up while that is the best).
  const second = pickIsBest ? withDay(candidates[1]) || null : pick;

  // The two compared picks are scored as real what-ifs, once each. Requests are not
  // cancelled when the selection moves on (that left a key asked but never answered: "..." for good);
  // an answer is dropped only once the matchup it was asked for has been replaced (week, stats, Refresh).
  useEffect(() => {
    if (!data || data !== loaded.current) return;   // a stale run in the same flush as a reload
    [best, second].filter(Boolean).forEach(c => {
      const key = keyOf(c);
      if (asked.current.has(key)) return;
      asked.current.add(key);
      analyze(activeWeek, view.statType, { adds: [c.name], drops: c.drop ? [c.drop] : [], day: c.day })
        .then(result => {
          if (loaded.current !== data) return;
          setPreviews(prev => ({ ...prev, [key]: result.what_if?.error ? { error: result.what_if.error } : result.what_if }));
        })
        .catch(err => {
          if (loaded.current !== data) return;
          asked.current.delete(key);   // a failed request is retried when he's picked again
          setPreviews(prev => ({ ...prev, [key]: { error: errorMessage(err) } }));
        });
    });
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data, best?.name, best?.drop, best?.day, second?.name, second?.drop, second?.day]);

  const days = data ? weekDays(data.week_start, data.week_end) : [];
  const opponentLabel = data?.opponent === 'league average' ? 'League avg' : data?.opponent;
  const hasOpponent = !!data?.opponent;
  const claims = data?.claims_per_week || config.capabilities?.claims_per_week || 1;
  const sideOf = (c) => { const s = c && previews[keyOf(c)]; return s && !s.error ? s : null; };
  const errorOf = (c) => (c && previews[keyOf(c)]?.error) || null;
  const pickSide = sideOf(pick);
  const baseChance = weekChance(data?.current, points);
  const progress = data?.progress || { started: false };
  const hasLead = !!data && (progress.live > 0 || data.opponent === 'league average' || !data.scheduled_opponent || progress.partial);
  const canonOff = Object.entries({ ...(data?.canon?.diff_mine || {}), ...Object.fromEntries(Object.entries(data?.canon?.diff_theirs || {}).map(([k, v]) => [`opp ${k}`, v])) }).filter(([, v]) => Math.abs(v) > 0.0015).map(([k, v]) => `${k} ${v > 0 ? '+' : ''}${v}`).join(', ');
  // The sides' scores: what each has so far once a game is played, else the projection.
  const nowTotal = (side) => points ? data.current.categories.FPTS?.[side === 'mine' ? 'now_mine' : 'now_theirs'] : null;
  const scoreMine = !data ? null : progress.started
    ? (points ? nowTotal('mine')?.toFixed(0) : data.current.leading)
    : (points ? data.current.categories.FPTS?.mine.toFixed(0) : data.current.expected?.toFixed(1));
  const scoreTheirs = !data ? null : progress.started
    ? (points ? nowTotal('theirs')?.toFixed(0) : data.current.leading != null ? data.categories.length - data.current.leading : null)
    : (points ? data.current.categories.FPTS?.theirs?.toFixed(0) : data.current.expected != null ? (data.categories.length - data.current.expected).toFixed(1) : null);
  const scoreLabel = points ? (progress.started ? '' : 'projected points') : (progress.started ? 'categories ahead now' : 'categories expected');
  // The columns beside "Now" in the category grid.
  const columns = [best, second].filter(Boolean).map(c => ({ key: keyOf(c), item: c, side: sideOf(c), error: errorOf(c) }));
  const pending = (col) => col.error ? '-' : '...';

  // A picked position filter stays listed after a week switch, so it can be seen and cleared.
  const positions = useMemo(() => [...new Set([...candidates.flatMap(c => c.positions), ...(filter.pos ? [filter.pos] : [])])].sort(),
    [candidates, filter.pos]);
  const shown = candidates.filter(c => (!filter.games || c.games >= 4)
    && (!filter.cat || (c.chance_changes[filter.cat] || 0) >= 0.02)
    && (!filter.pos || c.positions.includes(filter.pos)));
  const matches = search ? (data?.free_agents || []).filter(p => p.toLowerCase().includes(search.toLowerCase())).slice(0, 6) : [];
  const droppable = data ? data.roster.filter(p => !data.undroppable.includes(p)) : [];

  // A searched free agent starts on the open spot when the roster has one, else the best pick's drop,
  // else your lowest-rated droppable player (the drop picker changes it). One already in the candidates
  // is just selected, with his own best drop (a second card under the same name would light up both).
  const chooseManual = (name) => {
    setSearch('');
    if (candidates.some(c => c.name === name)) { setSelected(name); return; }
    const open = rosterSize && data.roster.length < rosterSize;
    // A player outside current.players (a weekly lineup's bench, or no stats this week) ranks below every rated one.
    const score = Object.fromEntries(data.current.players.map(p => [p.name, p.score]));
    const weakest = [...droppable].sort((a, b) => (score[a] ?? -Infinity) - (score[b] ?? -Infinity))[0];
    setManual({ name, drop: open ? null : best?.drop || weakest || null, positions: [], games: 0, manual: true });
    setSelected(name);
  };

  const format = (key, value) => {
    const m = meta[key] || {};
    if (value == null) return '-';
    return m.percent ? value.toFixed(3) : (key === 'WIN%' || key === 'TECH') ? value.toFixed(2) : value.toFixed(value >= 100 ? 0 : 1);
  };
  // Daily Leaders' column order (PTS, REB, A-TO, STL, BLK, then the rest): the categories object arrives key-sorted.
  const cats = data ? orderColumns(data.categories).map(c => c.key) : [];
  const catLabel = (k) => meta[k]?.label || k;
  // Green on top, red at the bottom: by your chance as it stands now (Daily Leaders' order breaks ties).
  const sortedCats = [...cats].sort((x, y) => (data.current.categories[y].chance ?? -1) - (data.current.categories[x].chance ?? -1));
  // Inverse categories (turnovers, times blocked...): the server's chance already means "lower wins".
  const catTitle = (k) => `${meta[k]?.name || k}${meta[k]?.inverse ? ': lower wins' : ''}`;

  // Healthy players with a game each day, for you without the drop (the open days are where a pickup streams) and for them.
  const perDay = (players) => days.map(day => players.filter(p => !p.injured && (p.days || []).includes(day)).length);
  const mineByDay = days.map(day => data ? data.current.players.filter(p => !p.injured && (p.days || []).includes(day)
    && !(pick?.drop === p.name && (!pick.day || day >= pick.day))).length : 0);
  const isOpen = (n) => !!openSlots && n < openSlots;
  const past = (day) => !!progress.started && day < progress.today;   // already played: nothing left to fill

  const pickPlayers = pickSide?.players.find(p => p.name === pick?.name);
  const pickDays = (pickPlayers?.open_days || pick?.days || []).filter(d => !pick?.day || d >= pick.day);
  // his possible claim days: from the ranking, else from any preview of him (kept while a moved day loads)
  const dayOptions = pick?.day_options || Object.entries(previews).map(([k, v]) => k.startsWith(`${pick?.name}|`) && v?.day_options?.[pick.name]).find(Boolean) || [];
  const dayName = (d) => new Date(`${d}T12:00`).toLocaleDateString('en-US', { weekday: 'short' });

  return (
    <div className="bg-gray-800 rounded-lg shadow-xl p-3 sm:p-6">
      <div className="flex flex-wrap items-center gap-3 sm:gap-4 mb-4">
        <h2 className="text-2xl font-bold text-nba-orange mr-2 sm:mr-4">Lineup Optimizer</h2>
        <WeekSelect weeks={weeks} value={activeWeek} onChange={(week) => { weekChosen.current = true; setAutoNote(null); setWeekOverride(null); setView({ week }); }} />
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
      {data && autoNote && (activeWeek === autoNote.next || activeWeek === autoNote.current) && (
        <div className="mb-4 p-3 rounded bg-gray-700 border border-gray-600 text-sm text-gray-200 flex flex-wrap items-center justify-between gap-2">
          <span>{activeWeek === autoNote.next
            ? (autoNote.reason === 'last-day' ? 'Next week.' : 'No claims left this week, so this is next week.')
            : (autoNote.reason === 'last-day' ? "Last day of this week and you still have a claim: it can catch tonight's games."
              : 'This week: no claims left, so a pickup cannot change these chances.')}</span>
          <button onClick={() => setWeekOverride(activeWeek === autoNote.next ? autoNote.current : autoNote.next)} className="btn-secondary text-xs shrink-0">
            {activeWeek === autoNote.next ? (autoNote.reason === 'last-day' ? 'Back to this week' : "See this week's chances") : 'Next week'}
          </button>
        </div>
      )}
      {loading && !data && <div className="py-8 flex justify-center"><div className="animate-spin rounded-full h-8 w-8 border-b-2 border-nba-orange"></div></div>}

      {data && (
        <>
          {/* Scoreboard: you, the week's chance, the opponent; the facts in one line. Once games are played the
              sides show what each has so far (categories led now; points so far), the chance is of the whole week. */}
          <div className="bg-gray-700 rounded-lg border border-gray-600 p-3 sm:p-4 mb-4">
            <div className="grid grid-cols-[1fr_auto_1fr] items-center gap-2 sm:gap-4">
              <div className="min-w-0">
                <div className="text-sm font-semibold text-mine">You</div>
                <div className="text-2xl sm:text-3xl font-bold text-mine">{scoreMine != null ? scoreMine : '-'}</div>
                <div className="text-xs text-gray-400">{scoreLabel}</div>
                <TeamFacts claims={data.claims_left ?? claims} perWeek={claims} games={gamesFraction(data.current.players, data.current.games_played)} />
              </div>
              <div className="text-center">
                {baseChance != null ? (
                  <div className={`rounded-lg px-3 py-1.5 ${chipClass(baseChance)}`}>
                    <div className="text-xl sm:text-2xl font-bold leading-none">{pct(baseChance)}</div>
                    <div className="text-[11px]">to win the week</div>
                  </div>
                ) : <div className="text-xs text-gray-400 max-w-[8rem]">Opponent TBD: your projected week only</div>}
              </div>
              <div className="text-right min-w-0">
                <div className="text-sm font-semibold text-opp truncate" title={hasOpponent ? opponentLabel : undefined}>{hasOpponent ? opponentLabel : 'Opponent'}</div>
                {hasOpponent && <div className="text-2xl sm:text-3xl font-bold text-opp">{scoreTheirs != null ? scoreTheirs : '-'}</div>}
                <div className="text-xs text-gray-400">{hasOpponent ? scoreLabel : ''}</div>
                {data.opponent_players && <TeamFacts right claims={data.opponent_claims_left} perWeek={claims} games={gamesFraction(data.opponent_players, data.opponent_games_played)} />}
              </div>
            </div>
            {(progress.live > 0 || data.opponent === 'league average' || !data.scheduled_opponent || progress.partial || (progress.started && progress.canon !== null && progress.canon !== undefined)) && (
              <p className="text-xs text-gray-400 mt-2 pt-2 border-t border-gray-600 text-center">
                {progress.live > 0 && <span className="text-green-400">{progress.live} live</span>}
                {data.opponent === 'league average' && `${progress.live > 0 ? ' · ' : ''}vs the league average${data.scheduled_opponent ? ` (${data.scheduled_opponent} has no roster yet)` : ''}`}
                {!data.scheduled_opponent && `${progress.live > 0 ? ' · ' : ''}no opponent scheduled`}
                {progress.partial && <span className="text-amber-400" title="Some box scores could not be loaded; those games are still projected"> · partial</span>}
                {progress.started && progress.canon === true && (canonOff && !(progress.live > 0)
                  ? <span className="text-amber-400" title={`Our played totals differ from Fantrax's: ${canonOff}`}>{hasLead ? ' · ' : ''}differs from Fantrax</span>
                  : <span title="Games played so far are Fantrax's own lineups and stats for both teams (adds, drops and bench moves included); only the rest is projected">{hasLead ? ' · ' : ''}so far = Fantrax's lineups</span>)}
                {progress.started && progress.canon === false && <span className="text-amber-400" title="Fantrax's lineups weren't available (unreachable, or a team has no Fantrax id): those played days assume the best players started">{hasLead ? ' · ' : ''}lineups guessed</span>}
              </p>
            )}
          </div>

          {/* Categories and the comparison in one grid (owner, 2026-10-26): categories sorted by your chance (green at
              the top, red at the bottom) in a Now column, and the same rows for two picks with the chance after
              adding him and its change. Colour alone says who wins. Once games are played, the label shows each
              side's total so far. */}
          <div className="bg-gray-700 rounded-lg border border-gray-600 p-3 sm:p-4 mb-4">
            <div className="grid grid-cols-[4.5rem_repeat(3,minmax(0,1fr))] sm:grid-cols-[7rem_repeat(3,minmax(0,1fr))] gap-x-1.5 gap-y-1 items-center text-sm">
              <div></div>
              <div className="text-center text-xs text-gray-400 pb-1">Now</div>
              {[0, 1].map(i => {
                const col = columns[i];
                if (!col) return <div key={i}></div>;
                const on = selected === col.item.name;
                return (
                  <CardButton key={col.key} onClick={() => setSelected(col.item.name)} aria-pressed={on} title={`Add ${col.item.name}${col.item.drop ? `, drop ${col.item.drop}` : ''}`}
                    className={`min-w-0 text-center text-xs pb-1 border-b cursor-pointer ${on ? 'border-nba-orange' : 'border-gray-600'}`}>
                    <span className={`block break-words font-semibold ${on ? 'text-nba-orange' : 'text-gray-100'}`}>+ <PlayerName name={col.item.name} /></span>
                    {col.item.day && <span className="block text-[10px] text-gray-400">{col.item.day > (progress.today || data.week_start) ? `${dayName(col.item.day)} ${shortDate(col.item.day)}` : `before 7pm (${shortDate(col.item.day)})`}</span>}
                    <span className="block break-words text-[10px] text-red-400">{col.item.drop ? <>- <PlayerName name={col.item.drop} /></> : 'open spot'}</span>
                  </CardButton>
                );
              })}
              {columns.length < 2 && <div></div>}

              {!points && (
                <>
                  <div className="font-semibold text-gray-200">Week</div>
                  <div className="text-center"><Chip chance={baseChance} bold /></div>
                  {columns.map(col => <Cell key={col.key} chance={col.side && weekChance(col.side, points)} base={baseChance} fallback={pending(col)} bold />)}
                  {columns.length < 2 && <div></div>}
                </>
              )}
              {sortedCats.map(k => {
                const base = data.current.categories[k];
                const soFar = progress.started && base.now_mine != null && hasOpponent;
                return (
                  <React.Fragment key={k}>
                    <div className="min-w-0 border-t border-gray-600/40 pt-1" title={`${catTitle(k)}${hasOpponent ? `. Week: ${format(k, base.mine)} v ${format(k, base.theirs)}` : ''}`}>
                      <span className="font-semibold text-gray-100">{points ? 'Week' : catLabel(k)}</span>
                      {soFar && <span className="block text-[10px] text-gray-400 truncate tabular-nums">{format(k, base.now_mine)} v {format(k, base.now_theirs)}</span>}
                    </div>
                    <div className="text-center border-t border-gray-600/40 pt-1"><Chip chance={base.chance} fallback={format(k, base.mine)} /></div>
                    {columns.map(col => {
                      const row = col.side?.categories[k];
                      return <Cell key={col.key} chance={row?.chance} base={base.chance} fallback={row ? format(k, row.mine) : pending(col)} />;
                    })}
                    {columns.length < 2 && <div></div>}
                  </React.Fragment>
                );
              })}
            </div>
            {columns.map(col => col.error && <p key={col.key} className="text-xs text-red-300 mt-2">{col.item.name}: {col.error}</p>)}
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
                {!points && (
                  <select value={filter.cat} onChange={(e) => setFilter(f => ({ ...f, cat: e.target.value }))} aria-label="Helps category"
                    className="px-2 py-1 rounded-full text-xs bg-gray-700 border border-gray-500 text-gray-200">
                    <option value="">Helps any</option>
                    {cats.map(k => <option key={k} value={k}>Helps {catLabel(k)}</option>)}
                  </select>
                )}
              </div>
              <div className="relative mb-2">
                <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Any free agent..." aria-label="Try any free agent"
                  className="w-full px-2 py-1 bg-gray-600 text-white text-xs rounded border border-gray-500" />
                {matches.length > 0 && (
                  <div className="absolute z-10 left-0 right-0 mt-0.5 bg-gray-800 border border-gray-500 rounded shadow-xl">
                    {matches.map(p => (
                      <button key={p} type="button" onClick={() => chooseManual(p)} className="block w-full text-left px-2 py-1 text-xs text-white hover:bg-gray-600">{p}</button>
                    ))}
                  </div>
                )}
              </div>
              <div className="space-y-1.5 max-h-[34rem] overflow-y-auto">
                {manual && (
                  <CardButton onClick={() => setSelected(manual.name)} aria-pressed={selected === manual.name}
                    className={`w-full text-left rounded-lg border p-2 cursor-pointer ${selected === manual.name ? 'border-nba-orange bg-gray-600' : 'border-gray-600 bg-gray-800'}`}>
                    <span className="text-sm font-medium text-white"><PlayerName name={manual.name} /></span>
                    <span className="ml-2 text-xs text-gray-400">your search</span>
                  </CardButton>
                )}
                {shown.map(c => {
                  const index = candidates.indexOf(c);
                  const on = selected === c.name;
                  return (
                    <CardButton key={c.name} onClick={() => setSelected(c.name)} aria-pressed={on}
                      className={`w-full text-left rounded-lg border p-2 cursor-pointer ${on ? 'border-nba-orange bg-gray-600' : 'border-gray-600 bg-gray-800 hover:border-gray-500'}`}>
                      <div className="flex items-baseline justify-between gap-2">
                        <span className="text-sm font-medium text-white truncate"><span className="text-gray-500 mr-1.5">{index + 1}</span><PlayerName name={c.name} /></span>
                        <span className={`text-sm font-bold shrink-0 ${deltaClass(c.gain)}`}>{points ? `${pointsDelta(c.gain)}%` : signed(c.gain)}</span>
                      </div>
                      {/* Fixed columns so the day dots line up from card to card, right-aligned like a table column. */}
                      <div className="grid grid-cols-[7rem_3.5rem_1fr_max-content] items-center gap-x-2 mt-1 text-xs text-gray-400">
                        <span className="truncate">{c.team_abv} · {c.positions.join('/')}</span>
                        <span className="whitespace-nowrap">{plays(c.plays)}/{c.games} games</span>
                        <span className="truncate">
                          {c.day > (progress.today || data.week_start) && <span className="text-nba-orange" title="The best day to claim him: he replaces the drop from then">from {dayName(c.day)}</span>}
                          {c.small_sample && <span className="ml-2 text-amber-400" title="Small sample: his numbers come from only a few games">{c.gp} GP</span>}
                        </span>
                        <DayDots days={days} played={c.days} />
                      </div>
                    </CardButton>
                  );
                })}
                {!shown.length && !manual && <p className="text-xs text-gray-400 p-2">{candidates.length ? 'No candidate matches these filters.' : pickupsError || 'No pickup improves this week.'}</p>}
              </div>
              <p className="text-[11px] text-gray-500 mt-2">Ranked by {points ? 'the rise in your chance of winning the week' : 'extra categories you would expect to win'}, with the drop that suits each best.</p>
            </div>

            {/* The one being looked at */}
            <div className="space-y-4 min-w-0">
              {pick ? (
                <div className="bg-gray-700 rounded-lg border border-gray-600 p-3 sm:p-4">
                  <div className="flex flex-wrap items-baseline justify-between gap-2">
                    <h3 className="text-lg font-bold text-white"><PlayerName name={pick.name} />
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
                  {dayOptions.length > 1 && (
                    <label className="mt-2 text-xs text-gray-300 flex items-center gap-1.5">Claim on
                      <select value={pick.day || dayOptions[0]} onChange={(e) => setDayPick(m => ({ ...m, [pick.name]: e.target.value }))} className={selectClass}
                        aria-label="Claim day">
                        {dayOptions.map(d => <option key={d} value={d}>{dayName(d)} {shortDate(d)}{d === (progress.today || data.week_start) ? ' (now)' : ''}</option>)}
                      </select>
                      <span className="text-gray-500">he plays from then; {pick.drop ? `${pick.drop} plays until the day before` : 'no drop'}</span>
                    </label>
                  )}
                </div>
              ) : (
                !loading && <div className="bg-gray-700 rounded-lg border border-gray-600 p-4 text-sm text-gray-400">
                  {candidates.length ? 'Pick a free agent on the left.' : `${pickupsError ? `${pickupsError.replace(/\.?$/, '.')}` : 'No free agent improves this week.'} Search one on the left to try him.`}
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
                          <td className="py-1 text-gray-400 pr-2 whitespace-nowrap">Yours{pick.drop ? ` without ${pick.drop}` : ''}</td>
                          {mineByDay.map((n, i) => past(days[i]) ? <td key={days[i]} className="text-center text-gray-600">-</td> : (
                            <td key={days[i]} className={`text-center ${isOpen(n) ? 'text-amber-300' : 'text-gray-200'}`} title={isOpen(n) ? 'Open slot: a pickup who plays this day adds a game' : undefined}>{n}</td>
                          ))}
                        </tr>
                        <tr className="border-t border-gray-600/40">
                          <td className="py-1 text-white pr-2 whitespace-nowrap"><PlayerName name={pick.name} /></td>
                          {days.map((d, i) => {
                            if (past(d) || !pickDays.includes(d)) return <td key={d}></td>;
                            if (!openSlots) return <td key={d} className="text-center text-gray-200">plays</td>;
                            const open = isOpen(mineByDay[i]);
                            return <td key={d} className="text-center"><span className={open ? 'text-green-400 font-bold' : 'text-gray-400'}>{open ? 'fills' : 'full'}</span></td>;
                          })}
                        </tr>
                        {data.opponent_players && (
                          <tr className="border-t border-gray-600/40">
                            <td className="py-1 text-opp pr-2 whitespace-nowrap max-w-[8rem] truncate" title={opponentLabel}>{opponentLabel}</td>
                            {perDay(data.opponent_players).map((n, i) => past(days[i]) ? <td key={days[i]} className="text-center text-gray-600">-</td> : (
                              <td key={days[i]} className={`text-center ${isOpen(n) ? 'text-amber-300' : 'text-gray-200'}`}>{n}</td>
                            ))}
                          </tr>
                        )}
                      </tbody>
                    </table>
                  </div>
                  <p className="text-[11px] text-gray-500 mt-2">Healthy players with a game each day{openSlots ? `; amber is under your ${openSlots} active slots, so a pickup who plays that day fills one` : ''}.</p>
                </div>
              )}

              <details className="bg-gray-700 rounded-lg border border-gray-600 p-3 sm:p-4">
                <summary className="cursor-pointer text-sm font-semibold text-gray-200">Matchup and both rosters</summary>
                <div className="grid gap-4 sm:grid-cols-2 mt-3">
                  <RosterTable title={pickSide ? `Your roster with ${pick.name}` : 'Your roster'} players={(pickSide || data.current).players}
                    days={days} nameClass="text-mine" lit="bg-nba-orange" dropName={pickSide ? pick?.drop : null} addName={pickSide ? pick?.name : null} />
                  {data.opponent_players
                    ? <RosterTable title={opponentLabel} players={data.opponent_players} days={days} nameClass="text-opp" lit="bg-opp" />
                    : <p className="text-xs text-gray-400">{hasOpponent ? 'No roster for the opponent yet.' : 'No opponent set for this week.'}</p>}
                </div>
                {data.il?.length > 0 && <p className="text-xs text-gray-500 mt-3">Injured list (no spot, no games): {data.il.join(', ')}</p>}
                <p className="text-xs text-gray-500 mt-2">
                  {daily
                    ?'Daily lineups: each day your best players who play and fit the starting slots count.'
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
