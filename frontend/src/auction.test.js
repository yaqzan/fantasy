import { auctionState, adjusted } from './auction';

// 2 teams, $100, 3 spots: six players worth drafting and two spares.
const likely = { A: 60, B: 50, C: 40, D: 30, E: 12, F: 8, G: 1, H: 1 };
const teams = [{ id: 1 }, { id: 2 }];
const base = (picks = {}) => auctionState({
  players: Object.keys(likely).map(name => ({
    name, drafted: name in picks, fantasy_team: name in picks ? { id: picks[name][0] } : null, draft_price: picks[name]?.[1] ?? null,
  })),
  likely, teams, budget: 100, rosterSize: 3,
});

test('nothing bought, or picks with no price: the factor is 1', () => {
  expect(base().factor).toBe(1);
  expect(base({ A: [1, null] }).factor).toBe(1);
});

test('a pick at its likely price leaves the factor at 1', () => {
  expect(base({ A: [1, 60] }).factor).toBeCloseTo(1, 5);
});

test('overpaying early makes the rest cheaper, a bargain makes it dearer', () => {
  const over = base({ A: [1, 90] }).factor;
  const under = base({ A: [1, 30] }).factor;
  expect(over).toBeLessThan(0.85);
  expect(under).toBeGreaterThan(1.15);
  expect(adjusted(40, over)).toBeLessThan(40);
  expect(adjusted(40, under)).toBeGreaterThan(40);
  expect(adjusted(1, over)).toBe(1);
});

test('team money, open spots and the most it can bid', () => {
  const { teams: t, left, open } = base({ A: [1, 90], G: [1, 2] });
  expect(t[1]).toMatchObject({ spent: 92, left: 8, open: 1, cap: 8 });
  expect(t[2]).toMatchObject({ left: 100, open: 3, cap: 98 });
  expect(left).toBe(108);
  expect(open).toBe(4);
});

test('the factor stays inside its limits', () => {
  expect(base({ A: [1, 1], B: [2, 1], C: [1, 1] }).factor).toBeLessThanOrEqual(1.5);
  expect(base({ F: [1, 99] }).factor).toBeGreaterThanOrEqual(0.5);
});
