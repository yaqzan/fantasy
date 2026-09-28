"""Technical fouls per player per game, scanned from stats.nba.com play-by-play.

No bulk NBA endpoint reports technicals, so each game's play-by-play is fetched once (about 3s a
game with the rate-limit delay) and recorded in `pbp_scanned_games`; later runs only fetch new
games. A full season backfill is ~1,230 games, about an hour. pull_api_data.py then sums the
counts into Player.tech / tech_5 / tech_10.

    python pull_technical_fouls.py [--season 2025-26] [--limit N]
"""
import argparse
from datetime import datetime

from colorama import Fore, init
from nba_api.stats.endpoints import leaguegamelog, playbyplayv3
from tqdm import tqdm

from fantasy_config import YEAR_START, YEAR_END
from fantasy_database import DB, ScannedGame, TechnicalFoul, Player

init(autoreset=True, convert=True)


def season_games(season, nba_api_call):
    """{game_id: game_date} for every regular-season game played so far."""
    resp = nba_api_call(leaguegamelog.LeagueGameLog, season=season, player_or_team_abbreviation='T',
                        season_type_all_star='Regular Season')
    if resp is None:
        return None
    df = resp.get_data_frames()[0]
    return {row.GAME_ID: datetime.strptime(row.GAME_DATE, '%Y-%m-%d').date()
            for row in df[['GAME_ID', 'GAME_DATE']].drop_duplicates().itertuples()}


def game_technicals(game_id, nba_api_call):
    """{personId: technical fouls} for one game, or None if the fetch failed. Team and coach
    technicals (personId not a player) are filtered out by the caller."""
    resp = nba_api_call(playbyplayv3.PlayByPlayV3, game_id=game_id)
    if resp is None:
        return None
    df = resp.get_data_frames()[0]
    if len(df) == 0:
        return None
    fouls = df[(df['actionType'] == 'Foul') & df['subType'].str.contains('Technical', case=False, na=False)]
    counts = {}
    for person_id in fouls['personId']:
        counts[int(person_id)] = counts.get(int(person_id), 0) + 1
    return counts


def scan_technical_fouls(season=None, limit=None):
    """Scan every not-yet-scanned game of the season. Returns (scanned, remaining)."""
    from pull_api_data import nba_api_call
    season = season or f'{YEAR_START}-{str(YEAR_END)[2:]}'
    games = season_games(season, nba_api_call)
    if games is None:
        print(Fore.RED + f'Could not list {season} games; technical fouls not updated')
        return 0, None
    done = {g.game_id for g in ScannedGame.select(ScannedGame.game_id).where(ScannedGame.game_id.in_(list(games)))} if games else set()
    todo = sorted(gid for gid in games if gid not in done)
    if limit:
        todo = todo[:limit]
    if not todo:
        print(f'Technical fouls: all {len(games)} {season} games already scanned')
        return 0, 0
    player_ids = {p.id for p in Player.select(Player.id)}
    scanned = 0
    for game_id in tqdm(todo, desc=f'Scanning {season} play-by-play for technicals'):
        counts = game_technicals(game_id, nba_api_call)
        if counts is None:
            continue  # retried later
        with DB.atomic():
            for person_id, count in counts.items():
                if person_id in player_ids:
                    TechnicalFoul.replace(game_id=game_id, player_id=person_id, game_date=games[game_id],
                                          count=count).execute()
            ScannedGame.replace(game_id=game_id, game_date=games[game_id], scanned_at=datetime.now()).execute()
        scanned += 1
    remaining = len(games) - len(done) - scanned
    print(f'Technical fouls: scanned {scanned} games, {remaining} {season} games left')
    return scanned, remaining


def technicals_by_player(game_ids):
    """{player_id: {game_id: count}} for the given games."""
    out = {}
    game_ids = list(game_ids)
    for i in range(0, len(game_ids), 1000):
        for row in TechnicalFoul.select().where(TechnicalFoul.game_id.in_(game_ids[i:i + 1000])):
            out.setdefault(row.player_id, {})[row.game_id] = row.count
    return out


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--season', help='e.g. 2025-26 (default: the current season)')
    parser.add_argument('--limit', type=int, help='scan at most N games this run')
    args = parser.parse_args()
    scan_technical_fouls(args.season, args.limit)
