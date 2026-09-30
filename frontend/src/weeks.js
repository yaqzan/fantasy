import React from 'react';

// Fantasy weeks come from the league (LeagueConfig.weeks(): start, end, days, opponent, playoffs).
export const parseDay = (iso) => {
  const [y, m, d] = iso.split('-').map(Number);
  return new Date(y, m - 1, d);
};
export const shortDate = (iso) => parseDay(iso).toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
export const weekdayLetter = (iso) => parseDay(iso).toLocaleDateString('en-US', { weekday: 'short' }).slice(0, 2);
const isoDay = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;

// "Oct 26-Nov 1" style range.
export const weekRange = ({ start, end }) => {
  const [a, b] = [parseDay(start), parseDay(end)];
  const month = (d) => d.toLocaleDateString('en-US', { month: 'short' });
  return a.getMonth() === b.getMonth() ? `${month(a)} ${a.getDate()}-${b.getDate()}` : `${month(a)} ${a.getDate()} - ${month(b)} ${b.getDate()}`;
};

// Every day of a week, so each player's games line up in the same columns.
export const weekDays = (start, end) => {
  const days = [];
  for (let d = parseDay(start); d <= parseDay(end); d.setDate(d.getDate() + 1)) days.push(isoDay(d));
  return days;
};

// The week to open on: the one being played, or the next once today is its last day (its lineups
// are set). Before the season the first week, after it the last.
export const defaultWeekStart = (weeks) => {
  if (!weeks?.length) return null;
  const today = isoDay(new Date());
  const i = weeks.findIndex(w => today <= w.end);
  if (i === -1) return weeks[weeks.length - 1].start;
  return weeks[i].end === today && weeks[i + 1] ? weeks[i + 1].start : weeks[i].start;
};

export const selectClass = 'px-3 py-1.5 bg-gray-700 border border-gray-600 rounded-md text-white text-sm focus:outline-none focus:ring-2 focus:ring-nba-orange focus:border-transparent';

// Week picker: number, date range, day count when it isn't 7, playoffs.
export const WeekSelect = ({ weeks, value, onChange }) => (
  <div className="flex items-center space-x-2">
    <span className="text-sm text-gray-300">Week:</span>
    <select value={value || ''} onChange={(e) => onChange(e.target.value || null)} className={selectClass}>
      {!weeks?.length && <option value="">This week</option>}
      {(weeks || []).map(w => (
        <option key={w.start} value={w.start}>
          Week {w.week}: {weekRange(w)}{w.days !== 7 ? ` (${w.days} days)` : ''}{w.playoffs ? ' · playoffs' : ''}
        </option>
      ))}
    </select>
  </div>
);

// Keeps a stored week only while the league's schedule still has it.
export const validWeek = (weeks) => (picked) => {
  const out = { ...picked };
  if (out.week && !(weeks || []).some(w => w.start === out.week)) delete out.week;
  return out;
};
