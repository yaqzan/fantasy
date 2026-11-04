"""Role-aware minutes: who is available each game, and who inherits an absent teammate's minutes.

NBA-wide (no league specifics). Built from this season's game logs (game_lines), last season's totals (player_seasons)
and the rosters (players.team); fit offline on 2014-15..2025-26 logs (.horizon/role-minutes, role_minutes_model.json;
findings in .claude/docs/rotation.md "Role-aware minutes").

Model, per player i in a game he plays (minutes normalised to 240 team minutes):
    minutes = H + b0 + bH*H + bS*starter + sum_c coef_c(starter) * (X_c - Xemb_c)/10 + sum_j delta_ij * (o_j - w_ij)
  H        his recency-weighted minutes (half-life 10 games, last season's mpg worth 5 games)
  X_c      absent teammates' minutes reaching him through channel c: 'role' (shared out over the players who play,
           weighted by their minutes x stat-profile similarity to the absent player) and 'equal' (equal shares)
  Xemb_c   the same channel's weighted mean over his own past games: what his numbers already contain (dF idea)
  delta_ij learned on/off pair effect (j out -> i), an online ridge on the residual this season; w_ij = the share of
           his recent games j was out. Empirical pairs take over from the similarity prior as games come in.
Future nights: each teammate's chance of being out (o_j -> P_j(d)) from tonight's NBA sheet, ESPN return dates
(injury_reports), Yahoo status and the game-log absence tables (P(out k team games ahead | streak)).

Consumers: `factors()` (per-day minutes multiplier for the optimizer / week plan / player_week_games), `tonight()`
(the live Opp column, nba_rotation), `ros_deltas()` (minutes delta over the next ROS_GAMES games, for the
rest-of-season value; built by the poller, `refresh_ros`, read with `ros_cached`).
Everything degrades to "no change" (factor 1.0, delta 0) when a player or team has no data.
"""
import json
import math
import threading
import time
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

import numpy as np

MODEL_PATH = Path(__file__).parent / 'role_minutes_model.json'
NBA_TO_TEAMS_ABV = {'BKN': 'BRK', 'CHA': 'CHO', 'PHX': 'PHO'}
DAY_TO_DAY_CHANCE = {'P': 0.9, 'Q': 0.5, 'DTD': 0.5, 'GTD': 0.5, 'D': 0.2}   # Yahoo status -> chance he plays (optimizer's table)
OUT_STATUSES = ('O', 'INJ')
OUT_FLOOR = 0.9          # Yahoo O/INJ with no usable date: at least this likely out next game
# Return-date slip: P(back by stated + x days) for a "long" ESPN estimate. ASSUMED until injury_score.py has scored
# enough returns (no history of ESPN estimates exists): rarely early, usually within a week late, a long tail.
SLIP = [(-4, 0.05), (-1, 0.15), (0, 0.40), (3, 0.60), (7, 0.75), (14, 0.88), (28, 0.95)]
SHORT_FLOOR = 0.85       # a "short" ESPN date (placeholder): out at least this likely before it
WT = '_projected'        # the one stats choice factors() serves (MIN_projected)
FACTOR_MIN, FACTOR_MAX = 0.5, 2.0
DELTA_CAP = 15.0         # minutes, either way
MAX_MIN = 44.0
REBUILD_EVERY = 15 * 60  # seconds: the season walk is rebuilt when game_lines change, checked at most this often
ROS_GAMES = 10           # team games ahead the rest-of-season value takes the role model's redistribution for (rotation.md)
ROS_WHY_MIN = 5.0        # minutes over those games before the ROS column says why

_lock = threading.Lock()
_cache = {'key': None, 'seasons': {}, 'checked': 0.0}


def load_model():
    return json.load(open(MODEL_PATH))


def _slip_cdf(x):
    """P(back within x days of the stated return date), piecewise linear through SLIP."""
    pts = SLIP
    if x <= pts[0][0]:
        return pts[0][1] * max(0.0, 1 + (x - pts[0][0]) / 7)
    for (x0, p0), (x1, p1) in zip(pts, pts[1:]):
        if x <= x1:
            return p0 + (p1 - p0) * (x - x0) / (x1 - x0)
    return min(0.99, pts[-1][1] + (x - pts[-1][0]) * 0.002)


class Season:
    """This season's walk: every player's H, embedded context, pair effects, streaks; then scenarios for future days."""

    def __init__(self, model=None, today=None, depth=True):
        from fantasy_database import GameLine, Player, PlayerSeason, Team
        from projections import season_label
        self.m = model or load_model()
        w = self.m['walk']
        self.lam = 0.5 ** (1 / w['half_life_games']); self.K = w['prior_games']; self.out_min = w['out_min']
        self.tau = w['tau']; self.pw = np.array(w['profile_weights']); self.shrink = w['profile_shrink_min']
        self.prof_keys = w['profile']
        self.today = today or date.today()
        season = season_label(self.today)
        prev = f'{int(season[:4]) - 1}-{season[2:4]}'
        abv_of_full = {}
        teams_abv = {v: k for k, v in NBA_TO_TEAMS_ABV.items()}
        for t in Team.select():
            if t.abv:
                abv_of_full[t.name] = teams_abv.get(t.abv, t.abv)
        abv_of_full['LA Clippers'] = abv_of_full.get('Los Angeles Clippers', 'LAC')
        abv_of_full['LA Lakers'] = abv_of_full.get('Los Angeles Lakers', 'LAL')
        self.abv_of_full = abv_of_full
        self.full_of_abv = {v: k for k, v in abv_of_full.items() if not k.startswith('LA ')}
        self.names, self.roster, self.injury = {}, {}, {}
        for p in Player.select(Player.id, Player.name, Player.team, Player.injury_status):
            self.names[p.id] = p.name
            if p.team:
                self.roster[p.id] = abv_of_full.get(p.team)
            if p.injury_status:
                self.injury[p.id] = p.injury_status
        # last season: mpg prior, half-weight stat totals for the profile, z scaling
        self.prior, prev_tot = {}, {}
        rates = []
        for r in PlayerSeason.select().where(PlayerSeason.season == prev):
            if not r.min:
                continue
            tot = np.array([r.min] + [float(getattr(r, k) or 0) for k in self.prof_keys])
            prev_tot[r.player_id] = prev_tot.get(r.player_id, 0) + tot * 0.5
            if r.gp and r.gp >= w['prior_min_gp']:
                self.prior[r.player_id] = r.min / r.gp
            if r.min >= 500:
                rates.append(tot[1:] / r.min * 36)
        rates = np.array(rates) if rates else np.ones((2, len(self.prof_keys)))
        self.mu, self.sd = rates.mean(0), rates.std(0) + 1e-9
        self.prev_tot = prev_tot
        # this season's lines -> team-games
        lines = defaultdict(dict)       # (team, date) -> {pid: (min_norm, statvec)}
        for r in GameLine.select().where((GameLine.season == season) & (GameLine.game_date < self.today)):
            if (r.min or 0) <= 0 or not r.team:
                continue
            lines[(r.team, r.game_date)][r.player_id] = (float(r.min), np.array([float(r.min)] + [float(getattr(r, k) or 0) for k in self.prof_keys]))
        for key, g in lines.items():
            tot = sum(v[0] for v in g.values())
            if tot >= 236:
                for p in g:
                    g[p] = (g[p][0] * 240.0 / tot, g[p][1])
        self.lines = lines
        self.key = (len(lines), max((d for _, d in lines), default=None))
        self.depth_on = depth
        try:
            import depth_charts
            self.depth = depth_charts.latest(self.today) if depth else {}
        except Exception as e:
            print(f'role_minutes depth: {e}')
            self.depth = {}
        self._walk()

    # ---------------------------------------------------------------- walk
    def _prof(self, p):
        tot = self.cum.get(p, 0) + self.prev_tot.get(p, 0)
        if isinstance(tot, int) or tot[0] <= 0:
            return np.zeros(len(self.prof_keys))
        m = tot[0]
        return (tot[1:] / m * 36 - self.mu) / self.sd * (m / (m + self.shrink))

    def H(self, p):
        pr = self.prior.get(p)
        if pr is not None:
            return (self.K * pr + self.Sm[p]) / (self.K + self.Sw[p])
        return self.Sm[p] / self.Sw[p] if self.ng[p] >= 3 else None

    def _alloc(self, pool_ids, pool_h, pool_w, j, team=None):
        """(role shares, equal shares) of j's minutes over the pool (j excluded); pool_w = chance each plays. The role
        weight of the first pool player listed behind j on ESPN's depth chart (any position j is listed at) is
        multiplied by 1 + depth_boost."""
        pj = self._prof(j)
        P = np.array([self._prof(p) for p in pool_ids])
        D = ((P - pj) ** 2 * self.pw).sum(1)
        keep = np.array([p != j for p in pool_ids], float) * pool_w
        w1 = np.maximum(pool_h, 1.0) * np.exp(-(D - D.min()) / self.tau) * keep
        boost = self.m.get('depth_boost', 0.0) if self.depth_on else 0.0
        if boost and team in self.depth:
            pos_of = {p: i for i, p in enumerate(pool_ids)}
            for lst in self.depth[team].values():
                if j in lst:
                    nxt = next((pos_of[q] for q in lst[lst.index(j) + 1:] if q in pos_of and keep[pos_of[q]] > 0), None)
                    if nxt is not None:
                        w1[nxt] *= 1 + boost
        w2 = keep.copy()
        s1, s2 = w1.sum(), w2.sum()
        return (w1 / s1 if s1 > 0 else w1), (w2 / s2 if s2 > 0 else w2)

    def _members(self):
        """(team, date) -> member pids: stints from the log, opening night on for a player still on that team's roster
        who has played for no one else, through today for a player still on the roster."""
        seqs = defaultdict(list)
        for (t, d) in self.lines:
            seqs[t].append(d)
        for t in seqs:
            seqs[t].sort()
        stints = defaultdict(list)
        for (t, d) in sorted(self.lines, key=lambda k: k[1]):
            for p in self.lines[(t, d)]:
                s = stints[p]
                if s and s[-1][0] == t:
                    s[-1][2] = d
                else:
                    s.append([t, d, d])
        mem = defaultdict(set)
        for p, s in stints.items():
            for k, (t, a, b) in enumerate(s):
                dates = seqs[t]
                lo, hi = dates.index(a), dates.index(b)
                if k == 0 and len(s) == 1 and self.roster.get(p) == t:
                    lo = 0
                if k == len(s) - 1 and self.roster.get(p) == t:
                    hi = len(dates) - 1
                for d in dates[lo:hi + 1]:
                    mem[(t, d)].add(p)
        for p, t in self.roster.items():   # on a roster, no game yet (out since opening night)
            if p not in stints and t in seqs and p in self.prior:
                for d in seqs[t]:
                    mem[(t, d)].add(p)
        self.seqs = seqs
        return mem

    def _walk(self):
        kp = self.m['pair_kp']; xbar = self.m['xbar']
        self.xbar = np.array([xbar['role'], xbar['equal']])
        self.Sm, self.Sw, self.ng = defaultdict(float), defaultdict(float), defaultdict(int)
        self.SX = defaultdict(lambda: np.zeros(2))
        self.cum = {}
        self.hist = defaultdict(list)     # pid -> [(team, date, X(2), starter, frozenset out j)] played games
        self.pairs = defaultdict(dict)    # (team, i) -> {j: [num, den, so]}
        self.psw = defaultdict(float)     # (team, i) -> decayed games (pair weights)
        self.streak = defaultdict(int)    # (team, p) -> team games missed in a row
        self.last_team = {}
        mem = self._members()
        self.members_last = {t: mem[(t, d[-1])] for t, d in self.seqs.items() if d}
        for t, d in sorted(((t, d) for (t, d) in self.lines), key=lambda k: (k[1], k[0])):
            g = self.lines[(t, d)]
            M = mem[(t, d)]
            A = [p for p in M if p in g]
            if not A:
                continue
            HA = np.array([self.H(p) if self.H(p) is not None else 8.0 for p in A])
            X = np.zeros((len(A), 2)); outsets = [set() for _ in A]
            top5 = set(np.array(A)[np.argsort(-HA)[:5]])
            for j in M:
                if j in g:
                    continue
                h = self.H(j)
                if h is None or h < self.out_min:
                    continue
                a1, a2 = self._alloc(A, HA, np.ones(len(A)), j, t)
                X[:, 0] += h * a1; X[:, 1] += h * a2
                for i in np.nonzero(h * a1 >= self.m['walk']['pair_min_alloc'])[0]:
                    outsets[i].add(j)
            for k, p in enumerate(A):
                y = g[p][0]
                Hp = self.H(p)
                st = p in top5
                if Hp is not None and Hp >= 8:
                    keff = self.K if p in self.prior else 0.0
                    emb = (keff * self.xbar + self.SX[p]) / (keff + self.Sw[p]) if keff + self.Sw[p] > 0 else self.xbar
                    lin = Hp + self._lin(Hp, st, (X[k] - emb) / 10)
                    self._pair_update((t, p), outsets[k], y - lin, kp)
                else:
                    self._pair_update((t, p), outsets[k], None, kp)
                self.hist[p].append((t, d, X[k].copy(), st, frozenset(outsets[k])))
            for k, p in enumerate(A):
                y, vec = g[p]
                self.Sm[p] = self.lam * self.Sm[p] + y; self.Sw[p] = self.lam * self.Sw[p] + 1
                self.SX[p] = self.lam * self.SX[p] + X[k]; self.ng[p] += 1
                self.cum[p] = self.cum.get(p, 0) + vec
                self.last_team[p] = t
            for p in M:
                self.streak[(t, p)] = 0 if p in g else self.streak[(t, p)] + 1

    def _lin(self, H, st, dx, c=None):
        c = c or self.m['coef']
        if st:
            return c['b0'] + c['H'] * H + c['starter'] + c['role_starter'] * dx[0] + c['equal_starter'] * dx[1]
        return c['b0'] + c['H'] * H + c['role_bench'] * dx[0] + c['equal_bench'] * dx[1]

    def _pair_update(self, key, out_now, r, kp):
        s = self.pairs[key]
        for j in out_now:
            s.setdefault(j, [0.0, 0.0, 0.0])
        den_w = self.K + self.psw[key]
        for j, v in s.items():
            o = 1.0 if j in out_now else 0.0
            z = o - v[2] / den_w
            if r is not None:
                v[0] += r * z; v[1] += z * z
            v[2] = self.lam * v[2] + o
        self.psw[key] = self.lam * self.psw[key] + 1

    # ---------------------------------------------------------------- embedded context per weighting
    def _weights(self, p, weighting):
        """(prior weight, per-game weights oldest first) of his played games this season."""
        n = len(self.hist.get(p, ()))
        if weighting == 'H':
            return (self.K if p in self.prior else 0.0), self.lam ** np.arange(n - 1, -1, -1)
        if weighting == '_projected':   # THE projection's minutes weights, the one shared definition (inseason.py)
            from inseason import minutes_weights
            k, w = minutes_weights(n)
            return float(k), w
        if weighting in ('_5', '_10'):
            w = np.zeros(n); w[max(0, n - int(weighting[1:])):] = 1.0
            return 0.0, w
        if weighting == '':
            return 0.0, np.ones(n)
        return 1.0, np.zeros(n)   # '_proj': the preseason line, typical context

    def embedded(self, p, team, weighting):
        """(Xemb(2), starter share, {j: share of his games j was out}) under `weighting`, over his games for `team`."""
        h = [x for x in self.hist.get(p, ()) if x[0] == team]
        k0, w = self._weights(p, weighting)
        w = w[-len(h):] if h else np.zeros(0)
        tot = k0 + w.sum()
        if tot <= 0:
            return self.xbar.copy(), 0.0, {}
        # the prior's context: 'H' (as fit) a typical night; a projection's prior knew who was out at the start of the
        # season (a season-long injury is in every expert line), so its context = his first games' (up to 3)
        x0 = self.xbar if weighting == 'H' or not h else np.mean([x[2] for x in h[:3]], axis=0)
        X = (k0 * x0 + sum(wi * x[2] for wi, x in zip(w, h))) / tot
        # starter share over his games only (a prior has no starter history): None = no games, no change
        st = sum(wi * x[3] for wi, x in zip(w, h)) / w.sum() if w.sum() > 0 else None
        share = defaultdict(float)
        for wi, x in zip(w, h):
            for j in x[4]:
                share[j] += wi / tot
        return X, st, share

    def delta_pair(self, team, i, j):
        v = self.pairs.get((team, i), {}).get(j)
        return v[0] / (v[1] + self.m['pair_kp']) if v else 0.0

    # ---------------------------------------------------------------- availability
    def refresh_status(self):
        """Re-read Yahoo statuses and rosters (hourly sync) without rebuilding the walk."""
        from fantasy_database import Player
        rows = list(Player.select(Player.id, Player.team, Player.injury_status))
        self.injury = {p.id: p.injury_status for p in rows if p.injury_status}
        self.roster = {p.id: self.abv_of_full.get(p.team) for p in rows if p.team}

    def members_now(self, team):
        """Current roster of `team` (players.team), plus anyone who played its last game and is on no roster."""
        on = {p for p, t in self.roster.items() if t == team}
        on |= {p for p in self.members_last.get(team, ()) if p not in self.roster}
        return on

    def p_out(self, p, team, d, k, ctx):
        """Chance p sits team game number k (1 = the next one) on day d. ctx: {'reports', 'sheet', 'today'}."""
        sheet = ctx.get('sheet') or {}
        if d == ctx.get('today') and p in sheet:
            active, starter, confirmed = sheet[p]
            if not active:
                return 1.0
            if starter and confirmed:
                return 0.0
        h = self.H(p) or 0.0
        streak = self.streak.get((team, p), 0)
        ab = self.m['absence']
        kk = max(1, min(k, len(ab['base']['10'])))

        def table(s):
            if s <= 0:
                band = max(b for b in (5, 10, 20, 30) if h >= b) if h >= 5 else 5
                return ab['base'][str(band)][kk - 1]
            lo = max(x for x in (1, 2, 4, 8, 16) if s >= x)
            return ab['out_k'][f'{lo}_{10 if h >= 10 else 5}'][min(k, 30) - 1]

        rep = (ctx.get('reports') or {}).get(p)
        status = self.injury.get(p)
        if rep and rep.get('status') == 'Out' and rep.get('return_date'):
            q = rep.get('quality')
            if q == 'long':
                return 1.0 - _slip_cdf((d - rep['return_date']).days)
            base = table(max(streak, 1))
            return max(base, SHORT_FLOOR) if d < rep['return_date'] else base
        if status in OUT_STATUSES:
            v = table(max(streak, 1))
            return max(v, OUT_FLOOR) if k == 1 else v
        if status in DAY_TO_DAY_CHANCE or (rep and rep.get('status') == 'Day-To-Day'):
            if k == 1:
                return 1 - DAY_TO_DAY_CHANCE.get(status, 0.5)
            return table(max(streak, 1) if streak else 1)
        return table(streak)

    def schedule(self, team):
        """The team's game dates from today on (sorted); every team's read in one query, once per Season."""
        if not hasattr(self, '_sched'):
            from fantasy_database import Game
            sched = defaultdict(set)
            for home, away, d in Game.select(Game.team_home, Game.team_away, Game.date).where(Game.date >= self.today).tuples():
                for full in (home, away):
                    sched[self.abv_of_full.get(full)].add(d)
            self._sched = {t: sorted(v) for t, v in sched.items() if t}
        return self._sched.get(team, [])

    def team_days(self, team, days):
        """The team's games on `days` (sorted), with k = game number counted from today (1 = next game)."""
        want = set(days)
        return {d: i + 1 for i, d in enumerate(self.schedule(team)) if d in want}

    def scenario(self, team, d, k, ctx, weightings=('H',)):
        """{pid: result} for every likely member of `team` on day d: exp (H-level minutes if he plays), base (H),
        delta[weighting] (minutes vs what that weighting's numbers already contain), p_out, reason [(name, minutes)]."""
        M = sorted(self.members_now(team))
        if not M:
            return {}
        H = {p: self.H(p) for p in M}
        P = {p: self.p_out(p, team, d, k, ctx) for p in M}
        pool = [p for p in M if H[p] is not None and P[p] < 1.0]
        if not pool:
            return {}
        ph = np.array([H[p] for p in pool]); pw = np.array([1 - P[p] for p in pool])
        sheet = ctx.get('sheet') or {}
        starters = {p for p, v in sheet.items() if v[1] and v[0]} if d == ctx.get('today') else set()
        likely = [p for p in pool if P[p] < 0.5]
        top5 = starters & set(pool) if len(starters & set(pool)) >= 5 else set(sorted(likely, key=lambda p: -H[p])[:5])
        X = np.zeros((len(pool), 2)); contrib = defaultdict(lambda: defaultdict(float))
        for j in M:
            h = H[j]
            if h is None or h < self.out_min or P[j] <= 0:
                continue
            a1, a2 = self._alloc(pool, ph, pw, j, team)
            X[:, 0] += P[j] * h * a1; X[:, 1] += P[j] * h * a2
            for i, p in enumerate(pool):
                contrib[p][j] += P[j] * h * a1[i]
        out = {}
        # tonight with the NBA sheet posted: the next-game fit; any other night only has a forecast of who plays:
        # the fit on forecast availability (future.py). Offsets: the typical night's (X - Xemb), so a typical
        # context is delta 0 (the projection's level is not this model's business).
        tonight = d == ctx.get('today') and any(p in sheet for p in M)
        c = self.m['coef'] if tonight else self.m['coef_future']
        off = np.array(self.m['offset']['tonight'] if tonight else self.m['offset']['future'][min(k, 4) - 1])
        for i, p in enumerate(pool):
            st = p in top5
            res = {'base': round(H[p], 1), 'p_out': round(P[p], 3), 'starter': st, 'delta': {}, 'tonight': tonight}
            pairs = self.pairs.get((team, p), {})
            den_w = self.K + self.psw.get((team, p), 0.0)
            pair_share = {j: v[2] / den_w for j, v in pairs.items()}   # the pair state's own embedded share (as fit)
            pair_H = sum(self.delta_pair(team, p, j) * (P.get(j, 0.0) - pair_share[j]) for j in pairs)
            cr = c['role_starter'] if st else c['role_bench']; ce = c['equal_starter'] if st else c['equal_bench']
            for wt in weightings:
                emb, st_emb, share = self.embedded(p, team, wt)
                dx = (X[i] - emb) / 10 - off
                dl = cr * dx[0] + ce * dx[1] + (c['starter'] * (float(st) - st_emb) if st_emb is not None else 0.0)
                dl += pair_H if wt == 'H' else sum(self.delta_pair(team, p, j) * (P.get(j, 0.0) - share.get(j, 0.0)) for j in pairs)
                res['delta'][wt] = float(np.clip(dl, -DELTA_CAP, DELTA_CAP))
            emb, _, _ = self.embedded(p, team, 'H')
            lin = H[p] + self._lin(H[p], st, (X[i] - emb) / 10, c)
            res['exp'] = round(float(np.clip(lin + pair_H, 0, MAX_MIN)), 1)
            top = sorted(((v + self.delta_pair(team, p, j) * P.get(j, 0.0), j) for j, v in contrib[p].items() if P.get(j, 0) >= 0.5),
                         reverse=True)[:2]
            res['reason'] = [(self.names.get(j, str(j)), round(v, 1), round(P[j], 2)) for v, j in top if v >= 1.0]
            out[p] = res
        return out


# ---------------------------------------------------------------- cache + public API

def season(today=None):
    """The cached Season for `today` (Eastern date), rebuilt when this season's game lines change (checked every
    REBUILD_EVERY s). One per day: the poller asks for tomorrow after a slate ends while web requests ask for today.
    None on error."""
    from fantasy_database import GameLine
    from projections import season_label
    from daily_leaders import nba_today
    from peewee import fn
    t = today or nba_today()
    now = time.time()
    with _lock:
        seasons = _cache['seasons']
        if t in seasons and now - _cache['checked'] < REBUILD_EVERY:
            return seasons[t]
        try:
            key = (GameLine.select(fn.COUNT(GameLine.player_id)).where(GameLine.season == season_label(t)).scalar(),
                   GameLine.select(fn.MAX(GameLine.game_date)).where(GameLine.season == season_label(t)).scalar())
            if _cache['key'] != key:
                seasons.clear()
                _cache['key'] = key
            if t in seasons:
                seasons[t].refresh_status()
            else:
                for old in [d for d in seasons if d != t][:-1]:   # keep two days at most
                    del seasons[old]
                seasons[t] = Season(today=t)
            _cache['checked'] = now
        except Exception as e:
            print(f'role_minutes: {e}')
            return seasons.get(t)
        return seasons[t]


def context(today, sheet=None):
    """The availability inputs read at call time: ESPN reports (DB), tonight's sheet {pid: (active, starter, confirmed)}."""
    try:
        import injury_reports
        reports = injury_reports.latest(today)
    except Exception as e:
        print(f'role_minutes reports: {e}')
        reports = {}
    return {'today': today, 'reports': reports, 'sheet': sheet or {}}


def tonight_sheet(today):
    """{pid: (active, starter, confirmed)} from the poller's NBA lineups state when it is fresh and for today, else {}."""
    try:
        import nba_rotation
        st = nba_rotation.get_state()
        players = nba_rotation.current(today, st)
        if not players or st['day'] != today.isoformat():
            return {}
        return {pid: (not v.get('inactive'), bool(v.get('starter')), bool(v.get('confirmed'))) for pid, v in players.items()}
    except Exception:
        return {}


def factors(player_stats, days, suffix, today=None, sheet=None):
    """{name: {day: minutes factor}} for every player in player_stats whose team plays on `days`: (MIN{suffix} + delta)
    / MIN{suffix}, delta = expected minutes change vs what that stats choice already contains, clipped to
    [FACTOR_MIN, FACTOR_MAX]. Players without data get no entry (factor 1.0). {} if the model can't be built."""
    from daily_leaders import nba_today
    if suffix != WT:
        return {}   # only THE projection carries a minutes line the role model's delta is measured against
    today = today or nba_today()
    s = season(today)
    if s is None:
        return {}
    ctx = context(today, tonight_sheet(today) if sheet is None else sheet)
    pid_of = {v: k for k, v in s.names.items()}
    teams = defaultdict(list)
    for name, st in player_stats.items():
        team = s.abv_of_full.get(st.get('TEAM'))
        pid = pid_of.get(name)
        if team and pid is not None:
            teams[team].append((name, pid, st))
    days = sorted(d for d in days if d >= today)
    scen = {}
    for team in teams:
        for d, k in s.team_days(team, days).items():
            scen[(team, d)] = s.scenario(team, d, k, ctx, (WT,))
    center(scen, WT, s)
    out = defaultdict(dict)
    for (team, d), sc in scen.items():
        for name, pid, st in teams[team]:
            r = sc.get(pid)
            base = float(st.get(f'MIN{suffix}') or 0)
            if r is None or base < 4:
                continue
            f = (base + r['delta'][WT]) / base
            if math.isfinite(f) and abs(f - 1) > 0.005:
                out[name][d] = round(min(max(f, FACTOR_MIN), FACTOR_MAX), 3)
    return dict(out)


def center(scen, wt, s):
    """Subtract the league-neutral mean delta (model['center'][wt], fit-time constants in role_minutes_model.json by
    tonight/forecast x starter/bench; `python .horizon/role-minutes/calibrate_center.py`): the league as a whole is
    neutral context, so what is left is each team's own situation. Raw means were bench -1.4 min, starters -0.1 (the
    pair term prices returns from absences already in his numbers). Constants, not live slate means: those moved with
    how many teams had posted a lineup (reviewed 2026-11-04). Mutates `scen` {(team, day): {pid: result}}."""
    c = s.m.get('center', {}).get(wt, {})
    for sc in scen.values():
        for r in sc.values():
            m = c.get(('tonight' if r.get('tonight') else 'future') + ('S' if r['starter'] else 'B'))
            if m:
                r['delta'][wt] -= m
                r['center'] = round(m, 2)


def tonight_day(day, sheet, teams):
    """{pid: scenario result + 'why'/'back'} for `teams` playing on `day`, with the NBA sheet {pid: (active, starter,
    confirmed)}: the live Opp column (nba_rotation.compute_day). delta['H'] = minutes vs his recent numbers (the fit),
    delta['_projected'] = vs what THE projection's minutes carry (what the optimizer's factor uses; the Opp column)."""
    s = season(day)
    if s is None:
        return {}
    ctx = context(day, sheet)
    scen = {}
    for team in teams:
        k = s.team_days(team, [day]).get(day)
        if k:
            scen[(team, day)] = s.scenario(team, day, k, ctx, ('H', '_projected'))
    center(scen, 'H', s)
    center(scen, '_projected', s)
    out = {}
    for sc in scen.values():
        for pid, r in sc.items():
            r['why'], r['back'] = reason_text(r, ctx['reports'], s)
            out[pid] = r
    return out


def reason_text(r, reports, s):
    """('Duren out (back ~Nov 9): +6 min', '2026-11-09') from a scenario result: the absent teammate whose minutes
    reach him most. ('', None) when no single absence explains a minute or more."""
    if not r.get('reason'):
        return '', None
    name, mins, p = r['reason'][0]
    pid = next((k for k, v in s.names.items() if v == name), None)
    rep = reports.get(pid) if pid is not None else None
    back = rep.get('return_date') if rep else None
    parts = [w for w in (name or '?').split(' ') if w.rstrip('.').lower() not in ('jr', 'sr', 'ii', 'iii', 'iv')]
    last = parts[-1] if parts else name
    when = f' (back ~{back:%b} {back.day})' if back else ''
    sure = '' if p >= 0.95 else f' ({round(p * 100)}% out)'
    return f'{last} out{when}{sure}: +{mins:.0f} min', back.isoformat() if back else None


def ros_deltas(today=None, sheet=None):
    """{pid: (minutes, games, why)}: the role model's minutes delta vs what THE projection carries, summed over his
    team's next ROS_GAMES games (if he plays them: the caller weights by his availability), the number of those games,
    and a one-line reason. Further out the redistribution is not trusted (rotation.md "Rest of season"). Each team's
    scenario per night is computed once for all its players. ~1-2 s: the poller builds it (refresh_ros), requests read
    the cache (ros_cached)."""
    from daily_leaders import nba_today
    today = today or nba_today()
    s = season(today)
    if s is None:
        return {}
    ctx = context(today, tonight_sheet(today) if sheet is None else sheet)
    teams = {t for t in s.roster.values() if t}
    scen = {}
    for team in teams:
        for k, d in enumerate(s.schedule(team)[:ROS_GAMES], start=1):
            scen[(team, d)] = s.scenario(team, d, k, ctx, (WT,))
    center(scen, WT, s)
    tot, n, best = defaultdict(float), defaultdict(int), {}
    for (team, d), sc in scen.items():
        for pid, r in sc.items():
            if s.roster.get(pid) != team:
                continue
            dl = r['delta'][WT]
            tot[pid] += dl; n[pid] += 1
            if abs(dl) > abs(best.get(pid, (0.0, None))[0]):
                best[pid] = (dl, r)
    out = {}
    for pid, total in tot.items():
        why = ''
        if abs(total) >= ROS_WHY_MIN and pid in best:
            line, _ = reason_text(best[pid][1], ctx['reports'], s)
            why = (f'{line}; ' if line and total > 0 else '') + f'{total:+.0f} min over the next {n[pid]} games'
        out[pid] = (round(total, 1), n[pid], why)
    return out


_ros = {'key': None, 'at': 0.0, 'deltas': {}}


def refresh_ros(today=None, every=3600):
    """Rebuild the ROS deltas when the day or this season's lines changed, or `every` s passed (poller thread only)."""
    from daily_leaders import nba_today
    today = today or nba_today()
    key = (today, _cache['key'])
    if key == _ros['key'] and time.time() - _ros['at'] < every:
        return
    deltas = ros_deltas(today)
    _ros.update({'key': (today, _cache['key']), 'at': time.time(), 'deltas': deltas, 'day': today})


def ros_cached(today=None):
    """The poller's ROS deltas for `today` ({} before its first build, or when they are for another day)."""
    from daily_leaders import nba_today
    return _ros['deltas'] if _ros.get('day') == (today or nba_today()) else {}


if __name__ == '__main__':
    import sys
    from daily_leaders import nba_today
    t = nba_today()
    s = season(t)
    team = sys.argv[1] if len(sys.argv) > 1 else 'DET'
    ctx = context(t, tonight_sheet(t))
    days = [t + timedelta(days=i) for i in range(14)]
    for d, k in s.team_days(team, days).items():
        sc = s.scenario(team, d, k, ctx, ('H', '_projected'))
        print(d, f'game {k}')
        for p, r in sorted(sc.items(), key=lambda x: -x[1]['exp']):
            if r['exp'] >= 8:
                print(f"   {s.names.get(p, p):24s} exp {r['exp']:5.1f}  H {r['base']:5.1f}  dH {r['delta']['H']:+5.1f}  dProj {r['delta']['_projected']:+5.1f}"
                      f"  out {r['p_out']:.2f}  {'S' if r['starter'] else ' '}  {r['reason']}")
