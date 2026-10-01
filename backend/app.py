from flask import Flask, Blueprint, jsonify, request, send_from_directory
from flask_cors import CORS
from werkzeug.exceptions import HTTPException
import sys
import os
import traceback
import json

# Add parent directory to path to import our existing modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fantasy_database import (DB, Player, Team, FantasyTeam, FantasyTeamPlayer, DailyPlayerStats,
                              PlayerProjection, ProjectionAdjustment)
from projections import season_label
from player_stats import (league_player_stats, calculate_auction_values, calculate_team_totals, week_schedule,
                          team_games, player_week_games, best_starters, games_floor, auction_value_at,
                          TEAM_DICT, STAT_SUFFIXES, YEAR3_BIAS_Z, BREAKOUT_Z)
from fantasy_config import TEAMNAMES, FPOINTS_SCORING
from fantasy_team_helper import (get_current_fantasy_week_dates, get_week_info_from_schedule, get_next_week_dates,
                                 league_team_ids, get_undroppable_players, set_league_flags)
from leagues import (POINT_STATS, fantasy_points, get_league, list_leagues, create_league, update_league, activate_league, delete_league,
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

DRAFT_DAY_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'draft_day.json')


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
    return {'id': team.id, 'name': team.name, 'abbreviation': team.abv, 'eliminated_stage': team.eliminated_stage}


def _week_json(start, end):
    return {'start': start.isoformat(), 'end': end.isoformat()} if start else None


def _draft_plan_league():
    """The league draft_day.json was built for, or None."""
    if not os.path.isfile(DRAFT_DAY_FILE):
        return None
    with open(DRAFT_DAY_FILE, encoding='utf-8') as f:
        return json.load(f).get('league')


def league_config(league):
    """League rules the frontend renders from (categories, roster, draft). Before the league's
    first week the stats are last season's, and the full season is the basis to draft on; after,
    the projection (half season, half last 10 games)."""
    schedule = league.schedule
    team_ids = league_team_ids(league)
    preseason = bool(schedule) and date.today().isoformat() < schedule[0][0]
    current_week = get_current_fantasy_week_dates(league)
    next_week = get_next_week_dates(league, current_week[0])
    has_projections = PlayerProjection.select().where(PlayerProjection.season == season_label()).exists()
    return {
        'MY_TEAM_ABV': league.my_team,
        'league': league.to_dict(),
        'categories': category_meta(league.categories),
        'current_week': _week_json(*current_week[:2]), 'next_week': _week_json(*next_week),
        'capabilities': {**league.capabilities(), 'draft_plan': _draft_plan_league() == league.id},
        # Nobody rostered yet: the draft hasn't happened (draft mode's default for leagues without a date).
        'rostered': FantasyTeamPlayer.select().where(FantasyTeamPlayer.fantasy_team_id.in_(team_ids)).count()
        if team_ids else 0,
        # Before the season: this season's projection when there is one, else last season.
        'default_stat_type': ('proj' if has_projections else 'season') if preseason else 'projected',
        'projection_season': season_label() if has_projections else None,
    }


# ---------------------------------------------------------------- leagues


@fantasy_api.route('/draft-day', methods=['GET'])
def get_draft_day():
    """The Draft Day tab's numbers (targets, max bids, past-auction evidence). Owner data: a gitignored
    draft_day.json written by the owner's research scripts; 404 when this install has none."""
    if not os.path.isfile(DRAFT_DAY_FILE):
        return jsonify({'error': "no draft_day.json on this server: the Draft Day tab needs the owner's research data"}), 404
    with open(DRAFT_DAY_FILE, encoding='utf-8') as f:
        return jsonify(json.load(f))


@fantasy_api.route('/leagues', methods=['GET'])
def get_leagues():
    leagues = list_leagues()
    active = next((l.id for l in leagues if l.is_active), leagues[0].id if leagues else None)
    return jsonify({'leagues': [l.to_dict() for l in leagues], 'active': active,
                    'category_catalog': category_meta(), 'defaults': DEFAULT_SETTINGS,
                    'point_stats': POINT_STATS, 'default_points': FPOINTS_SCORING})


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
    player_stats = league_player_stats(league)
    # A $ value per timeframe, so the price always matches the rank it is shown next to.
    for suffix in STAT_SUFFIXES.values():
        calculate_auction_values(player_stats, league, value_key=f'VALUE{suffix}', out_key=f'AUCTION_VALUE{suffix}')
    floor = games_floor(player_stats)

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

    # The 400 best on last season or on the projection (rookies only have the latter).
    top = sorted(player_stats.items(), key=lambda x: min(x[1].get('Z-RANK', 999), x[1].get('Z-RANK_proj', 999)))[:400]
    players_by_name = {p.name: p for p in Player.select().where(Player.name.in_([name for name, _ in top]))}

    players_data = []
    stats_all = player_stats
    for player_name, stats in top:
        player = players_by_name.get(player_name)
        team_name = player.team if player and player.team else "Unknown"

        category_stats = {}
        for category in league.categories:
            values, scores = {}, {}
            for period, suffix in (('season', ''), ('5', '_5'), ('10', '_10'), ('projected', '_projected'), ('proj', '_proj')):
                value = stats.get(category + suffix, 0) or 0
                values[period] = round(value * 100, 1) if CATEGORY_CATALOG[category].get('percent') else round(value, 2 if category in ('TECH', 'WIN%') else 1)
                scores[period] = int(stats.get(f'SCORE-{category}{suffix}', 0))
            category_stats[category] = {
                'value': values['projected'], 'value_season': values['season'], 'value_5': values['5'],
                'value_10': values['10'], 'value_projected': values['projected'], 'value_proj': values['proj'],
                'score': scores['projected'], 'score_season': scores['season'], 'score_5': scores['5'],
                'score_10': scores['10'], 'score_projected': scores['projected'], 'score_proj': scores['proj'],
                'is_inverse': category in league.inverse_categories,
            }

        full_team_name = TEAM_DICT.get(team_name, team_name)
        team_id = drafted.get(player_name)
        players_data.append({
            'name': player_name,
            'team': team_name,
            'team_abv': abbreviations.get(team_name) or abbreviations.get(full_team_name) or team_name[:3].upper(),
            'position': player.pos if player and player.pos else "Unknown",
            'positions': list(stats.get('Positions') or ()),
            'games_played': player.gp if player and player.gp else 0,
            'small_sample': 0 < (stats.get('GP') or 0) < floor,
            'projected_only': not stats.get('GP') and 'GP_proj' in stats,
            'projected_games': round(stats.get('GP_proj', 0)),
            'current_week_games': current_week_games.get(full_team_name, 0),
            'next_week_games': next_week_games.get(full_team_name, 0),
            'stats': category_stats,
            'overall_rank': stats.get('Z-RANK_projected', 0),  # Default to projected
            'overall_rank_season': stats.get('Z-RANK', 0),
            'overall_rank_5': stats.get('Z-RANK_5', 0),
            'overall_rank_10': stats.get('Z-RANK_10', 0),
            'overall_rank_projected': stats.get('Z-RANK_projected', 0),
            'overall_rank_proj': stats.get('Z-RANK_proj', 0),
            'z_score': round(stats.get('Z-SCORE_projected', 0), 1),  # Default to projected
            'z_score_season': round(stats.get('Z-SCORE', 0), 1),
            'z_score_5': round(stats.get('Z-SCORE_5', 0), 1),
            'z_score_10': round(stats.get('Z-SCORE_10', 0), 1),
            'z_score_projected': round(stats.get('Z-SCORE_projected', 0), 1),
            'z_score_proj': round(stats.get('Z-SCORE_proj', 0), 1),
            'auction_value': stats.get('AUCTION_VALUE_projected', 0),  # Default to projected
            'auction_value_season': stats.get('AUCTION_VALUE', 0),
            'auction_value_5': stats.get('AUCTION_VALUE_5', 0),
            'auction_value_10': stats.get('AUCTION_VALUE_10', 0),
            'auction_value_projected': stats.get('AUCTION_VALUE_projected', 0),
            'auction_value_proj': stats.get('AUCTION_VALUE_proj', 0),
            'hot_overall': round(stats.get('Z-SCORE_5', 0) - stats.get('Z-SCORE', 0), 1),
            'is_injured': bool(player and player.injured == 1),
            'injured_return': (player.injured_return if player and player.injured == 1 else None),
            'injured_games': ((player.injured_games_to_miss or None) if player and player.injured == 1 else None),
            'nba_year': stats.get('NBA_YEAR'),
            # Second- and third-year players: the projection $ after a breakout; third-years also with
            # their average projection miss added back (second-years are projected about right).
            'what_if': ({'corrected': (auction_value_at(stats_all, league, player_name, YEAR3_BIAS_Z)
                                       if stats.get('NBA_YEAR') == 3 else None),
                         'breakout': auction_value_at(stats_all, league, player_name, BREAKOUT_Z)}
                        if stats.get('NBA_YEAR') in (2, 3) and stats.get('ELIGIBLE_proj') else None),
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
    player_stats = league_player_stats(league, data.get('punt_categories', []))
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
    suffix = STAT_SUFFIXES.get(data.get('stat_type', 'projected'), '_projected')
    player_stats = league_player_stats(league, punt)
    # Punting: auction values follow the value over the categories still played.
    calculate_auction_values(player_stats, league, price_exponent,
                             value_key=f'Z-VALUE{suffix}' if punt else f'VALUE{suffix}')
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


@fantasy_api.route('/fantasy-teams/<int:team_id>/eliminate', methods=['POST'])
def eliminate_fantasy_team(team_id):
    """Guillotine: knock a team out after a stage (default: the last stage that ended) and release
    its players to free agency. The roster is kept on the team so /restore can undo it."""
    league = current_league()
    team = league_team(league, team_id)
    if not league.is_guillotine:
        return jsonify({'error': 'this league has no elimination stages (League settings > Guillotine)'}), 400
    if team.eliminated_stage:
        return jsonify({'error': f'{team.name} was already eliminated after stage {team.eliminated_stage}'}), 400
    stage = (request.get_json() or {}).get('stage')
    if not stage:
        info = league.stage_info() or {}
        stage = len(league.stage_weeks) - 1 if info.get('finished') else max((info.get('stage') or 1) - 1, 1)
    roster = [ftp.player_name for ftp in FantasyTeamPlayer.select().where(FantasyTeamPlayer.fantasy_team_id == team.id)]
    with DB.atomic():
        team.eliminated_stage = int(stage)
        team.released_roster = json.dumps(roster)
        team.save()
        FantasyTeamPlayer.delete().where(FantasyTeamPlayer.fantasy_team_id == team.id).execute()
    return jsonify({'team': team_json(team), 'released': roster})


@fantasy_api.route('/fantasy-teams/<int:team_id>/restore', methods=['POST'])
def restore_fantasy_team(team_id):
    """Undo an elimination: the team is back in and gets back the players it held then, except
    those another team in the league has picked up since."""
    league = current_league()
    team = league_team(league, team_id)
    released = json.loads(team.released_roster or '[]')
    taken = {ftp.player_name for ftp in FantasyTeamPlayer.select(FantasyTeamPlayer.player_name)
             .where(FantasyTeamPlayer.fantasy_team_id.in_(league_team_ids(league)))}
    restored, skipped = [], []
    with DB.atomic():
        for name in released:
            player = Player.get_or_none(Player.name == name)
            if player is None or name in taken:
                skipped.append(name)
                continue
            FantasyTeamPlayer.create(player_id=player, fantasy_team_id=team, player_name=name, fantasy_team_name=team.name)
            restored.append(name)
        team.eliminated_stage = None
        team.released_roster = None
        team.save()
    return jsonify({'team': team_json(team), 'restored': restored, 'skipped': skipped})


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
    if not player.injured:      # the return month and games belong to one injury
        player.injured_return, player.injured_games_to_miss = None, 0
    player.save()
    if 'is_undroppable' in data:
        set_league_flags(current_league(), player.id, undroppable=bool(data['is_undroppable']))
    return jsonify({'success': True}), 200


def _open_slots(slots, filled):
    open_slots = list(slots)
    for slot in filled:
        open_slots.remove(slot)
    return open_slots


@fantasy_api.route('/team-rosters', methods=['GET'])
def get_team_rosters():
    """Every team's roster in the current league, best first, with the slot each healthy starter
    fills (best_starters: the league's slots, season OVR), the starters' average OVR, and the
    starting slots no healthy player on the roster can fill (`open_slots`)."""
    league = current_league()
    player_stats = league_player_stats(league)
    injured = {p.name for p in Player.select(Player.name).where(Player.injured == 1)}
    rosters = {}
    team_ids = league_team_ids(league)
    for ftp in (FantasyTeamPlayer.select().where(FantasyTeamPlayer.fantasy_team_id.in_(team_ids)) if team_ids else []):
        rosters.setdefault(ftp.fantasy_team_id_id, []).append(ftp.player_name)
    out = {}
    for team_id, names in rosters.items():
        starters = best_starters(league, [p for p in names if p not in injured], player_stats)
        score = lambda p: player_stats.get(p, {}).get('Z-SCORE', 0)
        out[team_id] = {
            'players': [{'player_name': p, 'z_score': round(score(p)), 'is_injured': p in injured,
                         'positions': list(player_stats.get(p, {}).get('Positions') or ()), 'slot': starters.get(p)}
                        for p in sorted(names, key=score, reverse=True)],
            'score': round(sum(score(p) for p in starters) / len(starters)) if starters else 0,
            'open_slots': _open_slots(league.slots, starters.values()),
        }
    return jsonify({'teams': out, 'roster_size': league.roster_size, 'slots': league.slots})


@fantasy_api.route('/team-standings', methods=['GET'])
def get_team_standings():
    """A power ranking from each team's category totals, ranked per category. Not the league's
    real standings. view=per_game (default): roster strength, one game each of the best `active`
    players who fit the league's slots (best_starters), schedule-free. Points leagues have one
    category, so the rank sum is the rank by projected points. view=week: this fantasy week's projection,
    only games NBA teams actually play, daily-lineup leagues counting the best `active` players of
    each day (bench players fill empty days) and weekly-lineup leagues their starters' games."""
    league = current_league()
    suffix = STAT_SUFFIXES.get(request.args.get('stat_type', 'projected'), '_projected')
    healthy_only = request.args.get('healthy_only', 'true').lower() == 'true'
    view = 'week' if request.args.get('view') == 'week' else 'per_game'
    player_stats = league_player_stats(league)
    injured = {p.name for p in Player.select(Player.name).where(Player.injured == 1)} if healthy_only else set()

    # Guillotine: eliminated teams are out of the ranking (their players are free agents).
    teams = list(FantasyTeam.select().where((FantasyTeam.league == league.id) & FantasyTeam.eliminated_stage.is_null()))
    rosters = {t.id: [] for t in teams}
    if teams:
        for ftp in FantasyTeamPlayer.select().where(FantasyTeamPlayer.fantasy_team_id.in_(list(rosters))):
            if ftp.player_name in player_stats and ftp.player_name not in injured:
                rosters[ftp.fantasy_team_id_id].append(ftp.player_name)

    week_start = week_end = schedule = None
    if view == 'week':
        week_start, week_end, _ = get_current_fantasy_week_dates(league)
        schedule = week_schedule(week_start, week_end)

    team_totals = {}
    for team in teams:
        if view == 'week':
            # Daily lineups: player_week_games picks each day's best `active` from the whole roster.
            counted = rosters[team.id] if league.daily_lineups else best_starters(league, rosters[team.id], player_stats, suffix)
            games, wins = player_week_games(counted, player_stats, schedule, league, suffix, injured)
        else:
            counted = best_starters(league, rosters[team.id], player_stats, suffix)
            games = {p: 1 for p in counted}
            wins = {p: player_stats[p].get(f'WIN%{suffix}', 0) for p in counted}
        totals = calculate_team_totals(counted, player_stats, games, wins, league.categories, suffix)
        team_totals[team.id] = {'team': team_json(team), 'player_count': sum(1 for g in games.values() if g),
                                'games': sum(games.values()),
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
                    'active_slots': league.active_slots, 'view': view, 'stage': league.stage_info(),
                    'playoffs': league.settings['playoffs'],
                    'week_start': week_start.isoformat() if week_start else None,
                    'week_end': week_end.isoformat() if week_end else None})


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
    """Lineup Optimizer: my week against the opponent (lineup_optimizer.get_matchup). add/drop
    (repeatable): a what-if roster. moves=true: the best pickups for the week's claims."""
    from lineup_optimizer import get_matchup
    league = current_league()
    week_start, week_end, opponent = _requested_week(league, request.args.get('week_start'))
    result = get_matchup(league, request.args.get('timeframe', 'projected'), week_start, week_end, opponent,
                         adds=request.args.getlist('add'), drops=request.args.getlist('drop'),
                         moves=request.args.get('moves', 'false').lower() == 'true')
    if 'error' in result:
        return jsonify(result), 422
    result['categories'] = category_meta(league.categories)
    return jsonify(result)


# ---------------------------------------------------------------- projections (NBA-wide)

def _projection_season():
    return request.args.get('season') or season_label()


@fantasy_api.route('/projections/teams', methods=['GET'])
def get_team_projections():
    """Each team's projected wins: every source, the accuracy-weighted index, its range, the owner's
    adjustment, and last season's record."""
    from projections import team_projection_index, team_strength, TEAM_SOURCE_WEIGHT
    season = _projection_season()
    index = team_projection_index(season)
    strength = team_strength(season)
    sources = sorted({s for row in index.values() for s in row['sources']},
                     key=lambda s: -TEAM_SOURCE_WEIGHT.get(s, 1.0))
    teams = []
    for team in Team.select().order_by(Team.name):
        row = index.get(team.name)
        teams.append({'team': team.name, 'abbreviation': team.abv,
                      'sources': row['sources'] if row else {}, 'index': round(row['wins'], 1) if row else None,
                      'low': row['low'] if row else None, 'high': row['high'] if row else None,
                      'adjustment': row['adjustment'] if row else 0.0,
                      'final': round(row['final'], 1) if row else None,
                      'strength': round(strength.get(team.name, 0.5), 3),
                      'last_record': [team.wins, team.losses] if team.record_season != season else None})
    return jsonify({'season': season, 'teams': teams,
                    'sources': [{'key': s, 'weight': TEAM_SOURCE_WEIGHT.get(s, 1.0)} for s in sources]})


@fantasy_api.route('/projections/teams', methods=['PUT'])
def put_team_projection():
    """The owner's adjustment to a team's projected wins (+/- wins; 0 removes it)."""
    from fantasy_database import TeamProjection
    data = request.get_json() or {}
    season = data.get('season') or season_label()
    team = Team.get_or_none(Team.name == data.get('team'))
    if team is None:
        return jsonify({'error': f"no team {data.get('team')!r}"}), 400
    try:
        adjustment = float(data.get('adjustment') or 0)
    except (TypeError, ValueError):
        return jsonify({'error': 'the adjustment must be a number of wins'}), 400
    if abs(adjustment) > 40:
        return jsonify({'error': 'the adjustment must be within 40 wins'}), 400
    TeamProjection.delete().where((TeamProjection.season == season) & (TeamProjection.source == 'owner')
                                  & (TeamProjection.team == team.name)).execute()
    if adjustment:
        TeamProjection.create(season=season, source='owner', team=team.name, wins=adjustment)
    return jsonify({'team': team.name, 'adjustment': adjustment})


@fantasy_api.route('/projections/players', methods=['GET'])
def get_player_projections():
    """Players' projections for the current league's view: the blended line, each source's line,
    the owner's adjustment, and the league's projection rank and $."""
    from projections import player_lines
    season = _projection_season()
    league = current_league()
    lines = player_lines(season)
    by_player = {}
    for row in PlayerProjection.select().where(PlayerProjection.season == season).dicts():
        by_player.setdefault(row['player_id'], {})[row['source']] = row
    player_stats = league_player_stats(league)
    calculate_auction_values(player_stats, league, value_key='VALUE_proj', out_key='AUCTION_VALUE_proj')
    ids = {p.name: p for p in Player.select(Player.id, Player.name, Player.team, Player.pos)
           .where(Player.id.in_(list(lines)))}
    search = (request.args.get('q') or '').strip().lower()
    try:
        limit = max(1, min(int(request.args.get('limit', 250)), 600))
    except ValueError:
        return jsonify({'error': 'limit must be a whole number'}), 400
    adjustments = {a.player_id: a for a in ProjectionAdjustment.select().where(ProjectionAdjustment.season == season)}
    shown = ['gp', 'min', 'pts', 'reb', 'ast', 'stl', 'blk', 'fg3m', 'tov', 'fga', 'fta']
    rows = []
    for name, stats in player_stats.items():
        player = ids.get(name)
        if player is None or 'RANK_proj' not in stats:
            continue
        if search and search not in name.lower():
            continue
        line = lines[player.id]
        adj = adjustments.get(player.id)
        rows.append({'id': player.id, 'name': name, 'team': player.team, 'position': player.pos,
                     'type': line['type'], 'expert_weight': line['expert_weight'],
                     'rank': stats['RANK_proj'], 'auction_value': stats.get('AUCTION_VALUE_proj', 1),
                     'fpts': stats.get('FPTS_proj') if league.is_points else None,
                     'line': {k: round(line[k], 2) for k in shown},
                     'sources': {s: {k: round(r[k], 2) if r.get(k) is not None else None for k in shown}
                                 for s, r in by_player.get(player.id, {}).items()},
                     'adjustment': {'production': adj.production, 'games': adj.games, 'note': adj.note} if adj else None})
    rows.sort(key=lambda r: r['rank'])
    return jsonify({'season': season, 'players': rows[:limit], 'total': len(rows)})


@fantasy_api.route('/projections/players/<int:player_id>', methods=['PUT'])
def put_player_projection(player_id):
    """The owner's adjustment to a player's projection: `production` scales every counting stat and
    minutes (1.1 = +10%), `games` replaces projected games; 1.0 and no games removes it."""
    data = request.get_json() or {}
    season = data.get('season') or season_label()
    if Player.get_or_none(Player.id == player_id) is None:
        return jsonify({'error': f'no player {player_id}'}), 404
    try:
        production = float(data.get('production') if data.get('production') not in (None, '') else 1.0)
        games = float(data['games']) if data.get('games') not in (None, '') else None
    except (TypeError, ValueError):
        return jsonify({'error': 'production and games must be numbers'}), 400
    if not 0.3 <= production <= 2.0 or (games is not None and not 0 <= games <= 82):
        return jsonify({'error': 'production must be 0.3-2.0 and games 0-82'}), 400
    ProjectionAdjustment.delete().where((ProjectionAdjustment.season == season)
                                        & (ProjectionAdjustment.player_id == player_id)).execute()
    if production != 1.0 or games is not None:
        ProjectionAdjustment.create(season=season, player_id=player_id, production=production, games=games,
                                    note=(data.get('note') or '')[:255] or None)
    return jsonify({'id': player_id, 'production': production, 'games': games})


@fantasy_api.route('/pickups')
def pickups():
    """Free agents ranked by how many more categories they'd win you in a week, with the best drop
    (lineup_optimizer.get_pickup_candidates). Judged against the week's opponent once its roster
    is in, else the league's average team, else an evenly matched team."""
    from lineup_optimizer import get_pickup_candidates
    league = current_league()
    week_start, week_end, opponent = _requested_week(league, request.args.get('week_start'))
    try:
        limit = max(1, min(int(request.args.get('limit', 40)), 100))
    except ValueError:
        return jsonify({'error': 'limit must be a whole number'}), 400
    result = get_pickup_candidates(league, week_start, week_end, opponent,
                                   request.args.get('timeframe', 'projected'), limit=limit)
    if 'error' in result:
        return jsonify(result), 422
    abbreviations = _team_abbreviations()
    for candidate in result['candidates']:
        team = candidate['team']
        candidate['team_abv'] = abbreviations.get(team) or abbreviations.get(TEAM_DICT.get(team, team)) or team[:3].upper()
    result['categories'] = category_meta(league.categories)
    return jsonify(result)


# ---------------------------------------------------------------- daily stats (NBA-wide)

@fantasy_api.route('/daily-stats', methods=['GET'])
def get_daily_stats():
    """Every stat line of a date. Points leagues: fantasy_points from the league's own weights,
    best first; category leagues have no points (None), sorted by points scored."""
    league = current_league()
    date_str = request.args.get('date')
    try:
        target_date = datetime.strptime(date_str, '%Y-%m-%d').date() if date_str else date.today()
    except ValueError:
        return jsonify({'error': 'Invalid date format. Use YYYY-MM-DD'}), 400

    stats = DailyPlayerStats.select().where(DailyPlayerStats.game_date == target_date)

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
            'fantasy_points': fantasy_points({k.upper(): getattr(stat, k.lower(), None) for k in POINT_STATS},
                                             league.point_weights) if league.is_points else None,
            'created_at': stat.created_at.isoformat() if stat.created_at else None
        })
    daily_stats.sort(key=lambda s: s['fantasy_points'] if league.is_points else (s['pts'] or 0), reverse=True)

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
