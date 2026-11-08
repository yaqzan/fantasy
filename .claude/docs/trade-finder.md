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
- **Their side**: lineup value, no claims. They receive k and give k-1, so a full roster (13) is one over and cuts the player that
  costs the lineup least (`Ctx.with_forced_drop`; players the planner calls undroppable stay). `partner_week` = after - before.
  They are assumed NOT to stream, so it is a floor on what they gain. `min_partner` (API/UI, default 5 FPTS/wk) is the acceptance bar.
- **Closed form**: no-claims lineup value = sum over days of sum_k c_k x (top-k sum of the day's v), c_k = `claim_planner.layer_coefs`
  (the planner's own objective). Equal to the ILP with 0 claims: 1484.69 vs 1484.69, 1286.50, 1215.51 (3 weeks, 2026-11-08).

## How it is computed

`Ctx` builds, per sample week, one planner `Instance` with EVERY rostered player marked owned (`build_instance(roster_il=...)`:
~0.4 s a week) plus the free-agent pool. A hypothetical roster is a copy of it with other ownership flags (`Ctx.plan`; a traded-away
player is simply absent: not owned, not addable). Cached 120 s. Funnel:
1. (A) additive proxy, FPTS/week with no crowding, for every combination of partner x my fillers x their players: partner proxy >=
   `min_partner - 6`, ranked by my swap proxy, top 1200.
2. (B) exact no-claims lineup value of both rosters; partner gain >= `min_partner`; top 36 by my swap (the freed spot is worth about
   the same to every combination, 82-95 FPTS/wk, so ranking by swap is ranking by the total).
3. (C) the ILP on my side (3 weeks x 36, 4 threads). ~5 s warm, 8 s cold; result cache 60 s.

## Checked (2026-11-08, Courtside, anchor = one player, x=2)

All 1,884 combinations (every partner x every filler x every healthy player) through the ILP, 226 s: the funnel's top 8 equals the
exhaustive top 8 at `min_partner` 0 and 8. **Not checked: x=3** (stage A keeps 1200 of ~72,000 by the proxy).

## Traps and assumptions

- **The freed spot is worth ~85-95 FPTS/wk because my roster can only rotate ONE spot today**: the market rule makes every
  player above market + band undroppable, so the baseline streams through its single droppable player (claims worth 91 FPTS/wk to
  today's roster). A roster with more scrubs would see a smaller `slot`. It is the plan's rule, kept on purpose.
- A streamer on waivers above the market is a FAAB bid (`contested`); the plan counts on him anyway, as the week plan does.
- Positions are ignored (the planner's default), partners' IL players are not targets, injured (OUT) players are never targets.
- Partner acceptance is FPTS only: no draft capital, name value or ROS injury view. Raise `min_partner` for an offer they would take.
- Rosters are the DB's (hourly Yahoo sync); sync before trusting a result.
- Public repo: concrete trade targets and numbers for one player go in gitignored `.horizon/`, not here.
