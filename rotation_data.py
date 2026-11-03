"""Pull the data the rotation/injury-minutes model trains on, cached under .horizon/rotation/ (gitignored).

  python rotation_data.py lineups 2025-10-21 2026-04-13   # NBA daily lineups JSON per date: starters + Active/Inactive per game
  python rotation_data.py gamelog 2025-26                 # every player game line of a past season (one nba_api call)

Lineups JSON is the pregame truth: `position` set = starter, rosterStatus 'Inactive' = out (final status before tip).
Cached dates are never refetched; a date with no games is stamped empty so it is not asked again.
"""
import json
import sys
import time
import urllib.request
from datetime import date, timedelta
from pathlib import Path

CACHE = Path(__file__).parent / '.horizon' / 'rotation'
URL = 'https://stats.nba.com/js/data/leaders/00_daily_lineups_{}.json'


def fetch_day(d):
    path = CACHE / f'lineups_{d:%Y%m%d}.json'
    if path.exists():
        return False
    req = urllib.request.Request(URL.format(f'{d:%Y%m%d}'), headers={'User-Agent': 'Mozilla/5.0', 'Referer': 'https://www.nba.com/'})
    try:
        data = json.load(urllib.request.urlopen(req, timeout=30))
    except urllib.error.HTTPError as e:
        if e.code in (403, 404):
            data = {'games': []}   # no file for a day without games
        else:
            raise
    path.write_text(json.dumps(data))
    time.sleep(0.5)
    return True


def lineups(start, end):
    CACHE.mkdir(parents=True, exist_ok=True)
    d, n = start, 0
    while d <= end:
        n += fetch_day(d)
        d += timedelta(days=1)
    print(f'{n} days fetched')


def gamelog(season):
    from nba_api.stats.endpoints import leaguegamelog
    from pull_api_data import nba_api_call
    CACHE.mkdir(parents=True, exist_ok=True)
    resp = nba_api_call(leaguegamelog.LeagueGameLog, season=season, player_or_team_abbreviation='P')
    df = resp.get_data_frames()[0]
    df.to_csv(CACHE / f'gamelog_{season}.csv', index=False)
    print(f'{len(df)} lines')


if __name__ == '__main__':
    if sys.argv[1] == 'lineups':
        lineups(date.fromisoformat(sys.argv[2]), date.fromisoformat(sys.argv[3]))
    else:
        gamelog(sys.argv[2])
