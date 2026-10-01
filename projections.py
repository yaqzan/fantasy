"""Season projections: sources in, one blended line per player out. NBA-wide (not per league).

Sources are rows in `player_projections` (per-game lines + games), one set per source:
  - experts: 'espn' (ESPN's fantasy API, pull_projections.py) and whatever import_projections.py
    loaded (FantasyPros, CBS, FanScout, RotoWire, a rookie survey...);
  - 'model': ours (projection_model.py), built from `player_seasons` history.
`player_lines(season)` averages the experts stat by stat (each over the sources that have it),
blends that with our model per player type (EXPERT_WEIGHT, measured out of sample; see
.claude/docs/projections.md), fills stats no expert projects (times blocked, fouls, technicals,
double/triple-doubles) from our model and the technical-foul scan, and applies the owner's
adjustments (`projection_adjustments`).
"""
import json
import re
import time
import unicodedata
from datetime import date

import requests

from fantasy_database import Player, PlayerProjection, PlayerSeason, ProjectionAdjustment, TeamProjection, TechnicalFoul

# The experts' average's share of the blend with our model, by player type: fit on 2024-25 and
# 2025-26 preseason projections (ESPN + FantasyPros, the two experts with a past) against what
# happened. Experts are best on rookies and young players; our model's history (games played
# above all) helps most with veterans and players who changed teams.
EXPERT_WEIGHT = {'rookie': 0.9, 'year 2-3': 0.9, 'other': 0.7, 'age 32+': 0.6, 'changed team': 0.5}
MODEL_SOURCES = {'model'}
# Shown for comparison but not averaged in. CBS (2026-27): per-game lines ~16% below every other
# source (median points ratio to ESPN .84, games 1.12x: season totals spread over too many games).
NOT_BLENDED = {'cbs'}
LINE = ['gp', 'min', 'pts', 'reb', 'ast', 'stl', 'blk', 'fg3m', 'tov', 'fgm', 'fga', 'ftm', 'fta',
        'blka', 'pf', 'tech', 'dd2', 'td3']
ESPN_BLENDED = ['gp', 'min', 'pts', 'reb', 'ast', 'stl', 'blk', 'fg3m', 'tov', 'fgm', 'fga', 'ftm', 'fta']
SCALED = ['min', 'pts', 'reb', 'ast', 'stl', 'blk', 'fg3m', 'tov', 'fgm', 'fga', 'ftm', 'fta', 'blka', 'pf', 'tech',
          'dd2', 'td3']
# Technicals are sticky: two seasons weighted beat last season alone (MAE 1.58 vs 1.72 techs per
# 2000 minutes, 2025-26), and pulling toward league average only hurt, so the prior is light.
TECH_WEIGHTS = (5, 4, 3)  # last three seasons
TECH_PRIOR_MIN = 300      # minutes of league-average technicals a player's own rate is blended with

ESPN_URL = 'https://lm-api-reads.fantasy.espn.com/apis/v3/games/fba/seasons/{year}/players?scoringPeriodId=0&view=kona_player_info'
# ESPN stat ids -> ours (checked against our 2025-26 totals, 2026-09-30).
ESPN_STATS = {'0': 'pts', '1': 'blk', '2': 'stl', '3': 'ast', '6': 'reb', '11': 'tov', '13': 'fgm', '14': 'fga',
              '15': 'ftm', '16': 'fta', '17': 'fg3m', '40': 'min', '42': 'gp'}
ESPN_POSITIONS = {1: 'G', 2: 'G', 3: 'F', 4: 'F', 5: 'C'}


def season_label(today=None):
    """The season being played or next up: '2026-27' from July 2026 to June 2027."""
    today = today or date.today()
    start = today.year if today.month >= 7 else today.year - 1
    return f'{start}-{str(start + 1)[2:]}'


# Names sources spell differently from the NBA (normalized form -> NBA's normalized form).
NAME_ALIASES = {'carlton carrington': 'bub carrington', 'moe wagner': 'moritz wagner', 'gregory jackson': 'gg jackson',
                'dom barlow': 'dominick barlow', 'nicolas claxton': 'nic claxton', 'herb jones': 'herbert jones',
                'cam johnson': 'cameron johnson', 'kj martin': 'kenyon martin', 'ron holland': 'ronald holland'}


def norm_name(name):
    s = unicodedata.normalize('NFKD', str(name)).encode('ascii', 'ignore').decode()
    s = re.sub(r"[.'`,]", '', s.lower())
    s = re.sub(r'\b(jr|sr|ii|iii|iv|v)\b', '', s)
    s = re.sub(r'\s+', ' ', s).strip()
    return NAME_ALIASES.get(s, s)


def name_index():
    """{normalized name: NBA player id} from the players table and past seasons."""
    index = {}
    for p in Player.select(Player.id, Player.name):
        index.setdefault(norm_name(p.name), p.id)
    for p in PlayerSeason.select(PlayerSeason.player_id, PlayerSeason.name).distinct():
        index.setdefault(norm_name(p.name), p.player_id)
    return index


# ------------------------------------------------------------------ sources

def fetch_espn(season):
    """ESPN's projections for `season` as [{player_id, name, <LINE per game>}], plus unmatched names
    and positions ESPN gives (for players our rosters list without one)."""
    year = int(season[:4]) + 1
    headers = {'User-Agent': 'Mozilla/5.0', 'X-Fantasy-Filter': json.dumps({'players': {'limit': 5000}})}
    for attempt in range(4):
        try:
            response = requests.get(ESPN_URL.format(year=year), headers=headers, timeout=120)
            response.raise_for_status()
            data = response.json()
            break
        except (requests.RequestException, ValueError) as e:
            if attempt == 3:
                raise
            print(f'ESPN attempt {attempt + 1} failed ({e}); retrying')
            time.sleep(5 * (attempt + 1))
    index = name_index()
    rows, unmatched, positions = [], [], {}
    for entry in data if isinstance(data, list) else data.get('players', []):
        info = entry.get('player', entry)
        stat_set = next((s for s in info.get('stats', []) if s.get('seasonId') == year
                         and s.get('statSourceId') == 1 and s.get('statSplitTypeId') == 0), None)
        totals = (stat_set or {}).get('stats') or {}
        gp = totals.get('42') or 0
        # Rows with games but no stat line aren't projections; a missing stat otherwise means 0.
        if gp <= 0 or '0' not in totals or '14' not in totals:
            continue
        pid = index.get(norm_name(info.get('fullName')))
        if pid is None:
            unmatched.append(info.get('fullName'))
            continue
        line = {ours: (totals.get(sid) or 0.0) / gp for sid, ours in ESPN_STATS.items() if ours != 'gp'}
        rows.append({'player_id': pid, 'name': info.get('fullName'), 'gp': float(gp), **line})
        if info.get('defaultPositionId') in ESPN_POSITIONS:
            positions[pid] = ESPN_POSITIONS[info['defaultPositionId']]
    return rows, unmatched, positions


def history_frame():
    """`player_seasons` as the DataFrame projection_model expects."""
    import pandas as pd
    rows = list(PlayerSeason.select().dicts())
    h = pd.DataFrame(rows)
    h = h.rename(columns={'player_id': 'PLAYER_ID', 'name': 'PLAYER_NAME', 'team': 'TEAM_ABBREVIATION', 'age': 'AGE',
                          'gp': 'GP', 'min': 'MIN', 'w': 'W'})
    h['SEASON'] = h.season.str[:4].astype(int)
    for col in ['pts', 'reb', 'ast', 'stl', 'blk', 'fg3m', 'tov', 'fgm', 'fga', 'ftm', 'fta', 'blka', 'pf', 'dd2', 'td3']:
        h[col.upper()] = h[col]
    return h


def drafts_frame():
    import pandas as pd
    from nba_api.stats.endpoints import drafthistory
    d = drafthistory.DraftHistory(timeout=120).get_data_frames()[0]
    d = d[d.SEASON.astype(int) >= 2005]
    return pd.DataFrame({'PLAYER_ID': d.PERSON_ID.astype(int), 'PLAYER_NAME': d.PLAYER_NAME,
                         'SEASON': d.SEASON.astype(int), 'OVERALL_PICK': d.OVERALL_PICK.astype(int)})


def model_rows(season):
    """Our model's projections for `season` as rows for `player_projections` (source 'model')."""
    from projection_model import project_season
    proj = project_season(history_frame(), drafts_frame(), int(season[:4]))
    rows = []
    for r in proj.itertuples():
        mpg = r.MPG
        rows.append({'player_id': int(r.PLAYER_ID), 'name': r.PLAYER_NAME, 'gp': float(r.GP), 'min': float(mpg),
                     **{s.lower(): float(getattr(r, s)) for s in
                        ['PTS', 'REB', 'AST', 'STL', 'BLK', 'FG3M', 'TOV', 'FGM', 'FGA', 'FTM', 'FTA', 'BLKA', 'PF',
                         'DD2', 'TD3']},
                     'age': None if r.AGE != r.AGE else float(r.AGE), 'exp': int(r.EXP),
                     'prev_team': r.PREV_TEAM if isinstance(r.PREV_TEAM, str) else None})
    return rows


def tech_rates():
    """({player id: technicals per minute}, league rate): the last three seasons weighted
    TECH_WEIGHTS by minutes, plus TECH_PRIOR_MIN minutes of league average. Counts are Fantrax's
    (the league platform scores them; `pull_fantrax.py techs`), else our play-by-play scan for
    the last season."""
    seasons = [s for (s,) in PlayerSeason.select(PlayerSeason.season).distinct()
               .order_by(PlayerSeason.season.desc()).tuples()][:3]
    scan = {}
    for t in TechnicalFoul.select():
        scan[t.player_id] = scan.get(t.player_id, 0) + t.count
    num, den = {}, {}
    league_techs = league_min = 0.0
    for weight, season in zip(TECH_WEIGHTS, seasons):
        rows = list(PlayerSeason.select().where(PlayerSeason.season == season))
        has_fantrax = any(p.tech is not None for p in rows)
        for p in rows:
            techs = p.tech if has_fantrax else (scan.get(p.player_id, 0) if season == seasons[0] else None)
            if techs is None:
                continue
            num[p.player_id] = num.get(p.player_id, 0) + weight * techs
            den[p.player_id] = den.get(p.player_id, 0) + weight * p.min
            if season == seasons[0]:
                league_techs += techs
                league_min += p.min
    league = league_techs / league_min if league_min else 0.0
    rates = {p: (num[p] + TECH_PRIOR_MIN * league) / (den[p] + TECH_PRIOR_MIN) for p in num}
    return rates, league


def store(season, source, rows):
    """Replace one source's rows for a season."""
    from fantasy_database import DB
    with DB.atomic():
        PlayerProjection.delete().where((PlayerProjection.season == season) & (PlayerProjection.source == source)).execute()
        for i in range(0, len(rows), 300):
            PlayerProjection.insert_many([{'season': season, 'source': source, **r} for r in rows[i:i + 300]]).execute()


# ------------------------------------------------------------------ teams

TEAM_PRIOR_GAMES = 20       # the preseason projection counts as this many games of real record
# Weight in the win index by inverse squared error on past seasons: Vegas lines have been the most
# accurate for 13 seasons (off by 6.5 wins a team), the others only a little behind on the seasons
# they cover. Sources without a track record are shown but carry no weight.
TEAM_SOURCE_WEIGHT = {'vegas_consensus': 0.41, 'espn_summer_forecast': 0.30, 'bleacher_report': 0.29,
                      'si_staff': 0.0, 'sportingnews_noh': 0.0}
LAST_SEASON_REGRESSION = 0.7  # without projections: last season's win %, 30% of the way back to .500


def team_projection_index(season):
    """{team: {'wins': weighted mean of the sources' projected wins, 'low', 'high', 'sources': {source:
    wins}, 'adjustment': owner's +/- wins, 'final': wins + adjustment}} for `season`."""
    by_team = {}
    for row in TeamProjection.select().where(TeamProjection.season == season):
        by_team.setdefault(row.team, {})[row.source] = row.wins
    index = {}
    for team, sources in by_team.items():
        adjustment = sources.pop('owner', 0.0)
        if not sources:
            continue
        weights = {s: TEAM_SOURCE_WEIGHT.get(s, 1.0) for s in sources}
        if not sum(weights.values()):
            weights = {s: 1.0 for s in sources}
        wins = sum(sources[s] * weights[s] for s in sources) / sum(weights.values())
        index[team] = {'wins': wins, 'low': min(sources.values()), 'high': max(sources.values()),
                       'sources': sources, 'adjustment': adjustment, 'final': wins + adjustment}
    return index


def team_strength(season=None):
    """{team name: chance of winning a game}. Before the season: the projection index (with the
    owner's adjustments), or last season's win % pulled toward .500 when there is none. Once games
    are played the real record takes over: (wins + K x projected %) / (games + K), K =
    TEAM_PRIOR_GAMES, so after 20 games projection and record count the same."""
    from fantasy_database import Team
    season = season or season_label()
    index = team_projection_index(season)
    strength = {}
    for team in Team.select():
        if team.name in index:
            projected = min(max(index[team.name]['final'] / 82, 0.05), 0.95)
        elif team.win_percentage is not None and team.record_season != season:
            projected = 0.5 + LAST_SEASON_REGRESSION * (team.win_percentage - 0.5)
        else:
            projected = 0.5
        if team.record_season == season and (team.wins or 0) + (team.losses or 0) > 0:
            games = team.wins + team.losses
            strength[team.name] = (team.wins + TEAM_PRIOR_GAMES * projected) / (games + TEAM_PRIOR_GAMES)
        else:
            strength[team.name] = projected
    return strength


# ------------------------------------------------------------------ the blend

def player_type(model_row, current_team_abv):
    """rookie / year 2-3 / changed team / age 32+ / other, from our model's row."""
    if model_row is None or model_row.get('exp') in (None, 0):
        return 'rookie'
    if model_row['exp'] <= 2:
        return 'year 2-3'
    if model_row.get('prev_team') and current_team_abv and model_row['prev_team'] != current_team_abv:
        return 'changed team'
    if (model_row.get('age') or 0) >= 32:
        return 'age 32+'
    return 'other'


def player_lines(season, team_abv=None):
    """{player id: blended per-game line (LINE keys, 'gp' = projected games) + 'sources', 'type',
    'adjusted'} for `season`. team_abv: {player id: current team abbreviation}, to spot players who
    changed teams (default: from the players table)."""
    by_source = {}
    for row in PlayerProjection.select().where(PlayerProjection.season == season).dicts():
        by_source.setdefault(row['source'], {})[row['player_id']] = row
    if not by_source:
        return {}
    if team_abv is None:
        from fantasy_database import Team
        abv = {t.name: t.abv for t in Team.select()}
        team_abv = {p.id: abv.get(p.team) for p in Player.select(Player.id, Player.team).where(Player.team.is_null(False))}
    model = by_source.get('model', {})
    experts = {s: rows for s, rows in by_source.items() if s not in MODEL_SOURCES | NOT_BLENDED}
    rates, league_tech = tech_rates()
    adjustments = {a.player_id: a for a in ProjectionAdjustment.select().where(ProjectionAdjustment.season == season)}
    lines = {}
    everyone = set(model).union(*[set(rows) for rows in experts.values()])
    for pid in everyone:
        m = model.get(pid)
        mine = {s: rows[pid] for s, rows in experts.items() if pid in rows}
        e = {}
        for stat in ESPN_BLENDED:
            values = [row[stat] for row in mine.values() if row.get(stat) is not None]
            if values:
                e[stat] = sum(values) / len(values)
        e = e or None
        kind = player_type(m, team_abv.get(pid))
        w = EXPERT_WEIGHT[kind] if (m and e) else (1.0 if e else 0.0)
        line = {}
        for stat in ESPN_BLENDED:
            ev, mv = (e or {}).get(stat), (m or {}).get(stat)
            line[stat] = (w * ev + (1 - w) * mv) if (ev is not None and mv is not None) else (ev if ev is not None else mv)
        if line.get('gp') is None or line.get('min') is None or line.get('pts') is None:
            continue  # e.g. only a source without games or minutes (RotoWire) has him
        for stat in ESPN_BLENDED:
            if line.get(stat) is None:
                line[stat] = 0.0
        # Stats only our model projects: per shot (times blocked), per minute (fouls) or scaled
        # with scoring (double/triple-doubles), so they follow the blended line.
        if m and m.get('fga'):
            line['blka'] = m['blka'] / m['fga'] * line['fga']
        else:
            line['blka'] = 0.07 * line['fga']
        line['pf'] = (m['pf'] / m['min'] * line['min']) if (m and m.get('min')) else 0.09 * line['min']
        ratio = (line['pts'] / m['pts']) if (m and m.get('pts')) else 1.0
        line['dd2'] = (m['dd2'] * ratio) if m else 0.0
        line['td3'] = (m['td3'] * ratio) if m else 0.0
        line['tech'] = rates.get(pid, league_tech) * line['min']
        adj = adjustments.get(pid)
        if adj:
            for stat in SCALED:
                line[stat] *= adj.production
            if adj.games is not None:
                line['gp'] = adj.games
        line.update({'sources': sorted(mine) + (['model'] if m else []), 'type': kind, 'expert_weight': w,
                     'exp': m.get('exp') if m else None,  # NBA seasons before this one (our model's row)
                     'adjusted': adj is not None, 'name': (m or next(iter(mine.values())))['name']})
        lines[pid] = line
    return lines
