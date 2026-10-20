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

## Player card

Tap a player's name on Daily Leaders or Player Rankings (`PlayerName`) -> `components/PlayerCard.js`
(design A of the 2026-10-17 mockups: centred card from `sm`, bottom sheet on phones, drag the header
down 80px to close; Esc, the scrim or x also close). `GET /api/player-card?id=` (or `?name=`), `player_card.py`.

- **Averages** in the league's categories, Daily Leaders' column order (points leagues: FPTS first):
  Projection; Preseason at his projected minutes (per-minute x projected MPG: preseason minutes are
  rotations); Adjusted (the `'_pre'` timeframe, projections.md "Preseason signal"); Season, Last 10, Last 5 (a window only when he has more games than it). Delta under each
  vs the season from 10 games, else vs the projection; percentages in points; grey under 6% / 1 point.
- **Game log**: regular season then preseason (`preseason_lines`, never in season totals), scored by
  `daily_leaders.score_line`, so tints and Z equal the board's. Stats the source lacks per game (NBA
  rows: BLKA; preseason: TECH) show '–' and leave the game's Z; season BLKA comes from the player's totals.
- **Performance**: `PlayerCardProvider` wraps `<App>` in `index.js`, so opening a card re-renders no
  board. The request starts on tap and is cached 2 min per league + player. Only opacity/transform
  animate (`.pc-card` / `.pc-scrim` in `index.css`: ~160-190ms in, ~110-140ms out, none under
  reduced motion); the card unmounts after the close animation.

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
- Header: one row, logo + league picker + a menu button (colours, Draft mode switch, Settings, New league, guillotine stage).
- Tabs scroll sideways in one row; the draft-mode pill is desktop-only (phones: the menu switch).
- Fantasy Teams panel: phones get it as the last tab, **Teams** (`TeamManager asTab`, `useIsPhone` in
  App.js): rosters in a 2-column grid, no fold, no Add team (teams come from the platform syncs; the
  edit pencil stays). Wider screens keep the panel above the tabs.
- Desktop toolbars (owner, 2026-10-20): no "Daily Leaders" title; the date stepper (Daily Leaders) and the search box (Player Rankings) are the same
  14rem x 42px slot at the left of the row, same look, so the first control never moves between tabs; the rest of the row follows at the same x.
- Player Rankings table (in-season) copies Daily Leaders' geometry so tab switches don't jump (owner, 2026-10-20): bare toolbar row
  (60px min, same on both tabs), pinned 15rem Player column (rank + the owner's two-letter chip under it (`OwnerChip`: first and last word's initials, else the first two letters; a muted tint hashed from the name) (other teams only; `fantasy_teams.owner_name`, the Yahoo manager nickname filled by `pull_yahoo sync`, else the team name), name, `F · BOS · 2 + 4 GP`; no status text: dimming
  and the chip say it), 4rem OVR column (5rem in points leagues), stat cards (value + percentile, tinted), stats in `orderColumns` order. Header
  cells never wrap (a taller header row shifts the table). The GP warning (`small_sample`) scales with days since the first game
  (`player_stats.small_sample_floor`, shared by rankings, Lineup Optimizer and Weekly Pickups): week one flags nobody.
- Player Rankings toolbar: search + a Filters button (badge = levers changed from default); stats,
  positions, star premium, available/healthy fold into it.
- Daily Leaders toolbar: one row on phones: `‹ Wed 14 ›` (orange on today; hold it to jump back; tap it for a month calendar that picks on tap, no OK button (`DatePopover`), limited to `season_range`: regular season widened 30 days before, 70 after, `player_stats.season_window`), Avail / Mine chips (no All, no counts; tap the lit chip to return to everything), Best|Pace. Status text and the Today link are desktop-only.
- Daily Leaders: one pinned column (10.375rem, sized so the sixth stat column starts off-screen on a 400px phone: rank, name, team, minutes, game progress; an owner-initial chip under the rank on other teams' players (owner, 2026-10-20: the manager's name, `owner_person`; none on mine, the highlight says it); mine are the highlighted rows (theme colour `mine`: gold on Podium; the same tint colours Draft Board rows); this week's
  opponent's players differ only by name colour `opp` (copper, still inside the 40% dim; `vs_me`, from the league schedule, the first week before the season); a rostered player who sat a finished game
  is listed last with a dashed `DNP` tag (reason in the tooltip); the sub-line ends with `GameProgress` (quarter pips + clock while live, red pulse only on the floor, muted result when final; minutes read `27m` on phones); a red `-TF`-style tag names a category at z <= -2.5, `worstDrag`), Best (FPTS in points leagues) pinned next to
  it (2.375rem: the number only, the pace arrow sits absolute in its top-right corner on phones; on the Pace sort it shows the pace number and the rank is pace order), then stat columns at 2.25rem. Columns run PTS, REB, A-TO (AST where a league has
  none), STL, BLK, then the league's other categories (`orderColumns`): those five fit at 390px in
  every league, the rest scroll under the pinned pair. Scoreboard chips run ongoing, upcoming, completed (earliest start first within each; `orderGames`), each with a status dot beside the clock (hollow / red / grey, no pulse); an ongoing chip's border is one grey step lighter, a final one is faded. Tapping a chip filters the list to that game (orange
  ring, other chips fade; tap again to clear, another to move; owner chips count within it). Taken rows fade their cell
  contents, not the row: an opacity on the row lets scrolled cells show through the pinned ones. Their category
  tints stay (only the text fades), so a taken player's bad night shows why it ranked low. My rows lay the
  tint as a translucent overlay on the yellow `bg-row-mine` (two bg classes on one cell: yellow won).
  Points leagues tint their box columns too: `daily_leaders._tint_box_columns` fills `z[column]` = fantasy
  points that column paid (FG/FT: made + attempted weights) vs the day's 10+ minute lines, mean/SD, same
  `zTint` steps; columns the league doesn't score stay plain; needs 8+ such lines.
  Desktop is dense (owner, 2026-10-20): tabs and Fantasy Teams (collapsed by default, a muted one-liner) hug the top;
  title, date, owner chips, Best|Pace, scoreboard and status share one wrapping row; the scoreboard drops to
  its own scrolling row only past `INLINE_GAMES` (8) games; the "All" chip is gone everywhere (tap the lit owner chip to clear it); "next HH:MM" shows from 2xl up.
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
