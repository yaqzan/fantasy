"""
Test the daily stats functionality
"""
from datetime import date, datetime
from fantasy_database import DB, DailyPlayerStats, Player
from update_daily_stats import update_daily_stats_for_date, get_daily_stats_for_date

def test_daily_stats():
    """Test the daily stats functionality"""
    try:
        DB.connect()
        
        # Test with a recent date (you may need to adjust this)
        test_date = date(2024, 10, 22)  # Adjust to a date with NBA games
        
        print(f"Testing daily stats for {test_date}")
        
        # Update daily stats
        print("Updating daily stats...")
        update_daily_stats_for_date(test_date)
        
        # Get daily stats
        print("Retrieving daily stats...")
        stats = get_daily_stats_for_date(test_date)
        
        print(f"Found {len(stats)} player stats for {test_date}")
        
        # Display top 5 performers
        print("\nTop 5 performers by fantasy points:")
        for i, stat in enumerate(stats[:5]):
            print(f"{i+1}. {stat.player_name} ({stat.team}): {stat.pts} pts, {stat.reb} reb, {stat.ast} ast, {stat.fantasy_points} FP")
        
    except Exception as e:
        print(f"Error testing daily stats: {e}")
        import traceback
        traceback.print_exc()
    finally:
        DB.close()

if __name__ == '__main__':
    test_daily_stats()




