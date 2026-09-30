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
- Output: `out/f2026.csv` (per player: our $, market $, edge, category z). Biggest projected gaps
  (our $ vs likely market $): buy Kawhi, Haliburton, Curry, Holmgren, Derrick White, Reaves, Lillard,
  Paul George (market pays $15-27 less than value); fade Cade Cunningham (-55), Giannis (-28),
  Doncic (-25), Edwards (-25), Banchero (-30), Jaylen Brown, Sengun, Trae Young, Flagg.

## Return by price tier (another session, 2025 auction graded on 2025-26 finishes)
| Price | Players | Return per $1 | Median finish |
|---|---|---|---|
| $75+ | 5 | 0.89 | #4 |
| $40-74 | 14 | **0.70 (worst)** | #30 |
| $25-39 | 20 | 0.82 | #38 |
| $15-24 | 30 | 0.91 | #60 |
| $8-14 | 23 | **1.22** | #86 |
| $3-7 | 22 | 1.30 | #131 |
| $1-2 | 34 | 3.18 (21 of 34 busts) | #198 |
Stars hold value; the $40-74 tier is where this room burns money (Trae $51, Sengun $44, AD $58,
Giannis $75). 18 undrafted players finished top 100, but only 1 waiver claim a week.
Its source was the session "Fantasy auction draft bidding analysis"; target list `.archive/draft-2026-targets.csv`.

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
- Bench = 4 x $1 (only 1 waiver claim a week), so actives share ~$196.
- The app's auction $ price a 140-player pool (`num_teams x roster.size`). Pricing for the 84
  actives instead: the top 14 rise ~$30 each (Jokic 100 -> 159, SGA 165 uncapped), ranks 15-40
  +$6, everyone ranked 41+ loses $5-10. Not applied in the app (owner's call; see kanban).
- No positions: the center premium above is gone, so don't price bigs up.

## Build results (`strategy.py`, `out/strategy.txt`)
Anchor star at likely $105 (Giannis $81), five complements under $40 each, expected categories won
vs random budget teams (projected games scale each player's z; no weekly noise):
- Jokic 7.7: covers A-TO, REB, TS%, NFT, PTS; open: BLK, 3PM, TF, TB, W. Fill with BLK/W bigs
  (Holmgren, Mobley, Hartenstein), 3PM/TB wings (White, Murphy), shooters (Curry, Lillard).
- SGA 7.8: concedes REB (.12); needs REB/BLK bigs (Adebayo, Mobley, Towns, Hartenstein, Poeltl).
- Wemby 7.6: concedes REB/PTS; needs guards with A-TO, STL, 3PM (Haliburton, Quickley, Murray, Reaves).
- Luka 7.4: TF z -2.8 and BLK conceded; fill with BLK bigs; the weakest anchor.
- Giannis 7.5: REB conceded, 3PM -1.2, TB -1.6.
- **No star, nobody over $45: 8.1; any six: 8.2.** Balanced $20-45 teams score ~0.4-0.6 cats above
  one-star builds in this model.

**Unresolved conflict.** The tier grade says stars hold value and $25-39 returned 0.82; the build
model likes $20-45 players and says a star costs ~0.5 categories. Model error on the $ side is
larger than the gap. Where both agree: **cheap to lower-middle ($8-25) players with 65+ projected
games and value in categories the room doesn't price (A-TO, 3PM, TS%, TB, TF, W)**, e.g. White,
Reaves, Lillard, Paul George, Markkanen, Vassell, Hartenstein, Quickley, Murphy. Fade the $40-74
tier unless the price falls below value. Decide star vs balanced at the draft from what the room
actually does to prices. Investigation: kanban "Reconcile Star Vs Balanced Draft Strategy".

## Caveats
- Market z use last season's stats; 2026 z use blended projections. Rookies have no prior.
- TB and TF projections are our model's (per shot / per minute); Fantrax projects neither.
- Build search compares against random budget teams, not real opponents; weekly noise, injuries
  beyond the games scaling, and the 1-claim waiver limit are not modelled
  (see kanban "Punt Strategy From Matchup Simulation").
- Dollar gaps under ~$15 and any single-player "steal" are within model error.
- Rerun after projection edits (owner adjustments live in MySQL): `apply2026.py`, `pairs.py`,
  `strategy.py`, in that order from the repo root.
