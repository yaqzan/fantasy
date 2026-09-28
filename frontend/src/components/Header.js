import React from 'react';

// One line of the league's rules, e.g. "11 cats · 10 spots (6 active, daily) · $200 auction Oct 3".
const leagueSummary = (league) => {
  if (!league) return '';
  const s = league.settings;
  const parts = [
    `${s.categories.length} cats`,
    `${s.num_teams} teams`,
    `${s.roster.size} spots (${s.roster.active} active, ${s.roster.daily_lineups ? 'daily' : 'weekly'})`,
  ];
  if (s.draft.type === 'auction') {
    let draft = `$${s.draft.budget} auction`;
    if (s.draft.date) {
      const d = new Date(s.draft.date);
      if (!isNaN(d)) draft += ` ${d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}`;
    }
    parts.push(draft);
  }
  return parts.join(' · ');
};

const Header = ({ leagues = [], currentLeague, onSwitchLeague, onEditLeague, onNewLeague }) => {
  return (
    <header className="bg-nba-blue shadow-lg">
      <div className="max-w-full mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex flex-wrap items-center justify-between gap-3 py-3">
          <div className="flex items-center">
            <div className="w-8 h-8 bg-nba-orange rounded-full flex items-center justify-center mr-3">
              <span className="text-white font-bold text-lg">🏀</span>
            </div>
            <h1 className="text-xl font-bold text-white">NBA Fantasy Dashboard</h1>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            {currentLeague && (
              <span className="hidden lg:inline text-gray-300 text-xs mr-2">{leagueSummary(currentLeague)}</span>
            )}
            {leagues.length > 0 && (
              <select
                value={currentLeague?.id || ''}
                onChange={(e) => onSwitchLeague(e.target.value)}
                className="px-3 py-1.5 bg-gray-800 border border-gray-600 rounded-md text-white text-sm focus:outline-none focus:ring-2 focus:ring-nba-orange max-w-xs"
                aria-label="League"
              >
                {leagues.map(league => (
                  <option key={league.id} value={league.id}>{league.name}</option>
                ))}
              </select>
            )}
            {currentLeague && (
              <button onClick={onEditLeague} className="px-3 py-1.5 bg-gray-800 border border-gray-600 rounded-md text-gray-200 text-sm hover:bg-gray-700">
                Settings
              </button>
            )}
            <button onClick={onNewLeague} className="px-3 py-1.5 bg-nba-orange rounded-md text-white text-sm hover:bg-orange-600">
              New league
            </button>
          </div>
        </div>
      </div>
    </header>
  );
};

export default Header;
