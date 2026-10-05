import { auctionState, adjusted, shareMaxOf, earlyMarkup, roomPrice } from './auction';

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

test('share max never falls as the value rises (the $15 tier edge)', () => {
  const shares = [[40, 0.85], [15, 0.8], [0, 1.0]];
  const max = (v) => Math.max(1, ...shareMaxOf(shares, v));
  expect(max(14)).toBe(14);
  expect(max(15)).toBe(14);
  expect(max(39)).toBe(31);
  expect(max(40)).toBe(34);
  for (let v = 1; v < 120; v += 1) expect(max(v + 1)).toBeGreaterThanOrEqual(max(v));
});

test('progress is the share of spots filled', () => {
  expect(base().progress).toBe(0);
  expect(base({ A: [1, 60], B: [2, 50], C: [1, 40] }).progress).toBeCloseTo(0.5, 5);
});

test('early markup: $5-25 x1.6 and $26+ x1.1 until 20% of the draft, then back to x1', () => {
  expect(earlyMarkup(10, 0)).toBe(1.6);
  expect(earlyMarkup(10, 0.2)).toBe(1.6);
  expect(earlyMarkup(10, 0.275)).toBeCloseTo(1.3, 5);
  expect(earlyMarkup(10, 0.35)).toBe(1);
  expect(earlyMarkup(60, 0.1)).toBe(1.1);
  expect(earlyMarkup(60, 0.25)).toBe(1);
  expect(earlyMarkup(3, 0)).toBe(1);
  expect(earlyMarkup(null, 0)).toBe(1);
});

test('room price = likely x factor x early markup', () => {
  expect(roomPrice(10, 1, 0)).toBe(16);
  expect(roomPrice(10, 1, 0.5)).toBe(10);
  expect(roomPrice(11, 0.8, 0)).toBe(14);   // (1 + 10 x .8) x 1.6 = 14.4
  expect(roomPrice(80, 1, 0)).toBe(88);
  expect(roomPrice(1, 1, 0)).toBe(1);
  expect(roomPrice(null, 1, 0)).toBe(null);
});
