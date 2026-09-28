"""
Player statistics calculation.
Builds player_stats dictionary from fantasy_database data.
"""
from math import pow
from fantasy_database import Player, Team, Game
from fantasy_config import API_ATTRIBUTES, EXP_FACTOR, FPOINTS_SCORING
from leagues import CATEGORY_CATALOG


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
    team_win_percentages = {team.name: team.win_percentage for team in Team.select()}

    for player in Player.select().where(Player.team.is_null(False)).where(Player.pos.is_null(False)).where(Player.gp > 0):
        team_name = TEAM_DICT.get(player.team, player.team)
        player_stats[player.name] = {
            'TEAM': team_name,
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
            # Wins per game played; before player wins were ingested, fall back to the team's win %.
            player_stats[player.name][f'WIN%{n}'] = player_stats[player.name][f'W{n}'] if player.w is not None else (team_win_percentages.get(team_name) or 0)

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
        player_stats[player.name]['WIN%_projected'] = sum(player_stats[player.name][f'WIN%{n}'] * STAT_AVG_WEIGHTS[n] for n in STAT_AVG_WEIGHTS)
        player_stats[player.name]['NFT_projected'] = (
            2 * (player_stats[player.name].get('FTM_projected', 0) or 0) -
            (player_stats[player.name].get('FTA_projected', 0) or 0)
        )

    return player_stats

def _log5(p_a, p_b):
    """Chance team A beats team B from their win percentages."""
    p_a, p_b = min(max(p_a, 0.05), 0.95), min(max(p_b, 0.05), 0.95)
    return p_a * (1 - p_b) / (p_a * (1 - p_b) + p_b * (1 - p_a))

def week_schedule(week_start, week_end):
    """{NBA team: {game date: chance of winning}} for every game in the week."""
    win_pct = {team.name: team.win_percentage if team.win_percentage is not None else 0.5 for team in Team.select()}
    schedule = {}
    for game in Game.select().where(Game.date >= week_start, Game.date <= week_end):
        p_home = _log5(win_pct.get(game.team_home, 0.5), win_pct.get(game.team_away, 0.5))
        schedule.setdefault(game.team_home, {})[game.date] = p_home
        schedule.setdefault(game.team_away, {})[game.date] = 1 - p_home
    return schedule

def team_games(schedule):
    """{NBA team: games this week} from week_schedule()."""
    return {team: len(days) for team, days in schedule.items()}

def player_week_games(roster, player_stats, schedule, league, last_n_games='', unavailable=()):
    """Games and expected wins each rostered player contributes over the week.

    Daily lineups: each day only the best `active` players whose team plays that day count (best =
    Z-SCORE for the timeframe), so a deep bench adds little. Weekly lineups: every game of every
    player in `roster` counts. Players in `unavailable` (injured) contribute nothing.
    """
    games = {p: 0 for p in roster}
    wins = {p: 0.0 for p in roster}
    players = [p for p in roster if p in player_stats and p not in unavailable]
    if not league.daily_lineups:
        for p in players:
            days = schedule.get(player_stats[p]['TEAM'], {})
            games[p], wins[p] = len(days), sum(days.values())
        return games, wins
    by_day = {}
    for p in sorted(players, key=lambda p: player_stats[p].get(f'Z-SCORE{last_n_games}', 0), reverse=True):
        for day, p_win in schedule.get(player_stats[p]['TEAM'], {}).items():
            by_day.setdefault(day, []).append((p, p_win))
    for entries in by_day.values():
        for p, p_win in entries[:league.active_slots]:
            games[p] += 1
            wins[p] += p_win
    return games, wins

def calculate_team_totals(roster, player_stats, player_games, player_wins, categories, last_n_games=''):
    """Category totals for a group of players. Counting stats are per-game rate x games; ratios are
    built from summed components; wins are summed expected wins. Pass games of 1 for per-game totals."""
    players = [p for p in roster if p in player_stats]

    def total(stat):
        return sum((player_stats[p].get(f'{stat}{last_n_games}', 0) or 0) * player_games.get(p, 0) for p in players)

    totals = {'TOT': sum(player_games.get(p, 0) for p in players)}
    for category in categories:
        key = f'{category}{last_n_games}'
        if category == 'WIN%':
            totals[key] = sum(player_wins.get(p, 0) for p in players)
        elif category == 'TS%':
            denominator = 2 * (total('FGA') + 0.44 * total('FTA'))
            totals[key] = total('PTS') / denominator if denominator else 0
        elif category == 'EFG%':
            fga = total('FGA')
            totals[key] = (total('FGM') + 0.5 * total('FG3M')) / fga if fga else 0
        elif category == 'FT%':
            fta = total('FTA')
            totals[key] = total('FTM') / fta if fta else 0
        elif category == 'PPS':
            fga = total('FGA')
            totals[key] = total('PTS') / fga if fga else 0
        elif category == 'NFT':
            totals[key] = 2 * total('FTM') - total('FTA')
        else:
            totals[key] = total(category)
    return totals

def get_league_average_stat(player_stats, stat='EFG%', last_n_games= ''):
    values = [player_stats[player_name][f'{stat}{last_n_games}'] for player_name, _ in player_stats.items() if f'{stat}{last_n_games}' in player_stats[player_name]]
    return sum(values) / len(values) if values else 0

def calculate_overall_scores(player_stats, league, punt_categories=()):
    """Per-category 0-100 scores and the overall Z-SCORE / Z-RANK over the league's categories.
    Punted categories still get a score but leave the Z-SCORE."""
    categories = league.categories
    inverse_categories = league.inverse_categories
    for category in categories:
        for last_n_games in ['', '_5', '_10', '_projected']:
            category_last_n_games = category + last_n_games
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
                if category in inverse_categories:
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
            for category in categories:
                category_last_n_games = category + n
                score += player_stats[player_name].get(f'SCORE-{category_last_n_games}', 0)
                if category not in punt_categories:
                    z_score += player_stats[player_name].get(f'SCORE-{category_last_n_games}', 0)
            player_stats[player_name][f'SCORE{n}'] = score / len(categories)
            scored = len([c for c in categories if c not in punt_categories])
            player_stats[player_name][f'Z-SCORE{n}'] = z_score / scored if scored else 0

        # Normalize scores
        max_z_score = max(player_stats[player][f'Z-SCORE{n}'] for player in player_stats)
        if max_z_score > 0:
            for player_name, _ in player_stats.items():
                player_stats[player_name][f'Z-SCORE{n}'] = player_stats[player_name][f'Z-SCORE{n}'] / max_z_score * 100

        max_score = max(player_stats[player][f'SCORE{n}'] for player in player_stats)
        if max_score > 0:
            for player_name, _ in player_stats.items():
                player_stats[player_name][f'SCORE{n}'] = player_stats[player_name][f'SCORE{n}'] / max_score * 100

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

def calculate_auction_values(player_stats, league, exp_factor=EXP_FACTOR):
    """Split the league's total auction budget over the players who will be drafted
    (teams x roster spots), weighted by SCORE ** exp_factor, $1 minimum."""
    total_budget = league.num_teams * league.budget
    total_drafted_players = league.num_teams * league.roster_size

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

