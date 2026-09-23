"""
Fantasy team helper functions.
Handles database operations for fantasy teams and players.
"""
from datetime import datetime, date, timedelta
from fantasy_database import FantasyTeam, FantasyTeamPlayer, Player
from fantasy_config import MY_TEAM_ABV, FANTASY_SCHEDULE, FANTASY_SCHEDULE_DICT
from fileHelper import string_to_date, date_to_string

def get_week_info_from_schedule(week_start_param):
    """
    Get week information from fantasy schedule based on week_start date.
    
    :param str week_start_param: Week start date in 'YYYY-MM-DD' format
    :return: tuple: (week_start, week_end, opponent) or (None, None, None) if not found
    """
    try:
        # Quick lookup using dictionary
        opponent = FANTASY_SCHEDULE_DICT.get(week_start_param)
        if not opponent:
            return None, None, None
            
        week_start = datetime.strptime(week_start_param, '%Y-%m-%d').date()
        
        # Find the index for week_end calculation
        for i, (schedule_date, _) in enumerate(FANTASY_SCHEDULE):
            if schedule_date == week_start_param:
                # Calculate week_end based on next week's start date
                if i + 1 < len(FANTASY_SCHEDULE):
                    next_week_start = datetime.strptime(FANTASY_SCHEDULE[i + 1][0], '%Y-%m-%d').date()
                    week_end = next_week_start - timedelta(days=1)
                else:
                    # Last week of schedule - assume 7 days
                    week_end = week_start + timedelta(days=6)
                
                return week_start, week_end, opponent
        
        return None, None, None
        
    except ValueError:
        return None, None, None

def get_current_fantasy_week_dates(target_date=None):
    """
    Get the start and end dates for the current fantasy week based on the schedule.
    Handles variable week lengths and edge cases.
    
    Args:
        target_date (str, optional): Date in 'YYYY-MM-DD' format. If None, uses current date.
    
    Returns:
        tuple: (week_start, week_end, opponent) as date objects and string, or (None, None, None) if no week found
    """
    if target_date is None:
        target_date = date.today().strftime('%Y-%m-%d')
    
    # Convert target_date to date object for comparison
    target_date_obj = string_to_date(target_date)
    
    # Handle case where we're before the first game
    if target_date_obj < string_to_date(FANTASY_SCHEDULE[0][0]):
        week_start = string_to_date(FANTASY_SCHEDULE[0][0])
        # Calculate week length based on next week or default to 7
        if len(FANTASY_SCHEDULE) > 1:
            next_week_start = string_to_date(FANTASY_SCHEDULE[1][0])
            week_length = (next_week_start - week_start).days
        else:
            week_length = 7
        week_end = week_start + timedelta(days=week_length - 1)
        opponent = FANTASY_SCHEDULE[0][1]
        return week_start, week_end, opponent
    
    # Find the current week
    for i, (start_date_str, opponent) in enumerate(FANTASY_SCHEDULE):
        week_start = string_to_date(start_date_str)
        
        # Calculate week length based on next week or default to 7
        if i + 1 < len(FANTASY_SCHEDULE):
            next_week_start = string_to_date(FANTASY_SCHEDULE[i + 1][0])
            week_length = (next_week_start - week_start).days
        else:
            week_length = 7
        
        week_end = week_start + timedelta(days=week_length - 1)
        
        # If we're within this week
        if week_start <= target_date_obj <= week_end:
            return week_start, week_end, opponent
        
        # If we're after this week but before the next week
        if target_date_obj > week_end:
            # Check if there's a next week
            if i + 1 < len(FANTASY_SCHEDULE):
                next_week_start = string_to_date(FANTASY_SCHEDULE[i + 1][0])
                # If we're between weeks, use the next week
                if target_date_obj < next_week_start:
                    next_opponent = FANTASY_SCHEDULE[i + 1][1]
                    # Calculate next week length
                    if i + 2 < len(FANTASY_SCHEDULE):
                        next_next_week_start = string_to_date(FANTASY_SCHEDULE[i + 2][0])
                        next_week_length = (next_next_week_start - next_week_start).days
                    else:
                        next_week_length = 7
                    next_week_end = next_week_start + timedelta(days=next_week_length - 1)
                    return next_week_start, next_week_end, next_opponent
            else:
                # We're after the last week, use the last week
                return week_start, week_end, opponent
    
    # If we're after the last week, use the last week
    last_week = FANTASY_SCHEDULE[-1]
    week_start = string_to_date(last_week[0])
    week_length = 7  # Default to 7 for the last week
    week_end = week_start + timedelta(days=week_length - 1)
    opponent = last_week[1]
    return week_start, week_end, opponent

def get_my_team_players():
    """
    Get all players on my fantasy team excluding injured players.
    
    Returns:
        list: List of player names on my team (excluding injured)
    """
    try:
        my_team = FantasyTeam.get(FantasyTeam.abv == MY_TEAM_ABV)
        players = (Player
                  .select()
                  .join(FantasyTeamPlayer, on=(Player.id == FantasyTeamPlayer.player_id))
                  .where(FantasyTeamPlayer.fantasy_team_id == my_team.id)
                  .where(Player.injured == 0))
        return [player.name for player in players]
    except FantasyTeam.DoesNotExist:
        print(f"Warning: Fantasy team with abbreviation '{MY_TEAM_ABV}' not found in database")
        return []
    except Exception as e:
        print(f"Error getting my team players: {e}")
        return []

def get_all_my_team_players():
    """
    Get all players on my fantasy team including injured players.
    
    Returns:
        list: List of player names on my team (including injured)
    """
    try:
        my_team = FantasyTeam.get(FantasyTeam.abv == MY_TEAM_ABV)
        players = (Player
                  .select()
                  .join(FantasyTeamPlayer, on=(Player.id == FantasyTeamPlayer.player_id))
                  .where(FantasyTeamPlayer.fantasy_team_id == my_team.id))
        return [player.name for player in players]
    except FantasyTeam.DoesNotExist:
        print(f"Warning: Fantasy team with abbreviation '{MY_TEAM_ABV}' not found in database")
        return []
    except Exception as e:
        print(f"Error getting all my team players: {e}")
        return []

def get_opponent_team_players(target_date=None):
    """
    Get opponent team players based on fantasy schedule and current date.
    
    Args:
        target_date (str, optional): Date in 'YYYY-MM-DD' format. If None, uses current date.
    
    Returns:
        list: List of player names on opponent team (excluding injured)
    """
    if target_date is None:
        target_date = date.today().strftime('%Y-%m-%d')
    
    # Get the current week info including opponent
    week_start, week_end, opponent_abv = get_current_fantasy_week_dates(target_date)
    
    if not opponent_abv:
        print(f"Warning: No opponent found for date {target_date}")
        return []
    
    try:
        opponent_team = FantasyTeam.get(FantasyTeam.abv == opponent_abv)
        players = (Player
                  .select()
                  .join(FantasyTeamPlayer, on=(Player.id == FantasyTeamPlayer.player_id))
                  .where(FantasyTeamPlayer.fantasy_team_id == opponent_team.id)
                  .where(Player.injured == 0))
        return [player.name for player in players]
    except FantasyTeam.DoesNotExist:
        print(f"Warning: Fantasy team with abbreviation '{opponent_abv}' not found in database")
        return []
    except Exception as e:
        print(f"Error getting opponent team players: {e}")
        return []

def get_all_taken_players():
    """
    Get all players that are on any fantasy team (taken players).
    
    Returns:
        list: List of all taken player names
    """
    try:
        players = (Player
                  .select()
                  .join(FantasyTeamPlayer, on=(Player.id == FantasyTeamPlayer.player_id))
                  .distinct())
        return [player.name for player in players]
    except Exception as e:
        print(f"Error getting taken players: {e}")
        return []

def get_injured_players():
    """
    Get all injured players from the database.
    
    Returns:
        list: List of injured player names
    """
    try:
        injured_players = Player.select(Player.name).where(Player.injured == 1)
        return [player.name for player in injured_players]
    except Exception as e:
        print(f"Error getting injured players: {e}")
        return []

def is_player_injured(player_name):
    """
    Check if a specific player is injured.
    
    Args:
        player_name (str): Name of the player to check
        
    Returns:
        bool: True if player is injured, False otherwise
    """
    try:
        player = Player.get(Player.name == player_name)
        return player.injured == 1
    except Player.DoesNotExist:
        return False
    except Exception as e:
        print(f"Error checking injury status for {player_name}: {e}")
        return False

def get_available_players(player_stats):
    """
    Get all available players (not on any fantasy team and not injured).
    
    Args:
        player_stats (dict): Player statistics dictionary
        
    Returns:
        set: Set of available player names
    """
    taken_players = get_all_taken_players()
    injured_players = get_injured_players()
    available = set()
    
    for player_name, _ in player_stats.items():
        if player_name not in taken_players and player_name not in injured_players:
            available.add(player_name)
    
    return available
