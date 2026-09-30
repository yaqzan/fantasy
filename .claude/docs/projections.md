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
  win projections. Names match via `norm_name` + `NAME_ALIASES`.
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
  triple-doubles (scaled with points), technicals (last season's scan per minute + 1500 minutes
  of league rate). Owner adjustments apply last.
- **Stats basis `_proj`** (`player_stats._add_projections`): every rostered player with a line,
  rookies included; `GP_proj` >= 20 makes the scaling pool; ratios are not shrunk again. Once
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
- **Check a new source before blending it**: median per-game ratio to ESPN per stat and games.
  CBS 2026-27 came out at .84 points / 1.12 games (totals over too many games) and is in
  `NOT_BLENDED`; the others sit within ~7% (ESPN is the most optimistic, as in the backtests).
