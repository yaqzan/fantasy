import { bidEdge, bidColor } from './bidColor';

test('even prices are neutral, big gaps saturate, sign follows max minus likely', () => {
  expect(bidEdge(40, 40)).toBe(0);
  expect(bidColor(40, 40)).toBe('rgb(209, 213, 219)');
  expect(bidEdge(53, 40)).toBeGreaterThan(0.7);
  expect(bidColor(14, 1)).toBe('rgb(74, 222, 128)');
  expect(bidColor(31, 75)).toBe('rgb(249, 115, 22)');
  expect(bidEdge(90, 102)).toBeLessThan(0);
  expect(bidEdge(90, 102)).toBeGreaterThan(-0.5);
});

test('a few dollars on an expensive player stays near neutral; no likely price is neutral', () => {
  expect(Math.abs(bidEdge(94, 91))).toBeLessThan(0.15);
  expect(bidEdge(20, null)).toBe(0);
});
