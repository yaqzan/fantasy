import React, { useEffect, useRef, useState } from 'react';
import PriceDial from './PriceDial';

// Touch screens: tapping a player's name on the draft board opens this sheet instead of the Draft
// column far to the right. Price on a dial that starts at the room's likely price (slide it, or tap
// aim / max / room / value), then one tap on the team that bought him. Swipe the sheet down, or tap
// outside it, to close.
const CLOSE_AFTER = 90; // px dragged down

const DraftSheet = ({ player, prices, teams, myTeam, money, onDraft, onClose }) => {
  const [dollars, setDollars] = useState(() => Math.max(1, prices.likely ?? prices.aim ?? prices.max ?? prices.value ?? 1));
  const [drag, setDrag] = useState(0);
  const start = useRef(null);

  useEffect(() => {
    const body = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    const onKey = (e) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', onKey);
    return () => { document.body.style.overflow = body; window.removeEventListener('keydown', onKey); };
  }, [onClose]);

  // The dial runs to the most any team can still bid (the budget before any money is known).
  const top = Math.max(dollars, ...Object.values(money || {}).map(m => m.cap), money ? 1 : 200);
  // The price in the board's colours: green up to the aim, amber up to the max, red past it.
  const tone = prices.max == null ? 'text-white' : dollars > prices.max ? 'text-red-400'
    : dollars > (prices.aim ?? prices.max) ? 'text-amber-300' : 'text-green-400';
  const ordered = [...teams].sort((a, b) => (b.abbreviation === myTeam) - (a.abbreviation === myTeam));

  const onTouchStart = (e) => { start.current = e.touches[0].clientY; };
  const onTouchMove = (e) => { if (start.current != null) setDrag(Math.max(0, e.touches[0].clientY - start.current)); };
  const onTouchEnd = () => {
    if (drag > CLOSE_AFTER) onClose();
    else setDrag(0);
    start.current = null;
  };

  const chips = [['aim', prices.aim, 'text-green-400'], ['max', prices.max, 'text-amber-300'],
    ['room', prices.likely, 'text-gray-200'], ['value', prices.value, 'text-gray-200']].filter(([, v]) => v != null);

  return (
    <div className="fixed inset-0 z-50 flex items-end bg-black/60" onClick={onClose}>
      <div
        className="w-full max-h-[92dvh] overflow-y-auto rounded-t-2xl bg-gray-800 border-t border-gray-600 shadow-2xl pb-[max(1rem,env(safe-area-inset-bottom))]"
        style={{ transform: `translateY(${drag}px)`, transition: start.current == null ? 'transform 150ms' : 'none' }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Drag area: the handle and the player's line */}
        <div className="px-4 pt-2 pb-3 touch-none" onTouchStart={onTouchStart} onTouchMove={onTouchMove} onTouchEnd={onTouchEnd}>
          <div className="mx-auto mb-3 h-1.5 w-10 rounded-full bg-gray-600" />
          <div className="flex items-baseline justify-between gap-3">
            <div className="min-w-0">
              <p className="text-lg font-semibold text-white truncate">{player.name}</p>
              <p className="text-xs text-gray-400">{player.positions?.length ? player.positions.join('/') : player.position} · {player.team_abv || 'N/A'}</p>
            </div>
            <p className={`text-4xl font-extrabold tabular-nums ${tone}`}
               title="Green up to your aim, amber up to your max, red past it">${dollars}</p>
          </div>
        </div>

        <div className="px-4">
          {chips.length > 0 && (
            <div className="flex gap-2 mb-3">
              {chips.map(([label, v, color]) => (
                <button key={label} onClick={() => setDollars(Math.min(top, Math.max(1, v)))}
                        className="flex-1 rounded-lg bg-gray-900 border border-gray-700 py-1.5 active:bg-gray-700">
                  <span className="block text-[10px] uppercase tracking-wider text-gray-500">{label}</span>
                  <span className={`text-base font-bold tabular-nums ${color}`}>${v}</span>
                </button>
              ))}
            </div>
          )}

          <div className="mb-4">
            <PriceDial value={dollars} onChange={setDollars} min={1} max={top}
                       marks={[{ v: prices.aim, label: 'aim', color: 'rgb(var(--green-400))' },
                               { v: prices.max, label: 'max', color: 'rgb(var(--amber-300))' },
                               { v: prices.likely, label: 'room', color: 'rgb(var(--gray-200))' }]} />
          </div>

          <p className="text-xs text-gray-400 mb-2">Bought by</p>
          <div className="grid grid-cols-3 gap-2">
            {ordered.map(team => {
              const mine = team.abbreviation === myTeam;
              const m = money?.[team.id];
              const short = m && dollars > m.cap;
              return (
                <button key={team.id} onClick={() => onDraft(team, dollars)}
                        className={`rounded-lg px-2 py-2 text-left active:opacity-70 ${mine ? 'col-span-3 bg-nba-orange text-onaccent' : 'bg-gray-700 text-white'} ${short ? 'opacity-40' : ''}`}
                        title={short ? `Can bid at most $${m.cap}` : undefined}>
                  <span className={`block truncate font-semibold ${mine ? 'text-base' : 'text-sm'}`}>{mine ? `${team.abbreviation || team.name} (me)` : team.abbreviation || team.name}</span>
                  {m && <span className={`block truncate text-[11px] tabular-nums ${mine ? 'opacity-80' : 'text-gray-400'}`}>${m.left} · max ${m.cap}</span>}
                </button>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
};

export default DraftSheet;
