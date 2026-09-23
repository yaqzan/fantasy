import React, { useState, useEffect, useCallback } from 'react';
import { getDailyStats, updateDailyStats } from '../services/api';

const DailyStats = () => {
  const [dailyStats, setDailyStats] = useState([]);
  const [loading, setLoading] = useState(false);
  const [selectedDate, setSelectedDate] = useState(() => {
    const now = new Date();
    const currentHour = now.getHours();
    
    console.log('Current time:', now);
    console.log('Current hour:', currentHour);
    console.log('Current date string:', now.toISOString().split('T')[0]);
    
    // If before 7pm, show yesterday; otherwise show today
    if (currentHour < 19) {
      const yesterday = new Date(now);
      yesterday.setDate(yesterday.getDate() - 1);
      console.log('Showing yesterday:', yesterday.toISOString().split('T')[0]);
      return yesterday.toISOString().split('T')[0];
    } else {
      console.log('Showing today:', now.toISOString().split('T')[0]);
      return now.toISOString().split('T')[0];
    }
  });
  const [updating, setUpdating] = useState(false);

  const loadDailyStats = useCallback(async () => {
    try {
      setLoading(true);
      console.log('Loading daily stats for date:', selectedDate);
      const data = await getDailyStats(selectedDate);
      console.log('Received data:', data);
      setDailyStats(data.stats || []);
    } catch (error) {
      console.error('Error loading daily stats:', error);
    } finally {
      setLoading(false);
    }
  }, [selectedDate]);

  useEffect(() => {
    loadDailyStats();
  }, [loadDailyStats]);

  const handleUpdateStats = async () => {
    try {
      setUpdating(true);
      await updateDailyStats(selectedDate);
      await loadDailyStats();
    } catch (error) {
      console.error('Error updating daily stats:', error);
    } finally {
      setUpdating(false);
    }
  };

  const formatPercentage = (value) => {
    if (value === null || value === undefined) return '-';
    return `${(value * 100).toFixed(1)}%`;
  };

  const formatMinutes = (minutes) => {
    if (minutes === null || minutes === undefined) return '-';
    const hours = Math.floor(minutes / 60);
    const mins = minutes % 60;
    return hours > 0 ? `${hours}:${mins.toString().padStart(2, '0')}` : `${mins}m`;
  };

  return (
    <div className="p-6">
      <div className="mb-6">
        <h2 className="text-2xl font-bold text-white mb-4">Daily Player Stats</h2>
        
        <div className="flex flex-col sm:flex-row gap-4 items-start sm:items-center">
          <div className="flex items-center gap-3">
            <label className="text-sm font-medium text-gray-300">
              Select Date:
            </label>
            <div className="flex items-center gap-2 bg-gray-700 border border-gray-600 rounded-md">
              <button
                onClick={() => {
                  const currentDate = new Date(selectedDate);
                  currentDate.setDate(currentDate.getDate() - 1);
                  setSelectedDate(currentDate.toISOString().split('T')[0]);
                }}
                className="px-3 py-2 text-gray-300 hover:text-white hover:bg-gray-600 rounded-l-md transition-colors"
                title="Previous day"
              >
                ←
              </button>
              <div className="px-4 py-2 text-white font-medium min-w-[120px] text-center">
                {new Date(selectedDate + 'T00:00:00').toLocaleDateString('en-US', { 
                  weekday: 'short', 
                  month: 'short', 
                  day: 'numeric',
                  year: 'numeric'
                })}
              </div>
              <button
                onClick={() => {
                  const currentDate = new Date(selectedDate);
                  currentDate.setDate(currentDate.getDate() + 1);
                  setSelectedDate(currentDate.toISOString().split('T')[0]);
                }}
                className="px-3 py-2 text-gray-300 hover:text-white hover:bg-gray-600 rounded-r-md transition-colors"
                title="Next day"
              >
                →
              </button>
            </div>
          </div>
          
          <button
            onClick={handleUpdateStats}
            disabled={updating}
            className="btn-primary disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {updating ? 'Updating...' : 'Update Stats'}
          </button>
        </div>
      </div>

      {loading ? (
        <div className="flex justify-center items-center py-8">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-nba-orange"></div>
        </div>
      ) : dailyStats.length === 0 ? (
        <div className="text-center py-8 text-gray-400">
          No stats available for {selectedDate}
        </div>
      ) : (
        <div className="overflow-x-auto bg-gray-800 rounded-lg shadow-xl">
          <table className="min-w-full">
            <thead>
              <tr>
                <th className="table-header w-16 text-center">Rank</th>
                <th className="table-header w-48 text-left">Player</th>
                <th className="table-header w-32 text-center">Team</th>
                <th className="table-header w-40 text-center">Matchup</th>
                <th className="table-header w-16 text-center">Min</th>
                <th className="table-header w-16 text-center">PTS</th>
                <th className="table-header w-16 text-center">REB</th>
                <th className="table-header w-16 text-center">AST</th>
                <th className="table-header w-16 text-center">STL</th>
                <th className="table-header w-16 text-center">BLK</th>
                <th className="table-header w-16 text-center">TOV</th>
                <th className="table-header w-16 text-center">FG%</th>
                <th className="table-header w-16 text-center">3P%</th>
                <th className="table-header w-16 text-center">FT%</th>
                <th className="table-header w-16 text-center">+/-</th>
                <th className="table-header w-20 text-center">FP</th>
              </tr>
            </thead>
            <tbody className="bg-gray-800 divide-y divide-gray-700">
              {dailyStats.map((stat, index) => (
                <tr key={stat.id} className="hover:bg-gray-700 transition-colors">
                  <td className="table-cell text-center">
                    <div className="flex items-center justify-center">
                      <span className="ovr-badge">
                        {index + 1}
                      </span>
                    </div>
                  </td>
                  <td className="table-cell">
                    <div>
                      <div className="font-medium text-white">{stat.player_name}</div>
                    </div>
                  </td>
                  <td className="table-cell text-center text-gray-300">
                    {stat.team || '-'}
                  </td>
                  <td className="table-cell text-center text-gray-300">
                    {stat.matchup || '-'}
                  </td>
                  <td className="table-cell text-center text-gray-300">
                    {formatMinutes(stat.minutes)}
                  </td>
                  <td className="table-cell text-center font-medium text-white">
                    {stat.pts || 0}
                  </td>
                  <td className="table-cell text-center text-gray-300">
                    {stat.reb || 0}
                  </td>
                  <td className="table-cell text-center text-gray-300">
                    {stat.ast || 0}
                  </td>
                  <td className="table-cell text-center text-gray-300">
                    {stat.stl || 0}
                  </td>
                  <td className="table-cell text-center text-gray-300">
                    {stat.blk || 0}
                  </td>
                  <td className="table-cell text-center text-gray-300">
                    {stat.tov || 0}
                  </td>
                  <td className="table-cell text-center text-gray-300">
                    {formatPercentage(stat.fg_pct)}
                  </td>
                  <td className="table-cell text-center text-gray-300">
                    {formatPercentage(stat.fg3_pct)}
                  </td>
                  <td className="table-cell text-center text-gray-300">
                    {formatPercentage(stat.ft_pct)}
                  </td>
                  <td className="table-cell text-center text-gray-300">
                    {stat.plus_minus || 0}
                  </td>
                  <td className="table-cell text-center">
                    <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-bold bg-nba-orange text-white">
                      {stat.fantasy_points || 0}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
};

export default DailyStats;
