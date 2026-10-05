import React, { useState } from 'react';
import Logo from './Logo';
import { THEMES, applyTheme, getTheme } from '../theme';

// One line of the league's rules, e.g. "11 cats · 10 spots (6 active, daily) · $200 auction Oct 3".
const leagueSummary = (league) => {
  if (!league) return '';
  const s = league.settings;
  const parts = [
    s.scoring?.type === 'points' ? 'points' : `${s.categories.length} cats`,
    `${s.num_teams} teams`,
    `${s.roster.size} spots (${s.roster.active} active${s.roster.slots?.length ? ' in slots' : ''}, ${s.roster.daily_lineups ? 'daily' : 'weekly'})`,
  ];
  if (s.draft.type !== 'auction') parts.push(`${s.draft.type} draft`);
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

// Colour scheme picker: one dot per scheme, drawn in that scheme's own page and accent colours
// (data-theme on the button scopes the CSS variables to it).
const ThemePicker = () => {
  const [theme, setTheme] = useState(getTheme);
  return (
    <div className="flex items-center gap-1.5 mr-1" role="radiogroup" aria-label="Colour scheme">
      {THEMES.map(([id, label]) => (
        <button
          key={id}
          data-theme={id}
          role="radio"
          aria-checked={theme === id}
          aria-label={label}
          title={`${label} colours`}
          onClick={() => setTheme(applyTheme(id, { save: true }))}
          className={`w-5 h-5 rounded-full flex items-center justify-center border ${theme === id ? 'ring-2 ring-offset-1 ring-offset-transparent' : 'opacity-70 hover:opacity-100'}`}
          style={{ background: 'rgb(var(--gray-900))', borderColor: 'rgb(var(--gray-500))', '--tw-ring-color': 'rgb(var(--accent))' }}
        >
          <span className="w-2 h-2 rounded-full" style={{ background: 'rgb(var(--accent))' }} />
        </button>
      ))}
    </div>
  );
};

const Header = ({ leagues = [], currentLeague, onSwitchLeague, onEditLeague, onNewLeague }) => {
  // Phones: logo, league picker and a menu button on one row; the rest lives in the menu.
  const [menu, setMenu] = useState(false);
  const stage = currentLeague?.stage && (
    <span className="text-xs px-2 py-1 rounded bg-red-900/60 border border-red-700 text-red-100"
      title="Guillotine: the worst records over each stage are eliminated; records reset every stage">
      {stageSummary(currentLeague.stage)}
    </span>
  );
  const buttons = (
    <>
      {currentLeague && (
        <button onClick={() => { setMenu(false); onEditLeague(); }} className="px-3 py-1.5 bg-gray-800 border border-gray-600 rounded-md text-gray-200 text-sm hover:bg-gray-700">
          Settings
        </button>
      )}
      <button onClick={() => { setMenu(false); onNewLeague(); }} className="px-3 py-1.5 bg-nba-orange rounded-md text-onaccent text-sm hover:opacity-90 whitespace-nowrap">
        New league
      </button>
    </>
  );
  return (
    <header className="bg-head border-b border-gray-700 relative">
      <div className="max-w-full mx-auto px-3 sm:px-6 lg:px-8">
        <div className="flex items-center gap-2 py-2 sm:py-3">
          <div className="flex items-center min-w-0">
            <Logo className="w-8 h-8 sm:w-9 sm:h-9 sm:mr-3 flex-shrink-0" />
            <h1 className="hidden sm:block text-xl font-bold text-white whitespace-nowrap">NBA Fantasy Dashboard</h1>
          </div>

          <div className="hidden sm:flex items-center gap-2 ml-auto">
            <ThemePicker />
            {currentLeague && (
              <span className="hidden lg:inline text-gray-300 text-xs mr-2">{leagueSummary(currentLeague)}</span>
            )}
            {stage}
          </div>
          {leagues.length > 0 && (
            <select
              value={currentLeague?.id || ''}
              onChange={(e) => onSwitchLeague(e.target.value)}
              className="flex-1 sm:flex-none min-w-0 sm:max-w-xs px-2 sm:px-3 py-1.5 bg-gray-800 border border-gray-600 rounded-md text-white text-sm focus:outline-none focus:ring-2 focus:ring-nba-orange"
              aria-label="League"
            >
              {leagues.map(league => (
                <option key={league.id} value={league.id}>{league.name}</option>
              ))}
            </select>
          )}
          <div className="hidden sm:flex items-center gap-2">{buttons}</div>
          <button onClick={() => setMenu(!menu)} aria-label="Menu" aria-expanded={menu}
                  className={`sm:hidden ${leagues.length ? '' : 'ml-auto'} w-9 h-9 flex-none flex items-center justify-center rounded-md border border-gray-600 text-gray-200 ${menu ? 'bg-gray-700' : 'bg-gray-800'}`}>
            <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 24 24"><circle cx="5" cy="12" r="2" /><circle cx="12" cy="12" r="2" /><circle cx="19" cy="12" r="2" /></svg>
          </button>
        </div>
      </div>
      {menu && (
        <>
          <div className="sm:hidden fixed inset-0 z-40" onClick={() => setMenu(false)} />
          <div className="sm:hidden absolute right-3 top-full mt-1 z-50 w-64 rounded-lg bg-gray-800 border border-gray-600 shadow-2xl p-3 space-y-3">
            <div className="flex items-center justify-between">
              <span className="text-xs text-gray-400">Colours</span>
              <ThemePicker />
            </div>
            {stage}
            <div className="flex items-center justify-end gap-2">{buttons}</div>
          </div>
        </>
      )}
    </header>
  );
};

export default Header;
