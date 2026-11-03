"""Fit rotation_model.json from the cached 2025-26 lineups + game log (rotation_data.py):

  python rotation_fit.py [--write]       # prints the fit and its 2026-27 holdout; --write saves the JSON

P(play): logistic on [baseline, starter, DNP rate in his last 6 Active games, minutes freed /48, Active count].
Minutes if he plays: baseline + intercept + starter + a share of NEW absences' minutes (starter / bench / same
position group, per 10 baseline minutes). The bench term was ~0 out of sample, so it is halved. Refit monthly:
the 2026-27 play rate (69%) is still settling vs 84% in 2025-26.
"""
import json
import sys
from datetime import date, datetime

import numpy as np
from sklearn.linear_model import LogisticRegression

from nba_rotation import MODEL_PATH
from rotation_backtest import build, minutes_2526, minutes_2627, position_groups, rows_pplay

BENCH_SHRINK = 0.5
ALPHA, GAMMA = 0.75, 0.5


def mif_rows(recs, minb=8):
    X, Y = [], []
    for r in recs:
        F = sum(r['b'][p] for p in r['new_out']) / 10
        fg = {}
        for p in r['new_out']:
            fg[r['grp'].get(p)] = fg.get(r['grp'].get(p), 0) + r['b'][p] / 10
        for p in r['active']:
            if r['b'].get(p) is None or r['b'][p] < minb or r['actual'][p] <= 0:
                continue
            st = p in r['starter']
            g = r['grp'].get(p)
            X.append([1, st, F * st, F * (1 - st), fg.get(g, 0) if g else 0])
            Y.append(r['actual'][p] - r['b'][p])
    return np.array(X, float), np.array(Y)


def main():
    m25, _, df = minutes_2526()
    grp = position_groups()
    train = build(date(2025, 10, 21), date(2026, 4, 13), m25, {}, grp)
    prior = {int(p): v.mean() for p, v in df.groupby('PLAYER_ID')['MIN'] if len(v) >= 10}
    test = build(date(2026, 10, 20), date(2026, 11, 2), minutes_2627(), prior, grp)
    X, y = rows_pplay(train)
    lr = LogisticRegression(max_iter=2000).fit(X, y)
    Xm, Ym = mif_rows(train)
    w = np.linalg.lstsq(Xm, Ym, rcond=None)[0]
    model = {
        'pplay': {'intercept': float(lr.intercept_[0]), 'coef': [float(c) for c in lr.coef_[0]],
                  'features': ['baseline', 'starter', 'dnp_rate_last6', 'freed_min/48', 'n_active']},
        'mif': {'intercept': float(w[0]), 'starter': float(w[1]), 'new_starter': float(w[2]),
                'new_bench': float(w[3] * BENCH_SHRINK), 'same_group': float(w[4]),
                'note': 'baseline + intercept + starter*s + new_{starter|bench}*(new-absence min/10) + same_group*(same-group new-absence min/10)'},
        'alpha': ALPHA, 'gamma': GAMMA,
        'fit': {'trained_on': '2025-26', 'team_games': len(train), 'player_rows': int(len(Ym)), 'fit_date': datetime.now().strftime('%Y-%m-%d'),
                'bench_shrink': BENCH_SHRINK},
    }
    print(json.dumps(model, indent=1))
    Xt, Yt = mif_rows(test)
    wt = np.array([w[0], w[1], w[2], w[3] * BENCH_SHRINK, w[4]])
    for label, pred in (('baseline', 0), ('fitted', Xt @ wt)):
        e = np.abs(Yt - pred)
        print(f'2026-27 holdout minutes-if-plays MAE {label}: {e.mean():.3f}  (n={len(Yt)})')
    if '--write' in sys.argv:
        json.dump(model, open(MODEL_PATH, 'w'), indent=1)
        print('wrote', MODEL_PATH)


if __name__ == '__main__':
    main()
