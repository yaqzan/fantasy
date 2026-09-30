import React, { useState } from 'react';
import { createLeague, updateLeague, deleteLeague, generateWeeks, errorMessage } from '../services/api';

const inputClass = 'w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded-md text-white text-sm focus:outline-none focus:ring-2 focus:ring-nba-orange';
const labelClass = 'block text-xs font-medium text-gray-400 mb-1';

const Section = ({ title, children }) => (
  <div className="mb-5">
    <h4 className="text-sm font-semibold text-nba-orange mb-2">{title}</h4>
    {children}
  </div>
);

const NumberField = ({ label, value, onChange, min = 0, step, title }) => (
  <div title={title}>
    <label className={labelClass}>{label}</label>
    <input type="number" min={min} step={step} value={value} onChange={(e) => onChange(e.target.value)} className={inputClass} />
  </div>
);

// Create or edit a league: its rules, matchup schedule and notes. Teams are managed in the Team Manager.
const LeagueSettings = ({ mode, league, leagues, catalog, defaults, pointStats = {}, defaultPoints = {}, teams = [], onClose, onSaved, onDeleted }) => {
  const initial = mode === 'edit' ? league.settings : defaults;
  const [name, setName] = useState(mode === 'edit' ? league.name : '');
  const [settings, setSettings] = useState(() => {
    const s = JSON.parse(JSON.stringify(initial));
    // leagues saved before these keys existed
    s.elimination = { ...defaults?.elimination, ...s.elimination };
    s.waivers = { ...defaults?.waivers, ...s.waivers };
    s.scoring = { ...defaults?.scoring, ...s.scoring };
    return s;
  });
  const [stageText, setStageText] = useState((initial.elimination?.stage_weeks || []).join(', '));
  const [copyFrom, setCopyFrom] = useState('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);

  const set = (key, value) => setSettings(prev => ({ ...prev, [key]: value }));
  const setIn = (group, key, value) => setSettings(prev => ({ ...prev, [group]: { ...prev[group], [key]: value } }));

  const toggleCategory = (key) => {
    const has = settings.categories.includes(key);
    set('categories', has ? settings.categories.filter(c => c !== key) : [...settings.categories, key]);
  };

  const isPoints = settings.scoring.type === 'points';
  const setScoring = (type) => setSettings(prev => ({
    ...prev,
    scoring: { type, points: type === 'points' && !Object.keys(prev.scoring.points).length ? { ...defaultPoints } : prev.scoring.points },
  }));
  const setPoint = (stat, value) => setSettings(prev => ({ ...prev, scoring: { ...prev.scoring, points: { ...prev.scoring.points, [stat]: value } } }));

  const setWeek = (index, field, value) => {
    const schedule = settings.schedule.map((week, i) => i === index ? (field === 0 ? [value, week[1]] : [week[0], value]) : week);
    set('schedule', schedule);
  };

  const fillWeeks = async () => {
    if (settings.schedule.length && !window.confirm('Replace the current schedule with blank weeks from the NBA calendar?')) return;
    try {
      const data = await generateWeeks();
      set('schedule', data.weeks);
    } catch (err) {
      setError(errorMessage(err));
    }
  };

  const save = async (e) => {
    e.preventDefault();
    setSaving(true);
    setError(null);
    try {
      const toSave = { ...settings, elimination: { ...settings.elimination, stage_weeks: stageText } };
      const saved = mode === 'edit'
        ? await updateLeague(league.id, name, toSave)
        : await createLeague(name, toSave, copyFrom || null);
      onSaved(saved.id);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setSaving(false);
    }
  };

  const remove = async () => {
    if (!window.confirm(`Delete ${league.name} and its teams? This cannot be undone.`)) return;
    try {
      await deleteLeague(league.id);
      onDeleted(league.id);
    } catch (err) {
      setError(errorMessage(err));
    }
  };

  const teamAbbreviations = teams.map(t => t.abbreviation).filter(Boolean);

  return (
    <div className="fixed inset-0 bg-black bg-opacity-60 flex items-start justify-center z-50 overflow-y-auto py-8 px-4">
      <form onSubmit={save} className="bg-gray-800 rounded-lg p-6 w-full max-w-3xl shadow-2xl">
        <div className="flex items-center justify-between mb-5">
          <h3 className="text-xl font-semibold text-white">{mode === 'edit' ? 'League settings' : 'New league'}</h3>
          <button type="button" onClick={onClose} className="text-gray-400 hover:text-white text-2xl leading-none">&times;</button>
        </div>

        <Section title="League">
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            <div className="sm:col-span-2">
              <label className={labelClass}>Name</label>
              <input value={name} onChange={(e) => setName(e.target.value)} className={inputClass} placeholder="e.g. Office League 2026-27" required />
            </div>
            <div>
              <label className={labelClass}>Season</label>
              <input value={settings.season} onChange={(e) => set('season', e.target.value)} className={inputClass} placeholder="2026-27" />
            </div>
            <NumberField label="Teams" value={settings.num_teams} min={2} onChange={(v) => set('num_teams', v)} />
            <div>
              <label className={labelClass}>Your team's abbreviation</label>
              <input value={settings.my_team} onChange={(e) => set('my_team', e.target.value)} className={inputClass} list="league-team-abvs" placeholder="matches a team in the Team Manager" />
            </div>
            <div>
              <label className={labelClass}>Platform</label>
              <select value={settings.platform} onChange={(e) => set('platform', e.target.value)} className={inputClass}>
                <option value="fantrax">Fantrax</option>
                <option value="yahoo">Yahoo</option>
              </select>
            </div>
            {settings.platform === 'fantrax' && (
              <div>
                <label className={labelClass}>Fantrax league id</label>
                <input value={settings.fantrax_league_id} onChange={(e) => set('fantrax_league_id', e.target.value)} className={inputClass} placeholder="from the league URL" />
              </div>
            )}
            {mode === 'create' && leagues.length > 0 && (
              <div className="sm:col-span-3">
                <label className={labelClass}>Copy teams from (names only, rosters start empty)</label>
                <select value={copyFrom} onChange={(e) => setCopyFrom(e.target.value)} className={inputClass}>
                  <option value="">Start with no teams</option>
                  {leagues.map(l => <option key={l.id} value={l.id}>{l.name}</option>)}
                </select>
              </div>
            )}
          </div>
        </Section>

        <Section title="Scoring">
          <select value={settings.scoring.type} onChange={(e) => setScoring(e.target.value)} className={`${inputClass} mb-3 max-w-xs`}>
            <option value="categories">Categories (head to head)</option>
            <option value="points">Points</option>
          </select>
          {isPoints ? (
            <>
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                {Object.entries(pointStats).map(([stat, label]) => (
                  <NumberField key={stat} label={label} step="any" min={-100} value={settings.scoring.points[stat] ?? ''} onChange={(v) => setPoint(stat, v)} />
                ))}
              </div>
              <p className="text-xs text-gray-500 mt-2">Points per unit; blank = not scored. Every stat line collapses into one number, fantasy points.</p>
            </>
          ) : (
            <>
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
                {catalog.filter(cat => cat.key !== 'FPTS').map(cat => (
                  <label key={cat.key} title={cat.name} className={`flex items-center gap-2 px-2 py-1.5 rounded border text-sm cursor-pointer ${
                    settings.categories.includes(cat.key) ? 'border-nba-orange bg-gray-700 text-white' : 'border-gray-700 text-gray-400'}`}>
                    <input type="checkbox" checked={settings.categories.includes(cat.key)} onChange={() => toggleCategory(cat.key)}
                      className="h-4 w-4 text-nba-orange focus:ring-nba-orange border-gray-600 rounded bg-gray-700" />
                    <span className="truncate">{cat.name}{cat.inverse ? ' (neg)' : ''}</span>
                  </label>
                ))}
              </div>
              <p className="text-xs text-gray-500 mt-2">{settings.categories.length} categories. (neg): lower wins. All categories count equally.</p>
            </>
          )}
        </Section>

        <Section title="Roster">
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <NumberField label="Roster spots" value={settings.roster.size} min={1} onChange={(v) => setIn('roster', 'size', v)} />
            <NumberField label="Active spots" value={settings.roster.active} min={1} onChange={(v) => setIn('roster', 'active', v)} />
            <div className="col-span-2">
              <label className={labelClass}>Lineups</label>
              <select value={settings.roster.daily_lineups ? 'daily' : 'weekly'} onChange={(e) => setIn('roster', 'daily_lineups', e.target.value === 'daily')} className={inputClass}>
                <option value="daily">Daily substitutions (best active players each day count)</option>
                <option value="weekly">Weekly lineup (same starters all week)</option>
              </select>
            </div>
            <NumberField label="Min guards" value={settings.roster.min_guards} onChange={(v) => setIn('roster', 'min_guards', v)} />
            <NumberField label="Min forwards" value={settings.roster.min_forwards} onChange={(v) => setIn('roster', 'min_forwards', v)} />
            <NumberField label="Min centers" value={settings.roster.min_centers} onChange={(v) => setIn('roster', 'min_centers', v)} />
          </div>
          <p className="text-xs text-gray-500 mt-2">All minimums at 0 = all flex.</p>
        </Section>

        <Section title="Draft and waivers">
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <div>
              <label className={labelClass}>Draft type</label>
              <select value={settings.draft.type} onChange={(e) => setIn('draft', 'type', e.target.value)} className={inputClass}>
                <option value="auction">Auction</option>
                <option value="snake">Snake</option>
              </select>
            </div>
            <NumberField label="Auction budget ($)" value={settings.draft.budget} onChange={(v) => setIn('draft', 'budget', v)} />
            <div>
              <label className={labelClass}>Draft date</label>
              <input type="datetime-local" value={settings.draft.date} onChange={(e) => setIn('draft', 'date', e.target.value)} className={inputClass} />
            </div>
            <NumberField label="Waiver claims / week" value={settings.waivers.claims_per_week} onChange={(v) => setIn('waivers', 'claims_per_week', v)} />
            <NumberField
              label="Auction star premium"
              value={settings.draft.price_exponent ?? 1}
              min={0.2}
              step={0.05}
              onChange={(v) => setIn('draft', 'price_exponent', v)}
              title="Auction $ follow value above replacement raised to this power: 1 splits money in proportion to value, higher pays stars more. Fit it to the league's past drafts."
            />
          </div>
        </Section>

        <Section title="Guillotine (elimination stages)">
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <div className="col-span-2">
              <label className={labelClass}>Weeks per stage</label>
              <input value={stageText} onChange={(e) => setStageText(e.target.value)} className={inputClass} placeholder="e.g. 3, 3, 3, 2 (blank = no eliminations)" />
            </div>
            <NumberField label="Teams out per stage" value={settings.elimination.per_stage} onChange={(v) => setIn('elimination', 'per_stage', v)} />
            <div />
            <NumberField label="FAAB budget ($, season)" value={settings.waivers.faab_budget} onChange={(v) => setIn('waivers', 'faab_budget', v)} />
            <NumberField label="FAAB wins per stage" value={settings.waivers.faab_per_stage} onChange={(v) => setIn('waivers', 'faab_per_stage', v)} title="0 = no limit" />
          </div>
          <p className="text-xs text-gray-500 mt-2">
            Stages run over consecutive schedule weeks. After each stage but the last, the worst records over it are eliminated:
            mark them with Eliminate in the team's edit dialog and their players become free agents.
          </p>
        </Section>

        <Section title={`Matchup schedule (${settings.schedule.length} weeks)`}>
          <div className="flex flex-wrap gap-2 mb-2">
            <button type="button" onClick={fillWeeks} className="btn-secondary text-xs">Fill weeks from NBA calendar</button>
            <button type="button" onClick={() => set('schedule', [...settings.schedule, ['', '']])} className="btn-secondary text-xs">Add week</button>
          </div>
          {settings.schedule.length === 0 ? (
            <p className="text-xs text-gray-500">No weeks yet. The optimizer needs each week's start date and opponent.</p>
          ) : (
            <div className="max-h-72 overflow-y-auto border border-gray-700 rounded">
              {settings.schedule.map(([start, opponent], i) => (
                <div key={i} className="flex items-center gap-2 px-2 py-1 border-b border-gray-700 last:border-b-0">
                  <span className="text-xs text-gray-500 w-14">Week {i + 1}</span>
                  <input type="date" value={start} onChange={(e) => setWeek(i, 0, e.target.value)} className={`${inputClass} py-1 w-40`} />
                  <input value={opponent} onChange={(e) => setWeek(i, 1, e.target.value)} list="league-team-abvs" placeholder="opponent abbreviation" className={`${inputClass} py-1 flex-1`} />
                  <button type="button" onClick={() => set('schedule', settings.schedule.filter((_, j) => j !== i))} className="text-gray-500 hover:text-red-400 px-1">&times;</button>
                </div>
              ))}
            </div>
          )}
          <datalist id="league-team-abvs">
            {teamAbbreviations.map(abv => <option key={abv} value={abv} />)}
          </datalist>
        </Section>

        <Section title="Notes">
          <textarea value={settings.notes} onChange={(e) => set('notes', e.target.value)} rows={4} className={inputClass} placeholder="Prizes, tie-breakers, anything else" />
        </Section>

        {error && <p className="text-red-400 text-sm mb-3">{error}</p>}

        <div className="flex items-center justify-between">
          <div>
            {mode === 'edit' && (
              <button type="button" onClick={remove} className="text-sm text-red-400 hover:text-red-300">Delete league</button>
            )}
          </div>
          <div className="flex gap-3">
            <button type="button" onClick={onClose} className="btn-secondary" disabled={saving}>Cancel</button>
            <button type="submit" className="btn-primary" disabled={saving}>{saving ? 'Saving...' : mode === 'edit' ? 'Save' : 'Create league'}</button>
          </div>
        </div>
      </form>
    </div>
  );
};

export default LeagueSettings;
