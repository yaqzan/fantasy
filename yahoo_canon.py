"""Canon for Yahoo leagues: what Yahoo itself counted for a matchup week (the Yahoo provider for canon.py).

Without it the played part is a guess from today's rosters (week_actuals.carried): a player picked up mid-game
gets the points he scored for someone else, and the bench is ignored. Yahoo knows the truth: for each day, every
team's roster with the slot each player held that day (BN / IL = not counted) and the points Yahoo scored him.
One call per day returns all teams. No period totals call: Yahoo's scoreboard `team_points` is the figure to check by hand.
"""
import sys

import canon

PLATFORM = 'yahoo'
NOT_COUNTED = ('BN', 'IL', 'IL+', 'NA')   # slots whose points Yahoo doesn't score


def _parse(root, norm_name):
    """{team id: {norm name: {'name', 'stats': {'FPTS': points}}}} of the players in a counted slot who played, from one day's
    /league/<key>/teams/roster;date=D/players/stats;type=date;date=D."""
    import pull_yahoo as py
    out = {}
    for team in root.iter(f"{{{py.NS['y']}}}team"):
        players = {}
        for p in team.findall('y:roster/y:players/y:player', py.NS):
            if py._text(p, 'y:selected_position/y:position') in NOT_COUNTED:
                continue
            if all(py._text(s, 'y:value') in ('', '-') for s in p.findall('y:player_stats/y:stats/y:stat', py.NS)):
                continue    # a starter whose team had no game (or who has not played yet): all stats '-'; canon lists player-days played
            name = py._text(p, 'y:name/y:full')
            points = py._text(p, 'y:player_points/y:total')
            players[norm_name(name)] = {'name': name, 'stats': {'FPTS': float(points) if points else 0.0}}
        out[py._text(team, 'y:team_id')] = players
    return out


def fetch_day(league, day, today, norm_name):
    import pull_yahoo as py
    iso = day.isoformat()
    number = league.platform_league_id
    return canon.cached((PLATFORM, number, day), canon.ttl(day, today), lambda: _parse(
        py.fetch(f'league/nba.l.{number}/teams/roster;date={iso}/players/stats;type=date;date={iso}'), norm_name))


canon.register(sys.modules[__name__])
