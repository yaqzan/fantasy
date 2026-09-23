"""
Create the daily_player_stats table in the database
"""
from fantasy_database import DB, DailyPlayerStats

def create_daily_stats_table():
    """Create the daily_player_stats table"""
    try:
        DB.connect()
        DB.create_tables([DailyPlayerStats])
        print("Daily stats table created successfully!")
    except Exception as e:
        print(f"Error creating table: {e}")
    finally:
        DB.close()

if __name__ == '__main__':
    create_daily_stats_table()




