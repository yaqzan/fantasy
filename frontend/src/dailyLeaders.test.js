import { cellText, zTint, keepRow, sortRows, isPickup, orderColumns, paceMark, valueClass, inGame, toggleGame } from './dailyLeaders';

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

test('pickups: free agents with a positive signal, best pace first', () => {
  const rows = [
    { owner: 'free', pace: 1.6, pace_signal: 'up' },
    { owner: 'taken', pace: 3, pace_signal: 'up' },
    { owner: 'free', pace: 0.7, minutes_up: true },
    { owner: 'free', pace: 0.2, minutes_up: true },
    { owner: 'free', pace: -2, pace_signal: 'down' },
    { owner: 'free', pace: null, streak: 'hot' },
  ];
  const kept = sortRows('pickups', rows.filter(p => keepRow('pickups', p)));
  expect(kept.map(p => p.pace)).toEqual([1.6, 0.7, null]);
});

test('preseason pickups: pace only, rotation players only', () => {
  expect(isPickup({ owner: 'free', preseason: true, pace_signal: 'up', min_usual: 20 })).toBe(true);
  expect(isPickup({ owner: 'free', preseason: true, pace_signal: 'up', min_usual: 8 })).toBe(false);
  expect(isPickup({ owner: 'free', preseason: true, minutes_up: true, pace: 1, min_usual: 20 })).toBe(false);
});

test('pace sort', () => {
  const rows = [{ pace: 0.1 }, { pace: 2 }, { pace: null }];
  expect(sortRows('all', rows, 'pace').map(r => r.pace)).toEqual([2, 0.1, null]);
  expect(sortRows('all', rows, 'val')).toBe(rows);
});

test('phone-first column order', () => {
  const keys = (ks) => orderColumns(ks.map(key => ({ key }))).map(c => c.key);
  expect(keys(['AST-TOV', 'REB', 'BLK', 'STL', 'NFT', 'FG3M', 'TECH', 'TS%', 'PTS']))
    .toEqual(['PTS', 'REB', 'AST-TOV', 'STL', 'BLK', 'NFT', 'FG3M', 'TECH', 'TS%']);
  expect(keys(['FG%', 'FT%', 'FG3M', 'PTS', 'REB', 'AST', 'STL', 'BLK', 'TOV']))
    .toEqual(['PTS', 'REB', 'AST', 'STL', 'BLK', 'FG%', 'FT%', 'FG3M', 'TOV']);
});

test('pace mark: own colours, strength steps, grey when it disagrees with the night', () => {
  expect(paceMark({ pace_signal: null }, false)).toBeNull();
  const faint = paceMark({ pace_signal: 'up', pace: 1.8, value: 4 }, false);
  expect(faint.glyph).toBe('▲');
  expect(faint.cls).toContain('sky');
  expect(faint.cls).toContain('opacity-60');
  expect(paceMark({ pace_signal: 'up', pace: 3.8, value: 4 }, false).glyph).toBe('▲▲');
  const weakNight = paceMark({ pace_signal: 'up', pace: 2.6, value: -5.3, preseason: true }, false);
  expect(weakNight.glyph).toBe('△');
  expect(weakNight.cls).toContain('gray');
  expect(paceMark({ pace_signal: 'down', pace: -2, value: -1 }, false).cls).toContain('amber');
  expect(paceMark({ pace_signal: 'up', pace: 2, value: 12 }, true).cls).toContain('sky');  // points: no zero line
});

test('value colour and pickups skip nights that hurt', () => {
  expect(valueClass(4, false)).toBe('text-green-300');
  expect(valueClass(-1.5, false)).toBe('text-red-400');
  expect(valueClass(-9, true)).toBe('text-white');
  expect(isPickup({ owner: 'free', preseason: true, pace_signal: 'up', min_usual: 20, value: -5, z: { PTS: -1 } })).toBe(false);
});

test('game filter: its two teams; tap toggles on, moves, and off', () => {
  const game = { id: 'g1', teams: [{ abbr: 'BOS' }, { abbr: 'CLE' }] };
  expect(inGame(game, { team: 'CLE' })).toBe(true);
  expect(inGame(game, { team: 'MIA' })).toBe(false);
  expect(inGame(null, { team: 'MIA' })).toBe(true);
  expect(toggleGame(null, 'g1')).toBe('g1');
  expect(toggleGame('g1', 'g2')).toBe('g2');
  expect(toggleGame('g2', 'g2')).toBeNull();
});
