"""Canon: what the league's own platform counted for a matchup week, whatever the platform.

The Lineup Optimizer's played part used to be a guess (today's rosters, best-fitting players each day). A platform
knows the truth: per day, the players each team had in counted slots and their lines. A provider module turns its
platform's answer into this one shape, and nothing outside this file names a platform:

    load(league, week_start, week_end, today, norm_name) -> Canon | None   (None: no provider / unreachable: the caller guesses)
    Canon.lines[team id][day][normalised name] = {'name', 'stats': {category: value}}   counted player-days only
    Canon.totals[team id] = {category: the platform's own period total}                 {} when it gives none
    Canon.source = the provider's name ('fantrax', 'yahoo')

A provider (fantrax_canon, yahoo_canon) exposes `PLATFORM` and `fetch_day(league, day, today, norm_name) -> {team id:
{norm name: player entry}}` (called on several threads, one per day; use `cached`), and optionally `period_totals(league, last, norm_name)`.
A player entry is present only for a player-day the platform counted AND the player played.
`stats` uses our stat names; 'FPTS' = the platform's own points for the player-day (points leagues).
Shared here: the TTL cache, the back-off after a failure, and the concurrent day loop.
"""
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

LIVE_TTL, PAST_TTL = 90, 6 * 3600     # today and yesterday refresh fast; older days are final
DOWN_FOR = 300                        # after a failed call, don't ask the platform again for this long
WORKERS = 4

_cache = {}     # key -> (fetched at, value)
_lock = threading.Lock()
_down = {}      # (platform, league id) -> time before which load() returns None
_PROVIDERS = {}


class Canon:
    def __init__(self, source=None):
        self.source = source
        self.lines = {}     # {team id: {day: {norm name: {'name', 'stats'}}}}
        self.totals = {}    # {team id: {category: the platform's period total}}


def register(module):
    _PROVIDERS[module.PLATFORM] = module
    return module


def provider(league):
    import fantrax_canon, yahoo_canon   # noqa: F401  (each registers itself; a no-op once loaded, and other code imports fantrax_canon alone)
    return _PROVIDERS.get(league.platform)


def ttl(day, today):
    return LIVE_TTL if day >= today - timedelta(days=1) else PAST_TTL


def cached(key, max_age, fetch):
    """fetch() unless a value under `key` is younger than max_age seconds. Concurrent callers may both fetch; harmless."""
    with _lock:
        hit = _cache.get(key)
    if hit and time.time() - hit[0] < max_age:
        return hit[1]
    value = fetch()
    with _lock:
        _cache[key] = (time.time(), value)
    return value


def backed_off(platform, league_id):
    return time.time() < _down.get((platform, league_id), 0)


def back_off(platform, league_id):
    _down[(platform, league_id)] = time.time() + DOWN_FOR


def load(league, week_start, week_end, today, norm_name):
    """The week's canon so far, or None (no provider for the platform, no league id, or unreachable)."""
    mod = provider(league)
    if mod is None or not league.platform_league_id:
        return None
    lid = league.platform_league_id
    if backed_off(mod.PLATFORM, lid):
        return None
    days, day = [], week_start
    while day <= min(today, week_end):
        days.append(day)
        day += timedelta(days=1)
    canon = Canon(mod.PLATFORM)
    pool = ThreadPoolExecutor(max_workers=WORKERS)
    try:
        got = list(pool.map(lambda d: mod.fetch_day(league, d, today, norm_name), days))
        for d, teams in zip(days, got):
            for team_id, players in teams.items():
                canon.lines.setdefault(team_id, {})[d] = players
        if days and hasattr(mod, 'period_totals'):
            canon.totals = mod.period_totals(league, min(today, week_end), norm_name)
    except (Exception, SystemExit) as e:   # the pull_* modules raise SystemExit on a login/page error
        print(f'{mod.PLATFORM} canon: {e}')
        back_off(mod.PLATFORM, lid)
        return None
    finally:
        pool.shutdown(wait=False, cancel_futures=True)    # on a failure don't wait out the other days' timeouts
    return canon


def state(league, canon, my_team_id, opponent_team):
    """progress.canon: None = no provider or no game yet; True = both teams' played part is the platform's own;
    False = unreachable or a team the platform has no id for (that side is the best-fit guess)."""
    if provider(league) is None:
        return None
    if canon is None or my_team_id not in canon.lines:
        return False
    return not (opponent_team is not None and opponent_team.platform_team_id not in canon.lines)
