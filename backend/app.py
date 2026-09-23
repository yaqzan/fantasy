from flask import Flask, jsonify, request
from flask_cors import CORS
import sys
import os
from datetime import datetime
import traceback

# Add parent directory to path to import our existing modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fantasy_database import DB, Player, Team, FantasyTeam, FantasyTeamPlayer, DailyPlayerStats, Game
from player_stats import load_player_stats, calculate_overall_scores, calculate_auction_values, calculate_fantasy_points, TEAM_DICT
from fantasy_config import CATEGORIES, CATEGORY_NAMES, INVERSE_CATEGORIES, TEAMNAMES, EXP_FACTOR, SHOW_AUCTION_PRICE, MY_TEAM_ABV, FANTASY_SCHEDULE
from fantasy_team_helper import get_current_fantasy_week_dates, get_week_info_from_schedule
from datetime import date, timedelta

app = Flask(__name__)
CORS(app, resources={
    r"/*": {
        # Extra browser origins allowed to call the API (comma-separated, from .env).
        "origins": [o.strip() for o in os.getenv("FANTASY_CORS_ORIGINS", "http://localhost:3001").split(",") if o.strip()],
        "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        "allow_headers": ["Content-Type"]
    }
})


@app.route('/health', methods=['GET'])
def health():
    """Liveness probe for the server watcher (server.ps1)."""
    return jsonify({'status': 'ok'}), 200

# Blueprint for Fantasy API routes
from flask import Blueprint
fantasy_api = Blueprint('fantasy_api', __name__)

# Initialize database connection
try:
    DB.connect()
    print("Database connected successfully")
except Exception as e:
    print(f"Database connection failed: {e}")

@fantasy_api.route('/fantasy', methods=['GET'])
def get_fantasy_players():
    """Get all players with fantasy stats"""
    try:
        # Build player stats
        player_stats = load_player_stats()
        
        # Calculate scores and auction values
        calculate_overall_scores(player_stats)
        calculate_auction_values(player_stats)
        calculate_fantasy_points(player_stats)
        
        # Get drafted players
        drafted_players = {}
        for ftp in FantasyTeamPlayer.select():
            drafted_players[ftp.player_name] = {
                'fantasy_team_id': ftp.fantasy_team_id.id,
                'drafted_at': None
            }
        
        # Get fantasy teams for names
        fantasy_teams = {}
        for team in FantasyTeam.select():
            fantasy_teams[team.id] = {'id': team.id, 'name': team.name, 'abbreviation': team.abv}
        
        # Get team abbreviations from database (avoid N+1 queries)
        team_abbreviations = {}
        for team in Team.select():
            team_abbreviations[team.name] = team.abv
        
        # Calculate game counts for current and next week
        current_week_start, current_week_end, _ = get_current_fantasy_week_dates()
        
        # Get next week info
        next_week_start = None
        next_week_end = None
        if current_week_start:
            current_week_str = current_week_start.strftime('%Y-%m-%d')
            for i, (week_date, _) in enumerate(FANTASY_SCHEDULE):
                if week_date == current_week_str:
                    if i + 1 < len(FANTASY_SCHEDULE):
                        next_week_start_str = FANTASY_SCHEDULE[i + 1][0]
                        next_week_start, next_week_end, _ = get_week_info_from_schedule(next_week_start_str)
                    break
        
        # Calculate games played for each team in current and next week
        current_week_games = {}
        next_week_games = {}
        
        for team_name in TEAMNAMES.values():
            if current_week_start and current_week_end:
                current_week_games[team_name] = len(Game.select().where(
                    Game.date >= current_week_start, 
                    Game.date <= current_week_end
                ).where((Game.team_home == team_name) | (Game.team_away == team_name)))
            
            if next_week_start and next_week_end:
                next_week_games[team_name] = len(Game.select().where(
                    Game.date >= next_week_start, 
                    Game.date <= next_week_end
                ).where((Game.team_home == team_name) | (Game.team_away == team_name)))
        
        # Format response
        players_data = []
        # Sort by overall rank and limit to 400 records
        sorted_players = sorted(player_stats.items(), key=lambda x: x[1].get('Z-RANK', 999))
        limited_players = sorted_players[:400]
        
        for player_name, stats in limited_players:
            # Get player info from fantasy_database
            player = None
            try:
                player = Player.get(Player.name == player_name)
                team_name = player.team if player.team else "Unknown"
                position = player.pos if player.pos else "Unknown"
                games_played = player.gp if player.gp else 0
            except:
                team_name = "Unknown"
                position = "Unknown"
                games_played = 0
            
            # Build category stats with rankings for all time periods
            category_stats = {}
            for category in CATEGORIES:
                # Get stats for all time periods
                stat_periods = {
                    '': stats.get(category, 0),  # Season average
                    '_5': stats.get(category + '_5', 0),  # Last 5 games
                    '_10': stats.get(category + '_10', 0),  # Last 10 games
                    '_projected': stats.get(category + '_projected', 0)  # Projected
                }
                
                # Get scores for all time periods
                score_periods = {
                    '': int(stats.get(f'SCORE-{category}', 0)),
                    '_5': int(stats.get(f'SCORE-{category}_5', 0)),
                    '_10': int(stats.get(f'SCORE-{category}_10', 0)),
                    '_projected': int(stats.get(f'SCORE-{category}_projected', 0))
                }
                
                # Format values based on category type
                formatted_values = {}
                for period, value in stat_periods.items():
                    if category in ['TS%', 'EFG%', 'FT%']:
                        formatted_values[period] = round(value * 100, 1)
                    elif category == 'PLUS_MINUS':
                        formatted_values[period] = round(value, 1)
                    else:
                        formatted_values[period] = round(value, 1)
                
                category_stats[category] = {
                    'value': formatted_values['_projected'],  # Default to projected
                    'value_season': formatted_values[''],
                    'value_5': formatted_values['_5'],
                    'value_10': formatted_values['_10'],
                    'value_projected': formatted_values['_projected'],
                    'score': score_periods['_projected'],  # Default to projected
                    'score_season': score_periods[''],
                    'score_5': score_periods['_5'],
                    'score_10': score_periods['_10'],
                    'score_projected': score_periods['_projected'],
                    'is_inverse': category in INVERSE_CATEGORIES
                }
            
            # Handle team abbreviation mapping
            team_abv = None
            
            # First, try exact match in team_abbreviations (Team table)
            if team_name in team_abbreviations:
                team_abv = team_abbreviations[team_name]
            else:
                # Try fuzzy matching for common variations
                team_name_lower = team_name.lower()
                for db_team_name, abv in team_abbreviations.items():
                    db_team_lower = db_team_name.lower()
                    
                    # Check for common variations
                    if (team_name_lower in db_team_lower or 
                        db_team_lower in team_name_lower or
                        # Handle specific cases
                        (team_name_lower == 'la clippers' and db_team_lower == 'los angeles clippers') or
                        (team_name_lower == 'la lakers' and db_team_lower == 'los angeles lakers')):
                        team_abv = abv
                        break
                
                # If still not found, try TEAMNAMES mapping as fallback
                if team_abv is None:
                    if team_name in TEAMNAMES.values():
                        # team_name is a full name, find the abbreviation
                        for abv, full_name in TEAMNAMES.items():
                            if full_name == team_name:
                                team_abv = abv
                                break
                    elif team_name in TEAMNAMES.keys():
                        # team_name is already an abbreviation
                        team_abv = team_name
            
            # Get game counts for current and next week (use TEAM_DICT to convert abbreviated names)
            full_team_name = TEAM_DICT.get(team_name, team_name)
            current_week_gp = current_week_games.get(full_team_name, 0)
            next_week_gp = next_week_games.get(full_team_name, 0)
            
            player_data = {
                'name': player_name,
                'team': team_name,
                'team_abv': team_abv or (team_name[:3].upper() if team_name else 'N/A'),
                'position': position,
                'games_played': games_played,
                'current_week_games': current_week_gp,
                'next_week_games': next_week_gp,
                'current_week_start': current_week_start.strftime('%Y-%m-%d') if current_week_start else None,
                'next_week_start': next_week_start.strftime('%Y-%m-%d') if next_week_start else None,
                'stats': category_stats,
                'overall_rank': stats.get('Z-RANK_projected', 0),  # Default to projected
                'overall_rank_season': stats.get('Z-RANK', 0),
                'overall_rank_5': stats.get('Z-RANK_5', 0),
                'overall_rank_10': stats.get('Z-RANK_10', 0),
                'overall_rank_projected': stats.get('Z-RANK_projected', 0),
                'z_score': round(stats.get('Z-SCORE_projected', 0), 1),  # Default to projected
                'z_score_season': round(stats.get('Z-SCORE', 0), 1),
                'z_score_5': round(stats.get('Z-SCORE_5', 0), 1),
                'z_score_10': round(stats.get('Z-SCORE_10', 0), 1),
                'z_score_projected': round(stats.get('Z-SCORE_projected', 0), 1),
                'auction_value': stats.get('AUCTION_VALUE', 0),
                'fpoints': stats.get('FPOINTS_projected', 0),
                'fpoints_season': stats.get('FPOINTS', 0),
                'fpoints_5': stats.get('FPOINTS_5', 0),
                'fpoints_rank': stats.get('FPOINTS-RANK_projected', 0),
                'hot_overall': round(stats.get('Z-SCORE_5', 0) - stats.get('Z-SCORE', 0), 1),
                'hot_fpoints': round(stats.get('FPOINTS_5', 0) - stats.get('FPOINTS', 0), 1),
                'is_injured': (player.injured == 1) if (player and player.injured is not None) else False,
                'is_undroppable': player.undroppable == 1 if player else False,
                'drafted': player_name in drafted_players,
                'fantasy_team': fantasy_teams.get(drafted_players.get(player_name, {}).get('fantasy_team_id')) if player_name in drafted_players else None,
                'drafted_at': drafted_players.get(player_name, {}).get('drafted_at')
            }
            players_data.append(player_data)
        
        # Sort by overall rank
        players_data.sort(key=lambda x: x['overall_rank'] if x['overall_rank'] else 999)
        
        return jsonify({
            'players': players_data,
            'total': len(players_data),
            'config': {
                'show_auction_price': SHOW_AUCTION_PRICE,
                'MY_TEAM_ABV': MY_TEAM_ABV
            }
        })
    
    except Exception as e:
        print(f"ERROR in /api/fantasy: {str(e)}")
        print(f"Traceback: {traceback.format_exc()}")
        return jsonify({'error': str(e)}), 500

@fantasy_api.route('/calculate-zscores', methods=['POST'])
def calculate_custom_zscores():
    """Calculate z-scores with custom punt categories"""
    try:
        data = request.get_json()
        punt_categories = data.get('punt_categories', [])
        
        # Build player stats
        player_stats = load_player_stats()
        
        # Calculate scores
        calculate_overall_scores(player_stats)
        
        # Calculate custom z-scores with punt categories
        for n in ['', '_5', '_10', '_projected']:
            for player_name, _ in player_stats.items():
                z_score = 0
                for category in CATEGORIES:
                    category_last_n_games = category + n
                    if category not in punt_categories:
                        z_score += player_stats[player_name][f'SCORE-{category_last_n_games}']
                
                # Calculate z-score with custom categories
                active_categories = len(CATEGORIES) - len(punt_categories)
                if active_categories > 0:
                    player_stats[player_name][f'CUSTOM-Z-SCORE{n}'] = z_score / active_categories
                else:
                    player_stats[player_name][f'CUSTOM-Z-SCORE{n}'] = 0
        
        # Normalize custom z-scores
        for n in ['', '_5', '_10', '_projected']:
            max_value = max(player_stats[player][f'CUSTOM-Z-SCORE{n}'] for player in player_stats)
            for player_name, _ in player_stats.items():
                if max_value > 0:
                    denominator = max_value / player_stats[player_name][f'CUSTOM-Z-SCORE{n}']
                    player_stats[player_name][f'CUSTOM-Z-SCORE{n}'] = (1 / denominator) * 100
                else:
                    player_stats[player_name][f'CUSTOM-Z-SCORE{n}'] = 0
        
        # Calculate custom ranks
        for n in ['', '_5', '_10', '_projected']:
            for i, (key, val) in enumerate(sorted(player_stats.items(), key=lambda kv: kv[1][f'CUSTOM-Z-SCORE{n}'], reverse=True), start=1):
                player_stats[key][f'CUSTOM-Z-RANK{n}'] = i
        
        # Return custom z-scores and ranks
        custom_scores = {}
        for player_name, stats in player_stats.items():
            custom_scores[player_name] = {
                'custom_z_score': round(stats.get('CUSTOM-Z-SCORE', 0), 1),
                'custom_z_rank': stats.get('CUSTOM-Z-RANK', 0),
                'original_z_score': round(stats.get('Z-SCORE', 0), 1),
                'original_z_rank': stats.get('Z-RANK', 0)
            }
        
        return jsonify({'custom_scores': custom_scores})
    
    except Exception as e:
        print(f"ERROR in /api/calculate-zscores: {str(e)}")
        print(f"Traceback: {traceback.format_exc()}")
        return jsonify({'error': str(e)}), 500

@fantasy_api.route('/calculate-auction-values', methods=['POST'])
def calculate_custom_auction_values():
    """Calculate auction values with custom EXP_FACTOR and punt categories"""
    try:
        data = request.get_json()
        exp_factor = data.get('exp_factor', 5)
        punt_categories = data.get('punt_categories', [])
        
        # Build player stats
        player_stats = load_player_stats()
        
        # Calculate scores
        calculate_overall_scores(player_stats)
        
        # If punt categories are provided, calculate custom z-scores
        if punt_categories:
            # Calculate custom z-scores with punt categories
            for n in ['', '_5', '_10', '_projected']:
                for player_name, _ in player_stats.items():
                    z_score = 0
                    for category in CATEGORIES:
                        category_last_n_games = category + n
                        if category not in punt_categories:
                            z_score += player_stats[player_name][f'SCORE-{category_last_n_games}']
                    
                    # Calculate z-score with custom categories
                    active_categories = len(CATEGORIES) - len(punt_categories)
                    if active_categories > 0:
                        player_stats[player_name][f'CUSTOM-Z-SCORE{n}'] = z_score / active_categories
                    else:
                        player_stats[player_name][f'CUSTOM-Z-SCORE{n}'] = 0
            
            # Normalize custom z-scores
            for n in ['', '_5', '_10', '_projected']:
                max_value = max(player_stats[player][f'CUSTOM-Z-SCORE{n}'] for player in player_stats)
                for player_name, _ in player_stats.items():
                    if max_value > 0:
                        denominator = max_value / player_stats[player_name][f'CUSTOM-Z-SCORE{n}']
                        player_stats[player_name][f'CUSTOM-Z-SCORE{n}'] = (1 / denominator) * 100
                    else:
                        player_stats[player_name][f'CUSTOM-Z-SCORE{n}'] = 0
            
            # Use custom z-score for auction calculation
            for player_name, stats in player_stats.items():
                stats['SCORE'] = stats.get('CUSTOM-Z-SCORE', stats['SCORE'])
        
        # Calculate auction values with custom EXP_FACTOR
        from player_stats import calculate_auction_values
        calculate_auction_values(player_stats, exp_factor=exp_factor)
        
        auction_values = {}
        for player_name, stats in player_stats.items():
            auction_values[player_name] = {
                'auction_value': stats.get('AUCTION_VALUE', 0)
            }
        
        return jsonify({'auction_values': auction_values})
    
    except Exception as e:
        print(f"ERROR in /api/calculate-auction-values: {str(e)}")
        print(f"Traceback: {traceback.format_exc()}")
        return jsonify({'error': str(e)}), 500

@fantasy_api.route('/fantasy-teams', methods=['GET'])
def get_fantasy_teams():
    """Get all fantasy teams"""
    try:
        teams = []
        for team in FantasyTeam.select():
            teams.append({
                'id': team.id,
                'name': team.name,
                'abbreviation': team.abv
            })
        return jsonify({'teams': teams})
    except Exception as e:
        print(f"ERROR in /api/fantasy-teams GET: {str(e)}")
        print(f"Traceback: {traceback.format_exc()}")
        return jsonify({'error': str(e)}), 500

@fantasy_api.route('/fantasy-teams', methods=['POST'])
def create_fantasy_team():
    """Create a new fantasy team"""
    try:
        data = request.get_json()
        team = FantasyTeam.create(
            name=data['name'],
            abv=data.get('abbreviation')
        )
        return jsonify({
            'id': team.id,
            'name': team.name,
            'abbreviation': team.abv
        }), 201
    except Exception as e:
        print(f"ERROR in /api/fantasy-teams POST: {str(e)}")
        print(f"Traceback: {traceback.format_exc()}")
        return jsonify({'error': str(e)}), 500

@fantasy_api.route('/fantasy-teams/<int:team_id>', methods=['PUT'])
def update_fantasy_team(team_id):
    """Update a fantasy team's name and abbreviation"""
    try:
        data = request.get_json()
        team = FantasyTeam.get(FantasyTeam.id == team_id)
        
        team.name = data.get('name', team.name)
        team.abv = data.get('abbreviation', team.abv)
        team.save()
        
        return jsonify({
            'id': team.id,
            'name': team.name,
            'abbreviation': team.abv
        }), 200
    except Exception as e:
        print(f"ERROR in /api/fantasy-teams PUT: {str(e)}")
        print(f"Traceback: {traceback.format_exc()}")
        return jsonify({'error': str(e)}), 500

@fantasy_api.route('/draft-player', methods=['POST'])
def draft_player():
    """Draft a player to a fantasy team"""
    try:
        data = request.get_json()
        player_name = data['player_name']
        fantasy_team_id = data['fantasy_team_id']
        
        # Get player and fantasy team objects
        player = Player.get(Player.name == player_name)
        fantasy_team = FantasyTeam.get(FantasyTeam.id == fantasy_team_id)
        
        # Remove existing draft if any
        FantasyTeamPlayer.delete().where(
            FantasyTeamPlayer.player_name == player_name
        ).execute()
        
        # Create new draft entry
        ftp = FantasyTeamPlayer.create(
            player_id=player,
            fantasy_team_id=fantasy_team,
            player_name=player_name,
            fantasy_team_name=fantasy_team.name
        )
        
        return jsonify({'success': True}), 201
    except Exception as e:
        print(f"ERROR in /api/draft-player: {str(e)}")
        print(f"Traceback: {traceback.format_exc()}")
        return jsonify({'error': str(e)}), 500

@fantasy_api.route('/undraft-player', methods=['POST'])
def undraft_player():
    """Remove a player from a fantasy team"""
    try:
        data = request.get_json()
        player_name = data['player_name']
        
        # Remove draft entry
        deleted_count = FantasyTeamPlayer.delete().where(
            FantasyTeamPlayer.player_name == player_name
        ).execute()
        
        return jsonify({'success': True, 'deleted_count': deleted_count}), 200
    except Exception as e:
        print(f"ERROR in /api/undraft-player: {str(e)}")
        print(f"Traceback: {traceback.format_exc()}")
        return jsonify({'error': str(e)}), 500

@fantasy_api.route('/update-player', methods=['POST'])
def update_player():
    """Update player injured status and undroppable status"""
    try:
        data = request.get_json()
        player_name = data['player_name']
        is_injured = data.get('is_injured', False)
        is_undroppable = data.get('is_undroppable', False)
        
        # Update player status
        player = Player.get(Player.name == player_name)
        player.injured = 1 if is_injured else 0
        if 'is_undroppable' in data:
            player.undroppable = 1 if is_undroppable else 0
        player.save()
        
        return jsonify({'success': True}), 200
    except Exception as e:
        print(f"ERROR in /api/update-player: {str(e)}")
        print(f"Traceback: {traceback.format_exc()}")
        return jsonify({'error': str(e)}), 500

@fantasy_api.route('/team-players/<int:team_id>', methods=['GET'])
def get_team_players(team_id):
    """Get all players for a specific fantasy team"""
    try:
        # Get all player stats to find z-scores
        player_stats = load_player_stats()
        calculate_overall_scores(player_stats)
        
        players = []
        for ftp in FantasyTeamPlayer.select().where(FantasyTeamPlayer.fantasy_team_id == team_id):
            player_name = ftp.player_name
            
            # Check if player is injured
            is_injured = False
            try:
                player = Player.get(Player.name == player_name)
                is_injured = player.injured == 1
            except:
                # If player not found in database, assume not injured
                pass
            
            z_score = 0
            if player_name in player_stats:
                z_score = round(player_stats[player_name].get('Z-SCORE', 0))
            
            players.append({
                'player_name': player_name,
                'z_score': z_score,
                'is_injured': is_injured,
                'drafted_at': None
            })
        return jsonify({'players': players})
    except Exception as e:
        print(f"ERROR in /api/team-players: {str(e)}")
        print(f"Traceback: {traceback.format_exc()}")
        return jsonify({'error': str(e)}), 500

@fantasy_api.route('/team-standings', methods=['GET'])
def get_team_standings():
    """Get team standings with category totals and rankings"""
    try:
        stat_type = request.args.get('stat_type', 'projected')  # season, 5, 10, projected
        healthy_only = request.args.get('healthy_only', 'false').lower() == 'true'
        
        # Map stat_type to suffix
        stat_suffix_map = {
            'season': '',
            '5': '_5',
            '10': '_10',
            'projected': '_projected'
        }
        stat_suffix = stat_suffix_map.get(stat_type, '_projected')
        
        # Build player stats
        player_stats = load_player_stats()
        calculate_overall_scores(player_stats)
        
        # Get fantasy teams
        fantasy_teams = {}
        for team in FantasyTeam.select():
            fantasy_teams[team.id] = {
                'id': team.id,
                'name': team.name,
                'abbreviation': team.abv
            }
        
        # Get injured players set
        injured_players = set()
        if healthy_only:
            for player in Player.select().where(Player.injured == 1):
                injured_players.add(player.name)
        
        # Get all drafted players with their teams
        team_players = {}
        for ftp in FantasyTeamPlayer.select():
            team_id = ftp.fantasy_team_id.id
            player_name = ftp.player_name
            
            if team_id not in team_players:
                team_players[team_id] = []
            
            # Skip injured players if healthy_only is True
            if healthy_only and player_name in injured_players:
                continue
            
            # Only include players that exist in player_stats
            if player_name in player_stats:
                # Get z-score based on stat_type
                z_score_key = 'Z-SCORE' + stat_suffix
                z_score = player_stats[player_name].get(z_score_key, 0)
                team_players[team_id].append({
                    'name': player_name,
                    'z_score': z_score
                })
        
        # For each team, get top 11 players by z-score
        team_totals = {}
        for team_id, players in team_players.items():
            # Sort by z-score descending and take top 11
            sorted_players = sorted(players, key=lambda x: x['z_score'], reverse=True)[:11]
            player_names = [p['name'] for p in sorted_players]
            
            # Calculate category totals (sum of per-game averages)
            category_totals = {}
            
            # For percentage categories, we need to calculate from components
            # First collect component totals
            pts_total = 0
            fga_total = 0
            fta_total = 0
            ftm_total = 0
            fgm_total = 0
            fg3m_total = 0
            
            for player_name in player_names:
                pts_key = 'PTS' + stat_suffix
                fga_key = 'FGA' + stat_suffix
                fta_key = 'FTA' + stat_suffix
                ftm_key = 'FTM' + stat_suffix
                fgm_key = 'FGM' + stat_suffix
                fg3m_key = 'FG3M' + stat_suffix
                
                if pts_key in player_stats[player_name]:
                    pts_total += player_stats[player_name][pts_key]
                if fga_key in player_stats[player_name]:
                    fga_total += player_stats[player_name][fga_key]
                if fta_key in player_stats[player_name]:
                    fta_total += player_stats[player_name][fta_key]
                if ftm_key in player_stats[player_name]:
                    ftm_total += player_stats[player_name][ftm_key]
                if fgm_key in player_stats[player_name]:
                    fgm_total += player_stats[player_name][fgm_key]
                if fg3m_key in player_stats[player_name]:
                    fg3m_total += player_stats[player_name][fg3m_key]
            
            # Now calculate category totals
            for category in CATEGORIES:
                category_key = category + stat_suffix
                total = 0
                
                if category == 'TS%':
                    # Calculate TS% from summed components
                    denominator = 2 * (fga_total + (0.44 * fta_total))
                    total = pts_total / denominator if denominator != 0 else 0
                elif category in ['PTS', 'REB', 'AST', 'STL', 'BLK', 'FG3M', 'TOV', 'PF', 'PLUS_MINUS']:
                    # Sum per-game averages for counting stats
                    for player_name in player_names:
                        if category_key in player_stats[player_name]:
                            total += player_stats[player_name][category_key]
                elif category == 'NFT':
                    # NFT = 2 * FTM - FTA
                    total = (2 * ftm_total) - fta_total
                elif category == 'AST-TOV':
                    # AST-TOV = AST - TOV
                    ast_total = 0
                    tov_total = 0
                    for player_name in player_names:
                        if 'AST' + stat_suffix in player_stats[player_name]:
                            ast_total += player_stats[player_name]['AST' + stat_suffix]
                        if 'TOV' + stat_suffix in player_stats[player_name]:
                            tov_total += player_stats[player_name]['TOV' + stat_suffix]
                    total = ast_total - tov_total
                else:
                    # For other categories, just sum
                    for player_name in player_names:
                        if category_key in player_stats[player_name]:
                            total += player_stats[player_name][category_key]
                
                category_totals[category] = total
            
            team_totals[team_id] = {
                'team': fantasy_teams[team_id],
                'category_totals': category_totals,
                'player_count': len(player_names)
            }
        
        # Calculate rankings for each category
        category_rankings = {}
        for category in CATEGORIES:
            # Get all team values for this category
            team_values = [(team_id, team_totals[team_id]['category_totals'][category]) 
                          for team_id in team_totals.keys()]
            
            # Sort based on inverse categories
            is_inverse = category in INVERSE_CATEGORIES
            team_values.sort(key=lambda x: x[1], reverse=not is_inverse)
            
            # Assign rankings (1 = best)
            rankings = {}
            for rank, (team_id, _) in enumerate(team_values, 1):
                rankings[team_id] = rank
            
            category_rankings[category] = rankings
        
        # Calculate total ranking sum for each team
        teams_data = []
        for team_id, team_data in team_totals.items():
            total_rank_sum = sum(category_rankings[cat][team_id] for cat in CATEGORIES)
            
            teams_data.append({
                'team': team_data['team'],
                'category_totals': team_data['category_totals'],
                'category_rankings': {cat: category_rankings[cat][team_id] for cat in CATEGORIES},
                'total_rank_sum': total_rank_sum,
                'player_count': team_data['player_count']
            })
        
        # Sort by total_rank_sum (lowest = best)
        teams_data.sort(key=lambda x: x['total_rank_sum'])
        
        # Use the same category order as PlayerTable frontend
        category_order = ['TS%', 'PTS', 'REB', 'AST', 'STL', 'BLK', 'FG3M', 'NFT', 'TOV', 'PF', 'PLUS_MINUS']
        # Filter to only include categories that are in CATEGORIES
        ordered_categories = [cat for cat in category_order if cat in CATEGORIES]
        
        return jsonify({
            'teams': teams_data,
            'categories': ordered_categories,
            'category_names': {cat: CATEGORY_NAMES.get(cat, cat) for cat in ordered_categories}
        })
    
    except Exception as e:
        print(f"ERROR in /api/team-standings: {str(e)}")
        print(f"Traceback: {traceback.format_exc()}")
        return jsonify({'error': str(e)}), 500

@fantasy_api.route('/analyze')
def analyze():
    """Get lineup optimizer analysis data"""
    try:
        from lineup_optimizer import get_analysis_data
        from fantasy_team_helper import get_current_fantasy_week_dates, get_week_info_from_schedule

        # Get parameters from request
        week_start_param = request.args.get('week_start')
        timeframe = request.args.get('timeframe', 'projected')
        pickup = request.args.get('pickup', 'false').lower() == 'true'
        pickup_timeframe = request.args.get('pickup_timeframe', None)
        
        if week_start_param:
            # Get week info from schedule
            week_start, week_end, opponent = get_week_info_from_schedule(week_start_param)
            
            if not week_start or not week_end or not opponent:
                return jsonify({'error': 'Could not find week information for the specified date'}), 400
        else:
            # Get current fantasy week info
            week_start, week_end, opponent = get_current_fantasy_week_dates()
            
        # Get structured analysis data with week info
        analysis_data = get_analysis_data(timeframe, week_start, week_end, opponent, pickup, pickup_timeframe)

        if 'error' in analysis_data:
            return jsonify(analysis_data), 500
            
        # Add week info to the response
        analysis_data['matchup']['week_start'] = week_start.strftime('%Y-%m-%d') if week_start else None
        analysis_data['matchup']['week_end'] = week_end.strftime('%Y-%m-%d') if week_end else None
            
        return jsonify(analysis_data)
            
    except TimeoutError:
            return jsonify({'error': 'Analysis timed out - try again later'}), 408
            
    except Exception as e:
        print(f"ERROR in /api/analyze: {str(e)}")
        print(f"Traceback: {traceback.format_exc()}")
        return jsonify({'error': str(e)}), 500

@fantasy_api.route('/daily-stats', methods=['GET'])
def get_daily_stats():
    """Get daily player stats for a specific date"""
    try:
        from datetime import datetime, date
        
        # Get date parameter from query string
        date_str = request.args.get('date')
        print(f"Received date string: {date_str}")
        if not date_str:
            target_date = date.today()
        else:
            try:
                target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
                print(f"Parsed target date: {target_date}")
            except ValueError:
                return jsonify({'error': 'Invalid date format. Use YYYY-MM-DD'}), 400
        
        # Get daily stats for the date
        stats = DailyPlayerStats.select().where(
            DailyPlayerStats.game_date == target_date
        ).order_by(DailyPlayerStats.fantasy_points.desc())
        
        # Debug: Check what dates are available
        available_dates = DailyPlayerStats.select(DailyPlayerStats.game_date).distinct().order_by(DailyPlayerStats.game_date.desc()).limit(5)
        print(f"Available dates in database: {[str(d.game_date) for d in available_dates]}")
        print(f"Looking for stats on: {target_date}")
        print(f"Found {len(stats)} stats for this date")
        
        # Format response
        daily_stats = []
        for stat in stats:
            daily_stats.append({
                'id': stat.id,
                'player_id': stat.player_id.id,
                'player_name': stat.player_name,
                'team': stat.team,
                'game_date': stat.game_date.strftime('%Y-%m-%d'),
                'game_id': stat.game_id,
                'matchup': stat.matchup,
                'minutes': stat.minutes,
                'fgm': stat.fgm,
                'fga': stat.fga,
                'fg_pct': stat.fg_pct,
                'fg3m': stat.fg3m,
                'fg3a': stat.fg3a,
                'fg3_pct': stat.fg3_pct,
                'ftm': stat.ftm,
                'fta': stat.fta,
                'ft_pct': stat.ft_pct,
                'oreb': stat.oreb,
                'dreb': stat.dreb,
                'reb': stat.reb,
                'ast': stat.ast,
                'stl': stat.stl,
                'blk': stat.blk,
                'tov': stat.tov,
                'pf': stat.pf,
                'pts': stat.pts,
                'plus_minus': stat.plus_minus,
                'fantasy_points': stat.fantasy_points,
                'created_at': stat.created_at.isoformat() if stat.created_at else None
            })
        
        return jsonify({
            'date': target_date.strftime('%Y-%m-%d'),
            'stats': daily_stats,
            'total': len(daily_stats)
        })
        
    except Exception as e:
        print(f"ERROR in /api/daily-stats: {str(e)}")
        print(f"Traceback: {traceback.format_exc()}")
        return jsonify({'error': str(e)}), 500

@fantasy_api.route('/daily-stats/update', methods=['POST'])
def update_daily_stats():
    """Update daily stats for a specific date"""
    try:
        from datetime import datetime, date
        from update_daily_stats import update_daily_stats_for_date
        
        # Get date parameter from request body
        data = request.get_json()
        date_str = data.get('date') if data else None
        
        if not date_str:
            target_date = date.today()
        else:
            try:
                target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
            except ValueError:
                return jsonify({'error': 'Invalid date format. Use YYYY-MM-DD'}), 400
        
        # Update daily stats using efficient approach
        from update_daily_stats import update_daily_stats_efficient
        update_daily_stats_efficient(target_date)
        
        return jsonify({
            'message': f'Daily stats updated for {target_date.strftime("%Y-%m-%d")}',
            'date': target_date.strftime('%Y-%m-%d')
        })
        
    except Exception as e:
        print(f"ERROR in /api/daily-stats/update: {str(e)}")
        print(f"Traceback: {traceback.format_exc()}")
        return jsonify({'error': str(e)}), 500

@app.route('/manifest.json')
def manifest():
    """Serve a basic manifest.json for React app"""
    return jsonify({
        "short_name": "NBA Fantasy",
        "name": "NBA Fantasy Draft Assistant",
        "icons": [
            {
                "src": "favicon.ico",
                "sizes": "64x64 32x32 24x24 16x16",
                "type": "image/x-icon"
            }
        ],
        "start_url": ".",
        "display": "standalone",
        "theme_color": "#000000",
        "background_color": "#ffffff"
    })

@app.route('/favicon.ico')
def favicon():
    """Serve a basic favicon response"""
    return '', 204  # No Content response

# Register the fantasy API blueprint
app.register_blueprint(fantasy_api)

# Serve React static files
@app.route('/fantasy', defaults={'path': ''})
@app.route('/fantasy/<path:path>')
def serve_fantasy(path):
    """Serve the React frontend"""
    from flask import send_from_directory
    frontend_build = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'frontend', 'build')
    
    # If path is empty or doesn't exist, serve index.html
    if path and os.path.exists(os.path.join(frontend_build, path)):
        return send_from_directory(frontend_build, path)
    else:
        return send_from_directory(frontend_build, 'index.html')

if __name__ == '__main__':
    # Loopback by default; set FANTASY_HOST to expose it. Never combine FLASK_DEBUG=1 with a
    # non-loopback host: the Werkzeug debugger runs arbitrary code for anyone who can reach it.
    app.run(host=os.getenv('FANTASY_HOST', '127.0.0.1'), port=int(os.getenv('FANTASY_PORT', '5001')),
            debug=os.getenv('FLASK_DEBUG') == '1')
