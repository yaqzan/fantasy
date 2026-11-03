"""Score nba_rotation.py's logged pregame picks (rotation_picks) against what happened (game_lines).

  python rotation_score.py [--days 14]

P(play) calibration by bin, minutes error (baseline vs minutes-if-plays for players who played, team-normalised
exp for everyone), and the Opp check: players the model gave Opp >= 2 against the rest, mean (actual - baseline).
This is the only honest test of the live feature: the logged inputs are the real pregame ones.
"""
import sys
from datetime import date, timedelta

from fantasy_database import GameLine, RotationPick


def main():
    days = int(sys.argv[sys.argv.index('--days') + 1]) if '--days' in sys.argv else 14
    since = date.today() - timedelta(days=days)
    picks = list(RotationPick.select().where((RotationPick.game_date >= since) & (RotationPick.game_date < date.today())))
    lines = {(r.player_id, r.game_date): r.min or 0 for r in GameLine.select().where(GameLine.game_date >= since)}
    # a pick only counts once that day's lines are in (a day with none in game_lines is not scored yet)
    days_in = {d for _, d in lines}
    picks = [p for p in picks if p.game_date in days_in]
    if not picks:
        print('nothing to score yet')
        return
    print(f'{len(picks)} picks over {len({p.game_date for p in picks})} days')
    bins = [(0, .2), (.2, .5), (.5, .8), (.8, .95), (.95, 1.01)]
    for lo, hi in bins:
        s = [p for p in picks if lo <= p.p_play < hi]
        if s:
            played = sum(1 for p in s if lines.get((p.player_id, p.game_date), 0) > 0)
            print(f'  P(play) {lo:.2f}-{min(hi, 1):.2f}: n={len(s):4d}  predicted {sum(p.p_play for p in s) / len(s):.2f}  played {played / len(s):.2f}')
    played = [p for p in picks if lines.get((p.player_id, p.game_date), 0) > 0 and p.base]
    mae = lambda f, rows: sum(abs(f(p) - lines[(p.player_id, p.game_date)]) for p in rows) / len(rows)
    if played:
        print(f'  played-only minutes MAE: baseline {mae(lambda p: p.base, played):.2f}  minutes-if-plays {mae(lambda p: p.mif, played):.2f}  (n={len(played)})')
    allp = [p for p in picks if p.exp is not None and p.base and p.base >= 5]
    if allp:
        print(f'  all-active exp MAE {mae(lambda p: p.exp, allp):.2f}  vs P(play) x baseline {mae(lambda p: p.p_play * p.base, allp):.2f}  (n={len(allp)})')
    # rate check: FPTS/min (generic weights) on the night vs his previous 10 games, for players with a rate lift >= 1.5%
    gen = lambda r: (r.pts + 1.2 * r.reb + 1.5 * r.ast + 3 * r.stl + 3 * r.blk - r.tov)
    rows = {}
    for r in GameLine.select().where(GameLine.game_date >= since - timedelta(days=60)).order_by(GameLine.game_date):
        if (r.min or 0) > 0:
            rows.setdefault(r.player_id, []).append((r.game_date, gen(r), r.min))
    lift, rest = [], []
    for p in played:
        if p.rate_pct is None:   # logged before rate_pct existed: unlabelled, not 'others'
            continue
        h = [x for x in rows.get(p.player_id, ()) if x[0] < p.game_date][-10:]
        night = next((x for x in rows.get(p.player_id, ()) if x[0] == p.game_date), None)
        if len(h) < 5 or not night or night[2] < 8:
            continue
        base_rate = sum(x[1] for x in h) / sum(x[2] for x in h)
        if base_rate > 0:
            (lift if p.rate_pct >= 1.5 else rest).append((night[1] / night[2] - base_rate) / base_rate * 100)
    if lift and rest:
        print(f'  FPTS/min vs his last 10, % change: rate_pct>=1.5 {sum(lift) / len(lift):+.2f}% (n={len(lift)})   others {sum(rest) / len(rest):+.2f}% (n={len(rest)})')
    hi = [p for p in played if (p.opp or 0) >= 2]
    lo = [p for p in played if (p.opp or 0) < 2]
    resid = lambda rows: sum(lines[(p.player_id, p.game_date)] - p.base for p in rows) / max(len(rows), 1)
    print(f'  mean (actual - baseline): Opp>=2 {resid(hi):+.2f} (n={len(hi)})   others {resid(lo):+.2f} (n={len(lo)})')


if __name__ == '__main__':
    main()
