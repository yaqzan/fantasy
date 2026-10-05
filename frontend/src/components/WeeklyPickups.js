import React, { useState, useEffect } from 'react';
import { getPickups, errorMessage } from '../services/api';
import useLeagueViewState, { statOptions, validStat } from '../useLeagueViewState';
import { WeekSelect, defaultWeekStart, validWeek, selectClass, shortDate, weekdayLetter, weekDays } from '../weeks';

const chanceColor = (chance) => {
  if (chance >= 0.75) return 'bg-green-800 text-green-100';
  if (chance >= 0.55) return 'bg-green-900 text-green-200';
  if (chance > 0.45) return 'bg-gray-700 text-gray-200';
  if (chance > 0.25) return 'bg-red-900 text-red-200';
  return 'bg-red-800 text-red-100';
};

// Free agents ranked by how many more categories they'd win you in a fantasy week (points leagues:
// how much they raise the chance of winning it), from the NBA schedule (who plays how often, and
// against whom for Wins), with the best drop for each.
const WeeklyPickups = ({ config }) => {
  const weeks = config?.league?.weeks || [];
  const caps = config?.capabilities || {};
  const points = caps.scoring === 'points';
  const waivers = config?.league?.settings?.waivers || {};
  const [{ week: weekStart, statType: timeframe }, setView] = useLeagueViewState(config?.league?.id, 'pickups', {
    week: defaultWeekStart(weeks), statType: config?.default_stat_type || 'projected',
  }, (picked) => validWeek(weeks)(validStat(config)(picked)));
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    getPickups(weekStart, timeframe)
      .then(result => { if (!cancelled) setData(result); })
      .catch(err => { if (!cancelled) { setData(null); setError(errorMessage(err)); } })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [weekStart, timeframe]);

  const categoryMeta = data?.categories || config?.categories || [];
  const label = Object.fromEntries(categoryMeta.map(c => [c.key, c.label]));
  const days = data ? weekDays(data.week_start, data.week_end) : [];
  const opponentText = data?.opponent === 'league average' ? "the league's average team"
    : data?.opponent ? data.opponent : 'a team exactly as strong as yours';

  return (
    <div className="py-2 sm:p-6">
      <div className="mb-4">
        <h2 className="text-2xl font-bold text-white mb-4">Weekly Pickups</h2>
        <div className="flex flex-col sm:flex-row gap-4 items-start sm:items-center">
          <WeekSelect weeks={weeks} value={weekStart || data?.week_start} onChange={(week) => setView({ week })} />
          <div className="flex items-center space-x-2">
            <span className="text-sm text-gray-300">Stats:</span>
            <select value={timeframe} onChange={(e) => setView({ statType: e.target.value })} className={selectClass}>
              {statOptions(config).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
            </select>
          </div>
        </div>
      </div>

      {error && <div className="mb-4 p-3 rounded bg-red-900/40 border border-red-700 text-red-200 text-sm">{error}</div>}

      {data && (
        <div className="mb-4 text-sm text-gray-300">
          <p className="mb-2">
            {shortDate(data.week_start)} to {shortDate(data.week_end)}, against {opponentText}:{' '}
            {points
              ? <>you have a <span className="font-semibold text-white">{Math.round(data.expected_categories * 100)}%</span> chance of winning the week.</>
              : <>you're projected to win <span className="font-semibold text-white">{data.expected_categories}</span> of {categoryMeta.length} categories.</>}
            {data.claims_per_week === 1 ? ' One claim a week, so pick one.' : ` ${data.claims_per_week} claims a week (the Lineup Optimizer finds the best set).`}
            {caps.faab && ` FAAB: $${waivers.faab_budget} for the season${waivers.faab_per_stage ? `, ${waivers.faab_per_stage} wins per stage` : ''} (spending isn't tracked here).`}
          </p>
          <div className="flex flex-wrap gap-1.5">
            {categoryMeta.map(c => {
              const row = data.my_week[c.key];
              return row ? (
                <span key={c.key} className={`px-2 py-0.5 rounded text-xs ${chanceColor(row.chance)}`} title={`Your chance of winning ${c.name} this week`}>
                  {c.label} {Math.round(row.chance * 100)}%
                </span>
              ) : null;
            })}
          </div>
        </div>
      )}

      {loading ? (
        <div className="flex justify-center items-center py-8">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-nba-orange"></div>
        </div>
      ) : data && (
        <div className="overflow-x-auto bg-gray-800 rounded-lg shadow-xl">
          <table className="min-w-full">
            <thead>
              <tr>
                <th className="table-header text-left">Player</th>
                <th className="table-header text-center" title="Overall score, 50 = average drafted player">OVR</th>
                <th className="table-header text-center" title="Days his NBA team plays this week">Games</th>
                <th className="table-header text-center" title="Games he'd actually play in your lineup">Plays</th>
                <th className="table-header text-center" title="Expected wins from his games (Wins category)">W</th>
                <th className="table-header text-center" title={points ? 'How much he raises your chance of winning the week' : "Extra categories you'd expect to win this week"}>Gain</th>
                <th className="table-header text-left">Drop</th>
                <th className="table-header text-left" title="Biggest changes in your chance of winning a category">Moves</th>
              </tr>
            </thead>
            <tbody className="bg-gray-800 divide-y divide-gray-700">
              {data.candidates.map(p => {
                const moves = Object.entries(p.chance_changes)
                  .filter(([, v]) => Math.abs(v) >= 0.01)
                  .sort((a, b) => Math.abs(b[1]) - Math.abs(a[1]))
                  .slice(0, 4);
                return (
                  <tr key={p.name} className="hover:bg-gray-700 transition-colors">
                    <td className="table-cell">
                      <div className="font-medium text-white">{p.name}</div>
                      <div className="text-xs text-gray-400">
                        {p.team_abv} · {p.positions.join('/')}
                        {p.small_sample && (
                          <span className="ml-1 text-amber-400" title="Small sample: his numbers come from only a few games">· {p.gp} GP</span>
                        )}
                      </div>
                    </td>
                    <td className="table-cell text-center text-white">{Math.round(p.score)}</td>
                    <td className="table-cell">
                      <div className="flex justify-center gap-0.5">
                        {days.map(day => (
                          <span
                            key={day}
                            title={shortDate(day)}
                            className={`w-5 text-center text-[10px] rounded ${p.days.includes(day) ? 'bg-nba-orange text-onaccent' : 'bg-gray-700 text-gray-500'}`}
                          >
                            {weekdayLetter(day)}
                          </span>
                        ))}
                      </div>
                    </td>
                    <td className="table-cell text-center text-white">{p.plays}/{p.games}</td>
                    <td className="table-cell text-center text-gray-200">{p.expected_wins.toFixed(1)}</td>
                    <td className={`table-cell text-center font-semibold ${p.gain > 0 ? 'text-green-400' : 'text-gray-400'}`}>
                      {points ? `${p.gain > 0 ? '+' : ''}${Math.round(p.gain * 100)}%` : `${p.gain > 0 ? '+' : ''}${p.gain.toFixed(2)}`}
                    </td>
                    <td className="table-cell text-gray-300">{p.drop || 'open spot'}</td>
                    <td className="table-cell">
                      <div className="flex flex-wrap gap-1">
                        {moves.map(([cat, v]) => (
                          <span key={cat} className={`px-1.5 py-0.5 rounded text-[11px] ${v > 0 ? 'bg-green-900 text-green-200' : 'bg-red-900 text-red-200'}`}>
                            {label[cat] || cat} {v > 0 ? '+' : ''}{Math.round(v * 100)}%
                          </span>
                        ))}
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {data && (
        <p className="mt-3 text-xs text-gray-500">
          Gain is how much {points ? 'your chance of winning the week rises' : "more categories you'd expect to win this week"} with him in your lineup and the drop shown out.
          Only his team's games count, and in daily-lineup leagues only days he'd make your lineup ({config?.league?.settings?.roster?.active} starters{caps.positions?.length ? ' who fit the slots' : ''}).
          
          Opponents come from the league schedule; until a week's opponent and roster are in, pickups are judged against {opponentText}.
          Tried the {data.tried} best free agents with games this week.
        </p>
      )}
    </div>
  );
};

export default WeeklyPickups;
