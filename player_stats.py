"""
Player statistics calculation.
Builds player_stats dictionary from fantasy_database data.
"""
from math import pow
from fantasy_database import Player, Team
from fantasy_config import API_ATTRIBUTES, CATEGORIES, INVERSE_CATEGORIES, PUNT_CATEGORIES, EXP_FACTOR, NUM_STARTERS, NUM_TEAMS, FPOINTS_SCORING


TIME_PERIODS = ['', '_5', '_10']
VALID_POSITIONS = ['C', 'F', 'G']
STAT_AVG_WEIGHTS = {'': 0.5, '_10': 0.5, '_5': 0.0}
TEAM_DICT = {
    'LA Clippers': 'Los Angeles Clippers',
    'LA Lakers': 'Los Angeles Lakers',
}

# populates a full dictionary of player stats from the db
def load_player_stats():
    """
    Build player statistics dictionary from fantasy_database.
    
    Returns:
        dict: Player statistics keyed by player name
    """
    player_stats = {}
    team_win_percentages = {}
    
    for player in Player.select().where(Player.team.is_null(False)).where(Player.pos.is_null(False)).where(Player.gp > 0):
        team_name = TEAM_DICT.get(player.team, player.team)
        team = Team.get(name=team_name)
            
        player_stats[player.name] = {
            'TEAM': team_name, 
            'WIN%': team.win_percentage, 
            'Pos': player.pos
        }

        for n in TIME_PERIODS:
            gp = min(player.gp, int(n.replace('_', '')) if n else 100)
                
            for key in API_ATTRIBUTES:
                player_stats[player.name][f'{key}{n}'] = getattr(player, f'{key.lower()}{n}', 0) / gp if getattr(player, f'{key.lower()}{n}', 0) is not None else 0

            player_stats[player.name][f'PLUS_MINUS{n}'] = getattr(player, f'plus_minus{n}', 0)
            player_stats[player.name][f'AST-TOV{n}'] = player_stats[player.name][f'AST{n}'] - player_stats[player.name][f'TOV{n}']
            player_stats[player.name][f'PPS{n}'] = player_stats[player.name][f'PTS{n}'] / player_stats[player.name][f'FGA{n}'] if player_stats[player.name][f'FGA{n}'] != 0 else 0
            player_stats[player.name][f'NFT{n}'] = 2 * player_stats[player.name][f'FTM{n}'] - player_stats[player.name][f'FTA{n}']
            player_stats[player.name][f'FT%{n}'] = player_stats[player.name][f'FTM{n}'] / player_stats[player.name][f'FTA{n}'] if player_stats[player.name][f'FTA{n}'] != 0 else 0
            player_stats[player.name][f'TS%{n}'] = player_stats[player.name][f'PTS{n}'] / (2 * (player_stats[player.name][f'FGA{n}'] + (0.44 * player_stats[player.name][f'FTA{n}']))) if player_stats[player.name][f'FGA{n}'] != 0 or player_stats[player.name][f'FTA{n}'] != 0 else 0
            player_stats[player.name][f'EFG%{n}'] = (player_stats[player.name][f'FGM{n}'] + 0.5 * player_stats[player.name][f'FG3M{n}']) / player_stats[player.name][f'FGA{n}'] if player_stats[player.name][f'FGA{n}'] != 0 else 0

        for stat in API_ATTRIBUTES + ['PLUS_MINUS']:
            player_stats[player.name][f'{stat}_projected'] = sum((player_stats[player.name].get(f'{stat}{n}', 0) or 0) * STAT_AVG_WEIGHTS[n] for n in STAT_AVG_WEIGHTS)

        player_stats[player.name]['FG%_projected'] = (
            (player_stats[player.name].get('FGM_projected', 0) or 0) / (player_stats[player.name].get('FGA_projected', 0) or 1)
            if (player_stats[player.name].get('FGA_projected', 0) or 0) != 0 else 0
        )
        
        player_stats[player.name]['FT%_projected'] = (
            (player_stats[player.name].get('FTM_projected', 0) or 0) / (player_stats[player.name].get('FTA_projected', 0) or 1)
            if (player_stats[player.name].get('FTA_projected', 0) or 0) != 0 else 0
        )

        player_stats[player.name]['TS%_projected'] = (
            (player_stats[player.name].get('PTS_projected', 0) or 0) / 
            (2 * ((player_stats[player.name].get('FGA_projected', 0) or 0) + 
                  (0.44 * (player_stats[player.name].get('FTA_projected', 0) or 0))))
            if ((player_stats[player.name].get('FGA_projected', 0) or 0) != 0 or 
                (player_stats[player.name].get('FTA_projected', 0) or 0) != 0) else 0
        )
        player_stats[player.name]['EFG%_projected'] = (
            ((player_stats[player.name].get('FGM_projected', 0) or 0) + 
             0.5 * (player_stats[player.name].get('FG3M_projected', 0) or 0)) / 
            (player_stats[player.name].get('FGA_projected', 0) or 1)
            if (player_stats[player.name].get('FGA_projected', 0) or 0) != 0 else 0
        )
        player_stats[player.name]['AST-TOV_projected'] = (
            (player_stats[player.name].get('AST_projected', 0) or 0) - 
            (player_stats[player.name].get('TOV_projected', 0) or 0)
        )
        player_stats[player.name]['PPS_projected'] = (
            (player_stats[player.name].get('PTS_projected', 0) or 0) / 
            (player_stats[player.name].get('FGA_projected', 0) or 1)
            if (player_stats[player.name].get('FGA_projected', 0) or 0) != 0 else 0
        )
        player_stats[player.name]['NFT_projected'] = (
            2 * (player_stats[player.name].get('FTM_projected', 0) or 0) -
            (player_stats[player.name].get('FTA_projected', 0) or 0)
        )

    return player_stats

def calculate_team_totals(starters, player_stats, games_played, team_wins, last_n_games=''):
    total_stats = {'TOT': sum([games_played[player_stats[player]['TEAM']] for player in starters if player in player_stats and player_stats[player]['TEAM'] in games_played])}
    for category in CATEGORIES:
        if category in ['PTS', 'AST-TOV', 'REB', 'STL', 'BLK', 'BLKA', 'FG3M', 'DD2', 'PF', 'TOV', 'AST']:
            total_stats[f'{category}{last_n_games}'] = sum([player_stats[player][f'{category}{last_n_games}'] * games_played[player_stats[player]['TEAM']] for player in starters if player in player_stats and player_stats[player]['TEAM'] in games_played])
        elif category == 'PPS':
            total_stats[f'FGA{last_n_games}'] = sum([player_stats[player][f'FGA{last_n_games}'] * games_played[player_stats[player]['TEAM']] for player in starters if player in player_stats and player_stats[player]['TEAM'] in games_played])
            total_stats[f'PPS{last_n_games}'] = total_stats[f'PTS{last_n_games}'] / total_stats[f'FGA{last_n_games}']
        elif category == 'TS%':
            total_stats[f'FGA{last_n_games}'] = sum([player_stats[player][f'FGA{last_n_games}'] * games_played[player_stats[player]['TEAM']] for player in starters if player in player_stats and player_stats[player]['TEAM'] in games_played])
            total_stats[f'FTA{last_n_games}'] = sum([player_stats[player][f'FTA{last_n_games}'] * games_played[player_stats[player]['TEAM']] for player in starters if player in player_stats and player_stats[player]['TEAM'] in games_played])
            denominator = 2 * (total_stats[f'FGA{last_n_games}'] + (0.44 * total_stats[f'FTA{last_n_games}']))
            total_stats[f'TS%{last_n_games}'] = total_stats[f'PTS{last_n_games}'] / denominator if denominator != 0 else 0
        elif category == 'FT%':
            total_stats[f'FTM{last_n_games}'] = sum([player_stats[player][f'FTM{last_n_games}'] * games_played[player_stats[player]['TEAM']] for player in starters if player in player_stats and player_stats[player]['TEAM'] in games_played])
            total_stats[f'FTA{last_n_games}'] = sum([player_stats[player][f'FTA{last_n_games}'] * games_played[player_stats[player]['TEAM']] for player in starters if player in player_stats and player_stats[player]['TEAM'] in games_played])
            total_stats[f'FT%{last_n_games}'] = total_stats[f'FTM{last_n_games}'] / total_stats[f'FTA{last_n_games}']
        elif category == 'EFG%':
            total_stats[f'FGA{last_n_games}'] = sum([player_stats[player][f'FGA{last_n_games}'] * games_played[player_stats[player]['TEAM']] for player in starters if player in player_stats and player_stats[player]['TEAM'] in games_played])
            total_stats[f'FGM{last_n_games}'] = sum([player_stats[player][f'FGM{last_n_games}'] * games_played[player_stats[player]['TEAM']] for player in starters if player in player_stats and player_stats[player]['TEAM'] in games_played])
            total_stats[f'FG3M{last_n_games}'] = sum([player_stats[player][f'FG3M{last_n_games}'] * games_played[player_stats[player]['TEAM']] for player in starters if player in player_stats and player_stats[player]['TEAM'] in games_played])
            total_stats[f'EFG%{last_n_games}'] = (total_stats[f'FGM{last_n_games}'] + 0.5 * total_stats[f'FG3M{last_n_games}']) / total_stats[f'FGA{last_n_games}']
        elif category == 'NFT':
            total_stats[f'NFT{last_n_games}'] = sum((2 * player_stats[player][f'FTM{last_n_games}']) - player_stats[player][f'FTA{last_n_games}'] for player in starters if player in player_stats and player_stats[player]['TEAM'] in games_played)
        elif category == 'WIN%':
            total_stats['WIN%'] = sum([team_wins[player_stats[player]['TEAM']] for player in starters if player in player_stats and player_stats[player]['TEAM'] in team_wins])
        elif category == 'PLUS_MINUS':
            total_stats[f'PLUS_MINUS{last_n_games}'] = sum([player_stats[player][f'PLUS_MINUS{last_n_games}'] * games_played[player_stats[player]['TEAM']] for player in starters if player in player_stats and player_stats[player]['TEAM'] in games_played])
            total_stats[f'PLUS_MINUS_ABS{last_n_games}'] = sum([abs(player_stats[player][f'PLUS_MINUS{last_n_games}']) * games_played[player_stats[player]['TEAM']] for player in starters if player in player_stats and player_stats[player]['TEAM'] in games_played])

    return total_stats

def get_league_average_stat(player_stats, stat='EFG%', last_n_games= ''):
    values = [player_stats[player_name][f'{stat}{last_n_games}'] for player_name, _ in player_stats.items() if f'{stat}{last_n_games}' in player_stats[player_name]]
    return sum(values) / len(values) if values else 0

def calculate_overall_scores(player_stats):
    for category in CATEGORIES:
        for last_n_games in ['', '_5', '_10', '_projected']:
            category_last_n_games = category + last_n_games if category not in ['WIN%'] else category
            values = [player_stats[player][category_last_n_games] for player in player_stats if category_last_n_games in player_stats[player] and player_stats[player][category_last_n_games] is not None]
            if not values:
                continue
            max_value = max(values)
            min_value = min(values)
            needs_adjustment = (max_value > 0 and min_value < 0) or (max_value < 1 and min_value > 0)
            adjusted_max = max_value - min_value if needs_adjustment else max_value

            for player_name in player_stats:
                if category_last_n_games not in player_stats[player_name]:
                    player_stats[player_name][f'SCORE-{category_last_n_games}'] = 0
                    continue
                    
                player_value = player_stats[player_name][category_last_n_games]
                if player_value is None:
                    player_stats[player_name][f'SCORE-{category_last_n_games}'] = 0
                    continue
                    
                adjusted_value = player_value - min_value if needs_adjustment else player_value
                if category in INVERSE_CATEGORIES:
                    if player_value == 0:
                        player_stats[player_name][f'SCORE-{category_last_n_games}'] = 100
                    elif player_value == max_value:
                        player_stats[player_name][f'SCORE-{category_last_n_games}'] = 0
                    else:
                        denominator = adjusted_max / adjusted_value if adjusted_value != 0 else adjusted_max
                        player_stats[player_name][f'SCORE-{category_last_n_games}'] = 100 - ((1 / denominator) * 100)
                else:
                    if player_value == 0:
                        player_stats[player_name][f'SCORE-{category_last_n_games}'] = 0
                    elif player_value == max_value:
                        player_stats[player_name][f'SCORE-{category_last_n_games}'] = 100
                    else:
                        denominator = adjusted_max / adjusted_value if adjusted_value != 0 else adjusted_max
                        player_stats[player_name][f'SCORE-{category_last_n_games}'] = (1 / denominator) * 100
                if player_stats[player_name][f'SCORE-{category_last_n_games}'] > 100: 
                    player_stats[player_name][f'SCORE-{category_last_n_games}'] = 0

    for n in ['', '_5', '_10', '_projected']:
        for player_name, _ in player_stats.items():
            score = 0
            z_score = 0
            for category in CATEGORIES:
                category_last_n_games = category + n if category not in ['WIN%'] else category
                score += player_stats[player_name][f'SCORE-{category_last_n_games}']
                if category not in PUNT_CATEGORIES:
                    z_score += player_stats[player_name][f'SCORE-{category_last_n_games}']
            player_stats[player_name][f'SCORE{n}'] = score / len(CATEGORIES)
            player_stats[player_name][f'Z-SCORE{n}'] = z_score / (len(CATEGORIES) - len(PUNT_CATEGORIES))

        # Normalize scores
        max_z_score = max(player_stats[player][f'Z-SCORE{n}'] for player in player_stats)
        if max_z_score > 0:
            for player_name, _ in player_stats.items():
                denominator = max_z_score / player_stats[player_name][f'Z-SCORE{n}']
                player_stats[player_name][f'Z-SCORE{n}'] = (1 / denominator) * 100

        max_score = max(player_stats[player][f'SCORE{n}'] for player in player_stats)
        if max_score > 0:
            for player_name, _ in player_stats.items():
                denominator = max_score / player_stats[player_name][f'SCORE{n}']
                player_stats[player_name][f'SCORE{n}'] = (1 / denominator) * 100

        sorted_by_score = sorted(player_stats.items(), key=lambda kv: kv[1][f'SCORE{n}'], reverse=True)
        for i, (key, val) in enumerate(sorted_by_score, start=1):
            player_stats[key][f'RANK{n}'] = i

        sorted_by_z_score = sorted(player_stats.items(), key=lambda kv: kv[1][f'Z-SCORE{n}'], reverse=True)
        for i, (key, val) in enumerate(sorted_by_z_score, start=1):
            player_stats[key][f'Z-RANK{n}'] = i

    for days_n in ['', '_5', '_10']:
        average_efg = get_league_average_stat(player_stats, 'EFG%', days_n)
        average_fga = get_league_average_stat(player_stats, 'FGA', days_n)
        for player_name, _ in player_stats.items():
            volume = player_stats[player_name].get(f'FGA{days_n}', 0)
            efg_key = f'EFG%{days_n}'
            if efg_key in player_stats[player_name]:
                player_stats[player_name][f'VEFG%{days_n}'] = ((volume * player_stats[player_name][efg_key]) + (average_fga * average_efg)) / (volume + average_fga)
            else:
                player_stats[player_name][f'VEFG%{days_n}'] = 0

def calculate_fantasy_points(player_stats):
    for player_name, stats in player_stats.items():
        for n in ['', '_5', '_10', '_projected']:
            fpoints = 0
            for stat, multiplier in FPOINTS_SCORING.items():
                stat_key = f'{stat}{n}'
                fpoints += stats.get(stat_key, 0) * multiplier
            player_stats[player_name][f'FPOINTS{n}'] = round(fpoints, 2)
    
    for n in ['', '_5', '_10', '_projected']:
        sorted_by_fpoints = sorted(player_stats.items(), key=lambda kv: kv[1].get(f'FPOINTS{n}', 0), reverse=True)
        for i, (key, val) in enumerate(sorted_by_fpoints, start=1):
            player_stats[key][f'FPOINTS-RANK{n}'] = i

def calculate_auction_values(player_stats, num_teams=NUM_TEAMS, budget_per_team=200, roster_spots=NUM_STARTERS, exp_factor=EXP_FACTOR):
    total_budget = num_teams * budget_per_team
    total_drafted_players = num_teams * roster_spots

    sorted_players = sorted(player_stats.items(), key=lambda x: x[1]['SCORE'], reverse=True)
    top_players = sorted_players[:total_drafted_players]

    adjusted_scores = {player: pow(stats['SCORE'], exp_factor) for player, stats in top_players}
    total_adjusted_score = sum(adjusted_scores.values())

    total_spent = 0
    for player, stats in top_players:
        player_stats[player]['AUCTION_VALUE'] = int(max(round((adjusted_scores[player] / total_adjusted_score) * total_budget, 0), 1))
        # Note: AUCTION_INJURED was removed from config, so no injury adjustments
        total_spent += player_stats[player]['AUCTION_VALUE']

    adjustment_factor = total_budget / total_spent

    total_spent = 0
    for player, stats in top_players:
        adjusted_value = round(player_stats[player]['AUCTION_VALUE'] * adjustment_factor)
        player_stats[player]['AUCTION_VALUE'] = int(max(adjusted_value, 1))
        total_spent += player_stats[player]['AUCTION_VALUE']

    for player, stats in sorted_players[total_drafted_players:]:
        player_stats[player]['AUCTION_VALUE'] = 1

