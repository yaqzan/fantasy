import React, { useState, useEffect } from 'react';

const DraftModal = ({ player, teams, onClose, onDraft, onUndraft, onUpdatePlayer, isDrafted }) => {
  const [selectedTeamId, setSelectedTeamId] = useState('');
  const [isInjured, setIsInjured] = useState(false);
  const [loading, setLoading] = useState(false);

  // Initialize form with current player data
  useEffect(() => {
    if (player) {
      setSelectedTeamId(player.fantasy_team?.id ? String(player.fantasy_team.id) : '');
      setIsInjured(player.is_injured || false);
    }
  }, [player]);

  const handleSave = async () => {
    try {
      setLoading(true);
      
      // Update injured status if it changed
      if (isInjured !== player.is_injured) {
        await onUpdatePlayer(player.name, isInjured);
      }
      
      if (isDrafted) {
        // If currently drafted, we can either undraft or change team
        if (!selectedTeamId) {
          // No team selected = undraft
          await onUndraft(player.name);
        } else if (selectedTeamId !== String(player.fantasy_team?.id || '')) {
          // Different team selected = change team
          await onDraft(player.name, parseInt(selectedTeamId));
        }
      } else {
        // If not drafted, draft to selected team
        if (selectedTeamId) {
          await onDraft(player.name, parseInt(selectedTeamId));
        }
      }
      
      onClose();
    } catch (error) {
      console.error('Error updating player:', error);
      alert('Error updating player. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
      <div className="bg-gray-800 rounded-lg p-6 w-full max-w-md">
        <h3 className="text-lg font-semibold text-white mb-4">
          Edit {player.name}
        </h3>
        
        <div className="mb-6">
          <div className="bg-gray-700 rounded-lg p-4">
            <div className="grid grid-cols-2 gap-4 text-sm">
              <div>
                <span className="text-gray-400">Position:</span>
                <span className="text-white ml-2">{player.position}</span>
              </div>
              <div>
                <span className="text-gray-400">Team:</span>
                <span className="text-white ml-2">{player.team}</span>
              </div>
              <div>
                <span className="text-gray-400">Overall Rank:</span>
                <span className="text-white ml-2">{player.overall_rank}</span>
              </div>
              <div>
                <span className="text-gray-400">Auction Value:</span>
                <span className="text-white ml-2">${player.auction_value}</span>
              </div>
            </div>
          </div>
        </div>
        
        <div className="mb-6">
          <label className="block text-sm font-medium text-gray-300 mb-2">
            Fantasy Team
          </label>
          <select
            value={selectedTeamId}
            onChange={(e) => setSelectedTeamId(e.target.value)}
            className="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded-md text-white focus:outline-none focus:ring-2 focus:ring-nba-orange"
          >
            <option value="">Available (Not Drafted)</option>
            {teams
              .sort((a, b) => (a.abbreviation || '').localeCompare(b.abbreviation || ''))
              .map((team) => (
                <option key={team.id} value={String(team.id)}>
                  {team.abbreviation ? `${team.abbreviation} [${team.name}]` : team.name}
                </option>
              ))}
          </select>
        </div>

        <div className="mb-6">
          <label className="flex items-center">
            <input
              type="checkbox"
              checked={isInjured}
              onChange={(e) => setIsInjured(e.target.checked)}
              className="h-4 w-4 text-nba-orange focus:ring-nba-orange border-gray-600 rounded bg-gray-700"
            />
            <span className="ml-2 text-sm text-gray-300">Injured</span>
          </label>
        </div>
        
        <div className="flex justify-end space-x-3">
          <button
            onClick={onClose}
            className="btn-secondary"
            disabled={loading}
          >
            Cancel
          </button>
          <button
            onClick={handleSave}
            className="btn-primary"
            disabled={loading}
          >
            {loading ? 'Saving...' : 'Save Changes'}
          </button>
        </div>
      </div>
    </div>
  );
};

export default DraftModal;
