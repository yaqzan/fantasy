"""Past seasons' player totals into `player_seasons`, the history projections are built from.

One nba_api call per season (leaguedashplayerstats, regular season totals). Seasons already
stored are skipped unless --force; safe to re-run.

    python pull_history.py [--first 2010-11] [--last 2025-26] [--force]
"""
import argparse
import time

from nba_api.stats.endpoints import leaguedashplayerstats

from fantasy_database import DB, PlayerSeason

COLUMNS = {'PTS': 'pts', 'REB': 'reb', 'AST': 'ast', 'STL': 'stl', 'BLK': 'blk', 'FG3M': 'fg3m', 'TOV': 'tov',
           'FGM': 'fgm', 'FGA': 'fga', 'FTM': 'ftm', 'FTA': 'fta', 'BLKA': 'blka', 'PF': 'pf', 'DD2': 'dd2',
           'TD3': 'td3', 'W': 'w'}


def seasons(first, last):
    return [f'{y}-{str(y + 1)[2:]}' for y in range(int(first[:4]), int(last[:4]) + 1)]


def pull_season(season, retries=4):
    for attempt in range(retries):
        try:
            return leaguedashplayerstats.LeagueDashPlayerStats(
                season=season, per_mode_detailed='Totals', season_type_all_star='Regular Season',
                timeout=90).get_data_frames()[0]
        except Exception as e:  # noqa: BLE001 - nba_api raises plain Exceptions on timeouts
            print(f'{season}: attempt {attempt + 1} failed ({type(e).__name__}); retrying')
            time.sleep(10 * (attempt + 1))
    raise SystemExit(f'{season}: could not fetch player totals')


def main(first='2010-11', last='2025-26', force=False):
    for season in seasons(first, last):
        if not force and PlayerSeason.select().where(PlayerSeason.season == season).exists():
            continue
        df = pull_season(season)
        rows = [dict(season=season, player_id=int(r.PLAYER_ID), name=r.PLAYER_NAME, team=r.TEAM_ABBREVIATION,
                     age=float(r.AGE) if r.AGE == r.AGE else None, gp=int(r.GP), min=float(r.MIN),
                     **{dst: int(getattr(r, src) or 0) for src, dst in COLUMNS.items()})
                for r in df.itertuples()]
        with DB.atomic():
            PlayerSeason.delete().where(PlayerSeason.season == season).execute()
            for i in range(0, len(rows), 500):
                PlayerSeason.insert_many(rows[i:i + 500]).execute()
        print(f'{season}: {len(rows)} players')
        time.sleep(1.2)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Store past seasons of player totals for projections.')
    parser.add_argument('--first', default='2010-11')
    parser.add_argument('--last', default='2025-26')
    parser.add_argument('--force', action='store_true', help='re-fetch seasons already stored')
    args = parser.parse_args()
    main(args.first, args.last, args.force)
