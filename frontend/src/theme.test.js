import { applyTheme, getTheme, validTheme, DEFAULT_THEME } from './theme';

beforeEach(() => {
  localStorage.clear();
  delete document.documentElement.dataset.theme;
});

test('an unknown or missing scheme falls back to the default', () => {
  expect(validTheme('banner')).toBe('banner');
  expect(validTheme('neon')).toBe(DEFAULT_THEME);
  expect(getTheme()).toBe(DEFAULT_THEME);
  localStorage.setItem('fantasy.theme', 'neon');
  expect(getTheme()).toBe(DEFAULT_THEME);
});

test('picking a scheme sets data-theme and is remembered', () => {
  expect(applyTheme('pressbox', { save: true })).toBe('pressbox');
  expect(document.documentElement.dataset.theme).toBe('pressbox');
  expect(getTheme()).toBe('pressbox');
});

test('applying at startup does not write to storage', () => {
  applyTheme('hardwood');
  expect(localStorage.getItem('fantasy.theme')).toBeNull();
});
