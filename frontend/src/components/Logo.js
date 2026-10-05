import React from 'react';

// The mark: a basketball on a championship banner. Fixed colours (it is also public/favicon.svg),
// so it looks the same on every colour scheme.
const Logo = ({ className = 'w-9 h-9' }) => (
  <svg viewBox="0 0 64 64" className={className} role="img" aria-label="Fantasy">
    <path d="M6 7h52" stroke="#E9B949" strokeWidth="4" strokeLinecap="round" />
    <path d="M11 9h42v38L32 59 11 47z" fill="#12284D" stroke="#E9B949" strokeWidth="2.5" strokeLinejoin="round" />
    <circle cx="32" cy="28" r="12" fill="#F08A24" />
    <g fill="none" stroke="#0B1A33" strokeWidth="2" strokeLinecap="round">
      <path d="M32 16V40" />
      <path d="M20 28H44" />
      <path d="M23.6 19.6C28.6 23.2,28.6 32.8,23.6 36.4" />
      <path d="M40.4 19.6C35.4 23.2,35.4 32.8,40.4 36.4" />
    </g>
    <path d="M32 44l1.6 3.2 3.5.5-2.5 2.5.6 3.5-3.2-1.7-3.2 1.7.6-3.5-2.5-2.5 3.5-.5z" fill="#E9B949" />
  </svg>
);

export default Logo;
