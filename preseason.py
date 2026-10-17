"""The '_pre' timeframe: this season's projection updated by the player's preseason games.

Constants from the 2026-10-17 backtest (.claude/docs/projections.md "Preseason signal": 13 seasons,
fit before each target, holdout 2021-25). Per stat: take the preseason's hot level off (offset), then
move the projected per-minute rate m / (m + k) of the way to it, m = preseason minutes (attempts for
FG%/FT%), k by NBA year (years 1-3 trust preseason far more). Minutes: the surprise against the
expected preseason MPG (13.3 + 0.31 x projected) at g / (g + 5) games' weight, except for players
projected STARTER_MPG+: a rested star is not a lost role (eval_cutoff.py, 2026-10-17: 32 scored best
in the top 60 against ESPN and kept the gain from rank 60 down)."""
from functools import lru_cache

from fantasy_database import PreseasonLine

# stat -> (years 1-3, year 4+), each (preseason offset, k). FG%/FT% offsets are absolute.
SHRINK = {
    'pts': ((0.0812, 200), (0.0464, 350)), 'reb': ((0.0449, 120), (0.0462, 450)),
    'ast': ((0.0537, 120), (0.0936, 300)), 'stl': ((0.1975, 500), (0.2072, 1400)),
    'blk': ((0.0174, 190), (0.0497, 800)), 'fg3m': ((0.0557, 180), (0.1428, 350)),
    'tov': ((0.321, 300), (0.2819, 650)), 'fga': ((0.0565, 130), (0.0277, 250)),
    'fta': ((0.3031, 300), (0.2388, 550)),
}
RATIOS = {'fgm': ('fga', ((-0.0064, 170), (-0.0087, 550))), 'ftm': ('fta', ((-0.0085, 70), (-0.0064, 160)))}
MPG_A, MPG_B, MPG_K = 13.3, 0.31, 5
STARTER_MPG = 32
YOUNG_EXP = 2      # NBA seasons before this one: 0-2 = years 1-3
MAX_MPG = 40.0
FIELDS = ['min', 'pts', 'reb', 'ast', 'stl', 'blk', 'fg3m', 'tov', 'fga', 'fgm', 'fta', 'ftm']
PER_GAME = FIELDS[1:] + ['blka', 'pf', 'tech', 'dd2', 'td3']   # the line's per-game stats


@lru_cache(maxsize=4)
def _totals(season, stamp):
    out = {}
    for r in PreseasonLine.select().where((PreseasonLine.season == season) & (PreseasonLine.min > 0)):
        t = out.setdefault(r.player_id, {f: 0 for f in FIELDS} | {'g': 0})
        t['g'] += 1
        for f in FIELDS:
            t[f] += getattr(r, f) or 0
    return out


def preseason_totals(season):
    """{NBA player id: summed preseason line + 'g'} for `season` (cached until the table changes)."""
    from peewee import fn
    stamp = PreseasonLine.select(fn.COUNT(PreseasonLine.player_id), fn.MAX(PreseasonLine.game_date)) \
        .where(PreseasonLine.season == season).tuples()[0]
    return _totals(season, stamp)


def adjust(line, pre):
    """A projection line (per game, projections.player_lines shape) moved by preseason totals `pre`.
    Returns a new line; stats the backtest didn't cover (blka, pf, tech, dd2, td3) keep their
    per-minute rate at the new minutes."""
    mpg0 = line.get('min') or 0.0
    if not pre or pre['min'] <= 0 or mpg0 <= 0:
        return dict(line)
    young = (line.get('exp') or 0) <= YOUNG_EXP
    m = pre['min']
    rate = {s: (line.get(s) or 0.0) / mpg0 for s in PER_GAME}
    new = dict(rate)
    for s, groups in SHRINK.items():
        off, k = groups[0 if young else 1]
        new[s] = rate.get(s, 0.0) + m / (m + k) * (pre[s] / m / (1 + off) - rate.get(s, 0.0))
    for made, (att, groups) in RATIOS.items():
        off, k = groups[0 if young else 1]
        r0 = rate[made] / rate[att] if rate.get(att) else 0.0
        r = r0 + pre[att] / (pre[att] + k) * ((pre[made] / pre[att] - off) - r0) if pre[att] else r0
        new[made] = r * new[att]
    mpg = mpg0
    if mpg0 < STARTER_MPG and pre['g']:
        surprise = pre['min'] / pre['g'] - (MPG_A + MPG_B * mpg0)
        mpg = min(max(mpg0 + pre['g'] / (pre['g'] + MPG_K) * surprise, 0.0), MAX_MPG)
    out = dict(line)
    out.update({s: v * mpg for s, v in new.items()})
    out['min'] = mpg
    return out
