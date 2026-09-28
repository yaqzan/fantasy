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
- **Categories.** `CATEGORY_CATALOG` in `leagues.py`: key, label, `inverse` (lower wins), `kind`;
  ratios also carry `attempts` (per-game attempts formula) and `prior` (shrinkage strength in
  attempts, method of moments on 2025-26). Adding a category = a per-player per-period stat in
  `player_stats.load_player_stats` (keys `CAT`, `CAT_5`, `CAT_10`, `CAT_projected`) + a catalog
  entry; `calculate_team_totals` sums counting stats generically and special-cases ratios and
  `WIN%`.
  - `BLKA` (times blocked): `leaguedashplayerstats` (the game logs lack it); its last-N filter is
    the team's last N games, an approximation.
  - `TECH`: play-by-play scan, `pull_technical_fouls.py`, one fetch per game ever
    (`pbp_scanned_games`). Counts `Foul` actions whose subType contains "Technical" by players
    (coach/team techs and defensive 3 seconds drop out). Unscanned games count 0.
  - `WIN%` ("Wins"): per player, wins per game played (game log `WL`). Before the season's
    first game (`is_preseason`) and before player wins exist: his current team's win %, since
    his wins came with last season's team (Anthony Davis: Dallas-era .500, Washington .207).
    In a week projection a player's wins are the summed log5 chances of his team winning each
    game he is active for (`week_schedule`, team win % from standings).
- **Daily vs weekly lineups** (`roster.daily_lineups`). Weekly: the optimizer picks `active`
  starters from the healthy roster, position minimums apply, every game counts. Daily: each day
  only the best `active` players (by the timeframe's Z-SCORE) whose team plays count
  (`player_week_games`); the optimizer "lineup" is the whole roster (`lineup_size` =
  roster size), injured players hold a spot and score nothing, and a pickup means choosing a drop.
  Opponents are modelled the same way.
- **Weekly matchup model** (`team_week_totals`, `category_win_chances`): a team's weekly totals,
  each with a variance from per-game noise (catalog `noise`: variance per game = coef x the
  player's per-game stat; `attempt_sd` for ratios; wins are coin flips at each game's log5
  chance). The constants come from the 2025-26 game logs: points swing 3.4x their mean,
  most counting stats 1-1.5x. P(win a category) is normal on the difference.
- **Weekly pickups** (`get_pickup_candidates`, `/api/pickups`, the Weekly Pickups tab): for each
  of the 150 best free agents whose team plays that week, every possible drop (or an open spot)
  is tried and the gain is the change in expected categories won. Only games he'd play count
  (daily leagues: days he makes the best `active`). The opponent is the week's opponent once its
  roster is in, else the league's average rostered team, else a copy of my team (even match).
- **Team Standings** is a power ranking, not the league's real standings. `view=per_game`: one
  game each of every team's `best_starters` (best `active` by Z-SCORE, position minimums met;
  exact because each player has one position). `view=week`: the current fantasy week through
  `player_week_games`. Injured players are left out unless `healthy_only=false`.
- **Player value** (`calculate_overall_scores`): per category, a z-score of the per-game value
  against the draftable pool (`num_teams x roster.size`, re-ranked 3 times from the qualified
  players), capped at ±3, then summed (`VALUE`; `Z-VALUE` without punted categories). Ratios are
  scored as impact, attempts per game x (rate shrunk by `prior` - pool rate). Display scores are
  0-100 with 50 = the average drafted player: per category 0/100 = ∓3 SD, overall (`SCORE`,
  `Z-SCORE`, the UI's OVR) 10 points per SD of value among drafted players. Don't reintroduce min/max scaling
  (garbage-time players set the scale) or a logistic squash (it priced specialists like Gobert
  64 spots too low); both were tried 2026-09.
- **Auction values** (`calculate_auction_values`): value over replacement. Each drafted player
  (`num_teams x roster.size`) costs $1; the rest of `num_teams x budget` goes by (value -
  first undrafted player's value) ^ `draft.price_exponent`, rounded to whole dollars that add up
  to the budget. `/api/fantasy` prices every timeframe (`auction_value_<period>`) so the table's
  $ always sits on the same stats as its rank; before a league's first week the UI defaults to
  the full season (`config.default_stat_type`), after it to the projection. Players under
  `games_floor` are flagged `small_sample`. Fit the exponent to the league's past auction prices by rank (least squares
  over the drafted players); the owner's league stores its fit (a gitignored
  `draft_history_price_curve.json` holds the price curve it came from).
- **Schedule.** `[[week start, opponent abbreviation], ...]`; a week ends the day before the next
  starts (last week: 7 days). Empty schedule: Monday-Sunday weeks, no opponent, the optimizer
  answers 422 with a message. "Fill weeks from NBA calendar" (`/api/leagues/generate-weeks`) makes
  opening day + every Monday from the stored NBA schedule, opponents blank.
- **Upgrade from the single-league app.** `init_db.py` adds the columns/tables and imports teams
  with no league as `league-2025-26`, with the rules `fantasy_config.py` used to hard-code and
  `league.json`'s `my_team`/`schedule`. `league.json` is no longer read.
