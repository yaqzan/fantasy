# NBA Fantasy Basketball Configuration
import os

from dotenv import load_dotenv
load_dotenv()

# MySQL connection; override any of these in .env.
DB_NAME = os.getenv('FANTASY_DB_NAME', 'fantasy')
DB_CONFIGS = {
    'charset': 'utf8mb4',
    'use_unicode': True,
    'user': os.getenv('FANTASY_DB_USER', 'root'),
}
if os.getenv('FANTASY_DB_PASSWORD'):
    DB_CONFIGS['password'] = os.getenv('FANTASY_DB_PASSWORD')
if os.getenv('FANTASY_DB_HOST'):
    DB_CONFIGS['host'] = os.getenv('FANTASY_DB_HOST')
TEAMNAMES = {
    'MIL': 'Milwaukee Bucks', 'PHO': 'Phoenix Suns', 'ATL': 'Atlanta Hawks', 'LAC': 'Los Angeles Clippers', 'BRK': 'Brooklyn Nets', 'PHI': 'Philadelphia 76ers', 'UTA': 'Utah Jazz', 'DEN': 'Denver Nuggets', 'DAL': 'Dallas Mavericks', 'POR': 'Portland Trail Blazers', 'LAL': 'Los Angeles Lakers', 'MIA': 'Miami Heat', 'BOS': 'Boston Celtics', 'GSW': 'Golden State Warriors', 'MEM': 'Memphis Grizzlies', 'CHO': 'Charlotte Hornets', 'NYK': 'New York Knicks', 'IND': 'Indiana Pacers', 'SAS': 'San Antonio Spurs', 'WAS': 'Washington Wizards', 'NOP': 'New Orleans Pelicans', 'SAC': 'Sacramento Kings', 'TOR': 'Toronto Raptors', 'CHI': 'Chicago Bulls', 'MIN': 'Minnesota Timberwolves', 'CLE': 'Cleveland Cavaliers', 'ORL': 'Orlando Magic', 'DET': 'Detroit Pistons', 'HOU': 'Houston Rockets', 'OKC': 'Oklahoma City Thunder',
}

from datetime import datetime

current_date = datetime.now()
# NBA season starts in October, so use October 1st as the cutoff
YEAR_START = current_date.year if current_date.month >= 10 else current_date.year - 1
YEAR_END = YEAR_START + 1
URLS = [
    f"https://www.basketball-reference.com/leagues/NBA_{YEAR_START}_per_game.html",
    f"https://www.basketball-reference.com/leagues/NBA_{YEAR_END}_per_game.html",
]
STATS_URL = f"https://www.basketball-reference.com/leagues/NBA_{YEAR_END}_per_game.html"
STANDINGS_URL = f"https://www.basketball-reference.com/leagues/NBA_{YEAR_END}_standings.html"
SCHEDULE_URL = f"https://www.basketball-reference.com/leagues/NBA_{YEAR_END}_games.html"


# -------- Fantrax login --------
# A league's own Fantrax id lives in its settings; FANTRAX_LEAGUE_ID is the fallback.
FANTRAX_LEAGUE_ID = os.getenv("FANTRAX_LEAGUE_ID")
FANTRAX_USERNAME = os.getenv("FANTRAX_USERNAME")
FANTRAX_PASSWORD = os.getenv("FANTRAX_PASSWORD")

# League rules (categories, roster, team count, draft and its auction price exponent, schedule,
# your team) are per league: see leagues.py. What stays here is NBA-wide.

# FANTASY POINTS SCORING (daily stats tab)
FPOINTS_SCORING = {
    'FGA': -0.45,
    'FGM': 1,
    'FTA': -0.75,
    'FTM': 1,
    'FG3M': 1.5,
    'PTS': 1,
    'REB': 1.25,
    'AST': 2,
    'STL': 3,
    'BLK': 3,
    'TOV': -1
}

# Per-player counting columns in the players table (lower-cased, with _5 / _10 variants).
API_ATTRIBUTES = ['FGA', 'FGM', 'FTA', 'FTM', 'FG3M', 'PTS', 'AST', 'REB', 'STL', 'BLK', 'TOV', 'BLKA', 'DD2', 'TD3', 'PF',
                  'TECH', 'W']
