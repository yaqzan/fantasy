# NBA Fantasy Dashboard

A React + Flask dashboard for Fantrax NBA fantasy basketball leagues: player rankings, a lineup
optimizer, team standings, and daily stat tracking. Each league carries its own rules (scoring
categories, roster and lineup rules, auction budget, waivers, matchup schedule) and its own teams;
a switcher in the header moves between them. Mine runs at [fantasy.yaqzan.dev](https://fantasy.yaqzan.dev).

## Features

### Backend (Flask)
- RESTful API for player statistics, fantasy team management, and league data
- Several leagues side by side, each with its own rules, teams and rosters
- Season projections: several experts' projections averaged and blended with our own model
  (weights measured on past seasons), rookies included; team win projections weighted by each
  source's past accuracy
- Scores and auction values per league: category z-scores against the players who get drafted,
  auction dollars by value over replacement (its categories, team count, roster size and budget)
- Daily-lineup leagues (best N active players each day count) and weekly-lineup leagues
- Team standings: a power ranking from category totals, per game (roster strength) or this
  week (from the NBA schedule)
- Daily player stats tracking (`daily_player_stats` table) with fantasy points
- Fantrax league sync via `fantrax_client.py`
- Serves the built React frontend at `/` and `/fantasy/*`
- Frontend and API on one origin; `FANTASY_CORS_ORIGINS` only for a split setup

### Frontend (React)
- Sortable player statistics table with all key fantasy metrics
- Search functionality for players and teams
- Lineup optimizer with a duration-based filter for picking the best lineup
- Weekly pickups: free agents ranked by the categories they'd add that week, from the NBA schedule
- Team standings view
- Player pinning (favorites)
- Hot streak indicators
- Draft system with fantasy team selection, "Show Available Only" filter
- Modern NBA-themed UI with dark mode, responsive for desktop and mobile

### Scoring categories

Any mix of: points, rebounds, assists, steals, blocks, 3PM, assists minus turnovers, net free
throws, double/triple-doubles, plus/minus, turnovers, personal fouls, times blocked, technical
fouls, wins, TS%, EFG%, FT%, points per shot. Turnovers, fouls, times blocked and technicals count
against you.

### Key Statistics Displayed
- Overall Rank (OVR), Points, Rebounds, Assists, Steals, Blocks
- Field Goal %, Free Throw %, Three-pointers made
- True Shooting %, Effective FG%, Plus/Minus, AST-TOV ratio, Points per Shot
- Games played, hot streak status
- Auction Values and Z-Scores (per category, per league)

## Data Ingest (NBA stats)

Player and game data is pulled from `stats.nba.com` via the `nba_api` package and written into
MySQL:

- `pull_api_data.py`: season schedule, standings, rosters and player stats (one bulk game-log
  call, plus times blocked from `leaguedashplayerstats`), run daily in season. `--season 2025-26
  --force` backfills a past season (useful before a draft).
- `pull_technical_fouls.py`: technical fouls, scanned from each game's play-by-play once (about
  3 seconds a game; a full season is about an hour). `pull_api_data.py` runs it for new games.
- `pull_history.py`: past seasons' player totals (one call a season), the model's history.
- `pull_projections.py`: this season's projections: our model and ESPN's. Other sources load
  with `import_projections.py players <csv> --source <name>` (team wins: `teams <csv>`).
- `update_daily_stats.py`: daily box scores, scoped to teams that played on a given date
- `create_daily_stats_table.py`: one-time table setup

`stats.nba.com` rate-limits aggressively and occasionally goes fully unresponsive; the ingest
scripts retry with backoff (`nba_api_call` in `pull_api_data.py`). Keep `nba_api` current
(`pip install --upgrade nba_api`): an outdated client is a common cause of calls hanging or
timing out even when the retry logic is otherwise correct.

## Project Structure

```
Fantasy/
├── backend/                    # Flask API server
│   ├── app.py                  # Main Flask application (serves API + built frontend)
│   └── requirements.txt        # Flask/backend dependencies
├── frontend/                   # React application
│   ├── public/
│   ├── src/
│   │   ├── components/         # PlayerTable, LineupOptimizer, TeamStandings, DraftModal, ...
│   │   ├── App.js
│   │   └── index.js
│   └── package.json
├── requirements.txt             # Dependencies for the data-ingest scripts (root level)
├── pull_api_data.py             # NBA API backfill (players, rosters, game logs)
├── update_daily_stats.py        # Daily box scores (Daily Stats tab)
├── fantasy_database.py          # Peewee models: Player, Team, Game, FantasyTeam, DailyPlayerStats
├── pull_technical_fouls.py      # Technical fouls from play-by-play
├── leagues.py                   # League rules: category catalog, settings schema, CRUD
├── fantasy_team_helper.py       # Per-league schedule / roster helpers
├── fantasy_config.py            # NBA-wide settings; reads .env
├── init_db.py                   # Creates and upgrades the MySQL database and tables
├── fantrax_client.py            # Fantrax league sync client
├── lineup_optimizer.py          # Best lineup, best pickup, pickup/drop what-ifs
└── player_stats.py              # Scores, week projections, auction values, fantasy points
```

## Database Schema

- `teams`, `players`, `games`: NBA reference data
- `technical_fouls`, `pbp_scanned_games`: technicals per player per game, and which games are scanned
- `leagues`: each league's rules as JSON (`leagues.py` `DEFAULT_SETTINGS` lists every key)
- `fantasy_teams`, `fantasy_team_players`: each league's teams and drafted players
- `league_player_flags`: per-league player flags (undroppable)
- `daily_player_stats`: per-day fantasy point tracking

## Setup Instructions

### Prerequisites
- Python 3.8+
- Node.js 16+
- MySQL 8 (a local server with the default `root` user works)

### Environment
```bash
cp .env.example .env                  # Fantrax login, optional MySQL settings
pip install -r requirements.txt
python init_db.py                     # creates (or upgrades) the database and tables
python pull_api_data.py               # NBA schedule, rosters, stats
```

Open the app and create a league (**New league** in the header): categories, roster spots and
active spots, daily or weekly lineups, auction budget, waiver claims, your team's abbreviation.
**Fill weeks from NBA calendar** lays out the matchup weeks; type each week's opponent. Then add
the league's teams in the Team Manager (**Add team**, using the abbreviations the schedule uses)
and draft players onto them. Add another league any time; the header's switcher moves between them.
Fantrax login drives your own account through Selenium (Chrome), after first trying your
browser's saved cookie.

### Data ingest scripts
```bash
pip install -r requirements.txt
python pull_api_data.py
```

### Backend Setup
1. `cd backend`
2. `pip install -r requirements.txt`
3. `python app.py`

The backend is available at `http://127.0.0.1:5001` (health check at `/health`).

### Frontend Setup
1. `cd frontend`
2. `npm install`
3. `npm start`

The frontend is available at `http://localhost:3000`.

## API Endpoints

Everything except `/health` lives under `/api`; every other path serves the React app. League
endpoints aside, requests act on the league named in the `X-League` header (the switcher sends
it), else the active league.

### Leagues
- `GET /api/leagues`: leagues, the active one, the category catalog and default settings
- `POST /api/leagues`: create (`name`, `settings`, optional `copy_teams_from`)
- `PUT /api/leagues/<id>`: update name/settings; `DELETE` removes a league with no rostered players
- `POST /api/leagues/<id>/activate`: make it the default for header-less requests and CLI scripts
- `GET /api/leagues/generate-weeks`: blank matchup weeks from the stored NBA schedule

### Players
- `GET /api/fantasy`: all players with fantasy statistics
- `POST /api/calculate-zscores`: recalculate z-scores for custom categories
- `POST /api/calculate-auction-values`: recalculate auction values
- `POST /api/update-player`: update a player's manual fields (tier, notes, etc.)

### Fantasy Teams
- `GET /api/fantasy-teams`: list fantasy teams
- `POST /api/fantasy-teams`: create a fantasy team
- `PUT /api/fantasy-teams/<team_id>`: update a fantasy team; `DELETE` removes it and its roster
- `GET /api/team-players/<team_id>`: players on a team
- `POST /api/draft-player`: draft a player to a team
- `POST /api/undraft-player`: remove a player from a team

### Standings & Stats
- `GET /api/team-standings`: power ranking from category totals (`view=per_game` or `week`)
- `GET /api/analyze`: matchup analysis for a week (best lineup, or best pickup with `pickup=true`)
- `POST /api/analyze/custom`: what-if for a chosen pickup and drop, every timeframe
- `GET /api/pickups`: free agents ranked by expected categories gained in a week, with the best drop
- `GET/PUT /api/projections/teams`, `GET /api/projections/players`, `PUT /api/projections/players/<id>`:
  projected team wins and player lines by source, and the owner's adjustments
- `GET /api/daily-stats`: daily fantasy point stats
- `POST /api/daily-stats/update`: trigger a daily stats refresh

### Misc
- `GET /health`: liveness probe

## Deployment

One process serves everything: `python backend/app.py` (port 5001, loopback only) returns the
built frontend (`npm --prefix frontend run build`) at `/` and the API at `/api`. Put any reverse
proxy or tunnel in front of it; `ops/cloudflared-config.example.yml` is the Cloudflare tunnel I use.

On Windows, `ops/windows/install-tasks.ps1` registers a 5-minute watchdog that restarts the app
(and the tunnel, when `ops/cloudflared-config.yml` exists) if they're down. Pass
`-Controller <script>` to hand restarts to your own service manager instead.

## Your data

| file | what it is |
|---|---|
| `.env` | Fantrax login, MySQL settings |
| `ops/cloudflared-config.yml` | your tunnel, copied from the `.example` |
| `fantraxloggedin.cookie` | the saved Fantrax session |
| the MySQL `fantasy` database | stats, leagues (rules, schedules), teams, rosters |

None of it is in git. (An older install's `league.json` is imported once by `init_db.py` and then
no longer read.)

## Customization

### Adding New Statistics
1. Update `get_fantasy_players()` in `backend/app.py`
2. Add the column to `PlayerTable` in `frontend/src/components/PlayerTable.js`
3. Update table header and cell rendering

### League Settings
Everything about a league (categories, team count, roster and lineup rules, draft, waivers, the
matchup schedule, your team) is edited in the app under **Settings**. A new category needs a stat
in `player_stats.load_player_stats` and an entry in `leagues.CATEGORY_CATALOG`.

## Troubleshooting

1. **Database Connection**: ensure MySQL is running and `DB_CONFIGS`/`DB_NAME` in
   `fantasy_config.py` are correct.
2. **NBA API timeouts/hangs**: upgrade `nba_api` first (`pip install --upgrade nba_api`) —
   `stats.nba.com` frequently rejects older clients outright rather than returning a clean error.
3. **CORS errors** (split setup only): add the frontend's origin to `FANTASY_CORS_ORIGINS` in `.env`.
4. **Missing Dependencies**: `pip install -r requirements.txt` (root, for ingest scripts) and
   `pip install -r backend/requirements.txt` (for the API server), plus `npm install` in `frontend/`.

### Development Tips
- Backend runs on port 5001, frontend on port 3000
- Check browser console and terminal for error messages
- Use React Developer Tools for component debugging

## License

MIT
