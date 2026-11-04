import React, { useState } from 'react';
import { PlayerName } from './PlayerCard';
import usePlayerValues from '../usePlayerValues';
import { weekRange } from '../weeks';
import OwnerChip from './OwnerChip';
import { orderColumns, zAura } from '../dailyLeaders';

// The in-season player table (draft mode renders DraftBoard instead).
// priceExponent: null means the league's own draft.price_exponent (the server's default values).
// punts: categories left out of value (the tab's view state), changed through onPuntsChange.
// Pinned Player column: the same width as Daily Leaders' so the two tabs line up.
// Phones: each stat column is a fifth of what the Player column leaves (screen - 1rem page padding - pinned column), so exactly five show.
const STAT_W = 'w-[calc((100vw-11.375rem)/5)] min-w-[calc((100vw-11.375rem)/5)] max-w-[calc((100vw-11.375rem)/5)] sm:w-auto sm:min-w-0 sm:max-w-none';
// Percentile (0-100) as the z it stands for, so the cells reuse Daily Leaders' tint: 50 -> 0, 84 -> 1, 98 -> 2 SD.
const percentileZ = (score) => {
  const q = Math.min(0.995, Math.max(0.005, score / 100)), t = Math.sqrt(-2 * Math.log(Math.min(q, 1 - q)));
  const z = t - (2.515517 + 0.802853 * t + 0.010328 * t * t) / (1 + 1.432788 * t + 0.189269 * t * t + 0.001308 * t ** 3);
  return q < 0.5 ? -z : z;
};
// Points leagues: columns after FPTS. 'Vs proj' = this season's average against the preseason projection; L5/L10 the recent averages.
const RECENT = [['5', 'L5', 'Last 5 games'], ['10', 'L10', 'Last 10 games']];  // [n, label, title]; sorts on stats.FPTS.value_<n>
const RECENT_DELTA_PER_SD = 4;   // FPTS a game that a recent average may sit from the season average per aura SD
const deltaClass = (d) => d >= 3 ? 'text-green-400' : d >= 1 ? 'text-green-300' : d <= -3 ? 'text-red-400' : d <= -1 ? 'text-orange-300' : 'text-gray-400';
// This season's FPTS a game minus the preseason projection (null until both exist): the Δ column and its sort.
const fptsDelta = (p) => {
  const f = p.stats?.FPTS || {};
  return f.value_proj && f.value_season ? f.value_season - f.value_proj : null;
};
// Rotation model (nba_rotation.py + role_minutes.py): tonight's minutes if he plays (mif), the change from teammates
// who are out or back against what his projection carries (opp, the optimizer's factor), why (one line), his chance
// of playing (p). Points leagues: fpts = expected FPTS tonight if he plays, gain = vs his projection. Only players
// whose team has a posted lineup carry one. rotation_opp / rotation_tonight sort them.
const RISK_P = 0.6;
const rotOpp = (p) => (p.rotation && !p.rotation.inactive && p.rotation.opp != null ? p.rotation.opp : null);
const rotTonight = (p) => (p.rotation && !p.rotation.inactive && p.rotation.fpts != null ? p.rotation.fpts * p.rotation.p : null);
const rotTip = (player, points) => {
  const r = player.rotation;
  if (!r) return undefined;
  if (r.inactive) return 'Inactive tonight on the NBA lineup sheet';
  const l10 = player.stats?.FPTS?.value_10;
  // FPTS: the server's figure (projected FPTS x tonight's minutes factor) when there is one, else the extra minutes at his last-10 rate.
  const gain = r.gain != null ? r.gain : (points && l10 && r.base ? l10 / r.base * r.opp : null);
  const fpts = gain != null && Math.abs(gain) >= 0.5 ? ` (about ${gain >= 0 ? '+' : ''}${gain.toFixed(1)} FPTS${r.fpts != null ? `, ${r.fpts} expected if he plays` : ''})` : '';
  return [`${r.mif} min if he plays (usual ${r.base}); ${Math.round(r.p * 100)}% to play${r.confirmed ? ', lineup confirmed' : ', lineup expected, not confirmed'}`,
    r.why || null,
    r.opp || fpts ? `${r.opp > 0 ? '+' : ''}${r.opp} min against his projection${fpts}` : null,
    r.promoted ? 'Starting tonight, not his usual role' : null].filter(Boolean).join('. ');
};
// Rest of season (player_stats._rest_of_season): his projection x the games he is expected to play from here.
// ros_rank orders it (points: total FPTS; categories: z over the scaling pool's edge x games).
const rosTip = (p, points) => p.ros_rank == null ? undefined :
  `Rest of season #${p.ros_rank}: ${points && p.ros_fpts != null ? `${p.ros_fpts} FPTS` : `${p.ros_value} (z over the pool edge x games)`}. ` +
  `${p.ros_games} games, ${p.ros_min} min expected`;
const PLAYER_W ='w-[10.375rem] min-w-[10.375rem] max-w-[10.375rem] sm:w-60 sm:min-w-[15rem] sm:max-w-[15rem]';

const PlayerTable = ({ players, fantasyTeams, onDraftPlayer, onUndraftPlayer, priceExponent = null, config, statType = 'projected', punts: puntCategories = [], onPuntsChange }) => {
  // The league's categories, in display order, with labels and percent/inverse flags.
  const categoryMeta = config?.categories || [];
  const CATEGORIES = orderColumns(categoryMeta).map(c => c.key); // Daily Leaders' column order
  const CATEGORY_NAMES = Object.fromEntries(categoryMeta.map(c => [c.key, c.label]));
  const CATEGORY_FULL = Object.fromEntries(categoryMeta.map(c => [c.key, c.name || c.label]));
  const PERCENTAGE_CATEGORIES = categoryMeta.filter(c => c.percent).map(c => c.key);
  const caps = config?.capabilities || {};
  const points = caps.scoring === 'points' && CATEGORIES.includes('FPTS');
  const rotationOn = players.some(p => p.rotation);
  const rosOn = players.some(p => p.ros_rank != null);
  const [sortConfig, setSortConfig] = useState({ key: 'overall_rank', direction: 'asc' });
  const includedCategories = CATEGORIES.filter(c => !puntCategories.includes(c));
  const { customScores, loadingCustomScores, periodKey, getAuctionValue, getZScore, getOverallRank } =
    usePlayerValues({ punts: puntCategories, statType, priceExponent });

  // Unchecking a category punts it (the scores refetch through the effect above)
  const handleCategoryInclusionChange = (category) => onPuntsChange?.(puntCategories.includes(category)
    ? puntCategories.filter(c => c !== category) : [...puntCategories, category]);

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
    else if (sortConfig.key === 'fpts_delta') {
      aValue = fptsDelta(a);
      bValue = fptsDelta(b);
    }
    else if (sortConfig.key === 'rotation_opp') {
      aValue = rotOpp(a);
      bValue = rotOpp(b);
      if ((aValue == null) !== (bValue == null)) return aValue == null ? 1 : -1;  // no lineup yet: last either way
    }
    else if (sortConfig.key === 'rotation_tonight') {
      aValue = rotTonight(a);
      bValue = rotTonight(b);
      if ((aValue == null) !== (bValue == null)) return aValue == null ? 1 : -1;
    }
    else if (sortConfig.key === 'ros_value') {
      aValue = a.ros_rank == null ? null : -a.ros_rank;   // the rank breaks ties below the pool edge (value 0)
      bValue = b.ros_rank == null ? null : -b.ros_rank;
      if ((aValue == null) !== (bValue == null)) return aValue == null ? 1 : -1;
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
              <th className={`table-header hidden sm:table-cell text-center px-0.5 border-r border-gray-700 cursor-pointer hover:text-white whitespace-nowrap ${caps.scoring === 'points' ? 'sm:w-20 sm:min-w-[5rem]' : 'sm:w-16 sm:min-w-[4rem]'}`}
                  onClick={() => handleSort('z_score')} title="Overall rating (0-100): how he scores across your league's categories. Click to sort.">
                OVR <SortIcon columnKey="z_score" />
              </th>
              {CATEGORIES.map(category => {
                const isPunted = !includedCategories.includes(category);
                return (
                  <th
                    key={category}
                    className={`table-header ${STAT_W} !px-0 sm:!px-1 whitespace-nowrap ${isPunted ? 'opacity-40' : ''}`}
                  >
                    <div className="flex flex-col sm:flex-row items-center justify-center sm:space-x-1">
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
                        className="flex items-center whitespace-nowrap cursor-pointer hover:bg-gray-600 px-0 sm:px-1 rounded"
                        title={`${CATEGORY_FULL[category]} (click to sort)`}
                        onClick={() => handleSort(`stats.${category}.value`)}
                      >
                        {CATEGORY_NAMES[category]}<span className="hidden sm:inline ml-1"><SortIcon columnKey={`stats.${category}.value`} /></span>
                      </div>
                    </div>
                  </th>
                );
              })}
              {rotationOn && (
                <th className={`table-header text-center ${STAT_W} !px-0 sm:!px-1 sm:w-14 cursor-pointer hover:text-white whitespace-nowrap`} onClick={() => handleSort('rotation_opp')}
                    title={`Opportunity tonight: extra minutes from teammates who are out, per the NBA lineup sheet (as of ${config.rotation_as_of?.slice(11, 16) || '?'}). Click to sort.`}>
                  Opp<span className="ml-1"><SortIcon columnKey="rotation_opp" /></span>
                </th>
              )}
              {rotationOn && points && (
                <th className={`table-header text-center ${STAT_W} !px-0 sm:!px-1 sm:w-16 cursor-pointer hover:text-white whitespace-nowrap`} onClick={() => handleSort('rotation_tonight')}
                    title="Tonight: expected FPTS if he plays (his projection at tonight's expected minutes); sorts by that x his chance to play. Click to sort.">
                  Tonight<span className="ml-1"><SortIcon columnKey="rotation_tonight" /></span>
                </th>
              )}
              {rosOn && (
                <th className={`table-header text-center ${STAT_W} !px-0 sm:!px-1 sm:w-14 cursor-pointer hover:text-white whitespace-nowrap`} onClick={() => handleSort('ros_value')}
                    title="Rest of season: rank by his projection x the games he is expected to play from here. Click to sort.">
                  ROS<span className="ml-1"><SortIcon columnKey="ros_value" /></span>
                </th>
              )}
              {points && <>
                <th className={`table-header text-center ${STAT_W} !px-0 sm:!px-1 whitespace-nowrap cursor-pointer hover:text-white`} title="This season's FPTS a game against the preseason projection: green is beating it. Click to sort."
                    onClick={() => handleSort('fpts_delta')}>Δ<span className="hidden sm:inline ml-1"><SortIcon columnKey="fpts_delta" /></span></th>
                {RECENT.map(([n, label, title]) => (
                  <th key={label} className={`table-header text-center ${STAT_W} !px-0 sm:!px-1 whitespace-nowrap cursor-pointer hover:text-white`} title={`${title}: FPTS a game. Click to sort.`}
                      onClick={() => handleSort(`stats.FPTS.value_${n}`)}>{label}<span className="hidden sm:inline ml-1"><SortIcon columnKey={`stats.FPTS.value_${n}`} /></span></th>
                ))}
              </>}
              <th className="table-header text-center w-12" title="Games he has played this season">GP</th>
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
                        <span className="shrink-0 text-[11px]">{getHotColdIndicator(player)}</span>
                        {!player.is_injured && player.injury_status && player.injury_status !== 'NA' && (
                          <span className="shrink-0 inline-flex items-center px-1.5 py-px rounded-full text-[10px] leading-tight font-semibold text-white whitespace-nowrap bg-amber-600"
                                title="Yahoo's injury status">
                            {player.injury_status}
                          </span>
                        )}
                        {player.rotation && !player.is_injured && (player.rotation.inactive || player.rotation.p < RISK_P) && (
                          <span className="shrink-0 inline-flex items-center px-1.5 py-px rounded-full text-[10px] leading-tight font-semibold text-white whitespace-nowrap bg-gray-600"
                                title={rotTip(player, points)}>
                            {player.rotation.inactive ? 'Out tonight' : `${Math.round(player.rotation.p * 100)}%`}
                          </span>
                        )}
                        {player.rotation?.promoted && !player.rotation.inactive && (
                          <span className="shrink-0 inline-flex items-center px-1.5 py-px rounded-full text-[10px] leading-tight font-semibold text-white whitespace-nowrap bg-emerald-700"
                                title={rotTip(player, points)}>Starting</span>
                        )}
                        {player.is_injured && (
                          <span className="shrink-0 inline-flex items-center px-1.5 py-px rounded-full text-[10px] leading-tight font-semibold bg-red-600 text-white whitespace-nowrap"
                                title={`INJ${player.injured_return ? ` - ${player.injured_return}` : ''}${player.injured_games ? ` (${player.injured_games} missed)` : ''}`}>
                            INJ{player.injured_games ? ` ${player.injured_games}` : ''}
                          </span>
                        )}
                      </div>
                      <div className="text-[11px] text-gray-400 flex items-center gap-1 whitespace-nowrap overflow-hidden">
                        <span>{player.positions?.length ? player.positions.join('/') : player.position} · {player.team_abv || 'N/A'}</span>
                        {weeks.length > 0 && (
                          <span className="text-gray-300" title={weeks.map(w => `${w.n} games ${w.range}`).join(' · ')}>
                            · {weeks.map(w => w.n).join(' + ')} GP
                          </span>
                        )}
                      </div>
                      {player.rotation?.why && !player.rotation.inactive && Math.abs(rotOpp(player) ?? 0) >= 1 && (
                        <div className="sm:hidden text-[10px] leading-tight text-emerald-400/90 truncate" title={rotTip(player, points)}>{player.rotation.why}</div>
                      )}
                    </div>
                  </div>
                </td>
                <td className={`hidden sm:table-cell text-center px-0.5 whitespace-nowrap border-r border-gray-700 tabular-nums font-medium text-gray-200 ${bg}`}>
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

                  // Daily Leaders' look: no card or fill; the value is tinted on a gradient of z and glows at the high end
                  // (zAura), the percentile sits muted beside (desktop) or under (phone) it.
                  const aura = zAura(percentileZ(displayScore));
                  return (
                    <td key={category} className={`px-px sm:px-1 py-1 text-center tabular-nums whitespace-nowrap ${STAT_W} ${isPunted || taken ? 'opacity-40' : ''}`}
                        title={`${CATEGORY_FULL[category]}: percentile ${displayScore}`}>
                      <div className="flex flex-col sm:flex-row items-center justify-center sm:gap-1.5 leading-tight">
                        <span className="text-xs sm:text-sm text-gray-200" style={aura ? { color: aura.color, textShadow: aura.glow, fontWeight: aura.weight } : undefined}>
                          {category === 'PLUS_MINUS' && displayValue > 0 ? '+' : ''}{displayValue}{PERCENTAGE_CATEGORIES.includes(category) ? '%' : ''}
                        </span>
                        {category === 'FPTS' && player.fpts_range
                          ? <span className="text-[10px] sm:text-[11px] text-gray-500" title="Lowest to highest FPTS in a single game this season">{Math.round(player.fpts_range[0])}–{Math.round(player.fpts_range[1])}</span>
                          : <span className="text-[10px] sm:text-[11px] text-gray-500">{displayScore}</span>}
                      </div>
                    </td>
                  );
                })}
                {rotationOn && (
                  <td className={`text-center tabular-nums whitespace-nowrap px-px sm:px-1 ${STAT_W} ${fade}`} title={rotTip(player, points)}>
                    {rotOpp(player) == null ? <span className="text-gray-600">-</span>
                      : Math.abs(rotOpp(player)) < 0.5 ? <span className="text-gray-500">0</span>
                      : <span className={`text-xs sm:text-sm font-semibold ${rotOpp(player) >= 2 ? 'text-green-400' : rotOpp(player) > 0 ? 'text-green-300' : 'text-red-400'}`}>
                          {rotOpp(player) > 0 ? '+' : ''}{rotOpp(player).toFixed(1)}
                        </span>}
                  </td>
                )}
                {rotationOn && points && (
                  <td className={`text-center tabular-nums whitespace-nowrap px-px sm:px-1 ${STAT_W} ${fade}`} title={rotTip(player, points)}>
                    {rotTonight(player) == null ? <span className="text-gray-600">-</span>
                      : <span className={`text-xs sm:text-sm ${player.rotation.gain >= 2 ? 'text-green-400 font-semibold' : player.rotation.gain <= -2 ? 'text-red-400' : 'text-gray-200'}`}>
                          {player.rotation.fpts.toFixed(1)}{player.rotation.confirmed ? '' : <span className="text-gray-500">*</span>}
                        </span>}
                  </td>
                )}
                {rosOn && (
                  <td className={`text-center tabular-nums whitespace-nowrap px-px sm:px-1 ${STAT_W} ${fade}`} title={rosTip(player, points)}>
                    {player.ros_rank == null ? <span className="text-gray-600">-</span>
                      : <span className="text-xs sm:text-sm text-gray-200">
                          {player.ros_rank}
                        </span>}
                  </td>
                )}
                {points && (() => {
                  const f = player.stats.FPTS || {};
                  const delta = fptsDelta(player);
                  const cell = `px-px sm:px-1 py-1 text-center tabular-nums whitespace-nowrap ${STAT_W} ${fade}`;
                  return <>
                    <td className={cell} title={delta == null ? 'No projection or no games yet' : `${f.value_season} a game this season against a preseason projection of ${f.value_proj}${player.small_sample ? ' (small sample)' : ''}`}>
                      {delta == null ? <span className="text-gray-600">-</span> : (
                        <span className={`text-xs sm:text-sm font-semibold ${player.small_sample ? 'opacity-50' : ''} ${deltaClass(delta)}`}>
                          {delta >= 0.5 ? '▲' : delta <= -0.5 ? '▼' : '='}{Math.abs(delta).toFixed(1)}
                        </span>
                      )}
                    </td>
                    {RECENT.map(([n, label]) => {
                      const v = f[`value_${n}`];
                      // Tinted and glowing by how far the recent average sits from his season average (about 4 FPTS = 1 SD).
                      const d = v && f.value_season ? v - f.value_season : null;
                      const a = d == null ? null : zAura(d / RECENT_DELTA_PER_SD);
                      return (
                        <td key={label} className={cell} title={v ? `${label}: ${v} FPTS a game${d == null ? '' : `, ${d >= 0 ? '+' : ''}${d.toFixed(1)} against his ${f.value_season} season average`}` : undefined}>
                          {v ? <span className="text-xs sm:text-sm text-gray-200" style={a ? { color: a.color, textShadow: a.glow, fontWeight: a.weight } : undefined}>{v}</span> : <span className="text-gray-600">-</span>}
                        </td>
                      );
                    })}
                  </>;
                })()}
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
              </tr>
              );
            })}
          </tbody>
        </table>
      </div>

    </>
  );
};

export default PlayerTable;
