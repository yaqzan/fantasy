"""Score ESPN's stated return dates (injury_reports) against when players actually came back (game_lines).

    python injury_score.py

For each player's FIRST snapshot of an injury note (status Out, a return date), the actual return is his first game
with minutes after that snapshot. Slip = actual - stated (days; > 0 = late). Players not back yet count as censored
(slip at least today - stated). Printed by quality (injury_reports.quality: long = a real estimate, short = a
placeholder) and stated-duration band. Once a few dozen long ones are scored, replace role_minutes.SLIP (an
assumption until then) with the measured distribution (rotation.md "Return dates").
"""
from collections import defaultdict
from statistics import mean, median


def rows():
    from fantasy_database import GameLine, InjuryReport
    from daily_leaders import nba_today
    from injury_reports import quality
    today = nba_today()
    first = {}
    for r in InjuryReport.select().where(InjuryReport.player_id.is_null(False), InjuryReport.status == 'Out',
                                          InjuryReport.return_date.is_null(False)).order_by(InjuryReport.snapshot_date).dicts():
        key = (r['player_id'], r['reported'] or r['snapshot_date'])
        first.setdefault(key, r)
    played = defaultdict(list)
    for g in GameLine.select(GameLine.player_id, GameLine.game_date).where(GameLine.min > 0):
        played[g.player_id].append(g.game_date)
    out = []
    for (pid, _), r in first.items():
        back = min((d for d in played.get(pid, ()) if d > r['snapshot_date']), default=None)
        stated = r['return_date']
        rep = r['reported'].date() if r['reported'] else r['snapshot_date']
        if back is None and today <= stated:
            continue          # not due yet
        out.append({'name': r['name'], 'quality': quality(r), 'stated_days': (stated - rep).days,
                    'slip': ((back or today) - stated).days, 'censored': back is None})
    return out


def main():
    rs = rows()
    if not rs:
        print('nothing to score yet (no stated return date has passed)')
        return
    groups = defaultdict(list)
    for r in rs:
        band = '<7 d' if r['stated_days'] < 7 else '7-20 d' if r['stated_days'] <= 20 else '21+ d'
        groups[(r['quality'], band)].append(r)
    print(f'{"quality":8s} {"stated":7s} {"n":>4s} {"back":>5s} {"median":>7s} {"mean":>6s} {"early":>6s} {"+-2d":>6s}')
    for (q, band), g in sorted(groups.items(), key=lambda x: (str(x[0][0]), x[0][1])):
        back = [r for r in g if not r['censored']]
        s = [r['slip'] for r in back]
        print(f'{str(q):8s} {band:7s} {len(g):4d} {len(back):5d} {median(s) if s else float("nan"):7.1f} '
              f'{mean(s) if s else float("nan"):6.1f} {sum(x < 0 for x in s) / len(s) if s else 0:6.0%} '
              f'{sum(abs(x) <= 2 for x in s) / len(s) if s else 0:6.0%}  (+{len(g) - len(back)} not back yet)')


if __name__ == '__main__':
    main()
