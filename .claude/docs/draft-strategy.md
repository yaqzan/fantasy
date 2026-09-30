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
  #5 $75) in the weekly model; the other three fall $10-40 short. Per-star numbers: `out/player_notes.md`. Past the break-even each $10 costs
  ~0.08 categories a week. **Never two $60+ players** (worst structure in 2025, no better in 2024).
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
  `pairs.py`, `strategy.py`, then `builds_z.py`, `builds_week.py`, `bench.py`, `breakeven.py`,
  `draft_day.py`.

## Draft Day tab (`/draft`)
The app's cheat sheet: steps, diagrams, star break-evens, a max-bid lookup, bench targets. It reads
`/api/draft-day`, which serves a gitignored `draft_day.json` (repo root) written by
`.horizon/wsop-auction-2026/draft_day.py`; without the file the tab shows the 404 message. The page
is public (owner's choice, 2026-09-30); the player data stays out of git.

**Draft mode** (header toggle, per league in localStorage): on by default for an auction league until
6 hours past `draft.date`. It hides the in-season tabs (lineups, pickups, daily stats, standings),
the trend and fantasy-points columns, and the position filter when the league has no position
minimums. When `draft_day.json`'s `league` is the selected league, Player Rankings adds **Likely**
and **Max bid**. Max bid follows the Value column (so the stats basis and star-premium slider move
it) by the file's `rule`: stars at their break-even, else Value x 0.85 ($40+) / 0.80 ($15-39) / 1.0.
Fantasy points stay hidden only in draft mode; dropping them for category leagues is a later job.
