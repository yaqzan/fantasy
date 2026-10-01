# Draft strategy and auction behaviour (WSOP-style auction leagues)

Measured 2026-09-30 for the 2026-27 WSOP league (14 teams, $200, 10 spots / 6 active daily, no
positions, 11 categories). Read this before advising on bids; don't re-derive it or ask the owner
to recall it. Scripts and raw outputs: `.horizon/wsop-auction-2026/` (gitignored, this machine;
`README.md` there, outputs in `out/`, data in `data/`). Fantrax league ids: memory `fantrax-access`.

## Categories
- Stored league = A-TO, REB, BLK, STL, NFT, 3PM, TF (fewer wins), TB (fewer wins), W, TS%, PTS.
  Fantrax's own scoring on 09-30 was different (AST, TO, PF instead of A-TO, TF, TB); the
  commissioner had to change it. Fantrax has all 11 as stats (AS-T, TF, BLKD "Times Blocked").
- TB was a real WSOP category in 2024-25 and 2025-26 (Fantrax `BLKD`); 2023-24 had W, A-TO, PPS,
  flagrant fouls. Fantrax `getStandings` header lists a league's categories per season.

## What the room pays for (past auctions)
Data: Fantrax `getDraftResults` (pull_fantrax.session()): 2024-25 WSOP (12 teams, 156 picks) and
the 2025-26 NBA Fantasy league with the same people (14 teams, 154 picks). The 2025-26 WSOP league
has no stored draft; 2023-24 was a snake. Model: price = exp(a + b.z) on the previous season's
per-game category z-scores (`market.py`), pooled, log-price per 1 z (90% bootstrap range):

| PTS | BLK | REB | AST | STL | W | NFT | 3PM | TB | TF | PF | TS% | TOV (fewer) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| .39 (.23-.55) | .28 (.17-.39) | .20 (.09-.34) | .16 (-.05-.35) | .15 (.07-.24) | .16 (.08-.25) | .13 (.02-.26) | .07 (-.03-.18) | .04 | .06 | .05 | -.03 | -.15 |

- **Overpaid vs equal weighting: points** (3x a typical category), then blocks, rebounds.
  **Unpriced: TS%, 3PM, TB, TF, PF; A-TO nets to about 0** (assists pay, low turnovers don't).
  TB was not priced even in 2024, when it was scored. Wins are paid a little (stars play on winners).
- Fit on one draft, predict the other: rank correlation .83 (equal-weight z over all cats: .6).
  Dollar error is big: MAE $13-16 on $20+ players, only ~40% within $10. Treat gaps under ~$15 as noise.
- Age: against the category model the room paid 1.3-1.4x for players in NBA years 2-5 and 0.92x for
  year 6+ (0.86x at age 30+), both auctions. But an age term barely helps on hold-out (error $9.8/8.2
  -> $9.5/8.1, rho unchanged; coefficient 2x apart between the drafts), and it moves a 21-year-old's
  likely price ~15%. Not added: Likely runs low for hyped young players and the model can't see hype.
- Likely prices feed the model this season's PROJECTED category z (it was fit on last season's
  actual stats). Checked on hold-out with each season's blend: projections predict the room as well
  or better (error $9.0 / $8.1 vs $9.8 / $8.2 on last-season stats; $20+ picks $16.7 / $17.8 vs $20.1 /
  $19.0). Kept. One player is still +/-$17-20: the same veteran was predicted $48 (paid $48) one year
  and $24 (paid $70) the other.
- Position premium: centers +$0.6, nothing. Games played matters (more games, higher price).
- The league never pays past ~$102 (top prices 100, 102; 91-100 in 2024).
- Output: `out/f2026.csv` (per player: our $, market $, edge, category z). Player-level gaps
  (buy/fade), prices and targets stay out of this public doc: `out/player_notes.md`.

## Return by price tier (past auctions, graded on the season after)
Return per $1 = the room's price at the player's finish rank / price paid. The original grade
(another session: 2025 auction, that league's own categories, finish ranked per game) against a
regrade in WSOP's 11 categories with missed games counted (`regrade.py`, `out/regrade.txt`):

| Price | 2025, its categories (original) | 2025, WSOP | 2024 WSOP auction, WSOP |
|---|---|---|---|
| $75+ | 0.89 | 0.88 | 0.71 |
| $40-74 | **0.70** | **0.71** | **0.67** |
| $25-39 | 0.82 | 0.69 | 1.16 |
| $15-24 | 0.91 | 0.81 | 1.02 |
| $8-14 | 1.22 | 1.17 | 1.39 |
| $3-7 | 1.30 | 1.35 | 1.72 |
| $1-2 | 3.18 (21 of 34 busts) | 3.96 | 2.49 |
- **Only "$40-74 is the worst tier" holds in both auctions**; stars and $25-39 swing by season. In z
  bought per $ (value above replacement x games share) $40-74 is also the lowest or second-lowest
  of the $8+ tiers both years.
- The metric tilts toward cheap tiers by construction: a star can't earn above ~$102 (finish #1),
  a $1 player can't earn under $1.
- 18 undrafted players finished top 100 in 2025-26, but only 1 waiver claim a week.
Source: session "Fantasy auction draft bidding analysis"; target list `.archive/draft-2026-targets.csv`.

## Category structure (2026-27 projections, 140 likely-drafted players)
- **NFT and PTS are near-duplicates (.89 player-level; .52 in matchups).** Two categories that win
  or lose together.
- Two axes: guard/scorer (PTS, NFT, 3PM, A-TO, STL rise together) vs big (REB, BLK, TS%).
  BLK-REB +.63; REB/BLK against 3PM (-.43/-.47); BLK against A-TO (-.40).
- **TB and TF are conceded by scorers** (PTS-TB -.69, NFT-TB -.62, PTS-TF -.52, NFT-TF -.52) and
  move together (+.33): the low-usage players who avoid technicals and blocks. A star-scorer build
  gives up TB/TF unless a filler covers them; a no-technical player ranks high only in those two.
- **W is independent** of everything (|r| <= .15): stack it on any build. Its projection is team strength.
- The 11 categories behave like ~5 independent ones (participation ratio 5.2).
- Best pairs to win together (best 6 under $196 at market prices): STL+TS%, STL+NFT, A-TO+TS%,
  STL+3PM; worst real pairs BLK+PTS, REB+3PM, BLK+3PM. TF/TB/W pairs are cheap to win and carry
  nothing else. Tables: `out/pairs.txt`, `out/pair_builds.csv`.

## 10 spots, 6 active, no positions
- **The bench plays.** On an average day only ~4.6 of 10 rostered players have a game, so daily
  lineups count 97/92/84/69% of the 7th-10th best players' healthy games (2026-27 schedule;
  `recon.Season`, identical to the app's `player_week_games`). A team fields ~9.4 players' worth of games.
- The app's auction $ price a 140-player pool (`num_teams x roster.size`). Pricing only the 84
  actives would add ~$30 to each of the top 14, +$6 to ranks 15-40, and take $5-10 from everyone
  ranked 41+. With the bench playing (~132 players' worth league-wide) 140 is the right pool.
  **Recommendation: keep 140 and the 1.1 exponent** (owner's call; the app is unchanged).
- No positions: the center premium above is gone, so don't price bigs up.

## Star vs balanced: the draft-night rule
Tested 2026-09-30 (kanban "Reconcile Star Vs Balanced Draft Strategy"; scripts and outputs in the
`.horizon/wsop-auction-2026/` README). **The data can't separate one star from a balanced roster.**
At the room's real prices the gap is within ±0.2 categories a week, and its sign flips between
seasons and between price stand-ins; who you buy inside a tier matters ~3x more (a team's sd
inside one price structure is .5-.8 categories a week).
**Default: bid on price, not structure.**
- **At most one star, and only at or under his break-even.** Of the five players the room will
  likely price highest, only two are worth about its price for their rank (#1 $102, #2-4 $90-92,
  #5 $75) in the weekly model; the other three fall $15-40 short. Per-star numbers: `out/player_notes.md`. Past the break-even each $10 costs
  ~0.07 categories a week. **A break-even is good to about +/-$10** (see "How sure is a break-even"). **Never two $60+ players** (worst structure in 2025, no better in 2024).
- **Max bid = a share of the app's $: 85% at $40-74, 80% at $15-39, 100% under $15** (lower when he
  projects under ~60 games; the app's $ is per game). Backtest on both auctions (`below_value.py`,
  value from the season before, delivery with games counted): $40-74 picks bought above app value
  returned 0.59 per $1 (21 of 28), at or under it 0.97 (7), 15-30% under 1.19 (3). The tier loses
  because the room overpays in it, and the app's own value ran high there: its $40-74 players
  delivered 86% of it, $15-39 77%, under $15 121%.
- **Pick the 4 bench players like starters.** The right four $1 players for your core beat four
  random ones by 0.5-0.6 categories a week, more than the star question; re-spending the budget
  across all 10 spots added only 0-0.2 on top.
- Unchanged: $8-25 players with 65+ projected games and value in the categories the room doesn't
  price (A-TO, 3PM, TS%, TB, TF, W).

### How sure is a break-even (2026-09-30, `breakeven_ci.py`, `pricing_check.py`)
**Since 2026-10-01 the weekly model's availability is projected games / 82 x the games haircut**
(`recon.availability`: .88, .78 after a season under 41 games; projections.md). The 2026-27 weekly
numbers below this section predate it; rerun values: best star build 6.68 vs no-star 6.47 (six-man),
7.06 vs 7.07 (ten-man); best $1 bench +0.5 over a random one. Star break-evens moved -$9 to +$7
(up for durable stars, down for the two with a short last season).
The first break-evens came from one run each (one opponent field, one random bench, one injury
draw). Rerun over 5-8 seeds per roster shape (`out/breakeven_ci_*.txt`):
- **One run is off by $10-20**: a star's break-even ranges $35-45 across seeds; the pooled fit has
  a standard error of about $5 per shape. One ten-man run had put a top-3 star $18 under his
  replicated number. `draft_day.py` now reads the replicated values.
- The ten-man roster puts break-evens $6-16 under the six-man core (the no-star roster gains more
  from a bench it can choose); the Draft Day max is their average. Slope -0.07 categories a week per $10 in every run.
- **Projected games are the biggest lever: ~$4 of break-even per game** for a star (5 fewer games
  took $19 off). The haircut itself raised the durable stars' six-man break-evens $7-11 (missed weeks hurt a
  no-star roster as much) and left the ten-man ones within $2.
- Against the best roster that may hold another star at the room's price, break-evens are $10-15
  lower: at most one of the top three is a buy, whichever goes cheapest.
- The break-even is not the app's $. App $ = per-game value over replacement (z capped at +/-3,
  140 pool, exponent 1.1); the break-even is where a roster built around him ties the best roster
  without a star in the weekly model, at the room's likely prices for everyone else.
- App $ of the top players by assumption (top-3 range): leave one source out +/-$4; one source
  alone -$12 to +$19; exponent 1.0 / 1.2 -$11 / +$12; games-weighted +/-$10. The cap matters for
  one-category outliers only: a player 5+ SD out in one category moves about $15 when the cap is lifted
  (up for blocks, down for technicals). The weekly model uses raw stats, so its break-evens
  already count that a category can only be won once a week; they still come out under the app $ for such a player.
- Past auctions (`below_value.py`): the app's $75+ players delivered 93% of their app $ (n=6).

### Why non-stars keep the share rule, not a modelled break-even (2026-10-01, `player_breakeven.py`)
Tried: a break-even for every player (~150; the price where the best roster with him ties the best
roster without him, both roster shapes, 6 seeds), backtested as a max bid on both past auctions
(296 picks, graded on the $ each delivered the season after, `out/player_breakeven.txt`).
- **It loses to the app's $.** Rank correlation of max bid with what the pick delivered: app $ .62,
  share rule .62, break-even .38 (.12-.35 inside every price tier vs .43-.53). Error $13.1 vs $10.3.
- Buying whenever price <= max: share rule 145 buys returning 1.80 per $1 (passes 0.76); app $ as
  is 160 buys at 1.53; break-even 84 buys at 1.63 (passes 0.89). The share rule was tuned on these
  auctions, so its edge over plain app $ is in-sample.
- Why it fails below the top: the comparison is against the best roster the search can build, so
  every player outside that roster shows a break-even under his price (2026-27: 44 of 49 app
  $15-39 players, break-even 19% of app $, negative under $15), and the two roster shapes disagree
  by $41 a player. It only says "is he in the optimal roster", which the bench/target lists
  already give. For app $75+ players it is calibrated (delivered / break-even 1.02, n=6), which
  is why stars keep theirs.
- **App $ on the projection counts projected games since 2026-10-01** (surplus x projected games /
  82, `calculate_auction_values`; projections.md). **Shares re-fit on the games-weighted $ (`refit_shares.py`,
  `out/refit_shares.txt`): .79 at $40-74 (90% range .67-.90), .80 at $15-39 (.67-.92), 1.00 at $8-14:
  no higher than before, so 85 / 80 / 100 stay and nothing is double counted.** Buys under the rule on
  $15+ picks returned 1.21 per $1, passes 0.68. The weekly model's games haircut (.88 / .78) is a
  separate path (star break-evens only); it is not in app $. Weighting by LAST season's games does not help: surplus x last season's games share (or half-way
  to 62 games) predicts delivered $ no better (rank correlation .61-.62 vs .62, error $10.8-11.1 vs
  $10.6; worse inside every tier). Last season's games say little about next season's (r .21).
  Projected games (sources + our model) do carry known absences; last season's count does not.
- **Both kinds of max mean the same thing: the price where a pick returns $1 per $1.** Checked
  2026-10-01 on the 296 past picks: delivered / app $ is .86 at app $40-74 (share .85), .77 at
  $15-39 (share .80), 1.07 at $8-14 (share 1.0; .68 and 1.59 by year); stars delivered 1.02 per $1 of
  break-even. So nothing is rescaled. Picks priced 100-120% of max returned 1.08 (90% range
  .88-1.25, n=18): not evidence that the limit sits higher. Value (app $ before the tier discount)
  and Likely (the room's price) are not bid limits.
- **Decision: non-stars stay on share x app $** (projected performance x the tier's measured
  overpay); stars on the replicated break-even.

### Simulated auctions around the max-bid rule (2026-10-01, `draft_sim.py`, `out/draft_sim.txt`)
400 drafts. Room price = likely price x an error drawn from how far the same construction missed in
the two past auctions, by tier (price / likely, 10th-90th percentile): $25-59 .51-1.52, $8-24
.31-1.88, $2-7 .25-2.00; **the five stars .99-1.21 (n=10): they never go cheap**. We take a player
when room price + $1 <= max and the roster rules allow, expensive players nominated first, open
spots filled with the best $1 leftovers. Scored with the weekly model against budget teams at the
likely prices (5.5 = an average team). Projections are treated as true, so every edge is overstated
(tiers have delivered ~80% of app $); read the order, not the size.
- **The rule as built: 6.36 categories a week vs 5.43 for a team that pays the room's price.** It
  spends the whole budget (unspent $1) and lands a star in 96% of drafts, at ~$88.
- **Pickier is better up to a point**: only buying at <=90% of max 6.61, <=80% 6.83 (unspent $23,
  under $150 spent in 16% of drafts), <=70% 6.57 (unspent $66). The gain is six $15-39 players
  instead of a star, one $40+ player and five $1 players.
- **No star scores ~0.2-0.3 higher here** (rule without stars 6.64; 80% without stars 6.84; 80% for
  non-stars with a star at up to his max 6.62). The bargains are in the middle of the board, where
  prices swing, and a star's $88 can't be spent on them. The break-even runs had star and no-star
  level because they priced everyone at the likely price, with no bargains to find.
- Draft-night reading: **want ~10-20% under max on $15+ players early, loosen toward the max as
  the draft goes and money is left; take a star only at a real discount (about 90% of his max), not
  merely under it.** Bidding to full app $ instead of the shares is the worst rule tested (6.22).

Why the two analyses disagreed (the ticket's six causes, in its order):
1. **Cost basis: the cause.** `strategy.py` charged the market model's predicted prices: the top 4
   at its $105 cap (the room paid 102/92/91/90) and ranks 15-84 16% under the room's 2025 curve
   ($1,387 vs $1,649). The same search at the curve (by the model's bid rank or by general rank):
   the best one-star build beats nobody-over-$45 by 0.2 (it had trailed by 0.3). `builds_z.py`
2. **Weekly noise.** The app's weekly H2H model (real 2026-27 schedule, daily best 6 of 10,
   whole-week injuries at GP/82, catalog noise) shrinks the z-model's 7.4-8.2 categories to 6.3-6.9
   and the gap to noise: best star build vs balanced 6.85 vs 6.64 (curve by model rank), 6.65 vs
   6.55 (general rank); whole 10-man rosters 7.16 vs 7.25 and 7.20 vs 7.12. `builds_week.py`
3. **Games.** Every tier played 57-61 games the season after its auction (stars 65 -> 58 from the
   season before); 2026-27 projections run 5-11 games high in every tier. Not a separator.
4. **The grade's categories.** In WSOP's 11 the grade flips on stars vs $25-39 between seasons
   (table above). `regrade.py`
5. **Z cap.** Uncapped z moves anchors -0.2 to +0.25; the star-vs-balanced sign doesn't change.
6. **84 vs 140 pool.** Wrong premise: the bench plays (above).

Direct tests on what happened (`retro.py`: past auctions at real prices, graded on the season after
in WSOP categories with the weekly model; against the real room, whose average is 5.5 a week):
- Random teams inside a price structure (se .03-.04): 2025 one star + five under $40 5.43, nobody
  over $45 5.63, two $60+ 5.24; 2024: 5.35, 5.26, 5.29. Spreading the money over all 10 spots
  instead of 6 + four random $1 players: +0.45 on average in 2024, 0 in 2025.
- Real teams with a $75+ player: 5.71 vs 5.38 without (2025, 5 vs 9 teams); 5.39 vs 5.66 (2024, 7 vs 5).
- The build model's own picks at the time (last season's stats, real prices): unconstrained it took
  one star both years and won 6.0 and 6.3 a week; its balanced build won 5.5 and 5.4. Its forecasts
  (7.4-8.5) ran ~2.5 categories high: read z-model numbers as rankings only.

## Caveats
- Market z use last season's stats; 2026 z use blended projections. Rookies have no prior.
- TB and TF projections are our model's (per shot / per minute); Fantrax projects neither.
- "Likely price" = the room's 2025 curve at a predicted bid rank (rho .83 on hold-out). The $1-10
  players the searches lean on are where that guess is weakest; the room may pay more. Anything
  "at market prices" above (pair builds) used the model's prices, which undercharge ranks 15-84.
- Past rooms filled 11-13 spots; bidding with 6 actives and a bench that plays is unobserved.
- Weekly model: two past seasons and 26 real teams; injuries as whole-week draws; W counted as wins
  (Fantrax may score wins per game); waivers (1 claim a week) and trades not modelled.
- Dollar gaps under ~$15, single-player "steals", and build differences under ~0.15 categories a
  week (the searches' own noise) are within model error.
- Rerun after projection edits (owner adjustments live in MySQL), from the repo root: `apply2026.py`,
  `pairs.py`, `strategy.py`, then `builds_z.py`, `builds_week.py`, `bench.py`, `breakeven_ci.py 6 base 8`
  and `10 base 5` (~40 min each, run side by side), `draft_day.py`.

## Draft Day tab (`/draft`)
The app's cheat sheet: steps, diagrams, star break-evens, a max-bid lookup, bench targets. It reads
`/api/draft-day`, which serves a gitignored `draft_day.json` (repo root) written by
`.horizon/wsop-auction-2026/draft_day.py`; without the file the tab shows the 404 message. The page
is public (owner's choice, 2026-09-30); the player data stays out of git.

**Draft mode** (header toggle, per league in localStorage): on by default for an auction league until
6 hours past `draft.date`. It hides the in-season tabs (lineups, pickups, daily stats, standings),
the trend and fantasy-points columns, the games-this-week line under each name, and the position filter when the league has no position
minimums. When `draft_day.json`'s `league` is the selected league, Player Rankings adds **Likely**
and **Max bid**. Max bid follows the Value column (so the stats basis and star-premium slider move
it) by the file's `rule`: stars at their replicated break-even, else Value x 0.85 ($40+) / 0.80 ($15-39) / 1.0.
The Max bid colour is a gradient on max minus likely price (`frontend/src/bidColor.js`): green when
the room should stop well short, neutral when even, orange when it will pay well past; the gap is
scaled by 30% of the larger price (floor $5) so a few dollars on a star stays neutral.
A **Notes** column (draft mode, when the plan belongs to the league) holds chips per player:
`aim <=$N` (the price worth holding out for early: 90% of a star's max, 85% of others from $15,
`draft_day.json` `aim`, from the simulated auctions), the what-if max bids for second- and third-year
players (rocket = after a +2 z breakout; chart = third-years with their average +0.53 z projection
miss added back; `/api/fantasy` `what_if`, `player_stats.auction_value_at`; what-if only, no value
changes), then `draft_day.json` `notes` from `draft_day.py`: categories at +1.5 z or better, at -1.5
or worse, the rule that applies (star, the tier the room overpays), bench target, projected games
under 60. The name column is capped at the width of the longest star name in draft mode.
Fantasy points stay hidden only in draft mode; dropping them for category leagues is a later job.
