import React, { useEffect, useMemo, useState } from 'react';
import { getDraftDay, errorMessage } from '../services/api';

// Categorical slots 1-3 (dataviz reference palette, dark steps; validated on gray-800 #1f2937:
// all-pairs CVD dE 9.4, normal-vision 20.9, >= 3:1 contrast).
const C1 = '#3987e5';
const C2 = '#d95926';
const C3 = '#199e70';

const money = (v) => `$${v}`;

function Section({ title, subtitle, children }) {
  return (
    <section className="bg-gray-800 rounded-lg shadow-xl p-5 mb-6">
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

const STEPS = [
  { title: 'Stars: one at most, only at or under his max', body: 'Star or no star is a coin flip for the season (within 0.2 categories a week). Buy one only if the bid stays at or under his max below. Never two $60+ players.' },
  { title: '$40-74: bid up to 85% of the app\'s $', body: 'This tier lost money in both past auctions because the room paid above value (0.59 back per $1). Bought at or under value it broke even. The app\'s $ runs ~15% high here, so cap at 85%, lower if he projects under ~60 games.' },
  { title: '$15-39: bid up to 80% of the app\'s $', body: 'Same story, a little stronger: the app\'s value delivered ~77% in this range.' },
  { title: 'Under $15: the app\'s $ is your max', body: 'Cheap players delivered 1.2x their app value. This is where the room leaves money on the table.' },
  { title: 'Hunt the categories nobody pays for', body: 'A-TO, 3PM, TS%, TB, TF and W are unpriced by this room. Points and blocks are overpaid.' },
  { title: 'Pick your 4 bench players like starters', body: 'With daily lineups your bench plays most of its games. The right four $1 players beat four random ones by ~0.5 categories a week, more than the star question. Keep $4-10 for them.' },
];

function Verdict({ p }) {
  if (p.likely <= p.max) {
    return <span className="text-green-400 font-medium">Target: likely ~{money(p.likely)}, bid up to {money(p.max)}</span>;
  }
  return <span className="text-gray-400">Pass unless it stays at or under {money(p.max)} (likely ~{money(p.likely)})</span>;
}

function DraftDay() {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [query, setQuery] = useState('');
  const [showAll, setShowAll] = useState(false);

  useEffect(() => {
    getDraftDay().then(setData).catch(e => setError(errorMessage(e)));
  }, []);

  const matches = useMemo(() => {
    if (!data) return [];
    const q = query.trim().toLowerCase();
    if (!q) return [];
    return data.players.filter(p => p.name.toLowerCase().includes(q)).slice(0, 8);
  }, [data, query]);

  const targets = useMemo(() => {
    if (!data) return [];
    return data.players.filter(p => !p.star && p.likely <= p.max)
      .sort((a, b) => (b.max - b.likely) - (a.max - a.likely));
  }, [data]);

  if (error) return <div className="bg-gray-800 rounded-lg p-6 text-gray-300">{error}</div>;
  if (!data) return <div className="bg-gray-800 rounded-lg p-6 text-gray-400">Loading the draft plan...</div>;

  const tableRows = showAll ? data.players : targets.slice(0, 25);

  return (
    <div className="max-w-5xl">
      <div className="bg-gray-800 rounded-lg shadow-xl p-6 mb-6 border-l-4 border-nba-orange">
        <p className="text-sm text-gray-400">WSOP auction · {data.draft} · $200 · 10 spots, 6 active daily</p>
        <h1 className="text-2xl font-bold text-white mt-1">Bid on price, not structure.</h1>
        <p className="text-gray-300 mt-2">
          One star or none makes no real difference over a season. What wins: never paying above a
          player's max, and filling all 10 spots with players who help this league's categories.
        </p>
      </div>

      <Section title="Max bid lookup" subtitle="Type a name when he's nominated.">
        <input
          type="text" value={query} onChange={e => setQuery(e.target.value)} placeholder="e.g. Curry"
          className="w-full md:w-80 bg-gray-900 border border-gray-600 rounded px-3 py-2 text-white focus:outline-none focus:border-nba-orange"
        />
        {matches.length > 0 && (
          <div className="mt-4 space-y-2">
            {matches.map(p => (
              <div key={p.name} className="bg-gray-900 rounded p-3 flex flex-wrap items-baseline gap-x-6 gap-y-1">
                <span className="text-white font-semibold w-52">{p.name}</span>
                <span className="text-2xl font-bold text-nba-orange tabular-nums">max {money(p.max)}</span>
                <span className="text-sm text-gray-400">app {money(p.app)} · {p.gp} games{p.gp < 60 ? ' (injury risk)' : ''}</span>
                <span className="text-sm w-full"><Verdict p={p} /></span>
              </div>
            ))}
          </div>
        )}
        {query && matches.length === 0 && <p className="mt-3 text-sm text-gray-400">No player in the top 190 by value matches.</p>}
      </Section>

      <Section title="The steps">
        <ol className="space-y-4">
          {STEPS.map((s, i) => (
            <li key={s.title} className="flex gap-4">
              <span className="flex-none w-8 h-8 rounded-full bg-nba-orange text-gray-900 font-bold flex items-center justify-center">{i + 1}</span>
              <div>
                <p className="text-white font-medium">{s.title}</p>
                <p className="text-sm text-gray-400">{s.body}</p>
              </div>
            </li>
          ))}
        </ol>
      </Section>

      <Section title="The stars" subtitle="Max = where a build around him ties the best no-star roster (weekly matchup simulation). Each $10 over costs ~0.08 categories a week.">
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-3">
          {data.stars.map(s => {
            const ok = s.likely <= s.max;
            return (
              <div key={s.name} className={`rounded p-4 bg-gray-900 border ${ok ? 'border-green-600' : 'border-gray-700'}`}>
                <p className="text-white font-semibold">{s.name}</p>
                <p className="text-sm text-gray-400">likely ~{money(s.likely)} · app {money(s.app)}</p>
                <p className="mt-2 text-xl font-bold tabular-nums text-nba-orange">max {money(s.max)}</p>
                <p className={`text-sm mt-1 ${ok ? 'text-green-400' : 'text-gray-400'}`}>
                  {ok ? 'Worth his likely price' : `Let him go: ~${money(s.likely - s.max)} too pricey`}
                </p>
              </div>
            );
          })}
        </div>
        <p className="text-xs text-gray-500 mt-3">Break-evens are noisy by about $10. Only one star, ever.</p>
      </Section>

      <Section title="Why structure doesn't matter"
               subtitle="Expected categories won per week (of 11). Past seasons: random teams at that year's real prices, graded on what happened. 2026-27: best builds on projections.">
        <GroupedBars
          rows={data.structures}
          series={[
            { key: 'star', label: 'One star + cheap', color: C1 },
            { key: 'balanced', label: 'Balanced (nobody over $45)', color: C2 },
            { key: 'two', label: 'Two $60+ players', color: C3 },
          ]}
          min={4.5} max={7.2} format={v => v.toFixed(2)}
          reference={5.5} referenceLabel="league average (5.5)"
        />
        <p className="text-sm text-gray-400 mt-3">The winner flips by season. Who you buy inside a tier moves a team ~3x more.</p>
      </Section>

      <Section title="Where the room loses money"
               subtitle="Value delivered per $1 paid, by price tier, in past auctions (1.0 = got what you paid for).">
        <GroupedBars
          rows={data.tiers}
          series={[
            { key: 'orig', label: '2025, that league\'s categories', color: C1 },
            { key: 'w25', label: '2025, our 11 categories', color: C2 },
            { key: 'w24', label: '2024, our 11 categories', color: C3 },
          ]}
          max={1.8} format={v => v.toFixed(2)} reference={1} referenceLabel="break-even (1.0)"
        />
        <p className="text-sm text-gray-400 mt-3 mb-5">$40-74 is the worst tier in both years. But it's about the price paid, not the players:</p>
        <GroupedBars
          rows={data.below_value.map(b => ({ label: `n=${b.n}`, ret: b.ret, full: b.label }))}
          series={[{ key: 'ret', label: 'Delivered per $1', color: C1 }]}
          max={1.4} format={v => v.toFixed(2)} reference={1} referenceLabel="break-even (1.0)"
        />
        <ul className="text-xs text-gray-400 mt-2 ml-[8.25rem] space-y-0.5">
          {data.below_value.map(b => <li key={b.label}>n={b.n}: {b.label}</li>)}
        </ul>
      </Section>

      <Section title="Your bench plays"
               subtitle="Share of each roster slot's healthy games that count with daily lineups (slots ranked best to worst, 2026-27 schedule).">
        <GroupedBars
          rows={data.bench_share.map((v, i) => ({ label: i < 6 ? `Player ${i + 1}` : `Bench ${i - 5}`, v }))}
          series={[{ key: 'v', label: 'Games that count', color: C1 }]}
          max={100} format={v => `${v}%`}
        />
        <p className="text-sm text-gray-300 mt-4">
          Same core, four random $1 bench players: <b>{data.bench_gain.random}</b> categories a week.
          The right four: <b className="text-nba-orange">{data.bench_gain.best}</b>.
        </p>
        <h3 className="text-white font-medium mt-5 mb-2">Bench targets (likely $1-4)</h3>
        <div className="grid sm:grid-cols-2 gap-2">
          {data.bench.map(b => (
            <div key={b.name} className="bg-gray-900 rounded px-3 py-2 text-sm">
              <span className="text-white">{b.name}</span>
              <span className="text-gray-400"> · likely {money(b.likely)} · {b.gp} gp{b.strong.length ? ` · ${b.strong.join(', ')}` : ''}</span>
            </div>
          ))}
        </div>
      </Section>

      <Section title={showAll ? 'Every player' : 'Best value at likely prices'}
               subtitle="Likely = what this room paid for that rank in 2025, at our model's guess of his rank. Guesses miss by $13-16 on $20+ players, so use max bids, not likely prices.">
        <button onClick={() => setShowAll(!showAll)} className="text-sm text-nba-orange hover:underline mb-3">
          {showAll ? 'Show top value picks only' : `Show all ${data.players.length} players`}
        </button>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-gray-400 text-left border-b border-gray-700">
                <th className="py-2 pr-3">Player</th>
                <th className="py-2 pr-3 text-right">App $</th>
                <th className="py-2 pr-3 text-right">Likely</th>
                <th className="py-2 pr-3 text-right">Max bid</th>
                <th className="py-2 pr-3 text-right">Games</th>
              </tr>
            </thead>
            <tbody>
              {tableRows.map(p => (
                <tr key={p.name} className="border-b border-gray-700/50">
                  <td className="py-1.5 pr-3 text-white">{p.name}</td>
                  <td className="py-1.5 pr-3 text-right tabular-nums text-gray-300">{money(p.app)}</td>
                  <td className="py-1.5 pr-3 text-right tabular-nums text-gray-300">{money(p.likely)}</td>
                  <td className={`py-1.5 pr-3 text-right tabular-nums font-semibold ${p.likely <= p.max ? 'text-green-400' : 'text-gray-400'}`}>{money(p.max)}</td>
                  <td className={`py-1.5 pr-3 text-right tabular-nums ${p.gp < 60 ? 'text-yellow-400' : 'text-gray-300'}`}>{p.gp}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="text-xs text-gray-500 mt-3">Updated {data.generated}. Green max = the room will likely let him go at or under it. Yellow games = under 60 projected.</p>
      </Section>
    </div>
  );
}

export default DraftDay;
