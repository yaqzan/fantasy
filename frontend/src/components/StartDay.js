import React, { useEffect, useState } from 'react';
import { getStartDay, errorMessage } from '../services/api';
import { shortDate, weekdayLetter } from '../weeks';
import { PlayerName } from './PlayerCard';

const pct = (x) => `${Math.round(x * 100)}%`;
const signedPct = (x) => `${x > 0 ? '+' : ''}${(x * 100).toFixed(1)}%`;

// Start tab (start_day.py via /api/start-day): on a day with more healthy players than active slots, which ones the
// week's matchup says to start. Must-starts, then the players who compete for the open spots, then the bench.
const PlayerRow = ({ p, labels, pick }) => (
  <div className={`flex flex-wrap items-center gap-x-2 gap-y-0.5 rounded px-2 py-1.5 text-sm ${pick ? 'bg-gray-800 border border-nba-orange' : 'bg-gray-800/60'}`}>
    <span className="font-semibold text-gray-100 min-w-0"><PlayerName name={p.name} /></span>
    <span className="text-[11px] text-gray-500">{p.team}</span>
    {p.play_chance != null && <span className="text-[11px] rounded px-1 bg-amber-900/60 text-amber-300">{pct(p.play_chance)} to play</span>}
    {pick && <span className="text-[11px] rounded px-1 bg-nba-orange text-onaccent font-semibold">model pick</span>}
    <span className="ml-auto text-xs text-gray-400 tabular-nums text-right">
      {p.role === 'must'
        ? `-${p.bench_cost.toFixed(2)} cats if benched`
        : p.loss === 0 ? `-${p.bench_cost.toFixed(2)} if benched` : `-${p.loss.toFixed(2)} cats${p.win_delta ? `, ${signedPct(p.win_delta)} win` : ''}`}
    </span>
    {p.helps.length > 0 && (
      <span className="basis-full text-[11px] text-gray-400">
        Helps {p.helps.map(h => labels[h.category] || h.category).join(', ')}
      </span>
    )}
  </div>
);

const StartDay = ({ config, status }) => {
  const days = status?.conflict_days || [];
  const [day, setDay] = useState(null);
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    setData(null); setError(null);
    let cancelled = false;
    getStartDay(day)
      .then(r => { if (!cancelled) setData(r); })
      .catch(e => { if (!cancelled) setError(errorMessage(e)); });
    return () => { cancelled = true; };
  }, [day]);

  const labels = data?.category_labels || {};
  const musts = data?.players?.filter(p => p.role === 'must') || [];
  const options = data?.players?.filter(p => p.role === 'toss-up') || [];
  const bench = data?.players?.filter(p => p.role === 'bench') || [];
  const slots = data?.slots ?? config?.league?.settings?.roster?.active;

  return (
    <div className="bg-gray-700 rounded-lg border border-gray-600 p-2 sm:p-3 min-w-0 max-w-3xl">
      <div className="flex flex-wrap items-center gap-2 text-sm">
        <span className="font-semibold text-gray-100">Who to start</span>
        {days.length > 1 && days.map(d => (
          <button key={d} onClick={() => setDay(d)}
            className={`px-2 py-0.5 rounded text-xs border ${(data?.day || days[0]) === d ? 'border-nba-orange text-nba-orange' : 'border-gray-600 text-gray-400'}`}>
            {weekdayLetter(d)} {shortDate(d)}
          </button>
        ))}
        {data?.day && days.length <= 1 && <span className="text-xs text-gray-400">{shortDate(data.day)}</span>}
      </div>
      {!data && !error && <div className="text-xs text-gray-400 mt-2">Trying every lineup...</div>}
      {error && <div className="text-xs text-red-300 mt-2">{error}</div>}
      {data?.error && <div className="text-xs text-red-300 mt-2">{data.error}</div>}
      {data && !data.conflict && <div className="text-xs text-gray-300 mt-2">No conflict: {data.candidates} can start for {slots} spots, so everyone does.</div>}
      {data?.too_many && <div className="text-xs text-gray-300 mt-2">Too many lineups to try ({data.candidates} players for {data.slots - data.locked.length} spots).</div>}
      {data?.best && (
        <>
          <div className="mt-2 text-xs text-gray-300">
            Start {data.open_slots} of {data.candidates} vs {data.opponent}. The right group is <span className="font-bold text-green-300 tabular-nums">{pct(data.best.win)}</span> to
            win the week ({data.best.expected} categories); the worst is <span className="font-bold text-red-300 tabular-nums">{pct(data.worst.win)}</span> ({data.worst.expected}).
          </div>
          {data.locked.length > 0 && <div className="mt-1 text-[11px] text-gray-400">Already in a game: {data.locked.join(', ')}.</div>}
          {musts.length > 0 && <div className="mt-3 text-[11px] uppercase tracking-wide text-gray-400">Must start</div>}
          <div className="space-y-1 mt-1">{musts.map(p => <PlayerRow key={p.name} p={p} labels={labels} />)}</div>
          {options.length > 0 && (
            <>
              <div className="mt-3 text-[11px] uppercase tracking-wide text-gray-400">
                {data.open_for_options} {data.open_for_options === 1 ? 'spot' : 'spots'} for these, best first
              </div>
              <div className="space-y-1 mt-1">{options.map(p => <PlayerRow key={p.name} p={p} labels={labels} pick={p.in_best} />)}</div>
            </>
          )}
          {bench.length > 0 && (
            <>
              <div className="mt-3 text-[11px] uppercase tracking-wide text-gray-400">Bench</div>
              <div className="space-y-1 mt-1">{bench.map(p => <PlayerRow key={p.name} p={p} labels={labels} />)}</div>
            </>
          )}
        </>
      )}
    </div>
  );
};

export default StartDay;
