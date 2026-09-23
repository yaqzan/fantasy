"""
NBA API data fetching and database updating.
Pulls player data from the NBA API and updates the database.
Run this script daily to update player stats from the NBA API.
"""
from time import sleep
from datetime import datetime, date
from colorama import Fore, init
from nba_api.stats.static import players, teams
from nba_api.stats.endpoints import commonteamroster, playergamelog, leaguegamelog
from tqdm import tqdm
from unidecode import unidecode

from fantasy_database import Player, Game, Team, FantasyTeam, FantasyTeamPlayer
from fantasy_config import MY_TEAM_ABV, YEAR_START, YEAR_END
from fantrax_client import FantraxClient

init(autoreset=True, convert=True)

API_ATTRIBUTES = ['FGA', 'FGM', 'FTA', 'FTM', 'FG3M', 'PTS', 'AST', 'REB', 'STL', 'BLK', 'TOV', 'BLKA', 'DD2', 'TD3', 'PF']
# stats.nba.com rate-limits hard; short delays + short read timeouts cause read timeouts and empty rosters.
API_CALL_DELAY = 1.75
NBA_TIMEOUT = (20, 150)

def nba_api_call(func, *args, retries=7, timeout=NBA_TIMEOUT, **kwargs):
    """Call an NBA API endpoint with retry/backoff. Returns None if all retries exhausted."""
    kwargs.setdefault('timeout', timeout)
    for attempt in range(retries):
        try:
            result = func(*args, **kwargs)
            sleep(API_CALL_DELAY)
            return result
        except Exception as ex:
            if attempt + 1 >= retries:
                print(Fore.RED + f"NBA API call {func.__name__} failed after {retries} attempts: {ex}")
                break
            wait = min(12 * (attempt + 1), 90)
            print(Fore.YELLOW + f"API call failed (attempt {attempt+1}/{retries}): {ex} - retrying in {wait}s")
            sleep(wait)
    return None

def is_off_season():
    """Check if current date is in off-season (April 20 - October 15)."""
    current_date = date.today()
    return (current_date.month == 4 and current_date.day > 20) or \
           (current_date.month in [5, 6, 7, 8, 9]) or \
           (current_date.month == 10 and current_date.day < 15)

def compute_game_stats(df):
    """Compute stat totals from a game log DataFrame."""
    cats = sum((df[c] >= 10).astype(int) for c in ['PTS', 'REB', 'AST', 'STL', 'BLK'])
    return {
        'GP': len(df),
        'FGA': df['FGA'].sum(), 'FGM': df['FGM'].sum(),
        'FTA': df['FTA'].sum(), 'FTM': df['FTM'].sum(),
        'FG3M': df['FG3M'].sum(), 'PTS': df['PTS'].sum(),
        'AST': df['AST'].sum(), 'REB': df['REB'].sum(),
        'STL': df['STL'].sum(), 'BLK': df['BLK'].sum(),
        'TOV': df['TOV'].sum(), 'BLKA': 0, 'PF': df['PF'].sum(),
        'PLUS_MINUS': df['PLUS_MINUS'].sum(),
        'DD2': int((cats >= 2).sum()),
        'TD3': int((cats >= 3).sum()),
    }

def get_my_team_players():
    """Get all player names on my fantasy team."""
    try:
        my_team = FantasyTeam.get(FantasyTeam.abv == MY_TEAM_ABV)
        return {player.player_name for player in FantasyTeamPlayer.select().where(
            FantasyTeamPlayer.fantasy_team_id == my_team.id
        )}
    except FantasyTeam.DoesNotExist:
        return set()

def is_player_on_my_team(player_name, my_team_players):
    """Check if a player is on my fantasy team using cached player set."""
    return player_name in my_team_players

def pull_league_updates():
    """Pull league updates from Basketball Reference."""
    if is_off_season(): return
    from fantraxapi import League
    client = FantraxClient(auto_login=True)
    breakpoint()
    client.refresh_login(ignore_saved_cookie=True)
    league = client.league
    breakpoint()
    print()

def pull_game_schedule():
    """Pull game schedule from Basketball Reference if needed."""
    if Game.select().where(Game.date >= date(YEAR_START, 9, 1)).count() >= 1200: return
    from scraper import get_html, selenium_get
    from fileHelper import string_to_date
    for month in ['october', 'november', 'december', 'january', 'february', 'march', 'april']:
        url = f'https://www.basketball-reference.com/leagues/NBA_{YEAR_END}_games-{month}.html'
        soup = get_html(selenium_get(url), selenium=True)
        for tr in soup.find('table', {'id': 'schedule'}).tbody.find_all('tr'):
            if tr.find('th', {'data-stat':'date_game'}).text.strip() == 'Date': continue
            game_date = string_to_date(tr.find('th', {'data-stat':'date_game'}).text.strip())
            team_away = tr.find('td', {'data-stat':'visitor_team_name'}).text.strip()
            team_home = tr.find('td', {'data-stat':'home_team_name'}).text.strip()
            Game.build(team_home, team_away, game_date)

def pull_standings():
    """Pull team standings from Basketball Reference."""
    if is_off_season(): return

    from scraper import get_html, selenium_get
    from fantasy_config import STANDINGS_URL
    soup = get_html(selenium_get(STANDINGS_URL), selenium=True)
    for conference in ['all_confs_standings_E', 'all_confs_standings_W']:
        for tr in soup.find('div', {'id':conference}).tbody.find_all('tr'):
            team = Team.get(name=tr.a.text.strip())
            if tr.find('td', {"data-stat":"win_loss_pct"}).text:
                team.win_percentage = float(tr.find('td', {"data-stat":"win_loss_pct"}).text)
                team.wins = int(tr.find('td', {"data-stat":"wins"}).text)
                team.losses = int(tr.find('td', {"data-stat":"losses"}).text)
                team.save()

def update_team_rosters():
    """Update team rosters from NBA API. Returns set of rostered player names.
    Does not clear teams if too few roster calls succeed (API outage)."""
    nba_teams = teams.get_teams()
    season = f'{YEAR_START}-{str(YEAR_END)[2:]}'
    roster_rows = []
    for team in nba_teams:
        roster = nba_api_call(commonteamroster.CommonTeamRoster, team_id=team['id'], season=season)
        if roster is None:
            roster_rows.append((team, None))
            continue
        df = roster.get_data_frames()[0]
        roster_rows.append((team, df if len(df) > 0 else None))

    n_teams = len(nba_teams)
    ok = sum(1 for _, df in roster_rows if df is not None)
    need = max(1, (4 * n_teams + 4) // 5) if n_teams else 1
    if n_teams == 0 or ok < need:
        print(Fore.RED + f"Roster fetch incomplete ({ok}/{n_teams} teams); leaving Player.team unchanged.")
        return {p.name for p in Player.select(Player.name).where(Player.team.is_null(False))}

    rostered_players = set()
    rostered_ids = set()
    for team, df in roster_rows:
        if df is None:
            continue
        for _, row in df.iterrows():
            pid = int(row['PLAYER_ID'])
            rostered_ids.add(pid)
            player, created = Player.get_or_create(id=pid)
            if team['full_name']:
                player.team = team['full_name']
            player.name = unidecode(row['PLAYER'])
            if row.get('POSITION'):
                player.pos = row['POSITION'][0]
            if created:
                print(Fore.GREEN + f"Created Player: {player.name}")
            player.save()
            rostered_players.add(player.name)

    if rostered_ids:
        Player.update(team=None).where(Player.id.not_in(list(rostered_ids))).execute()

    return rostered_players

def pull_player_fantasy_data(player_id):
    """Pull fantasy data for a specific player from NBA API. Not implemented: playerfantasyprofile was removed from nba_api; use pull_player_stats_from_gamelog."""
    raise NotImplementedError("playerfantasyprofile removed from nba_api; use pull_player_stats_from_gamelog")

def pull_player_stats_from_gamelog(player_id):
    """Pull a single player's stats from their game log (used for CLI single-player updates)."""
    season = f"{YEAR_START}-{str(YEAR_END)[2:]}"
    resp = nba_api_call(playergamelog.PlayerGameLog, player_id=player_id, season=season)
    if resp is None:
        return False
    df = resp.get_data_frames()[0]
    if len(df) == 0:
        return None
    df = df.sort_values('GAME_DATE', ascending=False)
    return {
        'overall': compute_game_stats(df),
        'last_5': compute_game_stats(df.head(5)),
        'last_10': compute_game_stats(df.head(10)),
    }

def update_single_player_stats(player_name):
    """Update stats for a single player by name. Returns True on success, False on API failure."""
    try:
        player = Player.get(Player.name == player_name)
    except Player.DoesNotExist:
        print(f"Player '{player_name}' not found in database.")
        return True

    print(f"Updating stats for {player.name}...")
    stats_data = pull_player_stats_from_gamelog(player.id)
    if stats_data is False:
        return False

    if stats_data:
        overall, last_5, last_10 = stats_data['overall'], stats_data['last_5'], stats_data['last_10']
        for attr in API_ATTRIBUTES:
            setattr(player, attr.lower(), int(overall[attr]))
            setattr(player, f'{attr}_5'.lower(), int(last_5[attr]))
            setattr(player, f'{attr}_10'.lower(), int(last_10[attr]))
        player.plus_minus = overall['PLUS_MINUS'] / overall['GP'] if overall['GP'] > 0 else 0
        player.plus_minus_5 = last_5['PLUS_MINUS'] / last_5['GP'] if last_5['GP'] > 0 else 0
        player.plus_minus_10 = last_10['PLUS_MINUS'] / last_10['GP'] if last_10['GP'] > 0 else 0
        if player.injured and player.gp is not None and overall['GP'] > player.gp:
            player.injured = False
            player.injured_games_to_miss = 0
        player.gp = overall['GP']
    else:
        player.gp = 0

    player.api_updated_at = datetime.now()
    player.save()
    print(f"Successfully updated stats for {player.name}!")
    return True

def update_all_player_stats(rostered_players=None, retry_rounds=3):
    """Pull all player stats via a single bulk LeagueGameLog call instead of per-player requests."""
    if is_off_season(): return

    if rostered_players is None:
        rostered_players = {p.name for p in Player.select().where(Player.team.is_null(False))}

    today_start = datetime.combine(date.today(), datetime.min.time())
    already_updated = {p.name for p in Player.select().where(
        (Player.api_updated_at >= today_start) & (Player.name.in_(rostered_players))
    )}
    remaining = rostered_players - already_updated
    if already_updated:
        print(f"Skipping {len(already_updated)} players already updated today, {len(remaining)} remaining")
    if not remaining:
        print("All players already updated today!")
        return

    season = f"{YEAR_START}-{str(YEAR_END)[2:]}"
    all_games = None
    for attempt in range(retry_rounds + 1):
        print(f"Fetching bulk league game log (attempt {attempt+1}/{retry_rounds+1})...")
        resp = nba_api_call(leaguegamelog.LeagueGameLog, season=season,
                            player_or_team_abbreviation='P',
                            season_type_all_star='Regular Season')
        if resp is not None:
            all_games = resp.get_data_frames()[0]
            if len(all_games) > 0:
                break
        if attempt < retry_rounds:
            wait = 60 * (attempt + 1)
            print(Fore.YELLOW + f"Bulk fetch failed, retrying in {wait}s...")
            sleep(wait)

    if all_games is None or len(all_games) == 0:
        print(Fore.RED + "Failed to fetch league game log after all attempts")
        return

    print(f"Fetched {len(all_games)} game log entries, processing {len(remaining)} players...")
    remaining_db = {p.id: p for p in Player.select().where(Player.name.in_(remaining))}
    now = datetime.now()

    for pid, player in tqdm(remaining_db.items(), desc='Updating player stats...'):
        player_games = all_games[all_games['PLAYER_ID'] == pid]
        if len(player_games) == 0:
            player.gp = 0
        else:
            player_games = player_games.sort_values('GAME_DATE', ascending=False)
            overall = compute_game_stats(player_games)
            last_5 = compute_game_stats(player_games.head(5))
            last_10 = compute_game_stats(player_games.head(10))
            for attr in API_ATTRIBUTES:
                setattr(player, attr.lower(), int(overall[attr]))
                setattr(player, f'{attr}_5'.lower(), int(last_5[attr]))
                setattr(player, f'{attr}_10'.lower(), int(last_10[attr]))
            player.plus_minus = overall['PLUS_MINUS'] / overall['GP'] if overall['GP'] > 0 else 0
            player.plus_minus_5 = last_5['PLUS_MINUS'] / last_5['GP'] if last_5['GP'] > 0 else 0
            player.plus_minus_10 = last_10['PLUS_MINUS'] / last_10['GP'] if last_10['GP'] > 0 else 0
            if player.injured and player.gp is not None and overall['GP'] > player.gp:
                player.injured = False
                player.injured_games_to_miss = 0
            player.gp = overall['GP']
        player.api_updated_at = now
        player.save()

    print(f"\nAll {len(remaining_db)} players updated successfully!")

def update_player_data():
    """Alias for update_all_player_stats for backward compatibility."""
    update_all_player_stats()

def pull_all_data():
    """Pull all data from NBA API and update database."""
    print("Starting data pull...")
    # pull_league_updates()
    # pull_game_schedule()
    # pull_standings()
    rostered_players = update_team_rosters()
    update_all_player_stats(rostered_players)

if __name__ == '__main__':
    import sys
    if len(sys.argv) > 1:
        player_name = ' '.join(sys.argv[1:])
        update_single_player_stats(player_name)
    else:
        pull_all_data()
