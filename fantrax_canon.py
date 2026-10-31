"""Canon: what Fantrax itself counted for a matchup week.

The Lineup Optimizer's played part used to be guessed (today's rosters, best-fitting players each day). Fantrax
knows the truth: for each day, the players each team had in ACTIVE slots and their lines, so adds, drops, moves
to the bench and the opponent's real lineup are all in. `getLiveScoringStats` with `viewType='1'` + `date` is that
day; `viewType='2'` is the period totals (the number the matchup page shows, used to check ours against).

    fetch_day / period_totals: the Fantrax provider for canon.py (the shape, caching and back-off live there).

Only the nine categories Fantrax shows per player map here (SHORT); a league with others keeps ESPN's value for
those (week_actuals.canon_carried). Past days cache for hours, today and yesterday for a minute or two.
"""
import sys
import time

import canon

PLATFORM = 'fantrax'
SHORT = {'FG%': 'FG%', '3PTM': 'FG3M', 'FT%': 'FT%', 'PTS': 'PTS', 'REB': 'REB', 'AST': 'AST', 'ST': 'STL', 'BLK': 'BLK',
         'TO': 'TOV'}


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


def _fetch(league_id, key, max_age, norm_name, **data):
    return canon.cached((PLATFORM, league_id, *key), max_age, lambda: _parse(_call(league_id, **data), norm_name))


def fetch_day(league, day, today, norm_name):
    """{team id: {norm name: {'name', 'stats'}}} of the active-slot players Fantrax counted on `day`."""
    got = _fetch(league.platform_league_id, ('day', day), canon.ttl(day, today), norm_name, date=day.isoformat(), viewType='1')
    return {team_id: g['players'] for team_id, g in got.items()}


def period_totals(league, last, norm_name):
    """{team id: {category: Fantrax's period total}} up to `last`: the number the matchup page shows."""
    got = _fetch(league.platform_league_id, ('period', last), canon.LIVE_TTL, norm_name, date=last.isoformat(), viewType='2')
    return {team_id: g['total'] for team_id, g in got.items()}


canon.register(sys.modules[__name__])


_claims = {}   # (fantrax league id, team id) -> (fetched at, claims left)


def claims_remaining(league, team_id):
    """Claims `team_id` has left in Fantrax's CURRENT period ("Claims Remaining (Week)" on the roster page), or None
    (not Fantrax, no id, unreachable). Fantrax only answers for the current period; cached LIVE_TTL, backs off like load()."""
    if league.platform != 'fantrax' or not league.platform_league_id or not team_id:
        return None
    lid, key = league.platform_league_id, (league.platform_league_id, team_id)
    hit = _claims.get(key)
    if hit and time.time() - hit[0] < canon.LIVE_TTL:
        return hit[1]
    if canon.backed_off(PLATFORM, lid):
        return None
    try:
        import pull_fantrax as pf
        info = pf.call(pf.session(), lid, 'getTeamRosterInfo', teamId=team_id)['miscData']['transactionInfo']['info']
        left = next(int(i['value']) for i in info if i['name'] == 'Claims Remaining (Week)')
    except (Exception, SystemExit) as e:
        print(f'fantrax claims: {e}')
        canon.back_off(PLATFORM, lid)
        return None
    _claims[key] = (time.time(), left)
    return left
