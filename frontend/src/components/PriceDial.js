import React, { useEffect, useRef, useState } from 'react';

// A sideways price tape: drag or fling it, the $ under the centre line is the price. One tick per $1,
// a label every $5. `marks` ([{ v, color, label }]) pin aim / max / room on the tape.
// Haptics: a light tick per $1 passed while the finger is down. Android takes navigator.vibrate;
// iOS Safari has no vibrate API, but toggling a hidden <input switch> (Safari 18+) gives the system's
// own light tick. Older iPhones get no haptics.
const PX = 14;          // px per $1
const FRICTION = 0.92;  // fling slowdown per frame
const MIN_GAP = 30;     // ms between haptic ticks, so a fast fling stays a light buzz

const DIAL_INPUT_ATTRS = { switch: '' };

const PriceDial = ({ value, onChange, min = 1, max = 200, marks = [] }) => {
  const box = useRef(null);
  const [width, setWidth] = useState(340);
  const [pos, setPosState] = useState(value);
  const posRef = useRef(value);
  const drag = useRef(null);
  const anim = useRef(null);
  const lastTick = useRef(0);
  const haptic = useRef(null);

  useEffect(() => {
    const measure = () => box.current && setWidth(box.current.offsetWidth);
    measure();
    window.addEventListener('resize', measure);
    return () => { window.removeEventListener('resize', measure); cancelAnimationFrame(anim.current); };
  }, []);

  const tick = () => {
    const now = performance.now();
    if (now - lastTick.current < MIN_GAP) return;
    lastTick.current = now;
    if (navigator.vibrate) navigator.vibrate(4);
    else haptic.current?.click();
  };

  const setPos = (p, { feel = false } = {}) => {
    const clamped = Math.min(max, Math.max(min, p));
    const before = Math.round(posRef.current);
    posRef.current = clamped;
    setPosState(clamped);
    const now = Math.round(clamped);
    if (now !== before) {
      if (feel) tick();
      onChange(now);
    }
  };

  // Tween to a $ (chips, +/-), or settle on the nearest $ after a drag.
  const glide = (target, { feel = false } = {}) => {
    cancelAnimationFrame(anim.current);
    const from = posRef.current;
    const t0 = performance.now();
    const step = (t) => {
      const k = Math.min(1, (t - t0) / 220);
      setPos(from + (target - from) * (1 - (1 - k) ** 3), { feel });
      if (k < 1) anim.current = requestAnimationFrame(step);
    };
    anim.current = requestAnimationFrame(step);
  };

  // A chip tapped outside: follow the new value.
  useEffect(() => {
    if (!drag.current && Math.round(posRef.current) !== value) glide(value);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value]);

  const onPointerDown = (e) => {
    cancelAnimationFrame(anim.current);
    e.currentTarget.setPointerCapture(e.pointerId);
    drag.current = { x: e.clientX, pos: posRef.current, lastX: e.clientX, lastT: performance.now(), v: 0 };
  };
  const onPointerMove = (e) => {
    const d = drag.current;
    if (!d) return;
    const t = performance.now();
    d.v = (e.clientX - d.lastX) / Math.max(1, t - d.lastT); // px per ms
    d.lastX = e.clientX;
    d.lastT = t;
    setPos(d.pos - (e.clientX - d.x) / PX, { feel: true });
  };
  const onPointerUp = () => {
    const d = drag.current;
    drag.current = null;
    if (!d) return;
    // Fling: keep the finger's speed and let it slow down, then settle on a whole $.
    let v = performance.now() - d.lastT < 80 ? -d.v * 16 / PX : 0; // $ per frame
    const run = () => {
      if (Math.abs(v) < 0.05) { glide(Math.round(posRef.current)); return; }
      setPos(posRef.current + v, { feel: true });
      v *= FRICTION;
      anim.current = requestAnimationFrame(run);
    };
    run();
  };

  const half = width / 2 / PX + 1;
  const ticks = [];
  for (let v = Math.max(min, Math.floor(pos - half)); v <= Math.min(max, Math.ceil(pos + half)); v += 1) ticks.push(v);
  const x = (v) => width / 2 + (v - pos) * PX;

  return (
    <div className="relative select-none">
      <div className="flex items-center gap-2">
        <button type="button" aria-label="$1 less" onClick={() => { tick(); glide(Math.round(posRef.current) - 1); }}
                className="w-9 h-9 flex-none rounded-full bg-gray-700 text-white text-xl leading-none active:bg-gray-600">−</button>
        <div ref={box} className="relative flex-1 h-20 overflow-hidden touch-none cursor-grab rounded-lg bg-gray-900"
             onPointerDown={onPointerDown} onPointerMove={onPointerMove} onPointerUp={onPointerUp} onPointerCancel={onPointerUp}
             role="slider" aria-label="Price" aria-valuemin={min} aria-valuemax={max} aria-valuenow={Math.round(pos)} tabIndex={0}
             onKeyDown={(e) => { if (e.key === 'ArrowLeft') glide(Math.round(posRef.current) - 1); if (e.key === 'ArrowRight') glide(Math.round(posRef.current) + 1); }}>
          {ticks.map(v => (
            <div key={v} className="absolute bottom-0" style={{ left: x(v) }}>
              <div className={`absolute bottom-0 w-px -ml-px ${v % 5 === 0 ? 'h-6 bg-gray-400' : 'h-3 bg-gray-600'}`} />
              {v % 5 === 0 && <span className="absolute bottom-7 -translate-x-1/2 text-[10px] tabular-nums text-gray-500">{v}</span>}
            </div>
          ))}
          {marks.filter(m => m.v != null && m.v >= min && m.v <= max).map(m => (
            <div key={m.label} className="absolute top-0 bottom-0 pointer-events-none" style={{ left: x(m.v) }}>
              <span className="absolute top-1 -translate-x-1/2 text-[9px] font-semibold uppercase tracking-wider whitespace-nowrap" style={{ color: m.color }}>{m.label}</span>
              <div className="absolute top-4 bottom-0 w-[2px] -ml-px opacity-70" style={{ background: m.color }} />
            </div>
          ))}
          {/* fade the edges, centre line on top */}
          <div className="absolute inset-y-0 left-0 w-10 bg-gradient-to-r from-gray-900 to-transparent pointer-events-none" />
          <div className="absolute inset-y-0 right-0 w-10 bg-gradient-to-l from-gray-900 to-transparent pointer-events-none" />
          <div className="absolute inset-y-0 left-1/2 w-[3px] -ml-[1.5px] rounded-full bg-nba-orange pointer-events-none" />
        </div>
        <button type="button" aria-label="$1 more" onClick={() => { tick(); glide(Math.round(posRef.current) + 1); }}
                className="w-9 h-9 flex-none rounded-full bg-gray-700 text-white text-xl leading-none active:bg-gray-600">+</button>
      </div>
      {/* iOS haptic: clicking this label flips a hidden switch, which Safari answers with a light tick */}
      <label ref={haptic} className="absolute w-px h-px overflow-hidden opacity-0 pointer-events-none" aria-hidden="true"
             onClick={(e) => e.stopPropagation()}>
        <input type="checkbox" tabIndex={-1} {...DIAL_INPUT_ATTRS} />
      </label>
    </div>
  );
};

export default PriceDial;
