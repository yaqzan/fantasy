import React, { useState, useEffect } from 'react';
import PlayerRankings from './components/PlayerRankings';
import TeamManager from './components/TeamManager';
import Header from './components/Header';
import LineupOptimizer from './components/LineupOptimizer';
import DailyLeaders from './components/DailyLeaders';
import TeamStandings from './components/TeamStandings';
import WeeklyPickups from './components/WeeklyPickups';
import Projections from './components/Projections';
import LeagueSettings from './components/LeagueSettings';
import DraftDay from './components/DraftDay';
import {
  getPlayers, getFantasyTeams, draftPlayer, undraftPlayer, updatePlayer,
  getLeagues, activateLeague, getSelectedLeague, setSelectedLeague, errorMessage, getDraftDay, getDefaultTab
} from './services/api';

// Tabs: [key, label, in-season only (hidden in draft mode)]. Each tab keeps its own view state per
// league (useLeagueViewState) and follows the league's capabilities, never its platform or id.
const ALL_TABS = [
  ['daily', 'Daily Leaders', true], ['players', 'Player Rankings'], ['lineup', 'Lineup Optimizer', true],
  ['pickups', 'Weekly Pickups', true], ['projections', 'Projections'], ['standings', 'Team Standings', true],
  ['draft', 'Draft Day'], ['teams', 'Teams'],
];

// Phones fold the Fantasy Teams panel into the Teams tab; wider screens keep it above the tabs.
const PHONE = '(max-width: 639px)';
const useIsPhone = () => {
  const [isPhone, setIsPhone] = useState(() => Boolean(window.matchMedia?.(PHONE).matches));
  useEffect(() => {
    const mq = window.matchMedia?.(PHONE);
    if (!mq) return undefined;
    const onChange = () => setIsPhone(mq.matches);
    mq.addEventListener('change', onChange);
    return () => mq.removeEventListener('change', onChange);
  }, []);
  return isPhone;
};

function App() {
  const [players, setPlayers] = useState([]);
  const [fantasyTeams, setFantasyTeams] = useState([]);
  const [loading, setLoading] = useState(true);
  const [config, setConfig] = useState({});
  const isPhone = useIsPhone();
  // /draft opens the Draft Day tab directly (Flask serves index.html for every non-API path).
  // Otherwise the server picks (null until it answers): Daily Leaders from the first tip-off until
  // 8 am Eastern the next morning, Player Rankings the rest of the time. A click always wins.
  const [activeTab, setActiveTabState] = useState(
    window.location.pathname.replace(/\/+$/, '') === '/draft' ? 'draft' : null);
  useEffect(() => {
    if (activeTab !== null) return;
    getDefaultTab().then(tab => setActiveTabState(prev => prev ?? tab)).catch(() => setActiveTabState(prev => prev ?? 'players'));
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  const setActiveTab = (tab) => {
    setActiveTabState(tab);
    const path = tab === 'draft' ? '/draft' : '/';
    if (window.location.pathname !== path) window.history.replaceState(null, '', path);
  };
  const [leaguesData, setLeaguesData] = useState({ leagues: [], category_catalog: [], defaults: null, point_stats: {}, default_points: {} });
  const [leagueId, setLeagueId] = useState(null);
  const [leagueModal, setLeagueModal] = useState(null); // 'create' | 'edit' | null
  const [loadError, setLoadError] = useState(null);

  const currentLeague = leaguesData.leagues.find(l => l.id === leagueId) || null;
  const caps = config.capabilities || {};

  // Draft mode shows only what matters for drafting. Off unless switched on with the header
  // toggle, which is remembered per league (localStorage).
  const [draftModeOverride, setDraftModeOverride] = useState({});
  const storedDraftMode = (() => {
    try { return leagueId ? localStorage.getItem(`fantasy.draftMode.${leagueId}`) : null; } catch (e) { return null; }
  })();
  const draftMode = (draftModeOverride[leagueId] ?? storedDraftMode ?? 'off') === 'on';
  const toggleDraftMode = () => {
    const next = draftMode ? 'off' : 'on';
    setDraftModeOverride(prev => ({ ...prev, [leagueId]: next }));
    try { localStorage.setItem(`fantasy.draftMode.${leagueId}`, next); } catch (e) { /* storage blocked */ }
  };
  const [draftPlanData, setDraftPlanData] = useState(null);
  useEffect(() => {
    getDraftDay().then(setDraftPlanData).catch(() => setDraftPlanData(null));
  }, []);
  // The Draft Day plan is built for one league (capability draft_plan).
  const draftPlan = draftMode && caps.draft_plan && draftPlanData?.league === leagueId ? draftPlanData : null;

  const TABS = ALL_TABS.filter(([key, , inSeason]) => !(draftMode && inSeason) && (key !== 'draft' || caps.draft_plan) && (key !== 'teams' || isPhone));
  useEffect(() => {
    if (!loading && activeTab !== null && !TABS.some(([key]) => key === activeTab)) setActiveTab('players');
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [draftMode, caps.draft_plan, isPhone, loading, activeTab === null]);

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
    setPlayers([]);
    setFantasyTeams([]);
    activateLeague(id).catch(() => {}); // CLI scripts follow the league last picked here
    await loadData();
  };

  const loadData = async (showLoading = true) => {
    try {
      if (showLoading) setLoading(true);
      setLoadError(null);
      const [playersData, teamsData] = await Promise.all([getPlayers(), getFantasyTeams()]);
      setPlayers(playersData.players || []);
      setFantasyTeams(teamsData.teams || []);
      setConfig(playersData.config || {});
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
  const refreshAfter = (action) => async (...args) => {
    try {
      await action(...args);
      await refreshData();
    } catch (error) {
      console.error(error);
      setLoadError(errorMessage(error));
    }
  };

  // Draft mode: picks also arrive from outside the page (pull_fantrax.py draft --watch), so reload
  // the board every minute; prices and values recompute from the fresh rosters.
  useEffect(() => {
    if (!draftMode || !leagueId) return undefined;
    const timer = setInterval(() => { if (!document.hidden) loadData(false); }, 60000);
    return () => clearInterval(timer);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [draftMode, leagueId]);

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
      pointStats={leaguesData.point_stats}
      defaultPoints={leaguesData.default_points}
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

  if (!currentLeague || !config.league) {
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
      <main key={leagueId} className="max-w-full mx-auto px-2 sm:px-4 lg:px-6 py-2 sm:py-8">
        {loadError && (
          <div className="mb-4 p-3 rounded bg-red-900/40 border border-red-700 text-red-200 text-sm">{loadError}</div>
        )}
        {!isPhone && (
          <div className="mb-8">
            <TeamManager teams={fantasyTeams} onTeamUpdate={refreshData} refreshTrigger={players.length} config={config} />
          </div>
        )}

        {/* Tab Navigation */}
        {/* Phones: the tabs scroll sideways in one row; the draft-mode pill stays put */}
        <div className="mb-2 sm:mb-6">
          <div className="border-b border-gray-700 flex items-center gap-3">
            <nav className="-mb-px flex-1 min-w-0 flex items-center gap-5 sm:gap-8 overflow-x-auto hide-scrollbar">
              {TABS.map(([key, label]) => (
                <button
                  key={key}
                  onClick={() => setActiveTab(key)}
                  className={`py-2 px-1 border-b-2 font-medium text-sm whitespace-nowrap flex-shrink-0 ${
                    activeTab === key
                      ? 'border-nba-orange text-nba-orange'
                      : 'border-transparent text-gray-500 hover:text-gray-300 hover:border-gray-300'
                  }`}
                >
                  {label}
                </button>
              ))}
            </nav>
            <button
              onClick={toggleDraftMode}
              title="Draft mode shows only what matters for the draft: no in-season tabs or columns. On by default until the draft."
              className={`mb-1 px-3 py-1 rounded-full text-xs font-medium border whitespace-nowrap flex-shrink-0 ${
                draftMode ? 'bg-nba-orange text-onaccent border-nba-orange' : 'text-gray-400 border-gray-600 hover:text-gray-200'
              }`}
            >
              Draft mode {draftMode ? 'on' : 'off'}
            </button>
          </div>
        </div>

        {activeTab === 'players' && (
          <PlayerRankings
            players={players}
            fantasyTeams={fantasyTeams}
            config={config}
            draftMode={draftMode}
            draftPlan={draftPlan}
            onDraftPlayer={refreshAfter(draftPlayer)}
            onUndraftPlayer={refreshAfter(undraftPlayer)}
            onUpdatePlayer={refreshAfter(updatePlayer)}
          />
        )}
        {activeTab === 'lineup' && <LineupOptimizer config={config} onEditLeague={() => setLeagueModal('edit')} />}
        {activeTab === 'projections' && <Projections config={config} />}
        {activeTab === 'pickups' && <WeeklyPickups config={config} />}
        {activeTab === 'daily' && <DailyLeaders config={config} />}
        {activeTab === 'standings' && <TeamStandings config={config} />}
        {activeTab === 'draft' && <DraftDay />}
        {activeTab === 'teams' && isPhone && (
          <TeamManager teams={fantasyTeams} onTeamUpdate={refreshData} refreshTrigger={players.length} config={config} asTab />
        )}
      </main>
    </div>
  );
}

export default App;
