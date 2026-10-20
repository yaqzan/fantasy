import React from 'react';

// The small chip under a rank on another team's player: two letters of the manager's name (first and last
// word's initials, or the first two letters of a one-word name) in a muted colour picked from the name,
// so one owner is the same tint on every tab. Falls back to the team name when no manager name is stored.
const initials = (label) => {
  const words = label.replace(/[^\p{L}\p{N}\s]/gu, ' ').split(/\s+/).filter(Boolean);
  if (words.length > 1) return (words[0][0] + words[words.length - 1][0]).toUpperCase();
  const w = words[0] || '?';
  return (w[0].toUpperCase() + (w[1] || '').toLowerCase());
};

const hueOf = (label) => {
  let h = 0;
  for (const ch of label) h = (h * 31 + ch.codePointAt(0)) % 360;
  return h;
};

const OwnerChip = ({ person, team }) => {
  const label = person || team || '?';
  const hue = hueOf(label.toLowerCase());
  return (
    <span className="h-[14px] px-[3px] rounded-full border text-[8px] leading-[12px] font-semibold tracking-tight whitespace-nowrap select-none"
          style={{ color: `hsl(${hue} 40% 72%)`, borderColor: `hsl(${hue} 30% 48% / 0.55)`, background: `hsl(${hue} 40% 50% / 0.12)` }}
          title={person && team ? `${person} (${team})` : label}>
      {initials(label)}
    </span>
  );
};

export default OwnerChip;
