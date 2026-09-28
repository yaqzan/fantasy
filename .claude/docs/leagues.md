# Leagues

Every league-specific thing (rules, teams, rosters, undroppable flags, schedule, your team) belongs
to a league. NBA data (players, games, standings, injuries, daily stats) is shared by all leagues.

- **Storage.** `leagues` table: `id` (slug), `name`, `settings` (JSON), `is_active`.
  `leagues.py` owns the schema: `DEFAULT_SETTINGS` lists every key, `validate_settings` merges onto
  it, `LeagueConfig` is what the stats code receives. `fantasy_teams.league_id` scopes teams;
  team names are unique per league, not globally. `league_player_flags` holds per-league
  `undroppable`. `Player.injured` stays NBA-wide.
- **Which league a request is about.** `X-League` header (the frontend's switcher, stored in
  localStorage `fantasy.league`), else `?league=`, else the active league. Switching in the UI
  also activates the league, so CLI scripts (`lineup_optimizer.py`, default `--league`) follow
  the last pick. Every league-scoped query must filter by league (`league_team_ids`,
  `get_team_by_abv`); draft/undraft only touch the current league's teams, so one player can be
  on a team in each league.
- **Categories.** `CATEGORY_CATALOG` in `leagues.py`: key, label, `inverse` (lower wins), `kind`.
  Adding a category = a per-player per-period stat in `player_stats.load_player_stats` (keys
  `CAT`, `CAT_5`, `CAT_10`, `CAT_projected`) + a catalog entry; `calculate_team_totals` sums
  counting stats generically and special-cases ratios and `WIN%`.
  - `BLKA` (times blocked): `leaguedashplayerstats` (the game logs lack it); its last-N filter is
    the team's last N games, an approximation.
  - `TECH`: play-by-play scan, `pull_technical_fouls.py`, one fetch per game ever
    (`pbp_scanned_games`). Counts `Foul` actions whose subType contains "Technical" by players
    (coach/team techs and defensive 3 seconds drop out). Unscanned games count 0.
  - `WIN%` ("Wins"): per player, wins per game played (game log `WL`), falling back to team win %
    before player wins exist. In a week projection a player's wins are the summed log5 chances
    of his team winning each game he is active for (`week_schedule`, team win % from standings).
- **Daily vs weekly lineups** (`roster.daily_lineups`). Weekly: the optimizer picks `active`
  starters from the healthy roster, position minimums apply, every game counts. Daily: each day
  only the best `active` players (by the timeframe's Z-SCORE) whose team plays count
  (`player_week_games`); the optimizer "lineup" is the whole roster (`lineup_size` =
  roster size), injured players hold a spot and score nothing, and a pickup means choosing a drop.
  Opponents are modelled the same way.
- **Auction values** split `num_teams x budget` over `num_teams x roster.size` players.
- **Schedule.** `[[week start, opponent abbreviation], ...]`; a week ends the day before the next
  starts (last week: 7 days). Empty schedule: Monday-Sunday weeks, no opponent, the optimizer
  answers 422 with a message. "Fill weeks from NBA calendar" (`/api/leagues/generate-weeks`) makes
  opening day + every Monday from the stored NBA schedule, opponents blank.
- **Upgrade from the single-league app.** `init_db.py` adds the columns/tables and imports teams
  with no league as `league-2025-26`, with the rules `fantasy_config.py` used to hard-code and
  `league.json`'s `my_team`/`schedule`. `league.json` is no longer read.
