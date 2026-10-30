# Projections

This season's projections: players (the `_proj` stats basis, "2026-27 projection" in the UI) and
team wins (`team_strength`). NBA-wide, shared by every league.

- **Data.** `player_seasons` (history, `pull_history.py`, one nba_api call per season);
  `player_projections` (one row per season x source x player, per-game line + games);
  `team_projections` (season x source x team wins; source `owner` holds the owner's +/- wins);
  `projection_adjustments` (owner: `production` factor, `games` override). Third-party numbers
  live only in MySQL; the research CSVs they came from stay out of the public repo.
- **Sources.** `pull_projections.py`: `espn` (ESPN's unofficial fantasy API; a row with games
  but no stat line is not a projection, a missing stat otherwise means 0) and `model`
  (`projection_model.py`). `import_projections.py players <csv> --source X` for others
  (FantasyPros, CBS, FanScout, RotoWire, a rookie survey with `--by-player`); `teams <csv>` for
  win projections. Names match via `norm_name` + `NAME_ALIASES`. `pull_fantrax.py projections
  --league <this season's Fantrax league>`: Fantrax's own projections (source `fantrax`, scale
  like the other experts); it needs the owner's saved login (`fantraxloggedin.cookie`, made from
  their Firefox session with browser_cookie3; the permission rule for it is in the gitignored
  `.claude/settings.local.json`). Fantrax projects no technicals or double-doubles (all 0) and has
  no times-blocked stat.
- **Our model** (`projection_model.py`): last 3 seasons 5/4/3 by minutes + 800 minutes of league
  average, a one-year age factor (delta method, seasons before the target only); players
  entering year 2-3 use last season only + experience curves; rookies = past picks' first
  seasons by draft range; then an **age calibration** (2026-10-16, below). Backtest (fit before each target, 2023-24..2025-26, 9-cat per-game
  value rho): ESPN .840/.847/.800, ours .829/.842/.767, last season .823/.851/.769, blend
  .848/.852/.802.
- **Audit 2026-10-16** (`audit.py` -> `out/audit.md`, `calib.py`, `breakout_shape.py` in the `.horizon` driver;
  players with 20+ games; ours 2015-16..2025-26, ESPN/blend on 2020-21, 2021-22, 2023-24..2025-26, n=1,613).
  - Per game, blend vs ESPN vs ours (MAE): PTS 2.38/2.49/2.58, REB .83/.86/.90, AST .65/.65/.71, STL .18/.19/.19,
    BLK .16/.17/.15, 3PM .36/.37/.38, TOV .33/.34/.35, FG% 2.9/2.9/2.9 pts, FT% 4.0/4.1/4.0 pts, FPTS 4.87/5.05/5.31,
    9-cat value 1.56/1.62/1.64 z. The blend beats every source on every stat but blocks (ours). ESPN runs high:
    PTS +0.8, minutes +1.5, games +9.4, FPTS +1.6 a game; ours +0.2/+0.5/+1.3/+0.4. Everyone under-projects FT% by ~.3.
  - **Biggest miss: minutes.** Players whose minutes then rose 6+ were under-projected by 2.2 z (blend; -7 FPTS a
    game), down 6+ over by 2.5 z (+9 FPTS). That's half the error and nothing in the history predicts it.
  - **Systematic: age.** Before the fix, the blend over-projected 32+ by +0.81 z / +3.0 FPTS a game and <=24 by
    -0.01 / +0.14, in every season (ours alone in all 11, ESPN in all 5). By NBA year: rookies +0.84 z (ESPN +1.09,
    ours -0.46), year 2 -0.10, 3 -0.24, 8+ +0.6. Team changers +0.81 (inflated: "changed" is read off the final
    team, so mid-season trades count). Injury-short last season (<= 40 games) +0.45 vs +0.10 on 61+.
    Games by age: flat (+6 to +8 at every age), so no games fix.
  - **Adopted: age calibration in our model** (`projection_model.age_calibration`): per age (pooled +-1), actual /
    projected per-game sums of the model's own last 6 seasons, relative to all ages, pooled with 100 player-seasons
    of 1.0; scales per-game stats and minutes, rookies untouched. Out of sample on the blend (season-demeaned
    MAE, what ranks and $ feel): 9-cat 1.547 -> 1.538 z (90% bootstrap -.014 to -.004), WSOP-8 1.960 -> 1.946,
    FPTS 4.791 -> 4.764 (-.042 to -.011), Spearman .812 -> .814 / .849 -> .851; 32+ bias +2.96 -> +2.27 FPTS. Small
    because minutes changes dominate the error. On 2026-27 it moved top-150 ranks 2.3 on average (max 13) and $
    under $1.
  - Rejected: calibrating the final blend by age (leave one season out or forward) or both layers: same gain or
    less, and it pushes the young up. A games correction by age: no age pattern. Rookie weight: too few rookies
    with 20+ games and an ESPN line (80) to refit; `source_weights.py` already found the per-type weights tie.
- **Blend** (`projections.player_lines`): experts averaged stat by stat, then
  `EXPERT_WEIGHT` by player type (rookie .9, year 2-3 .9, other .7, age 32+ .6, changed team .5)
  vs our model: fit on 2024-25/2025-26 with ESPN + FantasyPros, the experts with a past.
  Experts overrate team changers and veterans; averaging experts beat ESPN alone. Stats no
  expert projects: times blocked (our BLKA per shot x blended FGA), fouls (per minute), double/
  triple-doubles (scaled with points), technicals (per minute over the last 3 seasons, 5/4/3,
  + 300 minutes of league rate; counts from Fantrax, `pull_fantrax.py techs`, since Fantrax scores
  the category; two seasons predicted the next better than one, a heavier prior did worse).
  Owner adjustments apply last.
- **Would other weights be more accurate? Tested 2026-09-30: no, keep the blend as is.**
  (`source_weights.py` -> `out/source_weights.md` in the `.horizon` driver; out of sample, ESPN
  2021-22 and 2023-24..2025-26, FantasyPros 2024-25/2025-26.)
  - Experts miss the same players: error correlation ESPN-FantasyPros .93 (value), .96 (games);
    each with our model .83-.91. Reweighting can't fix what all of them miss.
  - ESPN vs FantasyPros: best FantasyPros share .7-.8 in both seasons, but it saves .013 of 1.37
    value MAE over equal weights (90% range .001-.032). FantasyPros is clearly better only on team
    changers (1.43 vs 1.73).
  - Experts vs our model: any expert share from .5 to .7 scores within 0.5% (WSOP-8 and 9-cat,
    4 seasons, leave one season out); one weight for everyone, per-type weights and the live
    table tie. ESPN alone is 3% worse, our model alone 5%. The per-type direction holds (team
    changers and 32+ want more model, rookies more expert).
  - By component the best expert share is ~.4 for games, ~.65 for minutes, ~.3 for per-minute
    production (curves flat); splitting the weight that way gains 1-2% on season value, not
    consistent by season. Not adopted.
  - **Projected games run high: experts by ~10, our model by ~3** (top 150: ESPN 70, ours 62,
    played 59; players who missed the season count as 0). Delivered share of projected games
    (`games_haircut.py` -> `out/games_haircut.md`, top 250 x 4 seasons): **.86 overall, .84-.90
    in every value-rank band and every age band, so ranks and $ don't move.** Not uniform on
    injury history: under 41 games last season delivers .78, projected under 55 games .64, 66+
    games last season .89. By season .84-.91 (the top 15 alone swung .77-1.12).
    **It is an average, not a forecast for one player**: ~17% of the top 250 play under 41 games
    and the rest land near their projection, so multiplying a player's games by .88 predicts him
    no better (games MAE 14.2 vs 13.9 as projected; age, last season's games and regression lines
    don't help either; sd around any line ~18 games). Use it as an availability rate (weekly
    model: x .88, x .78 after a season under 41 games), not as "he plays 58". Per-game value needs no
    shrink: actual = -0.7 + 1.02 x projected (top 150), the top 5 projected delivered in full.
  - Fantrax, FanScout and RotoWire can't be scored: Fantrax and Sleeper (RotoWire) overwrite a
    past season's stored projections with actuals, and ESPN's stored 2022-23 set is a mid-season
    one (~40 games a player; never backtest on it). Hashtag Basketball's Wayback pages hold the
    top 30 only. Untested sources stay at equal weight; dropping any one moves the 140 drafted
    players $0.7-1.3 on average (`pricing_check.py`, auction `.horizon`).
- **Breakouts by NBA year** (`breakout_by_year.py` -> `out/breakout_by_year.md`; 2,834 season pairs
  2012-13..2025-26, WSOP-8 per-game value, breakout = +2 z): the biggest jump is into **year 2**
  (+0.84 z, 32% break out), then year 3 (+0.52, 28%), flat from year 4 (+0.13, 22%), falling from
  year 6. But **projections miss year 3 the most**: the blend under-projects players entering year 3
  by 0.53 z (ESPN -0.54, ours -0.42; n=132), year 2 by 0.08, and over-projects year 6+ by 0.76.
  About $3 at $6 a z in the middle of the board. **Not applied in code: it fails out of sample.**
  Year-3 bias by season -0.01, -0.34, -1.11, -0.69 (se .25 overall); adding the other seasons'
  bias makes year-3 error worse (MAE 2.23 -> 2.26); among draftable year-3 players (projected
  value above the ~110th player) the bias is -0.21 (n=33). An owner adjustment (`production`) is
  the place for a view on one player.
- **Breakout lines** (2026-10-16, `breakout_shape.py` -> `out/breakout_shape.md`): what a +2 z year-2/3 breakout
  looks like stat by stat (286 cases, per game after / before): minutes x1.32, PTS x1.52, AST x1.52, 3PM x1.60,
  STL x1.39, REB x1.35, BLK x1.32, TOV x1.35; FG% .445 -> .467, FT% .739 -> .772. Per minute it is usage (PTS, AST,
  3PM, FTA +17-21%), not boards or blocks (+1-3%). A z of WSOP-8 value came with 2.41 FPTS a game (Yahoo weights).
  `player_stats._what_if` scales a year-2/3 player's projection along that shape (multiplier ** t), t solved so his
  value in the league rises by `BREAKOUT_Z` (2) or, for third-years, `YEAR3_BIAS_Z` (.53); in a points league by
  that x `FPTS_PER_Z` fantasy points (+4.8 a game for a breakout). `what_if` on `/api/fantasy` and
  `/api/projections/players`: `{breakout: $, corrected: $, lines: {proj, breakout, corrected}}`; the Projections
  tab shows the lines (click a player, or "Year 2-3 only"), the auction board the $ tags, the points draft board a
  "🚀 FPTS/g · #rank" tag (breakout FPTS a game and the season-value rank it would earn; hover: projection, breakout and,
  for third-years, average-year-3 lines with their ranks).
- **Web breakout / MIP reports vs ours (checked 2026-10-03):** the summer's role changes (trades,
  new starters) are already in the expert lines' minutes, so a breakout list adds narrative, not
  information. MIP rewards a points jump; our value is per-game category z, so a scorer who leaps on
  poor efficiency (the usual MIP long shot) barely moves a price. No systematic adjustment; a view on
  one player is an owner `production` factor.
- **Team-changer typing maps history abbreviations** (`NBA_TO_TEAMS_ABV`: BKN/CHA/PHX -> BRK/CHO/PHO).
  Before 2026-10-03 every returning Net, Hornet and Sun was weighted as a team changer; fixing it
  moved 18 players' type and at most $1.
- **Auction $ on the projection are games-weighted** (2026-10-01): surplus over replacement x
  projected games / 82, so a known absence (ACL return in January) is priced. 4-season backtest of
  the blend ($ of delivered season value, top 140): error 9.37 per game only -> 9.05 weighted (better
  in 3 of 4 seasons, level in the other); players projected under 55 games were $17 overpriced, now $10. Weighting
  only the under-55 group gives 9.15. Ranks and z stay per game. On 2026-27 it moves the 140 drafted
  players $1.6 on average, 9 by $5+ (the long absences down $5-12, the two most durable stars up $5-9).
  Injured is Yahoo's Out status (`players.injury_status` O/INJ, hourly `pull_yahoo sync`); there is no hand flag. It drives the healthy filter and lineups; the price uses projected games, which already carry those absences. `players.injured_return` (month, or `season`) and `injured_games_to_miss` are still set by hand in the DB and show in the tag as `INJ - Jan (45 missed)` while he is Out; the stats pull zeroes the games when he plays.
- **Stats basis `_proj`** (`player_stats._add_projections`): every rostered player with a line,
  rookies included; `GP_proj` >= 20 makes the scaling pool, and only pool players get an auction $ (any timeframe:
  `ELIGIBLE{n}`; the rest show $1. A model-only line on 67 career minutes had priced at $18); ratios are not shrunk again. Once
  his games this season are loaded (`api_updated_at` after opening night), `_projected` updates it (below);
  `_proj` is the line as it is.
- **Team wins** (`team_projection_index`, `team_strength`): sources weighted by past accuracy
  (`TEAM_SOURCE_WEIGHT`: Vegas .41, ESPN summer panel .30, Bleacher .29; no track record = 0).
  Vegas has been off by 6.5 wins a team over 13 seasons, the rest slightly worse. Strength =
  (wins + 20 x projected %) / (games + 20) once this season's record exists
  (`teams.record_season`; `pull_standings` stores it from game 1). Used by Wins (per game) and
  every game's log5 chance.
- **Owner adjustments** (Projections tab): `GET/PUT /api/projections/teams` (per-team +/- wins,
  stored as source `owner`), `GET /api/projections/players` (blended line, every source's line,
  this league's projection rank and $), `PUT /api/projections/players/<id>` (`production` factor
  on counting stats and minutes, `games` override; 1.0 and no games deletes the row).
- **Yearly refresh** (before a draft; the season label flips July 1): `pull_api_data.py --rosters
  --season <new>` (summer moves, rookies), `pull_history.py` (adds the season just finished),
  `pull_projections.py`, `pull_fantrax.py projections --league <a new-season Fantrax league>` and
  `techs --seasons <last three>`, then any research CSVs through `import_projections.py`
  (players per source; `teams` for win projections). Recheck `EXPERT_WEIGHT` and
  `TEAM_SOURCE_WEIGHT` once a season's preseason numbers can be scored against what happened.
  The backtest scripts (ESPN vs model vs last season, per-type weights, expert averages, team-win
  accuracy) live outside the repo, in this machine's `.horizon/projections-2026-27/driver`.
- **Fantrax's own player ranking (`Rk`/`Score` in `getPlayerStats`, projection view) vs ours**
  (WSOP 2026-27, checked 2026-10-02, top 400 by our `overall_rank_proj`):
  - **Calibrated to the league's categories in the header only**: columns are TS%, 3PTM, NFT, PTS,
    REB, A-TO, ST, BLK, TF, BLKD, W (the same 11). Displayed NFT and A-TO equal 2*FTM-FTA and AST-TOV
    from the stored Fantrax line (r .998/.999). But **TF, BLKD and W are 0 for every player**, so the
    Score ranks on 8 of 11 categories. It also isn't an equal-weight z-sum of those 8: best fit
    R2 .81 per game, .89 on season totals (games count), PTS weighted ~2x the others and TS% ~0 or
    negative. Don't treat `Score` as a reference for our value.
  - Rank agreement with ours: Spearman .80 (top 100 overlap 64, top 150 109). Our value without W/TB/TF
    against Fantrax: .88 (top 100 overlap 74). So the three categories Fantrax zeroes explain about
    half the gap; the rest is Fantrax's Score formula and its games (it ranks on totals, so players with
    a short projected season sink: Fantrax gp 20-25 vs ours 28-42 for the injured). Rank gap vs
    W+TB+TF z-sum r .44.
  - Direction: Fantrax over-ranks high-usage scorers who are blocked a lot and play for weak teams
    (our TB and W cost them 2-3 z) and under-ranks low-usage defensive bigs and wings on good teams.
  - Name collisions: Fantrax lists two players under one name (two Jalen Johnsons, two Jaylin
    Williamses); join on team too or keep the better rank, or a scrub's row overwrites the starter's.
- **Check a new source before blending it**: median per-game ratio to ESPN per stat and games.
  CBS 2026-27 came out at .84 points / 1.12 games (totals over too many games) and is in
  `NOT_BLENDED`; the others sit within ~7% (ESPN is the most optimistic, as in the backtests).
- **In-season update (2026-10-24; `inseason.py`, backtest `.horizon/preseason-2026/inseason.py` + `inseason_rank.py`,
  logs `data/rs_*.csv`, `fetch_rs.py`).** `_projected`, THE projection (the one stats choice besides Season / Last 10 / Last 5), per stat per game:
  `(K x prior + games + R x last-10 games) / (K + n + R x n10)`; prior = the blended line moved by his preseason games.
  Before: one K=12 for every stat, no recency, minutes never updated, plus a separate "Recent form" (half season, half last 10,
  no prior) that was the default once games existed: on 2-3 games it made Davion Mitchell a +0.55 pickup against +0.06
  on the projection. K, R fit 2016-2022 (prior = `project_season` + `preseason.adjust`, checkpoints after 5/10/20/30 games, error on his
  REST-of-season per-game stat, players projected 15+ MPG, weighted by games left), scored on 2023-2025 (12,354 rows):
  | | MIN | PTS | REB | AST | STL | BLK | 3PM | TOV | FGA | FGM | FTA | FTM |
  |---|---|---|---|---|---|---|---|---|---|---|---|---|
  | K (games) | 16 | 12 | 16 | 12 | 32 | 32 | 16 | 16 | 16 | 16 | 16 | 16 |
  | R | 2 | 1 | 1 | 1 | 0 | .5 | .5 | .5 | 2 | 1 | .5 | .5 |
  BLKA / PF / DD / TD / TECH borrow a neighbour's (`inseason.FOLLOW`). Minutes now update too (game lines).
  Out of sample error (MSE / variance of the stat) vs prior only / old K=12 / recent form: PTS .155 / .244 / .157 / .230, REB .156,
  AST .152, MIN .260 / .454 / .275 / .358, FGA .148 / .259 / .157 / .197, STL .373 / .450 / .400 / .916. Fitted beats
  K=12 by 0-2% on PTS REB AST 3PM TOV FTA, 4-7% on MIN FGA STL BLK; recent form is 25-59% WORSE than the fitted blend and
  worse than the prior alone on REB, STL, BLK, 3PM, TOV, FTA. By games played (mean over stats): 5 g prior .269, K12 .217, form .500,
  fitted .211; 10 g .280 / .203 / .335 / .200; 20 g .300 / .194 / .266 / .187. **Ranking** (composite z of PTS REB AST STL BLK 3PM TOV,
  Spearman with rest-of-season, 2023-25 mean): after 5 games prior .806, form .775, K12 .853, fitted .857; 10 g .798 / .821 / .861 / .863;
  20 g .782 / .844 / .867 / .871; of the real top 30 found: 18 / 18 / 20 / 21 (5 g). So the gain over the old blend is small and
  consistent; the big fix is dropping "recent form" and the prior-less default. R is real but modest: R=1 (the last 10 count double) is
  the optimum for volume stats, 0 for steals. The backtest prior is our model alone, so the live prior (experts blended in) is a little better and
  would want a slightly higher K. Re-fit when a season of live games is in. A first-game call-up has no
  prior of his own (no line): he sits outside the pool.
- **Week-1 check (2026-10-25, `.horizon/week1-review/bias.py`, 242 players 2+ games, projected 18+ MPG, 4 days).** League-wide
  scoring ran under the model line: PTS -9%, 3PM -12%, AST -10%, FGA -9%, MIN -5%; TOV +9%, STL +8%, FTA +7%. A level shift
  hits every roster alike (H2H unaffected); the in-season blend already closes half of it (PTS -5%). Too short to retune K/R:
  the backtest above still says heavier weight on a few games is worse. Role changes (a teammate's long injury) are what the
  blend can't see: use the owner's `ProjectionAdjustment` (Projections tab, `production` x), e.g. +18% for the next man up.
- **Preseason signal (backtest 2026-10-17, `.horizon/preseason-2026/`: `backtest.py`, `holdout.py`).** In the app
  as step one of the `'_projected'` timeframe (`preseason.py` holds the constants below; the in-season update, next entry,
  runs on top; there is no separate preseason stats choice any more). Players projected 32+ MPG keep their minutes (below). Lines: `game_log.store_preseason` -> `preseason_lines` (every
  `pull_api_data.py` full pull, one call; minutes clamped at 0: the NBA log had a -4).
  stats.nba.com `LeagueGameLog` `Pre Season` has every season (one call each; 2019-20's also holds the July 2020
  bubble scrimmages: keep 45 days from the first game). 4,285 player-seasons 2013-14..2025-26 (500+ regular-season
  minutes), baseline = `project_season` fit before each target. Update: `rate = proj + m/(m+k) x (pre/(1+offset) - proj)`,
  m = preseason minutes (attempts for FG%/FT%). Preseason runs hot, so the offset comes off first: TOV +28-32%,
  FTA +24-30%, STL +20%, vet 3PM +14%, the rest +2-9%; FG%/FT% -0.6 to -0.9 points. k (minutes) by NBA year:
  | | PTS | REB | AST | STL | BLK | 3PM | TOV | FGA | FTA | FG% (att) | FT% (att) |
  |---|---|---|---|---|---|---|---|---|---|---|---|
  | years 1-3 | 200 | 120 | 120 | 500 | 190 | 180 | 300 | 130 | 300 | 170 | 70 |
  | year 4+ | 350 | 450 | 300 | 1400 | 800 | 350 | 650 | 250 | 550 | 550 | 160 |
  A young player's 100 preseason minutes move his REB/AST projection ~45% of the way; a veteran's ~18% (STL ~7%).
  Out of sample (fit 2013-20, scored 2021-25) the error removed vs the projection alone: young REB 35%, AST 30%,
  BLK 27%, FGA 23%, PTS 20%, 3PM 20%, TOV 12%, FG% 7%, STL 5%; veterans 2-16% (FGA 16, AST 11, REB 12, PTS 9, STL/BLK/FG% 2-3).
  Minutes: preseason MPG is not the role: starters play 8-11 fewer (projected 32+: -11.2), deep bench +5. Against
  the expected preseason MPG (13.3 + 0.31 x projected MPG) the surprise carries g/(g+5) games' weight and removes
  8% of the minutes error out of sample (young 7%, vets 9%); weakest part, and a star resting looks like a role loss.
  **In fantasy points** (`eval_fpts.py`, default weights, constants fit 2013-20, scored 2021-25, top 150 by the
  baseline, 500+ min players): vs our model FPTS/g RMSE 6.64 -> 6.39, Spearman .788 -> .80; vs ESPN's preseason
  projection (2020-21, 2023-24..2025-26) 6.14 -> 5.63, .816 -> .836, better in every season. Where the update reorders
  two players it is right 58-60% of the time: a tiebreaker inside a tier, not a reshuffle. Rates only (no minutes)
  gains about half. **By draft range** (`eval_cutoff.py`): ranks 60-250 gain most from the minutes part (RMSE -0.5,
  60-65% of reorders right); in the top 60 a rested star's minutes are noise: exempting players projected 32+ MPG
  is best vs ESPN (top 60: -0.50, 64% right; none exempt: -0.33, 54%) and keeps the gain below rank 60. **Top 30:**
  preseason doesn't help (vs ours RMSE +0.18, reorders ~coin flip): don't let it reorder the first ~30 picks.
