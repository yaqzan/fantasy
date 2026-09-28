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
CATEGORY_CATALOG = {
    'PTS': {'label': 'PTS', 'name': 'Points', 'kind': 'count'},
    'REB': {'label': 'REB', 'name': 'Rebounds', 'kind': 'count'},
    'AST': {'label': 'AST', 'name': 'Assists', 'kind': 'count'},
    'STL': {'label': 'STL', 'name': 'Steals', 'kind': 'count'},
    'BLK': {'label': 'BLK', 'name': 'Blocks', 'kind': 'count'},
    'FG3M': {'label': '3PM', 'name': 'Three-pointers made', 'kind': 'count'},
    'AST-TOV': {'label': 'A-TO', 'name': 'Assists minus turnovers', 'kind': 'count'},
    'NFT': {'label': 'NFT', 'name': 'Net free throws (2*FTM - FTA)', 'kind': 'count'},
    'DD2': {'label': 'DD', 'name': 'Double-doubles', 'kind': 'count'},
    'TD3': {'label': 'TD', 'name': 'Triple-doubles', 'kind': 'count'},
    'PLUS_MINUS': {'label': '+/-', 'name': 'Plus/minus', 'kind': 'count'},
    'TOV': {'label': 'TOV', 'name': 'Turnovers', 'kind': 'count', 'inverse': True},
    'PF': {'label': 'PF', 'name': 'Personal fouls', 'kind': 'count', 'inverse': True},
    'BLKA': {'label': 'TB', 'name': 'Times blocked', 'kind': 'count', 'inverse': True},
    'TECH': {'label': 'TF', 'name': 'Technical fouls', 'kind': 'count', 'inverse': True},
    'WIN%': {'label': 'W', 'name': 'Wins', 'kind': 'wins'},
    # Ratios are valued by impact (player_stats.py). `attempts`: the per-game attempts behind the
    # rate, as (stat, coefficient) terms. `prior`: attempts of league-average shooting a player's
    # rate is blended with before scoring (method of moments on 2025-26: TS% ~233, EFG% ~223,
    # FT% ~27, PPS ~98).
    'TS%': {'label': 'TS%', 'name': 'True shooting %', 'kind': 'ratio', 'percent': True,
            'attempts': [('FGA', 1.0), ('FTA', 0.44)], 'prior': 250},
    'EFG%': {'label': 'EFG%', 'name': 'Effective FG %', 'kind': 'ratio', 'percent': True,
             'attempts': [('FGA', 1.0)], 'prior': 250},
    'FT%': {'label': 'FT%', 'name': 'Free throw %', 'kind': 'ratio', 'percent': True,
            'attempts': [('FTA', 1.0)], 'prior': 50},
    'PPS': {'label': 'PPS', 'name': 'Points per shot', 'kind': 'ratio', 'attempts': [('FGA', 1.0)], 'prior': 100},
}
# Column order in tables: shooting first, then counting stats, inverse categories last.
CATEGORY_ORDER = ['TS%', 'EFG%', 'FT%', 'PPS', 'PTS', 'REB', 'AST', 'AST-TOV', 'STL', 'BLK', 'FG3M', 'NFT',
                  'DD2', 'TD3', 'WIN%', 'PLUS_MINUS', 'TOV', 'PF', 'BLKA', 'TECH']

DEFAULT_SETTINGS = {
    'season': '',                     # e.g. "2026-27", display only
    'platform': 'fantrax',
    'fantrax_league_id': '',          # falls back to FANTRAX_LEAGUE_ID in .env
    'my_team': '',                    # your team's abbreviation in this league's fantasy_teams
    'num_teams': 12,
    'categories': ['PTS', 'REB', 'AST', 'STL', 'BLK', 'FG3M', 'TOV', 'TS%', 'FT%'],
    'roster': {
        'size': 13,                   # total roster spots
        'active': 10,                 # starters that score
        'daily_lineups': True,        # True: lineups set daily (best `active` of each day count);
                                      # False: one lineup of `active` players for the whole week
        'min_guards': 0, 'min_forwards': 0, 'min_centers': 0,
    },
    'draft': {'type': 'auction', 'budget': 200, 'date': '',
              'price_exponent': 1.0},     # auction $ follow value over replacement ** this;
                                          # fit to the league's past drafts (1 = linear)
    'waivers': {'claims_per_week': 1},
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


def validate_settings(settings):
    """Merge onto the defaults and check every value; raises ValueError with a readable message."""
    s = _merge(DEFAULT_SETTINGS, settings)
    unknown = [c for c in s['categories'] if c not in CATEGORY_CATALOG]
    if unknown:
        raise ValueError(f"unknown categories: {', '.join(unknown)}")
    if not s['categories']:
        raise ValueError('pick at least one category')
    s['categories'] = list(dict.fromkeys(s['categories']))
    try:
        s['num_teams'] = int(s['num_teams'])
        for key in ('size', 'active', 'min_guards', 'min_forwards', 'min_centers'):
            s['roster'][key] = int(s['roster'][key] or 0)
        s['draft']['budget'] = int(s['draft']['budget'] or 0)
        s['waivers']['claims_per_week'] = int(s['waivers']['claims_per_week'] or 0)
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
    if s['roster']['min_guards'] + s['roster']['min_forwards'] + s['roster']['min_centers'] > s['roster']['active']:
        raise ValueError('position minimums add up to more than the active spots')
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
    s['my_team'] = (s['my_team'] or '').strip()
    return s


class LeagueConfig:
    """A league's rules, resolved. Everything league-specific the stats code needs hangs off this."""

    def __init__(self, row):
        self.id = row.id
        self.name = row.name
        self.is_active = bool(row.is_active)
        self.settings = validate_settings(json.loads(row.settings or '{}'))

    categories = property(lambda self: list(self.settings['categories']))
    inverse_categories = property(lambda self: [c for c in self.categories if CATEGORY_CATALOG[c].get('inverse')])
    my_team = property(lambda self: self.settings['my_team'])
    num_teams = property(lambda self: self.settings['num_teams'])
    roster_size = property(lambda self: self.settings['roster']['size'])
    active_slots = property(lambda self: self.settings['roster']['active'])
    daily_lineups = property(lambda self: self.settings['roster']['daily_lineups'])
    min_guards = property(lambda self: self.settings['roster']['min_guards'])
    min_forwards = property(lambda self: self.settings['roster']['min_forwards'])
    min_centers = property(lambda self: self.settings['roster']['min_centers'])
    budget = property(lambda self: self.settings['draft']['budget'] or 200)
    price_exponent = property(lambda self: self.settings['draft']['price_exponent'])
    claims_per_week = property(lambda self: max(self.settings['waivers']['claims_per_week'], 1))
    fantrax_league_id = property(lambda self: self.settings['fantrax_league_id'])

    @property
    def lineup_size(self):
        """How many players the optimizer picks: the whole roster when lineups are set daily (the
        daily best-`active` rule decides who scores), else the weekly starters."""
        return self.roster_size if self.daily_lineups else self.active_slots

    @property
    def schedule(self):
        return [tuple(e) for e in self.settings['schedule']]

    @property
    def schedule_dict(self):
        return {start: opponent for start, opponent in self.schedule}

    def to_dict(self):
        return {'id': self.id, 'name': self.name, 'is_active': self.is_active, 'settings': self.settings,
                'categories': category_meta(self.categories)}


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
