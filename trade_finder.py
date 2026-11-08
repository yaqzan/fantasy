"""Trade finder for a Yahoo daily-lineup points league: x-for-(x-1) trades (2 for 1, 3 for 2) where the roster spot the trade
frees is rented to a streamer.

The math is the week plan's (claim_planner.py), applied to a hypothetical roster, for a few normal weeks after this one:
  my side      value(R) = the week plan's expected FPTS for roster R with its claims (adds fill the open spot, drops are free),
               so a trade that gives up k players for k-1 is scored WITH its freed spot streamed.
               swap = the same roster with no claims at all (what the trade does to the lineup alone);
               slot = value - swap, minus what the claims were already worth to the roster I have today.
  their side   the lineup value with no claims; a team that receives k and gives k-1 holds one player too many and cuts the
               one that costs least (the forced drop). They win when that value goes up.
  funnel       (A) additive FPTS-per-week proxy, every combination -> (B) the exact lineup value of both rosters, no claims
               -> (C) the planner's ILP on my side. The ILP runs on the survivors only.
Read-only: nothing is written to the DB. Detail: .claude/docs/trade-finder.md.

    python trade_finder.py [league] [give player ...]
"""
from __future__ import annotations

import copy
import dataclasses
import itertools
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date

import numpy as np

SAMPLE_WEEKS = 3          # normal 7-day weeks after the current one that the value is averaged over
STAGE_A_KEEP = (1200, 6000)   # combinations (2 for 1, 3 for 2) that get the exact no-claims lineup value
STAGE_C = (36, 90)        # combinations (2 for 1, 3 for 2) that get the ILP: 3 for 2 has more near-ties
CTX_TTL = 120             # a league's built weeks, seconds


# ---------------------------------------------------------------- the weeks

def sample_weeks(lg, n=SAMPLE_WEEKS):
    """[(start, end)] of the next `n` seven-day fantasy weeks after the current one (a trade lands after this week is mostly
    played; the two-week matchups are skipped: their claims and days don't compare)."""
    from fantasy_team_helper import get_current_fantasy_week_dates, get_next_week_dates
    cur = get_current_fantasy_week_dates(lg)[0]
    out = []
    for _ in range(30):
        ws, we = get_next_week_dates(lg, cur)
        if ws is None:
            break
        cur = ws
        if (we - ws).days + 1 == 7:
            out.append((ws, we))
        if len(out) == n:
            break
    return out


def weeks_left(lg, first_start):
    """Season weeks from `first_start` to the end of the schedule (the playoffs' last week), in 7-day units."""
    ws = lg.weeks()
    if not ws:
        return 0.0
    end = date.fromisoformat(max(w['end'] for w in ws))
    return max((end - first_start).days + 1, 0) / 7.0


# ---------------------------------------------------------------- rosters

def team_rosters(lg):
    """{abv: {'name', 'active': [players], 'il': [players]}} for every team in the league, from the DB (synced hourly)."""
    from fantasy_database import FantasyTeam, FantasyTeamPlayer
    from fantasy_team_helper import league_team_ids
    ids = league_team_ids(lg)
    out = {}
    for t in FantasyTeam.select().where(FantasyTeam.id.in_(ids)):
        if not t.abv:
            continue
        rows = list(FantasyTeamPlayer.select().where(FantasyTeamPlayer.fantasy_team_id == t.id))
        out[t.abv] = {'name': t.name, 'active': [r.player_name for r in rows if not r.il],
                      'il': [r.player_name for r in rows if r.il]}
    return out


# ---------------------------------------------------------------- context: one planner instance per sample week, everyone owned

class Ctx:
    """Per sample week: the planner Instance built on EVERY rostered player (owned=True) plus the free-agent pool; a
    hypothetical roster is a copy of it with other ownership flags. `v[week][player]` = the FPTS array the planner scores."""

    def __init__(self, lg, weeks, suffix):
        import lineup_optimizer as lo
        import claim_planner as cp
        self.lg, self.weeks, self.suffix = lg, weeks, suffix
        self.rosters = team_rosters(lg)
        everyone = [p for r in self.rosters.values() for p in r['active']]
        everyone_il = [p for r in self.rosters.values() for p in r['il']]
        self.insts, self.v = [], []
        for ws, we in weeks:
            week = lo.Week(lg, ws, we)
            inst, _ = cp.build_instance(lg, week, suffix, None, (everyone, everyone_il))
            self.insts.append(inst)
            self.v.append({p: np.asarray(d.v, dtype=float) for p, d in inst.players.items()})
        self.built = time.time()
        inst = self.insts[0]
        self.N, self.avail = inst.N, inst.avail
        # layer weights c_k of the planner's objective for a normal day (every day has the league's 9 slots)
        self.c = np.zeros(self.N)
        for k, ck in cp.layer_coefs(inst.n_slots[0], self.N, self.avail).items():
            self.c[k - 1] = ck
        self.me = lg.my_team

    def player(self, name, w=0):
        return self.insts[w].players.get(name)

    def droppable(self, name):
        d = self.player(name)
        return d is not None and not d.undroppable

    # -- the no-claims lineup value of a fixed roster (the planner's objective with C = 0 and no drops)
    def lineup(self, w, names):
        v = self.v[w]
        rows = [v[p] for p in names if p in v]
        if not rows:
            return 0.0
        m = -np.sort(-np.vstack(rows), axis=0)
        cum = np.cumsum(m, axis=0)
        if cum.shape[0] < self.N:
            cum = np.vstack([cum, np.repeat(cum[-1:], self.N - cum.shape[0], axis=0)])
        return float((self.c[:, None] * cum[:self.N]).sum())

    def lineup_avg(self, names):
        return sum(self.lineup(w, names) for w in range(len(self.weeks))) / len(self.weeks)

    def with_forced_drop(self, names, il_used=0):
        """(average lineup value, [dropped players]) of a roster, after cutting the cheapest players if it is over the size.
        Players who are OUT go to a free IL slot first (`il_used` of the K are taken), so only a full IL costs a cut.
        Players the planner calls undroppable (market rule, can't-cut) stay."""
        room = max(self.insts[0].K - il_used, 0)
        out = [p for p in names if self.player(p) and self.player(p).out][:room]
        names = [p for p in names if p not in out]
        over = len(names) - self.N
        if over <= 0:
            return self.lineup_avg(names), []
        cand = [p for p in names if self.droppable(p)]
        best = (-1e18, [])
        for drop in itertools.combinations(cand, over):
            keep = [p for p in names if p not in drop]
            val = self.lineup_avg(keep)
            if val > best[0]:
                best = (val, list(drop))
        return best

    # -- my roster with the claims (the ILP)
    def plan(self, w, active, il, claims):
        import claim_planner as cp
        inst = self.insts[w]
        players = {}
        for p in list(active) + list(il):
            d = inst.players.get(p)
            if d is None:
                continue
            d = copy.copy(d)
            d.owned, d.il, d.first_add = True, p in il, None
            players[p] = d
        for p, d in inst.players.items():
            if not d.owned and d.first_add is not None:
                players[p] = d
        inst2 = dataclasses.replace(inst, players=players, claims_left=claims,
                                    healthy_in_il=sorted(p for p in il if p in players and not players[p].out))
        return cp.solve(inst2)


_ctx = {}
_ctx_lock = threading.Lock()


def context(lg, suffix, n=SAMPLE_WEEKS):
    key = (lg.id, suffix, n)
    with _ctx_lock:
        hit = _ctx.get(key)
        if hit and time.time() - hit.built < CTX_TTL:
            return hit
        weeks = sample_weeks(lg, n)
        if not weeks:
            return None
        ctx = _ctx[key] = Ctx(lg, weeks, suffix)
        return ctx


# ---------------------------------------------------------------- the search

def _proxy(ctx):
    """{player: FPTS per week the lineup would use, ignoring crowding} averaged over the sample weeks."""
    out = {}
    for r in ctx.rosters.values():
        for p in r['active']:
            out[p] = sum(float(ctx.v[w][p].sum()) for w in range(len(ctx.weeks)) if p in ctx.v[w]) / len(ctx.weeks) * ctx.avail
    return out


def find_trades(lg, give, keep=(), x=2, min_partner=0.0, top=15, sort='me', timeframe=None):
    """The trades worth offering. give: my players that must be in the offer; keep: my players that stay. x: players I send
    out (I get x-1 back). min_partner: the least a partner must gain per week (their lineup value, no claims, after cutting
    the extra player). Returns the payload dict of /api/trades."""
    from player_stats import default_stat_type
    import lineup_optimizer as lo
    t0 = time.time()
    if lg.platform != 'yahoo' or not lg.daily_lineups or not lg.is_points:
        return {'supported': False, 'reason': 'The trade finder is for Yahoo daily-lineup points leagues (its category version comes later).'}
    suffix = lo.timeframe_suffix(timeframe or default_stat_type(lg))
    ctx = context(lg, suffix)
    if ctx is None:
        return {'supported': False, 'reason': 'No full fantasy week left in the schedule.'}
    me = ctx.rosters.get(lg.my_team)
    if not me:
        return {'supported': False, 'reason': 'No team set as yours in the league settings.'}
    mine, my_il = me['active'], me['il']
    give = [g for g in give if g in mine]
    first = ctx.insts[0]
    roster = [{'player': p, 'fpg': round(first.players[p].fpts, 1), 'games': sum(first.players[p].game)}
              for p in mine if p in first.players]
    if not give:   # the page's first call: only who can be offered
        return {'supported': True, 'roster': roster, 'trades': [], 'give': [], 'x': x}
    x = max(x, len(give), 2)
    claims = lg.claims_per_week or 5
    proxy = _proxy(ctx)
    W = len(ctx.weeks)

    # --- my baseline: today's roster with and without claims
    base_stream = [ctx.plan(w, mine, my_il, claims).model_fpts for w in range(W)]
    base_lineup = ctx.lineup_avg(mine)
    base_claims = sum(base_stream) / W - base_lineup   # what the claims are worth to the roster I have

    fillers_pool = [p for p in mine if p not in give and p not in set(keep)]
    cands = []
    # --- stage A: additive proxy over every combination
    for abv, tm in ctx.rosters.items():
        if abv == lg.my_team:
            continue
        their = tm['active']
        targets = [p for p in their if ctx.player(p) and ctx.player(p).has_stats and not ctx.player(p).out]
        t_active_proxy = sorted(proxy.get(p, 0.0) for p in their if ctx.droppable(p))
        # k in, k-1 out: one player over the size if they are full; they cut their cheapest
        cut = t_active_proxy[0] if len(their) + 1 > ctx.N and t_active_proxy else 0.0
        for fill in itertools.combinations(fillers_pool, x - len(give)):
            out = list(give) + list(fill)
            out_p = sum(proxy.get(p, 0.0) for p in out)
            for get in itertools.combinations(targets, x - 1):
                get_p = sum(proxy.get(p, 0.0) for p in get)
                cands.append((out_p - get_p - cut, get_p - out_p, abv, out, list(get)))   # (their proxy gain, my swap proxy, ...)
    cands = [c for c in cands if c[0] >= min_partner - 6.0]
    # the freed spot is worth the same flat amount to every combination, so rank by what the swap does to my lineup
    cands.sort(key=lambda c: -c[1])
    considered = len(cands)
    cands = cands[:STAGE_A_KEEP[x - 2]]

    # --- stage B: exact lineup value, no claims, both sides
    base_theirs = {abv: ctx.lineup_avg(tm['active']) for abv, tm in ctx.rosters.items()}
    scored = []
    for _, _, abv, out, get in cands:
        their = ctx.rosters[abv]['active']
        after_them = [p for p in their if p not in get] + out
        v_them, cut = ctx.with_forced_drop(after_them, len(ctx.rosters[abv]['il']))
        gain_them = v_them - base_theirs[abv]
        if gain_them < min_partner:
            continue
        after_me = [p for p in mine if p not in out] + list(get)
        swap = ctx.lineup_avg(after_me) - base_lineup
        scored.append((swap, gain_them, abv, out, list(get), cut))
    scored.sort(key=lambda s: -s[0])
    scored = scored[:STAGE_C[x - 2]]

    # --- stage C: the ILP on my side
    def one(s):
        swap, gain_them, abv, out, get, cut = s
        after_me = [p for p in mine if p not in out] + get
        plans = [ctx.plan(w, after_me, my_il, claims) for w in range(W)]
        stream = [p.model_fpts for p in plans]
        d_me = sum(stream) / W - sum(base_stream) / W
        slot = d_me - swap
        adds = []
        for p in plans[0].moves:
            if p['type'] == 'add' and p['player'] not in adds:
                adds.append(p['player'])
        return {
            'partner': abv, 'partner_name': ctx.rosters[abv]['name'], 'give': out, 'get': get, 'cut': cut,
            'me': {'week': round(d_me, 1), 'swap': round(swap, 1), 'slot': round(slot, 1),
                   'by_week': [round(a - b, 1) for a, b in zip(stream, base_stream)]},
            'partner_week': round(gain_them, 1), 'streamers': adds,
        }

    with ThreadPoolExecutor(max_workers=4) as pool:
        rows = list(pool.map(one, scored))
    if sort == 'balance':
        rows.sort(key=lambda r: -min(r['me']['week'], r['partner_week']))
    else:
        rows.sort(key=lambda r: -r['me']['week'])
    rows = [r for r in rows if r['me']['week'] > 0][:top]
    left = weeks_left(lg, ctx.weeks[0][0])
    for r in rows:
        r['me']['season'] = round(r['me']['week'] * left)
    return {
        'supported': True, 'weeks': [[a.isoformat(), b.isoformat()] for a, b in ctx.weeks], 'weeks_left': round(left, 1),
        'give': give, 'x': x,
        'base': {'claims': round(base_claims, 1)},
        'roster': roster, 'considered': considered, 'exact': len(scored), 'trades': rows,
        'seconds': round(time.time() - t0, 1),
    }


_results = {}
_results_lock = threading.Lock()
RESULT_TTL = 60


def cached_find_trades(lg, give, keep=(), x=2, min_partner=0.0, top=15, sort='me'):
    """find_trades, cached RESULT_TTL seconds per request; one search at a time (the first caller computes, the rest read it)."""
    key = (lg.id, tuple(sorted(give)), tuple(sorted(keep)), x, round(min_partner, 1), top, sort)
    with _results_lock:
        hit = _results.get(key)
        if hit and time.time() - hit[0] < RESULT_TTL:
            return hit[1]
        out = find_trades(lg, give, keep, x, min_partner, top, sort)
        _results[key] = (time.time(), out)
        return out


def main(league=None, *give):
    from leagues import get_league
    lg = get_league(league)
    out = find_trades(lg, list(give), x=2, min_partner=5.0)
    if not out.get('supported'):
        print(out.get('reason') or out.get('error'))
        return
    b = out.get('base', {})
    print(f"{lg.id}: weeks {out.get('weeks')}, claims worth {b.get('claims')} FPTS/wk to today's roster; {out.get('seconds')} s")
    for t in out['trades']:
        m = t['me']
        print(f"{t['partner']:5} give {' + '.join(t['give'])} -> get {' + '.join(t['get'])}  me {m['week']:+.0f}/wk "
              f"(swap {m['swap']:+.0f}, spot {m['slot']:+.0f})  them {t['partner_week']:+.0f}/wk  cut {', '.join(t['cut']) or '-'}")


if __name__ == '__main__':
    import sys
    main(*sys.argv[1:])
