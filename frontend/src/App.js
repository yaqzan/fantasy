import React, { useState, useEffect, useRef } from 'react';
import PlayerTable from './components/PlayerTable';
import TeamManager from './components/TeamManager';
import Header from './components/Header';
import LineupOptimizer from './components/LineupOptimizer';
import DailyStats from './components/DailyStats';
import TeamStandings from './components/TeamStandings';
import WeeklyPickups from './components/WeeklyPickups';
import Projections from './components/Projections';
import LeagueSettings from './components/LeagueSettings';
import DraftDay from './components/DraftDay';
import {
  getPlayers, getFantasyTeams, draftPlayer, undraftPlayer, updatePlayer,
  getLeagues, activateLeague, getSelectedLeague, setSelectedLeague, errorMessage, getDraftDay
} from './services/api';

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
  const [priceExponent, setPriceExponent] = useState(null); // null: the league's own exponent
  // /draft opens the Draft Day tab directly (Flask serves index.html for every non-API path).
  const [activeTab, setActiveTabState] = useState(
    window.location.pathname.replace(/\/+$/, '') === '/draft' ? 'draft' : 'players');
  const setActiveTab = (tab) => {
    setActiveTabState(tab);
    const path = tab === 'draft' ? '/draft' : '/';
    if (window.location.pathname !== path) window.history.replaceState(null, '', path);
  };
  const [statType, setStatType] = useState('projected');
  const statTypePicked = useRef(false); // until the user picks one, the league's default applies
  const [leaguesData, setLeaguesData] = useState({ leagues: [], category_catalog: [], defaults: null });
  const [leagueId, setLeagueId] = useState(null);
  const [leagueModal, setLeagueModal] = useState(null); // 'create' | 'edit' | null
  const [loadError, setLoadError] = useState(null);

  const currentLeague = leaguesData.leagues.find(l => l.id === leagueId) || null;

  // Draft mode: an auction league before its draft (until 6 hours past the start) shows only what
  // matters for bidding. The header toggle overrides it per league (localStorage).
  const [draftModeOverride, setDraftModeOverride] = useState({});
  const draftDate = currentLeague?.settings?.draft?.date ? new Date(currentLeague.settings.draft.date) : null;
  const draftAhead = Boolean(currentLeague?.settings?.draft?.type === 'auction' && draftDate && !isNaN(draftDate)
    && Date.now() < draftDate.getTime() + 6 * 3600 * 1000);
  const storedDraftMode = (() => {
    try { return leagueId ? localStorage.getItem(`fantasy.draftMode.${leagueId}`) : null; } catch (e) { return null; }
  })();
  const draftMode = (draftModeOverride[leagueId] ?? storedDraftMode ?? (draftAhead ? 'on' : 'off')) === 'on';
  const toggleDraftMode = () => {
    const next = draftMode ? 'off' : 'on';
    setDraftModeOverride(prev => ({ ...prev, [leagueId]: next }));
    try { localStorage.setItem(`fantasy.draftMode.${leagueId}`, next); } catch (e) { /* storage blocked */ }
  };
  const [draftPlanData, setDraftPlanData] = useState(null);
  useEffect(() => {
    getDraftDay().then(setDraftPlanData).catch(() => setDraftPlanData(null));
  }, []);
  const draftPlan = draftMode && draftPlanData?.league === leagueId ? draftPlanData : null;
  // Leagues without position minimums don't need the filter while drafting.
  const rosterRules = currentLeague?.settings?.roster || {};
  const showPositionFilter = !draftMode || Boolean(rosterRules.min_guards || rosterRules.min_forwards || rosterRules.min_centers);

  const TABS = [
    ['players', 'Player Rankings'], ['lineup', 'Lineup Optimizer', true], ['pickups', 'Weekly Pickups', true],
    ['projections', 'Projections'], ['daily', 'Daily Stats', true], ['standings', 'Team Standings', true],
    ['draft', 'Draft Day'],
  ].filter(([, , inSeason]) => !(draftMode && inSeason));
  useEffect(() => {
    if (!TABS.some(([key]) => key === activeTab)) setActiveTab('players');
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [draftMode]);
  const leagueExponent = config?.league?.settings?.draft?.price_exponent ?? 1;

  useEffect(() => {
    loadLeagues();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Leagues first: the stored pick if it still exists, else the backend's active league.
  const loadLeagues = async (preferredId = null) => {
    try {
      const data = await getLeagues();
      setLeaguesData(data);
      const ids = data.leagues.map(l => l.id);
      const pick = [preferredId, getSelectedLeague(), data.active].find(id => id && ids.includes(id)) || null;
      setSelectedLeague(pick);
      setLeagueId(pick);
      if (pick) {
        await loadData();
      } else {
        setLoading(false);
      }
    } catch (error) {
      setLoadError(errorMessage(error));
      setLoading(false);
    }
  };

  const switchLeague = async (id) => {
    setSelectedLeague(id);
    setLeagueId(id);
    setPriceExponent(null);
    statTypePicked.current = false;
    setPlayers([]);
    setFantasyTeams([]);
    activateLeague(id).catch(() => {}); // CLI scripts follow the league last picked here
    await loadData();
  };

  const loadData = async (showLoading = true) => {
    try {
      if (showLoading) setLoading(true);
      setLoadError(null);
      const [playersData, teamsData] = await Promise.all([
        getPlayers(),
        getFantasyTeams()
      ]);
      setPlayers(playersData.players || []);
      setFantasyTeams(teamsData.teams || []);
      setConfig(playersData.config || { show_auction_price: true });
      // Before the season the full last season is the basis to draft on, after it the projection.
      if (!statTypePicked.current && playersData.config?.default_stat_type) {
        setStatType(playersData.config.default_stat_type);
      }
    } catch (error) {
      console.error('Error loading data:', error);
      setLoadError(errorMessage(error));
    } finally {
      if (showLoading) setLoading(false);
    }
  };

  const handleLeagueSaved = async (id) => {
    setLeagueModal(null);
    setLoading(true);
    await loadLeagues(id);
  };

  const handleLeagueDeleted = async () => {
    setLeagueModal(null);
    setSelectedLeague(null);
    setLoading(true);
    await loadLeagues();
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
    const matchesPosition = !showPositionFilter || positionFilters[player.position] || false;
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

  const leagueModalView = leagueModal && leaguesData.defaults && (
    <LeagueSettings
      mode={leagueModal}
      league={currentLeague}
      leagues={leaguesData.leagues}
      catalog={leaguesData.category_catalog}
      defaults={leaguesData.defaults}
      teams={leagueModal === 'edit' ? fantasyTeams : []}
      onClose={() => setLeagueModal(null)}
      onSaved={handleLeagueSaved}
      onDeleted={handleLeagueDeleted}
    />
  );

  const header = (
    <Header
      leagues={leaguesData.leagues}
      currentLeague={currentLeague}
      onSwitchLeague={switchLeague}
      onEditLeague={() => setLeagueModal('edit')}
      onNewLeague={() => setLeagueModal('create')}
    />
  );

  if (!currentLeague) {
    return (
      <div className="min-h-screen bg-gray-900">
        {header}
        <main className="max-w-xl mx-auto px-4 py-16 text-center">
          {loadError ? (
            <p className="text-red-400">{loadError}</p>
          ) : (
            <>
              <h2 className="text-2xl font-semibold text-white mb-3">No league yet</h2>
              <p className="text-gray-400 mb-6">Create a league with its scoring categories, roster rules and schedule, then add its teams.</p>
              <button onClick={() => setLeagueModal('create')} className="btn-primary">Create your first league</button>
            </>
          )}
        </main>
        {leagueModalView}
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-900">
      {header}
      {leagueModalView}
      <main key={leagueId} className="max-w-full mx-auto px-2 sm:px-4 lg:px-6 py-8">
        {loadError && (
          <div className="mb-4 p-3 rounded bg-red-900/40 border border-red-700 text-red-200 text-sm">{loadError}</div>
        )}
        <div className="mb-8">
          <TeamManager 
            teams={fantasyTeams} 
            onTeamUpdate={refreshData}
            refreshTrigger={players.length}
            activeSlots={currentLeague.settings.roster.active}
            rosterSize={currentLeague.settings.roster.size}
            guillotine={Boolean(currentLeague.settings.elimination?.stage_weeks?.length)}
          />
        </div>

        {/* Tab Navigation */}
        <div className="mb-6">
          <div className="border-b border-gray-700">
            <nav className="-mb-px flex items-center space-x-8">
              {TABS.map(([key, label]) => (
                <button
                  key={key}
                  onClick={() => setActiveTab(key)}
                  className={`py-2 px-1 border-b-2 font-medium text-sm ${
                    activeTab === key
                      ? 'border-nba-orange text-nba-orange'
                      : 'border-transparent text-gray-500 hover:text-gray-300 hover:border-gray-300'
                  }`}
                >
                  {label}
                </button>
              ))}
              <button
                onClick={toggleDraftMode}
                title="Draft mode shows only what matters for the auction: max bids, no in-season tabs or columns. On by default until the draft."
                className={`ml-auto mb-1 px-3 py-1 rounded-full text-xs font-medium border ${
                  draftMode ? 'bg-nba-orange text-gray-900 border-nba-orange' : 'text-gray-400 border-gray-600 hover:text-gray-200'
                }`}
              >
                Draft mode {draftMode ? 'on' : 'off'}
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
                    onChange={(e) => { statTypePicked.current = true; setStatType(e.target.value); }}
                    className="px-3 py-1.5 bg-gray-700 border border-gray-600 rounded-md text-white text-sm focus:outline-none focus:ring-2 focus:ring-nba-orange focus:border-transparent"
                  >
                    {config?.projection_season && <option value="proj">{config.projection_season} projection</option>}
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
                
                {showPositionFilter && (
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
                )}
                
                {config.show_auction_price && (
                  <div
                    className="flex items-center space-x-2"
                    title={`Auction $ follow each player's value above replacement, raised to this power. 1 splits money in proportion to value; higher pays stars more. This league's default: ${leagueExponent}`}
                  >
                    <span className="text-sm text-gray-300">Star premium:</span>
                    <input
                      type="range"
                      min="0.5"
                      max="2"
                      step="0.05"
                      value={priceExponent ?? leagueExponent}
                      onChange={(e) => {
                        const value = parseFloat(e.target.value);
                        setPriceExponent(Math.abs(value - leagueExponent) < 1e-9 ? null : value);
                      }}
                      className="w-20 h-2 bg-gray-700 rounded-lg appearance-none cursor-pointer slider"
                    />
                    <span className="text-sm text-gray-300 w-10 text-center">{(priceExponent ?? leagueExponent).toFixed(2)}</span>
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
            priceExponent={priceExponent}
            config={config}
            statType={statType}
            draftMode={draftMode}
            draftPlan={draftPlan}
          />
        </div>
        )}

        {activeTab === 'lineup' && (
          <LineupOptimizer league={currentLeague} onEditLeague={() => setLeagueModal('edit')} />
        )}

        {activeTab === 'projections' && (
          <Projections />
        )}

        {activeTab === 'pickups' && (
          <WeeklyPickups config={config} />
        )}

        {activeTab === 'daily' && (
          <DailyStats />
        )}

        {activeTab === 'standings' && (
          <TeamStandings config={config} />
        )}

        {activeTab === 'draft' && (
          <DraftDay />
        )}
      </main>
    </div>
  );
}

export default App;
