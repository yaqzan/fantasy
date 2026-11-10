"""Who to start on a crowded day (the "Start" tab): daily category leagues with fewer active slots than
healthy players with a game.

The matchup model decides. For a day, every legal lineup of the players who can still start is run through
`Week.team` (the sat players get a window that begins the next day, so every other day plays as usual) and
scored by expected categories won against this week's opponent, plus the week-win chance. From the grid:
a MUST is a player whose absence costs `MUST_COST` or more of the best lineup's value; the rest compete for
the open spots, each with what the best lineup containing him loses. Exact search only (`MAX_LINEUPS`):
Fantrax's 6 of 10 is 210 lineups.

    python start_day.py [league] [YYYY-MM-DD]
"""
import itertools
import time
from datetime import date, timedelta

import lineup_optimizer as lo
from leagues import category_meta
from player_stats import category_win_chances

MUST_COST = 0.03      # benching him loses this many expected categories (3% of a category)
TOSSUP_LOSS = 0.04    # an option within this of the best lineup is a toss-up for the open spot
MAX_LINEUPS = 600     # more lineups than this: not searched (the page shows the count only)
CACHE_SECONDS = 60
_cache = {}


def supported(league):
    """Daily lineups, category scoring, no positional slots: any k of the players fill the k slots."""
    return bool(league.daily_lineups and league.settings['scoring']['type'] == 'categories'
                and all(slot == 'UTIL' for slot in league.slots))


def _week_win(chances):
    """P(win more than half the categories); an exact half counts half."""
    dist = [1.0]
    for p in chances:
        nxt = [0.0] * (len(dist) + 1)
        for i, x in enumerate(dist):
            nxt[i] += x * (1 - p)
            nxt[i + 1] += x * p
        dist = nxt
    n = len(chances)
    return sum(dist[n // 2 + 1:]) + (dist[n // 2] / 2 if n % 2 == 0 else 0)


def _candidates(week, roster, day):
    """(who can still start on `day`, who is locked in by a game that has tipped or finished), healthy, with a game that day.
    A finished game has left `week.remaining`, so the full schedule decides who had a game."""
    st = week.stats
    tipped = week.actual.tipped if week.actual else ()
    plays = [p for p in roster if p in st and p not in week.injured and day in week.schedule.get(st[p]['TEAM'], {})]
    free = [p for p in plays if day in week.remaining.get(st[p]['TEAM'], {}) and (st[p]['TEAM'], day) not in tipped]
    return free, [p for p in plays if p not in free]


def status(league, day=None):
    """`_status` through the 60-s cache: every page load asks for it, the tab's badge reads it."""
    key = ('status', league.id, day)
    hit = _cache.get(key)
    if hit and time.time() - hit[0] < CACHE_SECONDS:
        return hit[1]
    result = _status(league, day)
    _cache[key] = (time.time(), result)
    return result


def _status(league, day=None):
    """{supported, slots, conflict, conflict_days} without searching lineups (the tab's badge; builds a Week, ~2 s cold).
    conflict: today has more players who can start than slots. conflict_days: this week's days from `day` on that do."""
    if not supported(league):
        return {'supported': False}
    week_start, week_end, _ = lo._resolve_week(league, None, None, None)
    week = lo.Week(league, week_start, week_end)
    roster, _ = lo._active_roster(league)
    day = day or week.start_day
    slots = len(league.slots)
    out = {'supported': True, 'slots': slots, 'conflict_days': []}
    d = day
    while d <= week_end:
        free, locked = _candidates(week, roster, d)
        if 0 < slots - len(locked) < len(free):   # no open spot (tipped games fill the slots): nothing to choose
            out['conflict_days'].append(d.isoformat())
        if d == day:
            out['conflict'] = d.isoformat() in out['conflict_days']
        d += timedelta(days=1)
    return out


def lineups(league, day=None):
    """The Start tab's payload for one day (see module doc). `day` default: today."""
    key = (league.id, day)
    hit = _cache.get(key)
    if hit and time.time() - hit[0] < CACHE_SECONDS:
        return hit[1]
    result = _lineups(league, day)
    _cache[key] = (time.time(), result)
    return result


def _lineups(league, day):
    if not supported(league):
        return {'supported': False, 'reason': 'Start days are for daily-lineup category leagues without positional slots.'}
    suffix = lo.timeframe_suffix(lo.default_stat_type(league))
    week_start, week_end, opponent = lo._resolve_week(league, None, None, None)
    week = lo.Week(league, week_start, week_end)
    roster, il = lo._active_roster(league)
    day = day or week.start_day
    if not week.start_day <= day <= week_end:
        return {'supported': True, 'error': f'{day.isoformat()} is not a day left this week'}
    free, locked = _candidates(week, roster, day)
    slots = len(league.slots)
    open_slots = slots - len(locked)
    base = {'supported': True, 'day': day.isoformat(), 'slots': slots, 'locked': locked, 'candidates': len(free)}
    if open_slots <= 0:   # tipped games already fill every slot
        return {**base, 'conflict': False, 'start': [], 'bench': free}
    if len(free) <= open_slots:
        return {**base, 'conflict': False, 'start': free, 'bench': []}
    combos = len(list(itertools.islice(itertools.combinations(range(len(free)), open_slots), MAX_LINEUPS + 1)))
    if combos > MAX_LINEUPS:
        return {**base, 'conflict': True, 'too_many': True}
    label, theirs = week.opponent(opponent, suffix)
    if theirs is None:
        return {**base, 'conflict': True, 'error': 'No opponent to judge lineups against yet.'}
    owned = roster + il
    grid = []   # (expected categories, week-win chance, lineup, {category: chance})
    doubtful = week.doubtful
    next_game = {p: min(week.remaining.get(week.stats[p]['TEAM'], {}), default=None) for p in doubtful if p in week.stats}
    for chosen in itertools.combinations(free, open_slots):
        sat = [p for p in free if p not in chosen]
        sit = {(p, day) for p in sat}
        # a doubtful player's doubt belongs to his next game; sat on it, it must not move to a later game
        week.doubtful = {p: v for p, v in doubtful.items() if p not in sat or next_game.get(p) != day}
        chances = category_win_chances(week.team(roster, suffix, owned, sit=sit).totals, theirs, league)
        grid.append((sum(chances.values()), _week_win(list(chances.values())), frozenset(chosen), chances))
    best = max(grid, key=lambda g: g[0])
    worst = min(grid, key=lambda g: g[0])

    def best_with(p):
        return max((g for g in grid if p in g[2]), key=lambda g: g[0])

    def best_without(p):
        return max((g for g in grid if p not in g[2]), key=lambda g: g[0])

    names = week.stats
    meta = {c['key']: c['label'] for c in category_meta(league.categories)}
    players = []
    for p in free:
        without = best_without(p)
        with_ = best_with(p)
        cost = best[0] - without[0] if p in best[2] else 0.0   # what benching him costs the best lineup
        helps = sorted(((c, with_[3][c] - without[3][c]) for c in best[3]), key=lambda x: -x[1])
        players.append({
            'name': p, 'team': names[p]['TEAM'], 'play_chance': week.doubtful.get(p), 'in_best': p in best[2],
            'bench_cost': round(cost, 3), 'loss': round(best[0] - with_[0], 3),
            'win': round(with_[1], 3), 'win_delta': round(with_[1] - best[1], 3),
            'helps': [{'category': c, 'delta': round(d, 3)} for c, d in helps[:2] if d > 0.01],
        })
    must = [p for p in players if p['in_best'] and p['bench_cost'] >= MUST_COST]
    for p in players:
        p['role'] = 'must' if p in must else ('toss-up' if p['loss'] <= TOSSUP_LOSS else 'bench')
    players.sort(key=lambda p: (p['role'] != 'must', p['loss'], -p['bench_cost']))
    return {**base, 'conflict': True, 'opponent': label, 'open_slots': open_slots, 'open_for_options': open_slots - len(must),
            'lineups': len(grid), 'best': {'players': sorted(best[2]), 'expected': round(best[0], 2), 'win': round(best[1], 3)},
            'worst': {'players': sorted(worst[2]), 'expected': round(worst[0], 2), 'win': round(worst[1], 3)},
            'categories': {c: round(v, 3) for c, v in best[3].items()}, 'players': players, 'category_labels': meta}


def main(league: str = None, day: str = None):
    """Print the crowded-day lineup for a league (default: the active one) and a day (default: today).

    :param league: league id
    :param day: YYYY-MM-DD
    """
    from leagues import get_league
    config = get_league(league)
    started = time.time()
    data = lineups(config, date.fromisoformat(day) if day else None)
    if not data.get('supported'):
        print(data.get('reason'))
        return
    print(f"{config.name} {data.get('day')}: {data.get('candidates')} can start, {data.get('slots')} slots ({time.time() - started:.1f}s)")
    if not data.get('conflict'):
        print('no conflict: start', data['start'])
        return
    for k in ('error', 'too_many'):
        if data.get(k):
            print(k, data[k])
            return
    print(f"best {data['best']['expected']} cats, win {data['best']['win']:.0%}; worst {data['worst']['expected']}, {data['worst']['win']:.0%}")
    for p in data['players']:
        print(f"  {p['role']:8s} {p['name']:22s} bench -{p['bench_cost']:.3f}  loss {p['loss']:.3f}  win {p['win_delta']:+.1%}  {p['helps']}")


if __name__ == '__main__':
    import defopt
    defopt.run(main)
