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
  seasons by draft range. Backtest (fit before each target, 2023-24..2025-26, 9-cat per-game
  value rho): ESPN .840/.847/.800, ours .829/.842/.767, last season .823/.851/.769, blend
  .848/.852/.802.
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
  The `injured` flag (owner-set; 2026-10-01 from sourced reports, `out/injuries/`) only drives the
  healthy filter and lineups; the price uses projected games, which already carry those absences.
  Set it only for absences of ~10+ games or no timetable (it hides the player from the default
  rankings view); `players.injured_return` (month, or `season`) and `injured_games_to_miss` show in
  the tag as `INJ - Jan (45 missed)`. Unflagging in the app clears both.
- **Stats basis `_proj`** (`player_stats._add_projections`): every rostered player with a line,
  rookies included; `GP_proj` >= 20 makes the scaling pool, and only pool players get an auction $ (any timeframe:
  `ELIGIBLE{n}`; the rest show $1. A model-only line on 67 career minutes had priced at $18); ratios are not shrunk again. Once
  his games this season are loaded (`api_updated_at` after opening night), each stat fades:
  (projection x 12 + actual total) / (12 + games). Pre-season the UI defaults to it.
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
