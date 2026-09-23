import React, { useState, useEffect } from 'react';
import { analyze } from '../services/api';

// Category display order for matchup comparison
const CATEGORY_ORDER = ['TS%', 'PTS', 'REB', 'AST', 'BLK', 'STL', 'FG3M', 'TOV', 'NFT', 'PF', 'PLUS_MINUS'];

// Inverse categories (lower is better)
const INVERSE_CATEGORIES = ['BLKA', 'TOV', 'PF'];

const LineupOptimizer = () => {
  const [analysisData, setAnalysisData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [contentLoading, setContentLoading] = useState(false);
  const [error, setError] = useState(null);
  const [activeWeek, setActiveWeek] = useState(0);
  const [hasSetDefaultWeek, setHasSetDefaultWeek] = useState(false);
  const [pickupAnalyses, setPickupAnalyses] = useState({
    '5_5': null,
    '5_10': null,
    '5_projected': null,
    '10_5': null,
    '10_10': null,
    '10_projected': null,
    'projected_5': null,
    'projected_10': null,
    'projected_projected': null
  });
  const [currentAnalyses, setCurrentAnalyses] = useState({
    'season': null,
    '5': null,
    '10': null,
    'projected': null
  });
  const [customPickup, setCustomPickup] = useState(null);
  const [customDrop, setCustomDrop] = useState(null);
  const [customAnalysis, setCustomAnalysis] = useState(null);
  const [loadingCustom, setLoadingCustom] = useState(false);
  const [pickupSearchTerm, setPickupSearchTerm] = useState('');
  const [showPickupDropdown, setShowPickupDropdown] = useState(false);

  const fetchAnalysis = async (weekStart = null, isInitialLoad = false) => {
    if (isInitialLoad) {
    setLoading(true);
    } else {
      setContentLoading(true);
    }
    setError(null);
    
    // Clear stale data to prevent race conditions
    setCurrentAnalyses({ 'season': null, '5': null, '10': null, 'projected': null });
    setPickupAnalyses({
      '5_5': null, '5_10': null, '5_projected': null,
      '10_5': null, '10_10': null, '10_projected': null,
      'projected_5': null, 'projected_10': null, 'projected_projected': null
    });
    
    try {
      const data = await analyze(weekStart, 'projected', false);
      setAnalysisData(data);
      
      // After main analysis loads, start loading current analyses and pickups sequentially
      if (!isInitialLoad) {
        fetchCurrentAnalyses(weekStart);
        fetchPickupAnalyses(weekStart);
      }
    } catch (err) {
      setError(err.message);
    } finally {
      if (isInitialLoad) {
      setLoading(false);
      } else {
        setContentLoading(false);
      }
    }
  };

  const fetchCurrentAnalyses = async (weekStart = null) => {
    const timeframes = ['season', '5', '10', 'projected'];
    
    for (const timeframe of timeframes) {
      try {
        // For season average, pass empty string or 'season' - backend should handle it
        const timeframeParam = timeframe === 'season' ? '' : timeframe;
        const data = await analyze(weekStart, timeframeParam, false);
        setCurrentAnalyses(prev => ({
          ...prev,
          [timeframe]: data
        }));
      } catch (err) {
        console.error(`Error loading current analysis for ${timeframe} stats:`, err);
      }
    }
  };

  const fetchPickupAnalyses = async (weekStart = null) => {
    const pickupTimeframes = ['5', '10', 'projected'];
    const statTimeframes = ['5', '10', 'projected'];
    
    // Fetch all 9 combinations (3 pickup timeframes × 3 stat timeframes)
    for (const pickupTimeframe of pickupTimeframes) {
      for (const statTimeframe of statTimeframes) {
        try {
          const data = await analyze(weekStart, statTimeframe, true, pickupTimeframe);
          setPickupAnalyses(prev => ({
            ...prev,
            [`${pickupTimeframe}_${statTimeframe}`]: data
          }));
        } catch (err) {
          console.error(`Error loading pickup analysis for ${pickupTimeframe} pickup, ${statTimeframe} stats:`, err);
        }
      }
    }
  };

  const calculateCustomLineup = async () => {
    if (!customPickup) return;
    
    setLoadingCustom(true);
    try {
      // Manually calculate the custom lineup stats
      const baseLineup = analysisData?.best_lineup || [];
      let customLineup = [...baseLineup];
      
      // Apply the custom changes
      if (customDrop && baseLineup.includes(customDrop)) {
        customLineup = customLineup.filter(p => p !== customDrop);
      }
      if (customPickup && !customLineup.includes(customPickup)) {
        customLineup.push(customPickup);
      }
      
      // Ensure lineup doesn't exceed NUM_STARTERS
      const numStarters = analysisData?.num_starters || 11;
      // If pickup was added without a drop, remove the last player from base lineup
      if (customPickup && !customDrop && customLineup.length > numStarters) {
        // Remove the last player that wasn't the pickup
        const pickupIndex = customLineup.indexOf(customPickup);
        if (pickupIndex !== -1) {
          customLineup = customLineup.filter((p, idx) => idx === pickupIndex || idx < numStarters);
        } else {
          customLineup = customLineup.slice(0, numStarters);
        }
      }
      
      // Remove any duplicate players (shouldn't happen, but safety check)
      customLineup = [...new Set(customLineup)];
      
      // Calculate stats for the custom lineup
      const playerStats = analysisData?.player_stats;
      const gamesPlayed = analysisData?.games_played;
      const teamWins = analysisData?.team_wins;
      
      if (!playerStats || !gamesPlayed || !teamWins) {
        console.error('Missing required data for custom calculation');
        return;
      }
      
      // Calculate stats for all timeframes: season, 5, 10, projected
      const timeframes = [
        { suffix: '', label: 'Current', analysisKey: 'season' },
        { suffix: '_5', label: 'Last 5', analysisKey: '5' },
        { suffix: '_10', label: 'Last 10', analysisKey: '10' },
        { suffix: '_projected', label: 'Projected', analysisKey: 'projected' }
      ];
      
      const customAnalysisData = {};
      
      timeframes.forEach(({ suffix, label, analysisKey }) => {
        let customScore = 0;
        const customCategories = {};
        
        // Get opponent stats from the appropriate analysis data
        // For season, the suffix is empty string, so we need to handle that
        const analysisForTimeframe = currentAnalyses[analysisKey];
        let theirStats = {};
        
        // First try to get their_stats directly from the timeframe-specific analysis
        if (analysisForTimeframe?.their_stats) {
          theirStats = analysisForTimeframe.their_stats;
        }
        
        // Always try to extract from matchup categories as well (in case their_stats doesn't have all keys)
        // The matchup.categories has opponent stats for the correct timeframe
        if (analysisForTimeframe?.matchup?.categories) {
          // Extract opponent stats from matchup categories
          // The matchup.categories already has the correct timeframe values, we just need to map to keys with suffix
          Object.keys(analysisForTimeframe.matchup.categories).forEach(cat => {
            const catKey = cat === 'WIN%' ? cat : `${cat}${suffix}`;
            const opponentValue = analysisForTimeframe.matchup.categories[cat]?.opponent;
            if (opponentValue !== undefined && opponentValue !== null) {
              theirStats[catKey] = opponentValue;
            }
          });
        }
        
        // Final fallback: try main analysis data (but this might only have projected stats)
        if (Object.keys(theirStats).length === 0) {
          if (analysisData?.their_stats) {
            // Try to extract stats with the correct suffix from main their_stats
            Object.keys(analysisData.matchup?.categories || {}).forEach(cat => {
              const catKey = cat === 'WIN%' ? cat : `${cat}${suffix}`;
              // Try to find the stat in their_stats with the suffix
              if (analysisData.their_stats[catKey] !== undefined) {
                theirStats[catKey] = analysisData.their_stats[catKey];
              }
            });
          }
          // Last resort: extract from main matchup categories (only works for projected)
          if (Object.keys(theirStats).length === 0 && analysisData?.matchup?.categories && suffix === '_projected') {
            Object.keys(analysisData.matchup.categories).forEach(cat => {
              const catKey = cat === 'WIN%' ? cat : `${cat}${suffix}`;
              const opponentValue = analysisData.matchup.categories[cat]?.opponent;
              if (opponentValue !== undefined && opponentValue !== null) {
                theirStats[catKey] = opponentValue;
              }
            });
          }
        }
        
        // Calculate your team totals (similar to calculate_team_totals in backend)
        const yourStats = {};
        
        // First, calculate totals for simple categories
        Object.keys(analysisData.matchup.categories).forEach(category => {
          const categoryKey = category === 'WIN%' ? category : `${category}${suffix}`;
          
          if (category === 'WIN%') {
            yourStats[categoryKey] = customLineup.reduce((sum, player) => {
              return sum + (teamWins[playerStats[player]?.TEAM] || 0);
            }, 0);
          } else if (category === 'TS%') {
            // TS% needs to be calculated from totals
            const totalPTS = customLineup.reduce((sum, player) => {
              return sum + (playerStats[player]?.[`PTS${suffix}`] || 0) * (gamesPlayed[playerStats[player]?.TEAM] || 0);
            }, 0);
            const totalFGA = customLineup.reduce((sum, player) => {
              return sum + (playerStats[player]?.[`FGA${suffix}`] || 0) * (gamesPlayed[playerStats[player]?.TEAM] || 0);
            }, 0);
            const totalFTA = customLineup.reduce((sum, player) => {
              return sum + (playerStats[player]?.[`FTA${suffix}`] || 0) * (gamesPlayed[playerStats[player]?.TEAM] || 0);
            }, 0);
            const denominator = 2 * (totalFGA + (0.44 * totalFTA));
            yourStats[categoryKey] = denominator > 0 ? totalPTS / denominator : 0;
          } else if (category === 'EFG%') {
            // EFG% needs to be calculated from totals
            const totalFGA = customLineup.reduce((sum, player) => {
              return sum + (playerStats[player]?.[`FGA${suffix}`] || 0) * (gamesPlayed[playerStats[player]?.TEAM] || 0);
            }, 0);
            const totalFGM = customLineup.reduce((sum, player) => {
              return sum + (playerStats[player]?.[`FGM${suffix}`] || 0) * (gamesPlayed[playerStats[player]?.TEAM] || 0);
            }, 0);
            const totalFG3M = customLineup.reduce((sum, player) => {
              return sum + (playerStats[player]?.[`FG3M${suffix}`] || 0) * (gamesPlayed[playerStats[player]?.TEAM] || 0);
            }, 0);
            yourStats[categoryKey] = totalFGA > 0 ? (totalFGM + 0.5 * totalFG3M) / totalFGA : 0;
          } else if (category === 'FT%') {
            // FT% needs to be calculated from totals
            const totalFTM = customLineup.reduce((sum, player) => {
              return sum + (playerStats[player]?.[`FTM${suffix}`] || 0) * (gamesPlayed[playerStats[player]?.TEAM] || 0);
            }, 0);
            const totalFTA = customLineup.reduce((sum, player) => {
              return sum + (playerStats[player]?.[`FTA${suffix}`] || 0) * (gamesPlayed[playerStats[player]?.TEAM] || 0);
            }, 0);
            yourStats[categoryKey] = totalFTA > 0 ? totalFTM / totalFTA : 0;
          } else if (category === 'PPS') {
            // PPS needs to be calculated from totals
            const totalPTS = customLineup.reduce((sum, player) => {
              return sum + (playerStats[player]?.[`PTS${suffix}`] || 0) * (gamesPlayed[playerStats[player]?.TEAM] || 0);
            }, 0);
            const totalFGA = customLineup.reduce((sum, player) => {
              return sum + (playerStats[player]?.[`FGA${suffix}`] || 0) * (gamesPlayed[playerStats[player]?.TEAM] || 0);
            }, 0);
            yourStats[categoryKey] = totalFGA > 0 ? totalPTS / totalFGA : 0;
          } else if (category === 'NFT') {
            // NFT is calculated as sum of (2*FTM - FTA) per player, where FTM and FTA are per-game averages
            // Backend does NOT multiply by games_played - it just sums the per-game NFT values
            yourStats[categoryKey] = customLineup.reduce((sum, player) => {
              // Only count players that exist in playerStats
              if (!playerStats[player]) return sum;
              const ftm = playerStats[player][`FTM${suffix}`] || 0;
              const fta = playerStats[player][`FTA${suffix}`] || 0;
              return sum + (2 * ftm - fta);
            }, 0);
          } else {
            // Regular categories: sum stat * games
            yourStats[categoryKey] = customLineup.reduce((sum, player) => {
              return sum + (playerStats[player]?.[categoryKey] || 0) * (gamesPlayed[playerStats[player]?.TEAM] || 0);
            }, 0);
          }
        });
        
        // Now compare with opponent stats
        Object.keys(analysisData.matchup.categories).forEach(category => {
          const categoryKey = category === 'WIN%' ? category : `${category}${suffix}`;
          const yourTotal = yourStats[categoryKey] || 0;
          const opponentStat = theirStats[categoryKey] || 0;
          
          // Calculate margin - reverse for inverse categories
          let margin;
          if (INVERSE_CATEGORIES.includes(category)) {
            margin = opponentStat - yourTotal; // Lower is better, so positive margin means you win
          } else {
            margin = yourTotal - opponentStat; // Higher is better
          }
          
          customCategories[category] = {
            your_team: yourTotal,
            opponent: opponentStat,
            margin: margin
          };
          
          if (margin > 0) customScore++;
        });
        
        const key = label.toLowerCase().replace(' ', '_');
        customAnalysisData[key] = {
          score: customScore,
          my_team_player_games: analysisData.matchup.my_team_player_games,
          their_team_player_games: analysisData.matchup.their_team_player_games,
          opponent: analysisData.matchup.opponent,
          categories: customCategories
        };
      });
      
      setCustomAnalysis(customAnalysisData);
    } catch (err) {
      console.error('Error calculating custom lineup:', err);
    } finally {
      setLoadingCustom(false);
    }
  };

  useEffect(() => {
    // Initial fetch to get fantasy schedule
    const initializeAnalysis = async () => {
      await fetchAnalysis(null, true);
      // Start loading current analyses and pickups after initial load
      fetchCurrentAnalyses(null);
      fetchPickupAnalyses(null);
    };
    initializeAnalysis();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    // Set default active week once we have the schedule (only once)
    if (analysisData?.fantasy_schedule && !hasSetDefaultWeek) {
      const today = new Date();
      today.setHours(0, 0, 0, 0); // Normalize to start of day
      const dayOfWeek = today.getDay(); // 0 = Sunday, 6 = Saturday
      const isWeekend = dayOfWeek === 0 || dayOfWeek === 6; // Saturday or Sunday
      
      // Find the current week (week that contains today)
      let currentWeekIndex = analysisData.fantasy_schedule.findIndex(([dateStr]) => {
        // Parse date string directly to avoid timezone issues
        const [year, month, day] = dateStr.split('-').map(Number);
        const weekStart = new Date(year, month - 1, day);
        weekStart.setHours(0, 0, 0, 0);
        const weekEnd = new Date(weekStart);
        weekEnd.setDate(weekEnd.getDate() + 6); // Week is 7 days
        return today >= weekStart && today <= weekEnd;
      });
      
      // If current week not found, default to first week
      if (currentWeekIndex === -1) {
        currentWeekIndex = 0;
      }
      
      // If it's Saturday or Sunday, show upcoming week instead
      let selectedWeekIndex = currentWeekIndex;
      if (isWeekend) {
        // Find the next week after current week
        const upcomingWeekIndex = analysisData.fantasy_schedule.findIndex(([dateStr], index) => {
          return index > currentWeekIndex;
        });
        
        if (upcomingWeekIndex !== -1) {
          selectedWeekIndex = upcomingWeekIndex;
        }
      }
      
      setActiveWeek(selectedWeekIndex);
      setHasSetDefaultWeek(true);
      
      // Fetch analysis for the selected week
      const [weekStart] = analysisData.fantasy_schedule[selectedWeekIndex];
      fetchAnalysis(weekStart);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [analysisData, hasSetDefaultWeek]);

  const formatScore = (score, category = null) => {
    if (typeof score !== 'number') return '0.0';
    
    // For percentage categories, show 3 decimal places
    if (category && (category.includes('%') || category === 'TS%' || category === 'EFG%' || category === 'FT%')) {
      return score.toFixed(3);
    }
    
    return score.toFixed(1);
  };

  const formatMatchupScore = (score) => {
    if (typeof score !== 'number') return '0-0';
    // Score represents the actual number of wins
    const totalCategories = 11;
    const wins = Math.round(score);
    const losses = totalCategories - wins;
    return `${wins}-${losses}`;
  };

  const getScoreColor = (score) => {
    const totalCategories = 11;
    const halfCategories = totalCategories / 2;
    
    if (score > halfCategories) return 'text-green-600'; // Winning
    if (score < halfCategories) return 'text-red-600';   // Losing
    return 'text-gray-600'; // Tied
  };

  // const getMarginColor = (margin) => {
  //   if (margin > 0) return 'text-green-600 font-semibold';
  //   if (margin < 0) return 'text-red-600 font-semibold';
  //   return 'text-gray-600';
  // };

  const getCategoryName = (category) => {
    const categoryNames = {
      'PTS': 'PTS',
      'FG3M': '3PM',
      'AST': 'AST',
      'TOV': 'TOV',
      'REB': 'REB',
      'STL': 'STL',
      'BLK': 'BLK',
      'PF': 'PF',
      'TS%': 'TS%',
      'NFT': 'NFT',
      'PLUS_MINUS': '+/-'
    };
    return categoryNames[category] || category;
  };

  const formatWeekTab = (weekIndex, scheduleEntry) => {
    const [startDate] = scheduleEntry;
    const weekNum = weekIndex + 1;
    // Parse date string directly to avoid timezone issues
    const [year, month, day] = startDate.split('-').map(Number);
    const date = new Date(year, month - 1, day);
    const monthName = date.toLocaleDateString('en-US', { month: 'short' });
    return `Week ${weekNum} (${monthName} ${day})`;
  };

  const renderTableCell = (matchupData, headerText, pickupDropInfo = null) => {
    if (!matchupData) {
      return (
        <div className="flex flex-col min-h-[200px] items-center">
          {pickupDropInfo && <div className="h-16 mb-2 flex items-center justify-center">{pickupDropInfo}</div>}
          <div className="bg-gray-700 rounded border border-gray-600 p-4 text-center text-gray-500 text-sm max-w-[256px] w-full">
            No data
          </div>
        </div>
      );
    }

    return (
      <div className="flex flex-col items-center">
        {pickupDropInfo && (
          <div className="h-16 mb-2 flex items-center justify-center w-full">
            {pickupDropInfo}
          </div>
        )}
        {!pickupDropInfo && <div className="h-16 mb-2"></div>}
        
        <h4 className="text-sm font-semibold text-gray-400 mb-2">{headerText}</h4>
        <div className="flex items-center justify-between mb-2 max-w-[256px] w-full">
          <div className="text-center">
            <p className="text-lg font-semibold text-white">
              {Object.values(matchupData.my_team_player_games || {}).reduce((sum, games) => sum + games, 0)}
            </p>
            <p className="text-xs text-gray-400">Your Games</p>
          </div>
          <div className="text-center">
            <p className={`text-2xl font-bold ${getScoreColor(matchupData.score)}`}>
              {formatMatchupScore(matchupData.score)}
            </p>
          </div>
          <div className="text-center">
            <p className="text-lg font-semibold text-white">
              {Object.values(matchupData.their_team_player_games || {}).reduce((sum, games) => sum + games, 0)}
            </p>
            <p className="text-xs text-gray-400">{matchupData.opponent} Games</p>
          </div>
        </div>
        
        <div className="bg-gray-600 rounded border border-gray-500 overflow-hidden max-w-[256px] w-full">
          <div className="text-xs text-gray-400 bg-gray-700 px-3 py-2 border-b border-gray-500">
            <div className="grid grid-cols-3 gap-2">
              <div className="text-center">Your Team</div>
              <div className="text-center">Category</div>
              <div className="text-center">Opponent</div>
            </div>
          </div>
          <div>
            {Object.entries(matchupData.categories || {})
              .sort(([a], [b]) => {
                const indexA = CATEGORY_ORDER.indexOf(a);
                const indexB = CATEGORY_ORDER.indexOf(b);
                if (indexA !== -1 && indexB !== -1) return indexA - indexB;
                if (indexA !== -1) return -1;
                if (indexB !== -1) return 1;
                return 0;
              })
              .map(([category, data]) => {
                const isWin = data.margin > 0;
                const isLoss = data.margin < 0;
                
                return (
                  <div key={category} className="relative px-3 py-2 border-b border-gray-600/30 last:border-b-0 hover:bg-gray-600/20 transition-all duration-200">
                    {isWin && (
                      <div className="absolute inset-0 bg-gradient-to-r from-emerald-500/10 via-emerald-400/8 to-transparent rounded-md"></div>
                    )}
                    {isLoss && (
                      <div className="absolute inset-0 bg-gradient-to-r from-red-500/10 via-red-400/8 to-transparent rounded-md"></div>
                    )}
                    
                    <div className="relative grid grid-cols-3 gap-3 items-center">
                      <div className="text-right">
                        <div className={`text-lg font-bold ${isWin ? 'text-emerald-300' : isLoss ? 'text-red-300' : 'text-gray-200'}`}>
                          {formatScore(data.your_team, category)}
                        </div>
                      </div>
                      <div className="text-center">
                        <div className="text-gray-500 text-xs font-medium uppercase tracking-wide">
                          {getCategoryName(category)}
                        </div>
                        <div className={`text-xs font-semibold ${
                          isWin ? 'text-emerald-400' : 
                          isLoss ? 'text-red-400' : 
                          'text-gray-500'
                        }`}>
                          {data.margin > 0 ? '+' : ''}{formatScore(data.margin, category)}
                        </div>
                      </div>
                      <div className="text-left">
                        <div className={`text-lg font-bold ${isLoss ? 'text-emerald-300' : isWin ? 'text-red-300' : 'text-gray-200'}`}>
                          {formatScore(data.opponent, category)}
                        </div>
                      </div>
                    </div>
                  </div>
                );
              })}
          </div>
        </div>
      </div>
    );
  };

  if (loading) {
    return (
      <div className="bg-gray-800 rounded-lg shadow-xl p-6">
        <div className="flex items-center justify-center">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-nba-orange"></div>
          <span className="ml-2 text-white">Analyzing lineup...</span>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="bg-gray-800 rounded-lg shadow-xl p-6">
        <div className="text-red-400 text-center">
          <p className="font-semibold">Error loading analysis</p>
          <p className="text-sm">{error}</p>
          <button 
            onClick={fetchAnalysis}
            className="mt-2 px-4 py-2 bg-nba-orange text-white rounded hover:bg-orange-600"
          >
            Retry
          </button>
        </div>
      </div>
    );
  }

  if (!analysisData) {
    return (
      <div className="bg-gray-800 rounded-lg shadow-xl p-6">
        <p className="text-gray-300 text-center">No analysis data available</p>
      </div>
    );
  }

  const { matchup, pickups = [] } = analysisData;
  
  // Use consistent player games from main analysis for all Current column cells
  const canonicalMyTeamPlayerGames = matchup?.my_team_player_games || {};
  const canonicalTheirTeamPlayerGames = matchup?.their_team_player_games || {};

  return (
    <div className="bg-gray-800 rounded-lg shadow-xl p-6">
      <div className="flex justify-between items-center mb-6">
        <h2 className="text-2xl font-bold text-nba-orange">Lineup Optimizer</h2>
        <button 
          onClick={fetchAnalysis}
          className="px-4 py-2 bg-nba-orange text-white rounded hover:bg-orange-600 transition-colors"
        >
          Refresh Analysis
        </button>
      </div>

      {/* Matchup Analysis */}
      <div className="mb-8">
        {/* Week Tabs */}
        {analysisData?.fantasy_schedule && (
          <div className="mb-4">
            <div className="flex flex-wrap gap-2">
              {analysisData.fantasy_schedule.map((scheduleEntry, index) => (
                <button
                  key={index}
                  onClick={() => {
                    setActiveWeek(index);
                    const [weekStart] = scheduleEntry;
                    console.log('scheduleEntry:', scheduleEntry, 'weekStart:', weekStart);
                    fetchAnalysis(weekStart);
                  }}
                  className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
                    activeWeek === index
                      ? 'bg-nba-orange text-white'
                      : 'bg-gray-600 text-gray-300 hover:bg-gray-500'
                  }`}
                >
                  {formatWeekTab(index, scheduleEntry)}
                </button>
              ))}
            </div>
          </div>
        )}
        
        <div className="relative overflow-x-auto w-full">
          {/* Content Loading Overlay */}
          {contentLoading && (
            <div className="absolute inset-0 bg-gray-800 bg-opacity-75 rounded-lg flex items-center justify-center z-10">
              <div className="text-white text-lg">Loading...</div>
            </div>
          )}
          
          {/* 4x5 Grid Layout: Rows (season average, last 5, last 10, projected) × Columns (Current, last 5 pickup, last 10 pickup, projected pickup, Manual pickup) */}
          <div style={{ display: 'grid', gridTemplateColumns: '120px repeat(5, minmax(280px, 1fr))', gridTemplateRows: '40px repeat(4, auto)', gap: '1rem', alignItems: 'start', minWidth: '1600px' }}>
            {/* Header row */}
            <div style={{ gridColumn: 1, gridRow: 1 }}></div>
            <div style={{ gridColumn: 2, gridRow: 1 }} className="text-sm font-semibold text-gray-400 text-center">Current</div>
            <div style={{ gridColumn: 3, gridRow: 1 }} className="text-sm font-semibold text-gray-400 text-center">Last 5 pickup</div>
            <div style={{ gridColumn: 4, gridRow: 1 }} className="text-sm font-semibold text-gray-400 text-center">Last 10 pickup</div>
            <div style={{ gridColumn: 5, gridRow: 1 }} className="text-sm font-semibold text-gray-400 text-center">Projected pickup</div>
            <div style={{ gridColumn: 6, gridRow: 1 }} className="text-sm font-semibold text-gray-400 text-center">Manual pickup</div>
            
            {/* Row 1: Season Average */}
            <div style={{ gridColumn: 1, gridRow: 2 }} className="text-sm font-semibold text-gray-400 flex items-center">Season Avg</div>
            {/* Column 1: Current */}
            <div style={{ gridColumn: 2, gridRow: 2 }}>
              {(() => {
                const currentMatchup = currentAnalyses.season?.matchup ? {
                  ...currentAnalyses.season.matchup,
                  my_team_player_games: canonicalMyTeamPlayerGames,
                  their_team_player_games: canonicalTheirTeamPlayerGames
                } : matchup;
                const dropsInfo = currentMatchup?.drops && currentMatchup.drops.length > 0 ? (
                  <div className="text-sm mb-2 text-center">
                    <div>
                      <span className="text-red-400 font-semibold">↓ </span>
                      <span className="text-white text-xs">{currentMatchup.drops.join(', ')}</span>
                    </div>
                  </div>
                ) : null;
                return renderTableCell(currentMatchup, 'Current', dropsInfo);
              })()}
            </div>
            {/* Column 2: Last 5 pickup */}
            <div style={{ gridColumn: 3, gridRow: 2 }}>
              {(() => {
                const pickupData = pickupAnalyses['5_projected']; // Use projected as closest to season average
                const pickupInfo = pickupData?.matchup?.pickups && pickupData.matchup.pickups.length > 0 ? (
                  <div className="text-sm mb-2 text-center">
                    <div className="mb-1">
                      <span className="text-green-400 font-semibold">↑ </span>
                      <span className="text-white text-xs">{pickupData.matchup.pickups.join(', ')}</span>
                    </div>
                    {pickupData.matchup.drops && pickupData.matchup.drops.length > 0 && (
                      <div>
                        <span className="text-red-400 font-semibold">↓ </span>
                        <span className="text-white text-xs">{pickupData.matchup.drops.join(', ')}</span>
                      </div>
                    )}
                  </div>
                ) : null;
                return renderTableCell(pickupData?.matchup, 'Last 5 pickup', pickupInfo);
              })()}
            </div>
            {/* Column 3: Last 10 pickup */}
            <div style={{ gridColumn: 4, gridRow: 2 }}>
              {(() => {
                const pickupData = pickupAnalyses['10_projected'];
                const pickupInfo = pickupData?.matchup?.pickups && pickupData.matchup.pickups.length > 0 ? (
                  <div className="text-sm mb-2 text-center">
                    <div className="mb-1">
                      <span className="text-green-400 font-semibold">↑ </span>
                      <span className="text-white text-xs">{pickupData.matchup.pickups.join(', ')}</span>
                    </div>
                    {pickupData.matchup.drops && pickupData.matchup.drops.length > 0 && (
                      <div>
                        <span className="text-red-400 font-semibold">↓ </span>
                        <span className="text-white text-xs">{pickupData.matchup.drops.join(', ')}</span>
                      </div>
                    )}
                  </div>
                ) : null;
                return renderTableCell(pickupData?.matchup, 'Last 10 pickup', pickupInfo);
              })()}
            </div>
            {/* Column 4: Projected pickup */}
            <div style={{ gridColumn: 5, gridRow: 2 }}>
              {(() => {
                const pickupData = pickupAnalyses['projected_projected'];
                const pickupInfo = pickupData?.matchup?.pickups && pickupData.matchup.pickups.length > 0 ? (
                  <div className="text-sm mb-2 text-center">
                    <div className="mb-1">
                      <span className="text-green-400 font-semibold">↑ </span>
                      <span className="text-white text-xs">{pickupData.matchup.pickups.join(', ')}</span>
                    </div>
                    {pickupData.matchup.drops && pickupData.matchup.drops.length > 0 && (
                      <div>
                        <span className="text-red-400 font-semibold">↓ </span>
                        <span className="text-white text-xs">{pickupData.matchup.drops.join(', ')}</span>
                      </div>
                    )}
                  </div>
                ) : null;
                return renderTableCell(pickupData?.matchup, 'Projected pickup', pickupInfo);
              })()}
            </div>
            {/* Column 5: Manual pickup */}
            <div style={{ gridColumn: 6, gridRow: 2 }} className="flex flex-col items-center">
              <div className="h-16 mb-2 flex items-center justify-center w-full max-w-[256px] gap-2">
                <div className="text-sm relative flex-1">
                  <div className="relative mb-1">
                    <input
                      type="text"
                      value={customPickup || pickupSearchTerm}
                      onChange={(e) => {
                        setPickupSearchTerm(e.target.value);
                        setShowPickupDropdown(true);
                        if (!e.target.value) {
                          setCustomPickup(null);
                        }
                      }}
                      onFocus={() => setShowPickupDropdown(true)}
                      onBlur={() => setTimeout(() => setShowPickupDropdown(false), 200)}
                      placeholder="Select pickup..."
                      className="w-full px-2 py-1 bg-gray-600 text-white text-xs rounded border border-gray-500 focus:outline-none focus:border-nba-orange"
                    />
                    {showPickupDropdown && analysisData?.available_players && (
                      <div className="absolute z-50 w-full mt-1 bg-gray-700 border border-gray-500 rounded max-h-60 overflow-y-auto">
                        {analysisData.available_players
                          .filter(p => {
                            if (!analysisData.player_stats?.[p]) return false;
                            if (!pickupSearchTerm) return true;
                            return p.toLowerCase().includes(pickupSearchTerm.toLowerCase());
                          })
                          .sort((a, b) => {
                            return (analysisData.player_stats[b]?.['Z-SCORE_projected'] || 0) - (analysisData.player_stats[a]?.['Z-SCORE_projected'] || 0);
                          })
                          .slice(0, 100)
                          .map(player => (
                            <div
                              key={player}
                              onClick={() => {
                                setCustomPickup(player);
                                setPickupSearchTerm(player);
                                setShowPickupDropdown(false);
                              }}
                              className="px-2 py-1 text-white text-xs hover:bg-gray-600 cursor-pointer"
                            >
                              {player}
                            </div>
                          ))
                        }
                        {analysisData.available_players.filter(p => {
                          if (!analysisData.player_stats?.[p]) return false;
                          if (!pickupSearchTerm) return true;
                          return p.toLowerCase().includes(pickupSearchTerm.toLowerCase());
                        }).length === 0 && (
                          <div className="px-2 py-1 text-gray-400 text-xs">No players found</div>
                        )}
                      </div>
                    )}
                  </div>
                  <select 
                    value={customDrop || ''} 
                    onChange={(e) => setCustomDrop(e.target.value)}
                    className="w-full px-2 py-1 bg-gray-600 text-white text-xs rounded border border-gray-500"
                  >
                    <option value="">Select drop...</option>
                    {(analysisData?.all_my_team_players || analysisData?.best_lineup || [])
                      .filter(player => {
                        return !analysisData?.undroppable_players?.includes(player);
                      })
                      .map(player => (
                        <option key={player} value={player}>{player}</option>
                      ))
                    }
                  </select>
                </div>
                <button
                  onClick={calculateCustomLineup}
                  disabled={!customPickup || loadingCustom}
                  className="px-3 py-2 bg-nba-orange text-white text-sm rounded hover:bg-orange-600 disabled:bg-gray-600 disabled:cursor-not-allowed whitespace-nowrap"
                >
                  {loadingCustom ? 'Calculating...' : 'Calculate'}
                </button>
              </div>
              
              <h4 className="text-sm font-semibold text-gray-400 mb-2">Manual pickup</h4>
              
              {customAnalysis?.current ? (
                <>
                  <div className="flex items-center justify-between mb-2 max-w-[256px] w-full">
                    <div className="text-center">
                      <p className="text-lg font-semibold text-white">
                        {Object.values(customAnalysis.current.my_team_player_games || {}).reduce((sum, games) => sum + games, 0)}
                      </p>
                      <p className="text-xs text-gray-400">Your Games</p>
                    </div>
                    <div className="text-center">
                      <p className={`text-2xl font-bold ${getScoreColor(customAnalysis.current.score)}`}>
                        {formatMatchupScore(customAnalysis.current.score)}
                      </p>
                    </div>
                    <div className="text-center">
                      <p className="text-lg font-semibold text-white">
                        {Object.values(customAnalysis.current.their_team_player_games || {}).reduce((sum, games) => sum + games, 0)}
                      </p>
                      <p className="text-xs text-gray-400">{customAnalysis.current.opponent} Games</p>
                    </div>
                  </div>
                  
                  <div className="bg-gray-600 rounded border border-gray-500 overflow-hidden max-w-[256px] w-full">
                    <div className="text-xs text-gray-400 bg-gray-700 px-3 py-2 border-b border-gray-500">
                      <div className="grid grid-cols-3 gap-2">
                        <div className="text-center">Your Team</div>
                        <div className="text-center">Category</div>
                        <div className="text-center">Opponent</div>
                      </div>
                    </div>
                    <div>
                      {Object.entries(customAnalysis.current.categories || {})
                        .sort(([a], [b]) => {
                          const indexA = CATEGORY_ORDER.indexOf(a);
                          const indexB = CATEGORY_ORDER.indexOf(b);
                          if (indexA !== -1 && indexB !== -1) return indexA - indexB;
                          if (indexA !== -1) return -1;
                          if (indexB !== -1) return 1;
                          return 0;
                        })
                        .map(([category, data]) => {
                          const isWin = data.margin > 0;
                          const isLoss = data.margin < 0;
                          
                          return (
                            <div key={category} className="relative px-3 py-2 border-b border-gray-600/30 last:border-b-0 hover:bg-gray-600/20 transition-all duration-200">
                              {isWin && (
                                <div className="absolute inset-0 bg-gradient-to-r from-emerald-500/10 via-emerald-400/8 to-transparent rounded-md"></div>
                              )}
                              {isLoss && (
                                <div className="absolute inset-0 bg-gradient-to-r from-red-500/10 via-red-400/8 to-transparent rounded-md"></div>
                              )}
                              
                              <div className="relative grid grid-cols-3 gap-3 items-center">
                                <div className="text-right">
                                  <div className={`text-lg font-bold ${isWin ? 'text-emerald-300' : isLoss ? 'text-red-300' : 'text-gray-200'}`}>
                                    {formatScore(data.your_team, category)}
                                  </div>
                                </div>
                                <div className="text-center">
                                  <div className="text-gray-500 text-xs font-medium uppercase tracking-wide">
                                    {getCategoryName(category)}
                                  </div>
                                  <div className={`text-xs font-semibold ${
                                    isWin ? 'text-emerald-400' : 
                                    isLoss ? 'text-red-400' : 
                                    'text-gray-500'
                                  }`}>
                                    {data.margin > 0 ? '+' : ''}{formatScore(data.margin, category)}
                                  </div>
                                </div>
                                <div className="text-left">
                                  <div className={`text-lg font-bold ${isLoss ? 'text-emerald-300' : isWin ? 'text-red-300' : 'text-gray-200'}`}>
                                    {formatScore(data.opponent, category)}
                                  </div>
                                </div>
                              </div>
                            </div>
                          );
                        })}
                    </div>
                  </div>
                </>
              ) : (
                <div className="bg-gray-700 rounded border border-gray-600 p-4 text-center text-gray-500 text-sm max-w-[256px] w-full">
                  No data
                </div>
              )}
            </div>

            {/* Row 2: Last 5 */}
            <div style={{ gridColumn: 1, gridRow: 3 }} className="text-sm font-semibold text-gray-400 flex items-center">Last 5</div>
            <div style={{ gridColumn: 2, gridRow: 3 }}>
              {(() => {
                const currentMatchup = currentAnalyses['5']?.matchup ? {
                  ...currentAnalyses['5'].matchup,
                  my_team_player_games: canonicalMyTeamPlayerGames,
                  their_team_player_games: canonicalTheirTeamPlayerGames
                } : matchup;
                const dropsInfo = currentMatchup?.drops && currentMatchup.drops.length > 0 ? (
                  <div className="text-sm mb-2 text-center">
                    <div>
                      <span className="text-red-400 font-semibold">↓ </span>
                      <span className="text-white text-xs">{currentMatchup.drops.join(', ')}</span>
                    </div>
                  </div>
                ) : null;
                return renderTableCell(currentMatchup, 'Current', dropsInfo);
              })()}
            </div>
            <div style={{ gridColumn: 3, gridRow: 3 }}>
              {renderTableCell(pickupAnalyses['5_5']?.matchup, 'Last 5 pickup', null)}
            </div>
            <div style={{ gridColumn: 4, gridRow: 3 }}>
              {renderTableCell(pickupAnalyses['10_5']?.matchup, 'Last 10 pickup', null)}
            </div>
            <div style={{ gridColumn: 5, gridRow: 3 }}>
              {renderTableCell(pickupAnalyses['projected_5']?.matchup, 'Projected pickup', null)}
            </div>
            <div style={{ gridColumn: 6, gridRow: 3 }}>
              {renderTableCell(customAnalysis?.last_5, 'Manual pickup', null)}
            </div>

            {/* Row 3: Last 10 */}
            <div style={{ gridColumn: 1, gridRow: 4 }} className="text-sm font-semibold text-gray-400 flex items-center">Last 10</div>
            <div style={{ gridColumn: 2, gridRow: 4 }}>
              {(() => {
                const currentMatchup = currentAnalyses['10']?.matchup ? {
                  ...currentAnalyses['10'].matchup,
                  my_team_player_games: canonicalMyTeamPlayerGames,
                  their_team_player_games: canonicalTheirTeamPlayerGames
                } : matchup;
                const dropsInfo = currentMatchup?.drops && currentMatchup.drops.length > 0 ? (
                  <div className="text-sm mb-2 text-center">
                    <div>
                      <span className="text-red-400 font-semibold">↓ </span>
                      <span className="text-white text-xs">{currentMatchup.drops.join(', ')}</span>
                    </div>
                  </div>
                ) : null;
                return renderTableCell(currentMatchup, 'Current', dropsInfo);
              })()}
            </div>
            <div style={{ gridColumn: 3, gridRow: 4 }}>
              {renderTableCell(pickupAnalyses['5_10']?.matchup, 'Last 5 pickup', null)}
            </div>
            <div style={{ gridColumn: 4, gridRow: 4 }}>
              {renderTableCell(pickupAnalyses['10_10']?.matchup, 'Last 10 pickup', null)}
            </div>
            <div style={{ gridColumn: 5, gridRow: 4 }}>
              {renderTableCell(pickupAnalyses['projected_10']?.matchup, 'Projected pickup', null)}
            </div>
            <div style={{ gridColumn: 6, gridRow: 4 }}>
              {renderTableCell(customAnalysis?.last_10, 'Manual pickup', null)}
            </div>

            {/* Row 4: Projected */}
            <div style={{ gridColumn: 1, gridRow: 5 }} className="text-sm font-semibold text-gray-400 flex items-center">Projected</div>
            <div style={{ gridColumn: 2, gridRow: 5 }}>
              {(() => {
                const currentMatchup = currentAnalyses.projected?.matchup ? {
                  ...currentAnalyses.projected.matchup,
                  my_team_player_games: canonicalMyTeamPlayerGames,
                  their_team_player_games: canonicalTheirTeamPlayerGames
                } : matchup;
                const dropsInfo = currentMatchup?.drops && currentMatchup.drops.length > 0 ? (
                  <div className="text-sm mb-2 text-center">
                    <div>
                      <span className="text-red-400 font-semibold">↓ </span>
                      <span className="text-white text-xs">{currentMatchup.drops.join(', ')}</span>
                    </div>
                  </div>
                ) : null;
                return renderTableCell(currentMatchup, 'Current', dropsInfo);
              })()}
            </div>
            <div style={{ gridColumn: 3, gridRow: 5 }}>
              {renderTableCell(pickupAnalyses['5_projected']?.matchup, 'Last 5 pickup', null)}
            </div>
            <div style={{ gridColumn: 4, gridRow: 5 }}>
              {renderTableCell(pickupAnalyses['10_projected']?.matchup, 'Last 10 pickup', null)}
            </div>
            <div style={{ gridColumn: 5, gridRow: 5 }}>
              {renderTableCell(pickupAnalyses['projected_projected']?.matchup, 'Projected pickup', null)}
            </div>
            <div style={{ gridColumn: 6, gridRow: 5 }}>
              {renderTableCell(customAnalysis?.projected, 'Manual pickup', null)}
            </div>
          </div>
        </div>
      </div>

      {/* Pickup Suggestions */}
      {pickups && pickups.length > 0 && (
        <div>
          <h3 className="text-xl font-semibold mb-4 text-white">Pickup Suggestions</h3>
          <div className="space-y-3">
            {pickups.slice(0, 5).map((pickup, index) => (
              <div key={index} className="border border-gray-600 rounded-lg p-4 bg-gray-700">
                <div className="flex justify-between items-start mb-2">
                  <div>
                    <h4 className="font-semibold text-white">{pickup.player}</h4>
                    <p className="text-sm text-gray-300">{pickup.position} • {pickup.team}</p>
                  </div>
                  <div className="text-right">
                    <p className={`text-lg font-bold ${getScoreColor(pickup.score_improvement)}`}>
                      {pickup.score_improvement > 0 ? '+' : ''}{formatScore(pickup.score_improvement)}
                    </p>
                    <p className="text-sm text-gray-300">score improvement</p>
                  </div>
                </div>
                
                <div className="text-sm text-gray-300">
                  <p>New projected score: {formatScore(pickup.new_projected_score)}</p>
                </div>

                {/* Category Impact */}
                <div className="mt-2">
                  <p className="text-xs font-medium text-gray-200 mb-1">Category Impact:</p>
                  <div className="flex flex-wrap gap-1">
                    {Object.entries(pickup.category_impact || {}).map(([cat, impact]) => (
                      <span 
                        key={cat}
                        className={`px-2 py-1 rounded text-xs ${
                          impact > 0 ? 'bg-green-600 text-green-100' : 
                          impact < 0 ? 'bg-red-600 text-red-100' : 
                          'bg-gray-600 text-gray-200'
                        }`}
                      >
                        {cat}: {impact > 0 ? '+' : ''}{formatScore(impact)}
                      </span>
                    ))}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

    </div>
  );
};

export default LineupOptimizer;
