import React, { useState, useEffect } from 'react';
import DraftModal from './DraftModal';
import usePlayerValues from '../usePlayerValues';
import { bidEdge } from '../bidColor';
import { auctionState, adjusted } from '../auction';

// The Player Rankings table in draft mode: one dense row per player, built to be read while he is
// being bid on. Left to right: who he is, what to pay (aim, max), what the room will pay (likely,
// edge), then his categories as a heat strip and games. The rules that apply to him are tags beside his name.
// draftPlan: the Draft Day data (/api/draft-day) when it belongs to this league; without it the
// price columns are just the Value (or the draft round, in a snake league).
// allPlayers: every player, filtered out or not: the prices paid so far move the prices left (auction.js).

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

// The bid rail: Aim, Max and Value sit at the same three places in every row (% of the cell), so
// they read as columns. The room's price is a quiet number on the rail, placed by where it falls:
// before the aim, between two of the three, or past the value. ROOM_ZONES keeps it clear of them.
const RAIL = { aim: 24, max: 58, value: 84 };
const ROOM_ZONES = { low: [3, 15.5], bar: [32.5, 49.5], over: [66.5, 75.5], past: [92.5, 96] };
const roomAt = (room, aim, max, value) => {
  const [zone, lo, hi] = room < aim ? ['low', 0, aim] : room <= max ? ['bar', aim, max]
    : room <= value ? ['over', max, value] : ['past', value, value * 1.5];
  const [from, to] = ROOM_ZONES[zone];
  return from + Math.min(1, Math.max(0, hi > lo ? (room - lo) / (hi - lo) : 0.5)) * (to - from);
};


// Bid colours: the aim is green, the max amber, the value white. The room's price takes its colour
// from where it lands: green at or under the aim, grey up to the max, red past it.
const AIM = '#4ade80';
const MAX = '#fbbf24';
const ROOM_OVER = '#fb7185';
const roomColor = (room, aim, max) => (room <= aim ? AIM : room <= max ? '#9ca3af' : ROOM_OVER);
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

const DraftBoard = ({ players, allPlayers = players, fantasyTeams, onDraftPlayer, onUndraftPlayer, onUpdatePlayer, priceExponent = null, config, statType = 'projected', punts = [], onPuntsChange, draftPlan = null }) => {
  const categories = config?.categories || [];
  const caps = config?.capabilities || {};
  const numTeams = config?.league?.settings?.num_teams || 1;
  const myTeam = config?.MY_TEAM_ABV;
  const [sort, setSort] = useState('rank');
  const [modalPlayer, setModalPlayer] = useState(null);
  // The Draft button's team menu: { name, top, right } (fixed to the button, so the table's scroll can't clip it).
  const [teamMenu, setTeamMenu] = useState(null);
  useEffect(() => {
    if (!teamMenu) return undefined;
    const close = () => setTeamMenu(null);
    const onKey = (e) => { if (e.key === 'Escape') close(); };
    window.addEventListener('click', close);
    window.addEventListener('scroll', close, true);
    window.addEventListener('resize', close);
    window.addEventListener('keydown', onKey);
    return () => {
      window.removeEventListener('click', close);
      window.removeEventListener('scroll', close, true);
      window.removeEventListener('resize', close);
      window.removeEventListener('keydown', onKey);
    };
  }, [teamMenu]);
  const openTeamMenu = (e, player) => {
    e.stopPropagation();
    const box = e.currentTarget.getBoundingClientRect();
    const height = Math.min(window.innerHeight - 16, fantasyTeams.length * 26 + 10);
    e.currentTarget.focus();
    setTeamMenu(teamMenu?.name === player.name ? null
      : { name: player.name, right: window.innerWidth - box.left + 6, top: Math.max(8, Math.min(box.top - 4, window.innerHeight - height - 8)) });
  };
  const { customScores, loadingCustomScores, periodKey, getAuctionValue, getOverallRank, getZScore, getRank, getScore } =
    usePlayerValues({ punts, statType, priceExponent });

  // A max bid from an app $ by the Draft Day share rule (non-stars).
  const shareMax = (value) => {
    const [, share] = draftPlan.rule.shares.find(([floor]) => value >= floor) || [0, 1];
    return Math.max(1, Math.round(value * share));
  };
  // The auction so far: the room's money and spots, each team's, and the factor the prices paid
  // put on the prices left. Mine also caps my bids (money less $1 for each other open spot).
  const settings = config?.league?.settings || {};
  const leagueTeams = fantasyTeams.filter(team => !team.eliminated_stage);
  const econ = draftPlan && leagueTeams.length
    ? auctionState({ players: allPlayers, likely: draftPlan.likely || {}, teams: leagueTeams,
                     budget: settings.draft?.budget || 200, rosterSize: settings.roster?.size || 1 })
    : null;
  const factor = econ?.factor ?? 1;
  const myMoney = econ?.teams[leagueTeams.find(team => team.abbreviation === myTeam)?.id];
  const myCap = myMoney?.open > 0 ? myMoney.cap : Infinity;
  // The prices for one player: the max follows the Value column (stars sit at their break-even),
  // the aim is the price worth holding out for early, the edge is the max against the room's price.
  // Max, aim and the room's price all move with the auction's factor; max0 / likely0 are pre-draft.
  const prices = (player) => {
    const value = getAuctionValue(player);
    if (!draftPlan) return { value };
    const star = draftPlan.rule.stars[player.name];
    const isStar = star != null;
    const max0 = isStar ? star : shareMax(value || 1);
    const max = Math.max(1, Math.min(adjusted(max0, factor), myCap));
    const rule = draftPlan.aim;
    const aim = !rule ? null : isStar ? Math.max(1, Math.round(max * rule.star)) : max0 >= rule.floor ? Math.max(1, Math.round(max * rule.other)) : null;
    const likely0 = draftPlan.likely?.[player.name] ?? null;
    const likely = adjusted(likely0, factor);
    return { value, isStar, max, max0, aim, likely, likely0, gap: likely == null ? null : max - likely, edge: bidEdge(max, likely) };
  };
  // The $ typed beside a Draft button, by player; sent with the pick.
  const [bids, setBids] = useState({});
  const bidFor = (name) => (/^\d+$/.test(bids[name] ?? '') ? parseInt(bids[name], 10) : null);
  const clearBid = (name) => setBids(({ [name]: _, ...rest }) => rest);
  // A drafted player's price, corrected in place
  const savePrice = (player) => {
    const price = bidFor(player.name);
    if (price != null && price !== player.draft_price) onDraftPlayer(player.name, player.fantasy_team.id, price);
    clearBid(player.name);
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

  return (
    <>
      <div className="flex flex-wrap items-center gap-x-5 gap-y-1 px-4 py-2 text-xs text-gray-400 border-b border-gray-700">
        <span className="text-gray-300 font-medium tabular-nums">{sorted.length} players</span>
        {draftPlan && (
          <>
            <span><b style={{ color: AIM }}>Aim</b> hold out for this early</span>
            <span><b style={{ color: MAX }}>Max</b> never past it</span>
            <span><b className="text-white">Value</b> the app's $, not a limit</span>
            <span>
              Room's likely price: <b style={{ color: AIM }}>under your aim</b> · <b className="text-gray-400">up to your max</b> · <b style={{ color: ROOM_OVER }}>past it</b>
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

      {econ && (
        <div className="flex flex-wrap items-center gap-x-2 gap-y-1 px-4 py-2 text-xs text-gray-400 border-b border-gray-700">
          <span className="mr-2 tabular-nums"
                title="Money the room has left above $1 a spot, against the likely prices of the best players left (one per open spot), compared with the same ratio before the draft. Under 1: the room has overpaid, so what is left should go cheaper, and the aim, max and room prices below are scaled down with it; over 1 the other way. Kept between 0.5 and 1.5. Picks entered without a price count at their likely price.">
            <b className="text-gray-200">Room</b> ${econ.left.toLocaleString()} left · {econ.open} spots ·{' '}
            {econ.priced === 0 ? 'prices move once picks have a $'
              : <b style={{ color: factor < 0.97 ? AIM : factor > 1.03 ? ROOM_OVER : undefined }} className="text-gray-200">
                  {factor < 0.97 ? 'overspent' : factor > 1.03 ? 'underspent'  : 'on its likely prices'}: prices left x{factor.toFixed(2)}
                </b>}
          </span>
          {leagueTeams.map(team => {
            const t = econ.teams[team.id];
            const me = team.abbreviation === myTeam;
            return (
              <span key={team.id} className={`rounded px-1.5 py-0.5 tabular-nums whitespace-nowrap ${me ? 'bg-nba-orange/20 text-orange-200' : 'bg-gray-700/60 text-gray-300'} ${t.open === 0 ? 'opacity-40' : ''}`}
                    title={t.open === 0 ? `${team.name}: roster full` : `${team.name}: $${t.left} left for ${t.open} spots, can bid up to $${t.cap}`}>
                {team.abbreviation || team.name} <b>${t.left}</b><span className="text-gray-500"> · {t.open}</span>
              </span>
            );
          })}
        </div>
      )}

      <div className="overflow-auto thin-scrollbar max-h-[calc(100vh-2rem)] rounded-b-lg">
        <table className="min-w-full border-separate border-spacing-0 text-sm">
          <thead>
            <tr>
              <th className={`${TH} top-0 h-6 left-0 z-30`} />
              <th className={`${TH} top-0 h-6 text-left ${draftPlan ? 'border-l border-gray-700' : ''}`}>
                {draftPlan && (
                  <span className="flex items-center gap-2.5 font-medium normal-case tracking-normal">
                    <span className="text-nba-orange font-semibold uppercase tracking-wider">Bid</span>
                    <span className="text-gray-600">sort</span>
                    {[['edge', 'best buys'], ['likely', 'room']].map(([k, label]) => (
                      <span key={k} className={`cursor-pointer hover:text-white ${sort === k ? 'text-white' : ''}`} onClick={() => sortBy(k)}
                            title={k === 'edge' ? "Your max against the room's likely price, scaled to his size (a few dollars on a star is noise): the players the room should let go cheapest first" : undefined}>
                        {label}{sort === k && <span className="text-nba-orange">↓</span>}
                      </span>
                    ))}
                  </span>
                )}
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
              {draftPlan ? (
                <th className={`${TH} top-6 h-8 border-l border-gray-700`}>
                  <div className="relative h-4 min-w-[26rem]">
                    {[['aim', "The price worth holding out for early in the draft: 90% of a star's max (a star is only worth it at a real discount), 85% of everyone else's from $15; under $15 it is the max. Loosen toward the max later if money is left."],
                      ['max', "Don't bid past this. 85% of Value at $40+, 80% at $15-39, Value under $15; stars at their break-even."],
                      ['value', "The app's auction $ on the selected stats (follows the star premium and punts). Not a bid limit."]].map(([k, title]) => (
                      <span key={k} className={`absolute top-0 -translate-x-1/2 cursor-pointer hover:text-white `}
                            style={{ left: `${RAIL[k]}%`, color: { aim: AIM, max: MAX, value: '#fff' }[k] }} onClick={() => sortBy(k)} title={title}>
                        {k}{sort === k && <span className="text-nba-orange">↓</span>}
                      </span>
                    ))}
                  </div>
                </th>
              ) : caps.auction
                ? <Head k="value" className="text-right border-l border-gray-700" title="The app's auction $ on the selected stats (follows the star premium and punts)">Value</Head>
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
              const target = p.aim ?? p.max;
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
                  {draftPlan ? (
                    <td className={`${cell} ${rowBg} px-2 py-1 border-l border-l-gray-700`}
                        title={`Aim $${target} · max $${p.max} · room ${p.likely != null ? `$${p.likely}` : '-'} · value $${p.value}`
                          + (p.gap == null ? '' : p.gap >= 0 ? `. The room's likely price is $${p.gap} under your max.` : `. The room's likely price is $${-p.gap} over your max.`)
                          + (p.isStar ? ' A star is only worth it about 10% under his max; past that, pass.' : '')
                          + (p.max !== p.max0 || p.likely !== p.likely0 ? ` Before the draft: max $${p.max0}, room ${p.likely0 != null ? `$${p.likely0}` : '-'}.` : '')}>
                      <div className="relative h-7 min-w-[26rem] tabular-nums">
                        <div className="absolute top-1/2 border-t border-dotted border-gray-600" style={{ left: '3%', right: '4%' }} />
                        <div className="absolute top-1/2 h-px bg-gray-500" style={{ left: `${RAIL.max}%`, width: `${RAIL.value - RAIL.max}%` }} />
                        <div className="absolute top-1/2 -mt-[1.5px] h-[3px] rounded-full"
                             style={{ left: `${RAIL.aim}%`, width: `${RAIL.max - RAIL.aim}%`, background: `linear-gradient(to right, ${AIM}, ${MAX})`, opacity: 0.75 }} />
                        {p.likely != null && (
                          <span className={`absolute top-1/2 -translate-x-1/2 -translate-y-1/2 ${rowBg} px-1 text-[11px] font-semibold leading-none`}
                                style={{ left: `${roomAt(p.likely, target, p.max, p.value)}%`, color: roomColor(p.likely, target, p.max), opacity: 0.85 }}>
                            {p.likely}
                          </span>
                        )}
                        <span className={`absolute top-1/2 -translate-x-1/2 -translate-y-1/2 ${rowBg} px-1.5 text-[17px] font-extrabold leading-none`}
                              style={{ left: `${RAIL.aim}%`, color: AIM }}>${target}</span>
                        <span className={`absolute top-1/2 -translate-x-1/2 -translate-y-1/2 ${rowBg} px-1.5 text-[15px] font-bold leading-none`}
                              style={{ left: `${RAIL.max}%`, color: MAX }}>${p.max}</span>
                        <span className={`absolute top-1/2 -translate-x-1/2 -translate-y-1/2 ${rowBg} px-1.5 text-[15px] font-semibold leading-none text-white`}
                              style={{ left: `${RAIL.value}%` }}>${p.value}</span>
                      </div>
                    </td>
                  ) : (
                    <td className={`${cell} ${rowBg} ${NUM} border-l border-l-gray-700 text-gray-200 font-semibold`}>
                      {caps.auction ? `$${p.value}` : Math.ceil((rank || 0) / numTeams) || '-'}
                    </td>
                  )}
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
                  <td className={`${cell} ${rowBg} px-2 py-1 text-right whitespace-nowrap`}>
                    {caps.auction && (
                      <input
                        type="text" inputMode="numeric" placeholder="$" aria-label={`Price paid for ${player.name}`}
                        value={bids[player.name] ?? (player.drafted ? player.draft_price ?? '' : '')}
                        onChange={(e) => setBids({ ...bids, [player.name]: e.target.value.replace(/\D/g, '').slice(0, 3) })}
                        onBlur={() => player.drafted && bids[player.name] != null && savePrice(player)}
                        onKeyDown={(e) => {
                          if (e.key !== 'Enter') return;
                          if (player.drafted) e.currentTarget.blur();
                          else e.currentTarget.nextSibling.click();
                        }}
                        disabled={fantasyTeams.length === 0}
                        title={player.drafted ? 'The price paid: type over it to correct' : 'The winning bid, then Draft and the team'}
                        className="w-9 mr-1 rounded border border-gray-600 bg-gray-900 px-1 py-1 text-xs text-right tabular-nums text-gray-100 placeholder-gray-600 focus:border-nba-orange focus:outline-none focus:ring-0"
                      />
                    )}
                    <button
                      onClick={(e) => player.drafted ? setModalPlayer({ ...player, overall_rank: rank, auction_value: p.value }) : openTeamMenu(e, player)}
                      disabled={fantasyTeams.length === 0}
                      className={player.drafted
                        ? 'rounded px-2 py-1 text-xs font-semibold bg-gray-600 text-white hover:bg-gray-500'
                        : 'rounded px-2 py-1 text-xs font-medium border border-gray-600 text-gray-300 hover:border-nba-orange hover:text-nba-orange disabled:opacity-40'}
                      title={player.drafted ? 'Change or undo' : 'Pick the team that bought him'}
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

      {teamMenu && (
        <div className="fixed z-50 py-1 rounded-md bg-gray-900 border border-gray-600 shadow-xl overflow-y-auto thin-scrollbar"
             style={{ top: teamMenu.top, right: teamMenu.right, maxHeight: 'calc(100vh - 16px)' }}>
          {fantasyTeams.filter(team => !team.eliminated_stage).map(team => (
            <button key={team.id}
                    onClick={() => { setTeamMenu(null); onDraftPlayer(teamMenu.name, team.id, bidFor(teamMenu.name)); clearBid(teamMenu.name); }}
                    className={`block w-full text-left px-3 h-[26px] text-xs whitespace-nowrap hover:bg-nba-orange hover:text-gray-900 ${team.abbreviation === myTeam ? 'text-nba-orange font-semibold' : 'text-gray-200'}`}>
              {team.abbreviation || team.name}
            </button>
          ))}
        </div>
      )}

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
