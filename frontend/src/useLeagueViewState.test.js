import { renderHook, act } from '@testing-library/react';
import useLeagueViewState from './useLeagueViewState';

// Switching leagues remounts each tab (<main key={leagueId}>), so a new hook instance per league.
const mount = (leagueId, categories) => renderHook(() => useLeagueViewState(
  leagueId, 'players', { statType: 'proj', punts: [] },
  (picked) => ({ ...picked, ...(picked.punts && { punts: picked.punts.filter(c => categories.includes(c)) }) }),
));

beforeEach(() => localStorage.clear());

test('each league keeps its own picks across a switch and back', () => {
  const wsop = mount('wsop', ['PTS', 'TECH', 'BLKA']);
  act(() => wsop.result.current[1]({ punts: ['TECH', 'BLKA'], statType: 'season' }));
  wsop.unmount();

  const courtside = mount('courtside', ['FPTS']);
  expect(courtside.result.current[0]).toEqual({ statType: 'proj', punts: [] });  // nothing leaks across
  act(() => courtside.result.current[1]({ statType: '10' }));
  courtside.unmount();

  const back = mount('wsop', ['PTS', 'TECH', 'BLKA']);
  expect(back.result.current[0]).toEqual({ statType: 'season', punts: ['TECH', 'BLKA'] });
});

test('stored picks the league no longer has are dropped', () => {
  const before = mount('wsop', ['PTS', 'TECH']);
  act(() => before.result.current[1]({ punts: ['TECH'] }));
  before.unmount();
  const after = mount('wsop', ['PTS']);  // TECH removed from the league's categories
  expect(after.result.current[0].punts).toEqual([]);
});

test('defaults that change still apply until the user picks', () => {
  const { result } = renderHook(({ d }) => useLeagueViewState('l', 't', { statType: d }), { initialProps: { d: 'proj' } });
  expect(result.current[0].statType).toBe('proj');
});
