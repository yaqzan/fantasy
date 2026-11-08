import React from 'react';

// A player on waivers: yellow where a free agent would be green (a claim, usually a FAAB bid, lands from the day he clears).
const dayName = (d) => new Date(`${d}T12:00`).toLocaleDateString('en-US', { weekday: 'short' });

const WaiverChip = ({ day, className = '' }) => (
  <span className={`shrink-0 px-1 rounded border border-yellow-500/60 bg-yellow-500/15 text-yellow-300 text-[10px] leading-4 font-semibold whitespace-nowrap ${className}`}
        title={day ? `On waivers: he clears ${dayName(day)}, and other teams can bid on him until then` : 'On waivers'}>
    W{day ? ` ${dayName(day)}` : ''}
  </span>
);

export default WaiverChip;
