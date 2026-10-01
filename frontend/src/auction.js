// The live auction: what the prices paid so far say about the prices still to come.
//
// factor = the room's money left above $1 a spot / the likely $ above $1 of the players still to be
// bought (the best undrafted ones, one per open spot), against the same ratio before the draft. When
// the room overpays early there is less money chasing the players left, so the factor drops under 1
// and what is left goes cheaper; when stars go cheap it rises. Replayed on both past auctions the
// later prices followed it (.claude/docs/draft-strategy.md "Live auction").
const LIMITS = [0.5, 1.5];

const extra = (dollars) => Math.max(0, (dollars ?? 1) - 1);
const topExtra = (prices, n) => [...prices].map(extra).sort((a, b) => b - a).slice(0, Math.max(0, n)).reduce((a, b) => a + b, 0);

// players: every player ({ name, drafted, fantasy_team, draft_price }); likely: name -> the room's
// likely price before the draft; teams: the league's teams still in it. A pick with no price
// recorded counts at its likely price (it moves nothing).
export function auctionState({ players, likely, teams, budget, rosterSize }) {
  const byTeam = Object.fromEntries(teams.map(t => [t.id, { spent: 0, count: 0, priced: 0 }]));
  const pool = [];
  players.forEach(p => {
    const team = p.drafted ? byTeam[p.fantasy_team?.id] : null;
    if (!team) {
      if (!p.drafted && likely[p.name] != null) pool.push(likely[p.name]);
      return;
    }
    team.count += 1;
    team.spent += p.draft_price ?? likely[p.name] ?? 1;
    if (p.draft_price != null) team.priced += 1;
  });
  Object.values(byTeam).forEach(t => {
    t.left = budget - t.spent;
    t.open = Math.max(0, rosterSize - t.count);
    // The most the team can bid: its money, less $1 for each other spot still to fill
    t.cap = t.open > 0 ? Math.max(0, t.left - (t.open - 1)) : 0;
  });
  const all = Object.values(byTeam);
  const spots = teams.length * rosterSize;
  const open = all.reduce((a, t) => a + t.open, 0);
  const left = all.reduce((a, t) => a + t.left, 0);
  const priced = all.reduce((a, t) => a + t.priced, 0);

  const before = topExtra(Object.values(likely), spots);
  const ahead = topExtra(pool, open);
  let factor = 1;
  if (priced > 0 && open > 0 && before > 0 && ahead > 0) {
    const start = (teams.length * budget - spots) / before;
    factor = Math.min(LIMITS[1], Math.max(LIMITS[0], ((left - open) / ahead) / start));
  }
  return { factor, left, open, priced, teams: byTeam };
}

// A pre-draft price moved by the factor ($1 stays $1).
export const adjusted = (dollars, factor) => (dollars == null ? null : Math.max(1, Math.round(1 + (dollars - 1) * factor)));
