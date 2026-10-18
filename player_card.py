"""The player card (Daily Leaders / Player Rankings -> tap a name): one player's game log and
averages in the selected league's categories.

Rows of averages: Projection; Preseason at his projected minutes (per-minute rates x projected
MPG, the pace idea of Daily Leaders: preseason minutes are rotations, not roles); Adjusted (the
'_pre' timeframe: the projection moved by the preseason, preseason.py); Season, Last 10,
Last 5 once regular-season games exist (a window only when he has played more games than it).
Then one row per past season (last HISTORY_SEASONS, from player_seasons totals / games played).
Deltas are against the season once he has DELTA_SEASON_GAMES games, else against the projection.
Each game is scored exactly as Daily Leaders scores it (daily_leaders.score_line): summed category z
in category leagues, fantasy points in points leagues."""
from datetime import date

from daily_leaders import _ratio, game_value, league_scale, league_stats, owners, score_line
from fantasy_database import Game, GameLine, Player, PlayerSeason, PreseasonLine, Team
from game_log import season_label
from leagues import CATEGORY_CATALOG, category_meta, fantasy_points

DELTA_SEASON_GAMES = 10
HISTORY_SEASONS = 5
NBA_TO_TEAMS_ABV = {'BKN': 'BRK', 'CHA': 'CHO', 'PHX': 'PHO'}
TEAMS_TO_NBA_ABV = {v: k for k, v in NBA_TO_TEAMS_ABV.items()}
POINTS_COLUMNS = ['FPTS', 'PTS', 'REB', 'AST', 'STL', 'BLK', 'FG3M', 'TOV']
SUMMED = ['MIN', 'PTS', 'REB', 'AST', 'STL', 'BLK', 'TOV', 'PF', 'FGM', 'FGA', 'FG3M', 'FTM', 'FTA',
          'TECH', 'BLKA', 'W', 'PLUS_MINUS', 'DD2', 'TD3']


def _line(r, tech=None, techs_known=False):
    """A stored game row as the stat-line dict Daily Leaders scores. '_unknown': stats the source
    doesn't have per game (NBA rows: times blocked; preseason: technicals), shown as '–', not 0."""
    line = {'MIN': r.min or 0, 'PTS': r.pts, 'REB': r.reb, 'AST': r.ast, 'STL': r.stl, 'BLK': r.blk,
            'TOV': r.tov, 'PF': r.pf, 'FGM': r.fgm, 'FGA': r.fga, 'FG3M': r.fg3m, 'FTM': r.ftm, 'FTA': r.fta,
            'TECH': r.tech if r.tech is not None else (tech or 0), 'BLKA': r.blka or 0, 'W': r.w or 0,
            'PLUS_MINUS': r.plus_minus or 0}
    tens = sum(line[s] >= 10 for s in ('PTS', 'REB', 'AST', 'STL', 'BLK'))
    line['DD2'], line['TD3'] = int(tens >= 2), int(tens >= 3)
    line['_unknown'] = ({'BLKA'} if r.blka is None else set()) |         ({'TECH'} if r.tech is None and not techs_known else set())
    return line


def _value(cat, line, league):
    if cat == 'FPTS':
        return fantasy_points(line, league.point_weights)
    return game_value(cat, line)


def _average(cats, lines, league, minutes=None):
    """{cat: per-game average} over lines; ratios pooled (made / attempts). minutes: scale counting
    stats to that many minutes a game instead (per-minute rate x minutes)."""
    if not lines:
        return {}
    total = {k: sum(l.get(k) or 0 for l in lines) for k in SUMMED}
    unknown = set().union(*(l['_unknown'] for l in lines))
    per = (minutes / total['MIN']) if minutes and total['MIN'] else 1 / len(lines)
    out = {}
    for cat in cats:
        spec = CATEGORY_CATALOG.get(cat, {})
        if cat in unknown:
            out[cat] = None
        elif spec.get('kind') == 'ratio':
            out[cat] = _ratio(cat, total)[0]
        elif spec.get('kind') == 'wins':
            out[cat] = total['W'] / len(lines)
        else:
            v = _value(cat, total, league)
            out[cat] = None if v is None else v * per
    return out


def _cell(cat, line, league):
    """What a game-log cell shows: made/attempts for FG% and FT%, the rate for other ratios."""
    if cat in line['_unknown']:
        return '–'
    if cat in ('FG%', 'FT%'):
        made, att = ('FGM', 'FGA') if cat == 'FG%' else ('FTM', 'FTA')
        return f'{line[made]}/{line[att]}' if line[att] else '–'
    spec = CATEGORY_CATALOG.get(cat, {})
    if spec.get('kind') == 'ratio':
        rate = _ratio(cat, line)[0]
        return '–' if rate is None else (f'{rate * 100:.0f}' if spec.get('percent') else f'{rate:.2f}')
    if spec.get('kind') == 'wins':
        return 'W' if line['W'] else 'L'
    v = _value(cat, line, league)
    return '–' if v is None else (round(v, 1) if isinstance(v, float) else v)


def _teams():
    """(NBA abbreviation -> full name, full name -> NBA abbreviation)."""
    full = {}
    for t in Team.select(Team.name, Team.abv):
        if t.abv:
            full[TEAMS_TO_NBA_ABV.get(t.abv, t.abv)] = t.name
    return full, {v: k for k, v in full.items()}


def card(league, player_id=None, name=None):
    player = (Player.get_or_none(Player.id == player_id) if player_id else None) or \
             (Player.get_or_none(Player.name == name) if name else None)
    if player is None:
        return None
    season = season_label()
    stats = league_stats(league).get(player.name) or {}
    points = league.is_points
    cats = POINTS_COLUMNS if points else list(league.categories)
    meta = category_meta(cats)
    cats = [m['key'] for m in meta]  # display order (PTS REB AST... as on Daily Leaders)
    scale = None if points else league_scale(league)
    full, abv_of = _teams()

    rs_rows = list(GameLine.select().where((GameLine.player_id == player.id) & (GameLine.season == season))
                   .order_by(GameLine.game_date.desc()))
    pre_rows = list(PreseasonLine.select().where((PreseasonLine.player_id == player.id) & (PreseasonLine.season == season))
                    .order_by(PreseasonLine.game_date.desc()))
    techs = {}
    if 'TECH' in cats and any(r.source == 'nba' for r in rs_rows):
        from pull_technical_fouls import technicals_by_player
        techs = technicals_by_player([r.game_id for r in rs_rows if r.source == 'nba']).get(player.id, {})

    # Opponents of regular-season games, from the stored schedule (game_lines has no matchup).
    opp = {}
    if rs_rows:
        for g in Game.select().where(Game.date.in_([r.game_date for r in rs_rows])):
            for r in rs_rows:
                mine = full.get(r.team)
                if r.game_date == g.date and mine in (g.team_home, g.team_away):
                    other = g.team_away if mine == g.team_home else g.team_home
                    opp[r.game_date] = f"{'vs' if mine == g.team_home else '@'} {abv_of.get(other, other[:3].upper())}"

    def game(r, kind, line):
        value, zs = score_line(line, league, scale)
        for cat in line['_unknown'] & set(zs):
            value -= zs[cat] or 0
            zs[cat] = None
        matchup = opp.get(r.game_date) if kind == 'regular' else \
            (r.matchup.split(' ', 1)[1].replace('vs. ', 'vs ') if r.matchup and ' ' in r.matchup else None)
        return {'date': r.game_date.isoformat(), 'kind': kind, 'team': r.team, 'opp': matchup, 'w': bool(r.w),
                'min': r.min, 'plus_minus': r.plus_minus, 'value': round(value, 1 if points else 2),
                'cells': {c: _cell(c, line, league) for c in cats}, 'z': zs}

    rs_lines = [_line(r, techs.get(r.game_id), techs_known=True) for r in rs_rows]
    pre_lines = [_line(r) for r in pre_rows]
    games = [game(r, 'regular', l) for r, l in zip(rs_rows, rs_lines)] + \
            [game(r, 'preseason', l) for r, l in zip(pre_rows, pre_lines)]

    proj_min = stats.get('MIN_proj') or 0
    rows = []
    if any(stats.get(f'{c}_proj') is not None for c in cats):
        rows.append({'key': 'proj', 'label': 'Projection', 'note': f'{proj_min:.0f} min' if proj_min else None,
                     'values': {c: stats.get(f'{c}_proj') for c in cats}})
    if pre_lines:
        pre_min = sum(l['MIN'] for l in pre_lines)
        rows.append({'key': 'pre', 'label': 'Preseason',
                     'note': f'{len(pre_lines)} g, per {proj_min:.0f} min' if proj_min else f'{len(pre_lines)} g',
                     'title': (f'{len(pre_lines)} preseason games, {pre_min} minutes, scaled to his projected '
                               f'{proj_min:.0f} minutes a game' if proj_min else None),
                     'values': _average(cats, pre_lines, league, minutes=proj_min or None)})
    if stats.get('PRE_G') and any(stats.get(f'{c}_pre') is not None for c in cats):
        rows.append({'key': 'adj', 'label': 'Adjusted', 'note': f"{stats.get('MIN_pre') or 0:.0f} min",
                     'title': 'The projection moved by his preseason, weighted by how much preseason has predicted '
                              'the season (projections.md "Preseason signal")',
                     'values': {c: stats.get(f'{c}_pre') for c in cats}})
    n = len(rs_lines)
    if n:
        windows = [('season', 'Season', None, '')] + [(f'l{w}', f'Last {w}', w, f'_{w}') for w in (10, 5) if n > w]
        for key, label, w, suffix in windows:
            values = _average(cats, rs_lines[:w] if w else rs_lines, league)
            if 'BLKA' in values and values['BLKA'] is None:  # the NBA gives totals only: the player's stored ones
                values['BLKA'] = stats.get(f'BLKA{suffix}')
            rows.append({'key': key, 'label': label, 'note': f'{n} g' if key == 'season' else None, 'values': values})

    for s in (PlayerSeason.select().where((PlayerSeason.player_id == player.id) & (PlayerSeason.season < season)
                                          & (PlayerSeason.gp > 0)).order_by(PlayerSeason.season.desc()).limit(HISTORY_SEASONS)):
        line = {'MIN': s.min, 'PTS': s.pts, 'REB': s.reb, 'AST': s.ast, 'STL': s.stl, 'BLK': s.blk, 'TOV': s.tov,
                'PF': s.pf, 'FGM': s.fgm, 'FGA': s.fga, 'FG3M': s.fg3m, 'FTM': s.ftm, 'FTA': s.fta,
                'TECH': s.tech or 0, 'BLKA': s.blka, 'W': s.w, 'PLUS_MINUS': 0, 'DD2': s.dd2, 'TD3': s.td3}
        line = {k: v / s.gp for k, v in line.items()}  # totals -> one average game; pooled ratios are unchanged
        line['_unknown'] = {'TECH'} if s.tech is None else set()
        rows.append({'key': f'y{s.season}', 'label': s.season, 'note': f'{s.gp} g · {s.team or ""}'.rstrip(' ·'),
                     'values': _average(cats, [line], league)})

    team = owners(league).get(player.id)
    nxt = None
    if player.team:
        g = (Game.select().where((Game.date >= date.today()) & ((Game.team_home == player.team) | (Game.team_away == player.team)))
             .order_by(Game.date).first())
        if g:
            home = g.team_home == player.team
            other = g.team_away if home else g.team_home
            nxt = {'date': g.date.isoformat(), 'opp': f"{'vs' if home else '@'} {abv_of.get(other, other[:3].upper())}"}
    return {
        'id': player.id, 'name': player.name, 'team': abv_of.get(player.team, player.team),
        'positions': list(stats.get('Positions') or ()) or [p for p in (player.positions or player.pos or '').split('-') if p],
        'injured': bool(player.injured), 'injured_return': player.injured_return if player.injured else None,
        'rank': stats.get('Z-RANK_projected') or None, 'rank_season': stats.get('Z-RANK') if n else None,
        'owner': ('mine' if team[0] == league.my_team else 'taken') if team else 'free',
        'owner_name': team[1] if team else None, 'next_game': nxt,
        'scoring': 'points' if points else 'categories', 'season': season,
        'categories': meta, 'averages': rows,
        'delta_base': 'season' if n >= DELTA_SEASON_GAMES else ('proj' if rows and rows[0]['key'] == 'proj' else None),
        'games': games,
    }
