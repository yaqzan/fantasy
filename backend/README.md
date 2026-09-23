# NBA Fantasy Backend API

Flask REST API for NBA fantasy basketball player statistics and draft management.

## Quick Start

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

2. Ensure your MySQL database is running and configured in `../fantasy_config.py`

3. Run the server:
   ```bash
   python app.py
   ```

The API will be available at `http://127.0.0.1:5001`

## API Endpoints

### Players
- `GET /api/fantasy` - Get all players with fantasy statistics
- `POST /api/draft-player` - Draft a player to a fantasy team
- `POST /api/undraft-player` - Remove a player from a fantasy team

### Fantasy Teams
- `GET /api/fantasy-teams` - Get all fantasy teams
- `POST /api/fantasy-teams` - Create a new fantasy team
- `GET /api/team-players/<team_id>` - Get players for a specific team

## Response Format

All endpoints return JSON responses. The main player endpoint includes:
- Player basic info (name, team, position)
- Fantasy statistics (points, rebounds, assists, etc.)
- Calculated metrics (overall rank, z-score, auction value)
- Draft status and team assignment

## Dependencies

- Flask 2.3.3
- Flask-CORS 4.0.0
- Peewee 3.17.0
- PyMySQL 1.1.0
- python-dotenv 1.0.0
