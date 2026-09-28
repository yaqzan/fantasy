from flask import Flask, Blueprint, jsonify, request, send_from_directory
from flask_cors import CORS
from werkzeug.exceptions import HTTPException
import sys
import os
import traceback

# Add parent directory to path to import our existing modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fantasy_database import DB, Player, Team, FantasyTeam, FantasyTeamPlayer, DailyPlayerStats, LeaguePlayerFlag
from player_stats import (load_player_stats, calculate_overall_scores, calculate_auction_values, calculate_fantasy_points,
                          calculate_team_totals, week_schedule, team_games, TEAM_DICT)
from fantasy_config import TEAMNAMES
from fantasy_team_helper import (get_current_fantasy_week_dates, get_week_info_from_schedule, get_next_week_dates,
                                 league_team_ids, get_undroppable_players)
from leagues import (get_league, list_leagues, create_league, update_league, activate_league, delete_league,
                     generate_weeks, category_meta, CATEGORY_CATALOG, DEFAULT_SETTINGS, NotFound)
from datetime import date, datetime

app = Flask(__name__, static_folder=None)  # /static/* belongs to the React build (serve_frontend)
CORS(app, resources={
    r"/*": {
        # Extra browser origins allowed to call the API (comma-separated, from .env).
        "origins": [o.strip() for o in os.getenv("FANTASY_CORS_ORIGINS", "http://localhost:3001").split(",") if o.strip()],
        "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        "allow_headers": ["Content-Type", "X-League"]
    }
})


@app.route('/health', methods=['GET'])
def health():
    """Liveness probe for the server watcher (server.ps1)."""
    return jsonify({'status': 'ok'}), 200


@app.errorhandler(Exception)
def handle_error(e):
    if isinstance(e, HTTPException):
        return e
    if isinstance(e, NotFound):  # unknown league / team / week, or no league yet
        return jsonify({'error': str(e), 'no_league': 'no league yet' in str(e)}), 404
    print(f"ERROR in {request.path}: {e}")
    print(f"Traceback: {traceback.format_exc()}")
    return jsonify({'error': str(e)}), 500


fantasy_api = Blueprint('fantasy_api', __name__)

# Initialize database connection
try:
    DB.connect()
    print("Database connected successfully")
except Exception as e:
    print(f"Database connection failed: {e}")

STAT_SUFFIXES = {'season': '', '5': '_5', '10': '_10', 'projected': '_projected'}


def current_league():
    """The league this request is about: X-League header (the frontend's switcher), ?league=, else
    the active league."""
    return get_league(request.headers.get('X-League') or request.args.get('league'))


def league_team(league, team_id):
    team = FantasyTeam.get_or_none((FantasyTeam.id == team_id) & (FantasyTeam.league == league.id))
    if team is None:
        raise NotFound(f'no team {team_id} in league {league.id}')
    return team


def team_json(team):
    return {'id': team.id, 'name': team.name, 'abbreviation': team.abv}


def league_config(league):
    """League rules the frontend renders from (categories, roster, draft)."""
    return {
        'show_auction_price': league.settings['draft']['type'] == 'auction',
        'MY_TEAM_ABV': league.my_team,
        'league': league.to_dict(),
        'categories': category_meta(league.categories),
    }


def scored_players(league, punt_categories=()):
    player_stats = load_player_stats()
    calculate_overall_scores(player_stats, league, punt_categories)
    return player_stats


# ---------------------------------------------------------------- leagues

@fantasy_api.route('/leagues', methods=['GET'])
def get_leagues():
    leagues = list_leagues()
    active = next((l.id for l in leagues if l.is_active), leagues[0].id if leagues else None)
    return jsonify({'leagues': [l.to_dict() for l in leagues], 'active': active,
                    'category_catalog': category_meta(), 'defaults': DEFAULT_SETTINGS})


@fantasy_api.route('/leagues', methods=['POST'])
def post_league():
    data = request.get_json() or {}
    try:
        league = create_league(data.get('name'), data.get('settings') or {}, data.get('copy_teams_from'))
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    return jsonify(league.to_dict()), 201


@fantasy_api.route('/leagues/<league_id>', methods=['PUT'])
def put_league(league_id):
    data = request.get_json() or {}
    try:
        league = update_league(league_id, data.get('name'), data.get('settings'))
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    return jsonify(league.to_dict())


@fantasy_api.route('/leagues/<league_id>/activate', methods=['POST'])
def post_activate_league(league_id):
    activate_league(league_id)
    return jsonify({'active': league_id})


@fantasy_api.route('/leagues/<league_id>', methods=['DELETE'])
def remove_league(league_id):
    try:
        delete_league(league_id)
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    return jsonify({'deleted': league_id})


@fantasy_api.route('/leagues/generate-weeks', methods=['GET'])
def get_generated_weeks():
    """Blank matchup weeks from the stored NBA schedule: opening day, then every Monday."""
    from fantasy_database import Game
    from peewee import fn
    since = date(date.today().year if date.today().month >= 7 else date.today().year - 1, 7, 1)
    first = Game.select(fn.MIN(Game.date)).where(Game.date >= since).scalar()
    last = Game.select(fn.MAX(Game.date)).where(Game.date >= since).scalar()
    if not first:
        return jsonify({'error': 'no NBA schedule stored for this season yet: run pull_api_data.py'}), 404
    return jsonify({'weeks': generate_weeks(first.isoformat(), last.isoformat())})


# ---------------------------------------------------------------- players

def _team_abbreviations():
    """NBA team name (any spelling we store) -> abbreviation."""
    names = {full: abv for abv, full in TEAMNAMES.items()}
    for team in Team.select():
        if team.abv:
            names[team.name] = team.abv
    for short, full in TEAM_DICT.items():
        if full in names:
            names[short] = names[full]
    return names


@fantasy_api.route('/fantasy', methods=['GET'])
def get_fantasy_players():
    """Get all players with fantasy stats, scored for the current league"""
    league = current_league()
    player_stats = scored_players(league)
    calculate_auction_values(player_stats, league)
    calculate_fantasy_points(player_stats)

    team_ids = league_team_ids(league)
    fantasy_teams = {t.id: team_json(t) for t in FantasyTeam.select().where(FantasyTeam.league == league.id)}
    drafted = {}
    if team_ids:
        for ftp in FantasyTeamPlayer.select().where(FantasyTeamPlayer.fantasy_team_id.in_(team_ids)):
            drafted[ftp.player_name] = ftp.fantasy_team_id_id
    undroppable = set(get_undroppable_players(league))
    abbreviations = _team_abbreviations()

    # Games per NBA team this fantasy week and next
    current_week_start, current_week_end, _ = get_current_fantasy_week_dates(league)
    next_week_start, next_week_end = get_next_week_dates(league, current_week_start)
    current_week_games = team_games(week_schedule(current_week_start, current_week_end))
    next_week_games = team_games(week_schedule(next_week_start, next_week_end)) if next_week_start else {}

    top = sorted(player_stats.items(), key=lambda x: x[1].get('Z-RANK', 999))[:400]
    players_by_name = {p.name: p for p in Player.select().where(Player.name.in_([name for name, _ in top]))}

    players_data = []
    for player_name, stats in top:
        player = players_by_name.get(player_name)
        team_name = player.team if player and player.team else "Unknown"

        category_stats = {}
        for category in league.categories:
            values, scores = {}, {}
            for period, suffix in (('season', ''), ('5', '_5'), ('10', '_10'), ('projected', '_projected')):
                value = stats.get(category + suffix, 0) or 0
                values[period] = round(value * 100, 1) if CATEGORY_CATALOG[category].get('percent') else round(value, 2 if category in ('TECH', 'WIN%') else 1)
                scores[period] = int(stats.get(f'SCORE-{category}{suffix}', 0))
            category_stats[category] = {
                'value': values['projected'], 'value_season': values['season'], 'value_5': values['5'],
                'value_10': values['10'], 'value_projected': values['projected'],
                'score': scores['projected'], 'score_season': scores['season'], 'score_5': scores['5'],
                'score_10': scores['10'], 'score_projected': scores['projected'],
                'is_inverse': category in league.inverse_categories,
            }

        full_team_name = TEAM_DICT.get(team_name, team_name)
        team_id = drafted.get(player_name)
        players_data.append({
            'name': player_name,
            'team': team_name,
            'team_abv': abbreviations.get(team_name) or abbreviations.get(full_team_name) or team_name[:3].upper(),
            'position': player.pos if player and player.pos else "Unknown",
            'games_played': player.gp if player and player.gp else 0,
            'current_week_games': current_week_games.get(full_team_name, 0),
            'next_week_games': next_week_games.get(full_team_name, 0),
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
            'is_injured': bool(player and player.injured == 1),
            'is_undroppable': player_name in undroppable,
            'drafted': team_id is not None,
            'fantasy_team': fantasy_teams.get(team_id),
            'drafted_at': None,
        })

    players_data.sort(key=lambda x: x['overall_rank'] if x['overall_rank'] else 999)
    return jsonify({'players': players_data, 'total': len(players_data), 'config': league_config(league)})


def _custom_ranks(player_stats, suffix):
    ranked = sorted(player_stats, key=lambda p: player_stats[p].get(f'Z-SCORE{suffix}', 0), reverse=True)
    return {name: i for i, name in enumerate(ranked, start=1)}


@fantasy_api.route('/calculate-zscores', methods=['POST'])
def calculate_custom_zscores():
    """Overall scores with some categories punted, for the chosen stat timeframe"""
    data = request.get_json() or {}
    league = current_league()
    suffix = STAT_SUFFIXES.get(data.get('stat_type', 'projected'), '_projected')
    player_stats = scored_players(league, data.get('punt_categories', []))
    ranks = _custom_ranks(player_stats, suffix)
    return jsonify({'custom_scores': {name: {'custom_z_score': round(stats.get(f'Z-SCORE{suffix}', 0), 1),
                                             'custom_z_rank': ranks[name]}
                                      for name, stats in player_stats.items()}})


@fantasy_api.route('/calculate-auction-values', methods=['POST'])
def calculate_custom_auction_values():
    """Auction values with a custom price exponent and punted categories"""
    data = request.get_json() or {}
    league = current_league()
    punt = data.get('punt_categories', [])
    try:
        price_exponent = float(data.get('price_exponent') or league.price_exponent)
    except (TypeError, ValueError):
        return jsonify({'error': 'price_exponent must be a number'}), 400
    if not 0.2 <= price_exponent <= 5:
        return jsonify({'error': 'price_exponent must be between 0.2 and 5'}), 400
    player_stats = scored_players(league, punt)
    # Punting: auction values follow the value over the categories still played.
    calculate_auction_values(player_stats, league, price_exponent, value_key='Z-VALUE' if punt else 'VALUE')
    return jsonify({'auction_values': {name: {'auction_value': stats.get('AUCTION_VALUE', 0)}
                                       for name, stats in player_stats.items()}})


# ---------------------------------------------------------------- teams and rosters

@fantasy_api.route('/fantasy-teams', methods=['GET'])
def get_fantasy_teams():
    league = current_league()
    return jsonify({'teams': [team_json(t) for t in FantasyTeam.select().where(FantasyTeam.league == league.id)
                              .order_by(FantasyTeam.id)]})


@fantasy_api.route('/fantasy-teams', methods=['POST'])
def create_fantasy_team():
    data = request.get_json() or {}
    league = current_league()
    if FantasyTeam.select().where((FantasyTeam.league == league.id) & (FantasyTeam.name == data['name'])).exists():
        return jsonify({'error': f"{data['name']} is already in this league"}), 400
    team = FantasyTeam.create(name=data['name'], abv=data.get('abbreviation'), league=league.id)
    return jsonify(team_json(team)), 201


@fantasy_api.route('/fantasy-teams/<int:team_id>', methods=['PUT'])
def update_fantasy_team(team_id):
    data = request.get_json() or {}
    team = league_team(current_league(), team_id)
    team.name = data.get('name', team.name)
    team.abv = data.get('abbreviation', team.abv)
    team.save()
    return jsonify(team_json(team)), 200


@fantasy_api.route('/fantasy-teams/<int:team_id>', methods=['DELETE'])
def delete_fantasy_team(team_id):
    """Remove a team and its roster from the current league"""
    team = league_team(current_league(), team_id)
    with DB.atomic():
        FantasyTeamPlayer.delete().where(FantasyTeamPlayer.fantasy_team_id == team.id).execute()
        team.delete_instance()
    return jsonify({'deleted': team_id})


@fantasy_api.route('/draft-player', methods=['POST'])
def draft_player():
    """Put a player on a team in the current league (moving him if another team there has him)"""
    data = request.get_json() or {}
    league = current_league()
    player_name = data['player_name']
    player = Player.get(Player.name == player_name)
    fantasy_team = league_team(league, data['fantasy_team_id'])
    with DB.atomic():
        FantasyTeamPlayer.delete().where((FantasyTeamPlayer.player_name == player_name)
                                         & FantasyTeamPlayer.fantasy_team_id.in_(league_team_ids(league))).execute()
        FantasyTeamPlayer.create(player_id=player, fantasy_team_id=fantasy_team, player_name=player_name,
                                 fantasy_team_name=fantasy_team.name)
    return jsonify({'success': True}), 201


@fantasy_api.route('/undraft-player', methods=['POST'])
def undraft_player():
    """Remove a player from his team in the current league"""
    data = request.get_json() or {}
    league = current_league()
    team_ids = league_team_ids(league)
    deleted_count = FantasyTeamPlayer.delete().where((FantasyTeamPlayer.player_name == data['player_name'])
                                                     & FantasyTeamPlayer.fantasy_team_id.in_(team_ids)).execute() if team_ids else 0
    return jsonify({'success': True, 'deleted_count': deleted_count}), 200


@fantasy_api.route('/update-player', methods=['POST'])
def update_player():
    """Injured is NBA-wide; undroppable belongs to the current league"""
    data = request.get_json() or {}
    player = Player.get(Player.name == data['player_name'])
    player.injured = 1 if data.get('is_injured', False) else 0
    player.save()
    if 'is_undroppable' in data:
        league = current_league()
        LeaguePlayerFlag.replace(league=league.id, player=player.id, undroppable=bool(data['is_undroppable'])).execute()
    return jsonify({'success': True}), 200


@fantasy_api.route('/team-players/<int:team_id>', methods=['GET'])
def get_team_players(team_id):
    """Players on a team in the current league"""
    league = current_league()
    team = league_team(league, team_id)
    player_stats = scored_players(league)
    injured = {p.name for p in Player.select(Player.name).where(Player.injured == 1)}
    players = [{'player_name': ftp.player_name,
                'z_score': round(player_stats.get(ftp.player_name, {}).get('Z-SCORE', 0)),
                'is_injured': ftp.player_name in injured,
                'drafted_at': None}
               for ftp in FantasyTeamPlayer.select().where(FantasyTeamPlayer.fantasy_team_id == team.id)]
    return jsonify({'players': players, 'active_slots': league.active_slots})


@fantasy_api.route('/team-standings', methods=['GET'])
def get_team_standings():
    """Per-game category totals of each team's best `active` players, ranked per category"""
    league = current_league()
    suffix = STAT_SUFFIXES.get(request.args.get('stat_type', 'projected'), '_projected')
    healthy_only = request.args.get('healthy_only', 'false').lower() == 'true'
    player_stats = scored_players(league)
    injured = {p.name for p in Player.select(Player.name).where(Player.injured == 1)} if healthy_only else set()

    teams = list(FantasyTeam.select().where(FantasyTeam.league == league.id))
    rosters = {t.id: [] for t in teams}
    if teams:
        for ftp in FantasyTeamPlayer.select().where(FantasyTeamPlayer.fantasy_team_id.in_(list(rosters))):
            if ftp.player_name in player_stats and ftp.player_name not in injured:
                rosters[ftp.fantasy_team_id_id].append(ftp.player_name)

    team_totals = {}
    for team in teams:
        starters = sorted(rosters[team.id], key=lambda p: player_stats[p].get(f'Z-SCORE{suffix}', 0),
                          reverse=True)[:league.active_slots]
        per_game = {p: 1 for p in starters}
        wins = {p: player_stats[p].get(f'WIN%{suffix}', 0) for p in starters}
        totals = calculate_team_totals(starters, player_stats, per_game, wins, league.categories, suffix)
        team_totals[team.id] = {'team': team_json(team), 'player_count': len(starters),
                                'category_totals': {c: totals.get(c + suffix, 0) for c in league.categories}}

    category_rankings = {}
    for category in league.categories:
        ordered = sorted(team_totals, key=lambda tid: team_totals[tid]['category_totals'][category],
                         reverse=category not in league.inverse_categories)
        category_rankings[category] = {tid: rank for rank, tid in enumerate(ordered, 1)}

    teams_data = [{**data,
                   'category_rankings': {c: category_rankings[c][tid] for c in league.categories},
                   'total_rank_sum': sum(category_rankings[c][tid] for c in league.categories)}
                  for tid, data in team_totals.items()]
    teams_data.sort(key=lambda x: x['total_rank_sum'])
    meta = category_meta(league.categories)
    return jsonify({'teams': teams_data, 'categories': [m['key'] for m in meta],
                    'category_names': {m['key']: m['label'] for m in meta}, 'category_meta': meta,
                    'active_slots': league.active_slots})


# ---------------------------------------------------------------- matchups

def _requested_week(league, week_start_param):
    if week_start_param:
        week_start, week_end, opponent = get_week_info_from_schedule(league, week_start_param)
        if not week_start:
            raise NotFound(f'{week_start_param} is not a week in this league\'s schedule')
        return week_start, week_end, opponent
    return get_current_fantasy_week_dates(league)


@fantasy_api.route('/analyze')
def analyze():
    """Lineup optimizer analysis for one week"""
    from lineup_optimizer import get_analysis_data
    league = current_league()
    week_start, week_end, opponent = _requested_week(league, request.args.get('week_start'))
    analysis_data = get_analysis_data(
        league, request.args.get('timeframe', 'projected'), week_start, week_end, opponent,
        request.args.get('pickup', 'false').lower() == 'true', request.args.get('pickup_timeframe'))
    if 'error' in analysis_data:
        analysis_data['fantasy_schedule'] = league.schedule
        return jsonify(analysis_data), 422
    analysis_data['categories'] = category_meta(league.categories)
    return jsonify(analysis_data)


@fantasy_api.route('/analyze/custom', methods=['POST'])
def analyze_custom():
    """What-if: add one player (optionally dropping one) and compare in every timeframe"""
    from lineup_optimizer import get_custom_analysis
    data = request.get_json() or {}
    league = current_league()
    week_start, week_end, opponent = _requested_week(league, data.get('week_start'))
    result = get_custom_analysis(league, week_start, week_end, opponent, data.get('pickup'), data.get('drop'))
    if 'error' in result:
        return jsonify(result), 422
    return jsonify(result)


# ---------------------------------------------------------------- daily stats (NBA-wide)

@fantasy_api.route('/daily-stats', methods=['GET'])
def get_daily_stats():
    """Get daily player stats for a specific date"""
    date_str = request.args.get('date')
    try:
        target_date = datetime.strptime(date_str, '%Y-%m-%d').date() if date_str else date.today()
    except ValueError:
        return jsonify({'error': 'Invalid date format. Use YYYY-MM-DD'}), 400

    stats = DailyPlayerStats.select().where(
        DailyPlayerStats.game_date == target_date
    ).order_by(DailyPlayerStats.fantasy_points.desc())

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


@fantasy_api.route('/daily-stats/update', methods=['POST'])
def update_daily_stats():
    """Update daily stats for a specific date"""
    from update_daily_stats import update_daily_stats_efficient
    data = request.get_json()
    date_str = data.get('date') if data else None
    try:
        target_date = datetime.strptime(date_str, '%Y-%m-%d').date() if date_str else date.today()
    except ValueError:
        return jsonify({'error': 'Invalid date format. Use YYYY-MM-DD'}), 400

    update_daily_stats_efficient(target_date)
    return jsonify({
        'message': f'Daily stats updated for {target_date.strftime("%Y-%m-%d")}',
        'date': target_date.strftime('%Y-%m-%d')
    })


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


# The API lives under /api; everything else is the React app (one origin, like the other apps).
app.register_blueprint(fantasy_api, url_prefix='/api')

# Serve the built React app (npm --prefix frontend run build). Unknown paths get index.html.
FRONTEND_BUILD = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'frontend', 'build')


@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def serve_frontend(path):
    if path and os.path.isfile(os.path.join(FRONTEND_BUILD, path)):
        return send_from_directory(FRONTEND_BUILD, path)
    if not os.path.isfile(os.path.join(FRONTEND_BUILD, 'index.html')):
        return jsonify({'error': 'frontend not built: run npm --prefix frontend run build'}), 404
    return send_from_directory(FRONTEND_BUILD, 'index.html')


if __name__ == '__main__':
    # Loopback by default; set FANTASY_HOST to expose it. Never combine FLASK_DEBUG=1 with a
    # non-loopback host: the Werkzeug debugger runs arbitrary code for anyone who can reach it.
    app.run(host=os.getenv('FANTASY_HOST', '127.0.0.1'), port=int(os.getenv('FANTASY_PORT', '5001')),
            debug=os.getenv('FLASK_DEBUG') == '1')
