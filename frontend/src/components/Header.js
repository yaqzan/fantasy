import React from 'react';

// One line of the league's rules, e.g. "11 cats · 10 spots (6 active, daily) · $200 auction Oct 3".
const leagueSummary = (league) => {
  if (!league) return '';
  const s = league.settings;
  const parts = [
    s.scoring?.type === 'points' ? 'points' : `${s.categories.length} cats`,
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

// Guillotine leagues: "Stage 2/7 · wk 1 of 3 · 12 teams, 2 out · trades open".
const stageSummary = (stage) => {
  if (stage.finished) return 'Guillotine over';
  const parts = [`Stage ${stage.stage}/${stage.stages}`];
  parts.push(stage.started ? `wk ${stage.week_in_stage} of ${stage.weeks}` : 'not started');
  parts.push(stage.final ? `final, ${stage.teams} teams` : `${stage.teams} teams, ${stage.eliminated} out`);
  if (stage.trade_window) parts.push('trades open');
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
            {currentLeague?.stage && (
              <span className="text-xs px-2 py-1 rounded bg-red-900/60 border border-red-700 text-red-100"
                title="Guillotine: the worst records over each stage are eliminated; records reset every stage">
                {stageSummary(currentLeague.stage)}
              </span>
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
