"""Week plan for a Yahoo daily-lineup points league: every add, drop, IL move and claim day for the rest of the week.

One MILP (scipy.optimize.milp / HiGHS) per activation day of each healthy IL player; the plan with the best expected
FPTS wins, then the repo's own `Week.team` + `category_win_chances` re-score it (and the no-moves roster) for the
page. Read-only: nothing is written to the DB. The math (corrected layer weights, the IL freeze, penalties) is in
`.claude/docs/lineup-optimizer.md` "Week plan (claim_planner.py)".

    python claim_planner.py [league] [timeframe]
"""
from __future__ import annotations

import copy
import itertools
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field, asdict
from datetime import date, timedelta
import json
from typing import Optional

import numpy as np
from scipy.optimize import milp, LinearConstraint, Bounds
from scipy.sparse import coo_matrix

EPS = 0.1      # FPTS per day earlier, on adds and drops (prefer later moves)
EPS_D = 0.5    # FPTS per drop (no gratuitous drops)
EPS_IL = 0.25  # FPTS per IL move (> EPS, so an OUT player is not shuffled out of IL just to drop him a day later)
BASE_POSITIONS = ('PG', 'SG', 'SF', 'PF', 'C')
LINEUP_TTL = 1800   # Yahoo's stored per-date lineups: one burst per 30 minutes
PLAN_TTL = 60       # a whole plan, per (league, week, timeframe)
SOLVE_BUDGET = 8.0  # wall-clock seconds for the activation-day search (solve)
FULL_ENUM = 60      # activation-day combinations up to which solve tries every one


# ---------------------------------------------------------------- instance

@dataclass
class PlayerData:
    """One player: my roster + IL + candidate free agents. v[t] = expected FPTS if he STARTS on day t (FPTS x his
    doubtful factor on his next game; 0 with no open game or OUT); the 0.86 availability lives in the layer weights.
    lk: his team's day-0 game is under way (no drop / IL move today). first_add: first day index a claim can land."""
    team: str = ''
    fpts: float = 0.0
    zscore: float = 0.0
    elig: list = field(default_factory=list)
    owned: bool = False
    il: bool = False
    undroppable: bool = False
    out: bool = False
    game: list = field(default_factory=list)
    v: list = field(default_factory=list)
    doubt: float = 1.0
    lk: bool = False
    live_share: float = 0.0
    locked_start: bool = False
    first_add: Optional[int] = None
    has_stats: bool = True
    mf: list = field(default_factory=list)   # per day: role_minutes factor (that night's expected minutes / usual); [] = 1.0
    keep: float = 0.0   # FPTS of holding him past this week (keep_values): earned if he is mine at the week's end

    def f(self, t):
        return self.mf[t] if self.mf else 1.0


@dataclass
class Instance:
    """My week frozen at one moment; day index t = 0 is today. stored_lineup[t] = Yahoo's stored starters for days[t]
    (played on frozen days). healthy_in_il: IL players who are not OUT (they freeze the lineup and block adds)."""
    league: str = ''
    week_start: str = ''
    week_end: str = ''
    suffix: str = '_projected'
    days: list = field(default_factory=list)
    slots: list = field(default_factory=list)
    open_slots: list = field(default_factory=list)
    n_slots: list = field(default_factory=list)
    players: dict = field(default_factory=dict)
    stored_lineup: list = field(default_factory=list)
    stored_source: str = 'yahoo'
    healthy_in_il: list = field(default_factory=list)
    claims_left: int = 5
    N: int = 13
    K: int = 3
    avail: float = 0.86
    my_carried: float = 0.0
    live_const: float = 0.0
    opp_mean: float = 0.0
    opp_var: float = 0.0
    notes: list = field(default_factory=list)

    @property
    def T(self):
        return len(self.days)

    def free_agents(self):
        return [p for p, d in self.players.items() if not d.owned]

    def to_json(self):
        return json.dumps(asdict(self), indent=1, sort_keys=True)


@dataclass
class Plan:
    """moves: [{'t', 'type': add|drop|il_in|il_out, 'player'}] in execution order within a day (drop, il_out, il_in,
    add). frozen[t]: a healthy player is still in IL that day. objective: model FPTS less the tie-break penalties."""
    moves: list = field(default_factory=list)
    lineups: list = field(default_factory=list)
    frozen: list = field(default_factory=list)
    objective: float = 0.0
    model_fpts: float = 0.0
    meta: dict = field(default_factory=dict)


def states(inst: Instance, plan: Plan):
    """[(owned set, IL set)] after each day's moves, replaying `plan.moves` from the instance's start state."""
    owned = {p for p, d in inst.players.items() if d.owned}
    il = {p for p, d in inst.players.items() if d.il}
    out, by_day = [], {}
    for m in plan.moves:
        by_day.setdefault(m['t'], []).append(m)
    for t in range(inst.T):
        for m in by_day.get(t, []):
            p, kind = m['player'], m['type']
            if kind == 'add':
                owned.add(p)
            elif kind == 'drop':
                owned.discard(p)
                il.discard(p)
            elif kind == 'il_in':
                il.add(p)
            elif kind == 'il_out':
                il.discard(p)
        out.append((set(owned), set(il)))
    return out


# ---------------------------------------------------------------- Yahoo's stored lineups (cached, one burst)

_lineups = {}                      # (yahoo league id, team id, date) -> (fetched at, {norm name: (name, slot, status, elig)})
_lineups_lock = threading.Lock()   # one burst at a time; a second caller waits and reads the cache


def yahoo_lineups(lg, days):
    """[{norm name: (display name, slot, status, eligible)}] per day from Yahoo's stored per-date roster, or None."""
    if lg.platform != 'yahoo':
        return None
    from fantasy_team_helper import get_team_by_abv
    import pull_yahoo as py
    from projections import norm_name
    team = get_team_by_abv(lg, lg.my_team)
    if team is None or not team.platform_team_id:
        return None
    key = f'nba.l.{lg.platform_league_id}.t.{team.platform_team_id}'

    def one(d):
        root = py.fetch(f'team/{key}/roster;date={d.isoformat()}')
        day = {}
        for p in root.iter(f"{{{py.NS['y']}}}player"):
            name = py._text(p, 'y:name/y:full')
            day[norm_name(name)] = (name, py._text(p, 'y:selected_position/y:position'), py._text(p, 'y:status'),
                                    [e.text for e in p.findall('y:eligible_positions/y:position', py.NS)])
        return day

    with _lineups_lock:
        now = time.time()
        missing = [d for d in days if now - _lineups.get((key, d), (0, None))[0] >= LINEUP_TTL]
        if missing:
            try:
                with ThreadPoolExecutor(max_workers=4) as pool:
                    got = list(pool.map(one, missing))
            except (Exception, SystemExit) as e:   # pull_yahoo raises SystemExit on a login error
                print(f'yahoo stored lineups: {e}')
                return None
            for d, day in zip(missing, got):
                _lineups[(key, d)] = (now, day)
        return [_lineups[(key, d)][1] for d in days]


# ---------------------------------------------------------------- instance building (the live state, read-only)

def load_week(lg, week_start, week_end, timeframe=None):
    """(Week, suffix) for a league-week: the repo's own objects."""
    import lineup_optimizer as lo
    from player_stats import default_stat_type
    return lo.Week(lg, week_start, week_end), lo.timeframe_suffix(timeframe or default_stat_type(lg))


def select_pool(inst, mult=1.0):
    """The candidate pool, in place: keep the free agents that are, for some base position and some day t, among the
    top round((C + 9) x mult) addable free agents by v[t] (that day) OR by sum_{t' >= t} v[t'] + keep (what adding
    him on t is worth: a multi-game streamer who tops no single day, or a keeper). Returns the kept names."""
    k = int(round((inst.claims_left + 9) * mult))
    fa = {p: d for p, d in inst.players.items() if not d.owned}
    chosen = set()
    for t in range(inst.T):
        rest = {p: sum(d.v[t:]) + d.keep for p, d in fa.items()}
        for pos in BASE_POSITIONS:
            ok = [p for p, d in fa.items() if d.first_add is not None and d.first_add <= t and pos in d.elig]
            chosen.update(sorted((p for p in ok if fa[p].v[t] > 0), key=lambda p: (-fa[p].v[t], p))[:k])
            chosen.update(sorted((p for p in ok if rest[p] > 0), key=lambda p: (-rest[p], p))[:k])
    for p in fa:
        if p not in chosen:
            del inst.players[p]
    return chosen


KEEP_WEEK_WEIGHTS = (1.0, 0.5)   # the next two fantasy weeks' games count this much (owner's choice: the 1/1 vs 1/0.5 difference is within noise)
AVG_WEEK_GAMES = 3.5      # NBA games per team-week (82 over ~23.5 weeks): a week whose schedule is not stored yet


def keep_of(fpg, plays, repl):
    """Keep value: (his FPTS per game - the replacement's, floored at 0) x the games he is expected to play past
    this week (plays = the chance he plays each team game, times its week's weight). A game he misses costs nothing: he sits in IL."""
    return max(fpg - repl, 0.0) * sum(plays)


def keep_values(lg, week, suffix, names, notes):
    """{name: keep}: what holding each of `names` past this week is worth, in the plan's units (FPTS): keep_of over
    his team's games in the next two fantasy weeks (weighted KEEP_WEEK_WEIGHTS) (league schedule). The chance he plays a game is
    role_minutes Season.p_out's (ESPN return dates, Yahoo's status, his absence streak; k = team games from today).
    Replacement = the claims_per_week-th best healthy free agent's FPTS per game (the worst of one week's claims).
    No next week in the schedule (the season's last week) = {}: pure streaming."""
    import role_minutes
    import daily_leaders
    from fantasy_team_helper import get_next_week_dates, get_available_players
    weeks, ws = [], week.week_start
    for _ in KEEP_WEEK_WEIGHTS:
        ws, we = get_next_week_dates(lg, ws)
        if ws is None:
            break
        weeks.append((ws, min(we, ws + timedelta(days=6))))   # a 2-week matchup counts its first week only
    if not weeks:
        notes.append('keep values off: no next fantasy week in the league schedule (the last week of the season, or this week is not in it)')
    today = daily_leaders.nba_today()
    s = role_minutes.season(today) if weeks else None
    if s is None:
        if weeks:
            notes.append('keep values off: the role_minutes season model could not be built')
        return {}
    ctx = role_minutes.context(today, {})
    stats = week.stats
    stored = {d for t in set(s.abv_of_full.values()) for d in s.schedule(t)}
    missing = [i for i, (a, b) in enumerate(weeks) if not any(a <= d <= b for d in stored)]
    if missing:
        notes.append(f'NBA schedule not stored for {len(missing)} of the next {len(weeks)} weeks: keep values assume '
                     f'{AVG_WEEK_GAMES} games there at his rest-of-season share')
    fpg = lambda p: float(stats[p].get(f'FPTS{suffix}') or 0.0)  # noqa: E731

    def plays(p):
        st = stats[p]
        team = s.abv_of_full.get(st.get('TEAM'))
        out = [KEEP_WEEK_WEIGHTS[i] * AVG_WEEK_GAMES * (st.get('ROS_SHARE') or 0.0) for i in missing]
        for k, d in enumerate(s.schedule(team), 1):
            if d > weeks[-1][1]:
                break
            for i, (a, b) in enumerate(weeks):
                if a <= d <= b:
                    out.append(KEEP_WEEK_WEIGHTS[i] * (1.0 - s.p_out(st.get('NBA_ID'), team, d, k, ctx)))
        return out

    per_game = sorted((fpg(p) for p in get_available_players(lg, stats)), reverse=True)
    C = lg.claims_per_week or 5
    repl = per_game[min(C, len(per_game)) - 1] if per_game else 0.0
    return {p: keep_of(fpg(p), plays(p), repl) for p in names if p in stats}


def build_instance(lg, week, suffix, opp):
    """The live Instance for my team's week, through the repo's own Week (`week`, already loaded)."""
    import lineup_optimizer as lo
    from fantasy_team_helper import get_undroppable_players, claims_left
    from leagues import slot_reach
    from projections import norm_name
    from player_stats import AVAILABILITY
    notes = []
    start = week.start_day
    days = []
    d = start
    while d <= week.week_end:
        days.append(d)
        d += timedelta(days=1)
    T = len(days)
    roster, il = lo._active_roster(lg)
    owned_all = roster + il
    undroppable = set(get_undroppable_players(lg))
    C = claims_left(lg, week.week_start)
    stats = week.stats
    tipped = week.actual.tipped if week.actual else set()
    weights = week.day_weights or {}
    mfac = week.minutes_factor(suffix)   # role_minutes: each day's minutes factor, so v[t] (and the judge) see it

    # today's canon: who already played / is playing in a counted slot (Week.team's locked / taken)
    lines = week.canon.lines.get(week.my_canon) if (week.canon and week.my_canon) else None
    mine_nn = {norm_name(p): p for p in owned_all}
    counted_today = set()
    if lines is not None and days and days[0] in lines:
        counted_today = {mine_nn.get(nn, lines[days[0]][nn]['name']) for nn in lines[days[0]]}
    elif week.actual:
        notes.append('no canon for today: taken/locked from the best-fit guess (week_actuals.lineup_of)')
        from week_actuals import lineup_of
        week.team(roster, suffix, owned_all)
        counted_today = set(lineup_of(week.actual, owned_all, suffix).get(days[0], ()))
    taken0 = len(counted_today)

    # the judge's view of the whole week (carried FPTS; the opponent's totals)
    mine = week.team(roster, suffix, owned_all)
    carried = (mine.carried or {}).get('FPTS', 0.0)
    label, theirs = week.opponent(opp, suffix)
    if theirs is None:
        theirs = mine.totals
        notes.append('no opponent: judged against a copy of my team (repo convention)')

    # Yahoo stored lineups per remaining date
    ylu = yahoo_lineups(lg, days)
    stored_source = 'yahoo'
    if ylu is None:
        stored_source = 'copied'
        notes.append('Yahoo stored lineups unavailable: today\'s best-fit lineup copied forward (NOT Yahoo\'s)')
    yahoo_name = {}   # norm name -> repo name
    stored = []
    if ylu:
        for t, day in enumerate(ylu):
            lu = {}
            for nn, (name, slot, status, elig) in day.items():
                repo = mine_nn.get(nn)
                if repo is None:
                    repo = name
                    if t == 0:
                        notes.append(f'Yahoo has {name} ({slot}) on my roster, the DB does not (stale sync?)')
                yahoo_name[nn] = repo
                if slot not in ('BN', 'IL', 'IL+', 'NA', ''):
                    lu[repo] = 'UTIL' if slot == 'Util' else slot
            stored.append(lu)
        for p in owned_all:
            if norm_name(p) not in ylu[0]:
                notes.append(f'DB has {p} on my roster, Yahoo today does not (stale sync?)')
        y_il = {yahoo_name[nn] for nn, row in ylu[0].items() if row[1] in ('IL', 'IL+')}
        if y_il != set(il):
            notes.append(f'IL differs: DB {sorted(il)} vs Yahoo {sorted(y_il)}')
    else:
        lu0 = {p: s for p, s in lo.best_starters(lg, [p for p in roster if p not in week.injured], stats, suffix).items()}
        stored = [dict(lu0) for _ in days]

    # open slots today: the slots not held by a player whose game already started
    slots = list(lg.slots)
    open0 = list(slots)
    if stored and days:
        for p in counted_today:
            s = stored[0].get(p)
            if s in open0:
                open0.remove(s)
            else:
                notes.append(f'{p} counted today but not in a stored starting slot: a UTIL slot assumed taken')
                for alt in ('UTIL',) + tuple(slots):
                    if alt in open0:
                        open0.remove(alt)
                        break
    if len(open0) != len(slots) - taken0:
        notes.append(f'open slots today {len(open0)} != 9 - taken {taken0}: using 9 - taken for n_0')
        open0 = open0[:max(len(slots) - taken0, 0)]
    open_slots = [open0] + [list(slots) for _ in days[1:]]

    def next_game(p, first):
        team = stats[p]['TEAM']
        return min((d for d in week.remaining.get(team, {}) if not (first and d < first)), default=None)

    def pdata(p, owned):
        s = stats.get(p)
        if s is None:
            return PlayerData(owned=owned, il=p in il, undroppable=p in undroppable, has_stats=False,
                              game=[False] * T, v=[0.0] * T, elig=['UTIL'])
        team = s['TEAM']
        fpts = float(s.get(f'FPTS{suffix}', 0) or 0)
        out = p in week.injured
        elig = set(s.get('Reach') or slot_reach(s.get('Positions') or ()))
        for lu in stored:
            if p in lu:
                elig.add(lu[p])
        first_add = None
        if not owned:
            first = week.first_claim_day(p)
            first_add = next((t for t, d in enumerate(days) if d >= first), None)
        doubt = week.doubtful.get(p, 1.0)
        nxt = next_game(p, None if owned else week.first_claim_day(p)) if doubt < 1 else None
        game, v = [], []
        mfp = mfac.get(p, {})
        mf = [mfp.get(d, 1.0) for d in days] if mfp else []
        for t, d in enumerate(days):
            open_game = d in week.remaining.get(team, {}) and (team, d) not in tipped
            game.append(bool(open_game))
            val = fpts * (doubt if d == nxt else 1.0) * (mf[t] if mf else 1.0) if open_game and not out else 0.0
            v.append(max(val, 0.0))
        lk = bool(days) and (team, days[0]) in tipped
        live_share = weights.get((team, days[0]), 1.0) if lk else 0.0
        locked_start = lk and p in counted_today
        return PlayerData(team=team, fpts=fpts, zscore=float(s.get(f'Z-SCORE{suffix}', 0) or 0), elig=sorted(elig),
                          owned=owned, il=p in il, undroppable=owned and p in undroppable, out=out, game=game, v=v,
                          doubt=doubt, lk=lk, live_share=live_share, locked_start=locked_start, first_add=first_add, mf=mf)

    players = {p: pdata(p, True) for p in owned_all}
    for p in (stored[0] if stored else {}):
        if p not in players:
            players[p] = PlayerData(owned=True, has_stats=p in stats, game=[False] * T, v=[0.0] * T, elig=['UTIL', stored[0][p]])
            notes.append(f'{p}: in Yahoo\'s lineup, not in the DB roster: present with v=0')
    for p in week.free_agents(suffix):
        players[p] = pdata(p, False)
    for p, k in keep_values(lg, week, suffix, list(players), notes).items():
        players[p].keep = k
    live_const = sum(d.fpts * d.live_share for d in players.values() if d.locked_start)
    inst = Instance(league=lg.id, week_start=week.week_start.isoformat(), week_end=week.week_end.isoformat(),
                    suffix=suffix, days=[d.isoformat() for d in days], slots=slots, open_slots=open_slots,
                    n_slots=[len(s) for s in open_slots], players=players, stored_lineup=stored,
                    stored_source=stored_source,
                    healthy_in_il=sorted(p for p in il if p in players and not players[p].out),
                    claims_left=C, N=lg.roster_size, K=3, avail=AVAILABILITY, my_carried=carried, live_const=live_const,
                    opp_mean=theirs['FPTS'][0], opp_var=theirs['FPTS'][1], notes=notes)
    select_pool(inst)
    return inst, label


# ---------------------------------------------------------------- the MILP

def layer_coefs(n, R, avail):
    """{k: c_k} for k = 1..R, c_k = w_{k-1} - w_k with w_r = _lineup_chance(r, n, avail) and w_R := 0.
    sum_r w_r v_(r) (r < R, v sorted descending, zeros allowed) == sum_k c_k * (sum of the top k)."""
    from player_stats import _lineup_chance
    if n <= 0:
        return {}
    w = [_lineup_chance(r, n, avail) for r in range(R)] + [0.0]
    return {k: w[k - 1] - w[k] for k in range(1, R + 1) if abs(w[k - 1] - w[k]) > 1e-15}


class _Model:
    """A tiny sparse MILP builder: named variables, rows, objective."""

    def __init__(self):
        self.idx, self.lb, self.ub, self.integ, self.obj = {}, [], [], [], []
        self.rows, self.rlb, self.rub = [], [], []

    def var(self, key, lb=0.0, ub=1.0, integer=True, obj=0.0):
        self.idx[key] = len(self.lb)
        self.lb.append(lb)
        self.ub.append(ub)
        self.integ.append(1 if integer else 0)
        self.obj.append(obj)
        return self.idx[key]

    def add_obj(self, key, c):
        self.obj[self.idx[key]] += c

    def row(self, terms, lb=-np.inf, ub=np.inf):
        cols = {}
        for k, c in terms:
            j = k if isinstance(k, int) else self.idx[k]
            cols[j] = cols.get(j, 0.0) + c
        self.rows.append(cols)
        self.rlb.append(lb)
        self.rub.append(ub)

    def solve(self, time_limit=60):
        n = len(self.lb)
        r, c, v = [], [], []
        for i, cols in enumerate(self.rows):
            for j, x in cols.items():
                r.append(i)
                c.append(j)
                v.append(x)
        A = coo_matrix((v, (r, c)), shape=(len(self.rows), n)).tocsr()
        cons = [LinearConstraint(A, np.array(self.rlb), np.array(self.rub))] if self.rows else []
        return milp(c=-np.array(self.obj), constraints=cons, integrality=np.array(self.integ),
                    bounds=Bounds(np.array(self.lb), np.array(self.ub)),
                    options={'time_limit': time_limit, 'mip_rel_gap': 1e-9, 'disp': False})


DOUBT_SEP = '\x00'   # '<name>\x00<day>': one copy of a doubtful free agent per next game (_split_doubtful)


def _split_doubtful(inst):
    """(players, alias): each doubtful free agent becomes one candidate per game g he can still be added before,
    addable only on the days whose next game is g (first_add..last_add), with the doubt factor on g. A Q/D status is
    about his NEXT game, so it lands on his first game after the day he is actually added (the judge's rule), not
    on the first game after his earliest add day. A day-0 game under way counts as his next game, as in the judge.
    alias maps a copy's key to his name; at most one copy is added (one add per player, _solve_one)."""
    T = inst.T
    players, alias = {}, {}
    for p, d in inst.players.items():
        if d.owned or d.doubt >= 1 or d.first_add is None:
            players[p] = d
            continue
        games = [t for t in range(T) if d.game[t] or (t == 0 and d.lk)]
        prev, copies = -1, []
        for g in games:
            lo, hi = max(prev + 1, d.first_add), g
            prev = g
            if lo > hi:
                continue
            c = copy.copy(d)
            c.first_add, c.last_add = lo, hi
            c.v = [max(d.fpts * (d.doubt if t == g else 1.0) * d.f(t), 0.0) if d.game[t] and not d.out else 0.0 for t in range(T)]
            copies.append((g, c))
        if len(copies) <= 1:      # one window: his v already carries the factor on that game
            players[p] = d
            continue
        for g, c in copies:
            players[f'{p}{DOUBT_SEP}{g}'] = c
            alias[f'{p}{DOUBT_SEP}{g}'] = p
    return players, alias


def _solve_one(inst: Instance, C, dstar, positions=False, time_limit=60, alias=None):
    """One MILP with the healthy IL players' activation days fixed (dstar {q: day index, T = never}). Plan or None.
    alias {key: name}: the copies of one doubtful free agent (_split_doubtful); at most one of them is added."""
    alias = alias or {}
    P, T, N, K, a_ = inst.players, inst.T, inst.N, inst.K, inst.avail
    names = list(P)
    healthy = list(inst.healthy_in_il)
    for q in healthy:   # a doubtful IL player's factor sits on his first game from his activation day (the judge's)
        d = P[q]
        if d.doubt < 1 and dstar.get(q, T) < T:
            g = next((t for t in range(dstar[q], T) if d.game[t] or (t == 0 and d.lk)), None)
            if P is inst.players:
                P = dict(P)
            P[q] = copy.copy(d)
            P[q].v = [max(d.fpts * (d.doubt if t == g else 1.0) * d.f(t), 0.0) if d.game[t] and not d.out else 0.0
                      for t in range(T)]
    frozen = [any(t < dstar.get(q, T) for q in healthy) for t in range(T)]
    m = _Model()

    def addable(p, t):
        d = P[p]
        last = getattr(d, 'last_add', None)
        return ((not d.owned) and d.first_add is not None and t >= d.first_add and not frozen[t]
                and (last is None or t <= last))

    # --- variables: o owned, a added, d dropped, i in IL, g an IL move (penalised)
    for p in names:
        d = P[p]
        if not d.owned and d.first_add is None:
            continue
        for t in range(T):
            lb, ub = 0.0, 1.0
            if d.owned and d.undroppable:
                lb = 1.0
            if d.owned and t == 0 and d.lk:
                lb = ub = 1.0
            if not d.owned and (d.first_add is None or t < d.first_add):
                ub = 0.0
            if p in healthy and t < dstar[p]:
                lb = ub = 1.0
            m.var(('o', p, t), lb, ub)
            if addable(p, t):
                m.var(('a', p, t), obj=-(EPS * (T - 1 - t)))
            if not (d.owned and d.undroppable):
                m.var(('d', p, t), 0.0, 1.0, integer=False, obj=-(EPS_D + EPS * (T - 1 - t)))
            if d.owned and (d.il or d.out):
                lb, ub = 0.0, 1.0
                if t == 0 and d.lk:
                    lb = ub = 1.0 if d.il else 0.0
                if p in healthy:
                    lb = ub = 1.0 if t < dstar[p] else 0.0
                m.var(('i', p, t), lb, ub)
                m.var(('g', p, t), 0.0, 1.0, integer=False, obj=-EPS_IL)

    def has(key):
        return key in m.idx

    def act(p, t):
        """[(key, coef)] of o - i."""
        terms = [(('o', p, t), 1.0)]
        if has(('i', p, t)):
            terms.append((('i', p, t), -1.0))
        return terms

    pl = [p for p in names if has(('o', p, 0))]
    # --- constraints
    for p in pl:
        d = P[p]
        for t in range(T):
            prev_o = 1.0 if d.owned else 0.0
            if d.owned:
                if t > 0:   # no re-add: o[t] <= o[t-1]
                    m.row([(('o', p, t), 1.0), (('o', p, t - 1), -1.0)], ub=0.0)
            else:           # o[t] - o[t-1] <= a[t]
                terms = [(('o', p, t), 1.0)] + ([(('o', p, t - 1), -1.0)] if t > 0 else [])
                if has(('a', p, t)):
                    terms.append((('a', p, t), -1.0))
                    m.row([(('a', p, t), 1.0), (('o', p, t), -1.0)], ub=0.0)    # an add owns him that day
                m.row(terms, ub=0.0)
            if has(('d', p, t)):   # d[t] >= o[t-1] - o[t]
                if t == 0:
                    m.row([(('d', p, 0), 1.0), (('o', p, 0), 1.0)], lb=prev_o)
                else:
                    m.row([(('d', p, t), 1.0), (('o', p, t), 1.0), (('o', p, t - 1), -1.0)], lb=0.0)
            if has(('i', p, t)):
                m.row([(('i', p, t), 1.0), (('o', p, t), -1.0)], ub=0.0)          # i <= o
                prev_i = [(('i', p, t - 1), -1.0)] if t > 0 else []
                i0 = 1.0 if (t == 0 and d.il) else 0.0
                if has(('g', p, t)):
                    m.row([(('g', p, t), 1.0), (('i', p, t), -1.0)] + [(k, -c) for k, c in prev_i], lb=-i0)
                    # an exit counts only when it is not a drop: g >= i[t-1] - i[t] - (o[t-1] - o[t])
                    if t > 0:
                        m.row([(('g', p, t), 1.0), (('i', p, t), 1.0), (('i', p, t - 1), -1.0),
                               (('o', p, t - 1), 1.0), (('o', p, t), -1.0)], lb=0.0)
                    else:
                        m.row([(('g', p, 0), 1.0), (('i', p, 0), 1.0), (('o', p, 0), -1.0)], lb=i0 - 1.0)
                # enter IL only if OUT: i[t] - i[t-1] <= OUT
                m.row([(('i', p, t), 1.0)] + prev_i, ub=(1.0 if d.out else 0.0) + i0)
                if frozen[t]:
                    # frozen: no IL entries (i[t] <= i[t-1]) ...
                    m.row([(('i', p, t), 1.0)] + prev_i, ub=i0)
                    # ... and an IL player leaves only by being dropped: i[t-1] - i[t] <= o[t-1] - o[t]
                    if t > 0:
                        m.row([(('i', p, t), 1.0), (('i', p, t - 1), -1.0), (('o', p, t), -1.0), (('o', p, t - 1), 1.0)], lb=0.0)
                    else:   # i0 - i[0] <= 1 - o[0]
                        m.row([(('i', p, 0), 1.0), (('o', p, 0), -1.0)], lb=i0 - 1.0)
        if not d.owned:
            akeys = [(('a', p, t), 1.0) for t in range(T) if has(('a', p, t))]
            if akeys:
                m.row(akeys, ub=1.0)
    allk = [(k, 1.0) for k in m.idx if k[0] == 'a']
    if allk:
        m.row(allk, ub=C)
    groups = {}
    for k in allk:
        if k[0][1] in alias:
            groups.setdefault(alias[k[0][1]], []).append(k)
    for ks in groups.values():   # one add per player across his copies (no re-adding my own drop)
        if len(ks) > 1:
            m.row(ks, ub=1.0)
    for t in range(T):
        m.row([kc for p in pl for kc in act(p, t)], ub=N)
        ik = [(('i', p, t), 1.0) for p in pl if has(('i', p, t))]
        if ik:
            m.row(ik, ub=K)

    # --- objective: day values (frozen: Yahoo's stored starters at 0.86 each; open: the corrected layers)
    R = N
    for t in range(T):
        live = [p for p in pl if P[p].v[t] > 0]
        if frozen[t]:
            for p in inst.stored_lineup[t] if t < len(inst.stored_lineup) else {}:
                if p in P and has(('o', p, t)) and P[p].v[t] > 0:
                    for k, c in act(p, t):
                        m.add_obj(k, a_ * P[p].v[t] * c)
            continue
        n = inst.n_slots[t]
        for k, ck in layer_coefs(n, R, a_).items():
            if k == R:
                for p in live:
                    for key, c in act(p, t):
                        m.add_obj(key, ck * P[p].v[t] * c)
            elif k == n and positions:
                caps = {}
                for s in inst.open_slots[t]:
                    caps[s] = caps.get(s, 0) + 1
                for p in live:
                    ys = [m.var(('y', p, s, t), integer=False, obj=ck * P[p].v[t]) for s in caps if s in P[p].elig]
                    if ys:
                        m.row([(j, 1.0) for j in ys] + [(key, -c) for key, c in act(p, t)], ub=0.0)
                for s, cap in caps.items():
                    col = [(('y', p, s, t), 1.0) for p in live if has(('y', p, s, t))]
                    if col:
                        m.row(col, ub=cap)
            else:
                us = []
                for p in live:
                    j = m.var(('u', k, p, t), integer=False, obj=ck * P[p].v[t])
                    us.append(j)
                    m.row([(j, 1.0)] + [(key, -c) for key, c in act(p, t)], ub=0.0)
                if us and len(us) > k:
                    m.row([(j, 1.0) for j in us], ub=k)
    for p in pl:   # past this week: his keep value if he is still mine at the end (a drop forfeits it, an add earns it)
        if P[p].keep:
            m.add_obj(('o', p, T - 1), P[p].keep)
    t0 = time.time()
    res = m.solve(time_limit)
    dt = time.time() - t0
    if res.x is None:
        return None
    x = res.x
    val = lambda key: x[m.idx[key]] if key in m.idx else 0.0  # noqa: E731
    # --- read the plan
    moves, lineups = [], []
    for t in range(T):
        day = []
        for p in pl:
            d = P[p]
            po = (1.0 if d.owned else 0.0) if t == 0 else val(('o', p, t - 1))
            pi = (1.0 if d.il else 0.0) if t == 0 else val(('i', p, t - 1))
            o, i = val(('o', p, t)), val(('i', p, t))
            if po > .5 and o < .5:
                day.append((0, 'drop', p))
            elif po < .5 and o > .5:
                day.append((3, 'add', p))
            if o > .5:
                if pi > .5 and i < .5:
                    day.append((1, 'il_out', p))
                elif pi < .5 and i > .5:
                    day.append((2, 'il_in', p))
        moves += [{'t': t, 'type': k, 'player': alias.get(p, p)} for _, k, p in sorted(day)]
        if frozen[t]:
            lineups.append(dict(inst.stored_lineup[t]))
        elif positions:
            lineups.append({alias.get(k[1], k[1]): k[2] for k, j in m.idx.items() if k[0] == 'y' and k[3] == t and x[j] > .5})
        else:
            act_p = [p for p in pl if val(('o', p, t)) - val(('i', p, t)) > .5 and P[p].v[t] > 0]
            lineups.append({alias.get(p, p): 'any' for p in sorted(act_p, key=lambda p: -P[p].v[t])[:inst.n_slots[t]]})
    obj = -res.fun
    pen = sum(-m.obj[j] * x[j] for k, j in m.idx.items() if k[0] in ('a', 'd', 'g'))
    keep_end = sum(P[p].keep * val(('o', p, T - 1)) for p in pl)
    return Plan(moves=moves, lineups=lineups, frozen=frozen, objective=obj + inst.my_carried + inst.live_const,
                model_fpts=inst.my_carried + inst.live_const + obj + pen - keep_end,
                meta={'dstar': {q: (inst.days[d] if d < T else 'never') for q, d in dstar.items()}, 'solve_s': round(dt, 3),
                      'vars': len(m.lb), 'rows': len(m.rows), 'penalty': pen, 'keep_end': keep_end})


def solve(inst: Instance, positions=False, budget=SOLVE_BUDGET, full_limit=FULL_ENUM, split_doubt=True) -> Plan:
    """Best plan over the healthy IL players' activation days d* (day 0 skipped while his game is on; 'never' = T).
    Activating on d* leaves him free to be dropped that day, which covers 'drop him'.

    Up to `full_limit` combinations: every one, in product order (the exact optimum). More (2-3 healthy players, long
    weeks): first every player on one common day D (the freeze ends at max d*, and activating before it scores nothing
    on a frozen day, so a common D is the natural candidate), then coordinate descent one player's day at a time from
    the best. `budget` seconds of wall clock (None = no limit): when it runs out the best plan so far is returned with
    meta['budget_hit'] = True. The first MILP always runs. split_doubt: doubtful free agents get one candidate per
    add window (_split_doubtful), so his factor sits on the game after the day he is actually added."""
    alias = {}
    if split_doubt:
        players, alias = _split_doubtful(inst)
        if alias:
            inst = copy.copy(inst)
            inst.players = players
    T = inst.T
    healthy = list(inst.healthy_in_il)
    choices = [[T] + [t for t in range(T) if not (t == 0 and inst.players[q].lk)] for q in healthy]
    n_combos = 1
    for c in choices:
        n_combos *= len(c)
    t0 = time.time()
    seen, state = {}, {'best': None, 'combo': None, 'hit': False}

    def run(combo):
        if combo in seen or state['hit']:
            return
        if budget is not None and state['best'] is not None and time.time() - t0 > budget:
            state['hit'] = True
            return
        left = 60 if (budget is None or state['best'] is None) else max(budget - (time.time() - t0), 1.0)
        plan = _solve_one(inst, inst.claims_left, dict(zip(healthy, combo)), positions, time_limit=left, alias=alias)
        seen[combo] = plan
        if plan is not None and (state['best'] is None or plan.objective > state['best'].objective + 1e-7):
            state['best'], state['combo'] = plan, combo

    if n_combos <= full_limit:
        search = 'full'
        for combo in itertools.product(*choices) if choices else [()]:
            run(combo)
    else:
        search = 'descent'
        common = sorted(set.intersection(*(set(c) for c in choices)), key=lambda d: (d != T, d))
        for d in common:
            run((d,) * len(healthy))
        improved = True
        while improved and not state['hit'] and state['combo'] is not None:
            improved, start = False, state['combo']
            for j, opts in enumerate(choices):
                for d in opts:
                    run(start[:j] + (d,) + start[j + 1:])
            improved = state['combo'] != start
    best = state['best']
    if best is None:
        raise RuntimeError('no feasible plan for any activation day: a data gap today (a stored starter missing '
                           'from the roster, or an eligibility gap), not a rule conflict')
    best.meta.update(solves=len(seen), combos=n_combos, search=search, budget_hit=state['hit'], doubt_copies=len(alias),
                     total_s=round(time.time() - t0, 2))
    return best


# ---------------------------------------------------------------- the judge (the repo's own model)

def score_judge(inst: Instance, plan: Plan, week, rules=True):
    """Re-score a plan with Week.team, day by day (week.remaining / doubtful narrowed to one day per call, restored
    after). Frozen days (rules=True) pass Yahoo's stored starters only: Week.team then scores each at 0.86, no cover.
    Returns {fpts, var, sd, p_win, per_day}; p_win is category_win_chances against the opponent's week."""
    from player_stats import category_win_chances
    suffix = inst.suffix
    P = inst.players
    days = [date.fromisoformat(d) for d in inst.days]
    st = states(inst, plan)
    owned0 = [p for p, d in P.items() if d.owned]
    saved = week.remaining, week.doubtful
    full = week.remaining
    first_active = {}
    for t in range(inst.T):
        owned, il = st[t]
        for p in owned - il:
            first_active.setdefault(p, t)
    start_active = {p for p, d in P.items() if d.owned and not d.il}
    total_m, total_v, per_day = 0.0, 0.0, []
    carried = inst.my_carried
    try:
        for t, day in enumerate(days):
            owned, il = st[t]
            active = owned - il
            frozen = rules and any(not P[q].out for q in il)
            roster = [p for p in inst.stored_lineup[t] if p in active] if frozen else sorted(active)
            week.remaining = {team: {day: g[day]} for team, g in full.items() if day in g}
            dbt = {}
            for p in roster:
                c = saved[1].get(p)
                if c is None or p not in week.stats:
                    continue
                team = week.stats[p]['TEAM']
                first = None if p in start_active else days[first_active.get(p, t)]
                nxt = min((d for d in full.get(team, {}) if not (first and d < first)), default=None)
                if nxt == day:
                    dbt[p] = c
            week.doubtful = dbt
            side = week.team(roster, suffix, owned0)
            m, v = side.totals['FPTS']
            c0 = (side.carried or {}).get('FPTS', 0.0)
            per_day.append(m - c0)
            total_m += m - c0
            total_v += v
            carried = c0
    finally:
        week.remaining, week.doubtful = saved
    mine = {'FPTS': (carried + total_m, total_v)}
    p = category_win_chances(mine, {'FPTS': (inst.opp_mean, inst.opp_var)}, week.league)['FPTS']
    return {'fpts': carried + total_m, 'var': total_v, 'sd': total_v ** .5, 'p_win': p, 'per_day': per_day}


# ---------------------------------------------------------------- the page's payload

ASSUMPTIONS = [
    'Adds use the week\'s claims; drops and IL moves are free.',
    'A player is worth his next two weeks too (keep: his FPTS per game above a free agent you could claim '
    'instead, x the games he should play): a drop gives it up, an add gains it.',
    'A dropped player cannot be added by anyone for 3 days.',
    'IL takes only OUT players. A healthy player left in IL freezes the lineup and blocks adds until he is activated, '
    'and activating him needs an open active spot.',
    'Only starters score; the bench covers absent starters (each player plays 86% of his games).',
    'OUT means out all week; positions are ignored, as in the rest of the Pickup Desk.',
    'Claims land at once and the opponent makes no moves.',
]


def unsupported_reason(lg, week_start, week_end):
    if lg.platform != 'yahoo':
        return 'The week plan reads Yahoo\'s stored lineups and IL rules: Yahoo leagues only.'
    if not lg.daily_lineups:
        return 'The week plan is for daily-lineup leagues.'
    if not lg.is_points:
        return 'The week plan is for points leagues (category leagues need the category model).'
    if not (week_start and week_end):
        return 'No scheduled week.'
    import daily_leaders
    if week_end < daily_leaders.nba_today():
        return 'This week is over.'
    return None


def _note(inst, m, n_add):
    d = inst.players.get(m['player'])
    kind = m['type']
    keep = f' · keep {d.keep:.0f}' if d.keep >= 0.5 else ''
    if kind == 'add':
        games = sum(1 for t in range(m['t'], inst.T) if d.game[t])
        return f"claim {n_add} · {games} game{'s' if games != 1 else ''} left · {d.fpts:.1f} FPTS/g{keep}"
    if kind == 'drop':
        return ('OUT · ' if d.out else '') + f'{d.fpts:.1f} FPTS/g{keep} · unaddable 3 days'
    if kind == 'il_in':
        return 'OUT: frees an active spot'
    return 'activate' if not d.out else 'back to the active roster'


def week_plan(lg, timeframe=None, week_start=None, week_end=None, opponent=None):
    """The /api/plan payload: the plan's moves per day, today's moves, win chance and points now vs with the plan."""
    reason = unsupported_reason(lg, week_start, week_end)
    if reason:
        return {'supported': False, 'reason': reason}
    started = time.time()
    import lineup_optimizer as lo
    week, suffix = load_week(lg, week_start, week_end, timeframe)
    if not any(p in week.stats for p in lo._active_roster(lg)[0]):
        return {'supported': False, 'reason': 'No players on your team in this league yet.'}
    inst, label = build_instance(lg, week, suffix, opponent)
    if not inst.days:
        return {'supported': False, 'reason': 'No days left in this week.'}
    plan = solve(inst)
    judged = score_judge(inst, plan, week)
    none = score_judge(inst, Plan(), week)
    days, n_add = [], 0
    for t, day in enumerate(inst.days):
        tx = []
        for m in plan.moves:
            if m['t'] != t:
                continue
            n_add += m['type'] == 'add'
            d = inst.players.get(m['player'])
            tx.append({'type': m['type'], 'player': m['player'], 'note': _note(inst, m, n_add),
                       'keep': round(d.keep, 1) if d and m['type'] in ('add', 'drop') else None})
        days.append({'date': day, 'frozen': bool(plan.frozen[t]), 'today': t == 0, 'transactions': tx})
    warnings = []
    if inst.stored_source != 'yahoo':
        warnings.append('Yahoo\'s stored lineups could not be read: frozen days assume today\'s best lineup.')
    if inst.claims_left == 0:
        warnings.append('No claims left this week: only drops and IL moves are possible.')
    if plan.meta.get('budget_hit'):
        warnings.append(f'Activation-day search stopped at its {SOLVE_BUDGET:.0f} s budget: the best plan found so far, '
                        'maybe not the best.')
    warnings += [n[0].upper() + n[1:] + '.' for n in inst.notes if 'stale sync' in n or 'IL differs' in n]
    return {
        'supported': True, 'week_start': inst.week_start, 'week_end': inst.week_end, 'today': inst.days[0],
        'timeframe': timeframe, 'opponent': label, 'claims_left': inst.claims_left,
        'claims_per_week': lg.claims_per_week,
        'now': {'win_chance': round(none['p_win'], 4), 'points': round(none['fpts'], 1)},
        'plan': {'win_chance': round(judged['p_win'], 4), 'points': round(judged['fpts'], 1),
                 'model_points': round(plan.model_fpts, 1),
                 # next-2-weeks value of the week-end roster minus today's (keep_values; negative = the plan sells future value)
                 'keep_total': round(plan.meta['keep_end'] - sum(d.keep for d in inst.players.values() if d.owned), 1)},
        'opponent_points': round(inst.opp_mean, 1),
        'days': days, 'do_today': days[0]['transactions'],
        'warnings': warnings, 'assumptions': ASSUMPTIONS,
        'solver': {'solves': plan.meta['solves'], 'solve_s': plan.meta['total_s'], 'dstar': plan.meta['dstar'],
                   'search': plan.meta['search'], 'budget_hit': plan.meta['budget_hit'],
                   'pool': len(inst.free_agents()), 'seconds': round(time.time() - started, 2)},
    }


_plans = {}                 # (league, week_start, timeframe) -> (made at, payload)
_plans_lock = threading.Lock()
_key_locks = {}


def cached_week_plan(lg, timeframe=None, week_start=None, week_end=None, opponent=None):
    """week_plan, cached PLAN_TTL seconds per (league, week, timeframe); concurrent callers for one key wait for the
    first instead of each building a Week."""
    key = (lg.id, str(week_start), timeframe)
    with _plans_lock:
        lock = _key_locks.setdefault(key, threading.Lock())
    with lock:
        hit = _plans.get(key)
        if hit and time.time() - hit[0] < PLAN_TTL:
            return hit[1]
        result = week_plan(lg, timeframe, week_start, week_end, opponent)
        _plans[key] = (time.time(), result)
        return result


def main(league=None, timeframe=None):
    from leagues import get_league
    from fantasy_team_helper import get_current_fantasy_week_dates
    lg = get_league(league)
    ws, we, opp = get_current_fantasy_week_dates(lg)
    out = week_plan(lg, timeframe, ws, we, opp)
    if not out['supported']:
        print(out['reason'])
        return
    sym = {'add': '+', 'drop': '-', 'il_in': 'IL<', 'il_out': 'IL>'}
    print(f"{lg.id} {out['week_start']}..{out['week_end']} vs {out['opponent']} ({out['opponent_points']:.0f}); "
          f"claims left {out['claims_left']}")
    for d in out['days']:
        txt = '  '.join(f"{sym[x['type']]}{x['player']} ({x['note']})" for x in d['transactions']) or '.'
        print(f"{d['date'][5:]} {'FROZEN' if d['frozen'] else '      '} {txt}")
    print(f"now {out['now']['points']:.0f} FPTS, {out['now']['win_chance']:.1%} -> plan {out['plan']['points']:.0f} "
          f"FPTS, {out['plan']['win_chance']:.1%}; next 2 weeks {out['plan']['keep_total']:+.0f} FPTS of keep value  "
          f"({out['solver']['solves']} solves, {out['solver']['seconds']} s)")
    for w in out['warnings']:
        print('!', w)


if __name__ == '__main__':
    import sys
    main(*sys.argv[1:3])
