# Draft strategy and auction behaviour (WSOP-style auction leagues)

Measured 2026-09-30 for the 2026-27 WSOP league (**16 teams** since 2026-10-02, see "16 teams";
$200, 10 spots / 6 active + 4 reserve daily, **no injury slot**, no positions, 11 categories). Read
this before advising on bids; don't re-derive it or ask the owner to recall it. Numbers below
dated before 2026-10-02 were measured at 14 teams; the "16 teams" section says what moved. Scripts and raw outputs: `.horizon/wsop-auction-2026/` (gitignored, this machine;
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
- **The pool the z-scores are standardized on is a separate question from the 140 that get priced,
  and a bigger one is more accurate** (2026-10-01, `pool_size.py` -> `out/pool_size.txt`).
  **Applied: `player_stats.SCALING_POOL_FACTOR = 1.8` players per roster spot (252 here; owner chose
  250), every league and timeframe. $ and the overall 0-100 score still use the 140 drafted.**
  Don't put it back to the roster spots. Pool-140 outputs: `backup_pool140/`.
  Chain rerun on it the same day: likely prices unchanged (the market model scales itself); weekly
  builds and bench identical (6.68 / 6.47, 7.06 / 7.07, same bench four: that model reads raw stats);
  star break-evens +$1-3 (seed noise; both shapes now 8 seeds); non-star max bids move $1.0 on
  average, none by $5; shares re-fit .82 / .80 / .97 (`refit_shares.py`), so 85 / 80 / 100 stay.
  Not rerun: `draft_sim.py`, and `builds_z.py` / `builds_week.py curve@gen`, which need the deleted
  2025-26 league (`.horizon/league-2025-26-backup.json`).
  Test: in the weekly model (raw stats, no z) swap one player for another on a random budget roster
  (~6,500 swaps a season, fringe players included); does the difference in summed z predict the
  difference in categories won? 2024-25 and 2025-26 realized, 2026-27 projected. Correlation, mean of
  the three, full health: pool 84 .915, **140 .926**, 160 .931, **200 .934**, 250 .938, **300 .940**,
  everyone .939. Same order in every season, with real games (.873 / .877 / .880 at 140 / 200 / 300),
  for whole rosters, and for swaps between two top-140 players. Flat from 180 to 220; "everyone"
  falls back in 2 of 3 seasons with real games. Smaller than 140 is worse every time.
  - The premise holds: only 73-75% of past picks were in our top 140 (by the season before), 87-88%
    in the top 200, 91-92% in the top 250. The room drafts by its own taste (points, blocks).
  - What a bigger pool does: a little more weight on A-TO, REB, BLK, 3PM, less on W and TB (5-9% at
    250). **It moves little money**: the 140 drafted players by $0.8 on average at 200, $1.2 at 250;
    only the top two move $5+ (down $5-9, they sit on the +3 cap in more categories); 2-5 players
    swap in and out of the top 140.
  - **The bigger miss is equal category weights, not the pool.** The best 11 weights fit to the same
    swaps reach .97 at any pool size (vs .93): W, TS%, TF and STL are worth ~0.5-0.75 of an average
    category (week-to-week noise swamps the gap between teams), PTS and NFT ~1.4-1.5, REB, BLK and
    A-TO ~1.2. With real games the fitted weights are unstable (PTS .6-1.4), so not adopted without
    its own test.
- No positions: the center premium above is gone, so don't price bigs up.

## 16 teams, no injury slot (2026-10-02)
Fantrax (`getStandings`, `getTeamRosterInfo` on the 2026-27 league) confirms 16 teams, 6 Active +
4 Reserve, no injury slot. Everything above was measured at 14 teams. The app already priced 16
(the `leagues` row): 160 players share $3,200, scaling pool 288. The research chain
(`.horizon/wsop-auction-2026/`) now reads teams, roster, budget and the price curve from the
league (`recon.TEAMS / DRAFTED / BUDGET / CURVE_KEY`); the 14-team outputs are in `backup_14teams/`.
- **The room's curve** `projected_16x10` (`draft_history_price_curve.json`, revised 2026-10-03 by the audit,
  `star_prices.py` -> `out/star_prices.txt`): the 2025 curve moved by **teams share** (rank r of 16 teams
  priced at the 2025 price of rank r x 14/16, interpolated, scaled so 160 players sum to $3,200): top 5
  104 / 96 / 93 / 92 / 86, rank 10 $51, rank 20 $41, rank 40 $27, ~12 players at $1. Checked by
  predicting each past auction from the other: teams share missed least overall (rank 1 within $2,
  ranks 6-12 $25-26 vs $31-38, ranks 13-160 best or tied); holding the top 5 in $ (the 2026-10-02 rule)
  was better only at ranks 2-5 for 2025 -> 2024. Proportional scaling is worst (#1 off by $13-15).
  The old curve is kept as `projected_16x10_hold5`; `projected_16x10_from2024` (the same rule from the
  2024 room: 102 / 101 / 98 / 95 / 94 / 92 / 90 / 89) is the high-star scenario.
  - **What the two rooms say about stars** (only two auctions exist; every other Fantrax league id we
    hold is a snake or has no stored draft): #1 went for $100 / $102 although money per pick rose 18%
    (proportional scaling misses him by $13-15), so "~$100-104 is the ceiling" holds. Hold-out likely
    prices for the model's $75+ players were right on average both years (paid / likely median 1.00).
    The bigger room was not the star-heavy one: the 12x13 room had six players at $85+ and 42% of its
    money in its top 12; the 14x11 room had four and 30%. More roster spots per team (more $1 fills) put
    more money on the top; 10 spots points the other way, 16 bidders for ~5 stars points up.
- **App $ moved ~+4% at the top** (the top three +$3-4 each), +$2-3
  through the $40s, +$1 in the teens; the top 160 now sum to $3,200. Replacement level (first
  undrafted) fell from value -0.75 (rank 141) to about -1 to -3 (rank 161).
- **Fewer bargains by the share rule**: with the richer middle, players whose likely price is at
  or under our max went from 82 to 74 of the 160. The $40-74 tier, already the room's overpay,
  gets more of the new money than the stars do.
- **No injury slot changes nothing in the model.** The weekly model always had an injured player
  holding a roster spot (whole-week injury draws, daily best 6 of the healthy), and star
  break-evens carry the games haircut (~$4 per projected game). What the thinner pool adds: after
  pick 140 the free agents are weaker than before, so a long absence costs more and projected
  games (known absences) weigh more. Bench targets still price at $1 on the new curve.
- Rerun on the teams-share curve (2026-10-03, `logs/a3_*.log`): `breakeven_ci.py 10` (8 seeds), `builds_week.py
  curve@model`, `bench.py`, `draft_day.py`; hold-5 outputs in `backup_hold5curve/`. Not rerun: `draft_sim.py`
  (superseded for live rules by `auction_sim.py`), the 6-man break-evens (no longer used).
- Rerun on the 16-team curve (2026-10-02, `logs/t16_*.log`): `apply2026.py`, `breakeven_ci.py` 6 +
  10 (8 seeds each), `builds_week.py curve@model`, `bench.py`, `draft_day.py`, `draft_sim.py`.

### What the 16th team changed (2026-10-02, revised by the 2026-10-03 audit)
Player-level numbers: `out/player_notes.md` ("16 teams" and "Audit 2026-10-03").
- **Stars are passes at the room's price on the corrected curve.** The 10-man break-evens of the top three
  fell $11-13 to the high $80s / low $80s, $4-23 under their likely prices ($92-104). Why: a dearer top
  leaves less of the $3,200 for the rest, so the no-star roster gets cheaper. One run had put them $10-20
  higher; the doc's 6-man shape was extrapolated past its $120 price grid, so **star maxes are now the
  whole 10-man roster's break-even alone** (`draft_day.py STAR_MODES`).
- Non-star maxes rose $3-4 at the top and $1-2 in the $20s with the 16-team app $; the $40-74 tier is
  still where the room's money lands first (likely a few dollars over our max).
- Bench targets still price at $1-3.

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
- $8-25 players with 65+ projected games and value in A-TO, 3PM or TB (cheap and worth winning; TS%, TF and W
  are cheap too but worth least: see "Mixed room" below; changed 2026-10-03).

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
  from a bench it can choose); the Draft Day max was their average until 2026-10-03, now the 10-man alone. Slope -0.07 categories a week per $10 in every run.
- **Projected games are the biggest lever: ~$4 of break-even per game** for a star (5 fewer games
  took $19 off). The haircut itself raised the durable stars' six-man break-evens $7-11 (missed weeks hurt a
  no-star roster as much) and left the ten-man ones within $2.
- Against the best roster that may hold another star at the room's price, break-evens are $10-15
  lower: at most one of the top three is a buy, whichever goes cheapest.
- The break-even is not the app's $. App $ = per-game value over replacement (z capped at +/-3
  against the 252-player scaling pool, 140 priced, exponent 1.1); the break-even is where a roster built around him ties the best roster
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
- **The sim's bargains are free; real ones are not (winner's curse, 2026-10-03).** On the 186 past
  picks with app $5+ (`out/player_breakeven_backtest.csv`; app $ from the season before, delivered
  $ the season after), log(delivered / app $) on log(price / app $): slope .33 (.34 in 2024, .35 in
  2025), rank correlation .30. When the room paid half our $ or less, the player delivered .60 of
  our $ (.55 at app $15+, n=30); at 85-100% of our $ he delivered .93. Cheap picks still returned
  well per $1 paid (3.1 at under half), so the share rule (fit on real outcomes) stands, but the
  sim prices every bargain at full projected value and stars never go cheap, so its "picky" and
  "no star" margins are overstated. Caveat: app $ there came from last season's stats; projections
  carry some of what the room knew, so the slope on projections is likely smaller.
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

## How the 2026-27 auction ended (2026-10-04, `final_sim.py`, `out/final_sim.txt`)
- Final 160 rosters from MySQL, weekly model (40 and 100 draws, same ranks), 4000 seasons on the real Fantrax
  schedule (getStandings view SCHEDULE -> `data/schedule_2026.json`) and on random ones. Fantrax ranks the regular
  season by category points (H2H each category), so the category record is the one that counts.
- **Our team ranks 1st of 16**: 57% of categories vs the field, 62% of matchups; 1st in 46% of seasons on the real
  schedule (31% on random ones), top 4 in 82% (72%). Board value $280 for $185 paid (+95; next best +69). No player
  over $34; ten $10-34 players.
- **Schedule strength has to be measured week by week.** Averaged over the season every team's opponents are within
  .05 categories of average; matched to the week we meet them (opponents short of games that week) ours are the
  easiest in the league, +0.19 categories a week (+3.2 over the season).
- Value over price predicts the sim order: the top three by board value minus price are the top three by sim;
  the two teams that paid ~$65 over board value (two $50+ buys the board valued under half) are last.
- Weakest categories: PTS and A-TO (.47-.49 vs the field); best W (.67) and REB (.61).
- **Don't punt** (`trade_sim.py`, `out/trade_sim.txt`): our weakest categories (PTS, A-TO) still win 52-53% of
  weeks, worth ~9 points each over the season. Ranked by the other categories, no trade beat a balanced one; the
  only punt-shaped gains were star-for-depth trades no partner would take (they lose 7-16 points).
- Trades (31,875 1-for-1 / 2-for-2 / 2-for-1 searched, real schedule): ones both teams gain from in the model add
  +1 to +3 points for us (1st 46% -> ~52-55%); ones a partner would read as fair on draft price add up to +4 (-> ~60%)
  at their expense. Free-agent swaps: under +1.
- Player-level detail (who, what price): `.horizon/wsop-auction-2026/out/final_sim.txt`, `out/trade_sim.txt`.

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
The app's draft-night cheat sheet (rebuilt 2026-10-03): the plan by phase of the draft (aim curve, what the room does, what to do), a nominate list (likely price furthest past the max), the stars, how to read the board, bench share and targets, the tier-return chart and what was tested. The max-bid lookup and player table were dropped: the board does that live. It reads
`/api/draft-day`, which serves a gitignored `draft_day.json` (repo root) written by
`.horizon/wsop-auction-2026/draft_day.py`; without the file the tab shows the 404 message. The page
is public (owner's choice, 2026-09-30); the player data stays out of git.

**Draft mode** (header toggle, per league in localStorage): off unless switched on (owner's call,
2026-10-09; it used to switch itself on until 6 h past `draft.date`). It hides the in-season tabs (daily leaders, lineups, pickups, standings),
the trend and fantasy-points columns, the games-this-week line under each name, and the position filter when the league has no position
minimums. Player Rankings renders `frontend/src/components/DraftBoard.js` instead of `PlayerTable.js` (rank,
score and $ come from the shared `usePlayerValues.js`): 40px rows that fit a 1650px pane without
sideways scroll, a header and player column that stay put while the table scrolls in its own pane,
and each category as one heat cell (teal strong, rose weak, value printed, score on hover).
The Draft button opens a small menu of the teams' short names; a click records the pick (he leaves
the Available list and shows on that team above). A drafted player's button opens the edit modal.
When `draft_day.json`'s `league` is the selected league the board adds one **Bid** cell, a ruler
across its full width: a baseline with end stops and a graduation every 4.25% of the cell, and
**Aim, Max and Value at the same three marks in every row** (`RAIL`), each number above a tick in
its colour, so they read as columns and sort from their header labels. The graduations are
decoration (the three marks are fixed, not to a $ scale); only the room's pointer moves.
- **Aim** (the limit now: 85% of the max from $15, 90% for stars, climbing to the max by 80% of the league's
  spots, `aimShare`; the max itself under $15; `draft_day.json` `aim` holds the starting shares) is the big
  number; a bar runs from it to the **Max**.
- **Max** follows the app value (so the stats basis and star-premium slider move it) by the file's
  `rule`: stars at their replicated 10-man break-even, else Value x 0.85 ($40+) / 0.80 ($15-39) / 1.0,
  never under the top of a cheaper tier ($15-18 -> $14; `shareMaxOf` in `auction.js`, `draft_day.share_max`;
  before 2026-10-03 a $15 player's max was $12, under a $14 player's $14).
- **Value** (the app's $; not a limit) ends the rail.
- **Room** (the likely price x the live factor x the early markup, `roomPrice`) is a smaller number with its own tick, placed by where it falls (`roomAt`):
  before the aim, between aim and max, between max and value, or past the value. Its distance
  inside a zone is to scale; the zones themselves are fixed.
- Colours are fixed: aim green, max amber, value white. The room's number carries the verdict: green
  at or under the aim, grey up to the max, red past it. "best buys" in the Bid header sorts by max
  minus likely price scaled by 30% of the larger price, floor $5 (`bidEdge` in `frontend/src/bidColor.js`).

### Live auction (2026-10-01, `frontend/src/auction.js`, `live_inflation.py`, `out/live_inflation.txt`)
Each row has a $ box beside Draft: type the winning bid, Draft, the team. The price is stored on
`fantasy_team_players.price` (`/api/draft-player` `price`; left out, a recorded price is kept;
`/api/fantasy` `draft_price`). A drafted player's box shows the price and can be typed over.
- **Factor** = the room's money left above $1 a spot / the likely $ above $1 of the best undrafted
  players (one per open spot), against the same ratio before the draft; kept in 0.5-1.5; picks with
  no price count at their likely price. **Only the room's price** becomes (1 + (pre-draft $ - 1) x
  factor) x the early markup (hover a row for the pre-draft numbers); aim, max and Value do not move (audit 2026-10-03, below).
- **Early markup (2026-10-03, `early.py` -> `out/early.txt`, `EARLY` in `auction.js`).** The factor starts at 1 and can't see
  the early overspend. Replayed on both auctions, paid / (likely x factor): likely $5-25 2.02 / 1.65 / 1.55 in the first
  10 / 10-20 / 20-30% of the draft (n=8-14 each), 1.08 at 30-50%; $26+ 1.06 / 1.16 / 0.89. Markup: $5-25 x1.6, $26+ x1.1
  until 20%, straight down to x1 by 35% / 25%. Early miss (likely $5+, first 35%) 10.6 -> 9.6 $ (2024), 9.3 -> 7.9 (2025),
  median paid / room 1.16-1.19 -> 1.01-1.05. Fit in-sample on 98 picks: one year's multipliers on the other split
  (the $5-25 cells run 1.1-2.75 by year), so read it as direction, not a price. It flows through the Room colour, "best
  buys", the nominate sort, the price dial's start, the "early: room x1.6" tag, and Draft Day's nominate and star lists
  (room at the opening, `roomPrice(likely, 1, 0)`).
- **Why it is trusted**: replayed in pick order on both past auctions (hold-out likely prices), the
  factor fell to .80 / .92 after 25 picks and .57 / .60 after 100 (the room overspends early both
  years), and later prices followed it: rank correlation of price / likely with the factor .53,
  slope 1.8 in logs; error on the second half of the draft $4.7 -> $2.9 with the factor, first half
  $8.9 -> $8.2. Part of the late drop is nomination order (cheap players come up last).
- **How the rooms spent (audit 2026-10-03, `dynamics.py` -> `out/dynamics.txt`)**: the first 20 picks went
  1.17 / 1.19 x likely in both rooms; overspending is sticky (paid / likely of the last 10 picks vs the
  next: corr +.56 / +.60). **The endgame is a money shortage, not a lack of interest**: in the last 30% of
  the draft, players who went for $1-2 had a second-highest team cap of $2 at that moment (median; under
  $5 in 63%), and only one team could bid $5+. Those late picks returned 2.86 per $1 ($5.4 delivered on
  average; 13 of 67 delivered $10+). Rooms left $27 / $43 unspent (1.1% / 1.5% of the money); by team $0-14 (2024) and
  $0-11 (2025); 10 of 12 and 6 of 14 teams ended with $1 or less. The owner left $4 (2024) and $11 (2025, the most of 14).
- **Scaling our max by the factor was the worst rule tested** (`auction_sim.py` -> `out/auction_sim.txt`,
  `out/auction_sim_tune.txt`). The sim: an auction with budgets, every room team bids its value (likely x
  a common error x its own taste) up to its cap, best bid wins at the second + $1; calibrated on both past
  rooms' shapes (`auction_sim.py calibrate` -> `out/auction_sim_calibrate.txt`). Best fit: **no pacing, no
  reserve** (teams bid value until broke), common error .15-.3; it reproduces the early overspend (1.07-
  1.12 vs 1.11-1.15 in the first fifth), the last-fifth collapse and the late caps, but runs q2-q3 hotter
  than 2024's room and nominates in weaker best-first order (rho .42-.50 vs .63-.80). Scored with the
  weekly model, 300 drafts, gain over "max as is" (three calibrations):
  aim 85% x room factor (the board as built 2026-10-01) **-0.31 to -0.40 categories a week, $64-77
  unspent**; max x room factor 0 to -0.01; max x my own factor (my $ per open spot vs the room's) -0.48
  to +0.18 (unstable); **aim 85% to half the draft + a spot bar 1.0: +0.32 to +0.47, $3-9 unspent**;
  spot bar 0.5 +0.15-0.24, 0.7 +0.26-0.37, 1.25 +0.42-0.46, 1.5 +0.35-0.40, 2.0 +0.28-0.32; aim held to
  50% or 65% of the draft ties; the aim without a spot bar loses (-0.09 to -0.27, money left over).
  **Spot bar** = before the last quarter of the draft, don't buy a player whose app $ is under my money
  per open spot (above $1 each, plus $1; $20 at the start). Why it works: with 10 spots a cheap pick
  spends a spot the money should fill, and the late room is broke, so spots left for the end fill at
  $1-3 anyway. Caveat: the sim treats projections as true (no winner's curse, see "Simulated
  auctions"), so the sizes are high; the order held in every calibration.
- **Mid-tier players bought early cost the most (2026-10-03, `my_draft.py` -> `out/my_draft.txt`).** Likely $5-25
  players across both rooms: first 20% of the draft paid 1.69 x likely (1.33 x app $), delivered 0.93 per $1
  (n=19); 20-50% 0.99 x likely, 1.21 per $1; 50-75% 0.85, 1.23; last 25% 0.45, 1.98. Early nominations of
  mid players are bait. The owner's own 2025 roster (player-level in `out/player_notes.md`) filled first of
  14 teams at 55% of the draft (room median 88%), 9 of 11 spots in the first half, nobody over $25; 6 of
  11 picks were under the spot bar, and 70 picks went by after it was full.
- **Stress test of the rules (2026-10-03, `stress.py`, `stress_catchup.py` -> `out/stress*.txt`).** Eight rooms x 300
  drafts: calibrated; disciplined (paces, keeps $3 a spot); hot (wide tastes, 1.37 x likely early); star-heavy (the
  2024-style curve); smart (half agrees with our $); best-first nominations; tight prices; disciplined + smart.
  - The rules beat the 2026-10-01 board in every room (+0.3 to +1.4 categories a week). **That old board reproduced
    the owner's 2025 draft**: full at 28-62% of the draft, 9.9 of 10 spots in the first half, $66-126 unspent.
  - **New risk: rooms with nothing under the max** (hot, star-heavy, smart): $30+ unspent in 45-57% of drafts,
    1-2.4 spots in the first half; the smart room's worst tenth ends with $58 and ~6 spots filled late. Every
    catch-up rule did worse there and elsewhere (behind 2 -> no aim -0.04 to +0.05; bid to app $ when behind or
    1.5x richer per spot than the room -0.02 to -0.35; with a lower bar or from 25% of the draft worse still):
    money left over is the rules refusing to overpay, not a loss. The real risk is abandoning them at half-way.
  - Pace guard 3 beat 2 in every room (+0.02-0.05), still never full before 60%. Dropping the aim lost 0.13-0.31
    except in the smart room (+0.07). The early-tier skip and overpay nominations are neutral in the sim (+/-0.05);
    kept for the real-draft evidence above.
- **Mixed room (2026-10-03, `mixed.py`, `mixed_rules.py` -> `out/mixed*.txt`).** The owner's read of the room:
  about half number-crunchers, the rest on vibes or a site's ranking. Each simulated team follows one source,
  priced on the room curve at its rank there: vibes (the market model = past pricing), Fantrax's projected rank
  for this league (`data/fantrax_rank_2026.json`; it has Luka #1), ESPN 9-cat on ESPN's projection (totals),
  BasketballMonster-style 9-cat per game, nerd (this league's 11 = the app $). Rank agreement with the app $:
  Fantrax .58, vibes .78, ESPN 9-cat .83, BBM .84. Rooms: 4/3/3/2/3 nerd/bbm/fantrax/espn/vibes, more vibes,
  more nerds; 300 drafts each.
  - The mixed room pays 0.92-0.95 x app $ for $15+ players, so the rules buy 0.2-1.1 players in the first half
    and leave $49-66 unspent (53-62% of drafts over $40). **Still best**: no aim -0.05 to -0.14, shares 90/90
    -0.06, bid to value -0.19 to -0.21, bar 0.7 -0.08 to -0.10, catch-up (behind or 1.5x richer -> value)
    -0.35 to -0.40, no rules -0.65 to -0.84. The second half is where it buys: the room is broke by then.
    Not modelled: a room that sees one team holding $150 at half-way and bids it up on purpose.
  - **Category weights don't belong in the max**: maxes from the fitted weights (mean of six fits, or 2024-25
    only, or only their stable part, or the old "unpriced x1.25" card) scored -0.08 to +0.03 against equal.
  - What the mixed room underpays per 1 z (log price / app $): W -.16, TF -.15, TB -.11, TS% -.11, 3PM -.09,
    NFT -.08; overpays PTS +.29. Fitted worth (`pool_size.txt`, pool 200, six fits): A-TO 1.06-1.46, REB
    1.17-1.37, BLK 1.03-1.37, 3PM .99-1.41, PTS .84-1.62, TB .89-1.10, NFT .66-1.45 (unstable), W .62-.98,
    TF .56-.97, STL .51-.75, TS% .37-.88. **Cheap and worth winning: A-TO, 3PM, TB**; TS%, TF and W are cheap
    because they matter least. The board's amber "unpriced" marks now flag only those three (`QUIET`).
- **Bid curve instead of aim-then-max (2026-10-03, `gradient.py` -> `out/gradient.txt`).** Limit = max x (a0 + (1 - a0) x
  min(1, progress / p_end)^k), optional boost above max when my $ per open spot beats the room's, spot bar level and
  end. 122 random curves x 6 rooms (calibrated, hot, star-heavy, 3 mixed) x 60 drafts; the best 8 re-scored on 300
  fresh drafts a room. **Adopted: a0 .85 (stars .90), full max at 80% of the league's spots, k 2 (slow then fast),
  spot bar 1.25 x my $ per spot until 80%: +0.08 categories a week over 85%-then-max at half-way, better in all six
  rooms (+0.03 to +0.10), $49 unspent vs $40.** The best mean (+0.09: a0 .75, same ramp, bar 1.0) lost in the
  star-heavy room and left $62. No top curve used the richness boost; the most aggressive (max from pick 1) -0.24.
  The search does not spend the leftover money: the gain is from staying patient longer, then ramping. Small next
  to model error (builds under ~0.15 are noise), kept because it never lost a room.
- **U-shaped curve and a deeper $40-74 cut: rejected (2026-10-03, `gradient2.py` -> `out/gradient2.txt`).** Against the
  adopted curve, 86 configs x 6 rooms, finalists on 300 fresh drafts a room: U (bid 95-100% early, dip to 75-90% at
  20-50% of the draft, max at 80%) -0.005 to +0.020, losing in 1-3 rooms; $40-74 at 90% / 80% of the max (on top
  of the 85% share) -0.02 / -0.09, star-heavy room -0.13 / -0.29. Best overall: $15-39 at 90% of the max, +0.026
  (se .004), never worse in a room; not adopted (well under model noise). Real drafts say why the U fails: $40-74
  players sell in the first third (median 13-16% of picks); app $40-74 bought in the first 10% went 1.26 x app $
  and returned 0.82 per $1, 10-20% 0.95 x / 0.89, 20-35% 0.70 x / 1.20. The overpay is early, where a U bids most.
- **Target lists instead of max bids: rejected (2026-10-03, `focus.py` -> `out/focus.txt`).** Targets = the top 20 / 40 /
  60 by the board's "best buys" edge, or the 21 names in the weekly model's best builds; 300 drafts x 6 rooms vs the
  adopted rules. Bidding only on targets (others skipped until 80% of the draft): -0.35 to -1.39 categories a week,
  $79-172 unspent (the edge list is mostly $8-21 players, and a predicted bargain often isn't one at the real
  price). Adopted rules for everyone plus the full max on targets: 0 to -0.07; plus 110% of max: -0.005 to -0.20.
  The max bid already is the focus: it buys whoever comes in under it.
- **Spending the leftover on 1-3 players: rejected (2026-10-03, `splash.py` -> `out/splash_*.txt`).** The adopted rules
  leave $47 unspent (46% of drafts $40+). The first 1-3 players the rules would buy (app $15+; the spot bar makes that
  $25+ early) bid at the full max, or at max + $20 or $40 split over them; 200 drafts x 6 rooms. Full max (no aim)
  -0.04 / -0.08 / -0.12 categories a week for 1 / 2 / 3, $33-24 unspent; max + $40 -0.23 / -0.41 / -0.55, $2-14
  unspent; max + $20 -0.14 to -0.37; the same from 40% of the draft -0.17 to -0.32; from 60% -0.01 to -0.02; from 75%
  0 (by then nobody worth $15+ is left to buy). Lost in every room. **Leftover money is the rules refusing to
  overpay; spending it buys worse value than what the late $1-3 spots return.**
- **Price enforcement: rejected (2026-10-03, `enforce.py` -> `out/enforce_*.txt`).** Before half-way, bid players the
  rules skip up to 0.8 / 1.0 / 1.2 x likely (likely $5+, no stars), so the winner pays our bid + $1; 200 drafts x 6
  rooms. -0.35 / -0.97 / -1.16 categories a week (1.0 until 30%: -0.62). We got stuck with 2.7 / 6.1 / 6.7 of them.
  **The drain doesn't show up**: the room's money left at 75% of the draft was $69-77 in every policy vs $73 (the room
  spends ~99% of its money either way, past rooms included, and buys other players with it), and the rules already buy 7.6 players after half-way
  at 0.33 x app $. No aim (full max from pick 1): -0.16, room $77 at 75%.
- **Hindsight search of the money-left drafts: no rule found (2026-10-03, `hindsight.py`, `hindsight_rules.py` ->
  `out/hindsight*.txt`).** 60 drafts (10 a room) that ended with $40+ unspent; each replayed with one change (win a
  player we lost at the room's price, or pass on one we bought; same random draws), the best kept, up to 3. Best path:
  6.92 -> 7.32 a week, $86 -> $38 unspent; 59 of 60 best first changes were winning one app $40-60 player (median 29% of
  the draft, paid 0.96 x app $ = 1.16 x max). Over all 5,047 "win him" changes only app $40-60 at up to 1.15 x max
  averaged positive (+0.12 to +0.18); stars past the max, anyone at 1.6x+ max and players under $15 lost. As live rules
  on 300 fresh drafts x 6 rooms (all drafts): $40-60 max = app $ -0.09 ($25 unspent), 0.95 x app $ -0.04, 1.1 x -0.25,
  $25-60 -0.19, from 20% of the draft -0.06, only when 1.5x richer than the room -0.05. **The hindsight gain is picking
  the one right player after the fact**; you can't tell a money-left draft in advance, and in the others the same bids
  cost. Real drafts agree: our $40-74 values delivered 0.84 of app $ (n=36), which is the 85% share.
- **A streaming 10th spot (2026-10-03, `stream.py` -> `out/stream.txt`).** 120 drafts (adopted rules, 20 a room), weekly
  model on the 2026-27 schedule: keep the best 9 and each week claim the free agent who adds most to that week (chosen
  on games and fit, not on who gets hurt) vs keep all 10. The 10th man by value is no $1 filler: app $ median 13.5
  (late picks are bargains). Free agents = the projection pool past the 160 drafted (pool 220). **Stream with first
  pick of the free agents: +0.15 a week (better in 96%); if the other teams' claims take the 15 best first: -0.04
  (28%).** Streamers are $1-4 players with 4 games that week (Larsson, Simons, Lopez, Huff, Robinson). Not modelled: the
  claim then can't go to a breakout (18 undrafted players finished top 100 in 2025-26) or an injury replacement, and
  free agents past the pool. **No draft change**: the money isn't short, and the 10th spot's value comes from the late
  bargains. Decide in-season by how hard the league claims; Weekly Pickups (`rank_moves`) ranks the weekly options.
- **Nine strong + a $1 flex: rejected (2026-10-03, `nine.py` -> `out/nine.txt`).** Hold the last spot for $1-2 and spread
  the money over 9 (spot bar, money per spot and cap on 9); variants with $15-60 maxes x1.1 or spot bar 1.0. 40 drafts a
  room x 6, same seeds. **The 9 don't get stronger**: app $ of the best 9 358 (adopted) vs 351-354, unspent $50 vs
  $38-57; x1.1 maxes spend more on the top 3 ($97 vs $87) for the same players. Vs adopted kept as 10: keep -0.09 to
  -0.12, stream (first pick of free agents) +0.10-0.12 vs adopted streaming +0.15, after 15 claimed by others -0.07 to
  -0.10 vs -0.04. The adopted rules already end with a strong 9 and a cheap 10th ($2.9 on average): prices, not money,
  limit the 9.
- **No IL: known absences capped at $1 (2026-10-03, `injured.py` -> `out/injured.txt`, `data/no_il.json`).** App $ prices a
  player out half the season at surplus x games / 82, as if a replacement held the spot; with no injury slot the spot is
  dead. Weekly model (whole-week absences, the slot stays empty): swap each player projected under 62 games for the
  weakest man on 45 rosters (5 best builds + 40 room-style teams) vs a typical healthy $1-2 player (+0.030 cats/wk;
  the best bench targets +0.135). Still worth it: Kawhi +.37, LaMelo +.28, AD +.22; Ingram, Kyrie, Porzingis +.10-.13;
  Embiid +.04; Kessler 0; Butler -.06, Mark Williams -.11, Lively -.15. **Only players injured now with a known absence
  (return month or 15+ games, `players.injured_*`) are capped** at $1 when below the bar (`draft_day.CAPS`, board
  `rule.caps`, tag "no IL: out till <month>"): a healthy player projected for fewer games may never get hurt, and a
  mid-season injury can be dropped, which the model can't do (owner's distinction). The room should skip them too
  (Fantrax ranks on totals: Butler 309, Williams 373): waiver stashes to claim a week or two before they return
  (1 claim a week).
- **Board since 2026-10-03**: max = max0 capped at my money less $1 per other open spot; the aim holds
  on the curve above (`AIM_FULL`, `AIM_POWER`; until 2026-10-03 85% until half-way, then the max); rows valued under the spot bar
  are dimmed and tagged "not a spot yet" until 80% (`SPOT_BAR` 1.25, `SPOT_BAR_UNTIL`); the strip shows "Others' top
  bid" (the most any other team can bid: one dollar over it wins anyone late) and the spot bar.
  Against the owner's 2025 habit (filling up early on mid-tier "bargains"): a **Pace** check (my spots
  filled vs the other teams' average, red at 3+ ahead, `PACE_AHEAD`; "don't chase" at 3+ behind past half, `PACE_BEHIND`), an **"early: room pays 1.7x"** tag on
  likely $5-25 players in the first 20% of the draft (`EARLY_UNTIL`, `EARLY_TIER`), and a **nominate** sort
  in the Bid header (undrafted players whose likely price is furthest past my max).

`draft_day.json` `notes` (from `draft_day.py`, up to five per player) are split by `sortNotes` on
their text, so keep these shapes when editing the script: `unpriced +X +Y` (A-TO, 3PM, TB: cheap and
worth winning, `draft_day.QUIET`; TS% and TF dropped 2026-10-03) becomes an amber dot on those heat cells and an amber underline on
the column header; `+X` / `-X` (categories at +/-1.5 z) and `57g` (projected games under 60) are
dropped because the heat cells and the GP column (projected games, amber under 60) already say it;
everything else is a tag under the name: other `bad` notes (under 41 games last season, new team)
in amber, the rest (star: wait for ~10% off / pass; the overpaid tier; one $60+ max; bench target;
30+ discount; young: room pays up) with the what-if max bids for second- and third-year players
(rocket = after a +2 z breakout; `yr 3` = third-years with their average +0.53 z projection miss
added back; `/api/fantasy` `what_if`, `player_stats.auction_value_at`; what-if only, no value changes).
Fantasy points stay hidden only in draft mode; dropping them for category leagues is a later job.
