"""Create the MySQL database and every table, and upgrade an older one. Safe to re-run.

    python init_db.py

Upgrades are additive (new tables, new columns, the per-league team index); nothing is dropped
or overwritten. An install from before leagues existed (teams with no league, a league.json with
`my_team` + `schedule`) is imported once as its own league, keeping the old hard-coded rules.
"""
import json
import os

from peewee import MySQLDatabase, IntegerField, CharField, TextField

from fantasy_config import DB_NAME, DB_CONFIGS

ROOT = os.path.dirname(os.path.abspath(__file__))

# The rules fantasy_config.py hard-coded before leagues existed (2025-26 season).
LEGACY_SETTINGS = {
    'season': '2025-26',
    'num_teams': 14,
    'categories': ['PTS', 'FG3M', 'AST', 'TOV', 'REB', 'STL', 'BLK', 'PF', 'TS%', 'NFT', 'PLUS_MINUS'],
    'roster': {'size': 14, 'active': 11, 'daily_lineups': False, 'min_guards': 2, 'min_forwards': 2, 'min_centers': 1},
    'draft': {'type': 'auction', 'budget': 200, 'date': ''},
    'waivers': {'claims_per_week': 1},
}


def upgrade_schema(DB):
    from playhouse.migrate import MySQLMigrator, migrate
    migrator = MySQLMigrator(DB)
    ops = []
    player_cols = {c.name for c in DB.get_columns('players')}
    for col in ('tech', 'tech_5', 'tech_10', 'w', 'w_5', 'w_10'):
        if col not in player_cols:
            ops.append(migrator.add_column('players', col, IntegerField(null=True)))
    if 'player_seasons' in DB.get_tables() and 'tech' not in {c.name for c in DB.get_columns('player_seasons')}:
        ops.append(migrator.add_column('player_seasons', 'tech', IntegerField(null=True)))
    if 'record_season' not in {c.name for c in DB.get_columns('teams')}:
        ops.append(migrator.add_column('teams', 'record_season', CharField(max_length=7, null=True)))
    team_cols = {c.name for c in DB.get_columns('fantasy_teams')}
    if 'league_id' not in team_cols:
        ops.append(migrator.add_column('fantasy_teams', 'league_id', CharField(max_length=64, null=True)))
    if 'eliminated_stage' not in team_cols:
        ops.append(migrator.add_column('fantasy_teams', 'eliminated_stage', IntegerField(null=True)))
    if 'released_roster' not in team_cols:
        ops.append(migrator.add_column('fantasy_teams', 'released_roster', TextField(null=True)))
    if ops:
        migrate(*ops)
        print(f'added {len(ops)} column(s)')
    indexes = DB.get_indexes('fantasy_teams')
    for index in indexes:  # team names were unique across the whole app; now per league
        if index.unique and index.columns == ['name']:
            migrate(migrator.drop_index('fantasy_teams', index.name))
            print(f'dropped global unique index {index.name}')
    if not any(i.unique and i.columns == ['league_id', 'name'] for i in indexes):
        migrate(migrator.add_index('fantasy_teams', ('league_id', 'name'), True))
        print('added unique index on (league_id, name)')


def import_legacy_league():
    """One league for teams that predate leagues. Returns the new league id, or None."""
    from fantasy_database import FantasyTeam, League, LeaguePlayerFlag, Player
    from leagues import create_league
    orphans = FantasyTeam.select().where(FantasyTeam.league.is_null())
    if not orphans.exists():
        return None
    settings = dict(LEGACY_SETTINGS)
    path = os.path.join(ROOT, 'league.json')
    if os.path.exists(path):
        with open(path, encoding='utf-8') as f:
            old = json.load(f)
        settings['my_team'] = old.get('my_team', '')
        settings['schedule'] = old.get('schedule', [])
    league = create_league(f"League {settings['season']}", settings)
    moved = FantasyTeam.update(league=league.id).where(FantasyTeam.league.is_null()).execute()
    flags = 0
    for player in Player.select().where(Player.undroppable == 1):
        LeaguePlayerFlag.replace(league=league.id, player=player.id, undroppable=True).execute()
        flags += 1
    print(f"imported the pre-league setup as league '{league.id}': {moved} teams, {flags} undroppable flags"
          + (', schedule from league.json (no longer read; safe to delete)' if os.path.exists(path) else ''))
    if not League.select().where(League.is_active == True).exists():  # noqa: E712
        League.update(is_active=True).where(League.id == league.id).execute()
    return league.id


def main():
    server = MySQLDatabase('information_schema', **DB_CONFIGS)  # any existing schema, just to reach the server
    server.connect()
    server.execute_sql(f"CREATE DATABASE IF NOT EXISTS `{DB_NAME}` CHARACTER SET utf8mb4")
    server.close()

    from fantasy_database import DB, ALL_MODELS
    DB.connect(reuse_if_open=True)
    DB.create_tables(ALL_MODELS, safe=True)
    upgrade_schema(DB)
    import_legacy_league()
    print(f"database `{DB_NAME}` ready: {', '.join(sorted(DB.get_tables()))}")


if __name__ == "__main__":
    main()
