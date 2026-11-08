"""Two-week claims: every claim judged on the rest of THIS week and on NEXT week's matchup.

Each candidate claim (add, drop) is scored by the change in P(win) of the CURRENT week (from today on, through
`Week.team` with the claim's window) plus `NEXT_WEIGHT` x the change in P(win) of the NEXT week (the roster without
the drop and with the add, against next week's scheduled opponent), greedily up to the claims left. The horizon rolls:
on Monday "next week" is the week after. A week already at 80% has little left to gain, so the claims go where the
leverage is, no separate "mode" to choose; each claim says which week it pays for.

Claims land today (the ones that can't: a player still on waivers is skipped), drops are players whose game has not
tipped. Yahoo daily points leagues, like the week plan (claim_planner.py), which this does not replace: it re-plans the
rest of this week, this adds next week to the question.
"""
import time
import threading

NEXT_WEIGHT = 0.5  # next week counts this much in the ranking (less certain rosters/injuries; claim_planner.KEEP_WEEK_WEIGHTS)
POOL = 200         # free agents (best Z-VALUE) tried for the first claim
NEXT_POOL = 30     # later claims retry the best candidates of the claim before (lineup_optimizer.NEXT_CLAIM_POOL)
MIN_GAIN = 1e-4    # lineup_optimizer's bar for "a claim helps"
TTL = 60

_cache = {}
_lock = threading.Lock()


def _inactive(reason):
    return {'supported': True, 'active': False, 'reason': reason}


def last_days_plan(lg, timeframe=None):
    """{supported, active, ...}: the claims worth making today for this week and next. `active` is False (with the
    reason) when there is no next week, no claim left, or a healthy player in IL blocks adds."""
    import daily_leaders
    import lineup_optimizer as lo
    from claim_planner import unsupported_reason
    from fantasy_team_helper import (claims_left, get_current_fantasy_week_dates, get_next_week_dates,
                                     get_week_info_from_schedule, get_undroppable_players)
    from player_stats import default_stat_type
    week_start, week_end, opponent = get_current_fantasy_week_dates(lg)
    reason = unsupported_reason(lg, week_start, week_end)
    if reason:
        return {'supported': False, 'reason': reason}
    today = daily_leaders.nba_today()
    next_start, next_end = get_next_week_dates(lg, week_start)
    if not next_start:
        return _inactive('No week after this one.')
    next_opponent = get_week_info_from_schedule(lg, next_start.isoformat())[2]
    left = claims_left(lg, week_start)
    if left <= 0:
        return _inactive('No claims left this week.')

    suffix = lo.timeframe_suffix(timeframe or default_stat_type(lg))
    cur, nxt = lo.Week(lg, week_start, week_end), lo.Week(lg, next_start, next_end)
    roster, il = lo._active_roster(lg)
    owned = roster + il
    if any(p not in cur.injured for p in il):   # Yahoo: a healthy player left in IL blocks every add (claim_planner's freeze)
        return _inactive('A healthy player is still in IL, which blocks adds on Yahoo: activate him first.')
    if not any(p in cur.stats for p in roster):
        return {'supported': False, 'reason': 'No players on your team in this league yet.'}
    label_c, theirs_c = cur.opponent(opponent, suffix)
    label_n, theirs_n = nxt.opponent(next_opponent, suffix)
    day = max(cur.start_day, today)

    def evaluate(players, windows, ghosts):
        """(P(win) and ranking key) of this week and of next week for a roster."""
        c = cur.team(list(players) + list(ghosts), suffix, owned, windows)
        n = nxt.team(list(players), suffix)
        return c, n

    base_c, base_n = evaluate(roster, None, ())
    theirs_c = theirs_c or base_c.totals
    theirs_n = theirs_n or base_n.totals
    pc0, kc0, _ = lo._value(base_c.totals, theirs_c, lg)
    pn0, kn0, _ = lo._value(base_n.totals, theirs_n, lg)

    keep = set(get_undroppable_players(lg))
    playing = lambda p: p in cur.stats and cur.stats[p]['TEAM'] in cur.schedule or p in nxt.stats and nxt.stats[p]['TEAM'] in nxt.schedule
    pool = [p for p in lo.get_available_players(lg, cur.stats)
            if not (cur.waivers.get(p) and cur.waivers[p] > today) and playing(p)]
    pool = sorted(pool, key=lambda p: cur.stats[p].get(f'Z-VALUE{suffix}', 0), reverse=True)[:POOL]

    roster_now, ghosts, windows, claims = list(roster), [], {}, []
    pc, pn, kc, kn = pc0, pn0, kc0, kn0
    for _ in range(left):
        drops = [p for p in roster_now if p not in keep and cur.can_drop_on(p, day)] + ([None] if len(roster_now) < lg.roster_size else [])
        best, ranked = None, []
        for add in pool:
            top = None
            for drop in drops:
                c, n = evaluate([p for p in roster_now if p != drop] + [add],
                                lo._claim_windows(windows, add, drop, day), ghosts + ([drop] if drop else []))
                ec, kc1, _ = lo._value(c.totals, theirs_c, lg)
                en, kn1, _ = lo._value(n.totals, theirs_n, lg)
                m = {'add': add, 'drop': drop, 'key': (kc1 - kc) + NEXT_WEIGHT * (kn1 - kn), 'p_cur': ec, 'p_next': en, 'k_cur': kc1, 'k_next': kn1}
                if top is None or m['key'] > top['key']:
                    top = m
            if top:
                ranked.append(top)
        ranked.sort(key=lambda m: m['key'], reverse=True)
        if not ranked or ranked[0]['key'] <= MIN_GAIN:
            break
        best = ranked[0]
        claims.append({'add': best['add'], 'drop': best['drop'],
                       'gain_cur': round(best['p_cur'] - pc, 4), 'gain_next': round(best['p_next'] - pn, 4)})
        pc, pn, kc, kn = best['p_cur'], best['p_next'], best['k_cur'], best['k_next']
        windows = lo._claim_windows(windows, best['add'], best['drop'], day)
        ghosts += [best['drop']] if best['drop'] else []
        roster_now = [p for p in roster_now if p != best['drop']] + [best['add']]
        keep.add(best['add'])
        pool = [m['add'] for m in ranked[1:NEXT_POOL + 1]]
    for c in claims:
        c['for'] = ('both' if min(c['gain_cur'], c['gain_next']) > 0.25 * max(c['gain_cur'], c['gain_next'], 1e-9)
                    else 'this week' if c['gain_cur'] > c['gain_next'] else 'next week')
    return {
        'supported': True, 'active': True, 'today': day.isoformat(), 'claims_left': left,
        'this_week': {'start': week_start.isoformat(), 'end': week_end.isoformat(), 'opponent': label_c,
                      'now': round(pc0, 4), 'after': round(pc, 4)},
        'next_week': {'start': next_start.isoformat(), 'end': next_end.isoformat(), 'opponent': label_n,
                      'now': round(pn0, 4), 'after': round(pn, 4)},
        'claims': claims,
        'notes': ['Claims are made today: players still on waivers are left out, and so is anyone whose game is under way.',
                  'An add uses one of this week\'s claims (drops are free); the allowance resets Monday.',
                  f'Next week counts {NEXT_WEIGHT:g} x this week in the ranking; its own claims start from this roster.'],
    }


def cached_last_days_plan(lg, timeframe=None):
    key = (lg.id, timeframe)
    with _lock:
        hit = _cache.get(key)
        if hit and time.time() - hit[0] < TTL:
            return hit[1]
    result = last_days_plan(lg, timeframe)
    with _lock:
        _cache[key] = (time.time(), result)
    return result
