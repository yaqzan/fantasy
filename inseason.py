"""The in-season update of the projection (spec U): preseason-adjusted prior + this season's games, minutes and
per-minute rates on different clocks.

  MPG    = (Km(n) x prior MPG + sum w(a) x min_a) / (Km(n) + sum w(a)),   w(a) = 1 + 16 x 2^(-a/5),  Km(n) = 64 / (1 + n/80)
  rate_s = (Ks(n) x prior MPG x prior rate + sum v(a) x s_a) / (Ks(n) x prior MPG + sum v(a) x min_a),
           v(a) = 2^(-a/20),  Ks(n) = Ks / (1 + n/80);   per game = MPG x rate_s
a = games ago (0 = his latest), n = games played (minutes > 0). Constants fit on 2016-2025 game logs, walk-forward
scored 2023-25 (.horizon/unified-projection: spec.py, verify_U.py; results in .claude/docs/projections.md "In-season
update"). Stats the fit doesn't cover borrow a neighbour's K (FOLLOW). `minutes_weights` is THE definition of what
the projected minutes carry: role_minutes measures its minutes delta against the same weights."""
import numpy as np

MIN_K, MIN_R, MIN_HALF = 64.0, 16.0, 5.0     # minutes: prior worth Km games, the latest game 1 + R, half-life 5 games
RATE_HALF = 20.0                             # rates: weight halves every 20 games back
TAU = 80.0                                   # K(n) = K / (1 + n / TAU): the prior fades, slowly
RATE_K = {'PTS': 10, 'REB': 16, 'AST': 10, 'STL': 48, 'BLK': 24, 'FG3M': 16, 'TOV': 20, 'FGA': 6, 'FGM': 12,
          'FTA': 16, 'FTM': 16}              # prior minutes x K the prior rate is worth
FOLLOW = {'BLKA': 'FGA', 'PF': 'REB', 'DD2': 'PTS', 'TD3': 'PTS', 'TECH': 'STL'}   # unfitted stats take this stat's K


def rate_k(stat):
    return RATE_K.get(stat) or RATE_K[FOLLOW.get(stat, 'PTS')]


def minutes_weights(n):
    """(prior weight, per-game weights OLDEST first) of the projected minutes after n played games."""
    a = np.arange(n - 1, -1, -1, dtype=float)
    return MIN_K / (1 + n / TAU), 1 + MIN_R * 2.0 ** (-a / MIN_HALF)


def rate_weights(n):
    """Per-game weights OLDEST first of the per-minute rates after n played games."""
    return 2.0 ** (-np.arange(n - 1, -1, -1, dtype=float) / RATE_HALF)


def project(prior, games, totals=None):
    """{stat: per game} after his games this season.

    prior  {stat: per game} from the preseason-adjusted line, 'MIN' included.
    games  {stat: array of per-game values, OLDEST first}, 'MIN' required (played games only, minutes > 0); stats in
           `prior` without an array here use `totals`.
    totals {stat: season total}: stats with no game-by-game record (times blocked, technicals: NBA gives totals),
           spread over his games at his season per-minute rate."""
    mins = np.asarray(games.get('MIN', ()), float)
    n = len(mins)
    m0 = prior.get('MIN') or 0.0
    if not n:
        return dict(prior)
    km, w = minutes_weights(n)
    mpg = (km * m0 + w @ mins) / (km + w.sum())
    v = rate_weights(n)
    vm = v @ mins
    out = {'MIN': mpg}
    for stat, p in prior.items():
        if stat == 'MIN':
            continue
        p = p or 0.0
        if stat in games:
            vx = v @ np.asarray(games[stat], float)
        elif totals is not None and stat in totals:
            vx = (totals[stat] or 0.0) / mins.sum() * vm if mins.sum() else 0.0
        else:
            out[stat] = p
            continue
        k = rate_k(stat) / (1 + n / TAU)
        den = k * m0 + vm
        out[stat] = mpg * (k * p + vx) / den if den > 0 else p
    return out
