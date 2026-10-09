import { cellText, zTint, keepRow } from './dailyLeaders';

const line = { PTS: 22, FGM: 6, FGA: 17, FG3M: 3, FTM: 7, FTA: 8, AST: 2, TOV: 0, PLUS_MINUS: 5, W: 1 };

test('ratio columns show made-attempted or a rate', () => {
  expect(cellText('FG%', line)).toBe('6-17');
  expect(cellText('FT', line)).toBe('7-8');
  expect(cellText('TS%', line)).toBe('.536');  // 22 / (2 * (17 + 0.44 * 8))
  expect(cellText('PPS', { ...line, FGA: 0 })).toBe('-');
});

test('derived counting categories', () => {
  expect(cellText('NFT', line)).toBe(6);
  expect(cellText('AST-TOV', line)).toBe(2);
  expect(cellText('PLUS_MINUS', line)).toBe('+5');
  expect(cellText('WIN%', { ...line, W: null })).toBe('…');
});

test('tint grows with |z| and stays off near zero', () => {
  expect(zTint(0.3)).toBe('');
  expect(zTint(null)).toBe('');
  expect(zTint(2.5)).toContain('green');
  expect(zTint(-1.2)).toContain('red-500/25');
});

test('owner filters', () => {
  expect(keepRow('all', { owner: 'taken' })).toBe(true);
  expect(keepRow('free', { owner: 'taken' })).toBe(false);
  expect(keepRow('mine', { owner: 'mine' })).toBe(true);
});
