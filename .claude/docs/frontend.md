# Frontend

## Colour schemes

Four schemes, picked with the dots in the header: Podium (default), Hardwood, Banner, Press Box
(light). The pick is per browser (`localStorage` `fantasy.theme`) and sets `data-theme` on `<html>`.

- **Colours are CSS variables, defined once in `frontend/tailwind.config.js` (`THEMES`).** Tailwind's
  `gray-*`, `white`, the status families (`red`, `green`, `amber`...) and the tokens below all read
  them, so components keep ordinary classes (`bg-gray-800`, `text-white`, `text-green-400`).
- **`gray` is a role, not a colour:** 900 page, 800 panel, 700 rule, down to 100 text. `white` is the
  strongest text. Press Box runs the scale the other way and mirrors every status shade
  (300 <-> 700), which is why pale-on-dark classes still read on paper.
- Tokens: `nba-orange` = the scheme's accent, `onaccent` = text on it, `head` = header bar,
  `th` / `onth` = table header and its text (`nba-blue` is an alias of `th`), `row-mine` /
  `row-hover` = the draft board's opaque row colours.
- **Never write a hex or `rgb()` literal for a neutral, accent or status colour in a component.**
  In inline styles use `rgb(var(--gray-400))`, `rgb(var(--white))`, `rgb(var(--green-400))`. Text on
  the accent is `text-onaccent`, never `text-white` (Banner's accent is gold).
- Adding a scheme: one entry in `THEMES` plus its id and label in `src/theme.js`.
- Not themed: `bidColor.js` (unused by the UI), the Draft Day chart colours, `fantasy-gold/silver/bronze`.

## Logo

`components/Logo.js` and `public/favicon.svg` are the same drawing with fixed colours (it does not
follow the scheme). Change both together, then run `python frontend/scripts/make_icons.py`.

**Home-screen icons are PNGs** (`apple-touch-icon.png`, `icon-192.png`, `icon-512.png`), rendered
from `favicon.svg` on an opaque tile by that script (Edge/Chrome headless + Pillow). iOS ignores SVG
touch icons and shows a letter instead. `public/manifest.json` must exist: a missing file gets
`index.html` from `serve_frontend`. Tile colour is `TILE` in the script.

## Live draft refresh

Draft mode reloads players and teams every 60s (App.js; skipped while the tab is hidden), because
`pull_fantrax.py draft --watch` writes picks behind the page's back. Values recompute in the browser
from those rosters. Typed bids are DraftBoard state and survive the reload.

## Deploying a change

`npm --prefix frontend run build` empties `frontend/build` first, so the live site 404s for the whole
build (3+ minutes when the box is busy). For no downtime: `BUILD_PATH=build-next npm run build` in
`frontend`, then swap `build-next` in for `build`. A build killed by a timeout leaves node children
running on Windows; kill the tree (`taskkill /T`) before starting another.

## Phones

Target a 390px-wide phone; nothing may scroll the page sideways (wide tables scroll inside their own
box). Phone styles are the unprefixed classes, `sm:` restores the desktop look, so a desktop change
must keep its `sm:` twin.

- **Phones keep only what drafting needs on screen; levers are one tap away.**
- Header: one row, logo + league picker + a menu button (colours, Settings, New league, guillotine stage).
- Tabs scroll sideways in one row; the draft-mode pill sits outside the scrolling strip.
- Fantasy Teams panel: hidden on phones in draft mode (the room strip has every team's $ and spots),
  folded by default otherwise; team columns get an 8.5rem floor on phones only.
- Player Rankings toolbar: search + a Filters button (badge = levers changed from default); stats,
  positions, star premium, available/healthy fold into it.
- Daily Leaders: one pinned column (8rem: rank, name, team, minutes, owner chip), Val pinned next to
  it (2.75rem), then stat columns at 2.25rem. Columns run PTS, REB, A-TO (AST where a league has
  none), STL, BLK, then the league's other categories (`orderColumns`): those five fit at 390px in
  every league, the rest scroll under the pinned pair. Taken rows fade their cell
  contents, not the row: an opacity on the row lets scrolled cells show through the pinned ones.
- Draft board: the key/legend is off on phones; the room strip is one line (top bid, spot bar, aim %,
  room factor once picks have prices, pace only when it warns) with team chips behind "Teams".
- The board's scroll box fills the rest of the screen on phones (measured in `DraftBoard`), so the
  page never scrolls before the table does.
- Hover-only buttons also show under `[@media(hover:none)]` (touch has no hover).
- Draft board: name column 8rem and bid rail 13.5rem on phones so name and aim/max/value fit the
  first screen; categories and the Draft button scroll sideways.
- **Draft sheet** (`DraftSheet.js`, touch screens only, `(hover: none)`): tapping a name opens a
  bottom sheet: a price dial (`PriceDial.js`, $1 a tick, starts at the room's likely price, drag or
  fling, aim/max/room marked on it), aim/max/room/value chips, +/- $1, then one tap on the buying
  team (mine first). The big price is green to the aim, amber to the max, red past it. Haptics: a
  light tick per $1 while dragging -- `navigator.vibrate` on Android; iOS Safari has none, so the dial
  clicks a hidden `<input type="checkbox" switch>` (Safari 18+ ticks on a switch toggle). Swipe down or tap outside to close. Each pick from it shows an Undo toast for 8s. A drafted
  player's name opens the usual DraftModal. Row swipes are deliberately not used: they would fight
  the board's sideways scroll. Desktop never sees any of it.
- `maximum-scale=1` in the viewport stops iOS zooming on every focused small input.
