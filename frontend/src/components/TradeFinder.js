import React, { useEffect, useState } from 'react';
import { getTrades, errorMessage } from '../services/api';
import useLeagueViewState from '../useLeagueViewState';
import { shortDate } from '../weeks';
import { PlayerName } from './PlayerCard';

const signed = (x, digits = 0) => `${x > 0 ? '+' : ''}${x.toFixed(digits)}`;
const tone = (x) => (x > 0 ? 'text-green-300' : x < 0 ? 'text-red-300' : 'text-gray-400');

// Trade Finder (trade_finder.py via /api/trades): x-for-(x-1) trades. I send x players and get x-1 back, so a roster spot
// opens, and the week plan's ILP rents it to a streamer. Each row splits my gain into what the swap does to the lineup and
// what the freed spot earns, and shows what the partner gains (their lineup value after cutting the extra player).
const Chip = ({ children, cls = 'bg-gray-800 text-gray-300', title }) => (
  <span className={`rounded px-1.5 py-0.5 text-[11px] tabular-nums ${cls}`} title={title}>{children}</span>
);

const TradeRow = ({ t, weeksLeft }) => (
  <div className="rounded bg-gray-800/70 px-2 py-2 text-sm min-w-0">
    <div className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
      <span className="font-semibold text-nba-orange" title={t.partner_name}>{t.partner}</span>
      <span className="text-[11px] text-gray-500 truncate">{t.partner_name}</span>
      <span className={`ml-auto font-bold tabular-nums ${tone(t.me.week)}`} title="My expected FPTS per week, averaged over the next weeks">{signed(t.me.week)}/wk</span>
    </div>
    <div className="mt-1 flex flex-wrap items-center gap-x-1.5 gap-y-0.5 min-w-0">
      <span className="text-[11px] uppercase text-gray-500">give</span>
      {t.give.map((p, i) => <span key={p} className="text-gray-100">{i > 0 && '+ '}<PlayerName name={p} /></span>)}
      <span className="text-gray-500" aria-hidden="true">-&gt;</span>
      <span className="text-[11px] uppercase text-gray-500">get</span>
      {t.get.map((p, i) => <span key={p} className="font-semibold text-gray-100">{i > 0 && '+ '}<PlayerName name={p} /></span>)}
    </div>
    <div className="mt-1.5 flex flex-wrap items-center gap-1">
      <Chip cls={`bg-gray-900 ${tone(t.me.swap)}`} title="What the swap alone does to my lineup, with no claims">lineup {signed(t.me.swap)}</Chip>
      <Chip cls={`bg-sky-900/60 ${tone(t.me.slot)}`} title="What the freed roster spot earns once it is rented to streamers (the claims are worth more to a roster with an open spot)">freed spot {signed(t.me.slot)}</Chip>
      <Chip cls={`bg-gray-900 ${tone(t.market.they)}`} title={`What the room thinks the partner gains (0-100 scale, steep in rank): they get ${t.market.give.toFixed(0)}, give ${t.market.get.toFixed(0)}, less the player they cut`}>room: they {signed(t.market.they)} ({t.market.give.toFixed(0)} for {t.market.get.toFixed(0)})</Chip>
      <Chip cls={`bg-gray-900 ${tone(t.partner_week)}`} title="How their roster really improves if they never stream: more of their active slots are filled on days they have few players with a game. Their lineup FPTS per week, no claims.">their lineup {signed(t.partner_week)}/wk ({signed(t.partner_games, 1)} games played)</Chip>
      <Chip cls={`bg-gray-900 ${tone(t.partner_stream)}`} title="Their weekly FPTS if they use their claims the way you do: the roster spot you free is one they lose. Negative = a partner who streams should say no.">if they stream {signed(t.partner_stream)}</Chip>
      {t.partner_adds != null && <Chip title="Claims they used this week (last sync): 0 = not a streamer">{t.partner_adds} adds this week</Chip>}
      {t.cut.length > 0 && <Chip title="The partner has one player too many and has no free IL slot: they cut one">they cut {t.cut.join(', ')}</Chip>}
      <Chip title="My gain in each of the weeks that were averaged">{t.me.by_week.map(v => signed(v)).join(' / ')}</Chip>
      {weeksLeft > 0 && <Chip title="Per week x the weeks left in the schedule, if the free-agent market and the lineups hold">~{signed(t.me.season)} to the end</Chip>}
    </div>
    {t.streamers.length > 0 && (
      <div className="mt-1 text-[11px] text-gray-400">Spot rents: {t.streamers.map((p, i) => <span key={p}>{i > 0 && ', '}<PlayerName name={p} /></span>)}</div>
    )}
  </div>
);

const TradeFinder = ({ config }) => {
  const [view, setView] = useLeagueViewState(config?.league?.id, 'trades', { give: [], keep: [], x: 2, minMarket: 0, minLineup: 0, tau: 35 });
  const [roster, setRoster] = useState(null);
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    let cancelled = false;
    getTrades()
      .then(r => { if (!cancelled) setRoster(r.supported === false ? r : r.roster); })
      .catch(e => { if (!cancelled) setError(errorMessage(e)); });
    return () => { cancelled = true; };
  }, []);

  const names = Array.isArray(roster) ? roster.map(r => r.player) : [];
  const give = view.give.filter(p => names.includes(p));
  const keep = view.keep.filter(p => names.includes(p) && !give.includes(p));
  const pick = (kind, p) => setView(cur => {
    const g = cur.give.filter(q => q !== p);
    const k = cur.keep.filter(q => q !== p);
    if (kind === 'give' && !cur.give.includes(p)) g.push(p);
    if (kind === 'keep' && !cur.keep.includes(p)) k.push(p);
    return { give: g, keep: k };
  });

  const run = () => {
    setLoading(true); setError(null);
    getTrades({ give, keep, x: Math.max(view.x, give.length, 2), minMarket: view.minMarket, minLineup: view.minLineup, tau: view.tau })
      .then(setResult)
      .catch(e => { setResult(null); setError(errorMessage(e)); })
      .finally(() => setLoading(false));
  };

  if (roster && !Array.isArray(roster)) return <div className="text-sm text-gray-400">{roster.reason}</div>;
  const x = Math.max(view.x, give.length, 2);
  const trades = result?.trades || [];
  return (
    <div className="bg-gray-700 rounded-lg border border-gray-600 p-2 sm:p-3 min-w-0 max-w-4xl">
      <div className="text-sm font-semibold text-gray-100">Trade finder</div>
      <p className="text-xs text-gray-400 mt-1">
        Send {x} players, get {x - 1} back: the roster spot you free is rented to a streamer, which is worth more than the extra player you give up.
        My gain is expected FPTS per week from the week plan's model, averaged over the next three full weeks. The partner has to see a win by the room's values.
      </p>

      <div className="mt-2 text-[11px] uppercase text-gray-500">Your players: Trade = must be in the offer, Keep = not offered</div>
      <div className="mt-1 grid grid-cols-1 sm:grid-cols-2 gap-1">
        {(Array.isArray(roster) ? roster : []).map(r => (
          <div key={r.player} className="flex items-center gap-2 rounded bg-gray-800/60 px-2 py-1 text-xs min-w-0">
            <span className="min-w-0 flex-1 truncate text-gray-100"><PlayerName name={r.player} /></span>
            <span className="text-gray-500 tabular-nums" title="FPTS per game, games next week">{r.fpg.toFixed(1)} · {r.games}g</span>
            <button onClick={() => pick('give', r.player)} className={`px-1.5 py-0.5 rounded border ${give.includes(r.player) ? 'bg-nba-orange text-onaccent border-nba-orange' : 'border-gray-600 text-gray-400'}`}>Trade</button>
            <button onClick={() => pick('keep', r.player)} className={`px-1.5 py-0.5 rounded border ${keep.includes(r.player) ? 'bg-sky-900/70 text-sky-200 border-sky-700' : 'border-gray-600 text-gray-400'}`}>Keep</button>
          </div>
        ))}
        {!roster && !error && <div className="text-xs text-gray-400">Loading your roster...</div>}
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-2 text-xs text-gray-300">
        <span className="flex items-center gap-1">Players I send
          {[2, 3].map(n => (
            <button key={n} onClick={() => setView({ x: n })} className={`px-2 py-0.5 rounded border ${x === n ? 'border-nba-orange text-nba-orange' : 'border-gray-600 text-gray-400'}`}>{n} for {n - 1}</button>
          ))}
        </span>
        <label className="flex items-center gap-1" title="The partner only sees a win when what they get is worth more to the room than what they give. 0 = fair, higher = a sweeter offer. A rank-100 player is worth about 6, a top-5 player about 90.">
          Room value they gain at least
          <input type="number" min="0" step="5" value={view.minMarket} onChange={e => setView({ minMarket: Number(e.target.value) || 0 })}
            className="w-14 rounded bg-gray-800 border border-gray-600 px-1 py-0.5 text-gray-100" />
        </label>
        <label className="flex items-center gap-1" title="Their own lineup, with no claims, must gain at least this many FPTS a week: the trade has to make their roster better, not only look better.">
          Their lineup gains at least
          <input type="number" step="5" value={view.minLineup} onChange={e => setView({ minLineup: Number(e.target.value) || 0 })}
            className="w-14 rounded bg-gray-800 border border-gray-600 px-1 py-0.5 text-gray-100" />
        </label>
        <span className="flex items-center gap-1" title="How steeply managers price rank. Steep: stars are worth far more than two role players. Flat: closer to the FPTS lineup math (less realistic).">Stars worth
          {[['Steep', 20], ['Normal', 35], ['Flat', 60]].map(([label, v]) => (
            <button key={label} onClick={() => setView({ tau: v })} className={`px-2 py-0.5 rounded border ${view.tau === v ? 'border-nba-orange text-nba-orange' : 'border-gray-600 text-gray-400'}`}>{label}</button>
          ))}
        </span>
        <button onClick={run} disabled={!give.length || loading}
          className="ml-auto px-3 py-1 rounded bg-nba-orange text-onaccent font-semibold disabled:opacity-40">{loading ? 'Searching...' : 'Find trades'}</button>
      </div>

      {error && <div className="mt-2 text-xs text-red-300">Trade finder: {error}</div>}
      {result && result.supported === false && <div className="mt-2 text-xs text-gray-400">{result.reason}</div>}
      {result && result.supported && result.base && (
        <div className="mt-3">
          <div className="text-xs text-gray-400">
            {result.weeks.map(([a, b]) => `${shortDate(a)}-${shortDate(b)}`).join(', ')} · claims are worth {result.base.claims.toFixed(0)} FPTS/wk to your roster today ·
            {' '}{result.considered} combinations narrowed to {result.exact} exact · {result.seconds}s
          </div>
          <div className="mt-1.5 space-y-1.5">
            {trades.map((t, i) => <TradeRow key={i} t={t} weeksLeft={result.weeks_left} />)}
            {!trades.length && <div className="text-xs text-gray-400">No trade gives you a gain while the room sees the partner gaining {view.minMarket}. Lower that, or give a bigger piece.</div>}
          </div>
          <p className="text-[11px] text-gray-500 mt-2">
            A partner must pass two tests: the room's value of the players (Yahoo's pre-draft rank averaged with today's FPTS rank, steep in rank: nobody gives a top-5 player for two role players) and their own lineup getting better. A 2-for-1 improves a partner's lineup only by filling empty slots on light days; if they stream, the spot you free is a spot they lose (see "if they stream").
            Injured players (out today) are never targets and count zero for all three weeks. The freed spot assumes the streamers shown stay on the wire.
          </p>
        </div>
      )}
    </div>
  );
};

export default TradeFinder;
