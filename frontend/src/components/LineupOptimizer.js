import React, { useEffect, useState } from 'react';
import { analyze, errorMessage } from '../services/api';
import useLeagueViewState, { statOptions, validStat } from '../useLeagueViewState';
import { WeekSelect, defaultWeekStart, validWeek, selectClass, shortDate } from '../weeks';

const pct = (x) => `${Math.round(x * 100)}%`;
const chanceClass = (chance) => chance == null ? 'text-gray-200' : chance > 0.55 ? 'text-emerald-300' : chance < 0.45 ? 'text-red-300' : 'text-gray-200';

// One side of the week: my roster as it is, after the best pickups, or a what-if. Categories
// leagues show each category with my chance of winning it; points leagues the points and the chance
// of winning the week. With no opponent yet, my totals only.
const WeekCard = ({ title, side, meta, points, opponent, note }) => {
  if (!side) return null;
  const format = (key, value) => {
    const m = meta[key] || {};
    if (value == null) return '-';
    return m.percent ? value.toFixed(3) : (key === 'WIN%' || key === 'TECH') ? value.toFixed(2) : value.toFixed(1);
  };
  const fpts = side.categories.FPTS;
  return (
    <div className="bg-gray-700 rounded-lg border border-gray-600 p-4 flex-1 min-w-[280px]">
      <h3 className="text-sm font-semibold text-gray-300 mb-1">{title}</h3>
      {note}
      <div className="mb-3">
        {points && fpts ? (
          <p className="text-2xl font-bold text-white">
            {fpts.mine.toFixed(0)}
            {fpts.theirs != null && <span className="text-gray-400 text-lg"> vs {fpts.theirs.toFixed(0)}</span>}
            {fpts.chance != null && <span className={`ml-2 text-lg ${chanceClass(fpts.chance)}`}>{pct(fpts.chance)} to win</span>}
          </p>
        ) : side.expected != null ? (
          <p className="text-2xl font-bold text-white">{side.expected.toFixed(1)}<span className="text-gray-400 text-lg"> of {Object.keys(side.categories).length} categories expected</span></p>
        ) : (
          <p className="text-sm text-gray-400">Opponent TBD: your projected week only.</p>
        )}
      </div>
      {!points && (
        <table className="w-full text-sm mb-3">
          <thead>
            <tr className="text-xs text-gray-400">
              <th className="text-left font-normal">Category</th><th className="text-right font-normal">You</th>
              {opponent && <><th className="text-right font-normal">{opponent}</th><th className="text-right font-normal">Win</th></>}
            </tr>
          </thead>
          <tbody>
            {Object.entries(side.categories).map(([key, row]) => (
              <tr key={key} className="border-t border-gray-600/40">
                <td className="text-gray-400 py-0.5">{meta[key]?.label || key}</td>
                <td className={`text-right font-semibold ${chanceClass(row.chance)}`}>{format(key, row.mine)}</td>
                {opponent && <><td className="text-right text-gray-300">{format(key, row.theirs)}</td>
                  <td className={`text-right ${chanceClass(row.chance)}`}>{pct(row.chance)}</td></>}
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <div className="text-xs text-gray-400 space-y-0.5">
        {side.players.map(p => (
          <div key={p.name} className={`flex justify-between ${p.plays ? '' : 'opacity-50'}`}>
            <span className="text-gray-200">{p.name} <span className="text-gray-500">{p.positions.join('/')}</span>{p.injured && <span className="text-red-400"> INJ</span>}</span>
            <span title="Games he counts for / games his team plays">{p.plays}/{p.games}</span>
          </div>
        ))}
      </div>
    </div>
  );
};

// The week's matchup, the best pickups for the week's claims and a what-if, on one model
// (lineup_optimizer.py): expected categories won, or the chance of winning a points week.
const LineupOptimizer = ({ config, onEditLeague }) => {
  const league = config.league;
  const weeks = league?.weeks || [];
  const points = config.capabilities?.scoring === 'points';
  const meta = Object.fromEntries((config.categories || []).map(c => [c.key, c]));
  const [view, setView] = useLeagueViewState(league?.id, 'lineup', {
    week: defaultWeekStart(weeks), statType: config.default_stat_type || 'projected',
  }, (picked) => validWeek(weeks)(validStat(config)(picked)));
  const [data, setData] = useState(null);
  const [moves, setMoves] = useState(null);
  const [whatIf, setWhatIf] = useState(null);
  const [adds, setAdds] = useState([]);
  const [drops, setDrops] = useState([]);
  const [pickSearch, setPickSearch] = useState('');
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);
  const [reload, setReload] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    setData(null);
    setMoves(null);
    setWhatIf(null);
    analyze(view.week, view.statType)
      .then(result => {
        if (cancelled) return;
        setData(result);
        return analyze(view.week, view.statType, { moves: true }).then(m => { if (!cancelled) setMoves(m.moves); });
      })
      .catch(err => { if (!cancelled) setError(errorMessage(err)); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [view.week, view.statType, reload]);

  const runWhatIf = () => {
    analyze(view.week, view.statType, { adds, drops })
      .then(result => setWhatIf(result.what_if))
      .catch(err => setError(errorMessage(err)));
  };

  const opponent = data?.opponent === 'league average' ? 'League avg' : data?.opponent;
  const matches = pickSearch ? (data?.free_agents || []).filter(p => p.toLowerCase().includes(pickSearch.toLowerCase())).slice(0, 8) : [];
  const claims = data?.claims_per_week || config.capabilities?.claims_per_week || 1;

  return (
    <div className="bg-gray-800 rounded-lg shadow-xl p-6">
      <div className="flex flex-wrap items-center gap-4 mb-4">
        <h2 className="text-2xl font-bold text-nba-orange mr-4">Lineup Optimizer</h2>
        <WeekSelect weeks={weeks} value={view.week} onChange={(week) => setView({ week })} />
        <div className="flex items-center space-x-2">
          <span className="text-sm text-gray-300">Stats:</span>
          <select value={view.statType} onChange={(e) => setView({ statType: e.target.value })} className={selectClass}>
            {statOptions(config).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
          </select>
        </div>
        <button onClick={() => setReload(n => n + 1)} className="btn-secondary text-sm">Refresh</button>
      </div>

      {data && (
        <p className="text-sm text-gray-300 mb-4">
          {shortDate(data.week_start)} to {shortDate(data.week_end)} ({data.days} days) against{' '}
          <span className="text-white font-semibold">
            {data.opponent === 'league average' ? "the league's average team" : data.opponent || 'an opponent not set yet'}
          </span>
          {data.opponent === 'league average' && data.scheduled_opponent && ` (${data.scheduled_opponent} has no roster yet)`}
          {!data.scheduled_opponent && ' (no opponent in the schedule for this week)'}.
          {config.league?.settings?.roster?.daily_lineups
            ? ' Daily lineups: each day your best players who play and fit the starting slots count.'
            : ' Weekly lineup: your best starters who fit the slots play every game.'}
        </p>
      )}

      {error && (
        <div className="mb-4 p-3 rounded bg-red-900/40 border border-red-700 text-red-200 text-sm flex items-center justify-between">
          <span>{error}</span>
          {onEditLeague && <button onClick={onEditLeague} className="btn-secondary text-xs">League settings</button>}
        </div>
      )}
      {loading && !data && <div className="py-8 flex justify-center"><div className="animate-spin rounded-full h-8 w-8 border-b-2 border-nba-orange"></div></div>}

      {data && (
        <div className="flex flex-wrap gap-4">
          <WeekCard title="Your roster" side={data.current} meta={meta} points={points} opponent={opponent} />
          <WeekCard
            title={`Best pickups (${claims} claim${claims === 1 ? '' : 's'} a week)`}
            side={moves} meta={meta} points={points} opponent={opponent}
            note={moves ? (
              <div className="text-xs mb-2 space-y-0.5">
                {moves.steps.length === 0 && <p className="text-gray-400">No pickup improves this week.</p>}
                {moves.steps.map(s => (
                  <p key={s.add}><span className="text-green-400">+ {s.add}</span> <span className="text-red-400">- {s.drop || 'open spot'}</span>
                    <span className="text-gray-400"> ({s.gain > 0 ? '+' : ''}{s.gain.toFixed(2)})</span></p>
                ))}
              </div>
            ) : <p className="text-xs text-gray-400 mb-2">Searching free agents...</p>}
          />
          <div className="flex-1 min-w-[280px]">
            <div className="bg-gray-700 rounded-lg border border-gray-600 p-4 mb-2 text-sm">
              <h3 className="font-semibold text-gray-300 mb-2">What if</h3>
              <input value={pickSearch} onChange={(e) => setPickSearch(e.target.value)} placeholder="Add a free agent..."
                className="w-full px-2 py-1 bg-gray-600 text-white text-xs rounded border border-gray-500 mb-1" />
              {matches.map(p => (
                <div key={p} onClick={() => { setAdds(a => a.includes(p) ? a : [...a, p]); setPickSearch(''); }}
                  className="px-2 py-0.5 text-xs text-white hover:bg-gray-600 cursor-pointer">{p}</div>
              ))}
              <select value="" onChange={(e) => e.target.value && setDrops(d => [...d, e.target.value])}
                className="w-full px-2 py-1 bg-gray-600 text-white text-xs rounded border border-gray-500 mt-1">
                <option value="">Drop...</option>
                {data.roster.filter(p => !data.undroppable.includes(p) && !drops.includes(p)).map(p => <option key={p} value={p}>{p}</option>)}
              </select>
              <div className="text-xs mt-2 space-y-0.5">
                {adds.map(p => <p key={p} className="text-green-400 cursor-pointer" onClick={() => setAdds(a => a.filter(x => x !== p))}>+ {p} ×</p>)}
                {drops.map(p => <p key={p} className="text-red-400 cursor-pointer" onClick={() => setDrops(d => d.filter(x => x !== p))}>- {p} ×</p>)}
              </div>
              <button onClick={runWhatIf} disabled={!adds.length && !drops.length} className="btn-primary text-xs mt-2 disabled:opacity-50">Compare</button>
            </div>
            <WeekCard title="What-if roster" side={whatIf} meta={meta} points={points} opponent={opponent} />
          </div>
        </div>
      )}
    </div>
  );
};

export default LineupOptimizer;
