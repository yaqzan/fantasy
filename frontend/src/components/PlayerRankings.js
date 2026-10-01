import React, { useState } from 'react';
import PlayerTable from './PlayerTable';
import DraftBoard from './DraftBoard';
import useLeagueViewState, { statOptions, validStat } from '../useLeagueViewState';

const selectClass = 'px-3 py-1.5 bg-gray-700 border border-gray-600 rounded-md text-white text-sm focus:outline-none focus:ring-2 focus:ring-nba-orange focus:border-transparent';
const checkboxClass = 'h-4 w-4 text-nba-orange focus:ring-nba-orange border-gray-600 rounded bg-gray-700';

// A player matches a position chip when one of his positions reaches it: NBA's generic G covers
// PG and SG, F covers SF and PF (the same rule as the league's slots, leagues.POSITION_REACH).
const REACH = { PG: ['PG', 'G'], SG: ['SG', 'G'], G: ['PG', 'SG', 'G'], SF: ['SF', 'F'], PF: ['PF', 'F'], F: ['SF', 'PF', 'F'], C: ['C'] };
const playsPosition = (player, chip) => (player.positions?.length ? player.positions : [player.position])
  .some(pos => (REACH[pos] || [pos]).includes(chip));

// The Player Rankings tab: toolbar (stats, search, positions, star premium, filters) and the table.
// Everything picked here is remembered per league (useLeagueViewState).
const PlayerRankings = ({ players, fantasyTeams, config, draftMode, draftPlan, onDraftPlayer, onUndraftPlayer, onUpdatePlayer }) => {
  const caps = config.capabilities || {};
  const categoryKeys = (config.categories || []).map(c => c.key);
  // Leagues with positions filter by their slot positions; all-flex leagues by NBA's G/F/C.
  const chips = caps.positions?.length ? caps.positions : ['G', 'F', 'C'];
  const [view, setView] = useLeagueViewState(config.league?.id, 'players', {
    statType: config.default_stat_type || 'projected', positions: chips, available: true, healthy: true,
    priceExponent: null, punts: [],
  }, (picked) => ({
    ...validStat(config)(picked),
    ...(picked.punts && { punts: picked.punts.filter(c => categoryKeys.includes(c)) }),
    ...(picked.positions && { positions: picked.positions.filter(p => chips.includes(p)) }),
  }));
  const [searchTerm, setSearchTerm] = useState('');
  const leagueExponent = config.league?.settings?.draft?.price_exponent ?? 1;
  const showPositionFilter = !draftMode || Boolean(caps.positions?.length);

  const search = searchTerm.toLowerCase();
  const filtered = players.filter(player => {
    const mine = player.fantasy_team?.abbreviation === config.MY_TEAM_ABV;
    return (player.name.toLowerCase().includes(search) || player.team.toLowerCase().includes(search))
      && (mine || !view.available || !player.drafted)
      && (!showPositionFilter || view.positions.some(chip => playsPosition(player, chip)))
      && (!view.healthy || !player.is_injured);
  });
  const togglePosition = (chip) => setView(v => ({
    positions: v.positions.includes(chip) ? v.positions.filter(p => p !== chip) : [...v.positions, chip],
  }));

  return (
    <div className="bg-gray-800 rounded-lg shadow-xl">
      <div className="px-6 py-4 border-b border-gray-700 overflow-x-hidden">
        <div className="flex flex-col lg:flex-row lg:items-center gap-4 overflow-x-hidden">
          <div className="flex items-center space-x-2">
            <span className="text-sm text-gray-300">Stats:</span>
            <select value={view.statType} onChange={(e) => setView({ statType: e.target.value })} className={selectClass}>
              {statOptions(config).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
            </select>
          </div>

          <div className="relative flex-1">
            <input
              type="text"
              placeholder="Search players or teams..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="w-full pl-10 pr-4 py-2 bg-gray-700 border border-gray-600 rounded-md text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-nba-orange focus:border-transparent"
            />
            <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
              <svg className="h-5 w-5 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
              </svg>
            </div>
          </div>

          {showPositionFilter && (
            <div className="flex items-center space-x-4">
              <span className="text-sm text-gray-300">Position:</span>
              {chips.map(chip => (
                <label key={chip} className="flex items-center">
                  <input type="checkbox" checked={view.positions.includes(chip)} onChange={() => togglePosition(chip)} className={checkboxClass} />
                  <span className="ml-1 text-sm text-gray-300">{chip}</span>
                </label>
              ))}
            </div>
          )}

          {caps.auction && (
            <div
              className="flex items-center space-x-2"
              title={`Auction $ follow each player's value above replacement, raised to this power. 1 splits money in proportion to value; higher pays stars more. This league's default: ${leagueExponent}`}
            >
              <span className="text-sm text-gray-300">Star premium:</span>
              <input
                type="range" min="0.5" max="2" step="0.05"
                value={view.priceExponent ?? leagueExponent}
                onChange={(e) => {
                  const value = parseFloat(e.target.value);
                  setView({ priceExponent: Math.abs(value - leagueExponent) < 1e-9 ? null : value });
                }}
                className="w-20 h-2 bg-gray-700 rounded-lg appearance-none cursor-pointer slider"
              />
              <span className="text-sm text-gray-300 w-10 text-center">{(view.priceExponent ?? leagueExponent).toFixed(2)}</span>
            </div>
          )}

          <div className="flex items-center space-x-4">
            <label className="flex items-center">
              <input type="checkbox" checked={view.available} onChange={(e) => setView({ available: e.target.checked })} className={checkboxClass} />
              <span className="ml-2 text-sm text-gray-300">Available</span>
            </label>
            <label className="flex items-center">
              <input type="checkbox" checked={view.healthy} onChange={(e) => setView({ healthy: e.target.checked })} className={checkboxClass} />
              <span className="ml-2 text-sm text-gray-300">Healthy</span>
            </label>
          </div>
        </div>
      </div>

      {React.createElement(draftMode ? DraftBoard : PlayerTable, {
        players: filtered,
        fantasyTeams,
        onDraftPlayer,
        onUndraftPlayer,
        onUpdatePlayer,
        priceExponent: view.priceExponent,
        config,
        statType: view.statType,
        punts: view.punts,
        onPuntsChange: (punts) => setView({ punts }),
        ...(draftMode && { draftPlan, allPlayers: players }),
      })}
    </div>
  );
};

export default PlayerRankings;
