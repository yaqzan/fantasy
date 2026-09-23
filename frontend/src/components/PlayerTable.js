import React, { useState, useEffect } from 'react';
import DraftModal from './DraftModal';
import { calculateCustomZScores, calculateCustomAuctionValues } from '../services/api';

// Category names mapping from config
const CATEGORY_NAMES = {
    'PTS': 'PTS',
    'AST-TOV': 'AST',
    'AST': 'AST',
    'TOV': 'TOV',
    'PF': 'PF',
    'REB': 'REB',
    'STL': 'STL',
    'BLK': 'BLK',
    'FG3M': '3PM',
    'PPS': 'PPS',
    'DD2': 'DD',
    'TD3': 'TD',
    'TS%': 'TS%',
    'EFG%': 'EFG%',
    'FT%': 'FT%',
    'PLUS_MINUS': '+/-',
    'WIN%': 'WIN',
    'TOT': 'Total Games',
    'SCORE': 'Score',
    'BLKA': 'BLKA',
    'NFT': 'NFT',
    'VEFG%': 'VEFG%'
};

// Categories from config (updated to match fantasy_config.py)
const CATEGORIES = ['TS%', 'PTS', 'REB', 'AST', 'STL', 'BLK', 'FG3M', 'NFT', 'TOV', 'PF', 'PLUS_MINUS'];

// Inverse categories (lower is better)
// const INVERSE_CATEGORIES = ['BLKA', 'TOV', 'PF'];

// Percentage-based categories
const PERCENTAGE_CATEGORIES = ['TS%', 'EFG%', 'FT%', 'VEFG%'];

// Default EXP_FACTOR from config
const DEFAULT_EXP_FACTOR = 4;

const formatWeekDate = (dateStr) => {
  if (!dateStr) return '';
  // Parse date string directly to avoid timezone issues
  const [year, month, day] = dateStr.split('-').map(Number);
  const date = new Date(year, month - 1, day);
  const monthName = date.toLocaleDateString('en-US', { month: 'short' });
  return `${monthName} ${day}`;
};

const PlayerTable = ({ players, fantasyTeams, onDraftPlayer, onUndraftPlayer, onUpdatePlayer, expFactor, onExpFactorChange, config, statType = 'projected' }) => {
  console.log('Config in PlayerTable:', config);
  const [sortConfig, setSortConfig] = useState({ key: 'overall_rank', direction: 'asc' });
  const [draftModalPlayer, setDraftModalPlayer] = useState(null);
  const [puntCategories, setPuntCategories] = useState([]);
  const [includedCategories, setIncludedCategories] = useState(CATEGORIES);
  const [customScores, setCustomScores] = useState({});
  const [loadingCustomScores, setLoadingCustomScores] = useState(false);
  const [customAuctionValues, setCustomAuctionValues] = useState({});
  const [, setLoadingAuctionValues] = useState(false);

  // Force re-sort when custom scores change
  useEffect(() => {
    if (Object.keys(customScores).length > 0) {
      // Trigger a re-sort by updating the sort config
      setSortConfig(prev => ({ ...prev }));
    }
  }, [customScores]);

  // Force re-sort when statType changes to update OVR and rankings
  useEffect(() => {
    // Trigger a re-sort by updating the sort config
    setSortConfig(prev => ({ ...prev }));
  }, [statType]);

  // Handle EXP_FACTOR changes
  const handleExpFactorChange = async (newExpFactor) => {
    onExpFactorChange(newExpFactor);
    
    // If using default factor, clear custom values
    if (newExpFactor === DEFAULT_EXP_FACTOR) {
      setCustomAuctionValues({});
      return;
    }
    
    setLoadingAuctionValues(true);
    
    try {
      const response = await calculateCustomAuctionValues(newExpFactor, puntCategories);
      setCustomAuctionValues(response.auction_values || {});
    } catch (error) {
      console.error('Error calculating custom auction values:', error);
      setCustomAuctionValues({});
    } finally {
      setLoadingAuctionValues(false);
    }
  };

  // Load custom auction values when expFactor changes
  useEffect(() => {
    handleExpFactorChange(expFactor);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [expFactor]);

  // Recalculate auction values when punt categories change
  useEffect(() => {
    if (expFactor !== DEFAULT_EXP_FACTOR) {
      handleExpFactorChange(expFactor);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [puntCategories]);

  // Get auction value (custom or original)
  const getAuctionValue = (playerName, originalValue) => {
    return customAuctionValues[playerName]?.auction_value || originalValue;
  };

  // Handle category inclusion changes (unchecked = punt)
  const handleCategoryInclusionChange = async (category) => {
    const newIncludedCategories = includedCategories.includes(category)
      ? includedCategories.filter(cat => cat !== category)
      : [...includedCategories, category];
    
    setIncludedCategories(newIncludedCategories);
    
    // Calculate punt categories (excluded from included categories)
    const newPuntCategories = CATEGORIES.filter(cat => !newIncludedCategories.includes(cat));
    setPuntCategories(newPuntCategories);
    
    if (newPuntCategories.length > 0) {
      setLoadingCustomScores(true);
      try {
        const response = await calculateCustomZScores(newPuntCategories);
        setCustomScores(response.custom_scores);
      } catch (error) {
        console.error('Error calculating custom z-scores:', error);
      } finally {
        setLoadingCustomScores(false);
      }
    } else {
      setCustomScores({});
    }
  };

  // Get custom rank display with change
  const getCustomRankDisplay = (playerName, originalRank) => {
    const customScore = customScores[playerName];
    if (!customScore) {
      return (
        <span className="text-gray-400 text-sm">
          {originalRank}
        </span>
      );
    }

    const customRank = customScore.custom_z_rank;
    const rankDiff = originalRank - customRank;
    
    if (rankDiff === 0) {
      return (
        <span className="text-gray-400 text-sm">
          {customRank}
        </span>
      );
    }
    
    let colorClass = 'text-gray-400';
    let symbol = '';
    
    if (rankDiff > 0) {
      colorClass = 'text-green-400';
      symbol = '+';
    } else if (rankDiff < 0) {
      colorClass = 'text-red-400';
    }
    
    return (
      <div className="flex items-center space-x-1">
        <span className="text-gray-400 text-sm">
          {customRank}
        </span>
        <span className={`text-xs ${colorClass}`}>
          ({symbol}{rankDiff})
        </span>
      </div>
    );
  };

  // Get custom score display with change
  const getCustomScoreDisplay = (playerName, originalScore) => {
    const customScore = customScores[playerName];
    const roundedOriginal = Math.round(originalScore);
    
    if (!customScore) {
      return (
        <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-bold ${getZScoreColor(roundedOriginal)}`}>
          {roundedOriginal}
        </span>
      );
    }

    const customScoreValue = customScore.custom_z_score;
    const roundedCustom = Math.round(customScoreValue);
    const scoreDiff = roundedCustom - roundedOriginal;
    
    if (Math.abs(scoreDiff) < 1) {
      return (
        <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-bold ${getZScoreColor(roundedCustom)}`}>
          {roundedCustom}
        </span>
      );
    }
    
    let colorClass = 'text-gray-400';
    let symbol = '';
    
    if (scoreDiff > 0) {
      colorClass = 'text-green-400';
      symbol = '+';
    } else if (scoreDiff < 0) {
      colorClass = 'text-red-400';
    }
    
    return (
      <div className="flex items-center space-x-1">
        <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-bold ${getZScoreColor(roundedCustom)}`}>
          {roundedCustom}
        </span>
        <span className={`text-xs ${colorClass}`}>
          ({symbol}{scoreDiff})
        </span>
      </div>
    );
  };

  // Green/Red gradient with clear text for stat values
  const getStatTextColor = (score, isInverse = false) => {
    if (score > 55) {
      // Green spectrum with clear text
      if (score >= 90) return 'text-green-300';      // High intensity green
      if (score >= 80) return 'text-green-400';      // Medium-high intensity green
      if (score >= 70) return 'text-green-500';      // Medium intensity green
      if (score >= 60) return 'text-green-500';      // Medium intensity green
      return 'text-green-500';                       // Medium intensity green
    } else if (score < 45) {
      // Red spectrum with clear text
      if (score <= 10) return 'text-red-300';         // High intensity red
      if (score <= 20) return 'text-red-400';        // Medium-high intensity red
      if (score <= 30) return 'text-red-500';        // Medium intensity red
      if (score <= 40) return 'text-red-500';        // Medium intensity red
      return 'text-red-500';                         // Medium intensity red
    }
    // Score between 45-55 - default color
    return 'text-white';                              // Default white
  };

  // Green/Red gradient for score ranks (smaller text, readable but less prominent)
  const getScoreColor = (score, isInverse = false) => {
    if (score > 55) {
      // Green spectrum with readable text
      if (score >= 90) return 'text-green-400';      // High intensity green
      if (score >= 80) return 'text-green-500';      // Medium-high intensity green
      if (score >= 70) return 'text-green-500';      // Medium intensity green
      if (score >= 60) return 'text-green-500';      // Medium intensity green
      return 'text-green-500';                       // Medium intensity green
    } else if (score < 45) {
      // Red spectrum with readable text
      if (score <= 10) return 'text-red-400';         // High intensity red
      if (score <= 20) return 'text-red-500';        // Medium-high intensity red
      if (score <= 30) return 'text-red-500';        // Medium intensity red
      if (score <= 40) return 'text-red-500';        // Medium intensity red
      return 'text-red-500';                         // Medium intensity red
    }
    // Score between 45-55 - default color
    return 'text-white';                              // Default white
  };

  const getScoreBgColor = (score, isInverse = false) => {
    if (score > 55) {
      // Green spectrum with opacity scaling
      if (score >= 90) return 'bg-green-900/60 border-green-400/80 shadow-lg shadow-green-400/30';     // High opacity green with halo
      if (score >= 80) return 'bg-green-900/50 border-green-500/70 shadow-md shadow-green-500/25';     // Medium-high opacity green with subtle halo
      if (score >= 70) return 'bg-green-900/40 border-green-600/60';     // Medium opacity green
      if (score >= 60) return 'bg-green-900/30 border-green-700/50';     // Medium-low opacity green
      return 'bg-green-900/20 border-green-900/30';                       // Very low opacity green
    } else if (score < 45) {
      // Red spectrum with opacity scaling
      if (score <= 10) return 'bg-red-900/60 border-red-400/80 shadow-lg shadow-red-400/30';             // High opacity red with halo
      if (score <= 20) return 'bg-red-900/50 border-red-500/70 shadow-md shadow-red-500/25';            // Medium-high opacity red with subtle halo
      if (score <= 30) return 'bg-red-900/40 border-red-600/60';         // Medium opacity red
      if (score <= 40) return 'bg-red-900/30 border-red-700/50';         // Medium-low opacity red
      return 'bg-red-900/20 border-red-900/30';                          // Very low opacity red
    }
    // Score between 45-55 - default background
    return 'bg-gray-800/10 border-gray-700/20';                          // Very subtle neutral
  };

  // Get aura styling based on hot/cold intensity
  const getHotAura = (diff) => {
    if (diff >= 20) return 'text-orange-300 drop-shadow-[0_0_8px_rgba(251,146,60,0.9)] animate-pulse';
    if (diff >= 15) return 'text-orange-300 drop-shadow-[0_0_6px_rgba(251,146,60,0.7)]';
    if (diff >= 10) return 'text-orange-400 drop-shadow-[0_0_4px_rgba(251,146,60,0.5)]';
    return 'text-orange-400';
  };

  const getColdAura = (diff) => {
    const absDiff = Math.abs(diff);
    if (absDiff >= 20) return 'text-cyan-300 drop-shadow-[0_0_8px_rgba(103,232,249,0.9)] animate-pulse';
    if (absDiff >= 15) return 'text-cyan-300 drop-shadow-[0_0_6px_rgba(103,232,249,0.7)]';
    if (absDiff >= 10) return 'text-blue-300 drop-shadow-[0_0_4px_rgba(147,197,253,0.5)]';
    return 'text-blue-300';
  };

  // Hot/Cold indicator comparing 5-game to season overall
  const getHotColdIndicator = (player) => {
    const diff = Math.round(player.hot_overall || 0);
    const threshold = 5;
    
    if (diff >= threshold) {
      return (
        <span className={`${getHotAura(diff)}`} title={`5-game OVR is ${diff} higher than season`}>
          <span className="text-xs">+{diff}</span>🔥
        </span>
      );
    } else if (diff <= -threshold) {
      return (
        <span className={`${getColdAura(diff)}`} title={`5-game OVR is ${Math.abs(diff)} lower than season`}>
          <span className="text-xs">{diff}</span>❄️
        </span>
      );
    }
    return null;
  };

  // Hot/Cold indicator for FPts comparing 5-game to season
  const getFptsHotColdIndicator = (player) => {
    const diff = Math.round(player.hot_fpoints || 0);
    const threshold = 3;
    
    if (diff >= threshold) {
      return (
        <span className={`${getHotAura(diff)}`} title={`5-game FPts is ${diff} higher than season`}>
          <span className="text-xs">+{diff}</span>🔥
        </span>
      );
    } else if (diff <= -threshold) {
      return (
        <span className={`${getColdAura(diff)}`} title={`5-game FPts is ${Math.abs(diff)} lower than season`}>
          <span className="text-xs">{diff}</span>❄️
        </span>
      );
    }
    return null;
  };

  const getZScoreColor = (score) => {
    if (score > 55) {
      // Green spectrum with clear text
      if (score >= 90) return 'bg-green-500 text-white shadow-lg shadow-green-500/40';      // High intensity green with halo
      if (score >= 80) return 'bg-green-600 text-white shadow-md shadow-green-600/30';      // Medium-high intensity green with subtle halo
      if (score >= 70) return 'bg-green-700 text-white';      // Medium intensity green
      if (score >= 60) return 'bg-green-800 text-white';      // Medium-low intensity green
      return 'bg-green-900 text-white';                       // Very low intensity green
    } else if (score < 45) {
      // Red spectrum with clear text
      if (score <= 10) return 'bg-red-500 text-white shadow-lg shadow-red-500/40';           // High intensity red with halo
      if (score <= 20) return 'bg-red-600 text-white shadow-md shadow-red-600/30';          // Medium-high intensity red with subtle halo
      if (score <= 30) return 'bg-red-700 text-white';         // Medium intensity red
      if (score <= 40) return 'bg-red-800 text-white';         // Medium-low intensity red
      return 'bg-red-900 text-white';                          // Very low intensity red
    }
    // Score between 45-55 - default background
    return 'bg-gray-700 text-white';                           // Neutral gray
  };

  const handleSort = (key) => {
    let direction;
    
    if (sortConfig.key === key) {
      // If clicking the same column, cycle: current direction -> unsorted -> unsorted
      if (sortConfig.direction === null) {
        direction = null; // Stay unsorted
      } else {
        direction = null; // Go to unsorted
      }
    } else {
      // Always use DESC for all categories
      direction = 'desc';
    }
    
    setSortConfig({ key, direction });
  };

  // Helper function to get the correct z_score based on statType
  const getZScore = (player) => {
    const zScoreKey = statType === 'season' ? 'z_score_season' : 
                     statType === '5' ? 'z_score_5' : 
                     statType === '10' ? 'z_score_10' : 
                     'z_score_projected';
    return player[zScoreKey] !== undefined ? player[zScoreKey] : player.z_score;
  };

  // Helper function to get the correct overall_rank based on statType
  const getOverallRank = (player) => {
    const rankKey = statType === 'season' ? 'overall_rank_season' : 
                   statType === '5' ? 'overall_rank_5' : 
                   statType === '10' ? 'overall_rank_10' : 
                   'overall_rank_projected';
    return player[rankKey] !== undefined ? player[rankKey] : player.overall_rank;
  };

  const sortedPlayers = [...players].sort((a, b) => {
    // Always use custom rank if available for default sorting, otherwise original rank
    if (sortConfig.direction === null || sortConfig.key === 'overall_rank') {
      const aRank = customScores[a.name]?.custom_z_rank || getOverallRank(a) || 999;
      const bRank = customScores[b.name]?.custom_z_rank || getOverallRank(b) || 999;
      return aRank - bRank;
    }
    
    let aValue, bValue;
    
    // Handle special case for z_score - use custom score if available, otherwise use statType-based score
    if (sortConfig.key === 'z_score') {
      aValue = customScores[a.name]?.custom_z_score || getZScore(a);
      bValue = customScores[b.name]?.custom_z_score || getZScore(b);
    }
    // Handle nested stat properties like "stats.PTS.value"
    else if (sortConfig.key.startsWith('stats.')) {
      const parts = sortConfig.key.split('.');
      const category = parts[1];
      const stat = parts[2]; // 'value' or 'score'
      
      // Determine the key based on stat type
      const valueKey = statType === 'season' ? 'value_season' : 
                      statType === '5' ? 'value_5' : 
                      statType === '10' ? 'value_10' : 
                      statType === 'projected' ? 'value_projected' : 'value';
      const scoreKey = statType === 'season' ? 'score_season' : 
                      statType === '5' ? 'score_5' : 
                      statType === '10' ? 'score_10' : 
                      statType === 'projected' ? 'score_projected' : 'score';
      
      const key = stat === 'value' ? valueKey : (stat === 'score' ? scoreKey : parts[2]);
      
      aValue = a[parts[0]]?.[category]?.[key] ?? a[parts[0]]?.[category]?.[parts[2]];
      bValue = b[parts[0]]?.[category]?.[key] ?? b[parts[0]]?.[category]?.[parts[2]];
    } else {
      // Handle top-level properties
      aValue = a[sortConfig.key];
      bValue = b[sortConfig.key];
    }
    
    // Handle null/undefined values
    if (aValue == null && bValue == null) return 0;
    if (aValue == null) return sortConfig.direction === 'asc' ? 1 : -1;
    if (bValue == null) return sortConfig.direction === 'asc' ? -1 : 1;
    
    if (aValue < bValue) {
      return sortConfig.direction === 'asc' ? -1 : 1;
    }
    if (aValue > bValue) {
      return sortConfig.direction === 'asc' ? 1 : -1;
    }
    return 0;
  });

  const SortIcon = ({ columnKey }) => {
    if (sortConfig.key !== columnKey || sortConfig.direction === null) {
      return <span className="text-gray-400">↕</span>;
    }
    return sortConfig.direction === 'asc' ? <span className="text-white">↑</span> : <span className="text-white">↓</span>;
  };


  const getTeamBadgeColor = (teamId) => {
    const colors = [
      'bg-red-600', 'bg-blue-600', 'bg-green-600', 'bg-yellow-600',
      'bg-purple-600', 'bg-pink-600', 'bg-indigo-600', 'bg-orange-600',
      'bg-teal-600', 'bg-cyan-600', 'bg-emerald-600', 'bg-rose-600'
    ];
    return colors[teamId % colors.length];
  };

  return (
    <>
      <div className="overflow-x-auto hide-scrollbar">
        <table className="min-w-full divide-y divide-gray-700">
          <thead className="bg-gray-700">
            <tr>
              <th 
                className="table-header cursor-pointer hover:bg-gray-600 w-16 text-center"
                onClick={() => handleSort('overall_rank')}
              >
                <div className="flex items-center justify-center">
                  Rank <SortIcon columnKey="overall_rank" />
                </div>
              </th>
              <th 
                className="table-header cursor-pointer hover:bg-gray-600 w-20 text-left"
                onClick={() => handleSort('z_score')}
              >
                <div className="flex items-center">
                  OVR <SortIcon columnKey="z_score" />
                </div>
              </th>
              <th 
                className="table-header cursor-pointer hover:bg-gray-600 w-10 text-center px-1"
                onClick={() => handleSort('hot_overall')}
                title="OVR Trend (5-game vs season)"
              >
                <div className="flex items-center justify-center">
                  📈<SortIcon columnKey="hot_overall" />
                </div>
              </th>
              <th 
                className="table-header cursor-pointer hover:bg-gray-600 w-48"
                onClick={() => handleSort('name')}
              >
                <div className="flex items-center">
                  Player <SortIcon columnKey="name" />
                </div>
              </th>
              {config.show_auction_price && (
                <th 
                  className="table-header cursor-pointer hover:bg-gray-600 w-16"
                  onClick={() => handleSort('auction_value')}
                >
                  <div className="flex items-center">
                    Value <SortIcon columnKey="auction_value" />
                  </div>
                </th>
              )}
              <th 
                className="table-header cursor-pointer hover:bg-gray-600 w-20"
                onClick={() => handleSort('fpoints')}
              >
                <div className="flex items-center">
                  FPts <SortIcon columnKey="fpoints" />
                </div>
              </th>
              <th 
                className="table-header cursor-pointer hover:bg-gray-600 w-10 text-center px-1"
                onClick={() => handleSort('hot_fpoints')}
                title="FPts Trend (5-game vs season)"
              >
                <div className="flex items-center justify-center">
                  📈<SortIcon columnKey="hot_fpoints" />
                </div>
              </th>
              {CATEGORIES.map(category => {
                const isPunted = !includedCategories.includes(category);
                return (
                  <th 
                    key={category}
                    className={`table-header w-24 ${isPunted ? 'opacity-40' : ''}`}
                  >
                    <div className="flex items-center justify-center space-x-1">
                      <input
                        type="checkbox"
                        checked={includedCategories.includes(category)}
                        onChange={() => handleCategoryInclusionChange(category)}
                        className="h-3 w-3 text-nba-orange focus:ring-nba-orange border-gray-500 rounded bg-gray-600"
                      />
                      <div 
                        className="flex items-center cursor-pointer hover:bg-gray-600 px-2 py-1 rounded"
                        onClick={() => handleSort(`stats.${category}.value`)}
                      >
                        {CATEGORY_NAMES[category]} <SortIcon columnKey={`stats.${category}.value`} />
                      </div>
                    </div>
                  </th>
                );
              })}
              <th className="table-header w-12">GP</th>
              <th className="table-header w-24">Status</th>
              <th className="table-header w-20">Actions</th>
            </tr>
          </thead>
          <tbody className="bg-gray-800 divide-y divide-gray-700">
            {sortedPlayers.map((player, index) => (
              <tr 
                key={player.name} 
                className={`hover:bg-gray-700 transition-colors relative ${
                  player.drafted ? 'drafted-row' : ''
                } ${
                  player.fantasy_team?.abbreviation && player.fantasy_team.abbreviation !== config?.MY_TEAM_ABV ? 'opacity-40' : ''
                } ${
                  player.fantasy_team?.abbreviation === config?.MY_TEAM_ABV 
                    ? 'bg-gradient-to-r from-nba-orange/10 via-nba-orange/5 to-transparent shadow-[0_0_8px_rgba(251,146,60,0.25)] ring-1 ring-nba-orange/30' 
                    : ''
                }`}
              >
                <td className="table-cell text-center">
                  <div className="flex items-center justify-center">
                    {getCustomRankDisplay(player.name, getOverallRank(player))}
                    {loadingCustomScores && (
                      <div className="animate-spin rounded-full h-3 w-3 border-b-2 border-nba-orange ml-2"></div>
                    )}
                  </div>
                </td>
                <td className="table-cell text-left">
                  <div className="flex items-center">
                    {getCustomScoreDisplay(player.name, getZScore(player))}
                  </div>
                </td>
                <td className="table-cell text-center px-1">
                  {getHotColdIndicator(player)}
                </td>
                <td className="table-cell">
                  <div>
                    <div className="flex items-center space-x-2">
                      <span className="font-medium text-white">{player.name}</span>
                      {player.is_injured && (
                        <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold bg-red-600 text-white">
                          INJ
                        </span>
                      )}
                    </div>
                    <div className="text-xs text-gray-400">
                      {player.position} | {player.team_abv || 'N/A'}
                      {player.current_week_games !== undefined && player.current_week_start && (
                        <>
                          {' | '}
                          <span className="text-gray-300">
                            {player.current_week_games} GP
                          </span>
                          <span className="text-gray-500">
                            {' '}({formatWeekDate(player.current_week_start)})
                          </span>
                        </>
                      )}
                      {player.next_week_games !== undefined && player.next_week_start && (
                        <>
                          {' | '}
                          <span className="text-gray-300">
                            {player.next_week_games} GP
                          </span>
                          <span className="text-gray-500">
                            {' '}({formatWeekDate(player.next_week_start)})
                          </span>
                        </>
                      )}
                    </div>
                  </div>
                </td>
                {config.show_auction_price && (
                  <td className="table-cell text-gray-300 font-medium">
                    ${getAuctionValue(player.name, player.auction_value)}
                  </td>
                )}
                <td className="table-cell text-center">
                  <div className="flex items-center justify-center space-x-2">
                    <span className="text-blue-400 font-semibold">
                      {player.fpoints ? player.fpoints.toFixed(1) : '0.0'}
                    </span>
                    <span className="text-xs text-gray-400">
                      (#{player.fpoints_rank || '-'})
                    </span>
                  </div>
                </td>
                <td className="table-cell text-center px-1">
                  {getFptsHotColdIndicator(player)}
                </td>
                {CATEGORIES.map(category => {
                  const stat = player.stats[category];
                  const isPunted = !includedCategories.includes(category);
                  
                  if (!stat) return (
                    <td key={category} className={`table-cell text-gray-500 ${isPunted ? 'opacity-40' : ''}`}>
                      -
                    </td>
                  );
                  
                  // Get value and score based on selected stat type
                  const valueKey = statType === 'season' ? 'value_season' : 
                                  statType === '5' ? 'value_5' : 
                                  statType === '10' ? 'value_10' : 
                                  'value_projected';
                  const scoreKey = statType === 'season' ? 'score_season' : 
                                  statType === '5' ? 'score_5' : 
                                  statType === '10' ? 'score_10' : 
                                  'score_projected';
                  
                  const displayValue = stat[valueKey] !== undefined ? stat[valueKey] : stat.value;
                  const displayScore = stat[scoreKey] !== undefined ? stat[scoreKey] : stat.score;
                  
                  return (
                    <td key={category} className={`table-cell ${isPunted ? 'opacity-40' : ''}`}>
                      <div className={`px-2 py-1 rounded border ${getScoreBgColor(displayScore, stat.is_inverse)}`}>
                        <div className="flex items-center justify-between">
                          <div className="flex items-center space-x-2">
                            <span className="text-xs text-gray-400 opacity-60 font-medium">
                              {CATEGORY_NAMES[category]}:
                            </span>
                            <span className={`text-sm font-bold ${getStatTextColor(displayScore, stat.is_inverse)}`}>
                              {category === 'PLUS_MINUS' && displayValue > 0 ? '+' : ''}{displayValue}{PERCENTAGE_CATEGORIES.includes(category) ? '%' : ''}
                            </span>
                          </div>
                          <span className={`text-xs opacity-75 ${getScoreColor(displayScore, stat.is_inverse)} ml-2`}>
                            ({displayScore})
                          </span>
                        </div>
                      </div>
                    </td>
                  );
                })}
                <td className="table-cell text-gray-300">{player.games_played}</td>
                <td className="table-cell">
                  {player.drafted ? (
                    <div className="flex items-center">
                      <span className={`team-badge text-white ${getTeamBadgeColor(player.fantasy_team?.id || 0)}`}>
                        {player.fantasy_team?.abbreviation || player.fantasy_team?.name || 'Unknown'}
                      </span>
                    </div>
                  ) : (
                    <span className="text-green-400 font-medium">Available</span>
                  )}
                </td>
                <td className="table-cell">
                  <button
                    onClick={() => setDraftModalPlayer(player)}
                    className="btn-primary text-xs"
                    disabled={fantasyTeams.length === 0}
                  >
                    Edit
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      
      {draftModalPlayer && (
        <DraftModal
          player={draftModalPlayer}
          teams={fantasyTeams}
          onClose={() => setDraftModalPlayer(null)}
          onDraft={onDraftPlayer}
          onUndraft={onUndraftPlayer}
          onUpdatePlayer={onUpdatePlayer}
          isDrafted={draftModalPlayer.drafted}
        />
      )}
    </>
  );
};

export default PlayerTable;
