# Leagues

Every league-specific thing (rules, teams, rosters, undroppable flags, position eligibility,
schedule, your team) belongs to a league. NBA data (players, games, standings, injuries, daily
stats) is shared by all leagues.

- **Storage.** `leagues` table: `id` (slug), `name`, `settings` (JSON), `is_active`.
  `leagues.py` owns the schema: `DEFAULT_SETTINGS` lists every key, `validate_settings` merges onto
  it (`_upgrade` first rewrites older documents: position minimums become slots,
  `fantrax_league_id` becomes `platform_league_id`), `LeagueConfig` is what the stats code
  receives. `fantasy_teams.league_id` scopes teams; team names are unique per league, not globally.
  `league_player_flags` holds per-league `undroppable` and `positions` (write through
  `set_league_flags`, which touches only the fields given: a peewee `replace` would wipe the other
  one). `Player.injured` stays NBA-wide.
- **Team names change; ids don't.** `fantasy_teams.platform_team_id` is the platform's permanent
  team id (Fantrax `teamId=`, Yahoo team number); `abv` is our own stable key. `python
  pull_fantrax.py teams --league <fantrax id> [--apply]` renames teams to match Fantrax by id (dry
  run by default; a team with no id links by its current name, else set the id by hand). Match
  rosters/schedules by id, never by name.
- **Platform importers** (dry run unless `--apply`; `settings.platform` + `platform_league_id` pick
  the league). `pull_fantrax.py` (saved browser cookie; a rejected login is re-read from Firefox once): team names by
  id, projections, techs, and `rosters`: prints new transactions (claims/drops and trades are separate
  Fantrax views; seen ids in gitignored `.cache/fantrax_transactions_seen.json`), then makes each team's roster
  exactly Fantrax's by team id (a player moving between teams keeps his draft price; an empty answer never wipes
  a roster). Hourly task, see ops.md.
  `pull_yahoo.py` (XML API v2, `nba.l.<number>` = the current season's league; two transports: Yahoo OAuth
  with the owner's app keys in `.env` + gitignored `yahoo_token.json`, else, or when Yahoo refuses the token
  (401/403: the developer program hadn't approved the app, 2026-10), the same API on Yahoo's site host
  `pub-api-ro.fantasysports.yahoo.com` with the owner's Firefox login, saved to gitignored `yahoo_web.cookie` and
  re-read from Firefox once on a 401; sign in to Yahoo in Firefox): teams
  linked by Yahoo team id (first sync by name), each roster made exactly Yahoo's, every rostered or
  available player's eligibility into `league_player_flags.positions`, Yahoo's can't-cut list into
  `undroppable` (a hand-set flag is never cleared, only reported). Its starting slots are compared
  with `roster.slots` and reported, never written. Names match through `projections.norm_name`.
  Parsers are tested on Yahoo-shaped XML (`test_pull_yahoo.py`); transactions aren't read. `draft` writes Yahoo's
  round-1 order (teams' `draft_position`, empty until Yahoo sets it shortly before the draft) to settings
  `draft.order` (team abbreviations) and puts each drafted player on his team (Yahoo wins; no pick number is
  stored); `--watch N` polls. `adp` writes Yahoo's pre-draft rank (`OR`) and ADP for the top 300 to
  `.cache/yahoo_adp_<league>.json` (the snake room model, draft-strategy.md).
- **Which league a request is about.** `X-League` header (the frontend's switcher, stored in
  localStorage `fantasy.league`), else `?league=`, else the active league. Switching in the UI
  also activates the league, so CLI scripts (`lineup_optimizer.py`, default `--league`) follow
  the last pick. Every league-scoped query must filter by league (`league_team_ids`,
  `get_team_by_abv`); draft/undraft only touch the current league's teams, so one player can be
  on a team in each league. Every league-scoped stats view starts from
  `player_stats.league_player_stats(league)` (the league's position eligibility, then its scoring).
- **Capabilities.** `LeagueConfig.capabilities()` (in `to_dict()` and `/api/fantasy`'s `config`,
  which adds `draft_plan`): `scoring`, `punts`, `positions` (filter chips; empty = all flex),
  `auction`, `guillotine`, `faab`, `claims_per_week`, `team_wins`, `long_weeks`, `playoffs`. Tabs,
  columns and controls switch on these names, never on a platform or league id: $ vs draft round,
  punt boxes, position filter, Team wins projections, FAAB line, playoff cut line, Eliminate,
  Daily Leaders' points vs category columns, the Draft Day tab (`draft_plan`: `draft_day.json` was built for this league).
- **View state per league** (`frontend/src/useLeagueViewState.js`): each tab's picks (stats
  timeframe, week, punts, position chips, filters, star premium, standings view) live in
  localStorage `fantasy.view.<league>.<tab>`. Only what the user picked is stored, over defaults
  that can change (the default timeframe flips when a season starts); a sanitizer drops stored
  values the league no longer has (a category, a week, a position chip). `<main key={leagueId}>`
  remounts every tab on a switch, so each reads its own league's state (test:
  `frontend/src/useLeagueViewState.test.js`, `CI=true npx react-scripts test --watchAll=false`). Draft mode is per league
  too (`fantasy.draftMode.<league>`); off unless toggled on. Daily Leaders is the first tab. The
  app opens on it from the day's first tip-off until 8 am Eastern the next morning, else on Player
  Rankings (`/api/default-tab`, `daily_leaders.default_tab`; a click wins; draft mode falls back
  to Player Rankings).
- **Scoring mode.** `settings.scoring`: `{type: 'categories'|'points', points: {stat: weight}}`. A points
  league's only category is `FPTS`: `player_stats.add_fantasy_points` folds the league's weights
  (`POINT_STATS` keys) into a per-game `FPTS{n}` for every timeframe, then z-scores, totals, weekly
  matchup, pickups and standings run unchanged on that one category. A single category isn't capped at
  +/-3 z (stars keep their full lead). Its noise: variance per game 6.0x the mean (2025-26 game logs,
  default weights, 452 players with 20+ games; the same method gives PTS 3.3 and REB 1.5, matching
  the catalog). The 2.5x estimate it replaced made points-league win chances far too sure. The
  coefficient grows roughly with the size of the weights, so a league with much bigger weights
  would need its own measurement.
  `fantasy_config.FPOINTS_SCORING` is the default weight table; Courtside Tamasha (Yahoo) uses it.
  Daily Leaders scores each game line with the same formula (`leagues.fantasy_points`); FPTS is its pinned primary
  column in every sort (bold, wider: 3rem on phones; in Pace order the pace number sits under it), paid for by 2rem stat
  columns so PTS REB AST STL BLK still fit a phone (166 + 48 + 5 x 32 = 374px). There's no separate FPts
  column in the player table: it was the same idea hard-coded for every league.
- **Categories.** `CATEGORY_CATALOG` in `leagues.py`: key, label, `inverse` (lower wins), `kind`;
  ratios also carry `attempts` (per-game attempts formula) and `prior` (shrinkage strength in
  attempts, method of moments on 2025-26; FG% measured ~55, stored 60). Adding a category = a per-player per-period stat in
  `player_stats.load_player_stats` (keys `CAT`, `CAT_5`, `CAT_10`, `CAT_projected`, and `CAT_proj`
  via `PROJECTED_STATS`/`_ratios` in `_add_projections`) + a catalog entry with its weekly noise
  (`noise`, or `attempt_sd` for a ratio); `calculate_team_totals` sums counting stats generically
  and special-cases ratios and `WIN%`.
  - `BLKA` (times blocked): `leaguedashplayerstats` (the game logs lack it); its last-N filter is
    the team's last N games, an approximation.
  - `TECH`: play-by-play scan, `pull_technical_fouls.py`, one fetch per game ever
    (`pbp_scanned_games`). Counts `Foul` actions whose subType contains "Technical" by players
    (coach/team techs and defensive 3 seconds drop out). Unscanned games count 0.
  - `WIN%` ("Wins"): per player, wins per game played (game log `WL`). Before the season's
    first game (`is_preseason`) and before player wins exist: his current team's strength
    (`projections.team_strength`, see projections.md), since
    his wins came with last season's team (Anthony Davis: Dallas-era .500, Washington .207).
    In a week projection a player's wins are the summed log5 chances of his team winning each
    game he is active for (`week_schedule`, from `team_strength`: projected wins faded into the
    real record).
- **Positions and slots.** `roster.slots`: the `active` starting slots from `SLOT_TYPES` (PG SG G SF
  PF F C UTIL), e.g. Courtside `PG SG G SF PF F C UTIL UTIL`; empty = all UTIL. A player's positions
  are the league's imported eligibility (`league_player_flags.positions`), else NBA's
  (`Player.positions`, the roster listing "G-F", filled by `pull_api_data.py`). `POSITION_REACH`:
  a position fills its own slot and its group (PG -> PG, G), and NBA's generic G/F reach every
  slot of their group, so leagues work before an import. `player_stats.fill_slots` picks the
  lineup: players best first, each gets in if the ones already in can be reshuffled to make room
  (augmenting path). Players that fit the slots form a transversal matroid, so this greedy is the
  best lineup for any ranking. Test: `test_league_rules.py` (9 centers score less than a balanced
  roster with slots, the same all flex).
- **Daily vs weekly lineups** (`roster.daily_lineups`). Weekly: `best_starters` (fill_slots on the
  healthy roster by Z-SCORE) play every game. Daily: each day `fill_slots` over the players whose
  team plays (`player_week_games`); injured players hold a spot and score nothing, and a pickup
  means choosing a drop. Opponents are modelled the same way.
- **Weekly matchup model** (`team_week_totals`, `category_margins`, `category_win_chances`): a
  team's weekly totals, each with a variance from per-game noise (catalog `noise`: variance per
  game = coef x the player's per-game stat; `attempt_sd` for ratios; wins are coin flips at each
  game's log5 chance). The constants come from the 2025-26 game logs: points swing 3.4x their mean,
  most counting stats 1-1.5x. A category's margin is my lead in SDs of the difference; P(win) is
  normal on it. A roster's value is its expected categories won (points leagues: the chance of
  winning the week). One model for the Lineup Optimizer, Weekly Pickups and the CLI
  (`lineup_optimizer.py`); the old hand-tuned lineup score and its weight table are gone.
  **Calibrated 2026-10-13** (`.horizon/weekly_model_backtest.py`: 2025-26 logs, Dec-Apr, 4,800 random
  10-player head-to-head category matchups from the top 150 by minutes, each player's season-to-date
  average): single-game noise alone was far too sure (it called 96% categories that won 83%, 4% ones
  that won 15%). Two fixes, both in `player_stats.py`: `AVAILABILITY` 0.86 (a healthy-looking player,
  one who played in the last 7 days, played 85.5% of his team's games; a game counts that fraction, and
  in daily leagues a bench player covers an absent starter: `_lineup_chance`, positions ignored then,
  plus the variance of games played) and `SD_SCALE` 1.5 on the difference's SD (log-loss optimum
  k=0.6-0.7 for counting categories, 0.7-0.75 for FG%/FT%; it covers projection error, minutes swings and
  teammates' correlated nights). Log-loss .644 -> .577. Still a little overconfident at 90%+. Wins
  (WIN%) weren't backtested. Known-injured players still count 0 for the whole week (the flag has no
  per-game dates).
- **Opponent** (`Week.opponent`): the week's scheduled opponent once its roster is in, else the
  average of the league's other teams still playing, else none (the Lineup Optimizer shows my
  totals only, "opponent TBD"; pickups judge against a copy of my team).
- **Pickups** (`rank_moves`): for each of the 250 best free agents (Z-VALUE) whose team plays that
  week, every drop (or an open spot) is tried; gain = change in expected categories won. Moves
  rank by gain + 0.01 x the change in summed margins (SDs), so when a week is as good as won or
  lost (Courtside against a weak team: 0.99+) a bigger margin still ranks first instead of
  everything tying at 0. Weekly Pickups lists single moves. The Lineup Optimizer's best pickups
  (`best_moves`) are greedy up to `claims_per_week` (Courtside 5): best move, then the best on top
  of it among the previous step's top 30, until nothing helps. Exhaustive claim combinations
  (5 of 150) are out of reach. ~0.4 s per league-week. `/api/analyze?add=&drop=` (repeatable) is
  the what-if; `moves=true` adds the best pickups.
- **Stage plan** (`plan_stage`, `/api/stage-plan`, `python lineup_optimizer.py <league> proj false true`): guillotine
  leagues only. The claims for each remaining week of the current stage: beam search (4 rosters) over `rank_moves`,
  each week judged against its scheduled opponent, the roster carrying over, so a claim that pays next week's
  4-game slate shows. Shows 5 next-best claims per week (the blind auction can be lost); an alternative can beat the
  chosen claim's single-week gain when the chosen one wins on the following weeks. Not modelled: FAAB bids, the
  next stage's pool (eliminated teams' players), waiver processing time. ~4 s.
- **Team Standings** is a power ranking, not the league's real standings. `view=per_game`: one
  game each of every team's `best_starters`. `view=week`: the current fantasy week through
  `player_week_games`. Injured players are left out unless `healthy_only=false`. Ranked by the sum
  of category ranks, which in a points league is the rank by projected points. `playoffs.teams`
  draws the cut line.
- **Player value** (`calculate_overall_scores`): per category, a z-score of the per-game value
  against the scaling pool (1.8 x `num_teams x roster.size`, `SCALING_POOL_FACTOR`, re-ranked 3
  times from the qualified players; bigger than the drafted set because it tracked categories won
  better, draft-strategy.md "10 spots"), capped at ±3, then summed (`VALUE`; `Z-VALUE` without punted categories). Ratios are
  scored as impact, attempts per game x (rate shrunk by `prior` - pool rate). Display scores are
  0-100: per category 50 = the scaling pool's average, 0/100 = ∓3 SD; overall (`SCORE`,
  `Z-SCORE`, the UI's OVR) 10 points per SD of value among drafted players. Don't reintroduce min/max scaling
  (garbage-time players set the scale) or a logistic squash (it priced specialists like Gobert
  64 spots too low); both were tried 2026-09. Non-auction leagues show the draft round (value
  rank / teams) instead of $.
- **Auction values** (`calculate_auction_values`): value over replacement. Each drafted player
  (`num_teams x roster.size`) costs $1; the rest of `num_teams x budget` goes by (value -
  first undrafted player's value) ^ `draft.price_exponent`, rounded to whole dollars that add up
  to the budget. `/api/fantasy` prices every timeframe (`auction_value_<period>`) so the table's
  $ always sits on the same stats as its rank. **Three different "projections"** (don't mix them up):
  `proj` = our projection model, `pre` = the model moved by preseason games (best before the season),
  `projected` = RECENT FORM (half the season's average, half the last 10 games; labelled that way in the
  UI). `player_stats.default_stat_type(league)` picks the default (`pre` > `proj` > `season` until a regular-season game
  has been played, `projected` (recent form) from then on: it reads the game log for the season, no date, so it flips by itself each year) for `config.default_stat_type` and for every API call without a
  timeframe. A player with no games (rookie, missed last season) has no recent form, so his `_projected`
  is his `_proj`. Players under
  `games_floor` are flagged `small_sample`. Fit the exponent to the league's past auction prices by rank (least squares
  over the drafted players); the owner's league stores its fit (a gitignored
  `draft_history_price_curve.json` holds the price curve it came from).
- **Guillotine leagues** (`elimination.stage_weeks`, e.g. `[3,3,3,3,3,3,2]`: six 3-week stages + a 2-week final; empty = ordinary
  league). Stages are consecutive schedule weeks; after each stage but the last, the
  `per_stage` worst records are eliminated and every record resets. `LeagueConfig.stage_info()`
  (in `to_dict()`, so the header shows it) gives the stage, its weeks and dates, teams in it and
  the trade window (first week of a stage). Eliminating a team (`/fantasy-teams/<id>/eliminate`,
  Team Manager edit dialog) sets `fantasy_teams.eliminated_stage`, saves its roster to
  `released_roster` and releases the players to free agency, so pickups see them; `/restore`
  undoes it minus players another team took since. Eliminated teams drop out of Team Standings
  and of the league-average opponent; Standings marks the bottom `per_stage` rows. Records aren't
  imported, so the red rows are the power ranking's guess, not the real stage standings. Auction
  prices and z-score pools still use the starting `num_teams`. `waivers.faab_budget` /
  `faab_per_stage` are shown (Weekly Pickups), not enforced, and spending isn't tracked.
- **Schedule.** `[[week start, opponent abbreviation], ...]`; a week ends the day before the next
  starts (last week: 7 days). `LeagueConfig.weeks()` (in `to_dict()`) gives each week's start,
  end, `days` (Courtside weeks 7 and 17 are 14) and `playoffs` (from `playoffs.first_week`); every
  week picker labels range and day count (`frontend/src/weeks.js`) and opens on the week being
  played, or the next one on its last day. The player table shows each NBA team's GP for this and
  next week (`config.current_week`/`next_week`). Empty schedule: Monday-Sunday weeks, no opponent.
  "Fill weeks from NBA calendar" (`/api/leagues/generate-weeks`) makes opening day + every Monday
  from the stored NBA schedule, opponents blank. Fantrax leagues: `pull_fantrax.py schedule` copies
  Fantrax's scoring periods and my opponents (by Fantrax team id; playoff opponents stay blank, seeding
  decides them) and fills an unset `playoffs.first_week`. Playoff weeks already set are kept: Fantrax's
  matchup list runs past the real rounds (WSOP 2026-27: 4 listed, 2 played; its settings page is the truth). The NBA leaves the Cup knockout window (Dec 4-11
  in 2026) unscheduled until the group stage ends, so those days have no games until a later
  schedule pull.
- **Daily Leaders** (`daily_leaders.py`, `/api/daily-leaders`, the "Daily Leaders" tab): every
  stat line of a day, ranked by the selected league, rows marked mine (highlighted) / taken
  (dimmed) / free. **Mine means mine in ANY league** (`my_players_everywhere`, row field `mine_any`; frontend
  `isMine`/`ownerKey` in `dailyLeaders.js`): the highlight, the My team filter and its count ignore which league is selected;
  a player taken here but mine elsewhere is highlighted (amber) AND dimmed like any taken player, and keeps the other owner's initials chip. Scoring and `owner` stay the selected league's. **Source is ESPN's public site API** (scoreboard + one `summary` per game):
  cdn.nba.com answers this host 403 and stats.nba.com box scores are empty while a game is on
  (checked 2026-10-09), so neither can be live. ESPN's box lacks times blocked and techs; both
  come from its play-by-play (a block play's first participant is the shooter; "technical foul"
  minus defensive 3-seconds, never "technical free throw"). Players match NBA ids by
  `projections.norm_name` (185/185 on 2026-10-08). **Refresh:** a background poller thread
  (`start_poller`, started by `backend/app.py` outside pytest) refetches today, and yesterday until
  its late games are final, every 75 s while a game is on (`REFRESH_SECONDS`; 2026-10-20, was 5 min; sized so a
  15-game night is ~2,200 calls, under the ~2,500/day guess; `espn_calls_today` in the API response counts
  the real ones, tune against it; watch for 429s, revert to 300 if it throttles; a game counts as
  on once its start time passes, whatever ESPN says), at the first tip-off, every 3 h before it
  (hourly in the last 3 h, so a game moved earlier shows up within the hour), never once all games
  are stored final. The 3-h check can't swallow a game: the tip time always cuts it short. If the
  poller is 2 min overdue (stalled thread, slept machine), a page request fetches itself. It sleeps until the next
  of those is due (`due_at`; 30 s..3 h), not on a fixed tick: a simulated 8-game day wakes 79 times
  (a 60-s tick: 1,440), 7 pm-1 am every 5 min, otherwise every 3 h. A refetch costs ~0.9 s CPU
  per 5 games (play-by-play parsing). The page is ready when opened; page requests read the cache
  (they fetch only a day nobody cached, or another date) and the Refresh button has a 60-s floor (`FORCE_FLOOR_SECONDS`). Only unfinished games are refetched; one
  failed game keeps its last lines and retries next pass. ESPN publishes no limit (hobbyist docs
  guess ~2,500 calls/day); a 15-game night is ~550 at 5 min, ~2,200 at 75 s (scaled from the 5-min figure; finished games drop out). It does drop TLS handshakes now and
  then (SSL EOF on 2 of 6 calls, 2026-10-09), hence the kept-alive session with backoff retries.
  Default day: yesterday until noon Eastern (`SCOREBOARD_FLIP_HOUR`), then today.
  **Logos + channels:** team logos are NBA's primary SVGs (`cdn.nba.com/logos/nba/<team id>/primary/L/logo.svg`, answers this host 200), saved once to `frontend/public/logos/<NBA abbr>.svg` (30 files); the UI maps ESPN's GS/NO/NY/SA/UTAH/WSH to them (`LOGO_ABBR`). Channels come free in the scoreboard call (`comp.broadcasts`: national / home / away names) and show in a modal opened by tapping a scoreboard chip (X, outside tap or Escape closes; its button toggles the only-this-game filter); ESPN fills them in close to tip-off, so a far-off game reads "not announced". The poller rechecks a not-yet-started slate at 7, 10, 12, 14 and 16 Eastern (`CHANNEL_CHECK_HOURS`, one scoreboard call each) on top of the 3-h/hourly checks, so channels are in by midday. Tomorrow's slate isn't polled.
  **Game progress / on court:** the same `summary` call carries `plays`, so no extra request: the
  box score's `starter` flags seed each team's floor, every "Substitution" play (participants
  `[enters, exits]`, team id on the play) is replayed, and a live game's lines get `ON`
  (verified 2026-10-15 on a finished game: 5 per side, 0 exits of a player not on the floor).
  It is as fresh as the 5-min refetch. The scoreboard adds `period` + `clock`; a player row gets
  `game_period`, `game_clock`, `on_court`, and `game_result` ("W 144-128", own score first, final
  games only). UI: four quarter pips under the name, the current one pulsing red on the floor and
  plain grey on the bench; a final game shows only the muted result. DNP: box-score athletes with
  `didNotPlay` stay off the stat lines (`_dnp`, so folds and pools ignore them) and come back as
  last-ranked rows (`dnp`, `dnp_reason`) only for rostered players of a finished game.
  Category leagues rank by summed z per category: (game value - scaling pool's per-game mean) /
  the SINGLE-GAME noise SD from the matchup model (`noise`, `attempt_sd`, wins a coin flip),
  capped at +/-3, ratios as impact. Wins count once final. **Don't switch to the OVR scale**
  (between-player SD of season averages): single-game noise is 1.1-1.2x that SD for PTS/REB but
  3-6x for STL, TECH, WIN%, TS%, FG%, FT%, so on the OVR scale every winner gets +3 W, one tech
  -3, an efficient 10-shot night +3 TS%. Measured on 2026-10-08 (WSOP): 1.84 capped cells per
  player vs 0.09, and a 12-3-0 line (2 stl, 2 blk, a win) ranked first over a 22-10-3-blk line.
  The two orders still agree broadly (Spearman 0.94, 8 of the top 10 shared, both leagues).
  Price of the cap: one technical is -3 in a TECH league, more than a 28-point night earns (+2.2 PTS): 10-13 Reaves 28 pts, 1 tech, 7 TO ranked 37th, under da Silva's 18. Matchup math agrees (one tech is ~2.5x the category-win swing of +14 points), so the page names the drag instead of softening it.
  **Signals** (`daily_leaders.signals`): *pace* (▲/▼ by Val) = tonight vs his own per-minute norm:
  expected = projected per-game line x (minutes tonight / projected minutes; `_proj` is the only
  timeframe with minutes, so real season minutes are a later pull), per category (tonight -
  expected) / single-game noise for that many minutes, capped +/-3, summed / sqrt(count); W, DD,
  TD, +/- skipped. So a hot first quarter shows, and a short stint needs a bigger surge; 6-minute
  floor; arrow at |pace| >= 1.5. Look (`frontend/src/dailyLeaders.js`): Val's colour is the
  night's quality (green/red at +/-1 and +/-3; FPTS plain), the pace mark has its own colours (sky
  up, amber down) and three steps (faint < 2.5, full, doubled >= 3.5), grey when it disagrees with
  Val (ahead of a low norm on a night that still hurt): a green arrow on -5.3 read as a good night. 2026-10-06..08: SD 1.07-1.15 in category leagues (≈N(0,1)), ~10%
  up / 5% down; the points league runs narrower (SD 0.75, ~4% flagged: its 6.0x FPTS noise looks
  high for preseason minutes, recheck in season). *Minutes* (green `27m`): >= 1.25x and +5 over
  projected minutes (15-18% of preseason lines; rotations). *Streak* (🔥/🧊): last-10 SCORE vs
  season SCORE, +/-8 (0.8 SD of value), off in preseason and under 10 games. The *Pickups* chip was merged into *Available* (2026-10-17, owner): one free-agent chip, ordered by the Best/Pace toggle; a saved `pickups` filter reads as Available. The owner chips multi-select (saved as `"free,mine"`; none lit = All). `isPickup` (pace up, or minutes up at pace >= 0.5, or hot; never a negative-Val night) is no longer shown.
  **Preseason** is per game, from ESPN's season type (1 pre, 2 regular, 3 playoffs, 5 play-in);
  the stored schedule agrees (`season_first_game`: 2026-10-20). Starters sit second halves, so
  minutes are rotations and raw Val favours reserves: no minutes flag, arrows hollow (△▽), default
  sort Pace (a Best/Pace toggle, remembered per league once picked; Best = Val, the server's order; renamed 2026-10-14 because the pinned column showed Val under a Pace order and read as random), Pickups = pace up among
  rotation players only (projected 15+ min: 2-12 a night on 10-06..08 vs 7-17 without). No
  on-page note (owner removed it 2026-10-09). Regular-season games switch all of it back on their own.
  Season averages take each game as ESPN calls it final, and the official NBA pull confirms them
  after the night (`game_log.py`, `nightly_stats.py`, ops.md); the page's pools and baselines
  rebuild on each. `daily_player_stats` (old per-player nba_api scrape) is no longer written or read.
- **Team Manager** (`/api/team-rosters`, one request for every team): rosters best first, each
  healthy starter's slot (BN = bench) and the starters' average OVR from `best_starters`, and
  spots used against `roster.size`.
- **Upgrade from the single-league app.** `init_db.py` adds the columns/tables and imports teams
  with no league as `league-2025-26` (that league was removed 2026-09-30; backup in `.horizon/league-2025-26-backup.json`), with the rules `fantasy_config.py` used to hard-code and
  `league.json`'s `my_team`/`schedule`. `league.json` is no longer read.
