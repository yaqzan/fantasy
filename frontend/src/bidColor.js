// Colour for a max bid by how it compares with the room's likely price: green when the room is
// expected to stop well short of the max, neutral when the two are about equal, orange when the
// room will likely pay well past it. The gap is scaled by the size of the player (a $5 gap is big
// on a $10 player, nothing on a $90 one; gaps under ~$15 on $40+ players are model noise), so the
// colour only saturates when the gap is outside that noise.
const GREEN = [74, 222, 128];     // tailwind green-400
const NEUTRAL = [209, 213, 219];  // gray-300
const ORANGE = [249, 115, 22];    // orange-500

// -1 (room pays far more than the max) .. 0 (even) .. 1 (room stops far below it).
export function bidEdge(max, likely) {
  if (max == null || likely == null) return 0;
  const scale = Math.max(5, 0.3 * Math.max(max, likely));
  return Math.max(-1, Math.min(1, (max - likely) / scale));
}

export function bidColor(max, likely) {
  const t = bidEdge(max, likely);
  const end = t >= 0 ? GREEN : ORANGE;
  const k = Math.abs(t);
  const rgb = NEUTRAL.map((n, i) => Math.round(n + (end[i] - n) * k));
  return `rgb(${rgb.join(', ')})`;
}
