"""Canon: what Fantrax itself counted for a matchup week.

The Lineup Optimizer's played part used to be guessed (today's rosters, best-fitting players each day). Fantrax
knows the truth: for each day, the players each team had in ACTIVE slots and their lines, so adds, drops, moves
to the bench and the opponent's real lineup are all in. `getLiveScoringStats` with `viewType='1'` + `date` is that
day; `viewType='2'` is the period totals (the number the matchup page shows, used to check ours against).

    load(league, week_start, week_end, today, norm_name) -> Canon | None     (None: not Fantrax / unreachable)
    Canon.lines[team id][day][normalised name] = {'name', 'stats': {category: value}}
    Canon.totals[team id] = {category: Fantrax's own period total}

Only the nine categories Fantrax shows per player map here (SHORT); a league with others keeps ESPN's value for
those (week_actuals.canon_carried). Past days cache for hours, today and yesterday for a minute or two.
"""
import threading
import time
from datetime import timedelta

SHORT = {'FG%': 'FG%', '3PTM': 'FG3M', 'FT%': 'FT%', 'PTS': 'PTS', 'REB': 'REB', 'AST': 'AST', 'ST': 'STL', 'BLK': 'BLK',
         'TO': 'TOV'}
LIVE_TTL, PAST_TTL = 90, 6 * 3600
_cache = {}      # (fantrax league id, day or 'period', date) -> (fetched at, parsed)
_lock = threading.Lock()
DOWN_FOR = 300   # after a failed call, don't ask Fantrax again for this long (each Week() would otherwise wait on it)
_down = {}       # fantrax league id -> time before which load() returns None


class Canon:
    def __init__(self):
        self.lines = {}     # {team id: {day: {norm name: {'name', 'stats'}}}}
        self.totals = {}    # {team id: {category: Fantrax's period total}}


def _call(league_id, **data):
    import pull_fantrax as pf
    return pf.call(pf.session(), league_id, 'getLiveScoringStats', sppId='-1', newView=True, **data)


def _stat_ids(reply):
    ids = {}
    for group in reply['scoringCategoriesPerGroup'].values():
        for c in group:
            if c['shortName'] in SHORT:
                ids[c['id']] = SHORT[c['shortName']]
    return ids


def _parse(reply, norm_name):
    """{team id: {'players': {norm name: {'name', 'stats'}}, 'total': {category: value}}} for one response."""
    ids = _stat_ids(reply)
    names = {}
    for status in reply['scorerMap'].values():
        for team in status.values():
            for entries in team.values():
                for e in entries:
                    names[e['scorer']['scorerId']] = e['scorer']['name']
    out = {}
    for team_id, groups in reply['statsPerTeam']['allTeamsStats'].items():
        active = groups.get('ACTIVE') or {}
        players, total = {}, {}
        for pid, v in (active.get('statsMap') or {}).items():
            stats = {ids[o['scipId']]: o['av'] for o in v['object2'] if o['scipId'] in ids}
            if pid.startswith('_'):
                total = stats
            elif pid in names:
                players[norm_name(names[pid])] = {'name': names[pid], 'stats': stats}
        out[team_id] = {'players': players, 'total': total}
    return out


def _fetch(league_id, key, ttl, norm_name, **data):
    with _lock:
        hit = _cache.get((league_id, *key))
    if hit and time.time() - hit[0] < ttl:
        return hit[1]
    parsed = _parse(_call(league_id, **data), norm_name)
    with _lock:
        _cache[(league_id, *key)] = (time.time(), parsed)
    return parsed


def load(league, week_start, week_end, today, norm_name):
    """The week's canon so far, or None (not a Fantrax league, no league id, or Fantrax unreachable: the caller falls
    back to the best-fit guess and says so)."""
    if league.platform != 'fantrax' or not league.platform_league_id:
        return None
    lid = league.platform_league_id
    if time.time() < _down.get(lid, 0):
        return None
    canon = Canon()
    try:
        day = week_start
        while day <= min(today, week_end):
            for team_id, got in _fetch(lid, ('day', day), LIVE_TTL if day >= today - timedelta(days=1) else PAST_TTL, norm_name, date=day.isoformat(), viewType='1').items():
                canon.lines.setdefault(team_id, {})[day] = got['players']
            day += timedelta(days=1)
        last = min(today, week_end)
        for team_id, got in _fetch(lid, ('period', last), LIVE_TTL, norm_name, date=last.isoformat(), viewType='2').items():
            canon.totals[team_id] = got['total']
    except (Exception, SystemExit) as e:   # pull_fantrax.call raises SystemExit on a login/page error
        print(f'fantrax canon: {e}')
        _down[lid] = time.time() + DOWN_FOR
        return None
    return canon


_claims = {}   # (fantrax league id, team id) -> (fetched at, claims left)


def claims_remaining(league, team_id):
    """Claims `team_id` has left in Fantrax's CURRENT period ("Claims Remaining (Week)" on the roster page), or None
    (not Fantrax, no id, unreachable). Fantrax only answers for the current period; cached LIVE_TTL, backs off like load()."""
    if league.platform != 'fantrax' or not league.platform_league_id or not team_id:
        return None
    lid, key = league.platform_league_id, (league.platform_league_id, team_id)
    hit = _claims.get(key)
    if hit and time.time() - hit[0] < LIVE_TTL:
        return hit[1]
    if time.time() < _down.get(lid, 0):
        return None
    try:
        import pull_fantrax as pf
        info = pf.call(pf.session(), lid, 'getTeamRosterInfo', teamId=team_id)['miscData']['transactionInfo']['info']
        left = next(int(i['value']) for i in info if i['name'] == 'Claims Remaining (Week)')
    except (Exception, SystemExit) as e:
        print(f'fantrax claims: {e}')
        _down[lid] = time.time() + DOWN_FOR
        return None
    _claims[key] = (time.time(), left)
    return left
