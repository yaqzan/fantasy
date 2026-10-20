import React, { useState } from 'react';
import DraftModal from './DraftModal';
import { PlayerName } from './PlayerCard';
import usePlayerValues from '../usePlayerValues';
import { weekRange } from '../weeks';
import OwnerChip from './OwnerChip';
import { orderColumns } from '../dailyLeaders';

// The in-season player table (draft mode renders DraftBoard instead).
// priceExponent: null means the league's own draft.price_exponent (the server's default values).
// punts: categories left out of value (the tab's view state), changed through onPuntsChange.
// Pinned Player column: the same width as Daily Leaders' so the two tabs line up.
const PLAYER_W = 'w-[10.375rem] min-w-[10.375rem] max-w-[10.375rem] sm:w-60 sm:min-w-[15rem] sm:max-w-[15rem]';

const PlayerTable = ({ players, fantasyTeams, onDraftPlayer, onUndraftPlayer, onUpdatePlayer, priceExponent = null, config, statType = 'projected', punts: puntCategories = [], onPuntsChange }) => {
  // The league's categories, in display order, with labels and percent/inverse flags.
  const categoryMeta = config?.categories || [];
  const CATEGORIES = orderColumns(categoryMeta).map(c => c.key); // Daily Leaders' column order
  const CATEGORY_NAMES = Object.fromEntries(categoryMeta.map(c => [c.key, c.label]));
  const CATEGORY_FULL = Object.fromEntries(categoryMeta.map(c => [c.key, c.name || c.label]));
  const PERCENTAGE_CATEGORIES = categoryMeta.filter(c => c.percent).map(c => c.key);
  const caps = config?.capabilities || {};
  const [sortConfig, setSortConfig] = useState({ key: 'overall_rank', direction: 'asc' });
  const [draftModalPlayer, setDraftModalPlayer] = useState(null);
  const includedCategories = CATEGORIES.filter(c => !puntCategories.includes(c));
  const { customScores, loadingCustomScores, periodKey, getAuctionValue, getZScore, getOverallRank } =
    usePlayerValues({ punts: puntCategories, statType, priceExponent });

  // Unchecking a category punts it (the scores refetch through the effect above)
  const handleCategoryInclusionChange = (category) => onPuntsChange?.(puntCategories.includes(category)
    ? puntCategories.filter(c => c !== category) : [...puntCategories, category]);

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

  // Preseason-adjusted view: how far his preseason games moved his OVR off the projection.
  const getPreIndicator = (player) => {
    const d = player.pre_trend;
    if (d === null || d === undefined) return <span className="text-[11px] text-gray-500" title="No preseason games">–</span>;
    const r = Math.round(d);
    const title = `${player.preseason_games} preseason games, ${player.preseason_minutes} min: OVR ${r > 0 ? '+' : ''}${r} vs the projection (rank ${player.overall_rank_proj} → ${player.overall_rank_pre})`;
    if (r === 0) return <span className="text-[11px] text-gray-500" title={title}>±0</span>;
    return <span className={`text-xs font-semibold ${r > 0 ? 'text-green-400' : 'text-red-400'}`} title={title}>{r > 0 ? '▲' : '▼'}{Math.abs(r)}</span>;
  };
  const preView = statType === 'pre';

  const handleSort = (key) => {
    let direction;
    
    if (sortConfig.key === key) {
      // If clicking the same column, cycle: current direction -> unsorted -> unsorted
      // (the preseason trend goes risers -> fallers -> unsorted)
      if (key === 'pre_trend' && sortConfig.direction === 'desc') {
        direction = 'asc';
      } else if (sortConfig.direction === null) {
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
    
    // Handle null/undefined values (players with no preseason games sit below risers and fallers alike)
    if (aValue == null && bValue == null) return 0;
    if (sortConfig.key === 'pre_trend' && (aValue == null || bValue == null)) return aValue == null ? 1 : -1;
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


  return (
    <>
      {/* Same geometry as the Daily Leaders table (card, pinned 15rem Player column with rank + name, 4rem
          column, then stats) so switching tabs does not move anything. */}
      <div className="overflow-x-auto bg-gray-800 rounded-lg shadow-xl">
        <table className="min-w-full text-xs sm:text-sm">
          <thead>
            <tr>
              <th className={`table-header sticky left-0 z-20 px-2 ${PLAYER_W}`}>
                <div className="flex items-center gap-1.5">
                  <span className="w-5 text-right cursor-pointer hover:text-white" onClick={() => handleSort('overall_rank')} title="Sort by rank">#<SortIcon columnKey="overall_rank" /></span>
                  <span className="cursor-pointer hover:text-white" onClick={() => handleSort('name')}>Player <SortIcon columnKey="name" /></span>
                </div>
              </th>
              <th className={`table-header text-center px-0.5 border-r border-gray-700 cursor-pointer hover:text-white whitespace-nowrap ${caps.scoring === 'points' ? 'sm:w-20 sm:min-w-[5rem]' : 'sm:w-16 sm:min-w-[4rem]'}`}
                  onClick={() => handleSort('z_score')} title="Overall rating (0-100): how he scores across your league's categories. Click to sort.">
                OVR <SortIcon columnKey="z_score" />
              </th>
              {CATEGORIES.map(category => {
                const isPunted = !includedCategories.includes(category);
                return (
                  <th
                    key={category}
                    className={`table-header !px-1 whitespace-nowrap ${isPunted ? 'opacity-40' : ''}`}
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
                        className="flex items-center whitespace-nowrap cursor-pointer hover:bg-gray-600 px-1 rounded"
                        title={`${CATEGORY_FULL[category]} (click to sort)`}
                        onClick={() => handleSort(`stats.${category}.value`)}
                      >
                        {CATEGORY_NAMES[category]} <SortIcon columnKey={`stats.${category}.value`} />
                      </div>
                    </div>
                  </th>
                );
              })}
              <th className="table-header w-12" title="Games he has played this season">GP</th>
              <th className="table-header w-16"></th>
            </tr>
          </thead>
          <tbody>
            {sortedPlayers.map((player) => {
              const mine = player.fantasy_team?.abbreviation === config?.MY_TEAM_ABV;
              const taken = player.fantasy_team?.abbreviation && !mine;
              const bg = mine ? 'bg-row-mine' : 'bg-gray-800 group-hover:bg-row-hover';
              const fade = taken ? 'opacity-40' : '';
              const rank = customScores[player.name]?.custom_z_rank || getOverallRank(player);
              const weeks = [config.current_week, config.next_week].map((week, i) => week && player[i ? 'next_week_games' : 'current_week_games'] !== undefined
                ? { n: player[i ? 'next_week_games' : 'current_week_games'], range: weekRange(week) } : null).filter(Boolean);
              return (
              <tr key={player.name} className={`group border-t border-gray-700 ${player.drafted ? 'drafted-row' : ''}`}>
                <td className={`sticky left-0 z-10 px-2 py-1.5 ${PLAYER_W} ${bg} ${mine ? 'shadow-[inset_3px_0_0_rgb(var(--mine))]' : ''}`}>
                  <div className={`flex items-center gap-1.5 ${fade}`}>
                    <div className="w-5 shrink-0 flex flex-col items-center gap-0.5">
                      <span className="text-gray-500 tabular-nums text-[11px] leading-none"
                            title={customScores[player.name] ? `Rank ${rank} with your punts (was ${getOverallRank(player)})` : undefined}>
                        {loadingCustomScores ? '…' : rank}
                      </span>
                      {taken && <OwnerChip person={player.fantasy_team.owner_name} team={player.fantasy_team.name} />}
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-1 min-w-0">
                        <PlayerName id={player.id} name={player.name} className={`font-medium truncate min-w-0 ${mine ? 'text-mine' : 'text-white'}`} />
                        <span className="shrink-0 text-[11px]">{preView ? getPreIndicator(player) : getHotColdIndicator(player)}</span>
                      </div>
                      <div className="text-[11px] text-gray-400 flex items-center gap-1 whitespace-nowrap overflow-hidden">
                        <span>{player.positions?.length ? player.positions.join('/') : player.position} · {player.team_abv || 'N/A'}</span>
                        {weeks.length > 0 && (
                          <span className="text-gray-300" title={weeks.map(w => `${w.n} games ${w.range}`).join(' · ')}>
                            · {weeks.map(w => w.n).join(' + ')} GP
                          </span>
                        )}
                        {player.is_injured && (
                          <span className="inline-flex items-center px-1.5 py-px rounded-full text-[10px] leading-tight font-semibold bg-red-600 text-white whitespace-nowrap"
                                title={`INJ${player.injured_return ? ` - ${player.injured_return}` : ''}${player.injured_games ? ` (${player.injured_games} missed)` : ''}`}>
                            INJ{player.injured_games ? ` ${player.injured_games}` : ''}
                          </span>
                        )}
                      </div>
                    </div>
                  </div>
                </td>
                <td className={`text-center px-0.5 whitespace-nowrap border-r border-gray-700 tabular-nums font-medium text-gray-200 ${bg}`}>
                  <span className={fade}>{Math.round(customScores[player.name]?.custom_z_score ?? getZScore(player))}</span>
                </td>
                {CATEGORIES.map(category => {
                  const stat = player.stats[category];
                  const isPunted = !includedCategories.includes(category);

                  if (!stat) return (
                    <td key={category} className={`text-center text-gray-500 ${isPunted ? 'opacity-40' : ''}`}>
                      -
                    </td>
                  );

                  // Get value and score based on selected stat type
                  const valueKey = periodKey('value');
                  const scoreKey = periodKey('score');

                  const displayValue = stat[valueKey] !== undefined ? stat[valueKey] : stat.value;
                  const displayScore = stat[scoreKey] !== undefined ? stat[scoreKey] : stat.score;

                  // Condensed card: the stat's name is in the header, so the cell is just value + percentile.
                  return (
                    <td key={category} className={`px-1 py-1 ${isPunted || taken ? 'opacity-40' : ''}`}
                        title={`${CATEGORY_FULL[category]}: percentile ${displayScore}`}>
                      <div className={`px-1.5 py-0.5 rounded border ${getScoreBgColor(displayScore, stat.is_inverse)}`}>
                        <div className="flex items-center justify-between gap-1.5 leading-tight">
                          <span className={`text-sm font-bold tabular-nums ${getStatTextColor(displayScore, stat.is_inverse)}`}>
                            {category === 'PLUS_MINUS' && displayValue > 0 ? '+' : ''}{displayValue}{PERCENTAGE_CATEGORIES.includes(category) ? '%' : ''}
                          </span>
                          <span className={`text-[11px] opacity-75 tabular-nums ${getScoreColor(displayScore, stat.is_inverse)}`}>
                            {displayScore}
                          </span>
                        </div>
                      </div>
                    </td>
                  );
                })}
                <td className={`text-center text-gray-300 ${fade}`}>
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
                <td className="text-center px-1">
                  <button
                    onClick={() => setDraftModalPlayer({
                      ...player,
                      overall_rank: customScores[player.name]?.custom_z_rank || getOverallRank(player),
                      auction_value: getAuctionValue(player),
                    })}
                    className="btn-primary text-xs !py-0.5 !px-2"
                    disabled={fantasyTeams.length === 0}
                  >
                    Edit
                  </button>
                </td>
              </tr>
              );
            })}
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
