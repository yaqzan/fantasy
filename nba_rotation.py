"""Rotation / injury opportunity: for every player whose team plays tonight, how likely he is to play,
the minutes he gets if he does, and how much of that comes from teammates who are out.

Source: the NBA's daily lineups JSON (stats.nba.com/js/data/leaders/00_daily_lineups_YYYYMMDD.json): every
rostered player Active / Inactive, starters, lineupStatus Expected / Confirmed. Persisted in nba_lineups
(game_lines holds only games played, so "Active but did not play" and "started" live there).
Model: rotation_model.json, fit by rotation_fit.py on 2025-26. Findings and the backtest: .claude/docs/rotation.md.

Never fetches in a request: a background thread (start_poller) builds the whole-NBA state and swaps it in
whole; /fantasy reads `get_state()["players"].get(player_id)`.
"""
import json
import math
import threading
import time
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

import requests

MODEL_PATH = Path(__file__).parent / 'rotation_model.json'
URL = 'https://stats.nba.com/js/data/leaders/00_daily_lineups_{}.json'
HEADERS = {'User-Agent': 'Mozilla/5.0', 'Referer': 'https://www.nba.com/'}
NORM = {'NO': 'NOP', 'NY': 'NYK', 'WSH': 'WAS', 'GS': 'GSW', 'SA': 'SAS', 'PHO': 'PHX', 'BRK': 'BKN', 'CHO': 'CHA', 'UTAH': 'UTA'}
WINDOW = 10            # baseline = mean of his last WINDOW played games ...
PRIOR_N = 4            # ... with last season's mpg counting as this many games
OUT_MIN = 10.0         # an Inactive player with this baseline frees minutes
NEW_WITHIN = 3         # a NEW absence: Active in one of the team's previous NEW_WITHIN games
HISTORY_DAYS = 250     # how far back game_lines / nba_lineups are read (a whole season: a player back from a long injury keeps his games)
GROUP = {'PG': 'G', 'SG': 'G', 'G': 'G', 'SF': 'W', 'F': 'W', 'PF': 'B', 'C': 'B', 'FC': 'B', 'GF': 'W'}
# Yahoo status -> assumed chance he plays (same table the optimizer uses; not calibrated)
DAY_TO_DAY_CHANCE = {'P': 0.9, 'Q': 0.5, 'DTD': 0.5, 'GTD': 0.5, 'D': 0.2}
OUT_STATUSES = ('O', 'INJ')
FAST_REFRESH, EMPTY_REFRESH, SLOW_REFRESH = 10 * 60, 20 * 60, 60 * 60
STATE_MAX_AGE = 3 * 3600   # a state older than this is not served (the poller is stuck)
RATE_PER_10 = 0.75     # % lift in FPTS per minute per 10 freed minutes of new absences (2025-26 fit, rate_fit in rotation.md); no position term
OPP_CAP = 6.0          # minutes: the fit rarely saw more than ~60 freed minutes at once, so a gutted roster is not extrapolated

_lock = threading.Lock()
_state = {'as_of': None, 'day': None, 'players': {}}
_poller = None


def norm_team(t):
    return NORM.get(t, t)


def load_model():
    return json.load(open(MODEL_PATH))


# ---------------------------------------------------------------- NBA lineups

def fetch_day(d):
    """The day's games from the NBA JSON: [] = nothing published (no games, or not yet); None = could not be read
    (a 403 is a block, not an empty day)."""
    try:
        r = requests.get(URL.format(f'{d:%Y%m%d}'), headers=HEADERS, timeout=20, allow_redirects=False)
        if r.status_code in (301, 302, 404):   # the NBA redirects a day whose file is not published (yet)
            return []
        r.raise_for_status()
        return r.json().get('games', [])
    except Exception as e:
        print(f'rotation: lineups {d}: {e}')
        return None


def store_day(d, games):
    """Upsert a day's regular-season lineups (gameId 002...). Returns rows written."""
    from fantasy_database import DB, NbaLineup
    rows = []
    for g in games:
        if not str(g.get('gameId', '')).startswith('002'):
            continue
        for side in ('homeTeam', 'awayTeam'):
            t = g[side]
            for p in t['players']:
                rows.append({'game_id': g['gameId'], 'player_id': p['personId'], 'game_date': d,
                             'team': norm_team(t['teamAbbreviation']), 'active': p['rosterStatus'] == 'Active',
                             'starter': bool(p['position']), 'lineup_status': p.get('lineupStatus') or None,
                             'game_status': g.get('gameStatus') or 1, 'updated_at': datetime.now()})
    with DB.atomic():
        for i in range(0, len(rows), 500):
            NbaLineup.replace_many(rows[i:i + 500]).execute()
    return len(rows)


def backfill(season_start=None):
    """Fetch the lineups of every played day this season that nba_lineups lacks (once per missing day)."""
    from fantasy_database import GameLine
    from projections import season_label
    from fantasy_database import NbaLineup
    have = {r.game_date for r in NbaLineup.select(NbaLineup.game_date).distinct()}
    days = sorted({r.game_date for r in GameLine.select(GameLine.game_date).where(GameLine.season == season_label()).distinct()})
    n = 0
    for d in days:
        if d in have or (season_start and d < season_start):
            continue
        games = fetch_day(d)
        if games:
            n += store_day(d, games)
        time.sleep(0.5)
    return n


# ---------------------------------------------------------------- context (history, from the database)

class Context:
    """Everything the model reads about the past, loaded once per refresh for games on `day`."""

    def __init__(self, day):
        from fantasy_database import GameLine, NbaLineup, Player, PlayerSeason
        from projections import season_label
        since = day - timedelta(days=HISTORY_DAYS)
        season = season_label()
        prev = f'{int(season[:4]) - 1}-{season[2:4]}'
        minutes = defaultdict(list)           # pid -> [(date, min)] played games
        for r in GameLine.select(GameLine.player_id, GameLine.game_date, GameLine.min).where(
                (GameLine.season == season) & (GameLine.game_date < day) & (GameLine.game_date >= since)).order_by(GameLine.game_date):
            if (r.min or 0) > 0:
                minutes[r.player_id].append((r.game_date, r.min))
        self.minutes = minutes
        played = {(pid, d) for pid, v in minutes.items() for d, _ in v}
        self.prior = {r.player_id: r.min / r.gp for r in PlayerSeason.select().where(PlayerSeason.season == prev) if r.gp and r.gp >= 10}
        act_hist = defaultdict(list)          # pid -> [(date, played?, starter?)] games he was Active, oldest first
        team_games = defaultdict(lambda: defaultdict(set))   # team -> date -> pids who PLAYED (the sheet lists long-term injured players Active)
        for r in NbaLineup.select().where((NbaLineup.game_date < day) & (NbaLineup.game_date >= since)).order_by(NbaLineup.game_date):
            if r.active:
                did = (r.player_id, r.game_date) in played
                act_hist[r.player_id].append((r.game_date, did, r.starter))
                if did:
                    team_games[r.team][r.game_date].add(r.player_id)
        self.act_hist = act_hist
        self.recent_played = {t: [d[k] for k in sorted(d)[-NEW_WITHIN:]] for t, d in team_games.items()}
        self.groups = {}
        self.names = {}
        self.injury = {}
        for p in Player.select(Player.id, Player.name, Player.pos, Player.positions, Player.injury_status):
            first = (p.positions or p.pos or '').replace('/', ',').split(',')[0].strip()
            self.groups[p.id] = GROUP.get(first)
            self.names[p.id] = p.name
            if p.injury_status:
                self.injury[p.id] = p.injury_status

    def base(self, pid):
        h = [m for _, m in self.minutes.get(pid, ())[-WINDOW:]]
        pr = self.prior.get(pid)
        if pr is None:
            return sum(h) / len(h) if len(h) >= 3 else None
        return (pr * PRIOR_N + sum(h)) / (PRIOR_N + len(h))

    def dnp6(self, pid):
        h = self.act_hist.get(pid, ())[-6:]
        return 1 - sum(1 for _, pl, _ in h if pl) / len(h) if h else 0.0

    def started_recently(self, pid):
        """(games started, games Active) over his last 5 Active games."""
        h = self.act_hist.get(pid, ())[-5:]
        return sum(1 for _, _, s in h if s), len(h)


# ---------------------------------------------------------------- the model

def _sigmoid(x):
    return 1 / (1 + math.exp(-x))


def compute_team(team, pl, ctx, model):
    """pl: {pid: (active, starter, lineup_status)} for one team-game -> {pid: dict}. Pure given ctx/model.
    Lineup not posted (no starters yet) -> {}."""
    if not any(s for _, s, _ in pl.values()):
        return {}
    pm, mm = model['pplay'], model['mif']
    inj = ctx.injury
    base = {p: ctx.base(p) for p in pl}
    chance = {}   # doubtful (not Confirmed, Yahoo day-to-day): chance he plays
    for p, (a, s, ls) in pl.items():
        if a and (ls != 'Confirmed' or not s) and inj.get(p) in DAY_TO_DAY_CHANCE:   # a Confirmed sheet lists Q/D bench players too
            chance[p] = DAY_TO_DAY_CHANCE[inj[p]]
    active = {p for p, (a, s, ls) in pl.items() if a and inj.get(p) not in OUT_STATUSES}
    recent = set().union(*ctx.recent_played.get(team, [set()]))
    freed, newfree, same = 0.0, 0.0, defaultdict(float)   # minutes freed (all), NEW absences /10, by group /10
    names = []
    for p in pl:
        b = base[p]
        if not b or b < OUT_MIN:
            continue
        w = 1.0 if p not in active else (1 - chance[p] if p in chance else 0.0)
        if w <= 0:
            continue
        freed += b * w
        if p in recent:
            newfree += b * w / 10
            g = ctx.groups.get(p)
            if g:
                same[g] += b * w / 10
            names.append((b * w, ctx.names.get(p, str(p))))
    out_names = [n for _, n in sorted(names, reverse=True)[:4]]
    res, exp_raw = {}, {}
    for p, (a, s, ls) in pl.items():
        b = base[p]
        if p not in active:
            res[p] = {'p': 0.0, 'inactive': True}
            continue
        if b is None:
            continue
        x = (pm['intercept'] + pm['coef'][0] * b + pm['coef'][1] * s + pm['coef'][2] * ctx.dnp6(p)
             + pm['coef'][3] * freed / 48 + pm['coef'][4] * len(active))
        pp = _sigmoid(x) * chance.get(p, 1.0)
        g = ctx.groups.get(p)
        opp = min(newfree * (mm['new_starter'] if s else mm['new_bench']) + (same[g] * mm['same_group'] if g else 0.0), OPP_CAP)
        mif = b + mm['intercept'] + mm['starter'] * s + opp
        st5, n5 = ctx.started_recently(p)
        res[p] = {'p': round(pp, 2), 'mif': round(max(mif, 0), 1), 'base': round(b, 1), 'opp': round(opp, 1),
                  'rate_pct': round(RATE_PER_10 * min(newfree, OPP_CAP), 2),
                  'starter': bool(s), 'promoted': bool(s and n5 >= 3 and st5 <= 1), 'confirmed': ls == 'Confirmed',
                  'out': out_names}
        exp_raw[p] = b * pp
    # the validated expected minutes: P(play) x baseline, shared out over the 240 team minutes, starters tilted
    tilt = {p: exp_raw[p] * (1 + model['gamma'] * pl[p][1]) for p in exp_raw}
    tot = sum(tilt.values()) or 1
    a = model['alpha']
    for p in exp_raw:
        res[p]['exp'] = round(min((1 - a) * exp_raw[p] + a * 240 * tilt[p] / tot, 40.0), 1)
    return res


def compute_day(day, games, ctx=None, model=None):
    """{pid: dict} for every team-game of the day (games: the lineups JSON 'games')."""
    ctx = ctx or Context(day)
    model = model or load_model()
    out = {}
    sheet, teams = {}, []
    for g in games:
        if not str(g.get('gameId', '')).startswith('002'):
            continue
        for side in ('homeTeam', 'awayTeam'):
            t = g[side]
            pl = {p['personId']: (p['rosterStatus'] == 'Active', bool(p['position']), p.get('lineupStatus')) for p in t['players']}
            team = norm_team(t['teamAbbreviation'])
            if any(s for _, s, _ in pl.values()):   # lineup posted
                teams.append(team)
                sheet.update({p: (a, s, ls == 'Confirmed') for p, (a, s, ls) in pl.items()})
            for pid, v in compute_team(team, pl, ctx, model).items():
                v['game_id'], v['game_status'], v['team'] = g['gameId'], g.get('gameStatus') or 1, team
                out[pid] = v
    role_opp(day, sheet, teams, out)
    return out


ROLE_OPP_CAP = 10.0   # minutes shown either way


def role_opp(day, sheet, teams, out):
    """Replace the shipped injury terms (`opp`, inside `mif`) with the role-aware model's delta for tonight
    (role_minutes: who inherits an absent teammate's minutes, return dates; .claude/docs/rotation.md "Role-aware
    minutes"). Adds `rm_exp` (its minutes if he plays), `why` (one line), `back` (that teammate's ESPN return date).
    Model unavailable = the shipped numbers stay. Replaces `mif` with the role model's minutes too."""
    if not teams:
        return
    try:
        import role_minutes
        rm = role_minutes.tonight_day(day, sheet, teams)
    except Exception as e:
        print(f'rotation: role minutes {e}')
        return
    for pid, v in out.items():
        r = rm.get(pid)
        if v.get('inactive') or r is None or v.get('base') is None:
            continue
        # Opp = the optimizer's delta (vs what the projection carries); mif = the role model's own minutes, which beat
        # the shipped mif on the 10-27..11-02 replay (MAE 4.54 vs 4.69, baseline 5.01; base + shipped terms + this
        # delta was 4.79, so the two are not added)
        v['opp'] = round(max(-ROLE_OPP_CAP, min(ROLE_OPP_CAP, r['delta']['_projected'])), 1)
        v['mif'] = r['exp']
        v['rm_exp'] = r['exp']
        v['why'] = r.get('why') or ''
        v['back'] = r.get('back')
        if r.get('reason'):
            v['out'] = [n for n, _, _ in r['reason']]


# ---------------------------------------------------------------- state + poller

def get_state():
    return _state


def current(today, st=None):
    """The state's players when it is fresh (built within STATE_MAX_AGE) and for `today` or later, else {}."""
    st = st or _state
    if not st['as_of'] or not st['day'] or st['day'] < today.isoformat():
        return {}
    if (datetime.now() - datetime.fromisoformat(st['as_of'])).total_seconds() > STATE_MAX_AGE:
        return {}
    return st['players']


def tonight_doubtful(doubtful, today):
    """The optimizer's {name: chance he plays his next game} with the Yahoo guess dropped for a player the NBA
    sheet CONFIRMS as tonight's starter (game not started). Removal only: a 0.0 for an Inactive player would land on
    the wrong day for free agents / IL activations (the factor sits on the first game after the add day), see
    lineup-optimizer.md. No state (CLI runs, stale, other day) = Yahoo's dict unchanged."""
    st = _state   # one snapshot: the poller swaps the whole dict
    players = current(today, st)
    if not players or st['day'] != today.isoformat():
        return doubtful
    names = st.get('names', {})
    drop = {names[pid] for pid, v in players.items()
            if v.get('game_status') == 1 and v.get('starter') and v.get('confirmed') and names.get(pid) in doubtful}
    return {n: c for n, c in doubtful.items() if n not in drop} if drop else doubtful


def log_picks(day, players, ctx):
    """Keep what we said before tip-off (rows for games that have not started), to score later."""
    from fantasy_database import DB, RotationPick
    rows = [{'game_date': day, 'player_id': pid, 'team': v['team'], 'p_play': v['p'], 'base': v.get('base'), 'mif': v.get('mif'),
             'opp': v.get('opp'), 'rate_pct': v.get('rate_pct'), 'exp': v.get('exp'), 'starter': v.get('starter', False),
             'lineup_status': 'Confirmed' if v.get('confirmed') else 'Expected', 'injury_status': ctx.injury.get(pid),
             'logged_at': datetime.now()} for pid, v in players.items() if v['game_status'] == 1]
    if rows:
        with DB.atomic():
            for i in range(0, len(rows), 500):
                RotationPick.replace_many(rows[i:i + 500]).execute()


def refresh(today=None):
    """Fetch the next slate, store it, rebuild the state. Returns seconds until the next refresh is due."""
    global _state
    from daily_leaders import nba_today
    today = today or nba_today()
    for d in (today, today + timedelta(days=1)):
        games = fetch_day(d)
        if games is None:
            return FAST_REFRESH       # unreadable: keep the old state (only if it is the same day, see get_state users)
        games = [g for g in games if str(g.get('gameId', '')).startswith('002')]
        if games and any(g.get('gameStatus') != 3 for g in games):
            break
    else:
        games, d = [], today
    if not games:
        with _lock:
            _state = {'as_of': datetime.now().isoformat(timespec='seconds'), 'day': d.isoformat(), 'players': {}}
        return EMPTY_REFRESH
    store_day(d, games)
    ctx = Context(d)
    players = compute_day(d, games, ctx)
    log_picks(d, players, ctx)
    with _lock:
        _state = {'as_of': datetime.now().isoformat(timespec='seconds'), 'day': d.isoformat(), 'players': players,
                  'names': {pid: ctx.names[pid] for pid in players if pid in ctx.names}}
    return FAST_REFRESH if any(g.get('gameStatus') != 3 for g in games) else SLOW_REFRESH


def start_poller():
    """Backfill missing days, then refresh on a timer in a daemon thread (once per process)."""
    global _poller
    if _poller is not None:
        return

    def loop():
        try:
            backfill()
        except Exception as e:
            print(f'rotation backfill: {e}')
        while True:
            try:
                import injury_reports   # ESPN return dates for role_minutes: at most every 3 h, 6 h cool-down on a block
                injury_reports.maybe_snapshot()
            except Exception as e:
                print(f'rotation poller injuries: {e}')
            try:
                wait = refresh()
            except Exception as e:
                print(f'rotation poller: {e}')
                wait = FAST_REFRESH
            try:
                import role_minutes     # rest-of-season minutes deltas: hourly, or when the day / game lines change
                role_minutes.refresh_ros()
            except Exception as e:
                print(f'rotation poller ros: {e}')
            try:
                import depth_charts     # data only (weight 0 until scored forward): once per 20 h, 30 calls 1 s apart, after the refresh so it never delays a lineup
                depth_charts.maybe_snapshot()
            except Exception as e:
                print(f'rotation poller depth charts: {e}')
            finally:
                from fantasy_database import DB
                if not DB.is_closed():
                    DB.close()   # this thread reconnects next round (a MySQL restart would otherwise kill it)
            time.sleep(wait)
    _poller = threading.Thread(target=loop, name='rotation-poller', daemon=True)
    _poller.start()
