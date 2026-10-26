import React, { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react';
import { getPlayerCard, getSelectedLeague, errorMessage } from '../services/api';
import { orderColumns, zTint } from '../dailyLeaders';

// Tap a player's name (Daily Leaders, Player Rankings) -> his card: averages (Projection, Preseason at
// his projected minutes, Season, Last 10, Last 5) with a delta under each against the season (from
// DELTA_SEASON_GAMES games, else the projection), then the game log scored like Daily Leaders.
// One card for the whole app: PlayerCardProvider owns its state, so opening it never re-renders a
// board (the provider's children are the same elements). Cards are cached per league + player.

const OpenContext = createContext(() => {});
export const usePlayerCard = () => useContext(OpenContext);

const CACHE_MS = 2 * 60 * 1000;
const cache = new Map();
const cacheKey = (t) => `${getSelectedLeague() || ''}|${t.id || t.name}`;
const loadCard = (target) => {
  const key = cacheKey(target);
  const hit = cache.get(key);
  if (hit && Date.now() - hit.at < CACHE_MS) return hit.promise;
  const promise = getPlayerCard(target);
  cache.set(key, { at: Date.now(), promise });
  promise.catch(() => cache.delete(key));
  return promise;
};

const CLOSE_MS = 150;

export function PlayerCardProvider({ children }) {
  const [target, setTarget] = useState(null);   // what is mounted (stays during the close animation)
  const [open, setOpen] = useState(false);
  const timer = useRef(null);
  const openCard = useCallback((t) => {
    if (!t || (!t.id && !t.name)) return;
    clearTimeout(timer.current);
    loadCard(t);  // start the request before the first frame
    setTarget(t);
    requestAnimationFrame(() => requestAnimationFrame(() => setOpen(true)));
  }, []);
  const close = useCallback(() => {
    setOpen(false);
    clearTimeout(timer.current);
    timer.current = setTimeout(() => setTarget(null), CLOSE_MS);
  }, []);
  return (
    <OpenContext.Provider value={openCard}>
      {children}
      {target && <PlayerCard target={target} open={open} onClose={close} />}
    </OpenContext.Provider>
  );
}

// A player's name that opens his card; looks like the plain name it replaces.
export function PlayerName({ id, name, className = '', children }) {
  const openCard = usePlayerCard();
  return (
    <button type="button" onClick={(e) => { e.stopPropagation(); openCard({ id, name }); }}
            className={`text-left hover:underline decoration-gray-500 underline-offset-2 ${className}`} title={name}>
      {children ?? name}
    </button>
  );
}

const isPercent = (c) => c.percent;
const fmtAvg = (c, v) => {
  if (v === null || v === undefined) return '–';
  if (isPercent(c) || c.key === 'WIN%') return v < 1 ? v.toFixed(3).replace(/^0/, '') : v.toFixed(3);
  if (c.key === 'TECH') return v.toFixed(2);
  if (c.key === 'FPTS') return String(Math.round(v));
  return v.toFixed(1);
};

// The change against the base row: an arrow and the size, green when it helps (inverse categories
// flip), grey when it is too small to matter. Percentages in points (.571 -> .585 is +1.4).
function Delta({ c, v, base }) {
  if (v === null || v === undefined || base === null || base === undefined) return <span className="block text-[10px] leading-tight text-gray-500">–</span>;
  const diff = v - base;
  const pct = isPercent(c) || c.key === 'WIN%';
  const mag = pct ? Math.abs(diff * 100).toFixed(1) : Math.abs(diff).toFixed(c.key === 'TECH' ? 2 : 1);
  if (Number(mag) === 0) return <span className="block text-[10px] leading-tight text-gray-500">±0</span>;
  const big = pct ? Math.abs(diff) >= 0.01 : Math.abs(diff) >= Math.max(0.1, Math.abs(base) * 0.06);
  if (!big) return <span className="block text-[10px] leading-tight text-gray-500">{diff > 0 ? '+' : '−'}{mag}</span>;
  const good = c.inverse ? diff < 0 : diff > 0;
  return <span className={`block text-[10px] leading-tight ${good ? 'text-green-400' : 'text-red-400'}`}>{diff > 0 ? '▲' : '▼'}{mag}</span>;
}

const shortDate = (iso) => new Date(`${iso}T12:00:00`).toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
const weekday = (iso) => new Date(`${iso}T12:00:00`).toLocaleDateString('en-US', { weekday: 'short' });
const signed = (v) => (v > 0 ? `+${v}` : `${v}`);

function Chip({ className = '', children, title }) {
  return <span title={title} className={`text-[11px] px-1.5 py-px rounded-full border whitespace-nowrap ${className || 'border-gray-600 text-gray-300'}`}>{children}</span>;
}

const STICKY = 'sticky left-0 z-[1] bg-gray-800';

// Averages and game log share one column layout (label, Min, categories) so the columns line up.
const tableStyle = (n) => ({ minWidth: `calc(7.5rem + 2.25rem + ${n} * 2.75rem)` });
function Cols({ n, extra = 0 }) {
  return (
    <colgroup>
      <col style={{ width: '7.5rem' }} /><col style={{ width: '2.25rem' }} />
      {Array.from({ length: n }, (_, i) => <col key={i} style={{ width: '2.75rem' }} />)}
      {extra > 0 && <col style={{ width: '2.5rem' }} />}
    </colgroup>
  );
}

const isHistory = (r) => r.key.startsWith('y');

function Averages({ card, columns }) {
  const [older, setOlder] = useState(false);
  const base = card.averages.find(r => r.key === card.delta_base);
  const history = card.averages.filter(isHistory);
  const rows = card.averages.filter(r => !isHistory(r) || older || r === history[0]);
  const hidden = history.length - 1;
  return (
    <table className="w-full table-fixed border-collapse tabular-nums text-xs" style={tableStyle(columns.length)}>
      <Cols n={columns.length} />
      <thead>
        <tr>
          <th className={`${STICKY} bg-th text-left pl-3 pr-2 py-1.5`} />
          <th className="bg-th text-onth text-[10px] font-semibold uppercase tracking-wide px-0.5 py-1.5">Min</th>
          {columns.map(c => <th key={c.key} className="bg-th text-onth text-[10px] font-semibold uppercase tracking-wide px-0.5 py-1.5" title={c.name}>{c.label}</th>)}
        </tr>
      </thead>
      <tbody>
        {rows.map(r => (
          <tr key={r.key} className="border-t border-gray-700">
            <td className={`${STICKY} pl-3 pr-2 py-1.5 text-left whitespace-nowrap`} title={r.title || undefined}>
              <span className="text-gray-300 text-[11px]">{r.label}</span>
              {r.note && <span className="block text-[10px] text-gray-500 leading-tight">{r.note}</span>}
            </td>
            <td className="text-center px-0.5 py-1.5 text-gray-400">{r.values.MIN ? Math.round(r.values.MIN) : '–'}</td>
            {columns.map(c => (
              <td key={c.key} className={`text-center px-0.5 py-1.5 whitespace-nowrap ${c.key === 'FPTS' ? 'bg-white/10' : ''}`}>
                <span className={r.key === card.delta_base ? 'text-white font-semibold' : 'text-white'}>{fmtAvg(c, r.values[c.key])}</span>
                {base && r !== base ? <Delta c={c} v={r.values[c.key]} base={base.values[c.key]} />
                  : <span className="block text-[10px] leading-tight">&nbsp;</span>}
              </td>
            ))}
          </tr>
        ))}
        {hidden > 0 && (
          <tr className="border-t border-gray-700">
            <td colSpan={columns.length + 1} className={`${STICKY} bg-gray-800 pl-3 py-1.5 text-left`}>
              <button type="button" onClick={() => setOlder(o => !o)} className="text-[11px] text-gray-400 hover:text-white">
                {older ? '▴ Hide older seasons' : `▾ ${hidden} older season${hidden > 1 ? 's' : ''}`}
              </button>
            </td>
          </tr>
        )}
      </tbody>
    </table>
  );
}

function GameLog({ card, columns, points }) {
  const row = (g, i) => (
    <tr key={`${g.kind}${g.date}`} className={`border-t ${g.kind === 'preseason' ? 'opacity-50 border-gray-700' : i === 5 || i === 10 ? 'border-dashed border-gray-500' : 'border-gray-700'}`}>
      <td className={`${STICKY} pl-3 pr-2 py-1 text-left whitespace-nowrap ${g.kind === 'regular' && i < 5 ? 'shadow-[inset_2px_0_0_rgb(var(--accent))]' : ''}`}>
        <span className="text-gray-300">{shortDate(g.date)}</span>
        <span className="text-gray-500 text-[10px] ml-1">{g.opp || ''}</span>
        <span className={`text-[10px] ml-1 ${g.w ? 'text-green-400' : 'text-red-400'}`}>{g.w ? 'W' : 'L'}</span>
      </td>
      <td className="text-center px-0.5 py-1 text-gray-400">{g.min}</td>
      {columns.map(c => (
        <td key={c.key} className={`text-center px-0.5 py-1 whitespace-nowrap ${c.key === 'FPTS' ? 'font-semibold text-white bg-white/10' : 'text-gray-200'} ${points ? '' : zTint(g.z?.[c.key])}`}
            title={!points && g.z?.[c.key] != null ? `z ${signed(g.z[c.key])}` : undefined}>
          {c.key === 'FPTS' && typeof g.cells[c.key] === 'number' ? Math.round(g.cells[c.key]) : g.cells[c.key]}
        </td>
      ))}
      {!points && <td className={`text-center px-0.5 py-1 font-semibold text-white border-l border-gray-700 ${zTint(g.value / 3)}`}>{signed(g.value.toFixed(1))}</td>}
    </tr>
  );
  return (
    <table className="w-full table-fixed border-collapse tabular-nums text-xs" style={tableStyle(columns.length)}>
      <Cols n={columns.length} extra={points ? 0 : 1} />
      <thead>
        <tr>
          <th className={`${STICKY} bg-th text-onth text-left pl-3 pr-2 py-1.5 text-[10px] font-semibold uppercase tracking-wide`}>Game</th>
          <th className="bg-th text-onth text-[10px] font-semibold uppercase tracking-wide px-0.5">Min</th>
          {columns.map(c => <th key={c.key} className="bg-th text-onth text-[10px] font-semibold uppercase tracking-wide px-1.5" title={c.name}>{c.label}</th>)}
          {!points && <th className="bg-th text-onth text-[10px] font-semibold uppercase tracking-wide px-0.5 border-l border-gray-700" title="Summed category z, as on Daily Leaders">Z</th>}
        </tr>
      </thead>
      <tbody>
        {(card.upcoming || []).map(u => (
          <tr key={`up${u.date}`} className="border-t border-gray-700 text-gray-500">
            <td className={`${STICKY} pl-3 pr-2 py-1 text-left whitespace-nowrap`}>
              <span>{shortDate(u.date)}</span><span className="text-[10px] ml-1">{u.opp}</span>
            </td>
            <td className="py-1" />
            {columns.map(c => <td key={c.key} className={c.key === 'FPTS' ? 'bg-white/10' : ''} />)}
            {!points && <td className="border-l border-gray-700" />}
          </tr>
        ))}
        {card.games.map((g, i) => row(g, g.kind === 'regular' ? i : -1))}
      </tbody>
    </table>
  );
}

function PlayerCard({ target, open, onClose }) {
  const [state, setState] = useState({ card: null, error: null });
  const closeRef = useRef(null);
  const drag = useRef(null);
  const cardRef = useRef(null);

  useEffect(() => {
    let live = true;
    setState({ card: null, error: null });
    loadCard(target).then(card => live && setState({ card, error: null }))
      .catch(e => live && setState({ card: null, error: errorMessage(e) }));
    return () => { live = false; };
  }, [target]);

  useEffect(() => {
    const onKey = (e) => { if (e.key === 'Escape') onClose(); };
    document.addEventListener('keydown', onKey);
    const overflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    closeRef.current?.focus({ preventScroll: true });
    return () => { document.removeEventListener('keydown', onKey); document.body.style.overflow = overflow; };
  }, [onClose]);

  // Phones: drag the header down to dismiss (the sheet follows the finger; 80px closes it).
  // The body swipes too, but only from its top (scrolled down, a swipe down scrolls up instead).
  const onTouchStart = (e) => {
    if (e.currentTarget.scrollTop > 0) { drag.current = null; return; }
    drag.current = e.touches[0].clientY;
  };
  const onTouchMove = (e) => {
    if (drag.current === null) return;
    const dy = Math.max(0, e.touches[0].clientY - drag.current);
    if (dy > 0) cardRef.current?.setAttribute('data-dragging', '');
    cardRef.current?.style.setProperty('--pc-drag', `${dy}px`);
  };
  const onTouchEnd = (e) => {
    if (drag.current === null) return;
    const dy = e.changedTouches[0].clientY - drag.current;
    drag.current = null;
    cardRef.current?.removeAttribute('data-dragging');
    cardRef.current?.style.setProperty('--pc-drag', '0px');
    if (dy > 80) onClose();
  };

  const { card, error } = state;
  const points = card?.scoring === 'points';
  const columns = card ? (points
    ? [...card.categories.filter(c => c.key === 'FPTS'), ...orderColumns(card.categories.filter(c => c.key !== 'FPTS'))]
    : orderColumns(card.categories)) : [];
  const ownerChip = card && (card.owner === 'mine' ? <Chip className="border-mine text-mine">My team</Chip>
    : card.owner === 'taken' ? <Chip>{card.owner_name}</Chip>
    : <Chip className="border-green-500 text-green-400">Free agent</Chip>);

  return (
    <div className="fixed inset-0 z-50 flex items-end sm:items-center justify-center sm:p-6">
      <div className="pc-scrim absolute inset-0 bg-black/55" data-open={open ? '' : undefined} onClick={onClose} />
      <div ref={cardRef} role="dialog" aria-modal="true" aria-labelledby="pc-name" data-open={open ? '' : undefined}
           className="pc-card relative flex flex-col w-full sm:max-w-3xl max-h-[88vh] sm:max-h-[85vh] bg-gray-800 border border-gray-700 border-b-0 sm:border-b rounded-t-2xl sm:rounded-xl overflow-hidden shadow-2xl will-change-transform">
        <div onTouchStart={onTouchStart} onTouchMove={onTouchMove} onTouchEnd={onTouchEnd}>
          <div className="sm:hidden mx-auto mt-2 -mb-1 h-1 w-9 rounded bg-gray-600" />
          <div className="flex items-start gap-3 px-4 pt-3 pb-2.5 border-b border-gray-700">
            <div className="min-w-0 flex-1">
              <h2 id="pc-name" className="text-lg font-bold text-white leading-tight truncate">{card?.name || target.name}</h2>
              {card && (
                <div className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-gray-400">
                  <span>{card.team} · {card.positions.join('/')}</span>
                  {card.rank && <span title="Rank on the projection in this league">#{card.rank} proj</span>}
                  {card.rank_season && <span title="Rank on this season's games in this league">#{card.rank_season} season</span>}
                  {ownerChip}
                  {card.injured && <Chip className="border-red-500 text-red-400">INJ{card.injured_return ? ` · ${card.injured_return}` : ''}</Chip>}
                  {card.next_game && <Chip>Next: {weekday(card.next_game.date)} {card.next_game.opp}</Chip>}
                </div>
              )}
            </div>
            <button ref={closeRef} type="button" onClick={onClose} aria-label="Close"
                    className="-mr-1 px-1 text-2xl leading-none text-gray-400 hover:text-white">×</button>
          </div>
        </div>
        <div className="flex-1 overflow-auto overscroll-contain thin-scrollbar"
             onTouchStart={onTouchStart} onTouchMove={onTouchMove} onTouchEnd={onTouchEnd}>
          {error && <p className="p-4 text-sm text-red-400">{error}</p>}
          {!card && !error && <div className="p-6 flex justify-center"><div className="animate-spin rounded-full h-5 w-5 border-b-2 border-nba-orange" /></div>}
          {card && (
            <>
              <div className="flex justify-between px-3 pt-2.5 pb-1 text-[10px] uppercase tracking-wider text-gray-500">
                <span>Averages</span>
                <span className="normal-case tracking-normal">{card.delta_base === 'season' ? 'Δ vs season' : 'Δ vs projection'}</span>
              </div>
              {card.averages.length ? <Averages card={card} columns={columns} />
                : <p className="px-3 pb-2 text-xs text-gray-500">No projection or games yet.</p>}
              <div className="px-3 pt-3 pb-1 text-[10px] uppercase tracking-wider text-gray-500">Game log</div>
              {card.games.length || card.upcoming?.length ? <GameLog card={card} columns={columns} points={points} />
                : <p className="px-3 pb-3 text-xs text-gray-500">No games this season yet.</p>}
              <div className="h-3" />
            </>
          )}
        </div>
      </div>
    </div>
  );
}
