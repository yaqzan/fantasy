"""
NBA API data fetching and database updating.
Pulls player data from the NBA API and updates the database.
Run this script daily to update player stats from the NBA API.
"""
from time import sleep
from datetime import datetime, date
from colorama import Fore, init
from nba_api.stats.static import players, teams
from nba_api.stats.endpoints import commonteamroster, playergamelog, leaguegamelog, leaguedashplayerstats, scheduleleaguev2, leaguestandingsv3
from tqdm import tqdm
from unidecode import unidecode

from fantasy_database import DB, Player, Game, Team
from fantasy_config import YEAR_START, YEAR_END, API_ATTRIBUTES

init(autoreset=True, convert=True)

SEASON = f'{YEAR_START}-{str(YEAR_END)[2:]}'  # e.g. 2026-27; flips on October 1
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

def compute_game_stats(df, techs=None, blka=0):
    """Compute stat totals from a game log DataFrame.

    techs: {game_id: technical fouls} for this player; blka: times blocked over the same games
    (the game log has no BLKA column, it comes from leaguedashplayerstats)."""
    cats = sum((df[c] >= 10).astype(int) for c in ['PTS', 'REB', 'AST', 'STL', 'BLK'])
    techs = techs or {}
    return {
        'GP': len(df),
        'FGA': df['FGA'].sum(), 'FGM': df['FGM'].sum(),
        'FTA': df['FTA'].sum(), 'FTM': df['FTM'].sum(),
        'FG3M': df['FG3M'].sum(), 'PTS': df['PTS'].sum(),
        'AST': df['AST'].sum(), 'REB': df['REB'].sum(),
        'STL': df['STL'].sum(), 'BLK': df['BLK'].sum(),
        'TOV': df['TOV'].sum(), 'BLKA': blka, 'PF': df['PF'].sum(),
        'TECH': sum(techs.get(gid, 0) for gid in df['GAME_ID']),
        'W': int((df['WL'] == 'W').sum()),
        'PLUS_MINUS': df['PLUS_MINUS'].sum(),
        'DD2': int((cats >= 2).sum()),
        'TD3': int((cats >= 3).sum()),
    }

def _team_names():
    """{NBA team id: full name as stored in teams/games, e.g. 'Los Angeles Clippers'}."""
    return {t['id']: t['full_name'] for t in teams.get_teams()}

def pull_game_schedule(season=SEASON):
    """Store the season's regular-season schedule in `games` (NBA schedule endpoint). Games in the
    season's date range that are no longer on the schedule (postponed, moved) are removed."""
    resp = nba_api_call(scheduleleaguev2.ScheduleLeagueV2, season=season)
    if resp is None:
        print(Fore.RED + f"Could not fetch the {season} schedule; games unchanged")
        return
    df = resp.get_data_frames()[0]
    df = df[df['gameId'].astype(str).str.startswith('002')]  # regular season only
    names = _team_names()
    wanted = set()
    for row in df.itertuples():
        home, away = names.get(row.homeTeam_teamId), names.get(row.awayTeam_teamId)
        if home and away:  # NBA Cup knockout slots are TBD (team id 0) until decided
            wanted.add((home, away, datetime.strptime(row.gameDateEst[:10], '%Y-%m-%d').date()))
    if not wanted:
        print(Fore.YELLOW + f"No {season} regular-season games published yet")
        return
    first, last = min(g[2] for g in wanted), max(g[2] for g in wanted)
    existing = {(g.team_home, g.team_away, g.date): g.id for g in Game.select().where(Game.date.between(first, last))}
    stale = [gid for key, gid in existing.items() if key not in wanted]
    new = [key for key in wanted if key not in existing]
    with DB.atomic():
        if stale:
            Game.delete().where(Game.id.in_(stale)).execute()
        for i in range(0, len(new), 500):
            Game.insert_many([{'team_home': h, 'team_away': a, 'date': d} for h, a, d in new[i:i + 500]]).execute()
    print(f"{season} schedule: {len(wanted)} games ({len(new)} added, {len(stale)} removed), {first} to {last}")

def pull_standings(season=SEASON):
    """Each team's record in `season`, from the first game (record_season says which season it
    is). projections.team_strength blends it with the preseason projection, so a 2-1 start
    barely moves a team."""
    resp = nba_api_call(leaguestandingsv3.LeagueStandingsV3, season=season)
    if resp is None:
        return
    df = resp.get_data_frames()[0]
    names = _team_names()
    if len(df) == 0:
        print(f"Standings: nothing published for {season} yet")
        return
    for row in df.itertuples():
        team = Team.get_or_none(Team.name == names.get(row.TeamID))
        if team:
            team.wins, team.losses = int(row.WINS), int(row.LOSSES)
            team.win_percentage = round(team.wins / (team.wins + team.losses), 3) if team.wins + team.losses else None
            team.record_season = season
            team.save()
    print(f"Standings updated for {len(df)} teams")

def update_team_rosters(season=SEASON):
    """Update team rosters from NBA API. Returns set of rostered player names.
    Does not clear teams if too few roster calls succeed (API outage). `season` defaults to the
    current one (flips Oct 1); pass the next season to pick up summer moves and rookies early."""
    nba_teams = teams.get_teams()
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
            position = row.get('POSITION')
            if isinstance(position, str) and position:  # blank (NaN) for some new signings
                player.pos, player.positions = position[0], position
            if created:
                print(Fore.GREEN + f"Created Player: {player.name}")
            player.save()
            rostered_players.add(player.name)

    if rostered_ids:
        Player.update(team=None).where(Player.id.not_in(list(rostered_ids))).execute()

    return rostered_players

def pull_times_blocked(season=SEASON):
    """{player id: (season, last 5, last 10) times blocked}. The game logs have no BLKA column;
    leaguedashplayerstats does. Its last-N filter counts the team's last N games, close enough."""
    out = {}
    for i, last_n in enumerate((0, 5, 10)):
        resp = nba_api_call(leaguedashplayerstats.LeagueDashPlayerStats, season=season,
                            per_mode_detailed='Totals', last_n_games=last_n)
        if resp is None:
            print(Fore.YELLOW + f"Times blocked (last {last_n or 'season'}) unavailable; keeping stored values")
            return None
        for row in resp.get_data_frames()[0][['PLAYER_ID', 'BLKA']].itertuples():
            out.setdefault(int(row.PLAYER_ID), [0, 0, 0])[i] = int(row.BLKA)
    return out

def apply_game_stats(player, player_games, techs, blka):
    """Write season / last 5 / last 10 totals from a player's game log rows onto the Player row.
    blka: (season, last 5, last 10) or None to keep the stored times-blocked values."""
    player_games = player_games.sort_values('GAME_DATE', ascending=False)
    kept_blka = (player.blka, player.blka_5, player.blka_10)
    overall = compute_game_stats(player_games, techs, blka[0] if blka else 0)
    last_5 = compute_game_stats(player_games.head(5), techs, blka[1] if blka else 0)
    last_10 = compute_game_stats(player_games.head(10), techs, blka[2] if blka else 0)
    for attr in API_ATTRIBUTES:
        setattr(player, attr.lower(), int(overall[attr]))
        setattr(player, f'{attr}_5'.lower(), int(last_5[attr]))
        setattr(player, f'{attr}_10'.lower(), int(last_10[attr]))
    if blka is None:
        player.blka, player.blka_5, player.blka_10 = kept_blka
    player.plus_minus = overall['PLUS_MINUS'] / overall['GP'] if overall['GP'] > 0 else 0
    player.plus_minus_5 = last_5['PLUS_MINUS'] / last_5['GP'] if last_5['GP'] > 0 else 0
    player.plus_minus_10 = last_10['PLUS_MINUS'] / last_10['GP'] if last_10['GP'] > 0 else 0
    if player.injured and player.gp is not None and overall['GP'] > player.gp:
        player.injured = False
        player.injured_games_to_miss = 0
    player.gp = overall['GP']

def update_single_player_stats(player_name, season=SEASON):
    """Update stats for a single player by name. Returns True on success, False on API failure."""
    from pull_technical_fouls import technicals_by_player
    try:
        player = Player.get(Player.name == player_name)
    except Player.DoesNotExist:
        print(f"Player '{player_name}' not found in database.")
        return True

    print(f"Updating stats for {player.name}...")
    resp = nba_api_call(playergamelog.PlayerGameLog, player_id=player.id, season=season)
    if resp is None:
        return False
    df = resp.get_data_frames()[0].rename(columns={'Game_ID': 'GAME_ID'})
    if len(df) == 0:
        player.gp = 0
    else:
        techs = technicals_by_player(df['GAME_ID']).get(player.id, {})
        apply_game_stats(player, df, techs, None)
    player.api_updated_at = datetime.now()
    player.save()
    print(f"Successfully updated stats for {player.name}!")
    return True

def update_all_player_stats(rostered_players=None, retry_rounds=3, season=SEASON, force=False):
    """Pull all player stats via a single bulk LeagueGameLog call instead of per-player requests.
    force: ignore the off-season gate and the once-a-day skip (backfills, a past season)."""
    from pull_technical_fouls import technicals_by_player
    if is_off_season() and not force: return

    if rostered_players is None:
        rostered_players = {p.name for p in Player.select().where(Player.team.is_null(False))}

    remaining = set(rostered_players)
    if not force:
        today_start = datetime.combine(date.today(), datetime.min.time())
        already_updated = {p.name for p in Player.select().where(
            (Player.api_updated_at >= today_start) & (Player.name.in_(rostered_players))
        )}
        remaining -= already_updated
        if already_updated:
            print(f"Skipping {len(already_updated)} players already updated today, {len(remaining)} remaining")
    if not remaining:
        print("All players already updated today!")
        return

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

    times_blocked = pull_times_blocked(season)
    techs = technicals_by_player(all_games['GAME_ID'].unique())
    print(f"Fetched {len(all_games)} game log entries, processing {len(remaining)} players...")
    remaining_db = {p.id: p for p in Player.select().where(Player.name.in_(remaining))}
    now = datetime.now()

    for pid, player in tqdm(remaining_db.items(), desc='Updating player stats...'):
        player_games = all_games[all_games['PLAYER_ID'] == pid]
        if len(player_games) == 0:
            player.gp = 0
        else:
            blka = tuple(times_blocked.get(pid, (0, 0, 0))) if times_blocked is not None else None
            apply_game_stats(player, player_games, techs.get(pid, {}), blka)
        player.api_updated_at = now
        player.save()

    print(f"\nAll {len(remaining_db)} players updated successfully!")

def pull_all_data(season=SEASON, force=False, skip_techs=False):
    """Pull all data from NBA API and update database."""
    from pull_technical_fouls import scan_technical_fouls
    print(f"Starting data pull for {season}...")
    pull_game_schedule(season)
    if not is_off_season() or force:
        pull_standings(season)
    rostered_players = update_team_rosters()
    if not skip_techs and (not is_off_season() or force):
        scan_technical_fouls(season)
    update_all_player_stats(rostered_players, season=season, force=force)

NOT_YET = 75  # exit code for --after-games: stats.nba.com doesn't have the whole night yet; try later


def night_is_in(day, expected_games, season=SEASON):
    """True once stats.nba.com's game log holds `expected_games` games on `day` (it lags the final
    buzzer; box scores stay empty while a game is on)."""
    stamp = day.strftime('%m/%d/%Y')
    resp = nba_api_call(leaguegamelog.LeagueGameLog, season=season, player_or_team_abbreviation='T',
                        season_type_all_star='Regular Season', date_from_nullable=stamp, date_to_nullable=stamp,
                        retries=3)
    found = resp.get_data_frames()[0]['GAME_ID'].nunique() if resp is not None else 0
    print(f'{day}: {found} of {expected_games} games in the NBA game log')
    return found >= expected_games


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Pull NBA schedule, standings, rosters and player stats.')
    parser.add_argument('player', nargs='*', help='update just this player (full name)')
    parser.add_argument('--season', default=SEASON, help=f'e.g. 2025-26 (default {SEASON})')
    parser.add_argument('--force', action='store_true', help='ignore the off-season gate and once-a-day skip')
    parser.add_argument('--skip-techs', action='store_true', help='skip the play-by-play technical foul scan')
    parser.add_argument('--rosters', action='store_true',
                        help="only set every player's team from --season's rosters (e.g. the next season's, "
                             'before Oct 1); stats untouched')
    parser.add_argument('--after-games', metavar='YYYY-MM-DD',
                        help='the nightly refresh (daily_leaders poller): exit 75 unless the NBA game log has '
                             '--games games on this date, else a full pull (forced past the once-a-day skip)')
    parser.add_argument('--games', type=int, default=1, help='games expected on --after-games')
    args = parser.parse_args()
    if args.after_games:
        import sys
        if not night_is_in(datetime.strptime(args.after_games, '%Y-%m-%d').date(), args.games, args.season):
            sys.exit(NOT_YET)
        pull_all_data(args.season, force=True, skip_techs=args.skip_techs)
    elif args.rosters:
        print(f'{len(update_team_rosters(args.season))} rostered players ({args.season} rosters)')
    elif args.player:
        update_single_player_stats(' '.join(args.player), args.season)
    else:
        pull_all_data(args.season, args.force, args.skip_techs)
