import React, { useState, useEffect } from 'react';
import { getTeamStandings } from '../services/api';

const CATEGORY_NAMES = {
  'PTS': 'PTS',
  'AST': 'AST',
  'TOV': 'TOV',
  'PF': 'PF',
  'REB': 'REB',
  'STL': 'STL',
  'BLK': 'BLK',
  'FG3M': '3PM',
  'TS%': 'TS%',
  'NFT': 'NFT',
  'PLUS_MINUS': '+/-'
};

const PERCENTAGE_CATEGORIES = ['TS%'];

const TeamStandings = ({ config }) => {
  const [statType, setStatType] = useState('projected');
  const [healthyOnly, setHealthyOnly] = useState(false);
  const [standingsData, setStandingsData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [dataCache, setDataCache] = useState({});

  useEffect(() => {
    const cacheKey = `teamStandings_${statType}_${healthyOnly}`;
    
    // Check sessionStorage first
    const cachedData = sessionStorage.getItem(cacheKey);
    if (cachedData) {
      try {
        const parsed = JSON.parse(cachedData);
        setStandingsData(parsed);
        return;
      } catch (e) {
        // Invalid cache, continue to fetch
      }
    }
    
    // Check in-memory cache
    if (dataCache[cacheKey]) {
      setStandingsData(dataCache[cacheKey]);
      return;
    }

    // Load data if not cached
    const loadStandings = async () => {
      setLoading(true);
      try {
        const data = await getTeamStandings(statType, healthyOnly);
        setStandingsData(data);
        setDataCache(prev => ({ ...prev, [cacheKey]: data }));
        // Cache in sessionStorage
        sessionStorage.setItem(cacheKey, JSON.stringify(data));
      } catch (error) {
        console.error('Error loading team standings:', error);
      } finally {
        setLoading(false);
      }
    };

    loadStandings();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [statType, healthyOnly]);

  const formatValue = (category, value) => {
    if (value === null || value === undefined) return '-';
    if (PERCENTAGE_CATEGORIES.includes(category)) {
      return (value * 100).toFixed(1);
    }
    if (category === 'PLUS_MINUS') {
      return value > 0 ? `+${value.toFixed(1)}` : value.toFixed(1);
    }
    return value.toFixed(1);
  };

  const getRankColor = (rank, totalTeams) => {
    // Interpolate from green (rank 1) to red (last rank)
    // rank is 1-indexed, so we convert to 0-1 scale
    const ratio = (rank - 1) / (totalTeams - 1);
    
    // Green: rgb(34, 197, 94) -> Red: rgb(239, 68, 68)
    const r = Math.round(34 + (239 - 34) * ratio);
    const g = Math.round(197 + (68 - 197) * ratio);
    const b = Math.round(94 + (68 - 94) * ratio);
    
    return `rgb(${r}, ${g}, ${b})`;
  };

  const getRankScore = (rank, totalTeams) => {
    // Convert rank (1 = best, totalTeams = worst) to score (100 = best, 0 = worst)
    return ((totalTeams - rank) / (totalTeams - 1)) * 100;
  };

  const getStatBgColor = (rank, totalTeams) => {
    const score = getRankScore(rank, totalTeams);
    
    if (score > 55) {
      // Green spectrum - better ranks
      if (rank === 1) return 'bg-green-900/60 border-green-400/80 shadow-lg shadow-green-400/30'; // Rank 1 with glow
      if (score >= 85) return 'bg-green-900/50 border-green-500/70 shadow-md shadow-green-500/25';
      if (score >= 70) return 'bg-green-900/40 border-green-600/60';
      if (score >= 60) return 'bg-green-900/30 border-green-700/50';
      return 'bg-green-900/20 border-green-900/30';
    } else if (score < 45) {
      // Red spectrum - worse ranks
      if (rank === totalTeams) return 'bg-red-900/60 border-red-400/80 shadow-lg shadow-red-400/30'; // Last rank with glow
      if (score <= 15) return 'bg-red-900/50 border-red-500/70 shadow-md shadow-red-500/25';
      if (score <= 30) return 'bg-red-900/40 border-red-600/60';
      if (score <= 40) return 'bg-red-900/30 border-red-700/50';
      return 'bg-red-900/20 border-red-900/30';
    }
    // Score between 45-55 - default background
    return 'bg-gray-800/10 border-gray-700/20';
  };

  const getStatTextColor = (rank, totalTeams) => {
    const score = getRankScore(rank, totalTeams);
    
    if (score > 55) {
      if (score >= 85) return 'text-green-300';
      if (score >= 70) return 'text-green-400';
      if (score >= 60) return 'text-green-500';
      return 'text-green-500';
    } else if (score < 45) {
      if (score <= 15) return 'text-red-300';
      if (score <= 30) return 'text-red-400';
      if (score <= 40) return 'text-red-500';
      return 'text-red-500';
    }
    return 'text-white';
  };

  const getRankTextColor = (rank, totalTeams) => {
    const score = getRankScore(rank, totalTeams);
    
    if (score > 55) {
      if (score >= 85) return 'text-green-400';
      if (score >= 70) return 'text-green-500';
      if (score >= 60) return 'text-green-500';
      return 'text-green-500';
    } else if (score < 45) {
      if (score <= 15) return 'text-red-400';
      if (score <= 30) return 'text-red-500';
      if (score <= 40) return 'text-red-500';
      return 'text-red-500';
    }
    return 'text-white';
  };

  if (loading && !standingsData) {
    return (
      <div className="flex justify-center items-center py-8">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-nba-orange"></div>
      </div>
    );
  }

  if (!standingsData || !standingsData.teams) {
    return (
      <div className="text-center py-8 text-gray-400">
        No standings data available
      </div>
    );
  }

  const { teams, categories, category_names } = standingsData;
  const isMyTeam = (team) => team.abbreviation === config?.MY_TEAM_ABV;
  
  // Use category_names from backend, fallback to local CATEGORY_NAMES
  const getCategoryName = (category) => {
    return category_names?.[category] || CATEGORY_NAMES[category] || category;
  };

  return (
    <div className="p-6">
      <div className="mb-6">
        <h2 className="text-2xl font-bold text-white mb-4">Team Standings</h2>
        
        <div className="flex flex-col sm:flex-row gap-4 items-start sm:items-center">
          <div className="flex items-center space-x-2">
            <span className="text-sm text-gray-300">Stats:</span>
            <select
              value={statType}
              onChange={(e) => setStatType(e.target.value)}
              className="px-3 py-1.5 bg-gray-700 border border-gray-600 rounded-md text-white text-sm focus:outline-none focus:ring-2 focus:ring-nba-orange focus:border-transparent"
            >
              <option value="season">Season Average</option>
              <option value="5">Last 5 Games</option>
              <option value="10">Last 10 Games</option>
              <option value="projected">Projected</option>
            </select>
          </div>

          <label className="flex items-center">
            <input
              type="checkbox"
              checked={healthyOnly}
              onChange={(e) => setHealthyOnly(e.target.checked)}
              className="h-4 w-4 text-nba-orange focus:ring-nba-orange border-gray-600 rounded bg-gray-700"
            />
            <span className="ml-2 text-sm text-gray-300">Healthy</span>
          </label>
        </div>
      </div>

      {loading ? (
        <div className="flex justify-center items-center py-8">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-nba-orange"></div>
        </div>
      ) : (
        <div className="overflow-x-auto bg-gray-800 rounded-lg shadow-xl">
          <table className="min-w-full">
            <thead>
              <tr>
                <th className="table-header w-16 text-center">Rank</th>
                <th className="table-header w-48 text-left">Team</th>
                {categories.map(category => (
                  <th key={category} className="table-header w-32 text-center">
                    {getCategoryName(category)}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="bg-gray-800 divide-y divide-gray-700">
              {teams.map((teamData, index) => {
                const team = teamData.team;
                const myTeam = isMyTeam(team);
                
                return (
                  <tr
                    key={team.id}
                    className={`hover:bg-gray-700 transition-colors ${
                      myTeam
                        ? 'bg-gradient-to-r from-nba-orange/10 via-nba-orange/5 to-transparent shadow-[0_0_8px_rgba(251,146,60,0.25)] ring-1 ring-nba-orange/30'
                        : ''
                    }`}
                  >
                    <td className="table-cell text-center">
                      <div className="flex items-center justify-center">
                        <span 
                          className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium text-white"
                          style={{
                            backgroundColor: getRankColor(index + 1, teams.length)
                          }}
                        >
                          {index + 1}
                        </span>
                      </div>
                    </td>
                    <td className="table-cell">
                      <div className="font-medium text-white">
                        {team.name || team.abbreviation}
                      </div>
                      <div className="text-xs text-gray-400">
                        Rank Sum: {teamData.total_rank_sum}
                      </div>
                    </td>
                    {categories.map(category => {
                      const total = teamData.category_totals[category];
                      const rank = teamData.category_rankings[category];
                      
                      return (
                        <td key={category} className="table-cell text-center">
                          <div className={`px-2 py-1 rounded border ${getStatBgColor(rank, teams.length)}`}>
                            <div className="flex items-center justify-center space-x-2">
                              <span className={`text-sm font-bold ${getStatTextColor(rank, teams.length)}`}>
                                {formatValue(category, total)}
                                {PERCENTAGE_CATEGORIES.includes(category) ? '%' : ''}
                              </span>
                              <span className={`text-xs opacity-75 ${getRankTextColor(rank, teams.length)}`}>
                                ({rank})
                              </span>
                            </div>
                          </div>
                        </td>
                      );
                    })}
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
};

export default TeamStandings;
