"""Leagues: each one carries its own rules and teams, and the app switches between them.

A league's rules are a JSON document in `leagues.settings` (DEFAULT_SETTINGS shows every key).
Requests pick a league with the `X-League` header (the frontend sends the one selected in the
switcher); CLI scripts and header-less requests use the active league (`leagues.is_active`).
"""
import copy
import json
import re
from datetime import date, datetime, timedelta

from fantasy_database import DB, League, FantasyTeam, FantasyTeamPlayer, LeaguePlayerFlag


class NotFound(LookupError):
    """No such league (or team / week in it); the API answers 404."""

# Every category the stats pipeline can compute. `inverse`: lower wins. `kind`: how a team total
# is built (count = per-game rate x games, ratio = from summed components, wins = expected wins).
# `noise`: a count's game-to-game variance, sum of coef x the player's per-game stat (None = 1 per
# game); `attempt_sd`: a ratio's spread per attempt; wins are Bernoulli. Both measured on the
# 2025-26 game logs (452 players with 20+ games); they set how likely a weekly lead holds up.
CATEGORY_CATALOG = {
    'PTS': {'label': 'PTS', 'name': 'Points', 'kind': 'count', 'noise': [('PTS', 3.4)]},
    'REB': {'label': 'REB', 'name': 'Rebounds', 'kind': 'count', 'noise': [('REB', 1.5)]},
    'AST': {'label': 'AST', 'name': 'Assists', 'kind': 'count', 'noise': [('AST', 1.3)]},
    'STL': {'label': 'STL', 'name': 'Steals', 'kind': 'count', 'noise': [('STL', 1.1)]},
    'BLK': {'label': 'BLK', 'name': 'Blocks', 'kind': 'count', 'noise': [('BLK', 1.1)]},
    'FG3M': {'label': '3PM', 'name': 'Three-pointers made', 'kind': 'count', 'noise': [('FG3M', 1.2)]},
    'AST-TOV': {'label': 'A-TO', 'name': 'Assists minus turnovers', 'kind': 'count',
                'noise': [('AST', 1.1), ('TOV', 1.1)]},
    'NFT': {'label': 'NFT', 'name': 'Net free throws (2*FTM - FTA)', 'kind': 'count', 'noise': [('FTA', 1.5)]},
    'DD2': {'label': 'DD', 'name': 'Double-doubles', 'kind': 'count', 'noise': [('DD2', 0.7)]},
    'TD3': {'label': 'TD', 'name': 'Triple-doubles', 'kind': 'count', 'noise': [('TD3', 0.8)]},
    'PLUS_MINUS': {'label': '+/-', 'name': 'Plus/minus', 'kind': 'count', 'noise': [(None, 127.0)]},
    'TOV': {'label': 'TOV', 'name': 'Turnovers', 'kind': 'count', 'inverse': True, 'noise': [('TOV', 1.1)]},
    'PF': {'label': 'PF', 'name': 'Personal fouls', 'kind': 'count', 'inverse': True, 'noise': [('PF', 1.0)]},
    # No per-game times-blocked data; assumed Poisson like blocks and steals.
    'BLKA': {'label': 'TB', 'name': 'Times blocked', 'kind': 'count', 'inverse': True, 'noise': [('BLKA', 1.0)]},
    'TECH': {'label': 'TF', 'name': 'Technical fouls', 'kind': 'count', 'inverse': True, 'noise': [('TECH', 1.0)]},
    'WIN%': {'label': 'W', 'name': 'Wins', 'kind': 'wins'},
    # Points leagues: the league's own point weights (`scoring.points`) collapse every stat into this one
    # category (player_stats.add_fantasy_points). Noise: variance per game 6.0x the mean, measured on the
    # 2025-26 game logs with the default weights (fantasy_config.FPOINTS_SCORING; 452 players, same
    # method as above). It grows roughly with the size of the weights.
    'FPTS': {'label': 'FPTS', 'name': 'Fantasy points', 'kind': 'count', 'noise': [('FPTS', 6.0)]},
    # Ratios are valued by impact (player_stats.py). `attempts`: the per-game attempts behind the
    # rate, as (stat, coefficient) terms. `prior`: attempts of league-average shooting a player's
    # rate is blended with before scoring (method of moments on 2025-26: TS% ~233, EFG% ~223,
    # FG% ~55, FT% ~27, PPS ~98).
    'FG%': {'label': 'FG%', 'name': 'Field goal %', 'kind': 'ratio', 'percent': True,
            'attempts': [('FGA', 1.0)], 'prior': 60, 'attempt_sd': 0.499},
    'TS%': {'label': 'TS%', 'name': 'True shooting %', 'kind': 'ratio', 'percent': True,
            'attempts': [('FGA', 1.0), ('FTA', 0.44)], 'prior': 250, 'attempt_sd': 0.566},
    'EFG%': {'label': 'EFG%', 'name': 'Effective FG %', 'kind': 'ratio', 'percent': True,
             'attempts': [('FGA', 1.0)], 'prior': 250, 'attempt_sd': 0.578},
    'FT%': {'label': 'FT%', 'name': 'Free throw %', 'kind': 'ratio', 'percent': True,
            'attempts': [('FTA', 1.0)], 'prior': 50, 'attempt_sd': 0.404},
    'PPS': {'label': 'PPS', 'name': 'Points per shot', 'kind': 'ratio', 'attempts': [('FGA', 1.0)], 'prior': 100,
            'attempt_sd': 1.327},
}
# Column order in tables: shooting first, then counting stats, inverse categories last.
CATEGORY_ORDER = ['TS%', 'EFG%', 'FG%', 'FT%', 'PPS', 'PTS', 'REB', 'AST', 'AST-TOV', 'STL', 'BLK', 'FG3M', 'NFT',
                  'DD2', 'TD3', 'WIN%', 'PLUS_MINUS', 'TOV', 'PF', 'BLKA', 'TECH']

# Stats a points league can weight (per-player per-game keys in player_stats), with display names.
POINT_STATS = {'PTS': 'Points', 'REB': 'Rebounds', 'AST': 'Assists', 'STL': 'Steals', 'BLK': 'Blocks',
               'TOV': 'Turnovers', 'FGM': 'Field goals made', 'FGA': 'Field goals attempted',
               'FTM': 'Free throws made', 'FTA': 'Free throws attempted', 'FG3M': 'Three-pointers made',
               'PF': 'Personal fouls', 'DD2': 'Double-doubles', 'TD3': 'Triple-doubles',
               'TECH': 'Technical fouls', 'BLKA': 'Times blocked'}

# Roster slots. A slot takes a player when one of his positions reaches it: platform positions
# (PG/SG/SF/PF/C) or NBA's generic G/F/C, which count for every slot of their group (a 'G' fills PG).
SLOT_TYPES = ['PG', 'SG', 'G', 'SF', 'PF', 'F', 'C', 'UTIL']
POSITION_REACH = {'PG': {'PG', 'G'}, 'SG': {'SG', 'G'}, 'G': {'PG', 'SG', 'G'}, 'SF': {'SF', 'F'}, 'PF': {'PF', 'F'},
                  'F': {'SF', 'PF', 'F'}, 'C': {'C'}}


def slot_reach(positions):
    """Every slot a player with these positions can fill (UTIL always)."""
    return set().union({'UTIL'}, *(POSITION_REACH.get(p, ()) for p in positions))


def fantasy_points(line, weights):
    """Points for one stat line ({stat: value}, POINT_STATS keys) under a league's weights."""
    return round(sum((line.get(stat) or 0) * weight for stat, weight in weights.items()), 2)


DEFAULT_SETTINGS = {
    'season': '',                     # e.g. "2026-27", display only
    'platform': 'fantrax',            # fantrax | yahoo: which importer reads it (pull_fantrax.py / pull_yahoo.py)
    'platform_league_id': '',         # the platform's league id (Fantrax id, Yahoo league number)
    'my_team': '',                    # your team's abbreviation in this league's fantasy_teams
    'num_teams': 12,
    # Scoring: 'categories' = head-to-head over `categories`; 'points' = the weights in `points`
    # ({stat: points per unit}, keys from POINT_STATS) and the only category is FPTS.
    'scoring': {'type': 'categories', 'points': {}},
    'categories': ['PTS', 'REB', 'AST', 'STL', 'BLK', 'FG3M', 'TOV', 'TS%', 'FT%'],
    'roster': {
        'size': 13,                   # total roster spots
        'active': 10,                 # starters that score
        'daily_lineups': True,        # True: lineups set daily (best `active` of each day count);
                                      # False: one lineup of `active` players for the whole week
        'slots': [],                  # the `active` starting slots (SLOT_TYPES), e.g. PG SG G SF PF F C UTIL UTIL;
                                      # empty = all UTIL (no positions)
    },
    'draft': {'type': 'auction', 'budget': 200, 'date': '',
              'price_exponent': 1.0},     # auction $ follow value over replacement ** this;
                                          # fit to the league's past drafts (1 = linear)
    'waivers': {'claims_per_week': 1,
                'faab_budget': 0,             # free agent auction budget for the season (0 = no FAAB)
                'faab_per_stage': 0},         # FAAB wins allowed per elimination stage (0 = no limit)
    # Guillotine: the season is split into stages of consecutive matchup weeks; after each stage
    # but the last, the `per_stage` teams with the worst record over it are eliminated and their
    # players become free agents. Empty `stage_weeks` = an ordinary league.
    'elimination': {'stage_weeks': [], 'per_stage': 2},
    'playoffs': {'teams': 0, 'first_week': 0},  # teams that make it, first playoff week (1-based); 0 = none
    'schedule': [],                   # [[week start "YYYY-MM-DD", opponent abbreviation], ...]
    'notes': '',                      # free text: prizes, tie-breakers, anything else
}


def category_meta(categories=None):
    """Label/inverse/percent info for the frontend, in display order."""
    keys = categories if categories is not None else list(CATEGORY_CATALOG)
    ordered = [c for c in CATEGORY_ORDER if c in keys] + [c for c in keys if c not in CATEGORY_ORDER]
    return [{'key': c, 'label': CATEGORY_CATALOG[c]['label'], 'name': CATEGORY_CATALOG[c]['name'],
             'inverse': bool(CATEGORY_CATALOG[c].get('inverse')), 'percent': bool(CATEGORY_CATALOG[c].get('percent'))}
            for c in ordered if c in CATEGORY_CATALOG]


def _merge(defaults, given):
    out = copy.deepcopy(defaults)
    for key, value in (given or {}).items():
        if isinstance(out.get(key), dict) and isinstance(value, dict):
            out[key] = _merge(out[key], value)
        else:
            out[key] = value
    return out


def _parse_date(value):
    return datetime.strptime(str(value).strip(), '%Y-%m-%d').date()


def _upgrade(settings):
    """Older settings documents: position minimums become G/F/C slots (the rest UTIL), and
    fantrax_league_id becomes platform_league_id."""
    s = copy.deepcopy(settings or {})
    roster = s.get('roster') or {}
    mins = [(pos, int(roster.pop(key, 0) or 0))
            for pos, key in (('G', 'min_guards'), ('F', 'min_forwards'), ('C', 'min_centers'))]
    if not roster.get('slots') and any(n for _, n in mins):
        slots = [pos for pos, n in mins for _ in range(n)]
        roster['slots'] = slots + ['UTIL'] * max(int(roster.get('active') or 0) - len(slots), 0)
    legacy_id = s.pop('fantrax_league_id', '')
    if legacy_id and not s.get('platform_league_id'):
        s['platform_league_id'] = legacy_id
    return s


def validate_settings(settings):
    """Merge onto the defaults and check every value; raises ValueError with a readable message."""
    s = _merge(DEFAULT_SETTINGS, _upgrade(settings))
    scoring = s['scoring']
    if scoring['type'] == 'points':
        try:
            points = {k: float(v) for k, v in (scoring['points'] or {}).items() if v not in ('', None)}
        except (TypeError, ValueError):
            raise ValueError('point weights must be numbers')
        unknown = [k for k in points if k not in POINT_STATS]
        if unknown:
            raise ValueError(f"unknown point stats: {', '.join(unknown)}")
        if not any(points.values()):
            raise ValueError('a points league needs at least one point weight')
        scoring['points'] = points
        s['categories'] = ['FPTS']
    elif scoring['type'] == 'categories':
        scoring['points'] = {}
        unknown = [c for c in s['categories'] if c not in CATEGORY_CATALOG or c == 'FPTS']
        if unknown:
            raise ValueError(f"unknown categories: {', '.join(unknown)}")
        if not s['categories']:
            raise ValueError('pick at least one category')
        s['categories'] = list(dict.fromkeys(s['categories']))
    else:
        raise ValueError("scoring type must be 'categories' or 'points'")
    try:
        s['num_teams'] = int(s['num_teams'])
        for key in ('size', 'active'):
            s['roster'][key] = int(s['roster'][key] or 0)
        s['playoffs'] = {k: int(s['playoffs'].get(k) or 0) for k in ('teams', 'first_week')}
        s['draft']['budget'] = int(s['draft']['budget'] or 0)
        s['waivers']['claims_per_week'] = int(s['waivers']['claims_per_week'] or 0)
        s['waivers']['faab_budget'] = int(s['waivers']['faab_budget'] or 0)
        s['waivers']['faab_per_stage'] = int(s['waivers']['faab_per_stage'] or 0)
        s['elimination']['per_stage'] = int(s['elimination']['per_stage'] or 0)
        stage_weeks = s['elimination']['stage_weeks'] or []
        if isinstance(stage_weeks, str):  # "3,3,3,2" from a text field
            stage_weeks = [w for w in re.split(r'[\s,]+', stage_weeks) if w]
        s['elimination']['stage_weeks'] = [int(w) for w in stage_weeks]
    except (TypeError, ValueError):
        raise ValueError('team count, roster sizes, budget and claims must be whole numbers')
    try:
        s['draft']['price_exponent'] = float(s['draft']['price_exponent'])
    except (TypeError, ValueError):
        raise ValueError('the price exponent must be a number')
    if not 0.2 <= s['draft']['price_exponent'] <= 5:
        raise ValueError('the price exponent must be between 0.2 and 5')
    s['roster']['daily_lineups'] = bool(s['roster']['daily_lineups'])
    if s['num_teams'] < 2:
        raise ValueError('a league needs at least 2 teams')
    if not 1 <= s['roster']['active'] <= s['roster']['size']:
        raise ValueError('active spots must be between 1 and the roster size')
    slots = [str(slot).strip().upper() for slot in s['roster']['slots'] or []]
    unknown = [slot for slot in slots if slot not in SLOT_TYPES]
    if unknown:
        raise ValueError(f"unknown roster slots: {', '.join(unknown)}")
    if slots and len(slots) != s['roster']['active']:
        raise ValueError(f"{len(slots)} starting slots but {s['roster']['active']} active spots: they must match")
    s['roster']['slots'] = [] if all(slot == 'UTIL' for slot in slots) else slots
    if s['playoffs']['teams'] > s['num_teams']:
        raise ValueError('more playoff teams than teams')
    schedule = []
    for entry in s['schedule'] or []:
        start, opponent = (list(entry) + [''])[:2]
        try:
            start = _parse_date(start).isoformat()
        except ValueError:
            raise ValueError(f'schedule date {start!r} is not YYYY-MM-DD')
        schedule.append([start, (opponent or '').strip()])
    schedule.sort(key=lambda e: e[0])
    if len({e[0] for e in schedule}) != len(schedule):
        raise ValueError('schedule has two weeks starting on the same day')
    s['schedule'] = schedule
    stage_weeks = s['elimination']['stage_weeks']
    if any(w < 1 for w in stage_weeks):
        raise ValueError('every elimination stage needs at least one week')
    if stage_weeks and schedule and sum(stage_weeks) > len(schedule):
        raise ValueError(f'the elimination stages cover {sum(stage_weeks)} weeks but the schedule has {len(schedule)}')
    if stage_weeks and s['num_teams'] - s['elimination']['per_stage'] * (len(stage_weeks) - 1) < 1:
        raise ValueError('eliminations run out of teams before the last stage')
    s['my_team'] = (s['my_team'] or '').strip()
    return s


class LeagueConfig:
    """A league's rules, resolved. Everything league-specific the stats code needs hangs off this."""

    def __init__(self, row):
        self.id = row.id
        self.name = row.name
        self.is_active = bool(row.is_active)
        self.settings = validate_settings(json.loads(row.settings or '{}'))

    categories = property(lambda self: list(self.settings['categories']))  # ['FPTS'] in a points league
    is_points = property(lambda self: self.settings['scoring']['type'] == 'points')
    point_weights = property(lambda self: dict(self.settings['scoring']['points']))
    inverse_categories = property(lambda self: [c for c in self.categories if CATEGORY_CATALOG[c].get('inverse')])
    my_team = property(lambda self: self.settings['my_team'])
    num_teams = property(lambda self: self.settings['num_teams'])
    roster_size = property(lambda self: self.settings['roster']['size'])
    active_slots = property(lambda self: self.settings['roster']['active'])
    daily_lineups = property(lambda self: self.settings['roster']['daily_lineups'])
    # The starting slots: all UTIL when the league has no positions.
    slots = property(lambda self: list(self.settings['roster']['slots']) or ['UTIL'] * self.active_slots)
    budget = property(lambda self: self.settings['draft']['budget'] or 200)
    price_exponent = property(lambda self: self.settings['draft']['price_exponent'])
    claims_per_week = property(lambda self: max(self.settings['waivers']['claims_per_week'], 1))
    stage_weeks = property(lambda self: list(self.settings['elimination']['stage_weeks']))
    is_guillotine = property(lambda self: bool(self.settings['elimination']['stage_weeks']))
    platform = property(lambda self: self.settings['platform'])
    platform_league_id = property(lambda self: self.settings['platform_league_id'])

    @property
    def schedule(self):
        return [tuple(e) for e in self.settings['schedule']]

    @property
    def schedule_dict(self):
        return {start: opponent for start, opponent in self.schedule}

    def weeks(self):
        """[{week, start, end, days, opponent, playoffs}]: a week ends the day before the next starts
        (last: 7 days)."""
        schedule = self.schedule
        first_playoff = self.settings['playoffs']['first_week'] or None
        out = []
        for i, (start, opponent) in enumerate(schedule):
            end = (_parse_date(schedule[i + 1][0]) - timedelta(days=1) if i + 1 < len(schedule)
                   else _parse_date(start) + timedelta(days=6))
            out.append({'week': i + 1, 'start': start, 'end': end.isoformat(),
                        'days': (end - _parse_date(start)).days + 1, 'opponent': opponent,
                        'playoffs': bool(first_playoff and i + 1 >= first_playoff)})
        return out

    def stage_of_week(self, week_index):
        """1-based stage a 0-based schedule week belongs to, None past the last stage."""
        end = 0
        for number, weeks in enumerate(self.stage_weeks, 1):
            end += weeks
            if week_index < end:
                return number
        return None

    def stage_info(self, today=None):
        """Where a guillotine league stands on `today`: its stage, that stage's weeks and dates,
        how many teams play it and how many it eliminates, and whether trades are open (first
        week of a stage). Before the first week: stage 1, not started. None for ordinary leagues
        or before a schedule exists."""
        schedule = self.schedule
        if not self.is_guillotine or not schedule:
            return None
        today = (today or date.today()).isoformat()
        started = today >= schedule[0][0]
        index = max((i for i, (start, _) in enumerate(schedule) if start <= today), default=0)
        stage = self.stage_of_week(index)
        if stage is None:
            return {'stage': None, 'stages': len(self.stage_weeks), 'finished': True}
        first = sum(self.stage_weeks[:stage - 1])
        last = first + self.stage_weeks[stage - 1] - 1
        per_stage = self.settings['elimination']['per_stage']
        teams = self.num_teams - per_stage * (stage - 1)
        final = stage == len(self.stage_weeks)
        end = _parse_date(self.weeks()[last]['end'])
        if today > end.isoformat():  # past the last scheduled week
            return {'stage': None, 'stages': len(self.stage_weeks), 'finished': True}
        return {'stage': stage, 'stages': len(self.stage_weeks), 'started': started, 'final': final,
                'week_in_stage': index - first + 1 if started else 0, 'weeks': self.stage_weeks[stage - 1],
                'first_week': first + 1, 'last_week': last + 1,
                'start': schedule[first][0], 'end': end.isoformat(),
                'teams': teams, 'eliminated': 0 if final else per_stage,
                'trade_window': started and index == first}

    def capabilities(self):
        """What the league's rules switch on, by name. Tabs and columns key off these, never off a
        platform or a league id."""
        s = self.settings
        slots = s['roster']['slots']
        detailed = any(slot in ('PG', 'SG', 'SF', 'PF') for slot in slots)
        return {
            'scoring': s['scoring']['type'],               # categories | points
            'punts': len(self.categories) > 1,             # a category can be left out of value
            'positions': (['PG', 'SG', 'SF', 'PF', 'C'] if detailed else ['G', 'F', 'C']) if slots else [],
            'auction': s['draft']['type'] == 'auction',
            'guillotine': self.is_guillotine,
            'faab': s['waivers']['faab_budget'] > 0,
            'claims_per_week': self.claims_per_week,
            'team_wins': 'WIN%' in self.categories,
            'long_weeks': any(w['days'] > 7 for w in self.weeks()),
            'playoffs': s['playoffs']['teams'] > 0,
        }

    def to_dict(self):
        return {'id': self.id, 'name': self.name, 'is_active': self.is_active, 'settings': self.settings,
                'categories': category_meta(self.categories), 'stage': self.stage_info(),
                'weeks': self.weeks(), 'capabilities': self.capabilities()}


def slugify(name):
    slug = re.sub(r'[^a-z0-9]+', '-', name.lower()).strip('-')[:48] or 'league'
    candidate, n = slug, 2
    while League.select().where(League.id == candidate).exists():
        candidate, n = f'{slug}-{n}', n + 1
    return candidate


def list_leagues():
    return [LeagueConfig(row) for row in League.select().order_by(League.created_at)]


def get_league(league_id=None):
    """The named league, else the active one, else the oldest. NotFound when there are none."""
    row = None
    if league_id:
        row = League.get_or_none(League.id == league_id)
        if row is None:
            raise NotFound(f'no league {league_id!r}')
    if row is None:
        row = League.select().order_by(League.is_active.desc(), League.created_at).first()
    if row is None:
        raise NotFound('no league yet: create one in the app (League > New league)')
    return LeagueConfig(row)


def create_league(name, settings, copy_teams_from=None):
    name = (name or '').strip()
    if not name:
        raise ValueError('the league needs a name')
    clean = validate_settings(settings)
    with DB.atomic():
        is_first = not League.select().exists()
        row = League.create(id=slugify(name), name=name, settings=json.dumps(clean), is_active=is_first)
        if copy_teams_from:
            for team in FantasyTeam.select().where(FantasyTeam.league == copy_teams_from):
                FantasyTeam.create(name=team.name, abv=team.abv, league=row)
    return LeagueConfig(row)


def update_league(league_id, name=None, settings=None):
    row = League.get_or_none(League.id == league_id)
    if row is None:
        raise NotFound(f'no league {league_id!r}')
    if name is not None:
        if not name.strip():
            raise ValueError('the league needs a name')
        row.name = name.strip()
    if settings is not None:
        row.settings = json.dumps(validate_settings(settings))
    row.save()
    return LeagueConfig(row)


def activate_league(league_id):
    if not League.select().where(League.id == league_id).exists():
        raise NotFound(f'no league {league_id!r}')
    with DB.atomic():
        League.update(is_active=False).execute()
        League.update(is_active=True).where(League.id == league_id).execute()


def delete_league(league_id):
    """Deletes a league and its teams. Refuses while any team still has players on it."""
    row = League.get_or_none(League.id == league_id)
    if row is None:
        raise NotFound(f'no league {league_id!r}')
    team_ids = [t.id for t in FantasyTeam.select(FantasyTeam.id).where(FantasyTeam.league == row)]
    if team_ids and FantasyTeamPlayer.select().where(FantasyTeamPlayer.fantasy_team_id.in_(team_ids)).exists():
        raise ValueError('this league still has rostered players; undraft them first')
    with DB.atomic():
        LeaguePlayerFlag.delete().where(LeaguePlayerFlag.league == row).execute()
        FantasyTeam.delete().where(FantasyTeam.league == row).execute()
        row.delete_instance()
        if not League.select().where(League.is_active == True).exists():  # noqa: E712 (peewee)
            first = League.select().order_by(League.created_at).first()
            if first:
                League.update(is_active=True).where(League.id == first.id).execute()


def generate_weeks(first_day, last_day):
    """Week starts for a season: opening day, then every Monday through `last_day`. Opponents blank."""
    first_day, last_day = _parse_date(first_day), _parse_date(last_day)
    weeks = [[first_day.isoformat(), '']]
    monday = first_day + timedelta(days=(7 - first_day.weekday()) % 7 or 7)
    while monday <= last_day:
        weeks.append([monday.isoformat(), ''])
        monday += timedelta(days=7)
    return weeks
