// Position fit for a points-league snake draft: what a player would add to MY roster over the season, on the real
// NBA schedule, with the league's lineup slots. Mirrors .horizon/courtside-2026/pos_sim.py, where picking by this
// (the best fit among the top 12 by season value) beat drafting on season value alone by ~60 FPTS a week: a roster
// of guards benches guards on busy nights while its forward and centre slots go to streamers.
//
// Each day, the players whose team plays and who are available go into the slots best FPTS/g first (greedy with
// augmenting paths, optimal for slot eligibility, as player_stats.fill_slots). Availability: each game with chance
// games / team games, a fixed pseudo-random draw per player (DRAWS seasons, averaged), so the numbers don't jump
// between refreshes. Empty slot-days get a streamer, at most STREAM a week (5 adds, ~2 games each).

const REACH = { PG: ['PG', 'G'], SG: ['SG', 'G'], G: ['PG', 'SG', 'G'], SF: ['SF', 'F'], PF: ['PF', 'F'], F: ['SF', 'PF', 'F'], C: ['C'] };
export const STREAM = 10;
const DRAWS = 3;

// Deterministic per-player random stream (mulberry32 seeded from the name).
const seeded = (name, draw) => {
  let h = 2166136261 ^ draw;
  for (let i = 0; i < name.length; i++) h = Math.imul(h ^ name.charCodeAt(i), 16777619);
  let a = h >>> 0;
  return () => {
    a = (a + 0x6D2B79F5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
};

// One player's inputs: { name, fpg, slots: [slot indices he can fill], days: [[day indices available] per draw] }.
export const fitPlayer = (name, fpg, games, positions, teamDays, slots) => {
  const reach = new Set(['UTIL']);
  (positions?.length ? positions : ['G', 'F']).forEach(p => (REACH[p] || []).forEach(r => reach.add(r)));
  const share = teamDays?.length ? Math.min(1, (games || 0) / teamDays.length) : 0;
  const days = Array.from({ length: DRAWS }, (_, d) => {
    const rnd = seeded(name, d);
    return (teamDays || []).filter(() => rnd() < share);
  });
  return { name, fpg: fpg || 0, slots: slots.map((s, i) => (reach.has(s) ? i : -1)).filter(i => i >= 0), days };
};

// Season FPTS of a roster (lineups + streamers), averaged over the draws.
export const seasonScore = (roster, nSlots, nDays, streamer) => {
  let sum = 0;
  for (let d = 0; d < DRAWS; d++) {
    const byDay = Array.from({ length: nDays }, () => []);
    roster.forEach(p => p.days[d].forEach(day => byDay[day].push(p)));
    const emptyWeek = new Array(Math.ceil(nDays / 7)).fill(0);
    let total = 0;
    for (let day = 0; day < nDays; day++) {
      const ps = byDay[day].sort((a, b) => b.fpg - a.fpg);
      const holder = new Array(nSlots).fill(null);
      let filled = 0;
      const place = (p, seen) => {
        for (const j of p.slots) {
          if (seen[j]) continue;
          seen[j] = true;
          if (holder[j] === null || place(holder[j], seen)) { holder[j] = p; return true; }
        }
        return false;
      };
      for (const p of ps) {
        if (filled === nSlots) break;
        if (place(p, new Array(nSlots).fill(false))) { filled++; total += p.fpg; }
      }
      emptyWeek[Math.floor(day / 7)] += nSlots - filled;
    }
    sum += total + streamer * emptyWeek.reduce((a, e) => a + Math.min(e, STREAM), 0);
  }
  return sum / DRAWS;
};

// For each candidate, against `roster` (both lists of { name, fpg, games, positions, teamDays }):
//   adds: season FPTS he adds with the league's slots, per week;
//   fit:  that over what he would add if every slot were UTIL. 1 = positions cost nothing; under 1 = some of his (or
//         a teammate's) games sit on busy nights. pos_sim.py: a 6th guard-only player 0.94, 7th 0.82, 8th 0.74, 9th 0.53.
export const fitTable = ({ roster, candidates, slots, nDays, streamer }) => {
  const util = slots.map(() => 'UTIL');
  const build = (list, s) => list.map(p => fitPlayer(p.name, p.fpg, p.games, p.positions, p.teamDays, s));
  const weeks = nDays / 7;
  const mine = { real: build(roster, slots), util: build(roster, util) };
  const base = { real: seasonScore(mine.real, slots.length, nDays, streamer), util: seasonScore(mine.util, slots.length, nDays, streamer) };
  const out = {};
  candidates.forEach(c => {
    const real = seasonScore([...mine.real, ...build([c], slots)], slots.length, nDays, streamer) - base.real;
    const asUtil = seasonScore([...mine.util, ...build([c], util)], slots.length, nDays, streamer) - base.util;
    out[c.name] = { adds: Math.round(real / weeks), fit: asUtil > 0 ? Math.min(1, real / asUtil) : 1 };
  });
  return out;
};
