"""Rotation / injury-minutes backtest, walk-forward, on pregame inputs only (rotation_data.py caches them).

  python rotation_backtest.py            # grid on 2025-26 (train), report the pick on 2026-27 (test)

Inputs per team-game: who is Active/Inactive and who starts (NBA daily lineups JSON), minutes after the game.
Prediction for a player = his baseline minutes, plus a share of the minutes the team's usual rotation
players who are Inactive tonight would have played. Scored on every Active player with a baseline,
including DNP-CDs (0 min), so the model pays for handing minutes to a man who never plays.
"""
import json
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

import pandas as pd

CACHE = Path(__file__).parent / '.horizon' / 'rotation'
NORM = {'NO': 'NOP', 'NY': 'NYK', 'WSH': 'WAS', 'GS': 'GSW', 'SA': 'SAS', 'PHO': 'PHX', 'BRK': 'BKN', 'CHO': 'CHA'}
WINDOW = 10            # baseline = mean of his last WINDOW played games
PRIOR_N = 4            # last season's mpg counts as this many games
OUT_MIN = 10.0         # an Inactive player with this baseline frees minutes
NEW_WITHIN = 3         # "new" absence: Active in one of the team's previous NEW_WITHIN games
GROUP = {'PG': 'G', 'SG': 'G', 'G': 'G', 'SF': 'W', 'F': 'W', 'PF': 'B', 'C': 'B', 'FC': 'B', 'GF': 'W'}


def minutes_2526():
    df = pd.read_csv(CACHE / 'gamelog_2025-26.csv', dtype={'GAME_ID': str})
    return {(r.GAME_ID, int(r.PLAYER_ID)): float(r.MIN or 0) for r in df.itertuples()}, \
        {int(r.PLAYER_ID): float(r.MIN or 0) for r in df.itertuples()}, df


def minutes_2627():
    from fantasy_database import GameLine
    return {(r.game_id, r.player_id): float(r.min or 0) for r in GameLine.select().where(GameLine.season == '2026-27')}


def position_groups():
    from fantasy_database import Player
    out = {}
    for p in Player.select(Player.id, Player.pos, Player.positions):
        first = (p.positions or p.pos or '').replace('/', ',').split(',')[0].strip()
        out[p.id] = GROUP.get(first)
    return out


def team_games(first, last):
    """[(date, game_id, team, {pid: (active, starter)})] for a date range, from the cached lineups JSON."""
    rows = []
    for f in sorted(CACHE.glob('lineups_*.json')):
        d = date(int(f.stem[8:12]), int(f.stem[12:14]), int(f.stem[14:16]))
        if not (first <= d <= last):
            continue
        for g in json.load(open(f))['games']:
            if g.get('gameStatus') != 3:
                continue
            for side in ('homeTeam', 'awayTeam'):
                t = g[side]
                rows.append((d, g['gameId'], NORM.get(t['teamAbbreviation'], t['teamAbbreviation']),
                             {p['personId']: (p['rosterStatus'] == 'Active', bool(p['position'])) for p in t['players']}))
    return rows


def build(first, last, mins, prior, grp):
    """One record per team-game: active players with baseline + actual, and the new-absence list."""
    hist = defaultdict(list)           # pid -> minutes in games played, in order
    recent_active = defaultdict(list)  # team -> list of sets of active pids
    played = defaultdict(list)         # pid -> 1/0 per game he was Active: did he play
    recs = []
    for d, gid, team, pl in sorted(team_games(first, last), key=lambda x: (x[0], x[1])):
        def base(pid):
            h = hist[pid][-WINDOW:]
            pr = prior.get(pid)
            n = len(h)
            if pr is None:
                return sum(h) / n if n >= 3 else None
            return (pr * PRIOR_N + sum(h)) / (PRIOR_N + n)
        active = {p for p, (a, s) in pl.items() if a}
        prev = recent_active[team][-NEW_WITHIN:]
        b = {p: base(p) for p in pl}
        out = [p for p, (a, s) in pl.items() if not a and b[p] and b[p] >= OUT_MIN]
        new_out = [p for p in out if any(p in s for s in prev)]
        recs.append(dict(date=d, team=team, b=b, active=active, starter={p for p, (a, s) in pl.items() if s},
                         actual={p: mins.get((gid, p), 0.0) for p in active}, out=out, new_out=new_out,
                         grp={p: grp.get(p) for p in pl},
                         dnp6={p: (1 - sum(played[p][-6:]) / len(played[p][-6:])) if played[p] else 0.0 for p in active}))
        for p in active:
            m = mins.get((gid, p), 0.0)
            played[p].append(int(m > 0))
            if m > 0:
                hist[p].append(m)
        recent_active[team].append(active)
    return recs


def predict(r, alpha, beta, gamma=0.0, cap=40.0):
    """Team minutes are fixed at 240: share them out by baseline, tilted toward the positions of the
    Inactive rotation players (beta) and toward starters (gamma); alpha mixes with the raw baseline."""
    base = {p: r['b'][p] for p in r['active'] if r['b'].get(p)}
    freed = defaultdict(float)
    for p in r['out']:
        freed[r['grp'].get(p)] += r['b'][p]
    w = {q: base[q] * (1 + beta * freed.get(r['grp'].get(q), 0) / 20) * (1 + gamma * (q in r['starter'])) for q in base}
    tot = sum(w.values()) or 1
    return {q: min((1 - alpha) * base[q] + alpha * 240 * w[q] / tot, cap) for q in base}


def score(recs, **kw):
    """(MAE on new-absence team-games, MAE on other team-games, n_new, n_other, mean freed minutes)."""
    new, oth = [], []
    for r in recs:
        pr = predict(r, **kw)
        errs = [abs(pr[p] - r['actual'][p]) for p in pr if r['b'][p] >= 5]
        (new if r['new_out'] else oth).append(errs)
    f = lambda L: sum(sum(e) for e in L) / max(sum(len(e) for e in L), 1)
    return f(new), f(oth), len(new), len(oth)


def main():
    m25, prior25, df = minutes_2526()
    grp = position_groups()
    train = build(date(2025, 10, 21), date(2026, 4, 13), m25, {}, grp)
    cnt = defaultdict(list)
    for p, v in df.groupby('PLAYER_ID')['MIN']:
        cnt[int(p)] = v
    prior = {p: v.mean() for p, v in cnt.items() if len(v) >= 10}
    test = build(date(2026, 10, 20), date(2026, 11, 2), minutes_2627(), prior, grp)
    for name, recs in (('2025-26 train', train), ('2026-27 test', test)):
        print(f"{name}: {len(recs)} team-games, {sum(1 for r in recs if r['new_out'])} with a new rotation absence")
        base = score(recs, alpha=0, beta=0)
        print(f"  baseline          new-absence MAE {base[0]:.2f}  other {base[1]:.2f}  (n {base[2]}/{base[3]})")
    best = None
    for alpha in (0.5, 0.75, 1.0):
        for beta in (0, 1, 3):
            for gamma in (0, 0.5):
                s = score(train, alpha=alpha, beta=beta, gamma=gamma)
                t = score(test, alpha=alpha, beta=beta, gamma=gamma)
                print(f"  a={alpha} b={beta} g={gamma}: train new {s[0]:.2f} oth {s[1]:.2f} | test new {t[0]:.2f} oth {t[1]:.2f}")
                if best is None or s[0] < best[0]:
                    best = (s[0], alpha, beta, gamma)
    print('best on train (new-absence games):', best)




# ---- play probability + expected minutes ----
def rows_pplay(recs):
    X, y = [], []
    for r in recs:
        freed = sum(r['b'][p] for p in r['out'])
        for p in r['active']:
            if r['b'].get(p) is None:
                continue
            X.append([r['b'][p], p in r['starter'], r['dnp6'][p], freed / 48, len(r['active'])])
            y.append(r['actual'][p] > 0)
    return X, y


def expected(r, model, alpha=0.75, gamma=0.5):
    """E[min] = P(plays) * minutes-if-plays, then the 240 team constraint with a starter tilt."""
    freed = sum(r['b'][p] for p in r['out'])
    base = {p: r['b'][p] for p in r['active'] if r['b'].get(p) is not None}
    if not base:
        return {}
    pp = model.predict_proba([[base[p], p in r['starter'], r['dnp6'][p], freed / 48, len(r['active'])] for p in base])[:, 1]
    e = {p: base[p] * q for p, q in zip(base, pp)}
    w = {p: e[p] * (1 + gamma * (p in r['starter'])) for p in e}
    tot = sum(w.values()) or 1
    return {p: min((1 - alpha) * e[p] + alpha * 240 * w[p] / tot, 40.0) for p in e}, pp


def main2():
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import roc_auc_score
    m25, _, df = minutes_2526()
    grp = position_groups()
    train = build(date(2025, 10, 21), date(2026, 4, 13), m25, {}, grp)
    prior = {int(p): v.mean() for p, v in df.groupby('PLAYER_ID')['MIN'] if len(v) >= 10}
    test = build(date(2026, 10, 20), date(2026, 11, 2), minutes_2627(), prior, grp)
    X, y = rows_pplay(train)
    model = LogisticRegression(max_iter=1000).fit(X, y)
    Xt, yt = rows_pplay(test)
    print('P(play) AUC train %.3f test %.3f; play rate train %.3f test %.3f' % (
        roc_auc_score(y, model.predict_proba(X)[:, 1]), roc_auc_score(yt, model.predict_proba(Xt)[:, 1]), sum(y) / len(y), sum(yt) / len(yt)))
    print('coefs [b, starter, dnp6, freed/48, n_active]:', [round(c, 3) for c in model.coef_[0]])
    for name, recs in (('train', train), ('test', test)):
        for label, fn in (('baseline', lambda r: {p: r['b'][p] for p in r['active'] if r['b'].get(p) is not None}),
                          ('240+starter', lambda r: predict(r, alpha=0.75, beta=0, gamma=0.5)),
                          ('P(play)*b +240+starter', lambda r: (expected(r, model) or ({},))[0])):
            allE, playedE, newE = [], [], []
            for r in recs:
                pr = fn(r)
                for p, v in pr.items():
                    if r['b'][p] < 5:
                        continue
                    e = abs(v - r['actual'][p])
                    allE.append(e)
                    if r['actual'][p] > 0:
                        playedE.append(e)
                    if r['new_out']:
                        newE.append(e)
            f = lambda L: sum(L) / len(L)
            print(f"{name} {label:24s} all-active MAE {f(allE):.2f}  played-only {f(playedE):.2f}  new-absence games {f(newE):.2f}")


if __name__ == '__main__':
    main2() if 'p' in sys.argv[1:] else main()
