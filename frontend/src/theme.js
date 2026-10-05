// Colour schemes: the picker in the header sets data-theme on <html>; the colours themselves are
// CSS variables defined per scheme in tailwind.config.js (THEMES). Ids here must match the ids there.
export const THEMES = [
  ['podium', 'Podium'], ['hardwood', 'Hardwood'], ['banner', 'Banner'], ['pressbox', 'Press Box'],
];
export const DEFAULT_THEME = 'podium';
const KEY = 'fantasy.theme';

export const validTheme = (id) => (THEMES.some(([key]) => key === id) ? id : DEFAULT_THEME);

export function getTheme() {
  try { return validTheme(localStorage.getItem(KEY)); } catch (e) { return DEFAULT_THEME; }
}

export function applyTheme(id, { save = false } = {}) {
  const theme = validTheme(id);
  document.documentElement.dataset.theme = theme;
  // The browser chrome (mobile address bar) follows the page colour.
  const meta = document.querySelector('meta[name="theme-color"]');
  if (meta) {
    const page = getComputedStyle(document.documentElement).getPropertyValue('--gray-900').trim();
    if (page) meta.setAttribute('content', `rgb(${page.split(' ').join(', ')})`);
  }
  if (save) {
    try { localStorage.setItem(KEY, theme); } catch (e) { /* storage blocked */ }
  }
  return theme;
}
