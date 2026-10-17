import React, { useEffect, useMemo, useState } from 'react';
import { getDraftDay, errorMessage } from '../services/api';
import { roomPrice } from '../auction';

// Categorical slots 1-3 (dataviz reference palette, dark steps; validated on gray-800 #1f2937:
// all-pairs CVD dE 9.4, normal-vision 20.9, >= 3:1 contrast).
const C1 = '#3987e5';
const C2 = '#d95926';
const C3 = '#199e70';

const money = (v) => `$${v}`;

function Section({ title, subtitle, children }) {
  return (
    <section className="bg-gray-800 rounded-lg shadow-xl p-4 sm:p-5 mb-4 sm:mb-6">
      <h2 className="text-lg font-semibold text-white">{title}</h2>
      {subtitle && <p className="text-sm text-gray-400 mt-1 mb-4">{subtitle}</p>}
      {!subtitle && <div className="mb-4" />}
      {children}
    </section>
  );
}

function Legend({ series }) {
  return (
    <div className="flex flex-wrap gap-4 mb-3 text-xs text-gray-300">
      {series.map(s => (
        <span key={s.key} className="flex items-center gap-1.5">
          <span className="inline-block w-3 h-3 rounded-sm" style={{ background: s.color }} />
          {s.label}
        </span>
      ))}
    </div>
  );
}

// Horizontal grouped bars on one axis, with a dashed reference line (e.g. break-even 1.0).
function GroupedBars({ rows, series, max, reference, referenceLabel, format, min = 0 }) {
  const [hover, setHover] = useState(null);
  const pct = (v) => `${Math.max(0, ((v - min) / (max - min)) * 100)}%`;
  return (
    <div>
      {series.length > 1 && <Legend series={series} />}
      <div className="space-y-3">
        {rows.map(row => (
          <div key={row.label} className="grid grid-cols-[7.5rem_1fr] gap-3 items-center">
            <div className="text-sm text-gray-300 text-right">{row.label}</div>
            <div className="relative">
              {reference != null && (
                <div className="absolute top-0 bottom-0 border-l-2 border-dashed border-gray-400 z-10"
                     style={{ left: pct(reference) }} title={referenceLabel} />
              )}
              <div className="flex flex-col gap-[2px]">
                {series.map(s => {
                  const v = row[s.key];
                  if (v == null) return <div key={s.key} className="h-4" />;
                  const id = `${row.label}|${s.key}`;
                  return (
                    <div key={s.key} className="flex items-center gap-2 h-4"
                         onMouseEnter={() => setHover(id)} onMouseLeave={() => setHover(null)}>
                      <div className="h-3 rounded-r transition-opacity"
                           style={{ width: pct(v), background: s.color, opacity: hover && hover !== id ? 0.45 : 1 }} />
                      <span className="text-xs text-gray-300 tabular-nums whitespace-nowrap">
                        {format(v)}{hover === id ? ` · ${s.label}` : ''}
                      </span>
                    </div>
                  );
                })}
              </div>
            </div>
          </div>
        ))}
      </div>
      {referenceLabel && (
        <p className="text-xs text-gray-500 mt-3 ml-[8.25rem]">Dashed line: {referenceLabel}</p>
      )}
    </div>
  );
}

// Draft night by phase (share of the league's roster spots filled; `spots` in draft_day.json, WSOP's file has none: 160).
// Sources: .claude/docs/draft-strategy.md "Live auction" (dynamics.py, auction_sim.py, stress.py, mixed*.py, gradient*.py,
// focus.py, my_draft.py), 2026-10-03.
const PHASES = [
  {
    from: 0, to: 20, share: 'first 20%', aim: '85-86%',
    room: 'Overspends: 1.1-1.4x likely prices. Mid-tier players nominated now went for 1.7x and returned 0.93 per $1.',
    do: [
      'Nominate players the room overpays for (list below), so other teams spend on them.',
      'Buy only players valued at or above your spot bar ($25 at the start).',
      'Skip players with a likely price of $5-25 (red "early" tag). They come back cheaper.',
      'Stars only at or under their max. The room is likely to pay more: let them go.',
    ],
  },
  {
    from: 20, to: 50, share: '20-50%', aim: '86-91%',
    room: 'Still spending. The last $40-74 players sell here, and the ones bought at 20-35% returned 1.20 per $1.',
    do: [
      'This is where your first good buys usually land: the room has cooled, you still have money.',
      'Watch Pace: never get 3+ spots ahead of the room (the 2025 mistake: full at 55% of the draft).',
      'Never two $60+ players.',
    ],
  },
  {
    from: 50, to: 80, share: '50-80%', aim: '91-100%',
    room: 'Money runs low. Prices fall below likely, and most teams can no longer bid big.',
    do: [
      "Being well behind the room with money left is normal. It is the plan working. Don't chase: every catch-up rule tested lost.",
      'Your limit climbs to the full max by 80%. Keep nominating the best players left that you want.',
    ],
  },
  {
    from: 80, to: 100, share: 'last 20%', aim: 'full max',
    room: 'Broke. Late $1-2 players went cheap because nobody had money (second-highest team cap: $2), not because nobody wanted them. They returned 2x their price.',
    do: [
      'The spot bar lifts: fill every open spot.',
      'One dollar over "Others\' top bid" wins anyone. Take the best players left first, then the bench targets.',
      'Leftover money is fine. Overpaying is not.',
    ],
  },
];

const AIM_CURVE = [[0, 85], [20, 86], [40, 89], [50, 91], [60, 93], [70, 96], [80, 100]];

const BOARD = [
  ['Aim (green)', 'Your limit right now: a share of the max that rises with the draft (strip: "Aim 89% of max").'],
  ['Max (amber)', 'Never past it. Fixed for the whole draft: it does not shrink when the room overspends.'],
  ['Value (white)', "The app's $. Not a bid limit."],
  ['Room price (small number)', 'The likely price, scaled as the room spends, and marked up early (x1.6 on $5-25 players until 20% of the draft, x1.1 on $26+). Green: at or under your aim. Grey: up to your max. Red: past it. A forecast only: still bid to your aim.'],
  ['Pace', "Your spots filled vs the room's average. Red at 3+ ahead: stop buying. Amber \"don't chase\" when 3+ behind past half-way."],
  ['Spot bar', '1.25x your money per open spot. Dimmed rows ("not a spot yet") are valued under it. Lifts at 80%.'],
  ["Others' top bid", 'The most any other team can bid now. Late in the draft, $1 over it wins anyone.'],
  ['"early: room pays 1.7x"', 'Likely $5-25 player in the first 20% of the draft. Let him go.'],
  ['Amber dots', 'Strength in {unpriced}: cheap and still worth winning. Use to break ties, not to raise a bid.'],
  ['Sorts', "\"best buys\": max far above the room's price. \"nominate\": room's price far above your max (put them up)."],
];

const TESTED = [
  ['Fixed max, rising aim, spot bar, pace guard (tonight)', 'best in all 6 simulated rooms', true],
  ["Max that shrinks with the room's spending (old board)", '-0.3 to -1.4 a week, $64-126 unspent', false],
  ['Bid to max from pick 1', '-0.24', false],
  ['Catch up when behind or cash-rich', '-0.02 to -0.45', false],
  ['U-shaped curve, deeper cut on $40-74', '-0.09 to +0.02', false],
  ['Bid only on a target list', '-0.35 to -1.39, $79-172 unspent', false],
  ['Category weights in the max', '-0.08 to +0.03', false],
];

// Room prices at the start of the draft, with the early markup (auction.js): what the nominate and star lists compare.
const opening = (likely) => roomPrice(likely, 1, 0);

// Pick range of a phase, e.g. "Picks 1-28" for the first 20% of 140 spots.
const picks = (ph, spots) => `Picks ${Math.floor(spots * ph.from / 100) + 1}-${Math.floor(spots * ph.to / 100)}`;

// Page texts that differ by league come from draft_day.json; WSOP's file predates them, hence the fallbacks.
const WSOP_HEADER = 'WSOP auction · {draft} · 16 teams · $200 · 10 spots, 6 active daily · no injury slot';
const WSOP_TIERS = [
  { key: 'orig', label: "2025, that league's categories" },
  { key: 'w25', label: '2025, our 11 categories' },
  { key: 'w24', label: '2024, our 11 categories' },
];
const STAR_NOTE = 'Max = where a roster built around him ties the best roster without a star (weekly simulation, 8 runs). Good to about ±$10.';

// A snake draft's plan (draft_day_<league>.json type 'snake', .horizon/courtside-2026/plan.py): the rule from the
// simulated drafts, then who the room lets slide and who it reaches for.
function PlayerList({ rows, good }) {
  return (
    <div className="overflow-x-auto">
      <table className="min-w-full text-sm tabular-nums">
        <thead>
          <tr className="text-xs uppercase tracking-wider text-gray-400">
            <th className="text-left font-semibold py-1 pr-3">Player</th>
            <th className="text-right font-semibold py-1 px-2" title="Season value rank: FPTS over a streamer across his projected games">Ours</th>
            <th className="text-right font-semibold py-1 px-2" title="Yahoo's average draft position (Yahoo's rank when it has none)">ADP</th>
            <th className="text-right font-semibold py-1 px-2">FPTS/g</th>
            <th className="text-right font-semibold py-1 px-2">GP</th>
            <th className="text-right font-semibold py-1 pl-2">{good ? 'Room waits' : 'Room early by'}</th>
          </tr>
        </thead>
        <tbody>
          {rows.map(r => (
            <tr key={r.name} className="border-t border-gray-700/60">
              <td className="py-1 pr-3 text-gray-100 whitespace-nowrap">{r.name} <span className="text-xs text-gray-500">{r.team}</span>
                {r.injured && <span className="ml-1.5 text-[11px] text-amber-300">out till {r.injured}</span>}</td>
              <td className="text-right px-2 text-white font-semibold">{r.rank}</td>
              <td className="text-right px-2 text-gray-300">{r.adp != null ? r.adp.toFixed(1) : r.yrank != null ? `#${r.yrank}` : '-'}</td>
              <td className="text-right px-2 text-gray-300">{r.fpg}</td>
              <td className={`text-right px-2 ${r.gp < 60 ? 'text-amber-400' : 'text-gray-300'}`}>{r.gp}</td>
              <td className={`text-right pl-2 font-semibold ${good ? 'text-emerald-300' : 'text-rose-300'}`}>{Math.abs(r.gap)} picks</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function SnakeDraftDay({ data }) {
  const sim = data.sim || {};
  return (
    <div className="max-w-5xl">
      <div className="bg-gray-800 rounded-lg shadow-xl p-4 sm:p-6 mb-4 sm:mb-6 border-l-4 border-nba-orange">
        <p className="text-sm text-gray-400">{data.header.replace('{draft}', data.draft)}</p>
        <h1 className="text-xl sm:text-2xl font-bold text-white mt-1">Draft by season value. Let the room take its category players.</h1>
        <p className="text-gray-300 mt-2">
          Daily lineups, 9 starters, 13 spots and 5 adds a week: almost every game a rostered player plays counts. So a player is
          worth his FPTS a game over a streamer's ({data.streamer_fpg}) times the games he plays, and the bench is not a bench.
          The room drafts off Yahoo's default ranking, which is built for categories: it reaches for defenders and efficient
          bigs and lets high-usage scorers slide.
        </p>
        <div className="mt-4 grid sm:grid-cols-3 gap-3 text-sm">
          <div className="bg-gray-900 rounded p-3"><p className="text-gray-400">Before the first pick</p><p className="text-white">Draft mode on, stats on <b>2026-27 projection</b>. Your slot comes from Yahoo once it's set (or pick it in the strip).</p></div>
          <div className="bg-gray-900 rounded p-3"><p className="text-gray-400">Every pick</p><p className="text-white">Take the <b>top Season</b> player left. <b>Next turn</b> only breaks near-ties: under 35%, he won't come back.</p></div>
          <div className="bg-gray-900 rounded p-3"><p className="text-gray-400">Never</p><p className="text-white">Take a <b>room's pick</b> player early, or a long-term injury before round 10.</p></div>
        </div>
      </div>

      <Section title="What the simulated drafts say"
               subtitle={`${(sim.drafts || 0).toLocaleString()} drafts: 10 teams, 13 rounds, the room picking around Yahoo's ADP with this league's 2025 spread (sd about 20% of ADP). Score: season FPTS over a streamer, all 13 players, a week, against the average other team.`}>
        <table className="text-sm tabular-nums">
          <tbody>
            {(sim.rows || []).map(([label, v]) => (
              <tr key={label} className="border-t border-gray-700/60">
                <td className="py-1 pr-6 text-gray-200">{label}</td>
                <td className="py-1 text-right font-semibold text-white">+{v} FPTS a week</td>
              </tr>
            ))}
          </tbody>
        </table>
        <ul className="mt-3 space-y-1.5 text-sm text-gray-300 list-disc ml-5">
          <li>Season value beats the room's way by about <b className="text-white">{sim.gain_vs_adp} FPTS a week</b>, and the app's per-game order by {sim.gain_vs_pergame} (games played matter).</li>
          <li>Waiting on a player the room undervalues (taking someone else first and hoping he lasts) added nothing ({sim.lookahead >= 0 ? '+' : ''}{sim.lookahead}): the room wants different players, so yours come back anyway.</li>
          {(sim.smart_room || []).map(([label, ours, adp]) => <li key={label}>{label}: season value still wins, +{ours} vs +{adp}.</li>)}
          <li>Caveat: the simulation treats our projections as the truth. Real edge is smaller; the order of the rules held in every room tried.</li>
        </ul>
      </Section>

      <Section title="The room lets these slide" subtitle="Our season rank at least 15 picks ahead of Yahoo's ADP: points players the category ranking undervalues. Still take them in value order, but don't panic if one looks early: the room is not on him.">
        <PlayerList rows={data.sleepers || []} good />
      </Section>

      <Section title="The room's picks, not ours" subtitle="Yahoo's ADP at least 20 picks before our season rank: category players (defence, efficiency, few shots). Let someone else spend the pick.">
        <PlayerList rows={data.avoid || []} />
      </Section>

      <p className="text-xs text-gray-500 mb-6">Built {data.generated}. During the draft, <code>python pull_yahoo.py draft --league &lt;Yahoo league&gt; --apply --watch 20</code> copies Yahoo's picks onto the board (needs Firefox signed in to Yahoo).</p>
    </div>
  );
}

function DraftDay() {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    getDraftDay().then(setData).catch(e => setError(errorMessage(e)));
  }, []);

  // Players the room will likely pay most past your max: put them up on your nomination turns.
  const nominate = useMemo(() => (data?.players ? data.players.map(p => ({ ...p, room: opening(p.likely) })).filter(p => p.room > p.max)
    .sort((a, b) => (b.room - b.max) - (a.room - a.max)).slice(0, 12) : []), [data]);

  if (error) return <div className="bg-gray-800 rounded-lg p-6 text-gray-300">{error}</div>;
  if (!data) return <div className="bg-gray-800 rounded-lg p-6 text-gray-400">Loading the draft plan...</div>;
  if (data.type === 'snake') return <SnakeDraftDay data={data} />;

  const spots = data.spots || 160;
  const unpriced = (data.unpriced || ['A-TO', '3PM', 'TB']).join(', ');
  const tierSeries = (data.tier_series || WSOP_TIERS).map((t, i) => ({ ...t, color: [C1, C2, C3][i] }));

  return (
    <div className="max-w-5xl">
      <div className="bg-gray-800 rounded-lg shadow-xl p-4 sm:p-6 mb-4 sm:mb-6 border-l-4 border-nba-orange">
        <p className="text-sm text-gray-400">{(data.header || WSOP_HEADER).replace('{draft}', data.draft)}</p>
        <h1 className="text-xl sm:text-2xl font-bold text-white mt-1">Be patient early, buy when the room is broke.</h1>
        <p className="text-gray-300 mt-2">
          The room spends big early and runs dry by the last fifth. Hold your aim, don't fill spots with cheap players,
          and let the late rounds come to you. Expect about one player by half-way and money left at the end: that's the plan working.
        </p>
        <div className="mt-4 grid sm:grid-cols-3 gap-3 text-sm">
          <div className="bg-gray-900 rounded p-3"><p className="text-gray-400">Before the first pick</p><p className="text-white">Stats dropdown on <b>2026-27 projection</b>.</p></div>
          <div className="bg-gray-900 rounded p-3"><p className="text-gray-400">Every pick</p><p className="text-white">Enter the winning <b>price</b>, then Draft. Aim, pace, spot bar and top bid update from it.</p></div>
          <div className="bg-gray-900 rounded p-3"><p className="text-gray-400">Never</p><p className="text-white">Past the max, two $60+ players, or 3+ spots ahead of the room.</p></div>
        </div>
      </div>

      {data.guillotine && (
        <Section title={data.guillotine.title} subtitle={data.guillotine.subtitle}>
          <ul className="space-y-2 text-sm text-gray-200 list-disc ml-5">
            {data.guillotine.points.map(d => <li key={d}>{d}</li>)}
          </ul>
        </Section>
      )}

      <Section title="Draft night by phase" subtitle={`Phases by how many of the league's ${spots} roster spots are filled.`}>
        <div className="space-y-3">
          {PHASES.map(ph => (
            <div key={ph.share} className="bg-gray-900 rounded p-4 grid md:grid-cols-[11rem_1fr] gap-3">
              <div>
                <p className="text-white font-semibold">{picks(ph, spots)}</p>
                <p className="text-xs text-gray-400">{ph.share} of the draft</p>
                <p className="text-sm mt-2"><span className="text-gray-400">Aim </span><b className="text-green-400 tabular-nums">{ph.aim}</b><span className="text-gray-400"> of max</span></p>
              </div>
              <div>
                <p className="text-sm text-gray-400">{ph.room}</p>
                <ul className="mt-2 space-y-1 text-sm text-gray-200 list-disc ml-5">
                  {ph.do.map(d => <li key={d}>{d}</li>)}
                </ul>
              </div>
            </div>
          ))}
        </div>
        <div className="mt-4">
          <p className="text-xs text-gray-400 mb-2">Your limit as a share of the max, by share of the draft filled ($15+ players; under $15 the max is the limit from the start; stars start at 90%)</p>
          <div className="grid grid-cols-4 sm:flex gap-1">
            {AIM_CURVE.map(([at, pct]) => (
              <div key={at} className="flex-1 bg-gray-900 rounded p-2 text-center">
                <p className="text-xs text-gray-500">{at}%</p>
                <p className="text-sm font-semibold text-green-400 tabular-nums">{pct}%</p>
              </div>
            ))}
          </div>
        </div>
      </Section>

      <div className="grid md:grid-cols-2 gap-x-6 md:gap-y-6">
        <Section title="Nominate these" subtitle="The room's likely price is furthest past your max: put them up early on your turns and let other teams spend.">
          <div className="space-y-1.5">
            {nominate.map(p => (
              <div key={p.name} className="flex justify-between bg-gray-900 rounded px-3 py-1.5 text-sm">
                <span className="text-white">{p.name}{p.star ? ' ★' : ''}</span>
                <span className="tabular-nums text-gray-400">room ~{money(p.room)} · max <span className="text-amber-300">{money(p.max)}</span></span>
              </div>
            ))}
          </div>
        </Section>

        <Section title="The stars" subtitle={data.stars_note || STAR_NOTE}>
          <div className="space-y-1.5">
            {data.stars.map(s => {
              const room = opening(s.likely);
              const ok = room <= s.max;
              return (
                <div key={s.name} className={`flex justify-between rounded px-3 py-1.5 text-sm bg-gray-900 border ${ok ? 'border-green-600' : 'border-transparent'}`}>
                  <span className="text-white">{s.name}</span>
                  <span className="tabular-nums text-gray-400">room ~{money(room)} · max <b className="text-amber-300">{money(s.max)}</b> · {ok ? <span className="text-green-400">worth it</span> : <span>pass</span>}</span>
                </div>
              );
            })}
          </div>
          <p className="text-xs text-gray-500 mt-3">{data.stars_footer || `At most one star, and only at or under his max. All ${data.stars.length} are likely to go for more: buy one only if the bidding stalls.`}</p>
        </Section>
      </div>

      <Section title="Reading the board">
        <dl className="grid md:grid-cols-2 gap-x-6 gap-y-2 text-sm">
          {BOARD.map(([k, v]) => (
            <div key={k} className="flex gap-3">
              <dt className="flex-none w-40 text-white font-medium">{k}</dt>
              <dd className="text-gray-400">{v.replace('{unpriced}', unpriced)}</dd>
            </div>
          ))}
        </dl>
      </Section>

      <Section title="The four bench spots matter" subtitle="With daily lineups the bench plays: share of each roster slot's healthy games that count (2026-27 schedule).">
        <GroupedBars
          rows={data.bench_share.map((v, i) => ({ label: i < 6 ? `Player ${i + 1}` : `Bench ${i - 5}`, v }))}
          series={[{ key: 'v', label: 'Games that count', color: C1 }]}
          max={100} format={v => `${v}%`}
        />
        {data.bench_gain && (
          <p className="text-sm text-gray-300 mt-4">
            Same core with four random $1 bench players: <b>{data.bench_gain.random}</b> categories a week. With the right four: <b className="text-nba-orange">{data.bench_gain.best}</b>.
          </p>
        )}
        <h3 className="text-white font-medium mt-5 mb-2">Bench targets for the last fifth (likely $1-4)</h3>
        <div className="grid sm:grid-cols-2 gap-2">
          {data.bench.map(b => (
            <div key={b.name} className="bg-gray-900 rounded px-3 py-2 text-sm">
              <span className="text-white">{b.name}</span>
              <span className="text-gray-400"> · likely {money(b.likely)} · {b.gp} gp{b.strong.length ? ` · ${b.strong.join(', ')}` : ''}</span>
            </div>
          ))}
        </div>
      </Section>

      <Section title="Where the room loses money" subtitle="Value delivered per $1 paid, by price tier, in past auctions (1.0 = got what you paid for).">
        <GroupedBars
          rows={data.tiers}
          series={tierSeries}
          max={1.8} format={v => v.toFixed(2)} reference={1} referenceLabel="break-even (1.0)"
        />
        <p className="text-sm text-gray-400 mt-3">
          $40-74 is the worst tier both years, and the overpay is early: these players sell in the first third of the draft.
          Bought in the first 10% they went for 1.26x value; at 20-35% for 0.70x, returning 1.20 per $1. Your max for this tier is already 85% of value; cutting deeper tested worse.
        </p>
      </Section>

      <Section title="What was tested" subtitle="Simulated auctions with budgets, calibrated on both past drafts; six kinds of room (calibrated, hot, star-heavy, and mixes of number-crunchers, Fantrax, ESPN, BasketballMonster and vibes bidders). Categories won a week vs tonight's rules.">
        <div className="space-y-1.5">
          {TESTED.map(([k, v, ok]) => (
            <div key={k} className="flex justify-between gap-4 bg-gray-900 rounded px-3 py-1.5 text-sm">
              <span className={ok ? 'text-white font-medium' : 'text-gray-300'}>{k}</span>
              <span className={`tabular-nums whitespace-nowrap ${ok ? 'text-green-400' : 'text-gray-400'}`}>{v}</span>
            </div>
          ))}
        </div>
        <p className="text-xs text-gray-500 mt-3">The simulations treat our projections as true, so read which rule wins, not the size. Updated {data.generated}.</p>
      </Section>
    </div>
  );
}

export default DraftDay;
