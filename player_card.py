"""The player card (Daily Leaders / Player Rankings -> tap a name): one player's game log and
averages in the selected league's categories.

Rows of averages: Projection; Preseason at his projected minutes (per-minute rates x projected
MPG, the pace idea of Daily Leaders: preseason minutes are rotations, not roles); Updated (the
'_projected' timeframe, THE projection: the model moved by the preseason, preseason.py, then by his games, inseason.py); Season, Last 10,
Last 5 once regular-season games exist (a window only when he has played more games than it).
Then one row per past season (last HISTORY_SEASONS, from player_seasons totals / games played).
Deltas are against the season once he has DELTA_SEASON_GAMES games, else against the projection.
Each game is scored exactly as Daily Leaders scores it (daily_leaders.score_line): summed category z
in category leagues, fantasy points in points leagues."""
from datetime import date
from types import SimpleNamespace

from daily_leaders import _ratio, game_value, league_scale, league_stats, nba_today, owners, score_line, slate
from fantasy_database import Game, GameLine, Player, PlayerSeason, PreseasonLine, Team
from fantasy_team_helper import get_current_fantasy_week_dates
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


def _average(cats, lines, league, minutes=None, scale=None):
    """{cat: per-game average} over lines; ratios pooled (made / attempts). minutes: scale counting
    stats to that many minutes a game instead (per-minute rate x minutes)."""
    if not lines:
        return {}
    total = {k: sum(l.get(k) or 0 for l in lines) for k in SUMMED}
    unknown = set().union(*(l['_unknown'] for l in lines))
    per = (minutes / total['MIN']) if minutes and total['MIN'] else 1 / len(lines)
    out = {'MIN': minutes or total['MIN'] / len(lines)}
    if scale:  # z of the average game, to colour the cells like the game log
        avg = {k: v * per for k, v in total.items()}
        avg['_unknown'] = unknown
        zs = score_line(avg, league, scale)[1]
        out['_z'] = {c: (None if c in unknown else z) for c, z in zs.items()}
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


def _note(games, minutes, age):
    """The sub-label under an average row: games, minutes a game, age."""
    parts = (f"{games:.0f} game{'' if round(games) == 1 else 's'}" if games else '', f'{minutes:.0f}mpg' if minutes else '',
             f'{age:.0f} yo' if age else '')
    return ' · '.join(x for x in parts if x) or None


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
        by_date = {r.game_date: r for r in rs_rows}
        teams = {full.get(r.team) for r in rs_rows} - {None}
        for g in Game.select().where(Game.date.in_(list(by_date)) & (Game.team_home.in_(teams) | Game.team_away.in_(teams))):
            mine = full.get(by_date[g.date].team) if g.date in by_date else None
            if mine in (g.team_home, g.team_away):
                other = g.team_away if mine == g.team_home else g.team_home
                opp[g.date] = f"{'vs' if mine == g.team_home else '@'} {abv_of.get(other, other[:3].upper())}"

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

    last = (PlayerSeason.select(PlayerSeason.season, PlayerSeason.age).where((PlayerSeason.player_id == player.id) & PlayerSeason.age.is_null(False))
            .order_by(PlayerSeason.season.desc()).first())  # his age this season: his last recorded one plus the years since
    age_now = last.age + int(season[:4]) - int(last.season[:4]) if last else None
    year = season  # '2026-27', how the card names seasons
    proj_min = stats.get('MIN_proj') or 0
    rows = []
    n = len(rs_lines)
    if n:
        values = _average(cats, rs_lines, league, scale=scale)
        if 'BLKA' in values and values['BLKA'] is None:  # the NBA gives totals only: the player's stored ones
            values['BLKA'] = stats.get('BLKA')
        rows.append({'key': 'season', 'label': f'{year} Season', 'note': _note(n, values['MIN'], age_now), 'values': values})
    # Running Projection: the projection moved by his preseason and then by his games this season (the
    # '_projected' timeframe); before either exists, the plain projection under the same name.
    running = (stats.get('PRE_G') or rs_lines) and 'GP_proj' in stats and any(stats.get(f'{c}_projected') is not None for c in cats)
    sfx = '_projected' if running else '_proj'
    if running or any(stats.get(f'{c}_proj') is not None for c in cats):
        rows.append({'key': 'adj', 'label': f'{year} Running Projection', 'note': _note(stats.get('GP' + sfx), stats.get('MIN' + sfx), age_now),
                     'title': 'The projection moved by his preseason and then by his games this season, each stat weighted '
                              'by how much that has predicted the rest of the season (projections.md "In-season update")',
                     'values': {'MIN': stats.get('MIN' + sfx) or None, **{c: stats.get(c + sfx) for c in cats}}})
    if pre_lines:
        pre_min = sum(l['MIN'] for l in pre_lines)
        rows.append({'key': 'pre', 'label': f'{year} Preseason',
                     'note': _note(len(pre_lines), proj_min or pre_min / len(pre_lines), age_now),
                     'title': (f'{len(pre_lines)} preseason games, {pre_min} minutes, scaled to his projected '
                               f'{proj_min:.0f} minutes a game' if proj_min else None),
                     'values': _average(cats, pre_lines, league, minutes=proj_min or None, scale=scale)})

    for s in (PlayerSeason.select().where((PlayerSeason.player_id == player.id) & (PlayerSeason.season < season)
                                          & (PlayerSeason.gp > 0)).order_by(PlayerSeason.season.desc()).limit(HISTORY_SEASONS)):
        line = {'MIN': s.min, 'PTS': s.pts, 'REB': s.reb, 'AST': s.ast, 'STL': s.stl, 'BLK': s.blk, 'TOV': s.tov,
                'PF': s.pf, 'FGM': s.fgm, 'FGA': s.fga, 'FG3M': s.fg3m, 'FTM': s.ftm, 'FTA': s.fta,
                'TECH': s.tech or 0, 'BLKA': s.blka, 'W': s.w, 'PLUS_MINUS': 0, 'DD2': s.dd2, 'TD3': s.td3}
        line = {k: v / s.gp for k, v in line.items()}  # totals -> one average game; pooled ratios are unchanged
        line['_unknown'] = {'TECH'} if s.tech is None else set()
        values = _average(cats, [line], league, scale=scale)
        rows.append({'key': f'y{s.season}', 'label': s.season,
                     'note': _note(s.gp, values['MIN'], s.age),
                     'values': values})

    team = owners(league).get(player.id)
    nxt, upcoming = None, []  # next game, and his team's games to the end of this fantasy week (not yet in the log)
    if player.team:
        week_end = get_current_fantasy_week_dates(league)[1]
        played = {r.game_date for r in rs_rows}
        for g in (Game.select().where((Game.date >= date.today()) & ((Game.team_home == player.team) | (Game.team_away == player.team)))
                  .order_by(Game.date)):
            if g.date in played:
                continue
            home = g.team_home == player.team
            other = g.team_away if home else g.team_home
            item = {'date': g.date.isoformat(), 'opp': f"{'vs' if home else '@'} {abv_of.get(other, other[:3].upper())}"}
            nxt = nxt or item
            if g.date <= week_end:
                upcoming.append(item)
            else:
                break

    # Tonight's game, live or final but not yet in game_lines (that lands after the night): the line
    # Daily Leaders holds, so the log shows it as it happens.
    today = nba_today().isoformat()
    tonight = next((u for u in upcoming if u['date'] == today), None)
    if tonight:
        try:
            from projections import norm_name
            cur = slate(nba_today())
            me = norm_name(player.name)
            state = {t['abbr']: g['state'] for g in cur['scoreboard'] for t in g['teams']}
            line = next((l for lines in cur['games'].values() for l in lines.values() if norm_name(l['name']) == me), None)
        except Exception:  # ESPN hiccup: the log just lacks tonight's row
            line = None
        if line:
            line = {**line, '_unknown': set()}
            live = SimpleNamespace(game_date=nba_today(), team=player.team, w=line['W'], min=line['MIN'],
                                   plus_minus=line['PLUS_MINUS'], matchup=None)
            opp[live.game_date] = tonight['opp']
            row = game(live, 'regular', line)
            row['live'] = state.get(line['team']) == 'in'
            if line['W'] is None and 'WIN%' in row['cells']:
                row['cells']['WIN%'] = '…'  # the result isn't known until the game ends
            games.insert(0, row)
            upcoming.remove(tonight)
    upcoming.reverse()  # newest first like the log: the next game sits right above the last one played
    return {
        'upcoming': upcoming,
        'id': player.id, 'name': player.name, 'team': abv_of.get(player.team, player.team),
        'positions': list(stats.get('Positions') or ()) or [p for p in (player.positions or player.pos or '').split('-') if p],
        'injured': bool(player.injured), 'injured_return': player.injured_return if player.injured else None,
        'rank': stats.get('Z-RANK_projected') or None, 'rank_season': stats.get('Z-RANK') if n else None,
        'owner': ('mine' if team[0] == league.my_team else 'taken') if team else 'free',
        'owner_name': team[1] if team else None, 'next_game': nxt,
        'scoring': 'points' if points else 'categories', 'season': season,
        'categories': meta, 'averages': rows,
        'delta_base': 'season' if n >= DELTA_SEASON_GAMES else ('adj' if any(r['key'] == 'adj' for r in rows) else None),
        'games': games,
    }
