from datetime import datetime

from peewee import CharField, FloatField, DateTimeField, IntegerField, DateField, ForeignKeyField, CompositeKey, BooleanField, TextField
from peewee import MySQLDatabase, Model
from fileHelper import date_to_string
from fantasy_config import DB_NAME, DB_CONFIGS

DB = MySQLDatabase(DB_NAME, **DB_CONFIGS)

class BaseModel(Model):
    class Meta:
        database = DB

class Team(BaseModel):
    name = CharField(primary_key=True)
    win_percentage = FloatField(null=True)
    wins = IntegerField(null=True)
    losses = IntegerField(null=True)
    abv = CharField(null=True)
    record_season = CharField(max_length=7, null=True)  # season wins/losses are from, e.g. '2026-27'
    
    class Meta:
        table_name = 'teams'

class Player(BaseModel):
    id = IntegerField(primary_key=True)
    name = CharField()
    team = CharField(null=True)
    fga = IntegerField(null=True)
    fgm = IntegerField(null=True)
    fta = IntegerField(null=True)
    ftm = IntegerField(null=True)
    fg3m = IntegerField(null=True)
    pts = IntegerField(null=True)
    ast = IntegerField(null=True)
    reb = IntegerField(null=True)
    stl = IntegerField(null=True)
    blk = IntegerField(null=True)
    blka = IntegerField(null=True)
    tov = IntegerField(null=True)
    plus_minus = FloatField(null=True)
    dd2 = IntegerField(null=True)
    td3 = IntegerField(null=True)
    fga_5 = IntegerField(null=True)
    fgm_5 = IntegerField(null=True)
    fta_5 = IntegerField(null=True)
    ftm_5 = IntegerField(null=True)
    fg3m_5 = IntegerField(null=True)
    pts_5 = IntegerField(null=True)
    ast_5 = IntegerField(null=True)
    reb_5 = IntegerField(null=True)
    stl_5 = IntegerField(null=True)
    blk_5 = IntegerField(null=True)
    blka_5 = IntegerField(null=True)
    tov_5 = IntegerField(null=True)
    plus_minus_5 = FloatField(null=True)
    dd2_5 = IntegerField(null=True)
    td3_5 = IntegerField(null=True)
    fga_10 = IntegerField(null=True)
    fgm_10 = IntegerField(null=True)
    fta_10 = IntegerField(null=True)
    ftm_10 = IntegerField(null=True)
    fg3m_10 = IntegerField(null=True)
    pts_10 = IntegerField(null=True)
    ast_10 = IntegerField(null=True)
    reb_10 = IntegerField(null=True)
    stl_10 = IntegerField(null=True)
    blk_10 = IntegerField(null=True)
    blka_10 = IntegerField(null=True)
    tov_10 = IntegerField(null=True)
    plus_minus_10 = FloatField(null=True)
    dd2_10 = IntegerField(null=True)
    td3_10 = IntegerField(null=True)
    pos = CharField(null=True)
    gp = IntegerField(null=True)
    pf = IntegerField(null=True)
    pf_5 = IntegerField(null=True)
    pf_10 = IntegerField(null=True)
    tech = IntegerField(null=True)  # technical fouls, from play-by-play (technical_fouls table)
    tech_5 = IntegerField(null=True)
    tech_10 = IntegerField(null=True)
    w = IntegerField(null=True)  # team wins in games the player played
    w_5 = IntegerField(null=True)
    w_10 = IntegerField(null=True)
    injured = IntegerField(null=True)  # BOOL field (0/1)
    injured_games_to_miss = IntegerField(null=True)
    undroppable = IntegerField(null=True)  # legacy, pre-leagues; now per league in league_player_flags
    api_updated_at = DateTimeField(null=True)

    class Meta:
        table_name = 'players'

class Game(BaseModel):
    id = IntegerField(primary_key=True)
    team_home = CharField()
    team_away = CharField()
    date = DateField(null=True)

    @classmethod
    def build(cls, team_home, team_away, date):
        game, created = cls.get_or_create(
            team_home=team_home,
            team_away=team_away,
            date=date
        )
        if created:
            print(f"Created NBA Game: ({game.id}) {game.team_home} vs {game.team_away} - {date_to_string(game.date)}")
        return game

    class Meta:
        table_name = 'games'

class League(BaseModel):
    """A fantasy league: its rules live in `settings` (JSON, see leagues.py), its teams in fantasy_teams."""
    id = CharField(primary_key=True, max_length=64)
    name = CharField()
    settings = TextField()
    is_active = BooleanField(default=False)  # the league CLI scripts and header-less requests use
    created_at = DateTimeField(default=datetime.now)

    class Meta:
        table_name = 'leagues'

class FantasyTeam(BaseModel):
    id = IntegerField(primary_key=True)
    name = CharField()
    abv = CharField(max_length=10, null=True)
    league = ForeignKeyField(League, backref='teams', column_name='league_id', null=True)
    # Guillotine leagues: the stage the team was knocked out after (None = still in), and the
    # players it held then (JSON names), kept so an elimination can be undone.
    eliminated_stage = IntegerField(null=True)
    released_roster = TextField(null=True)

    class Meta:
        table_name = 'fantasy_teams'
        indexes = ((('league', 'name'), True),)

class FantasyTeamPlayer(BaseModel):
    player_id = ForeignKeyField(Player, backref='fantasy_teams')
    fantasy_team_id = ForeignKeyField(FantasyTeam, backref='players')
    player_name = CharField(null=True)
    fantasy_team_name = CharField(null=True)

    class Meta:
        table_name = 'fantasy_team_players'
        primary_key = CompositeKey('player_id', 'fantasy_team_id')

class LeaguePlayerFlag(BaseModel):
    """Per-league player flags (injury is NBA-wide and stays on Player)."""
    league = ForeignKeyField(League, column_name='league_id')
    player = ForeignKeyField(Player, column_name='player_id')
    undroppable = BooleanField(default=False)

    class Meta:
        table_name = 'league_player_flags'
        primary_key = CompositeKey('league', 'player')

class TechnicalFoul(BaseModel):
    """Technical fouls per player per game, scanned from play-by-play (pull_technical_fouls.py)."""
    game_id = CharField(max_length=16)
    player_id = IntegerField()
    game_date = DateField()
    count = IntegerField()

    class Meta:
        table_name = 'technical_fouls'
        primary_key = CompositeKey('game_id', 'player_id')

class ScannedGame(BaseModel):
    """Games whose play-by-play has been scanned for technicals, so they are never fetched twice."""
    game_id = CharField(primary_key=True, max_length=16)
    game_date = DateField()
    scanned_at = DateTimeField(default=datetime.now)

    class Meta:
        table_name = 'pbp_scanned_games'

class DailyPlayerStats(BaseModel):
    player_id = ForeignKeyField(Player, backref='daily_stats')
    player_name = CharField()
    team = CharField(null=True)
    game_date = DateField()
    game_id = CharField(null=True)
    matchup = CharField(null=True)
    minutes = IntegerField(null=True)
    fgm = IntegerField(null=True)
    fga = IntegerField(null=True)
    fg_pct = FloatField(null=True)
    fg3m = IntegerField(null=True)
    fg3a = IntegerField(null=True)
    fg3_pct = FloatField(null=True)
    ftm = IntegerField(null=True)
    fta = IntegerField(null=True)
    ft_pct = FloatField(null=True)
    oreb = IntegerField(null=True)
    dreb = IntegerField(null=True)
    reb = IntegerField(null=True)
    ast = IntegerField(null=True)
    stl = IntegerField(null=True)
    blk = IntegerField(null=True)
    tov = IntegerField(null=True)
    pf = IntegerField(null=True)
    pts = IntegerField(null=True)
    plus_minus = IntegerField(null=True)
    fantasy_points = FloatField(null=True)
    created_at = DateTimeField()

    class Meta:
        table_name = 'daily_player_stats'
        primary_key = CompositeKey('player_id', 'game_date', 'game_id')


class PlayerSeason(BaseModel):
    """A player's regular-season totals for one past season (nba_api leaguedashplayerstats), the
    history projections are built from (pull_history.py)."""
    season = CharField(max_length=7)          # '2025-26'
    player_id = IntegerField()
    name = CharField()
    team = CharField(max_length=8, null=True)  # abbreviation of his last team that season
    age = FloatField(null=True)
    gp = IntegerField()
    min = FloatField()
    pts = IntegerField()
    reb = IntegerField()
    ast = IntegerField()
    stl = IntegerField()
    blk = IntegerField()
    fg3m = IntegerField()
    tov = IntegerField()
    fgm = IntegerField()
    fga = IntegerField()
    ftm = IntegerField()
    fta = IntegerField()
    blka = IntegerField()
    pf = IntegerField()
    dd2 = IntegerField()
    td3 = IntegerField()
    w = IntegerField()

    class Meta:
        table_name = 'player_seasons'
        primary_key = CompositeKey('season', 'player_id')


class PlayerProjection(BaseModel):
    """One source's projection of a player's season (per-game line and games). NBA-wide."""
    season = CharField(max_length=7)          # the projected season, '2026-27'
    source = CharField(max_length=32)         # 'espn', 'model', a research source...
    player_id = IntegerField()
    name = CharField()
    gp = FloatField(null=True)
    min = FloatField(null=True)               # per game, like every stat below
    pts = FloatField(null=True)
    reb = FloatField(null=True)
    ast = FloatField(null=True)
    stl = FloatField(null=True)
    blk = FloatField(null=True)
    fg3m = FloatField(null=True)
    tov = FloatField(null=True)
    fgm = FloatField(null=True)
    fga = FloatField(null=True)
    ftm = FloatField(null=True)
    fta = FloatField(null=True)
    blka = FloatField(null=True)
    pf = FloatField(null=True)
    tech = FloatField(null=True)
    dd2 = FloatField(null=True)
    td3 = FloatField(null=True)
    # Filled by the 'model' source, used to weigh sources by player type (projections.py):
    age = FloatField(null=True)               # age during the projected season
    exp = IntegerField(null=True)             # NBA seasons before it
    prev_team = CharField(max_length=8, null=True)  # abbreviation of last season's team
    updated_at = DateTimeField(default=datetime.now)

    class Meta:
        table_name = 'player_projections'
        primary_key = CompositeKey('season', 'source', 'player_id')


class ProjectionAdjustment(BaseModel):
    """The owner's own read on a player's projection: production and games scaled, applied after
    the sources are combined."""
    season = CharField(max_length=7)
    player_id = IntegerField()
    production = FloatField(default=1.0)      # scales every counting stat and minutes
    games = FloatField(null=True)             # replaces projected games when set
    note = CharField(null=True)
    updated_at = DateTimeField(default=datetime.now)

    class Meta:
        table_name = 'projection_adjustments'
        primary_key = CompositeKey('season', 'player_id')


class TeamProjection(BaseModel):
    """One source's projected regular-season wins for a team. source 'owner' holds the owner's
    adjustment in wins (added to the index), not a projection."""
    season = CharField(max_length=7)
    source = CharField(max_length=32)
    team = CharField()                        # full name, as in `teams`
    wins = FloatField()
    url = CharField(max_length=512, null=True)
    updated_at = DateTimeField(default=datetime.now)

    class Meta:
        table_name = 'team_projections'
        primary_key = CompositeKey('season', 'source', 'team')


ALL_MODELS = [Team, Player, Game, League, FantasyTeam, FantasyTeamPlayer, LeaguePlayerFlag, TechnicalFoul,
              ScannedGame, DailyPlayerStats, PlayerSeason, PlayerProjection, ProjectionAdjustment, TeamProjection]
