"""Canon for Yahoo leagues: what Yahoo itself counted for a matchup week (the Yahoo twin of fantrax_canon.py).

Without it the played part is a guess from today's rosters (week_actuals.carried): a player picked up mid-game
gets the points he scored for someone else, and the bench is ignored. Yahoo knows the truth: for each day, every
team's roster with the slot each player held that day (BN / IL = not counted) and the points Yahoo scored him.

    load(league, week_start, week_end, today, norm_name) -> Canon | None     (None: not Yahoo / unreachable)
    Canon.lines[team id][day][normalised name] = {'name', 'stats': {'FPTS': Yahoo's points}}   (starters only)
    Canon.totals                                                                              (empty: no per-team check)

Same shape as fantrax_canon, so Week.team and week_actuals.canon_carried_impl take either. One call per day returns
all teams. Past days cache for hours, today and yesterday for a minute or two.
"""
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

from fantrax_canon import Canon, DOWN_FOR, LIVE_TTL, PAST_TTL

NOT_COUNTED = ('BN', 'IL', 'IL+', 'NA')   # slots whose points Yahoo doesn't score
_cache = {}      # (yahoo league number, day) -> (fetched at, parsed)
_lock = threading.Lock()
_down = {}       # yahoo league number -> time before which load() returns None


def _parse(root, norm_name):
    """{team id: {norm name: {'name', 'stats': {'FPTS': points}}}} of the players in a counted slot, from one day's
    /league/<key>/teams/roster;date=D/players/stats;type=date;date=D."""
    import pull_yahoo as py
    out = {}
    for team in root.iter(f"{{{py.NS['y']}}}team"):
        players = {}
        for p in team.findall('y:roster/y:players/y:player', py.NS):
            if py._text(p, 'y:selected_position/y:position') in NOT_COUNTED:
                continue
            name = py._text(p, 'y:name/y:full')
            points = py._text(p, 'y:player_points/y:total')
            players[norm_name(name)] = {'name': name, 'stats': {'FPTS': float(points) if points else 0.0}}
        out[py._text(team, 'y:team_id')] = players
    return out


def _fetch(number, day, today, norm_name):
    ttl = LIVE_TTL if day >= today - timedelta(days=1) else PAST_TTL
    with _lock:
        hit = _cache.get((number, day))
    if hit and time.time() - hit[0] < ttl:
        return hit[1]
    import pull_yahoo as py
    iso = day.isoformat()
    parsed = _parse(py.fetch(f'league/nba.l.{number}/teams/roster;date={iso}/players/stats;type=date;date={iso}'), norm_name)
    with _lock:
        _cache[(number, day)] = (time.time(), parsed)
    return parsed


def load(league, week_start, week_end, today, norm_name):
    """The week's canon so far, or None (not a Yahoo league, no league number, or Yahoo unreachable: the caller falls
    back to the best-fit guess and says so)."""
    if league.platform != 'yahoo' or not league.platform_league_id:
        return None
    number = league.platform_league_id
    if time.time() < _down.get(number, 0):
        return None
    days, day = [], week_start
    while day <= min(today, week_end):
        days.append(day)
        day += timedelta(days=1)
    canon = Canon()
    try:
        if days:
            first = _fetch(number, days[0], today, norm_name)    # opens the web session before the pool shares it
            with ThreadPoolExecutor(max_workers=4) as pool:
                got = [first] + list(pool.map(lambda d: _fetch(number, d, today, norm_name), days[1:]))
            for d, teams in zip(days, got):
                for team_id, players in teams.items():
                    canon.lines.setdefault(team_id, {})[d] = players
    except (Exception, SystemExit) as e:   # pull_yahoo.fetch raises SystemExit on a login/page error
        print(f'yahoo canon: {e}')
        _down[number] = time.time() + DOWN_FOR
        return None
    return canon
