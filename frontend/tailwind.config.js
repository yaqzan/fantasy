const colors = require('tailwindcss/colors');
const plugin = require('tailwindcss/plugin');

// Colour schemes. Components keep their Tailwind classes (bg-gray-800, text-white, text-green-400...);
// those classes read CSS variables, and each scheme sets the variables under [data-theme="<id>"].
// The first scheme is the default (:root). Ids and labels are repeated in src/theme.js for the picker.
// gray runs 900 (page) -> 800 (panel) -> 700 (rule) ... -> 100 (text); white is the strongest text.
const THEMES = {
  podium: {
    gray: { 100: '#F0F2F5', 200: '#DEE2E7', 300: '#C2C8D0', 400: '#949CA7', 500: '#6A727D', 600: '#3A4048', 700: '#262A30', 800: '#15171B', 900: '#0C0D0F' },
    white: '#FFFFFF', accent: '#FF7A1A', onaccent: '#0C0D0F', head: '#0C0D0F', th: '#1A1D22', onth: '#C2C8D0',
    'row-mine': '#2E2212', 'row-hover': '#20242A',
  },
  hardwood: {
    gray: { 100: '#F5EEE5', 200: '#E6DBCE', 300: '#CDBFAF', 400: '#A39382', 500: '#7A6A59', 600: '#4A3B2D', 700: '#33281E', 800: '#1F1812', 900: '#15100C' },
    white: '#FFF8EF', accent: '#F2731D', onaccent: '#1A120C', head: '#1F1812', th: '#2C2219', onth: '#E6DBCE',
    'row-mine': '#3A2712', 'row-hover': '#2A2118',
  },
  banner: {
    gray: { 100: '#EFF3F9', 200: '#DCE4F0', 300: '#BECADC', 400: '#8FA1BD', 500: '#62779B', 600: '#2B467A', 700: '#1C3157', 800: '#0F1D36', 900: '#0A1426' },
    white: '#FFFFFF', accent: '#E9B949', onaccent: '#0A1426', head: '#12284D', th: '#16305A', onth: '#E9B949',
    'row-mine': '#303439', 'row-hover': '#18294A',
  },
  // Light: the gray scale runs the other way, and the status colours are mirrored (see LIGHT below).
  pressbox: {
    light: true,
    gray: { 100: '#1B1B1B', 200: '#2E2B26', 300: '#4A453D', 400: '#6E675B', 500: '#8A8275', 600: '#CFC6B5', 700: '#E6DFD1', 800: '#FFFFFF', 900: '#F7F3EB' },
    white: '#111111', accent: '#F06A1A', onaccent: '#FFFFFF', head: '#FFFFFF', th: '#E6DFD1', onth: '#1B1B1B',
    'row-mine': '#FDEBDD', 'row-hover': '#F1ECE2',
  },
};

// Status and chart colours the components use. On a light scheme each shade swaps with its
// opposite (300 <-> 700, 900 <-> 100), so pale text and dark tints written for a dark page still read.
const FAMILIES = ['red', 'green', 'emerald', 'amber', 'yellow', 'orange', 'sky', 'cyan', 'blue', 'teal', 'rose', 'purple', 'pink', 'indigo'];
const SHADES = [50, 100, 200, 300, 400, 500, 600, 700, 800, 900, 950];

const triplet = (hex) => [1, 3, 5].map(i => parseInt(hex.slice(i, i + 2), 16)).join(' ');
const asVar = (name) => `rgb(var(--${name}) / <alpha-value>)`;

const themeVars = (theme) => {
  const vars = {};
  Object.entries(theme.gray).forEach(([shade, hex]) => { vars[`--gray-${shade}`] = triplet(hex); });
  ['white', 'accent', 'onaccent', 'head', 'th', 'onth', 'row-mine', 'row-hover'].forEach(k => { vars[`--${k}`] = triplet(theme[k]); });
  FAMILIES.forEach(family => SHADES.forEach(shade => {
    vars[`--${family}-${shade}`] = triplet(colors[family][theme.light ? 1000 - shade : shade]);
  }));
  return vars;
};

const base = {};
Object.entries(THEMES).forEach(([id, theme], i) => {
  base[i === 0 ? `:root, [data-theme="${id}"]` : `[data-theme="${id}"]`] = themeVars(theme);
});

const family = (name, shades) => Object.fromEntries(shades.map(shade => [shade, asVar(`${name}-${shade}`)]));

/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./src/**/*.{js,jsx,ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        white: asVar('white'),
        gray: family('gray', [100, 200, 300, 400, 500, 600, 700, 800, 900]),
        ...Object.fromEntries(FAMILIES.map(name => [name, family(name, SHADES)])),
        // nba-orange is the scheme's accent and nba-blue its table-header colour (names kept from
        // before the schemes existed).
        nba: {
          orange: asVar('accent'),
          blue: asVar('th'),
          red: '#C8102E',
        },
        onaccent: asVar('onaccent'),
        head: asVar('head'),
        th: asVar('th'),
        onth: asVar('onth'),
        row: { mine: asVar('row-mine'), hover: asVar('row-hover') },
        fantasy: {
          gold: '#FFD700',
          silver: '#C0C0C0',
          bronze: '#CD7F32',
        }
      },
      fontFamily: {
        'sans': ['Inter', 'system-ui', 'sans-serif'],
      }
    },
  },
  plugins: [
    plugin(({ addBase }) => addBase(base)),
  ],
}
