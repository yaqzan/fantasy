"""Our own season projection: last seasons, pulled toward league average, aged one year.

Backtested out of sample on 2023-24, 2024-25 and 2025-26 against ESPN's preseason projections
and "same as last season" (see .claude/docs/projections.md for results). Per player, for the
target season:
- per-minute rates from the last 3 seasons weighted 5/4/3 by minutes, blended with 800 minutes
  of league-average play; players entering their 2nd or 3rd season use last season only
  (blended with 200 minutes): their rookie year says less about them;
- a one-year change factor per stat, minutes and games, by age (by NBA experience for players
  entering year 2-3), measured from consecutive seasons before the target (delta method);
- rookies: the average first season of past picks in the same draft range.
Everything is fit on seasons before the target, so backtests stay out of sample.
"""
import numpy as np
import pandas as pd

COUNT_STATS = ['PTS', 'REB', 'AST', 'STL', 'BLK', 'FG3M', 'TOV', 'FGM', 'FGA', 'FTM', 'FTA', 'BLKA', 'PF', 'DD2', 'TD3']
WEIGHTS = (5, 4, 3)
YOUNG_WEIGHTS = (1, 0, 0)
PRIOR_MIN = 800
YOUNG_PRIOR_MIN = 200
GP_PRIOR = 0.8          # share of 82 games a player is assumed to play before his record says otherwise
PICK_BUCKETS = [(1, 3), (4, 7), (8, 14), (15, 30), (31, 60)]


def delta_curves(hist, before, key='AGE', min_minutes=500):
    """{age or experience: {stat: one-year multiplicative change}} from consecutive seasons of the
    same player (seasons < `before`), minutes-weighted (harmonic mean of the two seasons' minutes),
    each value pooled with its neighbours (a 3-wide window)."""
    h = hist[hist.SEASON < before].copy()
    if key == 'EXP':
        h = h.sort_values(['PLAYER_ID', 'SEASON'])
        h['EXP'] = h.groupby('PLAYER_ID').cumcount() + 1
    cur = h.set_index(['PLAYER_ID', 'SEASON'])
    nxt = h.assign(SEASON=h.SEASON - 1).set_index(['PLAYER_ID', 'SEASON'])
    pairs = cur.join(nxt, lsuffix='_a', rsuffix='_b', how='inner')
    pairs = pairs[(pairs.MIN_a >= min_minutes) & (pairs.MIN_b >= min_minutes)]
    group = pairs[f'{key}_b']
    w = 2 / (1 / pairs.MIN_a + 1 / pairs.MIN_b)
    out = {}
    for v in sorted(group.dropna().unique()):
        sel = (group >= v - 1) & (group <= v + 1)
        if sel.sum() < 25:
            continue
        p, ww = pairs[sel], w[sel]
        row = {}
        for s in COUNT_STATS:
            a = (ww * p[f'{s}_a'] / p.MIN_a).sum()
            b = (ww * p[f'{s}_b'] / p.MIN_b).sum()
            row[s] = b / a if a > 0 else 1.0
        row['MPG'] = (ww * p.MIN_b / p.GP_b).sum() / (ww * p.MIN_a / p.GP_a).sum()
        row['GP'] = (ww * p.GP_b).sum() / (ww * p.GP_a).sum()
        out[v] = row
    return out


def _factor(curves, v, stat):
    if not curves:
        return 1.0
    key = v if v in curves else min(curves, key=lambda k: abs(k - v))
    return curves[key].get(stat, 1.0)


def rookie_baselines(hist, drafts, before, years=6):
    """{(first pick, last pick): {'rates': per-minute, 'MPG', 'GP'}} from the first NBA season of
    players drafted in the `years` drafts before `before`."""
    d = drafts[(drafts.SEASON >= before - years) & (drafts.SEASON < before)]
    first = hist.merge(d[['PLAYER_ID', 'SEASON', 'OVERALL_PICK']], on=['PLAYER_ID', 'SEASON'], how='inner')
    out = {}
    for lo, hi in PICK_BUCKETS:
        g = first[(first.OVERALL_PICK >= lo) & (first.OVERALL_PICK <= hi) & (first.GP > 0)]
        if g.empty or g.MIN.sum() == 0:
            continue
        out[(lo, hi)] = {'rates': {s: g[s].sum() / g.MIN.sum() for s in COUNT_STATS},
                         'MPG': g.MIN.sum() / g.GP.sum(), 'GP': g.GP.mean()}
    return out


def project_season(hist, drafts, target):
    """Per-game projections for the season starting in year `target`: a DataFrame with PLAYER_ID,
    PLAYER_NAME, AGE, EXP (NBA seasons before it), PREV_TEAM, GP, MPG and COUNT_STATS per game.

    hist: one row per player-season (PLAYER_ID, PLAYER_NAME, TEAM_ABBREVIATION, AGE, GP, MIN, SEASON
    as the start year, COUNT_STATS as totals). drafts: PLAYER_ID, PLAYER_NAME, SEASON, OVERALL_PICK."""
    age_c = delta_curves(hist, target, 'AGE')
    exp_c = delta_curves(hist, target, 'EXP')
    before = hist[hist.SEASON < target]
    last_season = hist[hist.SEASON == target - 1]
    lg = {s: last_season[s].sum() / last_season.MIN.sum() for s in COUNT_STATS}
    exp_count = before.groupby('PLAYER_ID').SEASON.nunique()
    rows = []
    for pid, g in hist[(hist.SEASON >= target - 3) & (hist.SEASON < target)].groupby('PLAYER_ID'):
        g = g.sort_values('SEASON', ascending=False)
        exp_next = int(exp_count.get(pid, 0)) + 1
        young = exp_next <= 3
        weights = YOUNG_WEIGHTS if young else WEIGHTS
        w = {target - 1: weights[0], target - 2: weights[1], target - 3: weights[2]}
        wmin = sum(w[r.SEASON] * r.MIN for r in g.itertuples())
        if wmin <= 0:
            continue
        last = g.iloc[0]
        age_next = (last.AGE + (target - last.SEASON)) if pd.notna(last.AGE) else 27.0
        curves, key_v = (exp_c, exp_next) if young else (age_c, age_next)
        prior = YOUNG_PRIOR_MIN if young else PRIOR_MIN
        rates = {s: (sum(w[r.SEASON] * getattr(r, s) for r in g.itertuples()) + prior * lg[s]) / (wmin + prior)
                 * _factor(curves, key_v, s) for s in COUNT_STATS}
        wg = sum(w[r.SEASON] * r.GP for r in g.itertuples())
        mpg = (wmin / wg if wg else 0.0) * _factor(curves, key_v, 'MPG')
        gp_share = sum(w[r.SEASON] * r.GP / 82 for r in g.itertuples()) / sum(w[r.SEASON] for r in g.itertuples())
        gp = 82 * (gp_share * 3 + GP_PRIOR) / 4 * min(_factor(curves, key_v, 'GP'), 1.1)
        row = {'PLAYER_ID': pid, 'PLAYER_NAME': last.PLAYER_NAME, 'AGE': age_next, 'EXP': exp_next - 1,
               'PREV_TEAM': last.TEAM_ABBREVIATION if last.SEASON == target - 1 else None,
               'GP': min(gp, 82.0), 'MPG': min(mpg, 40.0)}
        row.update({s: rates[s] * row['MPG'] for s in COUNT_STATS})
        rows.append(row)
    base = rookie_baselines(hist, drafts, target)
    seen = set(before.PLAYER_ID)
    for r in drafts[(drafts.SEASON == target) & (~drafts.PLAYER_ID.isin(seen))].itertuples():
        b = next((v for (lo, hi), v in base.items() if lo <= r.OVERALL_PICK <= hi), None)
        if not b:
            continue
        row = {'PLAYER_ID': r.PLAYER_ID, 'PLAYER_NAME': r.PLAYER_NAME, 'AGE': np.nan, 'EXP': 0, 'PREV_TEAM': None,
               'GP': b['GP'], 'MPG': b['MPG']}
        row.update({s: b['rates'][s] * b['MPG'] for s in COUNT_STATS})
        rows.append(row)
    return pd.DataFrame(rows)
