// Snake draft helpers for the draft board (points leagues on Yahoo first: Courtside Tamasha 2026-27).
// Research: .horizon/courtside-2026/sim.py, draft-strategy.md "Snake draft, points league".

// Spread of where the room takes a player around his Yahoo ADP: sd = ROOM_SD x ADP, at least ROOM_SD_MIN picks.
// Measured on Courtside's 2025-26 draft: 0.2-0.24 x ADP in rounds 1-5, 9-12 picks in rounds 2-8.
export const ROOM_SD = 0.2;
export const ROOM_SD_MIN = 2.5;

// The team picking at overall pick n (1-based) in a snake draft over `order` (round-1 order; even rounds reverse).
export const teamAt = (n, order) => {
  const t = order.length;
  if (!t) return null;
  const r = Math.floor((n - 1) / t);
  const k = (n - 1) % t;
  return order[r % 2 === 0 ? k : t - 1 - k];
};

// Overall pick numbers of a team over `rounds` rounds.
export const picksOf = (abv, order, rounds) => {
  const t = order.length;
  const i = order.indexOf(abv);
  if (i < 0) return [];
  return Array.from({ length: rounds }, (_, r) => r * t + (r % 2 === 0 ? i : t - 1 - i) + 1);
};

const erfc = (x) => {
  // Abramowitz-Stegun 7.1.26, good to 1e-7
  const z = Math.abs(x);
  const t = 1 / (1 + 0.5 * z);
  const r = t * Math.exp(-z * z - 1.26551223 + t * (1.00002368 + t * (0.37409196 + t * (0.09678418 + t * (-0.18628806
    + t * (0.27886807 + t * (-1.13520398 + t * (1.48851587 + t * (-0.82215223 + t * 0.17087277)))))))));
  return x >= 0 ? r : 2 - r;
};
const beyond = (pick, adp) => 0.5 * erfc((pick - 0.5 - adp) / Math.max(ROOM_SD_MIN, ROOM_SD * adp) / Math.SQRT2);

// Chance a player still on the board before pick `now` is still there at pick `next`, the room drafting
// around his ADP. null without an ADP.
export const survival = (now, next, adp) => {
  if (adp == null || next == null) return null;
  const s = beyond(next, adp) / Math.max(beyond(now, adp), 1e-9);
  return Math.max(0, Math.min(1, s));
};

// Season value in a points league: (FPTS a game - a streamer's) x projected games. With daily lineups and a deep
// bench nearly every game a rostered player plays counts, and the weekly adds stream the rest; the streamer is the
// average of the best free agents once the league's spots are filled (ranks spots+1..spots+20 by FPTS a game).
export const seasonValues = (players, fpgOf, gpOf, spots) => {
  const fpg = players.map(fpgOf).filter(v => v != null).sort((a, b) => b - a);
  const tail = fpg.slice(spots, spots + 20);
  const streamer = tail.length ? tail.reduce((a, b) => a + b, 0) / tail.length : 0;
  const value = {};
  players.forEach(p => {
    const f = fpgOf(p);
    const g = gpOf(p);
    if (f != null && g != null) value[p.name] = Math.round((f - streamer) * g);
  });
  const rank = {};
  Object.entries(value).sort((a, b) => b[1] - a[1]).forEach(([name], i) => { rank[name] = i + 1; });
  return { streamer, value, rank };
};
