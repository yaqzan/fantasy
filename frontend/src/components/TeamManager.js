import React, { useState, useEffect, useRef, useCallback } from 'react';
import {
  createFantasyTeam, deleteFantasyTeam, getTeamRosters, undraftPlayer, updateFantasyTeam, eliminateFantasyTeam, restoreFantasyTeam,
  errorMessage,
} from '../services/api';

// The league's teams and rosters. Roster size and slots follow the league; Eliminate/Restore only
// show in guillotine leagues.
const TeamManager = ({ teams, onTeamUpdate, refreshTrigger, config }) => {
  const rosterSize = config?.league?.settings?.roster?.size || 13;
  const guillotine = Boolean(config?.capabilities?.guillotine);
  const hasSlots = Boolean(config?.capabilities?.positions?.length);
  const [teamScores, setTeamScores] = useState({});
  const [openSlots, setOpenSlots] = useState({});
  const [showModal, setShowModal] = useState(false);
  const [newTeamName, setNewTeamName] = useState('');
  const [newTeamAbbrev, setNewTeamAbbrev] = useState('');
  const [loading, setLoading] = useState(false);
  const [teamPlayers, setTeamPlayers] = useState({});
  const [editingTeam, setEditingTeam] = useState(null);
  const [editTeamName, setEditTeamName] = useState('');
  const [editTeamAbbrev, setEditTeamAbbrev] = useState('');
  const [teamBlockWidth, setTeamBlockWidth] = useState('calc(8% - 0.25rem)');
  // Folded by default on phones, where 16 rosters would push the tabs off the first screen.
  const [expanded, setExpanded] = useState(() => !window.matchMedia?.('(max-width: 639px)').matches);
  const containerRef = useRef(null);

  // Calculate optimal team block width
  const calculateTeamBlockWidth = useCallback(() => {
    if (containerRef.current && teams.length > 0) {
      const containerWidth = containerRef.current.offsetWidth;
      const gapSize = 4; // 0.25rem = 4px
      const totalGaps = (teams.length - 1) * gapSize;
      const availableWidth = containerWidth - totalGaps;
      const blockWidth = availableWidth / teams.length;
      const widthPercent = (blockWidth / containerWidth) * 100;
      
      // Force single line layout - use calculated width without minimum
      setTeamBlockWidth(`calc(${widthPercent.toFixed(2)}% - ${(gapSize / containerWidth * 100).toFixed(2)}%)`);
    }
  }, [teams.length]);

  // Recalculate width when teams change or window resizes
  useEffect(() => {
    calculateTeamBlockWidth();
    
    const handleResize = () => calculateTeamBlockWidth();
    window.addEventListener('resize', handleResize);
    
    return () => window.removeEventListener('resize', handleResize);
  }, [teams.length, calculateTeamBlockWidth]);

  // Every roster in one request (starters and scores come from the league's slots).
  useEffect(() => {
    if (teams.length === 0) return;
    getTeamRosters()
      .then(data => {
        setTeamPlayers(Object.fromEntries(teams.map(t => [t.id, data.teams[t.id]?.players || []])));
        setTeamScores(Object.fromEntries(teams.map(t => [t.id, data.teams[t.id]?.score || 0])));
        setOpenSlots(Object.fromEntries(teams.map(t => [t.id, data.teams[t.id]?.open_slots || []])));
      })
      .catch(error => console.error('Error loading rosters:', error));
  }, [teams, refreshTrigger]);

  const handleCreateTeam = async (e) => {
    e.preventDefault();
    if (!newTeamName.trim()) return;

    try {
      setLoading(true);
      await createFantasyTeam({
        name: newTeamName.trim(),
        abbreviation: newTeamAbbrev.trim() || null
      });
      
      setNewTeamName('');
      setNewTeamAbbrev('');
      setShowModal(false);
      onTeamUpdate();
    } catch (error) {
      console.error('Error creating team:', error);
      alert(`Error creating team: ${errorMessage(error)}`);
    } finally {
      setLoading(false);
    }
  };

  const handleEditTeam = (team) => {
    setEditingTeam(team);
    setEditTeamName(team.name);
    setEditTeamAbbrev(team.abbreviation || '');
  };

  const handleSaveEdit = async (e) => {
    e.preventDefault();
    if (!editTeamName.trim()) return;

    try {
      setLoading(true);
      await updateFantasyTeam(editingTeam.id, {
        name: editTeamName.trim(),
        abbreviation: editTeamAbbrev.trim() || null
      });
      setEditingTeam(null);
      onTeamUpdate();
    } catch (error) {
      console.error('Error updating team:', error);
      alert('Error updating team. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  const handleDeleteTeam = async () => {
    const count = (teamPlayers[editingTeam.id] || []).length;
    if (!window.confirm(`Delete ${editingTeam.name}${count ? ` and its ${count} rostered players` : ''} from this league?`)) return;
    try {
      setLoading(true);
      await deleteFantasyTeam(editingTeam.id);
      setEditingTeam(null);
      onTeamUpdate();
    } catch (error) {
      alert(`Error deleting team: ${errorMessage(error)}`);
    } finally {
      setLoading(false);
    }
  };

  const handleEliminate = async () => {
    const count = (teamPlayers[editingTeam.id] || []).length;
    const stage = window.prompt(
      `Eliminate ${editingTeam.name}? Its ${count} players become free agents. After which stage? (blank = the last one that ended)`, '');
    if (stage === null) return;
    try {
      setLoading(true);
      await eliminateFantasyTeam(editingTeam.id, parseInt(stage, 10) || null);
      setEditingTeam(null);
      onTeamUpdate();
    } catch (error) {
      alert(`Error eliminating team: ${errorMessage(error)}`);
    } finally {
      setLoading(false);
    }
  };

  const handleRestore = async () => {
    try {
      setLoading(true);
      const result = await restoreFantasyTeam(editingTeam.id);
      if (result.skipped?.length) alert(`Restored. Not given back (on another team now): ${result.skipped.join(', ')}`);
      setEditingTeam(null);
      onTeamUpdate();
    } catch (error) {
      alert(`Error restoring team: ${errorMessage(error)}`);
    } finally {
      setLoading(false);
    }
  };

  const handleUndraftPlayer = async (playerName) => {
    try {
      await undraftPlayer(playerName);
      onTeamUpdate(); // Refresh data
    } catch (error) {
      console.error('Error undrafting player:', error);
      alert('Error undrafting player. Please try again.');
    }
  };

  const getZScoreColor = (score) => {
    if (score >= 70) {
      // Green spectrum with clear text
      if (score >= 95) return 'text-green-400';      // High intensity green
      if (score >= 90) return 'text-green-500';      // Medium-high intensity green
      if (score >= 85) return 'text-green-600';      // Medium intensity green
      if (score >= 80) return 'text-green-700';      // Medium-low intensity green
      if (score >= 75) return 'text-green-800';      // Low intensity green
      return 'text-green-900';                       // Very low intensity green
    } else if (score <= 30) {
      // Red spectrum with clear text
      if (score <= 5) return 'text-red-400';         // High intensity red
      if (score <= 10) return 'text-red-500';        // Medium-high intensity red
      if (score <= 15) return 'text-red-600';        // Medium intensity red
      if (score <= 20) return 'text-red-700';        // Medium-low intensity red
      if (score <= 25) return 'text-red-800';        // Low intensity red
      return 'text-red-900';                         // Very low intensity red
    }
    // Mediocre scores blend into background
    return 'text-gray-400';                          // Neutral gray
  };

  // The starters' average OVR (the server picks the starters that fit the league's slots)
  const getTeamAverageScore = (teamId) => teamScores[teamId] || 0;

  // Sort teams by average score (descending)
  const sortedTeams = [...teams].sort((a, b) => {
    if (!a.eliminated_stage !== !b.eliminated_stage) return a.eliminated_stage ? 1 : -1; // knocked-out teams last
    const scoreA = getTeamAverageScore(a.id);
    const scoreB = getTeamAverageScore(b.id);
    return scoreB - scoreA;
  });
  

  return (
    <div className="bg-gray-800 rounded-lg shadow-lg p-3 sm:p-6">
      <div className={`flex items-center justify-between ${expanded ? 'mb-3 sm:mb-4' : ''}`}>
        <button onClick={() => setExpanded(!expanded)} aria-expanded={expanded}
          className="flex items-center gap-2 text-base sm:text-lg font-semibold text-white">
          <svg className={`w-4 h-4 text-gray-400 transition-transform ${expanded ? 'rotate-90' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
          </svg>
          Fantasy Teams
          {!expanded && teams.length > 0 && <span className="text-xs font-normal text-gray-400">{teams.length}</span>}
        </button>
        <button onClick={() => setShowModal(true)} className="btn-secondary text-sm py-1.5 sm:py-2">Add team</button>
      </div>

      {!expanded ? null : teams.length === 0 ? (
        <p className="text-gray-400 text-center py-4">No fantasy teams created yet.</p>
      ) : (
        <div ref={containerRef} className="flex flex-nowrap gap-1 overflow-x-auto thin-scrollbar">
          {sortedTeams.map((team) => (
            <div key={team.id} className={`bg-gray-700 rounded p-0.5 group hover:bg-gray-600 transition-colors flex-shrink-0 min-h-64 min-w-[8.5rem] sm:min-w-0 ${team.eliminated_stage ? 'opacity-40' : ''}`} style={{width: teamBlockWidth}}>
              <div className="text-center mb-1 relative">
                <h4 className="font-medium text-white text-xs truncate leading-tight">{team.name}</h4>
                {team.abbreviation && (
                  <p className="text-xs text-gray-400 leading-tight">{team.abbreviation}</p>
                )}
                {team.eliminated_stage ? (
                  <div className="team-badge bg-red-800 text-white text-xs mt-0.5 px-1" title={`Eliminated after stage ${team.eliminated_stage}`}>
                    Out S{team.eliminated_stage}
                  </div>
                ) : (
                  <div className="team-badge bg-th text-onth text-xs mt-0.5 px-1">
                    {getTeamAverageScore(team.id)}
                  </div>
                )}
                {(teamPlayers[team.id] || []).length > 0 && (
                  <p className={`text-[10px] leading-tight ${(teamPlayers[team.id] || []).length > rosterSize ? 'text-red-400' : 'text-gray-500'}`}
                     title={`Roster spots used (the league has ${rosterSize})`}>
                    {(teamPlayers[team.id] || []).length}/{rosterSize}
                  </p>
                )}
                {hasSlots && (teamPlayers[team.id] || []).length > 0 && openSlots[team.id]?.length > 0 && (
                  <p className="text-[10px] leading-tight text-red-400" title="Starting slots no healthy player on this roster can fill">
                    no {openSlots[team.id].join(' ')}
                  </p>
                )}
                
                {/* Edit icon - only visible on hover */}
                <button
                  onClick={() => handleEditTeam(team)}
                  className="absolute top-0 right-0 opacity-0 group-hover:opacity-100 [@media(hover:none)]:opacity-100 transition-opacity p-0.5 hover:bg-gray-500 rounded"
                >
                  <svg className="w-2.5 h-2.5 text-gray-300" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
                  </svg>
                </button>
              </div>
              
              {/* Team Players */}
              <div className="mt-1">
                {teamPlayers[team.id] && teamPlayers[team.id].length > 0 ? (
                  <div className="space-y-0.5">
                    {teamPlayers[team.id]
                      .slice(0, Math.max(rosterSize, 10))
                      .map((player, index) => (
                      <div key={index} className="text-xs text-gray-400 truncate flex items-center justify-between group/item">
                        <span className="flex-1 truncate leading-tight flex items-center gap-1">
                          <span className={`font-medium ${getZScoreColor(player.z_score)} w-8 text-right inline-block`}>
                            {player.z_score !== 0 ? player.z_score : '-'}
                          </span>
                          {hasSlots && <span className="text-gray-500 text-[10px] w-7 inline-block" title="Starting slot">{player.slot || 'BN'}</span>}
                          {player.player_name}
                          {player.is_injured && (
                            <span className="inline-flex items-center px-1 py-0.5 rounded-full text-[10px] font-semibold bg-red-600 text-white">
                              O
                            </span>
                          )}
                        </span>
                        <button
                          onClick={() => handleUndraftPlayer(player.player_name)}
                          className="opacity-0 group-hover/item:opacity-100 [@media(hover:none)]:opacity-60 transition-opacity ml-0.5 hover:bg-red-600 rounded p-0.5"
                        >
                          <svg className="w-2 h-2 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                          </svg>
                        </button>
                      </div>
                    ))}
                    {teamPlayers[team.id].length > Math.max(rosterSize, 10) && (
                      <div className="text-xs text-gray-500 leading-tight">
                        +{teamPlayers[team.id].length - Math.max(rosterSize, 10)}
                      </div>
                    )}
                  </div>
                ) : (
                  <div className="text-xs text-gray-500 leading-tight">Empty</div>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Edit Team Modal */}
      {editingTeam && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-3">
          <div className="bg-gray-800 rounded-lg p-4 sm:p-6 w-full max-w-md max-h-full overflow-y-auto">
            <h3 className="text-lg font-semibold text-white mb-4">Edit Team</h3>
            
            <form onSubmit={handleSaveEdit}>
              <div className="mb-4">
                <label className="block text-sm font-medium text-gray-300 mb-2">
                  Team Name *
                </label>
                <input
                  type="text"
                  value={editTeamName}
                  onChange={(e) => setEditTeamName(e.target.value)}
                  className="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded-md text-white focus:outline-none focus:ring-2 focus:ring-nba-orange"
                  placeholder="Enter team name"
                  required
                />
              </div>
              
              <div className="mb-6">
                <label className="block text-sm font-medium text-gray-300 mb-2">
                  Abbreviation (Optional)
                </label>
                <input
                  type="text"
                  value={editTeamAbbrev}
                  onChange={(e) => setEditTeamAbbrev(e.target.value)}
                  className="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded-md text-white focus:outline-none focus:ring-2 focus:ring-nba-orange"
                  placeholder="e.g., LAL, GSW"
                  maxLength="10"
                />
              </div>
              
              <div className="flex flex-wrap justify-end gap-3">
                <button
                  type="button"
                  onClick={handleDeleteTeam}
                  className="mr-auto text-sm text-red-400 hover:text-red-300"
                  disabled={loading}
                >
                  Delete team
                </button>
                {guillotine && (editingTeam.eliminated_stage ? (
                  <button type="button" onClick={handleRestore} className="text-sm text-gray-300 hover:text-white" disabled={loading}
                    title={`Eliminated after stage ${editingTeam.eliminated_stage}; gives back its players unless another team has them`}>
                    Undo elimination
                  </button>
                ) : (
                  <button type="button" onClick={handleEliminate} className="text-sm text-red-400 hover:text-red-300" disabled={loading}>
                    Eliminate
                  </button>
                ))}
                <button
                  type="button"
                  onClick={() => setEditingTeam(null)}
                  className="btn-secondary"
                  disabled={loading}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="btn-primary"
                  disabled={loading}
                >
                  {loading ? 'Saving...' : 'Save Changes'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Create Team Modal */}
      {showModal && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-3">
          <div className="bg-gray-800 rounded-lg p-4 sm:p-6 w-full max-w-md max-h-full overflow-y-auto">
            <h3 className="text-lg font-semibold text-white mb-4">Create New Team</h3>
            
            <form onSubmit={handleCreateTeam}>
              <div className="mb-4">
                <label className="block text-sm font-medium text-gray-300 mb-2">
                  Team Name *
                </label>
                <input
                  type="text"
                  value={newTeamName}
                  onChange={(e) => setNewTeamName(e.target.value)}
                  className="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded-md text-white focus:outline-none focus:ring-2 focus:ring-nba-orange"
                  placeholder="Enter team name"
                  required
                />
              </div>
              
              <div className="mb-6">
                <label className="block text-sm font-medium text-gray-300 mb-2">
                  Abbreviation (Optional)
                </label>
                <input
                  type="text"
                  value={newTeamAbbrev}
                  onChange={(e) => setNewTeamAbbrev(e.target.value)}
                  className="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded-md text-white focus:outline-none focus:ring-2 focus:ring-nba-orange"
                  placeholder="e.g., LAL, GSW"
                  maxLength="10"
                />
              </div>
              
              <div className="flex flex-wrap justify-end gap-3">
                <button
                  type="button"
                  onClick={() => setShowModal(false)}
                  className="btn-secondary"
                  disabled={loading}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="btn-primary"
                  disabled={loading}
                >
                  {loading ? 'Creating...' : 'Create Team'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};

export default TeamManager;
