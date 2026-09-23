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
CATEGORY_NAMES = {
    'PTS': 'PTS',
    'AST-TOV': 'AST',
    'AST': 'AST',
    'TOV': 'TOV',
    'PF': 'PF',
    'REB': 'REB',
    'STL': 'STL',
    'BLK': 'BLK',
    'FG3M': '3PM',
    'PPS': 'PPS',
    'DD2': 'DD',
    'TD3': 'TD',
    'TS%': 'TS%',
    'EFG%': 'EFG%',
    'FT%': 'FT%',
    'PLUS_MINUS': '+/-',
    'WIN%': 'WIN',
    'TOT': 'Total Games',
    'SCORE': 'Score',
    'BLKA': 'BLKA',
    'NFT': 'NFT',
    'VEFG%': 'VEFG%'
}
INVERSE_CATEGORIES = ['BLKA', 'TOV', 'PF']

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


# -------- League Configuration --------
FANTRAX_LEAGUE_ID = os.getenv("FANTRAX_LEAGUE_ID")
FANTRAX_USERNAME = os.getenv("FANTRAX_USERNAME")
FANTRAX_PASSWORD = os.getenv("FANTRAX_PASSWORD")

MIN_GUARDS = 2
MIN_FORWARDS = 2
MIN_CENTERS = 1

NUM_PICKUPS = 1
NUM_STARTERS = 11
NUM_TEAMS = 14

# AUCTION
SHOW_AUCTION_PRICE = False
EXP_FACTOR = 5

# FANTASY POINTS SCORING
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

PUNT_CATEGORIES = []
CATEGORIES = ['PTS', 'FG3M', 'AST', 'TOV', 'REB', 'STL', 'BLK', 'PF', 'TS%', 'NFT', 'PLUS_MINUS']
API_ATTRIBUTES = ['FGA', 'FGM', 'FTA', 'FTM', 'FG3M', 'PTS', 'AST', 'REB', 'STL', 'BLK', 'TOV', 'BLKA', 'DD2', 'TD3', 'PF']

# Your league (team abbreviation + matchup schedule) lives in league.json, gitignored.
# A fresh clone runs on league.example.json until you create it.
import json
_ROOT = os.path.dirname(os.path.abspath(__file__))
_LEAGUE_FILE = next(p for p in (os.path.join(_ROOT, 'league.json'), os.path.join(_ROOT, 'league.example.json'))
                    if os.path.exists(p))
with open(_LEAGUE_FILE, encoding='utf-8') as _f:
    _LEAGUE = json.load(_f)
MY_TEAM_ABV = _LEAGUE['my_team']
FANTASY_SCHEDULE = [tuple(week) for week in _LEAGUE['schedule']]

# Create a lookup dictionary for faster access
FANTASY_SCHEDULE_DICT = {date_str: opponent for date_str, opponent in FANTASY_SCHEDULE}

HIGHLIGHTED_TEAMS = []

