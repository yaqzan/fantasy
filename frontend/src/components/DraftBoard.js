import React, { useState, useEffect, useLayoutEffect, useRef } from 'react';
import DraftModal from './DraftModal';
import DraftSheet from './DraftSheet';
import usePlayerValues from '../usePlayerValues';
import { bidEdge } from '../bidColor';
import { auctionState, roomPrice, earlyMarkup, shareMaxOf } from '../auction';

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
  if (k < 0.12) return { color: 'rgb(var(--gray-400))' };
  return {
    backgroundColor: `rgba(${t > 0 ? STRONG : WEAK}, ${(0.05 + 0.4 * k).toFixed(2)})`,
    color: k > 0.45 ? 'rgb(var(--white))' : 'rgb(var(--gray-300))',
    fontWeight: k > 0.7 ? 700 : 500,
  };
};

// The bid ruler: a graduated rule with Aim, Max and Value at the same three marks in every row (%
// of the cell, RULER_UNIT apart), so they read as columns. The room's price is a smaller pointer
// on the same rule, placed by where it falls: before the aim, between two of the three, or past the
// value. ROOM_ZONES keeps its number clear of theirs.
const RULER_UNIT = 4.25;
const RULER = [3, 3 + 22 * RULER_UNIT];
const GRADUATIONS = Array.from({ length: 21 }, (_, i) => 3 + (i + 1) * RULER_UNIT);
const RAIL = { aim: 3 + 5 * RULER_UNIT, max: 3 + 13 * RULER_UNIT, value: 3 + 19 * RULER_UNIT };
const ROOM_ZONES = { low: [4, 15.5], bar: [33, 49.5], over: [67, 75], past: [92.5, 95.5] };
const roomAt = (room, aim, max, value) => {
  const [zone, lo, hi] = room < aim ? ['low', 0, aim] : room <= max ? ['bar', aim, max]
    : room <= value ? ['over', max, value] : ['past', value, value * 1.5];
  const [from, to] = ROOM_ZONES[zone];
  return from + Math.min(1, Math.max(0, hi > lo ? (room - lo) / (hi - lo) : 0.5)) * (to - from);
};


// Bid colours: the aim is green, the max amber, the value white. The room's price takes its colour
// from where it lands: green at or under the aim, grey up to the max, red past it.
const AIM = 'rgb(var(--green-400))';
const MAX = 'rgb(var(--amber-400))';
const ROOM_OVER = 'rgb(var(--rose-400))';
const roomColor = (room, aim, max) => (room <= aim ? AIM : room <= max ? 'rgb(var(--gray-400))' : ROOM_OVER);
const UNPRICED = 'rgb(var(--amber-400))';
// The aim is a share of the max that rises with the draft: a0 + (1 - a0) x (progress / AIM_FULL)^AIM_POWER, a0 = the
// file's 85% (stars 90%), full max once AIM_FULL of the league's spots are filled. Spot bar = SPOT_BAR x my $ per open
// spot until SPOT_BAR_UNTIL. gradient.py (122 curves, 6 rooms, best 8 re-scored on 1,800 fresh drafts): +0.08 categories
// a week over 85%-then-max at half-way, better in all six rooms; bidding more when richer than the room never helped.
const AIM_FULL = 0.8;
const AIM_POWER = 2;
const SPOT_BAR = 1.25;
const SPOT_BAR_UNTIL = 0.8;
const aimShare = (a0, progress) => a0 + (1 - a0) * Math.min(1, progress / AIM_FULL) ** AIM_POWER;
// Early in the draft the room pays most for mid-tier players (the room price carries the markup, auction.js EARLY):
// likely $5-25 bought in the first 20% returned 0.93 per $1, against 1.2-2.0 later (my_draft.py). Tagged while the
// markup is at least EARLY_TAG.
const EARLY_TAG = 1.2;
// Spots filled ahead of the room's average that turn the pace check red (the owner filled first of 14 in 2025).
// stress.py: 3 beat 2 in all eight simulated rooms (+0.02-0.05) and still never filled before 60% of the draft.
const PACE_AHEAD = 3;
// Spots behind the room, past half the draft, that show "don't chase": in rooms with nothing under the max the rules
// end with $30+ unspent, and every catch-up rule tested (bid to value, drop the aim, lower the bar) did worse.
const PACE_BEHIND = 3;

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
  // Touch screens: tapping a name opens the draft sheet ({ player, prices }); the last pick made there
  // shows an Undo toast for a few seconds.
  const touch = typeof window !== 'undefined' && window.matchMedia?.('(hover: none)').matches;
  const [sheet, setSheet] = useState(null);
  // Phones: the team chips in the room strip fold away, and the table takes the rest of the screen
  // (its own scroll box starts where it sits, so the page itself never needs scrolling first).
  const [showTeams, setShowTeams] = useState(false);
  const tableBox = useRef(null);
  const [fitHeight, setFitHeight] = useState(null);
  useLayoutEffect(() => {
    const fit = () => {
      const el = tableBox.current;
      if (!el || !window.matchMedia('(max-width: 639px)').matches) { setFitHeight(null); return; }
      const top = el.getBoundingClientRect().top + window.scrollY;
      setFitHeight(h => (h === top ? h : top));
    };
    fit();
    window.addEventListener('resize', fit);
    return () => window.removeEventListener('resize', fit);
  });
  const [lastPick, setLastPick] = useState(null);
  useEffect(() => {
    if (!lastPick) return undefined;
    const t = setTimeout(() => setLastPick(null), 8000);
    return () => clearTimeout(t);
  }, [lastPick]);
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

  // A max bid from an app $ by the Draft Day share rule (non-stars), never under the max at the top
  // of a cheaper tier: a $15 player at 80% ($12) would otherwise sit under a $14 one at 100%.
  const shareMax = (value) => Math.max(1, ...shareMaxOf(draftPlan.rule.shares, value));
  // The auction so far: the room's money and spots, each team's, and the factor the prices paid
  // put on the prices left. Mine also caps my bids (money less $1 for each other open spot).
  const settings = config?.league?.settings || {};
  const leagueTeams = fantasyTeams.filter(team => !team.eliminated_stage);
  const econ = draftPlan && leagueTeams.length
    ? auctionState({ players: allPlayers, likely: draftPlan.likely || {}, teams: leagueTeams,
                     budget: settings.draft?.budget || 200, rosterSize: settings.roster?.size || 1 })
    : null;
  const factor = econ?.factor ?? 1;
  const myId = leagueTeams.find(team => team.abbreviation === myTeam)?.id;
  const myMoney = econ?.teams[myId];
  const myCap = myMoney?.open > 0 ? myMoney.cap : Infinity;
  // The most any other team can bid now: late in the draft the room is broke and this is the price to win anyone.
  const othersCap = econ ? Math.max(0, ...leagueTeams.filter(t => t.id !== myId).map(t => econ.teams[t.id].cap)) : null;
  const progress = econ?.progress ?? 0;
  // My $ per open spot (above $1 each, plus the $1): before the last quarter of the draft a spot goes only to a
  // player valued at least this. Simulated auctions (auction_sim.py) +0.3-0.5 categories a week; holding out
  // for the aim with no such bar left $40-75 unspent.
  // My spots filled against the other teams' average: filling up early leaves no room for the cheap late rounds.
  const others = econ ? leagueTeams.filter(t => t.id !== myId).map(t => econ.teams[t.id]) : [];
  const roomFilled = others.length ? others.reduce((a, t) => a + t.count, 0) / others.length : null;
  const ahead = myMoney && roomFilled != null ? myMoney.count - roomFilled : 0;
  const spotBar = myMoney?.open > 0 && progress < SPOT_BAR_UNTIL ? SPOT_BAR * ((myMoney.left - myMoney.open) / myMoney.open + 1) : null;
  // The prices for one player: the max follows the Value column (stars sit at their break-even) and does not
  // move with the room's factor (scaling it by the room's spending was the worst rule in the simulated
  // auctions); only the room's price does (x the factor, x the early markup). The aim climbs to the max by AIM_FULL.
  const prices = (player) => {
    const value = getAuctionValue(player);
    if (!draftPlan) return { value };
    const star = draftPlan.rule.stars[player.name];
    const isStar = star != null;
    // No injury slot: a known absence to start the season holds a dead spot (draft_day.json rule.caps, injured.py).
    const cap = draftPlan.rule.caps?.[player.name];
    const max0 = cap != null ? cap : isStar ? star : shareMax(value || 1);
    const max = Math.max(1, Math.min(max0, myCap));
    const rule = draftPlan.aim;
    const aim = !rule || progress >= AIM_FULL ? null
      : isStar ? Math.max(1, Math.round(max * aimShare(rule.star, progress))) : max0 >= rule.floor ? Math.max(1, Math.round(max * aimShare(rule.other, progress))) : null;
    const likely0 = draftPlan.likely?.[player.name] ?? null;
    const likely = roomPrice(likely0, factor, progress);
    const belowBar = spotBar != null && !player.drafted && (value || 0) < spotBar;
    const markup = player.drafted ? 1 : earlyMarkup(likely0, progress);
    const early = markup >= EARLY_TAG ? markup : null;
    return { value, isStar, max, max0, aim, likely, likely0, belowBar, early, gap: likely == null ? null : max - likely, edge: bidEdge(max, likely) };
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
      // players to nominate: the room's likely price furthest past my max (they drain the room's money, not mine)
      case 'nominate': return player.drafted || p.gap == null || p.gap >= 0 ? null : -p.gap;
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
      {/* The key: off on phones (the Draft Day tab explains the rules) */}
      <div className="hidden sm:flex flex-wrap items-center gap-x-5 gap-y-1 px-4 py-2 text-xs text-gray-400 border-b border-gray-700">
        <span className="text-gray-300 font-medium tabular-nums">{sorted.length} players</span>
        {draftPlan && (
          <>
            <span><b style={{ color: AIM }}>Aim</b> your limit now: rises from 85% of max to the max by 80% of the draft</span>
            <span><b style={{ color: MAX }}>Max</b> never past it</span>
            <span><b className="text-white">Value</b> the app's $, not a limit</span>
            <span>
              Room's likely price: <b style={{ color: AIM }}>under your aim</b> · <b className="text-gray-400">up to your max</b> · <b style={{ color: ROOM_OVER }}>past it</b>
            </span>
            <span className="flex items-center gap-1.5">
              <span className="inline-block w-1.5 h-1.5 rounded-full" style={{ background: UNPRICED }} /> cheap strength worth having (A-TO, 3PM, TB)
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
        <div className="flex flex-wrap items-center gap-x-2 gap-y-1 px-2 sm:px-4 py-1.5 sm:py-2 text-xs text-gray-400 border-b border-gray-700">
          {/* Phones: the room in one short line */}
          {econ.priced > 0 && (
            <span className="sm:hidden mr-1 tabular-nums">
              <b className="text-gray-200">Room</b> <b style={{ color: factor < 0.97 ? AIM : factor > 1.03 ? ROOM_OVER : undefined }} className="text-gray-200">x{factor.toFixed(2)}</b>
            </span>
          )}
          <span className="hidden sm:inline mr-2 tabular-nums"
                title="Money the room has left above $1 a spot, against the likely prices of the best players left (one per open spot), compared with the same ratio before the draft. Under 1: the room has overpaid, so what is left should go cheaper, and the room prices below are scaled down with it; over 1 the other way. Kept between 0.5 and 1.5. On top of it, room prices carry an early markup the factor can't see yet: $5-25 players x1.6 until 20% of the draft (back to x1 by 35%), $26+ x1.1 (x1 by 25%). Your aim and max do not move with either. Picks entered without a price count at their likely price.">
            <b className="text-gray-200">Room</b> ${econ.left.toLocaleString()} left · {econ.open} spots ·{' '}
            {econ.priced === 0 ? 'prices move once picks have a $'
              : <b style={{ color: factor < 0.97 ? AIM : factor > 1.03 ? ROOM_OVER : undefined }} className="text-gray-200">
                  {factor < 0.97 ? 'overspent' : factor > 1.03 ? 'underspent'  : 'on its likely prices'}: prices left x{factor.toFixed(2)}
                </b>}
          </span>
          {myMoney && roomFilled != null && (
            <span className={`mr-2 tabular-nums ${ahead >= PACE_AHEAD ? 'rounded px-1.5 py-0.5 bg-rose-500/20 text-rose-200 font-semibold' : 'hidden sm:inline'}`}
                  title="Your spots filled against the other teams' average. Two or more ahead: slow down. Late players go for $1-8 because the room is broke, and they returned about 2x their price in past drafts; keep spots for them.">
              <b className={ahead >= PACE_AHEAD ? '' : 'text-gray-200'}>Pace</b> you {myMoney.count} of {myMoney.count + myMoney.open} · room {roomFilled.toFixed(1)}
              {ahead >= PACE_AHEAD ? ' · slow down' : ''}
            </span>
          )}
          {myMoney && roomFilled != null && -ahead >= PACE_BEHIND && progress >= 0.5 && (
            <span className="mr-2 rounded px-1.5 py-0.5 bg-amber-500/15 text-amber-200"
                  title="You are well behind the room past half the draft. In simulated rooms where nothing comes in under the max, holding was right: every catch-up rule (bid to full value, drop the aim, lower the spot bar) lost 0.02-0.45 categories a week. Keep bidding to your max; money left over is better than overpaying.">
              behind the room: don't chase, bid to your max
            </span>
          )}
          {othersCap != null && (
            <span className="mr-2 tabular-nums" title="The most any other team can bid right now (its money less $1 for each other open spot). Late in the draft the room runs dry: one dollar over this wins anyone.">
              <b className="text-gray-200"><span className="hidden sm:inline">Others' top</span><span className="sm:hidden">Top</span> bid</b> ${othersCap}
            </span>
          )}
          {spotBar != null && (
            <span className="mr-2 tabular-nums" title="1.25 x your money per open spot (above $1 each, plus the $1). Until 80% of the league's spots are filled, don't spend a spot on a player valued under this; rows under it are dimmed.">
              <b className="text-gray-200">Spot bar</b> ${Math.round(spotBar)}
            </span>
          )}
          {draftPlan?.aim && (
            <span className="mr-2 tabular-nums text-gray-300" title="Your bid limit as a share of the max. It starts at 85% (stars 90%) and climbs slowly, then faster, to the full max once 80% of the league's spots are filled.">
              <b className="text-gray-200">Aim</b> {progress >= AIM_FULL ? 'bid to your max' : <>{Math.round(100 * aimShare(draftPlan.aim.other, progress))}%<span className="hidden sm:inline"> of max</span></>}
            </span>
          )}
          <button onClick={() => setShowTeams(!showTeams)} aria-expanded={showTeams}
                  className="sm:hidden ml-auto rounded px-1.5 py-0.5 bg-gray-700/60 text-gray-300">
            Teams {showTeams ? '▴' : '▾'}
          </button>
          {leagueTeams.map(team => {
            const t = econ.teams[team.id];
            const me = team.abbreviation === myTeam;
            return (
              <span key={team.id} className={`${showTeams ? '' : 'hidden sm:inline'} rounded px-1.5 py-0.5 tabular-nums whitespace-nowrap ${me ? 'bg-nba-orange/20 text-orange-200' : 'bg-gray-700/60 text-gray-300'} ${t.open === 0 ? 'opacity-40' : ''}`}
                    title={t.open === 0 ? `${team.name}: roster full` : `${team.name}: $${t.left} left for ${t.open} spots, can bid up to $${t.cap}`}>
                {team.abbreviation || team.name} <b>${t.left}</b><span className="text-gray-500"> · {t.open}</span>
              </span>
            );
          })}
        </div>
      )}

      <div ref={tableBox} className="overflow-auto thin-scrollbar max-h-[calc(100dvh-2rem)] rounded-b-lg"
           style={fitHeight != null ? { maxHeight: `calc(100dvh - ${fitHeight}px - 0.5rem)` } : undefined}>
        <table className="min-w-full border-separate border-spacing-0 text-sm">
          <thead>
            <tr>
              <th className={`${TH} top-0 h-6 left-0 z-30`} />
              <th className={`${TH} top-0 h-6 text-left ${draftPlan ? 'border-l border-gray-700' : ''}`}>
                {draftPlan && (
                  <span className="flex items-center gap-2.5 font-medium normal-case tracking-normal">
                    <span className="text-nba-orange font-semibold uppercase tracking-wider">Bid</span>
                    <span className="text-gray-600">sort</span>
                    {[['edge', 'best buys'], ['nominate', 'nominate'], ['likely', 'room']].map(([k, label]) => (
                      <span key={k} className={`cursor-pointer hover:text-white ${sort === k ? 'text-white' : ''}`} onClick={() => sortBy(k)}
                            title={k === 'edge' ? "Your max against the room's likely price, scaled to his size (a few dollars on a star is noise): the players the room should let go cheapest first"
                              : k === 'nominate' ? "Players the room will likely pay most past your max: throw them out when it is your turn to nominate, early especially. Their money comes out of the other teams' budgets, not yours." : undefined}>
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
                  <div className="relative h-4 min-w-[13.5rem] sm:min-w-[26rem]">
                    {[['aim', "The price worth holding out for early in the draft: 90% of a star's max (a star is only worth it at a real discount), 85% of everyone else's from $15; under $15 it is the max. It climbs to the max by the time 80% of the league's spots are filled."],
                      ['max', "Don't bid past this. 85% of Value at $40+, 80% at $15-39, Value under $15; stars at their break-even."],
                      ['value', "The app's auction $ on the selected stats (follows the star premium and punts). Not a bid limit."]].map(([k, title]) => (
                      <span key={k} className={`absolute top-0 -translate-x-1/2 cursor-pointer hover:text-white `}
                            style={{ left: `${RAIL[k]}%`, color: { aim: AIM, max: MAX, value: 'rgb(var(--white))' }[k] }} onClick={() => sortBy(k)} title={title}>
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
                      title={unpriced ? `${c.label}: the room has not paid for it, and it moves weekly wins at least as much as an average category` : undefined}>
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
              const rowBg = mine ? 'bg-row-mine' : 'bg-gray-800 group-hover:bg-row-hover';
              return (
                <tr key={player.name} className={`group ${gone ? 'opacity-40' : ''}`}>
                  <td className={`${cell} ${rowBg} sticky left-0 z-10 w-[1%] pl-1 pr-1.5 sm:pl-3 sm:pr-3 py-1 ${mine ? 'shadow-[inset_3px_0_0_rgb(var(--accent))]' : ''} ${touch && caps.auction && fantasyTeams.length ? 'active:bg-row-hover' : ''}`}
                      onClick={touch && caps.auction && fantasyTeams.length ? () => (player.drafted
                        ? setModalPlayer({ ...player, overall_rank: rank, auction_value: p.value })
                        : setSheet({ player, prices: { aim: target === p.max ? null : target, max: p.max, likely: p.likely, value: p.value } })) : undefined}>
                    <div className="flex items-center gap-1.5 sm:gap-2.5">
                      <div className="w-5 sm:w-7 flex-none text-right tabular-nums text-xs text-gray-500 leading-tight">
                        {rank}
                        {moved !== 0 && <div className={`text-[10px] ${moved > 0 ? 'text-green-400' : 'text-red-400'}`}>{moved > 0 ? '+' : ''}{moved}</div>}
                      </div>
                      <div className="w-[8rem] sm:w-[14.5rem]">
                        <div className="flex items-center gap-1.5">
                          <span className="font-semibold text-gray-100 max-w-[7rem] sm:max-w-[11.5rem] truncate leading-tight" title={player.name}>{player.name}</span>
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
                          {p.early && <span className={`${TAG} bg-rose-500/15 text-rose-300`} title={`Early in the draft the room pays 1.5-2x for $5-25 players; the room price already carries x${p.early.toFixed(1)}. Bought in the first 20% they returned 0.93 per $1, against 1.2-2.0 later. Let him go now; he comes back cheaper.`}>early: room x{p.early.toFixed(1)}</span>}
                          {p.belowBar && <span className={`${TAG} bg-gray-700 text-gray-400`} title={`Valued under your $${Math.round(spotBar)} a spot: buying him now uses a spot your money should fill with a better player. Fine once 80% of the league's spots are filled.`}>not a spot yet</span>}
                        </div>
                      </div>
                    </div>
                  </td>
                  {draftPlan ? (
                    <td className={`${cell} ${rowBg} px-1.5 sm:px-2 py-1 border-l border-l-gray-700 ${p.belowBar ? 'opacity-40' : ''}`}
                        title={`Aim $${target} · max $${p.max} · room ${p.likely != null ? `$${p.likely}` : '-'} · value $${p.value}`
                          + (p.gap == null ? '' : p.gap >= 0 ? `. The room's likely price is $${p.gap} under your max.` : `. The room's likely price is $${-p.gap} over your max.`)
                          + (p.isStar ? ' A star is only worth it about 10% under his max; past that, pass.' : '')
                          + (p.max !== p.max0 || p.likely !== p.likely0 ? ` Likely before the draft: max $${p.max0}, room ${p.likely0 != null ? `$${p.likely0}` : '-'}${p.early ? ` (x${p.early.toFixed(1)} early now)` : ''}.` : '')
                          + (p.belowBar ? ` Under your $${Math.round(spotBar)} a spot: not worth a spot yet.` : '')}>
                      <div className="relative h-[34px] min-w-[13.5rem] sm:min-w-[26rem] tabular-nums">
                        {/* the ruler: a baseline with end stops, a graduation every unit, the aim-to-max span drawn heavy */}
                        <div className="absolute top-[29px] h-px bg-gray-600" style={{ left: `${RULER[0]}%`, width: `${RULER[1] - RULER[0]}%` }} />
                        {GRADUATIONS.map(x => <div key={x} className="absolute top-[26px] h-[3px] w-px bg-gray-600" style={{ left: `${x}%` }} />)}
                        {RULER.map(x => <div key={x} className="absolute top-[22px] h-[8px] w-px bg-gray-500" style={{ left: `${x}%` }} />)}
                        <div className="absolute top-[28px] h-[2px]"
                             style={{ left: `${RAIL.aim}%`, width: `${RAIL.max - RAIL.aim}%`, background: `linear-gradient(to right, ${AIM}, ${MAX})` }} />
                        {[['aim', target, AIM, 'text-[17px] font-extrabold'], ['max', p.max, MAX, 'text-[15px] font-bold top-px'], ['value', p.value, 'rgb(var(--white))', 'text-[15px] font-semibold top-px']].map(([k, dollars, color, size]) => (
                          <React.Fragment key={k}>
                            <span className={`absolute -translate-x-1/2 leading-none ${size}`} style={{ left: `${RAIL[k]}%`, color }}>${dollars}</span>
                            <div className="absolute top-[19px] h-[11px] w-[2px] -ml-px" style={{ left: `${RAIL[k]}%`, background: color }} />
                          </React.Fragment>
                        ))}
                        {p.likely != null && (() => {
                          const x = roomAt(p.likely, target, p.max, p.value);
                          const color = roomColor(p.likely, target, p.max);
                          return (
                            <>
                              <span className="absolute top-[7px] -translate-x-1/2 text-[11px] font-semibold leading-none" style={{ left: `${x}%`, color }}>{p.likely}</span>
                              <div className="absolute top-[20px] h-[10px] w-px" style={{ left: `${x}%`, background: color }} />
                            </>
                          );
                        })()}
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
                    className={`block w-full text-left px-3 h-[26px] text-xs whitespace-nowrap hover:bg-nba-orange hover:text-onaccent ${team.abbreviation === myTeam ? 'text-nba-orange font-semibold' : 'text-gray-200'}`}>
              {team.abbreviation || team.name}
            </button>
          ))}
        </div>
      )}

      {sheet && (
        <DraftSheet
          player={sheet.player}
          prices={sheet.prices}
          teams={leagueTeams}
          myTeam={myTeam}
          money={econ?.teams}
          onClose={() => setSheet(null)}
          onDraft={(team, price) => {
            setSheet(null);
            onDraftPlayer(sheet.player.name, team.id, price);
            clearBid(sheet.player.name);
            setLastPick({ name: sheet.player.name, team: team.abbreviation || team.name, price });
          }}
        />
      )}

      {lastPick && (
        <div className="fixed inset-x-3 bottom-[max(0.75rem,env(safe-area-inset-bottom))] z-50 flex items-center gap-3 rounded-lg bg-gray-900 border border-gray-600 shadow-2xl px-4 py-3 text-sm">
          <span className="flex-1 min-w-0 truncate text-gray-200">
            <b className="text-white">{lastPick.name}</b> to {lastPick.team}{lastPick.price != null ? ` for $${lastPick.price}` : ''}
          </span>
          <button onClick={() => { onUndraftPlayer(lastPick.name); setLastPick(null); }}
                  className="font-semibold text-nba-orange px-2 py-1">Undo</button>
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
