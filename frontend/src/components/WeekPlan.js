import React, { useEffect, useState } from 'react';
import { getPlan, getLastDays, errorMessage } from '../services/api';
import { weekdayLetter, shortDate } from '../weeks';
import { PlayerName } from './PlayerCard';

const pct = (x) => `${Math.round(x * 100)}%`;
const chanceClass = (x) => x >= 0.55 ? 'bg-green-900/70 text-green-300' : x <= 0.45 ? 'bg-red-900/70 text-red-300' : 'bg-gray-600 text-gray-300';
// A win chance, or now -> after with the gain in points of chance.
const WinChance = ({ now, after }) => (
  <span className="flex items-center gap-1">
    <span className={`rounded px-1 py-0.5 font-semibold ${chanceClass(now)}`}>{pct(now)}</span>
    {after !== undefined && (
      <>
        <span aria-hidden="true">-&gt;</span>
        <span className={`rounded px-1 py-0.5 font-bold ${chanceClass(after)}`}>{pct(after)}</span>
        <span className={after >= now ? 'text-green-300' : 'text-red-300'}>{after >= now ? '+' : ''}{((after - now) * 100).toFixed(1)}</span>
      </>
    )}
  </span>
);

const TX = {
  add: { label: '+', cls: 'bg-green-900/70 text-green-300' },
  drop: { label: '-', cls: 'bg-red-900/70 text-red-300' },
  il_in: { label: 'IL-in', cls: 'bg-gray-600 text-gray-200' },
  il_out: { label: 'IL-out', cls: 'bg-gray-600 text-gray-200' },
};

// The week plan (claim_planner.py via /api/plan): every add, drop and IL move left this week. Rolling: only today's
// moves are firm, the rest is re-made each morning. Loads on its own after the page (`ready`), so it never delays
// it, and hides itself where the planner does not apply (supported: false).
const WeekPlan = ({ week, statType, ready, title = 'Week plan', withClaims = true, afterPrevious = false }) => {
  const [plan, setPlan] = useState(null);
  const [pre, setPre] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    setPlan(null); setPre(null); setError(null);
    if (!ready) return undefined;
    let cancelled = false;
    setLoading(true);
    getPlan(week, statType, afterPrevious)
      .then(result => { if (!cancelled) setPlan(result); })
      .catch(err => { if (!cancelled) setError(errorMessage(err)); })
      .finally(() => { if (!cancelled) setLoading(false); });
    // Two-week claims (last_days.py): always for the calendar's current week + the next; a failure just hides the section.
    if (withClaims) getLastDays(statType).then(result => { if (!cancelled) setPre(result); }).catch(() => {});
    return () => { cancelled = true; };
  }, [week, statType, ready, withClaims, afterPrevious]);

  if (plan && !plan.supported) return null;
  if (!plan && !loading && !error) return null;
  return (
    <div className="bg-gray-700 rounded-lg border border-gray-600 p-2 sm:p-3 mb-4 min-w-0">
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-sm">
        <span className="font-semibold text-gray-100">{title}{plan && plan.opponent ? <span className="font-normal text-gray-400"> {shortDate(plan.week_start)}-{shortDate(plan.week_end)} v {plan.opponent}</span> : null}</span>
        {plan && (
          <span className="flex items-center gap-1 text-xs text-gray-300">
            Win chance now <span className={`rounded px-1 py-0.5 font-semibold tabular-nums ${chanceClass(plan.now.win_chance)}`}>{pct(plan.now.win_chance)}</span>
            <span aria-hidden="true">-&gt;</span> plan <span className={`rounded px-1 py-0.5 font-bold tabular-nums ${chanceClass(plan.plan.win_chance)}`}>{pct(plan.plan.win_chance)}</span>
            <span className={plan.plan.win_chance >= plan.now.win_chance ? 'text-green-300' : 'text-red-300'}>{plan.plan.win_chance >= plan.now.win_chance ? '+' : ''}{((plan.plan.win_chance - plan.now.win_chance) * 100).toFixed(1)}</span>
            <span className="text-gray-400 tabular-nums" title="Expected points: now, with the plan (opponent's week)">{plan.now.points.toFixed(0)} -&gt; {plan.plan.points.toFixed(0)} v {plan.opponent_points.toFixed(0)}</span>
          </span>
        )}
        {plan && <span className="text-xs text-gray-400">{plan.claims_left}/{plan.claims_per_week} claims</span>}
      </div>
      {plan && plan.continues_from && <div className="text-xs text-gray-400 mt-1">Starts from the roster the plan above ends with.</div>}
      {loading && !plan && <div className="text-xs text-gray-400 mt-2">Planning the week...</div>}
      {error && <div className="text-xs text-red-300 mt-2">Week plan: {error}</div>}
      {plan && (
        <>
          <div className="mt-2 space-y-1">
            {plan.days.map(day => (
              <div key={day.date} className={`flex items-start gap-2 rounded px-1.5 py-1 text-xs ${day.today ? 'bg-gray-800 border border-nba-orange' : ''}`}>
                <span className="w-7 shrink-0 font-semibold text-gray-200 pt-0.5" title={shortDate(day.date)}>{weekdayLetter(day.date)}</span>
                <div className="flex flex-wrap gap-1 min-w-0 flex-1">
                  {day.today && <span className="rounded px-1.5 py-0.5 bg-nba-orange text-onaccent font-semibold">Do today</span>}
                  {day.frozen && <span className="text-amber-300 py-0.5" title="Frozen: a healthy player is in IL, so no lineup changes or adds">🔒</span>}
                  {day.transactions.map((tx, i) => (
                    <span key={i} className={`rounded px-1.5 py-0.5 break-words min-w-0 ${TX[tx.type].cls}`} title={tx.note}>
                      {TX[tx.type].label} <PlayerName name={tx.player} />
                    </span>
                  ))}
                  {!day.transactions.length && !day.frozen && !day.today && <span className="text-gray-500 py-0.5">-</span>}
                  {day.today && !day.transactions.length && <span className="text-gray-400 py-0.5">nothing today</span>}
                </div>
              </div>
            ))}
          </div>
          {pre && pre.active && (
            <div className="mt-2 rounded border border-gray-600 bg-gray-800 px-2 py-1.5 text-xs" title={pre.notes.join(' ')}>
              <div className="font-semibold text-gray-100">Claims for this week + next</div>
              <div className="mt-1 grid grid-cols-[auto_1fr_1fr] gap-x-2 gap-y-1 items-center text-gray-300 tabular-nums">
                <span />
                <span className="text-gray-400" title={`${shortDate(pre.this_week.start)}-${shortDate(pre.this_week.end)}`}>This week{pre.this_week.opponent ? ` v ${pre.this_week.opponent}` : ''}</span>
                <span className="text-gray-400" title={`${shortDate(pre.next_week.start)}-${shortDate(pre.next_week.end)}`}>Next week{pre.next_week.opponent ? ` v ${pre.next_week.opponent}` : ''}</span>
                <span className="text-gray-400">Now</span>
                <WinChance now={pre.this_week.now} />
                <WinChance now={pre.next_week.now} />
                {pre.claims.map((c, i) => (
                  <React.Fragment key={i}>
                    <span className="rounded px-1.5 py-0.5 bg-gray-700 text-gray-200 break-words min-w-0">
                      <span className="text-green-300">+</span> <PlayerName name={c.add} /> <span className="text-red-300">-</span> {c.drop ? <PlayerName name={c.drop} /> : 'open spot'}
                    </span>
                    <WinChance now={c.cur_before} after={c.cur_after} />
                    <WinChance now={c.next_before} after={c.next_after} />
                  </React.Fragment>
                ))}
                {pre.claims.length > 0 && (
                  <>
                    <span className="text-gray-400">All claims</span>
                    <WinChance now={pre.this_week.now} after={pre.this_week.after} />
                    <WinChance now={pre.next_week.now} after={pre.next_week.after} />
                  </>
                )}
              </div>
              {!pre.claims.length && <div className="mt-1 text-gray-400">No claim today helps either week.</div>}
              <div className="mt-1 text-gray-400">Ranked on both weeks (next week counts {pre.next_weight} x). The plan above weighs this week plus a rough 2-week keep value, so the two can differ.</div>
            </div>
          )}
          {plan.warnings.map((w, i) => <p key={i} className="text-xs text-amber-300 mt-1.5">{w}</p>)}
        </>
      )}
    </div>
  );
};

export default WeekPlan;
