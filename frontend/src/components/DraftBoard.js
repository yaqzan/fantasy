import React, { useState } from 'react';
import DraftModal from './DraftModal';
import usePlayerValues from '../usePlayerValues';
import { bidColor, bidEdge } from '../bidColor';

// The Player Rankings table in draft mode: one dense row per player, built to be read while he is
// being bid on. Left to right: who he is, what to pay (aim, max), what the room will pay (likely,
// edge), then his categories as a heat strip and games. The rules that apply to him are tags beside his name.
// draftPlan: the Draft Day data (/api/draft-day) when it belongs to this league; without it the
// price columns are just the Value (or the draft round, in a snake league).

// Heat for a 0-100 score: neutral at 50, teal above, rose below (values stay printed, so the
// colour is never the only signal).
const STRONG = '45, 212, 191';
const WEAK = '244, 63, 94';
const heat = (score) => {
  if (score == null) return {};
  const t = Math.max(-1, Math.min(1, (score - 50) / 45));
  const k = Math.abs(t);
  if (k < 0.12) return { color: '#9ca3af' };
  return {
    backgroundColor: `rgba(${t > 0 ? STRONG : WEAK}, ${(0.05 + 0.4 * k).toFixed(2)})`,
    color: k > 0.45 ? '#f9fafb' : '#d1d5db',
    fontWeight: k > 0.7 ? 700 : 500,
  };
};

const EDGE_UNDER = 'rgb(74, 222, 128)';  // the room stops short of the max (bidColor's green)
const EDGE_OVER = 'rgb(249, 115, 22)';   // the room pays past it (bidColor's orange)
const UNPRICED = '#fbbf24';

// Draft Day notes by where they show: strengths and gaps are the heat strip, projected games the
// GP column, the rest tags under his name: rules and how the room prices him, and risks in amber.
const sortNotes = (notes = []) => {
  const out = { tags: [], risks: [], unpriced: [] };
  notes.forEach(n => {
    if (n.t.startsWith('unpriced ')) out.unpriced.push(...n.t.slice(9).split(' ').map(c => c.replace(/^\+/, '')));
    else if (/^[+-]\S+( [+-]\S+)*$/.test(n.t) || /^\d+g$/.test(n.t)) return;
    else if (n.k === 'bad') out.risks.push(n.t);
    else out.tags.push(n);
  });
  return out;
};

const TAG = 'inline-block rounded px-1 py-[2px] text-[10.5px] leading-none font-medium whitespace-nowrap';
const TH = 'sticky z-20 bg-gray-900 px-2 text-[11px] font-semibold uppercase tracking-wider text-gray-400 border-b border-gray-700 whitespace-nowrap select-none';
const NUM = 'px-2 py-1 text-right tabular-nums whitespace-nowrap';

const DraftBoard = ({ players, fantasyTeams, onDraftPlayer, onUndraftPlayer, onUpdatePlayer, priceExponent = null, config, statType = 'projected', punts = [], onPuntsChange, draftPlan = null }) => {
  const categories = config?.categories || [];
  const caps = config?.capabilities || {};
  const numTeams = config?.league?.settings?.num_teams || 1;
  const myTeam = config?.MY_TEAM_ABV;
  const [sort, setSort] = useState('rank');
  const [modalPlayer, setModalPlayer] = useState(null);
  const { customScores, loadingCustomScores, periodKey, getAuctionValue, getOverallRank, getZScore, getRank, getScore } =
    usePlayerValues({ punts, statType, priceExponent });

  // A max bid from an app $ by the Draft Day share rule (non-stars).
  const shareMax = (value) => {
    const [, share] = draftPlan.rule.shares.find(([floor]) => value >= floor) || [0, 1];
    return Math.max(1, Math.round(value * share));
  };
  // The prices for one player: the max follows the Value column (stars sit at their break-even),
  // the aim is the price worth holding out for early, the edge is the max against the room's price.
  const prices = (player) => {
    const value = getAuctionValue(player);
    if (!draftPlan) return { value };
    const star = draftPlan.rule.stars[player.name];
    const isStar = star != null;
    const max = isStar ? star : shareMax(value || 1);
    const rule = draftPlan.aim;
    const aim = !rule ? null : isStar ? Math.round(max * rule.star) : max >= rule.floor ? Math.round(max * rule.other) : null;
    const likely = draftPlan.likely?.[player.name] ?? null;
    return { value, isStar, max, aim, likely, gap: likely == null ? null : max - likely, edge: bidEdge(max, likely) };
  };
  const games = (player) => player.projected_games ?? player.games_played;
  const stat = (player, key, field) => {
    const s = player.stats?.[key];
    return s ? (s[periodKey(field)] ?? s[field]) : null;
  };

  const sortValue = (player) => {
    if (sort.startsWith('cat:')) return stat(player, sort.slice(4), 'value');
    const p = prices(player);
    switch (sort) {
      case 'score': return getScore(player);
      case 'name': return player.name;
      case 'value': return p.value;
      case 'max': return p.max;
      case 'aim': return p.aim ?? p.max;
      case 'likely': return p.likely;
      case 'edge': return p.gap == null ? null : p.edge * 1000 + p.gap;
      case 'gp': return games(player);
      default: return null;
    }
  };
  const byRank = (a, b) => (getRank(a) || 999) - (getRank(b) || 999);
  const sorted = [...players].sort((a, b) => {
    if (sort === 'rank') return byRank(a, b);
    const [x, y] = [sortValue(a), sortValue(b)];
    if (x == null || y == null) return (x == null) - (y == null) || byRank(a, b);
    if (sort === 'name') return x.localeCompare(y);
    return y - x || byRank(a, b);
  });
  // A click sorts by the column (highest first); a second click goes back to rank.
  const sortBy = (key) => setSort(sort === key ? 'rank' : key);
  const Head = ({ k, top = 'top-6', className = '', title, children }) => (
    <th className={`${TH} ${top} h-8 cursor-pointer hover:text-white ${sort === k ? 'text-white' : ''} ${className}`} onClick={() => sortBy(k)} title={title}>
      {children}{sort === k && <span className="text-nba-orange ml-0.5">{k === 'name' || k === 'rank' ? '↑' : '↓'}</span>}
    </th>
  );

  const unpricedLabels = new Set(draftPlan?.unpriced
    || Object.values(draftPlan?.notes || {}).flatMap(notes => sortNotes(notes).unpriced));
  const togglePunt = (key) => onPuntsChange?.(punts.includes(key) ? punts.filter(c => c !== key) : [...punts, key]);
  const priceColumns = draftPlan ? 5 : 1;

  return (
    <>
      <div className="flex flex-wrap items-center gap-x-5 gap-y-1 px-4 py-2 text-xs text-gray-400 border-b border-gray-700">
        <span className="text-gray-300 font-medium tabular-nums">{sorted.length} players</span>
        {draftPlan && (
          <>
            <span><b className="text-gray-200">Aim</b> hold out for this early</span>
            <span><b className="text-gray-200">Max</b> stop here</span>
            <span><b className="text-gray-200">Room</b> what they'll likely pay</span>
            <span className="flex items-center gap-1.5">
              <span className="inline-block w-3 h-2 rounded-sm" style={{ background: EDGE_UNDER }} /> room stops under your max
              <span className="inline-block w-3 h-2 rounded-sm ml-2" style={{ background: EDGE_OVER }} /> room pays past it
            </span>
            <span className="flex items-center gap-1.5">
              <span className="inline-block w-1.5 h-1.5 rounded-full" style={{ background: UNPRICED }} /> strength the room doesn't pay for
            </span>
          </>
        )}
        <span className="flex items-center gap-1.5">
          weak
          {[5, 27, 50, 73, 95].map(s => <span key={s} className="inline-block w-3 h-3 rounded-sm bg-gray-700/40" style={heat(s)} />)}
          strong
        </span>
        {loadingCustomScores && <span className="text-nba-orange">recalculating...</span>}
      </div>

      <div className="overflow-auto thin-scrollbar max-h-[calc(100vh-2rem)] rounded-b-lg">
        <table className="min-w-full border-separate border-spacing-0 text-sm">
          <thead>
            <tr>
              <th className={`${TH} top-0 h-6 left-0 z-30`} />
              <th className={`${TH} top-0 h-6 text-center ${draftPlan ? 'text-nba-orange border-l border-gray-700' : ''}`} colSpan={priceColumns}>
                {draftPlan ? 'Bid' : ''}
              </th>
              <th className={`${TH} top-0 h-6 text-center border-l border-gray-700`} colSpan={categories.length + 1}>
                {statType === 'proj' || statType === 'projected' ? 'Projected per game' : 'Per game'}
              </th>
              <th className={`${TH} top-0 h-6 border-l border-gray-700`} colSpan={2} />
            </tr>
            <tr>
              <th className={`${TH} top-6 h-8 left-0 z-30 text-left`}>
                <span className={`cursor-pointer hover:text-white ${sort === 'rank' ? 'text-white' : ''}`} onClick={() => setSort('rank')}>#</span>
                <span className={`cursor-pointer hover:text-white ml-4 ${sort === 'name' ? 'text-white' : ''}`} onClick={() => sortBy('name')}
                      title={draftPlan ? "Tags: the rule that applies to him and how this room prices his kind (discounts players over 30, pays up for young ones). Rocket: his max if he breaks out (second- and third-year players). Yr 3: his max with the average third-year correction." : undefined}>Player</span>
              </th>
              {draftPlan && (
                <>
                  <Head k="aim" className="text-right border-l border-gray-700"
                        title="The price worth holding out for early in the draft: 90% of a star's max (a star is only worth it at a real discount), 85% of everyone else's from $15. Loosen toward the max later if money is left.">Aim</Head>
                  <Head k="max" className="text-right text-nba-orange"
                        title="Don't bid past this. 85% of Value at $40+, 80% at $15-39, Value under $15; stars at their break-even.">Max</Head>
                  <Head k="likely" className="text-right"
                        title="What this room paid for his likely bid rank in 2025 (a guess: misses by $13-16 on $20+ players)">Room</Head>
                  <Head k="edge" className="text-center"
                        title="Your max against the room's likely price, scaled to his size (a few dollars on a star is noise). Green to the right: the room should stop short of your max. Orange to the left: it will likely pay past it.">Edge</Head>
                </>
              )}
              {caps.auction
                ? <Head k="value" className={`text-right ${draftPlan ? '' : 'border-l border-gray-700'}`} title="The app's auction $ on the selected stats (follows the star premium and punts). Not a bid limit.">Value</Head>
                : <th className={`${TH} top-6 h-8 text-right border-l border-gray-700`} title={`The draft round his rank goes in (${numTeams} teams)`}>Rd</th>}
              <Head k="score" className="text-center border-l border-gray-700" title="Overall score, 0-100, on the categories not punted">OVR</Head>
              {categories.map(c => {
                const unpriced = unpricedLabels.has(c.label);
                return (
                  <th key={c.key} className={`${TH} top-6 h-8 text-center !px-1 ${punts.includes(c.key) ? 'opacity-40' : ''} ${sort === `cat:${c.key}` ? 'text-white' : ''}`}
                      title={unpriced ? `${c.label}: this room has not paid for it` : undefined}>
                    <span className="inline-flex items-center gap-1">
                      {caps.punts && (
                        <input type="checkbox" checked={!punts.includes(c.key)} onChange={() => togglePunt(c.key)}
                               title="Uncheck to punt: leave it out of value"
                               className="h-2.5 w-2.5 rounded-sm border-gray-600 bg-gray-800 text-nba-orange focus:ring-0 focus:ring-offset-0 cursor-pointer" />
                      )}
                      <span className="cursor-pointer hover:text-white" onClick={() => sortBy(`cat:${c.key}`)}
                            style={unpriced ? { borderBottom: `2px solid ${UNPRICED}` } : undefined}>
                        {c.label}{sort === `cat:${c.key}` && <span className="text-nba-orange">↓</span>}
                      </span>
                    </span>
                  </th>
                );
              })}
              <Head k="gp" className="text-right border-l border-gray-700" title="Projected games this season (amber under 60). Hover a number for last season's.">GP</Head>
              <th className={`${TH} top-6 h-8`} />
            </tr>
          </thead>
          <tbody>
            {sorted.map(player => {
              const p = prices(player);
              const notes = sortNotes(draftPlan?.notes?.[player.name]);
              const mine = player.fantasy_team?.abbreviation && player.fantasy_team.abbreviation === myTeam;
              const gone = player.drafted && !mine;
              const rank = getRank(player);
              const moved = customScores[player.name] ? getOverallRank(player) - rank : 0;
              const score = Math.round(getScore(player));
              const scoreMoved = customScores[player.name] ? score - Math.round(getZScore(player)) : 0;
              const whatIf = draftPlan && !p.isStar ? player.what_if : null;
              const gp = games(player);
              const cell = 'border-b border-gray-700/60';
              const rowBg = mine ? 'bg-[#3a2c17]' : 'bg-gray-800 group-hover:bg-[#283548]';
              return (
                <tr key={player.name} className={`group ${gone ? 'opacity-40' : ''}`}>
                  <td className={`${cell} ${rowBg} sticky left-0 z-10 w-[1%] pl-3 pr-3 py-1 ${mine ? 'shadow-[inset_3px_0_0_#FF8C00]' : ''}`}>
                    <div className="flex items-center gap-2.5">
                      <div className="w-7 flex-none text-right tabular-nums text-xs text-gray-500 leading-tight">
                        {rank}
                        {moved !== 0 && <div className={`text-[10px] ${moved > 0 ? 'text-green-400' : 'text-red-400'}`}>{moved > 0 ? '+' : ''}{moved}</div>}
                      </div>
                      <div className="w-[14.5rem]">
                        <div className="flex items-center gap-1.5">
                          <span className="font-semibold text-gray-100 max-w-[11.5rem] truncate leading-tight" title={player.name}>{player.name}</span>
                          {p.isStar && <span className="text-[10px] text-nba-orange" title="Star: priced at his break-even, not the share rule">★</span>}
                          {player.is_injured && (
                            <span className={`${TAG} bg-red-600 text-white`}>
                              INJ{player.injured_return ? ` - ${player.injured_return}` : ''}{player.injured_games ? ` (${player.injured_games} missed)` : ''}
                            </span>
                          )}
                        </div>
                        <div className="flex flex-wrap items-center gap-x-1 gap-y-0.5 mt-0.5 text-[11px] text-gray-500 leading-tight">
                          <span className="whitespace-nowrap mr-0.5">{player.positions?.length ? player.positions.join('/') : player.position} · {player.team_abv || 'N/A'}</span>
                          {notes.tags.map(n => (
                            <span key={n.t} className={`${TAG} ${n.k === 'good' ? 'bg-emerald-500/15 text-emerald-300' : 'bg-gray-700 text-gray-200'}`}>{n.t}</span>
                          ))}
                          {whatIf && <span className={`${TAG} bg-emerald-500/15 text-emerald-300`} title={`${player.nba_year === 3 ? 'Third' : 'Second'}-year player: max bid if he breaks out`}>🚀 ${shareMax(whatIf.breakout)}</span>}
                          {whatIf && whatIf.corrected != null && <span className={`${TAG} bg-sky-500/15 text-sky-300`} title="Third-year player: max bid with the average third-year correction">yr 3 ${shareMax(whatIf.corrected)}</span>}
                          {notes.risks.map(r => <span key={r} className={`${TAG} bg-amber-500/15 text-amber-300`}>{r}</span>)}
                        </div>
                      </div>
                    </div>
                  </td>
                  {draftPlan && (
                    <>
                      <td className={`${cell} ${rowBg} ${NUM} text-gray-300 border-l border-l-gray-700`}
                          title={p.aim == null ? 'Under $15: the max is the price' : p.isStar ? 'A star is only worth it about 10% under his max; past that, pass' : 'Worth holding out for early in the draft; go to the max later if money is left'}>
                        {p.aim != null ? `$${p.aim}` : <span className="text-gray-600">-</span>}
                      </td>
                      <td className={`${cell} ${NUM} ${mine ? 'bg-[#3a2c17]' : 'bg-[#2a2a2a] group-hover:bg-[#33302b]'} text-lg font-extrabold leading-none`} style={{ color: bidColor(p.max, p.likely) }}>
                        ${p.max}
                      </td>
                      <td className={`${cell} ${rowBg} ${NUM} text-gray-400`}>{p.likely != null ? `$${p.likely}` : <span className="text-gray-600">-</span>}</td>
                      <td className={`${cell} ${rowBg} px-2 py-1`}
                          title={p.gap == null ? undefined : p.gap >= 0 ? `Room's likely price is $${p.gap} under your max` : `Room's likely price is $${-p.gap} over your max`}>
                        {p.gap != null && (
                          <div className="flex items-center gap-1.5">
                            <div className="relative w-14 h-2.5 flex-none">
                              <div className="absolute inset-y-0 left-1/2 w-px bg-gray-500" />
                              <div className="absolute inset-y-0.5 rounded-sm"
                                   style={p.edge >= 0
                                     ? { left: '50%', width: `${p.edge * 50}%`, background: EDGE_UNDER }
                                     : { right: '50%', width: `${-p.edge * 50}%`, background: EDGE_OVER }} />
                            </div>
                            <span className="w-7 text-right text-xs tabular-nums text-gray-300">{p.gap > 0 ? '+' : ''}{p.gap}</span>
                          </div>
                        )}
                      </td>
                    </>
                  )}
                  <td className={`${cell} ${rowBg} ${NUM} text-gray-500 ${draftPlan ? '' : 'border-l border-l-gray-700 text-gray-200 font-semibold'}`}>
                    {caps.auction ? `$${p.value}` : Math.ceil((rank || 0) / numTeams) || '-'}
                  </td>
                  <td className={`${cell} ${rowBg} p-0.5 pl-1.5 border-l border-l-gray-700`}>
                    <div className="h-7 min-w-[2.5rem] px-1 rounded-sm flex items-center justify-center gap-0.5 tabular-nums text-[13px]" style={{ ...heat(score), fontWeight: 700 }}>
                      {score}
                      {scoreMoved !== 0 && <span className={`text-[10px] ${scoreMoved > 0 ? 'text-green-300' : 'text-red-300'}`}>{scoreMoved > 0 ? '+' : ''}{scoreMoved}</span>}
                    </div>
                  </td>
                  {categories.map(c => {
                    const value = stat(player, c.key, 'value');
                    const catScore = stat(player, c.key, 'score');
                    const edge = notes.unpriced.includes(c.label);
                    return (
                      <td key={c.key} className={`${cell} ${rowBg} p-0.5 ${punts.includes(c.key) ? 'opacity-30' : ''}`}
                          title={value == null ? undefined : `${c.label} ${value}${c.percent ? '%' : ''}: score ${catScore}${edge ? ', and this room has not paid for it' : ''}`}>
                        <div className="relative h-7 min-w-[2.75rem] px-1 rounded-sm flex items-center justify-center tabular-nums text-[13px]" style={heat(catScore)}>
                          {value == null ? <span className="text-gray-600">-</span> : <>{c.key === 'PLUS_MINUS' && value > 0 ? '+' : ''}{value}</>}
                          {edge && <span className="absolute top-[3px] right-[3px] w-1.5 h-1.5 rounded-full" style={{ background: UNPRICED }} />}
                        </div>
                      </td>
                    );
                  })}
                  <td className={`${cell} ${rowBg} ${NUM} border-l border-l-gray-700 ${gp != null && gp < 60 ? 'text-amber-400 font-semibold' : 'text-gray-300'}`}
                      title={player.projected_only ? 'No NBA games last season (rookie, or out all year): valued on his projection only'
                        : `${player.games_played} games last season${player.small_sample ? ': a small sample, his numbers may not hold' : ''}`}>
                    {gp ?? '-'}{player.projected_only && <span className="text-sky-400 text-[10px] ml-0.5">new</span>}
                  </td>
                  <td className={`${cell} ${rowBg} px-2 py-1 text-right`}>
                    <button
                      onClick={() => setModalPlayer({ ...player, overall_rank: rank, auction_value: p.value })}
                      disabled={fantasyTeams.length === 0}
                      className={player.drafted
                        ? 'rounded px-2 py-1 text-xs font-semibold bg-gray-600 text-white hover:bg-gray-500'
                        : 'rounded px-2 py-1 text-xs font-medium border border-gray-600 text-gray-300 hover:border-nba-orange hover:text-nba-orange disabled:opacity-40'}
                      title={player.drafted ? 'Change or undo' : 'Mark him drafted'}
                    >
                      {player.drafted ? (player.fantasy_team?.abbreviation || player.fantasy_team?.name || 'Taken') : 'Draft'}
                    </button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {modalPlayer && (
        <DraftModal
          player={modalPlayer}
          teams={fantasyTeams}
          onClose={() => setModalPlayer(null)}
          onDraft={onDraftPlayer}
          onUndraft={onUndraftPlayer}
          onUpdatePlayer={onUpdatePlayer}
          isDrafted={modalPlayer.drafted}
        />
      )}
    </>
  );
};

export default DraftBoard;
