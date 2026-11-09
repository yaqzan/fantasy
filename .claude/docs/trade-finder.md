# Trade Finder (trade_finder.py, `/api/trades`, tab "Trade Finder")

Yahoo daily-lineup points leagues (capability `trade_finder`). x-for-(x-1) trades (2 for 1, 3 for 2): I send x players, get x-1
back, and the roster spot that opens is rented to a streamer. Owner idea (2026-11-08): the spot is worth more than the extra player
I give up, so I can offer a partner a better-looking package and still win. Category leagues (Fantrax) come later.

## The math

All values are expected FPTS per week from the week plan's own model (`claim_planner`), for a hypothetical roster, averaged over the
next `SAMPLE_WEEKS` (3) full seven-day weeks after the current one (a trade lands after this week is mostly played; two-week
matchups are skipped). Streamers (and their waiver clearing dates, the market rule, keep values) are the plan's.
- **My side**, `value(R)` = `claim_planner.solve` on roster R with the week's claims (`model_fpts`: that week's points, no keep
  value). The ILP caps active players at N=13 per day, so a roster of 12 uses its claims to fill the open spot.
  - `swap` = the lineup value of R' with NO claims (closed form, below) minus today's. What the trade does to the lineup alone.
  - `slot` = `value(R') - value(R) - swap` = how much more the claims are worth to a roster with an open spot.
  - `me.week` = `swap + slot`. `me.season` = per week x the schedule weeks left (assumes the market and lineups hold).
- **Their side = the room's value, not lineup math (owner 2026-11-08: "nobody gives up Wemby for breadcrumbs like CMB").** The first
  version accepted a trade when the partner's LINEUP FPTS rose; FPTS is linear and the lineup has empty slots, so it offered Rank 2 for
  Rank 103 + a mid player. Now `market_values`: 100 x exp(-(rank-1)/tau), tau 35 (UI Steep 20 / Normal 35 / Flat 60), rank = mean of
  Yahoo's pre-draft rank (`.cache/yahoo_adp_<league>.json`) and today's FPTS/g rank among rostered + pool. A partner needs
  `market = value(what they get) - value(what they give) - value(the player they cut)` >= `min_market` (default 0 = fair). Not fitted
  to any trade data (none exists): at tau 20-35 the top offers are identical; at 60 star-for-two trades come back. A trade must
  ALSO raise their own lineup (no claims, forced cut, OUT players to a free IL slot first) by `min_lineup` (default 0).
- **How a 2-for-1 improves a partner's roster (owner asked 2026-11-08; numbers for the first, lineup-only version's Wemby-for-CMB-and-
  a-guard offer):** only through volume. Their lineup has empty slots on light days (3 players with a game on 3 days of a week), so
  two bodies play games one star would not: star 62 FPTS/g x 4 = 248/wk vs two players 266/wk, +31 / +6 / -15 over three weeks. If the
  partner streams, the spot I free is a spot they lose (-49 / -60 / -84 there): the slot value is close to zero-sum between two
  streamers, so a 2-for-1 is a real win-win only against a partner who does NOT use their claims, or when the swap itself is fair.
  Each row shows `partner_games` (extra active-slot games a week), `partner_stream` (their change if they stream, same ILP, 5
  claims; a healthy player in their IL is left out of that valuation) and `partner_adds` (claims they used this week, from the
  sync: 0 = not a streamer; one week is a weak signal).
- **Closed form**: no-claims lineup value = sum over days of sum_k c_k x (top-k sum of the day's v), c_k = `claim_planner.layer_coefs`
  (the planner's own objective). Equal to the ILP with 0 claims: 1484.69 vs 1484.69, 1286.50, 1215.51 (3 weeks, 2026-11-08).

## How it is computed

`Ctx` builds, per sample week, one planner `Instance` with EVERY rostered player marked owned (`build_instance(roster_il=...)`:
~0.4 s a week) plus the free-agent pool. A hypothetical roster is a copy of it with other ownership flags (`Ctx.plan`; a traded-away
player is simply absent: not owned, not addable). Cached 120 s. Funnel:
1. (A) every combination of partner x my fillers x their players that the room accepts (market >= `min_market` - 1), ranked by my
   additive swap proxy (FPTS/week, no crowding), top 1200 (6000 for 3 for 2).
2. (B) exact no-claims lineup value of both rosters, the real forced cut, the exact market test and `min_lineup`; top 36 (90 for 3 for 2) by my swap (the freed spot is worth about
   the same to every combination, 82-95 FPTS/wk, so ranking by swap is ranking by the total).
3. (C) the ILP on my side (3 weeks x 36, 4 threads), then on the shown rows' partners (what they do if they stream). 2 for 1: ~10 s; 3 for 2: ~20 s; result cache 60 s.

## Checked (2026-11-08, Courtside, anchor = one player, x=2)

(Run on the FIRST version, lineup-only acceptance, before the market filter.) All 1,884 combinations through the ILP, 226 s: the
funnel's top 8 equaled the exhaustive top 8. The market filter only removes combinations before stage A, so it is not a new pruning
risk; the exhaustive run was not repeated with it. x=3 (stage A keeps 6000 of ~49,000 by the proxy) was compared with a 20,000/200 widening: the 36-wide ILP stage missed a top-8 trade, 90 finds it; not re-run exhaustively.

## Traps and assumptions

- **The freed spot is worth ~85-95 FPTS/wk because my roster can only rotate ONE spot today**: the market rule makes every
  player above market + band undroppable, so the baseline streams through its single droppable player (claims worth 91 FPTS/wk to
  today's roster). A roster with more scrubs would see a smaller `slot`. It is the plan's rule, kept on purpose.
- A streamer on waivers above the market is a FAAB bid (`contested`); the plan counts on him anyway, as the week plan does.
- Positions are ignored (the planner's default), partners' IL players are not targets, injured (OUT) players are never targets.
- Today's injury list zeroes a player for all 3 weeks (`Week.injured`), so an OUT star is never a target; ESPN return dates would be new scope.
- `me.season` = week value x weeks left (playoffs included) and assumes the market rule holds all season.
- Acceptance is the room's rank value only: no draft capital, positional need or ROS injury view. Raise `min_market` for an offer they would take.
- The best offers give away real market value (a star in the package) because the freed spot is worth ~80 FPTS/wk and the swap costs ~30: it is a big FPTS gain only if the spot is truly worth that, so Keep your best players and compare.
- Rosters are the DB's (hourly Yahoo sync); sync before trusting a result.
- Public repo: concrete trade targets and numbers for one player go in gitignored `.horizon/`, not here.
