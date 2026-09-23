from itertools import combinations
from colorama import Fore, init
from tqdm import tqdm
from datetime import timedelta, date
import defopt

from fileHelper import string_to_date, date_to_string
from fantasy_config import NUM_STARTERS, CATEGORIES, INVERSE_CATEGORIES, NUM_PICKUPS, TEAMNAMES, MIN_GUARDS, MIN_FORWARDS, MIN_CENTERS, FANTASY_SCHEDULE
from fantasy_database import Game, Team, Player
from player_stats import load_player_stats, calculate_team_totals, calculate_overall_scores
from display import print_player_stats, print_matchup
from fantasy_team_helper import get_my_team_players, get_all_my_team_players, get_opponent_team_players, get_available_players, get_current_fantasy_week_dates

init(autoreset=True, convert=True)

best_lineup, best_stats, best_score = [], {}, 0
best_pickup_lineup, best_pickup_stats, best_pickup_score = [], {}, 0

def reset_stats():
    global best_lineup, best_stats, best_score, best_pickup_lineup, best_pickup_stats, best_pickup_score
    best_lineup = []
    best_stats = {}
    best_score = 0
    best_pickup_lineup = []
    best_pickup_stats = {}
    best_pickup_score = 0

def calculate_team_schedules(week_start, week_end, team_win_percentages):
    """
    Calculate games played and projected wins for each team in the given week.
    
    :param week_start: Start date of the week
    :param week_end: End date of the week  
    :param team_win_percentages: Dictionary of team names to win percentages
    :return: tuple: (games_played dict, team_wins dict)
    """
    games_played = {}
    team_wins = {}
    for team in TEAMNAMES.values():
        games_played[team] = len(Game.select().where(Game.date >= week_start, Game.date <= week_end).where((Game.team_home == team) | (Game.team_away == team)))
        wins = 0
        for matchup in Game.select().where(Game.date >= week_start, Game.date <= week_end).where((Game.team_home == team) | (Game.team_away == team)):
            winning_team = matchup.team_home if team_win_percentages[matchup.team_home] > team_win_percentages[matchup.team_away] else (matchup.team_home if team_win_percentages[matchup.team_home] == team_win_percentages[matchup.team_away] else matchup.team_away)
            if team == winning_team:
                wins += 1
        team_wins[team] = wins
    return games_played, team_wins

def calculate_category_weight(category):
    weights = {
        'PTS': (0.15, 1.0),
        'FG3M': (0.25, 0.9),
        'AST': (0.25, 0.9),
        'TOV': (0.35, 0.80),
        'AST-TOV': (0.30, 0.85),
        'REB': (0.20, 0.95),
        'STL': (0.35, 0.80),
        'BLK': (0.35, 0.80),
        'BLKA': (0.35, 0.80),
        'EFG%': (0.10, 1.0),
        'TS%': (0.12, 0.95),
        'PF': (0.30, 0.85),
        'PLUS_MINUS': (0.25, 0.90),
        'DD2': (0.30, 0.80),
        'NFT': (0.20, 0.95)
    }
    return weights.get(category, (0.25, 1.0))

def calculate_lineup_score(the_stats, their_stats, last_n_games=''):
    """
    Calculate the score and value for a given lineup against opponent stats.
    
    :param dict the_stats: Stats for the lineup being evaluated
    :param dict their_stats: Stats for the opponent lineup
    :param str last_n_games: Suffix for last N games stats
    :return: tuple: (lineup_value, score)
    """
    weighted_margins = {}
    the_score = 0
    
    for category in CATEGORIES:
        category_last_n_games = category + last_n_games if category != 'WIN%' else category
        
        stat, their_stat = the_stats[category_last_n_games], their_stats[category_last_n_games]
        denominator = (abs(stat) + abs(their_stat) 
                     if category == 'PLUS_MINUS' 
                     else abs(their_stat) if category in INVERSE_CATEGORIES 
                     else abs(stat))
        
        if category in INVERSE_CATEGORIES:
            margin = (-1.0 if denominator == 0 and stat < 0 
                     else 1.0 if denominator == 0 
                     else (their_stat - stat) / denominator)
        else:
            margin = (1.0 if denominator == 0 and their_stat < 0 
                     else -1.0 if denominator == 0 
                     else (stat - their_stat) / denominator)
        
        variance, weight = calculate_category_weight(category)
        adjusted_margin = margin * (1 - variance) * weight
        
        weighted_margins[category] = adjusted_margin
        if margin > 0:
            the_score += 1

    winning_margins = [m for m in weighted_margins.values() if m > 0]
    
    if not winning_margins:
        return float('-inf'), 0

    risk_penalty = 0
    for category, margin in weighted_margins.items():
        if margin > 0:
            variance, _ = calculate_category_weight(category)
            if margin < 0.1 and variance > 0.25:
                risk_penalty += variance * 0.5

    min_margin = min(winning_margins)
    avg_margin = sum(winning_margins) / len(winning_margins)
    
    lineup_value = (
        the_score * 15 +
        min_margin * 8 +
        avg_margin * 4 -
        risk_penalty * 2
    )

    return lineup_value, the_score

def calculate_best_lineup(player_pool, their_stats, player_stats, games_played, team_wins, last_n_games='', undroppable_players=None):
    global best_lineup, best_stats, best_score
    best_lineup = None
    best_stats = None
    best_value = float('-inf')
    best_score = 0
    
    if undroppable_players is None:
        undroppable_players = []

    for the_starters in combinations(player_pool, NUM_STARTERS):
        # Ensure all undroppable players are in the lineup
        if undroppable_players and not all(undroppable in the_starters for undroppable in undroppable_players if undroppable in player_pool):
            continue
            
        position_counts = {'C': 0, 'F': 0, 'G': 0}
        for player in the_starters:
            if player_stats[player]['Pos'] not in position_counts:
                continue
            position_counts[player_stats[player]['Pos']] += 1

        if position_counts['G'] < MIN_GUARDS or position_counts['F'] < MIN_FORWARDS or position_counts['C'] < MIN_CENTERS:
            continue

        the_stats = calculate_team_totals(the_starters, player_stats, games_played, team_wins, last_n_games)
        lineup_value, the_score = calculate_lineup_score(the_stats, their_stats, last_n_games)

        if lineup_value > best_value:
            best_value = lineup_value
            best_lineup = the_starters
            best_stats = the_stats
            best_score = the_score
            best_stats['SCORE'] = best_score

    return best_value

def calculate_best_pickup_lineup(my_team_no_injuries, their_stats, player_stats, games_played, team_wins, last_n_games='', undroppable_players=None):
    global best_pickup_lineup, best_pickup_stats, best_pickup_score
    available_players = get_available_players(player_stats)
    best_pickup_value = calculate_best_lineup(my_team_no_injuries, their_stats, player_stats, games_played, team_wins, last_n_games, undroppable_players)
    best_pickup_lineup, best_pickup_stats = [], {}
    for pickup_players in tqdm(list(combinations(list(available_players), NUM_PICKUPS)), desc='Calculating best pickup lineup for last ' + last_n_games + ' games'):
        trial_pool = my_team_no_injuries + list(pickup_players)
        current_value = calculate_best_lineup(trial_pool, their_stats, player_stats, games_played, team_wins, last_n_games, undroppable_players)
        
        if current_value > best_pickup_value:
            best_pickup_value = current_value
            best_pickup_lineup = best_lineup
            best_pickup_stats = best_stats
            best_pickup_score = best_score


def process_pickups(suffix, description, my_team_no_injuries, available_players, their_team_starting, player_stats, games_played, team_wins):
    reset_stats()
    their_stats = calculate_team_totals(their_team_starting, player_stats, games_played, team_wins, suffix)
    best_pickup_value = calculate_best_lineup(my_team_no_injuries, their_stats, player_stats, games_played, team_wins, suffix)
    best_pickup_lineup, best_pickup_stats = [], {}
    
    for pickup_players in tqdm(list(combinations(list(available_players), NUM_PICKUPS)), desc=description):
        trial_pool = my_team_no_injuries + list(pickup_players)
        current_value = calculate_best_lineup(trial_pool, their_stats, player_stats, games_played, team_wins, suffix)
        
        if current_value > best_pickup_value:
            best_pickup_value = current_value
            best_pickup_lineup = best_lineup
            best_pickup_stats = best_stats

    if not best_pickup_lineup:
        print(Fore.RED + 'No good pickups found')
        return
    
    print(Fore.WHITE + f'\n{suffix[1:]}-Game Pickup Results:')
    my_team_players = get_my_team_players()
    [print_player_stats(player_name, player_stats, games_played, suffix, Fore.GREEN) for player_name in best_pickup_lineup if player_name not in my_team_players]
    print_matchup(best_pickup_lineup, best_pickup_stats, their_stats, player_stats, suffix)


def get_analysis_data(timeframe, week_start=None, week_end=None, opponent_team_name=None, pickup=False, pickup_timeframe=None):
    """
    Get structured analysis data for API consumption.
    
    :param str timeframe: Timeframe to analyze - 'projected' (default), '5' (last 5 games), '10' (last 10 games), or 'season' (full season)
    :param date week_start: Start date of the week (optional)
    :param date week_end: End date of the week (optional)
    :param str opponent_team_name: Name of the opponent team (optional)
    :param bool pickup: If True, analyze pickups instead of current roster (optional)
    :return: dict: Structured analysis data
    """

    # Use provided parameters or get current week info
    if not week_start or not week_end or not opponent_team_name:
        their_team_starting = get_opponent_team_players()
        if not their_team_starting:
            return {'error': 'Could not determine opponent team from fantasy schedule'}
        
        week_start, week_end, opponent_team_name = get_current_fantasy_week_dates()
    else:
        # Get opponent team players for the specified week
        # Convert date object to string for the helper function
        week_start_str = week_start.strftime('%Y-%m-%d') if hasattr(week_start, 'strftime') else week_start
        their_team_starting = get_opponent_team_players(week_start_str)
        if not their_team_starting:
            return {'error': f'Could not determine opponent team players for week starting {week_start}'}
    rank_suffix = f'_{timeframe}' if timeframe in ['5', '10', 'projected'] else ''
    team_win_percentages = {team.name: team.win_percentage for team in Team.select()}
    player_stats = load_player_stats()
    calculate_overall_scores(player_stats)

    if not week_start or not week_end:
        week_start = date.today()
        week_end = week_start + timedelta(days=6)
    
    games_played, team_wins = calculate_team_schedules(week_start, week_end, team_win_percentages)

    # Limit opponent team to best NUM_STARTERS players based on overall rank (excluding injured already done)
    if len(their_team_starting) > NUM_STARTERS:
        # Sort by overall rank (lower rank = better) and take top NUM_STARTERS
        # Use projected rank as default, or timeframe-specific rank if available
        rank_key = f'Z-RANK{rank_suffix}' if rank_suffix else 'Z-RANK'
        # Fallback to projected rank if timeframe-specific rank not available
        their_team_starting = sorted(
            their_team_starting, 
            key=lambda p: player_stats.get(p, {}).get(rank_key) or player_stats.get(p, {}).get('Z-RANK_projected', 999) or 999
        )[:NUM_STARTERS]
    
    # Calculate their_stats using rank_suffix for non-pickup case (will be recalculated for pickup case)
    their_stats = calculate_team_totals(their_team_starting, player_stats, games_played, team_wins, rank_suffix)

    my_team_no_injuries = get_my_team_players()
    
    # Get undroppable players - these must always be in the lineup
    undroppable_players = [p.name for p in Player.select().where(Player.undroppable == 1)]

    if pickup:
        # Use pickup_timeframe for calculating pickups, timeframe for stat comparison
        pickup_rank_suffix = f'_{pickup_timeframe}' if pickup_timeframe and pickup_timeframe in ['5', '10', 'projected'] else rank_suffix
        # Calculate their_stats using pickup_rank_suffix for finding best pickups
        their_stats_for_pickup = calculate_team_totals(their_team_starting, player_stats, games_played, team_wins, pickup_rank_suffix)
        calculate_best_pickup_lineup(list(my_team_no_injuries), their_stats_for_pickup, player_stats, games_played, team_wins, pickup_rank_suffix, undroppable_players)
    else:
        calculate_best_lineup(list(my_team_no_injuries), their_stats, player_stats, games_played, team_wins, rank_suffix, undroppable_players)

    the_lineup = best_pickup_lineup if pickup else best_lineup
    
    # Handle case where no lineup was found (e.g., team has fewer players than starters)
    if the_lineup is None or (not pickup and len(my_team_no_injuries) < NUM_STARTERS):
        # For base table with incomplete roster, just use all available players
        the_lineup = list(my_team_no_injuries)
    
    # Calculate their_stats using rank_suffix (timeframe) for comparison
    # This ensures both the_stats and their_stats use the same suffix for comparison
    their_stats = calculate_team_totals(their_team_starting, player_stats, games_played, team_wins, rank_suffix)
    
    # Recalculate the_stats using rank_suffix (timeframe) for comparison, not pickup_rank_suffix
    # This ensures both the_stats and their_stats use the same suffix for comparison
    if the_lineup:
        the_stats = calculate_team_totals(the_lineup, player_stats, games_played, team_wins, rank_suffix)
        # Recalculate the score using the correct timeframe (rank_suffix) for comparison
        _, the_score = calculate_lineup_score(the_stats, their_stats, rank_suffix)
    else:
        the_stats = {}
        the_score = 0
    
    # Calculate player game counts after best lineup is determined
    my_team_player_games, their_team_player_games = {}, {}
    for player in the_lineup:
        my_team_player_games[player] = games_played[player_stats[player]['TEAM']]
    for player in their_team_starting:
        their_team_player_games[player] = games_played[player_stats[player]['TEAM']]

    pickups = [p for p in the_lineup if p not in my_team_no_injuries]
    # Filter out undroppable players from drops list
    drops = [p for p in my_team_no_injuries if p not in the_lineup and p not in undroppable_players]

    matchup_data = {
        'opponent': opponent_team_name if opponent_team_name else 'Unknown',
        'score': the_score,
        'week_start': week_start.strftime('%Y-%m-%d') if week_start else None,
        'week_end': week_end.strftime('%Y-%m-%d') if week_end else None,
        'my_team_player_games': my_team_player_games,
        'their_team_player_games': their_team_player_games,
        'timeframe': timeframe,
        'is_pickup': pickup,
        'pickups': pickups,
        'drops': drops,
        'categories': {}
    }
    
    # Calculate category margins
    for category in CATEGORIES:
        category_last_n_games = category + rank_suffix if category != 'WIN%' else category
        
        if the_stats and their_stats and category_last_n_games in the_stats and category_last_n_games in their_stats:
            my_stat = the_stats[category_last_n_games]
            their_stat = their_stats[category_last_n_games]
            if category in INVERSE_CATEGORIES:
                margin = their_stat - my_stat
            else:
                margin = my_stat - their_stat
            
            matchup_data['categories'][category] = {
                'your_team': my_stat,
                'opponent': their_stat,
                'margin': margin
            }

    # Get undroppable player names for frontend filtering
    undroppable_player_names = [p.name for p in Player.select().where(Player.undroppable == 1)]
    
    # Get available players (not on any fantasy team and not injured) for frontend filtering
    available_players_list = list(get_available_players(player_stats))
    
    # Get all my team players (including injured) for dropdown
    all_my_team_players = get_all_my_team_players()
    
    return {
        'matchup': matchup_data,
        'timeframe': timeframe,
        'best_stats': the_stats,
        'their_stats': their_stats,
        'best_lineup': the_lineup,
        'player_stats': player_stats,
        'games_played': games_played,
        'team_wins': team_wins,
        'fantasy_schedule': FANTASY_SCHEDULE,
        'undroppable_players': undroppable_player_names,
        'available_players': available_players_list,
        'all_my_team_players': all_my_team_players,
        'num_starters': NUM_STARTERS,
    }

def main():
    """Run pickup analysis for all timeframes"""
    print("Starting pickup analysis...")
    try:
        # Get opponent team from fantasy schedule
        their_team_starting = get_opponent_team_players()
        if not their_team_starting:
            print(Fore.RED + "Error: Could not determine opponent team from fantasy schedule")
            return

        # Use the shared data loading logic
        analysis_data = get_analysis_data('projected')
        if 'error' in analysis_data:
            print(Fore.RED + f"Error: {analysis_data['error']}")
            return
            
        player_stats = analysis_data['player_stats']
        games_played = analysis_data['games_played']
        team_wins = analysis_data['team_wins']
        my_team_no_injuries = get_my_team_players()
        available_players = analysis_data['available_players']
        
        print(Fore.CYAN + f'Opponent Team: {", ".join(their_team_starting)}\n')
        
        process_pickups('_5', "Calculating best pickups based on last 5 games...", my_team_no_injuries, available_players, their_team_starting, player_stats, games_played, team_wins)
        process_pickups('_10', "Calculating best pickups based on last 10 games...", my_team_no_injuries, available_players, their_team_starting, player_stats, games_played, team_wins)
        process_pickups('', "Calculating best overall pickups...", my_team_no_injuries, available_players, their_team_starting, player_stats, games_played, team_wins)
        process_pickups('_projected', "Calculating best projected pickups...", my_team_no_injuries, available_players, their_team_starting, player_stats, games_played, team_wins)
        
    except Exception as e:
        print(Fore.RED + f"Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    main()

