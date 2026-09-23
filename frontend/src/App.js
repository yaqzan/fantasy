import React, { useState, useEffect } from 'react';
import PlayerTable from './components/PlayerTable';
import TeamManager from './components/TeamManager';
import Header from './components/Header';
import LineupOptimizer from './components/LineupOptimizer';
import DailyStats from './components/DailyStats';
import TeamStandings from './components/TeamStandings';
import { getPlayers, getFantasyTeams, draftPlayer, undraftPlayer, updatePlayer } from './services/api';

function App() {
  const [players, setPlayers] = useState([]);
  const [fantasyTeams, setFantasyTeams] = useState([]);
  const [loading, setLoading] = useState(true);
  const [config, setConfig] = useState({ show_auction_price: true });
  const [showAvailableOnly, setShowAvailableOnly] = useState(true);
  const [showHealthyOnly, setShowHealthyOnly] = useState(true);
  const [searchTerm, setSearchTerm] = useState('');
  const [positionFilters, setPositionFilters] = useState({
    G: true,
    F: true,
    C: true
  });
  const [expFactor, setExpFactor] = useState(4);
  const [activeTab, setActiveTab] = useState('players');
  const [statType, setStatType] = useState('5');

  useEffect(() => {
    loadData();
  }, []);

  const loadData = async (showLoading = true) => {
    try {
      if (showLoading) setLoading(true);
      const [playersData, teamsData] = await Promise.all([
        getPlayers(),
        getFantasyTeams()
      ]);
      setPlayers(playersData.players || []);
      setFantasyTeams(teamsData.teams || []);
      setConfig(playersData.config || { show_auction_price: true });
    } catch (error) {
      console.error('Error loading data:', error);
    } finally {
      if (showLoading) setLoading(false);
    }
  };

  const refreshData = () => loadData(false);

  const handleDraftPlayer = async (playerName, fantasyTeamId) => {
    try {
      await draftPlayer(playerName, fantasyTeamId);
      await refreshData(); // Refresh data without loading screen
    } catch (error) {
      console.error('Error drafting player:', error);
    }
  };

  const handleUndraftPlayer = async (playerName) => {
    try {
      await undraftPlayer(playerName);
      await refreshData(); // Refresh data without loading screen
    } catch (error) {
      console.error('Error undrafting player:', error);
    }
  };

  const handleUpdatePlayer = async (playerName, isInjured, isUndroppable) => {
    try {
      await updatePlayer(playerName, isInjured, isUndroppable);
      await refreshData(); // Refresh data without loading screen
    } catch (error) {
      console.error('Error updating player:', error);
    }
  };

  const getPinnedPlayers = () => {
    const saved = sessionStorage.getItem('pinnedPlayers');
    return saved ? new Set(JSON.parse(saved)) : new Set();
  };

  const filteredPlayers = players.filter(player => {
    const pinnedPlayers = getPinnedPlayers();
    const isPinned = pinnedPlayers.has(player.name);
    
    // Always show pinned players
    if (isPinned) return true;
    
    const matchesSearch = player.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
                         player.team.toLowerCase().includes(searchTerm.toLowerCase());
    const isMyTeamPlayer = player.fantasy_team?.abbreviation === config?.MY_TEAM_ABV;
    // Always show my team players, otherwise respect the available filter
    const matchesFilter = isMyTeamPlayer ? true : (showAvailableOnly ? !player.drafted : true);
    const matchesPosition = positionFilters[player.position] || false;
    // Health filter: if showHealthyOnly is false (unchecked), show all players
    // If showHealthyOnly is true (checked), only show healthy players (is_injured !== true)
    const matchesHealth = !showHealthyOnly ? true : (player.is_injured !== true);
    return matchesSearch && matchesFilter && matchesPosition && matchesHealth;
  });

  if (loading) {
    return (
      <div className="min-h-screen bg-gray-900 flex items-center justify-center">
        <div className="text-center">
          <div className="animate-spin rounded-full h-32 w-32 border-b-2 border-nba-orange mx-auto"></div>
          <p className="mt-4 text-xl text-gray-300">Loading NBA Fantasy Data...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-900">
      <Header />
      <main className="max-w-full mx-auto px-2 sm:px-4 lg:px-6 py-8">
        <div className="mb-8">
          <TeamManager 
            teams={fantasyTeams} 
            onTeamUpdate={refreshData}
            refreshTrigger={players.length}
          />
        </div>

        {/* Tab Navigation */}
        <div className="mb-6">
          <div className="border-b border-gray-700">
            <nav className="-mb-px flex space-x-8">
              <button
                onClick={() => setActiveTab('players')}
                className={`py-2 px-1 border-b-2 font-medium text-sm ${
                  activeTab === 'players'
                    ? 'border-nba-orange text-nba-orange'
                    : 'border-transparent text-gray-500 hover:text-gray-300 hover:border-gray-300'
                }`}
              >
                Player Rankings
              </button>
              <button
                onClick={() => setActiveTab('lineup')}
                className={`py-2 px-1 border-b-2 font-medium text-sm ${
                  activeTab === 'lineup'
                    ? 'border-nba-orange text-nba-orange'
                    : 'border-transparent text-gray-500 hover:text-gray-300 hover:border-gray-300'
                }`}
              >
                Lineup Optimizer
              </button>
              <button
                onClick={() => setActiveTab('daily')}
                className={`py-2 px-1 border-b-2 font-medium text-sm ${
                  activeTab === 'daily'
                    ? 'border-nba-orange text-nba-orange'
                    : 'border-transparent text-gray-500 hover:text-gray-300 hover:border-gray-300'
                }`}
              >
                Daily Stats
              </button>
              <button
                onClick={() => setActiveTab('standings')}
                className={`py-2 px-1 border-b-2 font-medium text-sm ${
                  activeTab === 'standings'
                    ? 'border-nba-orange text-nba-orange'
                    : 'border-transparent text-gray-500 hover:text-gray-300 hover:border-gray-300'
                }`}
              >
                Team Standings
              </button>
            </nav>
          </div>
        </div>
        
        {activeTab === 'players' && (
          <div className="bg-gray-800 rounded-lg shadow-xl">
          <div className="px-6 py-4 border-b border-gray-700 overflow-x-hidden">
            <div className="flex flex-col gap-4">
              <div className="flex flex-col lg:flex-row lg:items-center gap-4 overflow-x-hidden">
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
                
                <div className="flex items-center space-x-4">
                  <span className="text-sm text-gray-300">Position:</span>
                  {['G', 'F', 'C'].map(position => (
                    <label key={position} className="flex items-center">
                      <input
                        type="checkbox"
                        checked={positionFilters[position]}
                        onChange={(e) => setPositionFilters(prev => ({
                          ...prev,
                          [position]: e.target.checked
                        }))}
                        className="h-4 w-4 text-nba-orange focus:ring-nba-orange border-gray-600 rounded bg-gray-700"
                      />
                      <span className="ml-1 text-sm text-gray-300">{position}</span>
                    </label>
                  ))}
                </div>
                
                {config.show_auction_price && (
                  <div className="flex items-center space-x-2">
                    <span className="text-sm text-gray-300">Price Factor:</span>
                    <input
                      type="range"
                      min="1"
                      max="5"
                      step="0.5"
                      value={expFactor}
                      onChange={(e) => setExpFactor(parseFloat(e.target.value))}
                      className="w-20 h-2 bg-gray-700 rounded-lg appearance-none cursor-pointer slider"
                    />
                    <span className="text-sm text-gray-300 w-8 text-center">{expFactor}</span>
                  </div>
                )}
                
                <div className="flex items-center space-x-4">
                  <label className="flex items-center">
                    <input
                      type="checkbox"
                      checked={showAvailableOnly}
                      onChange={(e) => setShowAvailableOnly(e.target.checked)}
                      className="h-4 w-4 text-nba-orange focus:ring-nba-orange border-gray-600 rounded bg-gray-700"
                    />
                    <span className="ml-2 text-sm text-gray-300">Available</span>
                  </label>
                  
                  <label className="flex items-center">
                    <input
                      type="checkbox"
                      checked={showHealthyOnly}
                      onChange={(e) => setShowHealthyOnly(e.target.checked)}
                      className="h-4 w-4 text-nba-orange focus:ring-nba-orange border-gray-600 rounded bg-gray-700"
                    />
                    <span className="ml-2 text-sm text-gray-300">Healthy</span>
                  </label>
                </div>
              </div>
            </div>
          </div>
          
          <PlayerTable 
            players={filteredPlayers}
            fantasyTeams={fantasyTeams}
            onDraftPlayer={handleDraftPlayer}
            onUndraftPlayer={handleUndraftPlayer}
            onUpdatePlayer={handleUpdatePlayer}
            expFactor={expFactor}
            onExpFactorChange={setExpFactor}
            config={config}
            statType={statType}
          />
        </div>
        )}

        {activeTab === 'lineup' && (
          <LineupOptimizer />
        )}

        {activeTab === 'daily' && (
          <DailyStats />
        )}

        {activeTab === 'standings' && (
          <TeamStandings config={config} />
        )}
      </main>
    </div>
  );
}

export default App;
