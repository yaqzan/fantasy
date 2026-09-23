"""
DEPRECATED: This file is deprecated.

Please use the new scripts instead:
- For data pulling: python pull_data.py
- For analysis: python analyze.py

See README.md for full documentation.
"""
import sys
import warnings
from colorama import init, Fore
from datetime import timedelta
import defopt

from fileHelper import string_to_date, date_to_string
from fantasy_config import TEAMNAMES
from fantasy_database import Game
from player_stats import load_player_stats
from api_client import update_player_data
from player_stats import calculate_overall_scores, calculate_auction_values, calculate_team_totals
from display import print_player_stats
from lineup_optimizer import reset_stats, calculate_best_lineup, process_pickups, best_lineup, best_stats
from fantasy_team_helper import get_my_team_players, get_available_players, get_current_fantasy_week_dates

init(autoreset=True, convert=True)

warnings.warn(
    "main.py is deprecated. Use 'pull_data.py' for data pulling or 'analyze.py' for analysis.",
    DeprecationWarning,
    stacklevel=2
)

def main(command=None):
    """
    DEPRECATED - Use analyze.py instead.
    
    Trader

    :param str command: what to do with trader. Can be 'pull', '5', '10'
    """
    print("\n" + "="*80)
    print("WARNING: main.py is DEPRECATED")
    print("="*80)
    print("Please use: python analyze.py [command] --timeframe=[projected|5|10|season]")
    print("="*80 + "\n")
    # ## Pull game schedules (run once per season)
    # from scraper import request_url, get_html, selenium_get, get_cookie
    # for month in ['october', 'november', 'december', 'january', 'february', 'march', 'april']:
    #     url = f'https://www.basketball-reference.com/leagues/NBA_2026_games-{month}.html'
    #     # soup = get_html(request_url(url))
    #     soup = get_html(selenium_get(url, cookies = get_cookie('bbref')), selenium=True)
    #     for tr in soup.find('table', {'id': 'schedule'}).tbody.find_all('tr'):
    #         if tr.find('th', {'data-stat':'date_game'}).text.strip() == 'Date': continue
    #         date = string_to_date(tr.find('th', {'data-stat':'date_game'}).text.strip())
    #         team_away = tr.find('td', {'data-stat':'visitor_team_name'}).text.strip()
    #         team_home = tr.find('td', {'data-stat':'home_team_name'}).text.strip()
    #         Game.build(team_home, team_away, date)

    team_win_percentages = {team: 0.5 for team in TEAMNAMES.values()}
    

    
    if command == 'pull':
        update_player_data()
        return
    
    player_stats = load_player_stats()
    calculate_overall_scores(player_stats)

    # Get current fantasy week dates
    week_start, week_end, opponent = get_current_fantasy_week_dates()
    if not week_start or not week_end:
        print("Warning: Could not determine current fantasy week")
        from datetime import date
        week_start = date.today()
        week_end = week_start + timedelta(days=6)
    
    games_played = {}
    team_wins = {}
    for team in Team.select():
        games_played[team.name] = len(Game.select().where(Game.date >= week_start, Game.date <= week_end).where((Game.team_home == team.name) | (Game.team_away == team.name)))
        wins = 0
        for matchup in Game.select().where(Game.date >= week_start, Game.date <= week_end).where((Game.team_home == team.name) | (Game.team_away == team.name)):
            winning_team = matchup.team_home if team_win_percentages[matchup.team_home] > team_win_percentages[matchup.team_away] else (matchup.team_home if team_win_percentages[matchup.team_home] == team_win_percentages[matchup.team_away] else matchup.team_away)
            if team.name == winning_team:
                wins += 1
        team_wins[team.name] = wins

    calculate_auction_values(player_stats)

    # Get my team players from database
    my_team_players = get_my_team_players()
    
    # Get available players (not on any fantasy team and not injured)
    available_players = get_available_players(player_stats)

    print('Available Players: ', str(len(available_players)))

    rank_suffix = f'_5' if command == '5' else f'_10' if command == '10' else '_projected'
    sorted_ranks = sorted(player_stats.items(), key=lambda kv: kv[1][f"AUCTION_VALUE"], reverse=False)[-200:]
    append_players = sorted([(p, player_stats[p]) for p in my_team_players if p not in [r[0] for r in sorted_ranks]], key=lambda x: x[1][f"Z-RANK{rank_suffix}"], reverse=True)
    for key, val in append_players + sorted_ranks:
        print_player_stats(key, player_stats, games_played, rank_suffix)

    # Lineup optimization (uncomment to use)
    # my_team_no_injuries = get_my_team_players()
    # # for suffix in ['_5', '_10', '', '_projected']:
    # for suffix in ['_projected']:
    #     print(Fore.CYAN + f'{suffix[1:]}-Game Lineup:', end='')
    #     from fantasy_team_helper import get_opponent_team_players
    #     their_team_starting = get_opponent_team_players()
    #     their_stats = calculate_team_totals(their_team_starting, player_stats, games_played, team_wins, suffix)
    #     calculate_best_lineup(my_team_no_injuries, their_stats, player_stats, games_played, team_wins, suffix)
    #     from display import print_matchup
    #     print_matchup(best_lineup, best_stats, their_stats, player_stats, suffix)

    # Pickup analysis (uncomment to use)
    # from fantasy_team_helper import get_opponent_team_players
    # their_team_starting = get_opponent_team_players()
    # process_pickups('_5', "Calculating best pickups based on last 5 games...", my_team_no_injuries, available_players, their_team_starting, player_stats, games_played, team_wins)
    # process_pickups('_10', "Calculating best pickups based on last 10 games...", my_team_no_injuries, available_players, their_team_starting, player_stats, games_played, team_wins)
    # process_pickups('', "Calculating best overall pickups...", my_team_no_injuries, available_players, their_team_starting, player_stats, games_played, team_wins)
    # process_pickups('_projected', "Calculating best projected pickups...", my_team_no_injuries, available_players, their_team_starting, player_stats, games_played, team_wins)
    # print(Fore.CYAN + ', '.join(their_team_starting))

if __name__ == '__main__':
    defopt.run(main)

