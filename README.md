# NBA Fantasy Dashboard

A React + Flask dashboard for a Fantrax NBA fantasy basketball league: player rankings, a lineup
optimizer, team standings, and daily stat tracking, built around one league's category scoring.
Mine runs at [fantasy.yaqzan.dev](https://fantasy.yaqzan.dev).

## Features

### Backend (Flask)
- RESTful API for player statistics, fantasy team management, and league data
- Custom z-score and auction value calculation per the league's scoring categories
- Team standings computed from category scoring across the fantasy schedule
- Daily player stats tracking (`daily_player_stats` table) with fantasy points
- Fantrax league sync via `fantrax_client.py`
- Serves the built React frontend at `/` and `/fantasy/*`
- CORS limited to the origins in `FANTASY_CORS_ORIGINS`

### Frontend (React)
- Sortable player statistics table with all key fantasy metrics
- Search functionality for players and teams
- Lineup optimizer with a duration-based filter for picking the best lineup
- Team standings view
- Player pinning (favorites)
- Hot streak indicators
- Draft system with fantasy team selection, "Show Available Only" filter
- Modern NBA-themed UI with dark mode, responsive for desktop and mobile

### Key Statistics Displayed
- Overall Rank (OVR), Points, Rebounds, Assists, Steals, Blocks
- Field Goal %, Free Throw %, Three-pointers made
- True Shooting %, Effective FG%, Plus/Minus, AST-TOV ratio, Points per Shot
- Games played, hot streak status
- Auction Values and Z-Scores (per-category, configurable in `fantasy_config.py`)

## Data Ingest (NBA stats)

Player and game data is pulled from `stats.nba.com` via the `nba_api` package and written into
MySQL:

- `pull_api_data.py`: full player/roster/game-log backfill, run periodically
- `update_daily_stats.py` / `update_daily_stats_efficient.py`: daily fantasy-point updates,
  scoped to teams that played on a given date
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
├── update_daily_stats.py        # Daily fantasy stats updater
├── update_daily_stats_efficient.py
├── fantasy_database.py          # Peewee models: Player, Team, Game, FantasyTeam, DailyPlayerStats
├── fantasy_team_helper.py       # Fantasy schedule / week helpers
├── fantasy_config.py            # Scoring, categories, roster rules; reads .env + league.json
├── init_db.py                   # Creates the MySQL database and tables
├── league.example.json          # Example team + schedule (copy to league.json)
├── fantrax_client.py            # Fantrax league sync client
├── lineup_optimizer.py          # Best-lineup calculation
├── player_stats.py              # Z-scores, auction values, fantasy points
└── display.py                   # CLI stat display helpers
```

## Database Schema

- `teams`, `players`, `games`: NBA reference data
- `fantasy_teams`, `fantasy_team_players`: this league's teams and drafted players
- `daily_player_stats`: per-day fantasy point tracking

## Setup Instructions

### Prerequisites
- Python 3.8+
- Node.js 16+
- MySQL 8 (a local server with the default `root` user works)

### Environment
```bash
cp .env.example .env                  # Fantrax login + league id, optional MySQL settings
cp league.example.json league.json    # your team abbreviation + matchup schedule
pip install -r requirements.txt
python init_db.py                     # creates the database and tables
```

Without `league.json` the app runs on the example league. Fantrax login drives your own account
through Selenium (Chrome), after first trying your browser's saved cookie.

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

### Players
- `GET /fantasy`: all players with fantasy statistics
- `POST /calculate-zscores`: recalculate z-scores for custom categories
- `POST /calculate-auction-values`: recalculate auction values
- `POST /update-player`: update a player's manual fields (tier, notes, etc.)

### Fantasy Teams
- `GET /fantasy-teams`: list fantasy teams
- `POST /fantasy-teams`: create a fantasy team
- `PUT /fantasy-teams/<team_id>`: update a fantasy team
- `GET /team-players/<team_id>`: players on a team
- `POST /draft-player`: draft a player to a team
- `POST /undraft-player`: remove a player from a team

### Standings & Stats
- `GET /team-standings`: league standings from category scoring
- `GET /analyze`: category analysis
- `GET /daily-stats`: daily fantasy point stats
- `POST /daily-stats/update`: trigger a daily stats refresh

### Misc
- `GET /health`: liveness probe

## Deployment

`python backend/app.py` serves the API and the built frontend (`npm --prefix frontend run build`)
from one origin, so you can put any reverse proxy or tunnel in front of it. To host the frontend
separately, build it with `REACT_APP_API_URL=https://your-api-host` (in
`frontend/.env.production.local`) and add the frontend's origin to `FANTASY_CORS_ORIGINS` in `.env`.

## Your data

| file | what it is |
|---|---|
| `.env` | Fantrax login, league id, MySQL and CORS settings |
| `league.json` | your team and the season's matchup schedule |
| `fantraxloggedin.cookie` | the saved Fantrax session |
| the MySQL `fantasy` database | stats, teams, rosters |

All of it is gitignored.

## Customization

### Adding New Statistics
1. Update `get_fantasy_players()` in `backend/app.py`
2. Add the column to `PlayerTable` in `frontend/src/components/PlayerTable.js`
3. Update table header and cell rendering

### League Settings
Scoring categories, punt categories, team count, roster minimums, and the fantasy week schedule
live in `fantasy_config.py`. Your team and the week-by-week schedule live in `league.json`: update
it each season once matchup dates are set.

## Troubleshooting

1. **Database Connection**: ensure MySQL is running and `DB_CONFIGS`/`DB_NAME` in
   `fantasy_config.py` are correct.
2. **NBA API timeouts/hangs**: upgrade `nba_api` first (`pip install --upgrade nba_api`) —
   `stats.nba.com` frequently rejects older clients outright rather than returning a clean error.
3. **CORS errors**: allowed origins are hardcoded in `backend/app.py`; add new ones there.
4. **Missing Dependencies**: `pip install -r requirements.txt` (root, for ingest scripts) and
   `pip install -r backend/requirements.txt` (for the API server), plus `npm install` in `frontend/`.

### Development Tips
- Backend runs on port 5001, frontend on port 3000
- Check browser console and terminal for error messages
- Use React Developer Tools for component debugging

## License

MIT
