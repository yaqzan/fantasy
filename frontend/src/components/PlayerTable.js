import React, { useState, useEffect } from 'react';
import DraftModal from './DraftModal';
import { calculateCustomZScores, calculateCustomAuctionValues } from '../services/api';
import { weekRange } from '../weeks';
import { bidColor } from '../bidColor';

// API field suffix for each stats choice ('proj' = this season's projection).
const PERIOD_SUFFIX = { season: '_season', '5': '_5', '10': '_10', projected: '_projected', proj: '_proj' };

// priceExponent: null means the league's own draft.price_exponent (the server's default values).
// punts: categories left out of value (the tab's view state), changed through onPuntsChange.
// draftMode: before the league's draft, hide in-season columns (trends).
// draftPlan: the Draft Day data (/api/draft-day) when it belongs to this league: adds Likely $ and
// Max bid, the max following the Value column (share of it by price band, stars at break-even).
const PlayerTable = ({ players, fantasyTeams, onDraftPlayer, onUndraftPlayer, onUpdatePlayer, priceExponent = null, config, statType = 'projected', punts: puntCategories = [], onPuntsChange, draftMode = false, draftPlan = null }) => {
  // The league's categories, in display order, with labels and percent/inverse flags.
  const categoryMeta = config?.categories || [];
  const CATEGORIES = categoryMeta.map(c => c.key);
  const CATEGORY_NAMES = Object.fromEntries(categoryMeta.map(c => [c.key, c.label]));
  const PERCENTAGE_CATEGORIES = categoryMeta.filter(c => c.percent).map(c => c.key);
  const caps = config?.capabilities || {};
  // Snake and offline drafts: the round a player's rank goes in, from the team count.
  const numTeams = config?.league?.settings?.num_teams || 1;
  const [sortConfig, setSortConfig] = useState({ key: 'overall_rank', direction: 'asc' });
  const [draftModalPlayer, setDraftModalPlayer] = useState(null);
  const includedCategories = CATEGORIES.filter(c => !puntCategories.includes(c));
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

  // Punted scores are per timeframe: fetched for the punts (restored ones too) and the timeframe.
  const puntKey = puntCategories.join(',');
  useEffect(() => {
    if (puntCategories.length === 0) {
      setCustomScores({});
      return;
    }
    let cancelled = false;
    setLoadingCustomScores(true);
    calculateCustomZScores(puntCategories, statType)
      .then(response => { if (!cancelled) setCustomScores(response.custom_scores); })
      .catch(error => console.error('Error calculating custom z-scores:', error))
      .finally(() => { if (!cancelled) setLoadingCustomScores(false); });
    return () => { cancelled = true; };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [puntKey, statType]);

  // Force re-sort when statType changes to update OVR and rankings
  useEffect(() => {
    // Trigger a re-sort by updating the sort config
    setSortConfig(prev => ({ ...prev }));
  }, [statType]);

  // Auction values follow the star-premium slider and the punted categories; with neither
  // changed, the server's values (the league's own exponent, nothing punted) stand.
  useEffect(() => {
    if (priceExponent === null && puntCategories.length === 0) {
      setCustomAuctionValues({});
      return;
    }
    let cancelled = false;
    setLoadingAuctionValues(true);
    calculateCustomAuctionValues(priceExponent, puntCategories, statType)
      .then(response => { if (!cancelled) setCustomAuctionValues(response.auction_values || {}); })
      .catch(error => {
        console.error('Error calculating custom auction values:', error);
        if (!cancelled) setCustomAuctionValues({});
      })
      .finally(() => { if (!cancelled) setLoadingAuctionValues(false); });
    return () => { cancelled = true; };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [priceExponent, puntKey, statType]);

  // The field for the selected stats: periodKey('z_score') -> 'z_score_season' etc.
  const periodKey = (base) => `${base}${PERIOD_SUFFIX[statType] || '_projected'}`;

  // Auction value on the same stats as the rank (custom slider/punt values when set)
  const getAuctionValue = (player) => {
    return customAuctionValues[player.name]?.auction_value || (player[periodKey('auction_value')] ?? player.auction_value);
  };

  const likelyPrice = (player) => draftPlan?.likely?.[player.name] ?? null;
  const maxBid = (player) => {
    if (!draftPlan) return null;
    const star = draftPlan.rule.stars[player.name];
    if (star != null) return star;
    return shareMax(getAuctionValue(player) || 1);
  };
  // A max bid from an app $ by the Draft Day share rule (non-stars).
  const shareMax = (value) => {
    const [, share] = draftPlan.rule.shares.find(([floor]) => value >= floor) || [0, 1];
    return Math.max(1, Math.round(value * share));
  };

  // Unchecking a category punts it (the scores refetch through the effect above)
  const handleCategoryInclusionChange = (category) => onPuntsChange?.(puntCategories.includes(category)
    ? puntCategories.filter(c => c !== category) : [...puntCategories, category]);

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
    const zScoreKey = periodKey('z_score');
    return player[zScoreKey] !== undefined ? player[zScoreKey] : player.z_score;
  };

  // Helper function to get the correct overall_rank based on statType
  const getOverallRank = (player) => {
    const rankKey = periodKey('overall_rank');
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
    else if (sortConfig.key === 'auction_value') {
      aValue = getAuctionValue(a);
      bValue = getAuctionValue(b);
    }
    else if (sortConfig.key === 'max_bid') {
      aValue = maxBid(a) ?? 0;
      bValue = maxBid(b) ?? 0;
    }
    else if (sortConfig.key === 'likely') {
      aValue = likelyPrice(a) ?? 0;
      bValue = likelyPrice(b) ?? 0;
    }
    // Handle nested stat properties like "stats.PTS.value"
    else if (sortConfig.key.startsWith('stats.')) {
      const parts = sortConfig.key.split('.');
      const category = parts[1];
      const stat = parts[2]; // 'value' or 'score'
      
      // Determine the key based on stat type
      const valueKey = periodKey('value');
      const scoreKey = periodKey('score');
      
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
              {!draftMode && <th 
                className="table-header cursor-pointer hover:bg-gray-600 w-10 text-center px-1"
                onClick={() => handleSort('hot_overall')}
                title="OVR Trend (5-game vs season)"
              >
                <div className="flex items-center justify-center">
                  📈<SortIcon columnKey="hot_overall" />
                </div>
              </th>}
              <th 
                className="table-header cursor-pointer hover:bg-gray-600 w-48"
                onClick={() => handleSort('name')}
              >
                <div className="flex items-center">
                  Player <SortIcon columnKey="name" />
                </div>
              </th>
              {caps.auction ? (
                <th
                  className="table-header cursor-pointer hover:bg-gray-600 w-16"
                  onClick={() => handleSort('auction_value')}
                >
                  <div className="flex items-center">
                    Value <SortIcon columnKey="auction_value" />
                  </div>
                </th>
              ) : (
                <th className="table-header w-12" title={`The draft round his rank goes in (${numTeams} teams)`}>Rd</th>
              )}
              {draftPlan && (
                <>
                  <th className="table-header cursor-pointer hover:bg-gray-600 w-16" onClick={() => handleSort('likely')}
                      title="What this room paid for his likely bid rank in 2025 (a guess: misses by $13-16 on $20+ players)">
                    <div className="flex items-center">Likely <SortIcon columnKey="likely" /></div>
                  </th>
                  <th className="table-header cursor-pointer hover:bg-gray-600 w-16" onClick={() => handleSort('max_bid')}
                      title="Don't bid past this. 85% of Value at $40+, 80% at $15-39, Value under $15; stars at their break-even. Green: the room will likely let him go at or under it.">
                    <div className="flex items-center">Max bid <SortIcon columnKey="max_bid" /></div>
                  </th>
                </>
              )}
              {CATEGORIES.map(category => {
                const isPunted = !includedCategories.includes(category);
                return (
                  <th 
                    key={category}
                    className={`table-header w-24 ${isPunted ? 'opacity-40' : ''}`}
                  >
                    <div className="flex items-center justify-center space-x-1">
                      {caps.punts && (
                        <input
                          type="checkbox"
                          checked={includedCategories.includes(category)}
                          onChange={() => handleCategoryInclusionChange(category)}
                          title="Uncheck to punt: leave it out of value"
                          className="h-3 w-3 text-nba-orange focus:ring-nba-orange border-gray-500 rounded bg-gray-600"
                        />
                      )}
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
                {!draftMode && <td className="table-cell text-center px-1">
                  {getHotColdIndicator(player)}
                </td>}
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
                      {player.positions?.length ? player.positions.join('/') : player.position} | {player.team_abv || 'N/A'}
                      {[config.current_week, config.next_week].map((week, i) => week && player[i ? 'next_week_games' : 'current_week_games'] !== undefined && (
                        <React.Fragment key={i}>
                          {' | '}
                          <span className="text-gray-300">{player[i ? 'next_week_games' : 'current_week_games']} GP</span>
                          <span className="text-gray-500"> ({weekRange(week)})</span>
                        </React.Fragment>
                      ))}
                    </div>
                  </div>
                </td>
                {caps.auction ? (
                  <td className="table-cell text-gray-300 font-medium">
                    ${getAuctionValue(player)}
                  </td>
                ) : (
                  <td className="table-cell text-gray-400">
                    {Math.ceil((customScores[player.name]?.custom_z_rank || getOverallRank(player) || 0) / numTeams) || '-'}
                  </td>
                )}
                {draftPlan && (() => {
                  const likely = likelyPrice(player);
                  const max = maxBid(player);
                  return (
                    <>
                      <td className="table-cell text-gray-400">{likely != null ? `$${likely}` : '-'}</td>
                      <td className="table-cell font-semibold" style={{ color: bidColor(max, likely) }}
                          title={likely != null ? `Room's likely price $${likely}: ${max >= likely ? `$${max - likely} under your max` : `$${likely - max} over your max`}` : undefined}>
                        ${max}
                        {player.year3 && draftPlan.rule.stars[player.name] == null && (
                          <span className="relative group ml-0.5 align-super text-[10px] font-bold text-sky-400 cursor-help">
                            Y3
                            {/* Third-year what-ifs: max with the average third-year miss added back, and after a breakout */}
                            <span className="hidden group-hover:flex absolute right-0 top-full z-30 mt-1 gap-2 whitespace-nowrap rounded border border-gray-600 bg-gray-900 px-2 py-1 text-sm font-semibold shadow-lg">
                              <span className="text-sky-300" aria-label="Max with the average third-year correction">📈 ${shareMax(player.year3.corrected)}</span>
                              <span className="text-green-400" aria-label="Max if he breaks out">🚀 ${shareMax(player.year3.breakout)}</span>
                            </span>
                          </span>
                        )}
                      </td>
                    </>
                  );
                })()}
                {CATEGORIES.map(category => {
                  const stat = player.stats[category];
                  const isPunted = !includedCategories.includes(category);
                  
                  if (!stat) return (
                    <td key={category} className={`table-cell text-gray-500 ${isPunted ? 'opacity-40' : ''}`}>
                      -
                    </td>
                  );
                  
                  // Get value and score based on selected stat type
                  const valueKey = periodKey('value');
                  const scoreKey = periodKey('score');
                  
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
                <td className="table-cell text-gray-300">
                  {player.projected_only ? (
                    <span className="text-sky-400" title="No NBA games last season (rookie, or out all year): valued on his projection only">
                      new
                    </span>
                  ) : player.small_sample ? (
                    <span className="text-amber-400" title={`Small sample: only ${player.games_played} games, so his numbers may not hold`}>
                      {player.games_played}⚠
                    </span>
                  ) : player.games_played}
                </td>
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
                    onClick={() => setDraftModalPlayer({
                      ...player,
                      overall_rank: customScores[player.name]?.custom_z_rank || getOverallRank(player),
                      auction_value: getAuctionValue(player),
                    })}
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
