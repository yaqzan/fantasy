"""Create the MySQL database and every table. Safe to re-run (existing tables are left alone).

    python init_db.py
"""
from peewee import MySQLDatabase

from fantasy_config import DB_NAME, DB_CONFIGS


def main():
    server = MySQLDatabase('information_schema', **DB_CONFIGS)  # any existing schema, just to reach the server
    server.connect()
    server.execute_sql(f"CREATE DATABASE IF NOT EXISTS `{DB_NAME}` CHARACTER SET utf8mb4")
    server.close()

    from fantasy_database import DB, Team, Player, Game, FantasyTeam, FantasyTeamPlayer, DailyPlayerStats
    DB.connect(reuse_if_open=True)
    DB.create_tables([Team, Player, Game, FantasyTeam, FantasyTeamPlayer, DailyPlayerStats], safe=True)
    print(f"database `{DB_NAME}` ready: {', '.join(sorted(DB.get_tables()))}")


if __name__ == "__main__":
    main()
