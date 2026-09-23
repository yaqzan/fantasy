"""
Efficient daily stats updater using Game table to get schedule and only process relevant players
"""
from datetime import datetime, date
from nba_api.stats.static import players, teams
from nba_api.stats.endpoints import playergamelog, commonteamroster
from fantasy_database import DailyPlayerStats, Player, Game, DB
from fantasy_config import FPOINTS_SCORING
import pandas as pd
import time

def calculate_fantasy_points(stats):
    """Calculate fantasy points based on scoring system"""
    fpoints = 0
    for stat, value in stats.items():
        if stat in FPOINTS_SCORING and value is not None:
            fpoints += value * FPOINTS_SCORING[stat]
    return round(fpoints, 2)

def get_teams_for_date(target_date):
    """Get teams that played on the target date from Game table"""
    games = Game.select().where(Game.date == target_date)
    teams = set()
    
    for game in games:
        teams.add(game.team_home)
        teams.add(game.team_away)
    
    print(f"Found {len(games)} games on {target_date}")
    for game in games:
        print(f"  {game.team_away} @ {game.team_home}")
    
    return list(teams)

def get_players_for_teams(team_names):
    """Get players from our database that play for the specified teams"""
    if not team_names:
        return []
    
    print(f"Looking for players in our database from teams: {team_names}")
    
    # Get players from our database that play for these teams
    team_players = []
    for team_name in team_names:
        players_for_team = Player.select().where(Player.team == team_name)
        team_players.extend(list(players_for_team))
        print(f"  Found {len(players_for_team)} players from {team_name} in our database")
    
    print(f"Found {len(team_players)} total players from teams that played on the target date")
    return team_players

def update_daily_stats_efficient(target_date):
    """Update daily stats efficiently by only processing players from teams that played"""
    print(f"Updating daily stats for {target_date} using efficient approach")
    
    # Get teams that played on this date
    teams = get_teams_for_date(target_date)
    
    if not teams:
        print(f"No games found for {target_date}")
        return
    
    # Get players from those teams only
    team_players = get_players_for_teams(teams)
    
    if not team_players:
        print("No players found for teams that played on this date")
        return
    
    stats_updated = 0
    
    for i, player in enumerate(team_players):
        try:
            player_id = player.id
            player_name = player.name
            team_name = player.team or 'Unknown'
            
            print(f"Processing player {i+1}/{len(team_players)}: {player_name} ({team_name})")
            
            # Add delay to avoid rate limiting
            time.sleep(0.5)  # Reduced delay since we're processing fewer players
            
            # Get game log for the player
            game_log = playergamelog.PlayerGameLog(player_id=player_id, season='2025-26')
            df = game_log.get_data_frames()[0]
            
            if len(df) == 0:
                print(f"  No games found for {player_name}")
                continue
            
            # Filter for the target date
            df['GAME_DATE'] = pd.to_datetime(df['GAME_DATE'])
            day_games = df[df['GAME_DATE'].dt.date == target_date]
            
            if len(day_games) == 0:
                print(f"  No games on {target_date} for {player_name}")
                continue
            
            # Process each game for this player on this date
            for _, game in day_games.iterrows():
                matchup = game['MATCHUP']
                game_id = game['Game_ID']
                
                # Calculate fantasy points
                fantasy_points = calculate_fantasy_points({
                    'FGA': game['FGA'],
                    'FGM': game['FGM'],
                    'FTA': game['FTA'],
                    'FTM': game['FTM'],
                    'FG3M': game['FG3M'],
                    'PTS': game['PTS'],
                    'REB': game['REB'],
                    'AST': game['AST'],
                    'STL': game['STL'],
                    'BLK': game['BLK'],
                    'TOV': game['TOV']
                })
                
                # Create or update daily stats
                daily_stats, created = DailyPlayerStats.get_or_create(
                    player_id=player_id,
                    game_date=target_date,
                    game_id=game_id,
                    defaults={
                        'player_name': player_name,
                        'team': team_name,
                        'matchup': matchup,
                        'minutes': game['MIN'],
                        'fgm': game['FGM'],
                        'fga': game['FGA'],
                        'fg_pct': game['FG_PCT'],
                        'fg3m': game['FG3M'],
                        'fg3a': game['FG3A'],
                        'fg3_pct': game['FG3_PCT'],
                        'ftm': game['FTM'],
                        'fta': game['FTA'],
                        'ft_pct': game['FT_PCT'],
                        'oreb': game['OREB'],
                        'dreb': game['DREB'],
                        'reb': game['REB'],
                        'ast': game['AST'],
                        'stl': game['STL'],
                        'blk': game['BLK'],
                        'tov': game['TOV'],
                        'pf': game['PF'],
                        'pts': game['PTS'],
                        'plus_minus': game['PLUS_MINUS'],
                        'fantasy_points': fantasy_points,
                        'created_at': datetime.now()
                    }
                )
                
                if not created:
                    # Update existing record
                    daily_stats.player_name = player_name
                    daily_stats.team = team_name
                    daily_stats.matchup = matchup
                    daily_stats.minutes = game['MIN']
                    daily_stats.fgm = game['FGM']
                    daily_stats.fga = game['FGA']
                    daily_stats.fg_pct = game['FG_PCT']
                    daily_stats.fg3m = game['FG3M']
                    daily_stats.fg3a = game['FG3A']
                    daily_stats.fg3_pct = game['FG3_PCT']
                    daily_stats.ftm = game['FTM']
                    daily_stats.fta = game['FTA']
                    daily_stats.ft_pct = game['FT_PCT']
                    daily_stats.oreb = game['OREB']
                    daily_stats.dreb = game['DREB']
                    daily_stats.reb = game['REB']
                    daily_stats.ast = game['AST']
                    daily_stats.stl = game['STL']
                    daily_stats.blk = game['BLK']
                    daily_stats.tov = game['TOV']
                    daily_stats.pf = game['PF']
                    daily_stats.pts = game['PTS']
                    daily_stats.plus_minus = game['PLUS_MINUS']
                    daily_stats.fantasy_points = fantasy_points
                    daily_stats.save()
                
                stats_updated += 1
                print(f"  ✓ {player_name}: {game['PTS']} pts, {game['REB']} reb, {game['AST']} ast, {fantasy_points} FP")
                
        except Exception as e:
            print(f"  ✗ Error processing player {player_name}: {e}")
            continue
    
    print(f"\nUpdated {stats_updated} player stats for {target_date}")

def get_daily_stats_for_date(target_date):
    """Get daily stats for a specific date"""
    stats = DailyPlayerStats.select().where(DailyPlayerStats.game_date == target_date).order_by(DailyPlayerStats.fantasy_points.desc())
    return list(stats)

if __name__ == '__main__':
    import sys
    if len(sys.argv) > 1:
        target_date = datetime.strptime(sys.argv[1], '%Y-%m-%d').date()
        update_daily_stats_efficient(target_date)
    else:
        update_daily_stats_efficient(date.today())
