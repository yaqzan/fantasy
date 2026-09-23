from colorama import Fore, Back

from fantasy_config import CATEGORIES, CATEGORY_NAMES, INVERSE_CATEGORIES, HIGHLIGHTED_TEAMS
from fantasy_team_helper import get_my_team_players, get_all_taken_players, is_player_injured

def determine_colour(player_name):
    my_team_players = get_my_team_players()
    taken_players = get_all_taken_players()
    
    if player_name in HIGHLIGHTED_TEAMS:
        return Back.MAGENTA
    elif player_name in taken_players:
        return Fore.BLUE
    elif player_name in my_team_players:
        return Back.GREEN
    elif is_player_injured(player_name):
        return Back.RED
    else:
        return Fore.WHITE

def score_colour(score):
    if score > 50:
        if score >= 90: return Fore.GREEN + Back.GREEN
        elif score >= 80: return Fore.GREEN + Back.BLACK
        elif score >= 70: return Fore.GREEN
        elif score >= 60: return Fore.GREEN
        else: return Fore.GREEN
    elif score < 50:
        if score <= 10: return Fore.RED + Back.RED
        elif score <= 20: return Fore.RED + Back.BLACK
        elif score <= 30: return Fore.RED
        elif score <= 40: return Fore.RED
        else: return Fore.RED
    else:  # score == 50
        return Fore.WHITE

def print_matchup(my_lineup, my_stats, their_stats, player_stats, last_n_games=''):
    if not my_lineup:
        print(Fore.RED + "No valid lineup found. Must have 2 C's, 3 F's, and 3 G's.")
        return
    from fantasy_team_helper import get_my_team_players
    my_team_no_injuries = get_my_team_players()
    print(Fore.RED + ', '.join([item for item in my_team_no_injuries if item not in my_lineup]))
    print(Fore.YELLOW + ', '.join(my_lineup))
    their_stats['SCORE'] = 11 - my_stats['SCORE']
    print_score(Fore.YELLOW + '   MY TEAM', my_stats, their_stats, last_n_games)
    print_score(Fore.CYAN + 'THEIR TEAM', their_stats, my_stats, last_n_games)
    print('-----------------------------------------------------------------')

def print_score(player_name, my_stats, their_stats, last_n_games=''):
    print(f"{player_name}:", end='')
    for category in ['TOT', 'SCORE'] + CATEGORIES:
        category_last_n_games = category + last_n_games if category not in ['TOT', 'SCORE', 'WIN%'] else category
        if category_last_n_games not in my_stats or category_last_n_games not in their_stats:
            breakpoint()
        if category in INVERSE_CATEGORIES:
            colour = Fore.GREEN if my_stats[category_last_n_games] < their_stats[category_last_n_games] else (Fore.RED if my_stats[category_last_n_games] > their_stats[category_last_n_games] else Fore.WHITE)
        else:
            colour = Fore.GREEN if my_stats[category_last_n_games] > their_stats[category_last_n_games] else (Fore.RED if my_stats[category_last_n_games] < their_stats[category_last_n_games] else Fore.WHITE)
        formatted_number = ("{:.2f}" if category in ['TS%', 'PPS', 'FT%', 'EFG%'] else ("{}" if category in ['TOT', 'SCORE', 'WIN%'] else "{:.1f}")).format(my_stats[category_last_n_games])
        padding = ' ' * (4 - len(str(formatted_number)))
        print(' | ' + colour + f"{CATEGORY_NAMES[category]}: {formatted_number}{padding}", end='')
    print()

def print_player_stats(player_name, player_stats, games_played, last_n_games='', colour_override=None):
    delta = int(player_stats[player_name]['Z-SCORE'] - player_stats[player_name]['SCORE'])
    games = games_played[player_stats[player_name]['TEAM']] if player_stats[player_name]['TEAM'] != 'UNAVAILABLE' else 0
    z_score_colour = Fore.GREEN if delta > 0 else (Fore.RED if delta < 0 else Fore.WHITE)
    z_score = z_score_colour + str(int(player_stats[player_name]['Z-SCORE']))
    position = player_stats[player_name]['Pos']
    colour = colour_override if colour_override else Fore.GREEN if delta > 0 else (Fore.RED if delta < 0 else Fore.WHITE)
    prepadding = ' ' * (3 - len(str(player_stats[player_name][f'Z-RANK{last_n_games}'])))
    name_text = f"{prepadding}{player_stats[player_name][f'Z-RANK{last_n_games}']}) {games} | {position} {player_name}: {delta}"
    postpadding = '-' * (45 - len(name_text))
    print(colour + f"{name_text}{postpadding}", end='')
    colour = determine_colour(player_name)
    ovr_padding = ' ' * (3 - len(str(z_score)))
    print(colour + f" | OVR: {z_score}{ovr_padding})", end='')
    for category in CATEGORIES:
        category_last_n_games = category + last_n_games if category not in ['WIN%'] else category
        category_score = int(player_stats[player_name][f'SCORE-{category_last_n_games}'])
        formatted_number = "{:.2f}".format(player_stats[player_name][category_last_n_games]) if category in ['TS%', 'PPS', 'FT%', 'EFG%', 'VEFG%'] else "{:.1f}".format(player_stats[player_name][category_last_n_games])
        padding = ' ' * (7 - len(str(formatted_number)) - len(str(category_score)))
        category_score = score_colour(category_score) + f'{category_score}'
        print(colour + f" | {CATEGORY_NAMES[category]}: {formatted_number} ({category_score}){padding}", end='')
    print()

