"""Daily Leaders: every NBA stat line of a date, live, scored by one league's rules.

Source: ESPN's public site API, one scoreboard call plus one summary per game. cdn.nba.com refuses
this host (403) and stats.nba.com box scores stay empty until well after a game ends, so neither
can be live. ESPN's play-by-play gives what its box score lacks: times blocked (a block play's
first participant is the shooter) and technical fouls.

Throttled: a date is refetched at most every REFRESH_SECONDS, only its unfinished games; a finished
game is kept for the life of the process. A background poller (start_poller) keeps today and last
night's late games current whether or not anyone has the page open, so it is ready when opened,
and starts the nightly season-stats refresh once a night is final (nightly_stats.py).
"""
import re
import threading
import time
from datetime import date, datetime, timedelta
from statistics import mean
from zoneinfo import ZoneInfo

import requests

from leagues import CATEGORY_CATALOG, fantasy_points

ESPN = 'https://site.api.espn.com/apis/site/v2/sports/basketball/nba'
REFRESH_SECONDS = 5 * 60    # a live slate is refetched this often (~0.9 s CPU per 5 games; ~550 ESPN calls on a 15-game night)
IDLE_REFRESH_SECONDS = 3 * 3600  # a slate with nothing started yet (tip-off times can move)
NEAR_TIP_REFRESH_SECONDS = 3600  # ... hourly once the first tip is less than that away
OVERDUE_SECONDS = 2 * 60    # a page request fetches itself when the poller is this late (stalled, machine slept)
MIN_SLEEP, MAX_SLEEP = 30, 3 * 3600  # the poller sleeps until the next thing is due, within these
FORCE_FLOOR_SECONDS = 120   # the Refresh button can't go faster than this
SCALE_SECONDS = 60 * 60     # league pools and the name index change slowly
NBA_TZ = ZoneInfo('America/New_York')  # an NBA "day" is an Eastern-time date

_lock = threading.Lock()
_days = {}    # date -> {'fetched': epoch, 'scoreboard': [...], 'games': {event id: parsed summary}}
_cache = {}   # key -> (epoch, value), for _cached


def _cached(key, build, ttl=SCALE_SECONDS):
    hit = _cache.get(key)
    if hit and time.time() - hit[0] < ttl:
        return hit[1]
    value = build()
    _cache[key] = (time.time(), value)
    return value


def nba_today():
    return datetime.now(NBA_TZ).date()


# ---------------------------------------------------------------- ESPN

def _session():
    """One kept-alive connection, retried with backoff: ESPN drops a TLS handshake now and then
    (SSL EOF on 2 of 6 calls, 2026-10-09)."""
    from requests.adapters import HTTPAdapter
    from urllib3.util.retry import Retry
    session = requests.Session()
    retry = Retry(total=3, backoff_factor=1.0, status_forcelist=(429, 500, 502, 503, 504), allowed_methods=('GET',))
    session.mount('https://', HTTPAdapter(max_retries=retry))
    return session


_http = _session()


def _get(path, **params):
    resp = _http.get(f'{ESPN}/{path}', params=params, timeout=15)
    resp.raise_for_status()
    return resp.json()


def _scoreboard(day):
    """[{id, state, detail, start, teams: [{abbr, score, home, winner}]}] for one date."""
    games = []
    for event in _get('scoreboard', dates=day.strftime('%Y%m%d')).get('events', []):
        comp = event['competitions'][0]
        status = comp['status']['type']
        games.append({
            'id': event['id'],
            'state': status['state'],          # pre | in | post
            # ESPN season type: 1 preseason, 2 regular season, 3 playoffs, 5 play-in
            'preseason': (event.get('season') or {}).get('type') == 1,
            'season_type': (event.get('season') or {}).get('type'),
            'detail': status.get('shortDetail') or status.get('detail'),
            'start': event.get('date'),
            'teams': [{'abbr': c['team']['abbreviation'], 'score': int(c['score']) if c.get('score') else None,
                       'home': c['homeAway'] == 'home', 'winner': c.get('winner')}
                      for c in comp['competitors']],
        })
    return games


def _made_attempted(text):
    made, _, attempted = (text or '0-0').partition('-')
    return int(made or 0), int(attempted or 0)


TECH_RE = re.compile(r'technical foul', re.I)  # not "makes technical free throw"
NOT_PLAYER_TECH_RE = re.compile(r'second|delay|team|coach|bench', re.I)  # defensive 3 seconds etc.


def _summary(game):
    """{espn athlete id: stat line} for one game, from ESPN's summary (box score + play-by-play)."""
    data = _get('summary', event=game['id'])
    winners = {t['abbr']: t['winner'] for t in game['teams']} if game['state'] == 'post' else {}
    teams = [t['abbr'] for t in game['teams']]
    lines = {}
    for team in data.get('boxscore', {}).get('players', []):
        abbr = team['team']['abbreviation']
        block = team['statistics'][0] if team.get('statistics') else None
        if not block:
            continue
        keys = block['names']
        for athlete in block['athletes']:
            if athlete.get('didNotPlay') or not athlete.get('stats'):
                continue
            s = dict(zip(keys, athlete['stats']))
            minutes = int(s.get('MIN') or 0) if str(s.get('MIN', '')).isdigit() else 0
            if not minutes:
                continue
            fgm, fga = _made_attempted(s.get('FG'))
            fg3m, fg3a = _made_attempted(s.get('3PT'))
            ftm, fta = _made_attempted(s.get('FT'))
            num = lambda k: int(str(s.get(k) or 0).lstrip('+') or 0)
            info = athlete['athlete']
            lines[info['id']] = {
                'espn_id': info['id'], 'name': info['displayName'], 'team': abbr,
                'opp': next((t for t in teams if t != abbr), None), 'starter': athlete.get('starter', False),
                'MIN': minutes, 'PTS': num('PTS'), 'REB': num('REB'), 'AST': num('AST'), 'STL': num('STL'),
                'BLK': num('BLK'), 'TOV': num('TO'), 'PF': num('PF'), 'OREB': num('OREB'), 'DREB': num('DREB'),
                'PLUS_MINUS': num('+/-'), 'FGM': fgm, 'FGA': fga, 'FG3M': fg3m, 'FG3A': fg3a, 'FTM': ftm, 'FTA': fta,
                'BLKA': 0, 'TECH': 0, 'W': (1 if winners[abbr] else 0) if abbr in winners else None,
            }
    for play in data.get('plays', []):
        text = play.get('text') or ''
        people = [p.get('athlete', {}).get('id') for p in play.get('participants', [])]
        if not people or people[0] not in lines:
            continue
        if ' blocks ' in text and len(people) >= 2:
            lines[people[0]]['BLKA'] += 1
        elif TECH_RE.search(text) and not NOT_PLAYER_TECH_RE.search(text):
            lines[people[0]]['TECH'] += 1
    for line in lines.values():
        tens = sum(line[k] >= 10 for k in ('PTS', 'REB', 'AST', 'STL', 'BLK'))
        line['DD2'], line['TD3'] = int(tens >= 2), int(tens >= 3)
    return lines


def _started(cur):
    """A game is on or has just ended and isn't stored as final yet."""
    now = datetime.now().astimezone()
    return any(g['state'] == 'in' or (g['state'] == 'post' and g['id'] not in cur['final'])
               or (g['state'] == 'pre' and g['start'] and datetime.fromisoformat(g['start'].replace('Z', '+00:00')) <= now)
               for g in cur['scoreboard'])


def _all_final(cur):
    return bool(cur['scoreboard']) and all(g['state'] == 'post' and g['id'] in cur['final'] for g in cur['scoreboard'])


def _due(cur, floor):
    """Should a cached day be refetched? Never once every game is stored final."""
    if cur is None:
        return True
    if _all_final(cur):
        return False
    return time.time() - cur['fetched'] >= floor


def due_at(cur):
    """Epoch when the poller next refetches a day, or None once every game is final: while a game
    is on, REFRESH_SECONDS after the last fetch; before tip-off, the first tip (or the idle
    recheck, if sooner)."""
    if cur is None:
        return 0.0
    if _all_final(cur):
        return None
    if _started(cur):
        return cur['fetched'] + REFRESH_SECONDS
    tips = [datetime.fromisoformat(g['start'].replace('Z', '+00:00')).timestamp()
            for g in cur['scoreboard'] if g['state'] == 'pre' and g.get('start')]
    # Within IDLE_REFRESH_SECONDS of tip-off, recheck hourly: a game moved earlier shows up within the hour.
    near = tips and min(tips) - time.time() < IDLE_REFRESH_SECONDS
    return min([cur['fetched'] + (NEAR_TIP_REFRESH_SECONDS if near else IDLE_REFRESH_SECONDS)] + tips)


def _polled_days():
    today = nba_today()
    return (today - timedelta(days=1), today)


def slate(day, force=False, poll=False):
    """The date's games and stat lines. The poller owns today and yesterday (refetched at due_at);
    a page request only fetches a day nobody has cached, another day after REFRESH_SECONDS while it
    has unfinished games, today/yesterday when the poller is OVERDUE_SECONDS late (a stalled
    thread or a slept machine can't leave a halftime check empty), or anything with force
    (FORCE_FLOOR_SECONDS)."""
    with _lock:
        cur = _days.get(day)
        if poll:
            stale = cur is None or (due_at(cur) is not None and time.time() >= due_at(cur))
        elif force:
            stale = _due(cur, FORCE_FLOOR_SECONDS)
        else:
            due = due_at(cur) if cur is not None else 0.0
            stale = (cur is None or (day not in _polled_days() and _due(cur, REFRESH_SECONDS))
                     or (day in _polled_days() and due is not None and time.time() > due + OVERDUE_SECONDS))
        if stale:
            games = dict(cur['games']) if cur else {}
            finished = set(cur['final']) if cur else set()
            board = _scoreboard(day)
            for g in board:
                if g['state'] == 'pre' or g['id'] in finished:
                    continue
                try:
                    games[g['id']] = _summary(g)
                except requests.RequestException as e:  # keep its last lines; not final, so retried
                    print(f'daily leaders: game {g["id"]}: {e}')
                    continue
                if g['state'] == 'post':
                    finished.add(g['id'])
                    _fold(day, g, games[g['id']])
            cur = {'fetched': time.time(), 'scoreboard': board, 'games': games, 'final': finished}
            _days[day] = cur
        return cur


def poll_once():
    """One poller pass: today, and yesterday until its late games are final. Returns the epoch the
    next pass is due: the soonest day refetch, stats-refresh check, or Eastern midnight (a new day
    to watch)."""
    import nightly_stats
    wake = []
    for day in _polled_days():
        try:
            cur = slate(day, poll=True)
            nightly_stats.tick(day, cur, on_done=_forget_stats)
            wake += [due_at(cur), nightly_stats.next_check(day)]
        except Exception as e:  # ESPN down or slow: try again soon
            print(f'daily leaders poll {day}: {e}')
            wake.append(time.time() + REFRESH_SECONDS)
    today = nba_today()
    for day in [d for d in _days if d < today - timedelta(days=7)]:
        _days.pop(day, None)  # browsed old dates don't pile up
    midnight = datetime.combine(today + timedelta(days=1), datetime.min.time(), NBA_TZ).timestamp() + 60
    return min([w for w in wake if w is not None] + [midnight])


def _forget_stats():
    """Season stats just changed (nightly_stats): rebuild pools, baselines and scales on next use."""
    for key in [k for k in _cache if k[0] in ('stats', 'by_name', 'scale', 'names')]:
        _cache.pop(key, None)


_poller = None


def start_poller():
    """Run poll_once in a daemon thread (once per process), sleeping until the next thing is due
    (MIN_SLEEP..MAX_SLEEP): a 5-minute rhythm only while games are on, one wake at tip-off,
    otherwise a few a day."""
    global _poller
    if _poller is not None:
        return
    def loop():
        while True:
            try:
                wake = poll_once()
            except Exception as e:
                print(f'daily leaders poller: {e}')
                wake = time.time() + REFRESH_SECONDS
            time.sleep(max(MIN_SLEEP, min(MAX_SLEEP, wake - time.time())))
    _poller = threading.Thread(target=loop, name='daily-leaders-poller', daemon=True)
    _poller.start()


_folds = {}  # NBA date -> {'folded': n, 'skipped': n} from ESPN folds this process


def _fold(day, game, lines):
    """A regular-season game just went final: fold its lines into season totals now (game_log.py),
    so averages don't wait for stats.nba.com. Never raises into the poller."""
    if game.get('season_type') != 2 or not str(game.get('detail') or '').startswith('Final'):
        return
    try:
        from game_log import fold_espn
        from projections import norm_name
        names = _name_index()
        folded, skipped = fold_espn(day, [(names.get(norm_name(l['name'])), {**l, 'game_id': game['id']})
                                          for l in lines.values()])
        tally = _folds.setdefault(day, {'folded': 0, 'skipped': 0})
        tally['folded'] += folded
        tally['skipped'] += skipped
        if folded:
            _forget_stats()
    except Exception as e:
        print(f'daily leaders: fold {game["id"]}: {e}')


MORNING_AFTER_HOUR = 8  # Eastern: the app opens on Daily Leaders until this hour after a game night


def default_tab():
    """'daily' from the day's first tip-off until MORNING_AFTER_HOUR the next morning (Eastern),
    else 'players' (mornings, afternoons before tip-off, days without games). Reads the poller's
    cached slates."""
    now = datetime.now(NBA_TZ)
    today = now.date()
    if any(g['state'] != 'pre' for g in slate(today)['scoreboard']):
        return 'daily'
    yesterday = slate(today - timedelta(days=1))['scoreboard']
    if yesterday and (now.hour < MORNING_AFTER_HOUR or any(g['state'] == 'in' for g in yesterday)):
        return 'daily'
    return 'players'


def default_day():
    """Today (Eastern) once a game has tipped, else yesterday's results."""
    today = nba_today()
    started = any(g['state'] != 'pre' for g in slate(today)['scoreboard'])
    return today if started else today - timedelta(days=1)


# ---------------------------------------------------------------- scoring

def _ratio(cat, line):
    """(rate, attempts) of a ratio category in one stat line."""
    spec = CATEGORY_CATALOG[cat]
    attempts = sum(coef * (line.get(stat) or 0) for stat, coef in spec['attempts'])
    if not attempts:
        return None, 0.0
    made = {'FG%': line['FGM'], 'FT%': line['FTM'], 'EFG%': line['FGM'] + 0.5 * line['FG3M'],
            'TS%': line['PTS'] / 2, 'PPS': line['PTS']}[cat]
    return made / attempts, attempts


def game_value(cat, line):
    """What one stat line puts into category `cat` (ratios: see _ratio)."""
    if cat == 'AST-TOV':
        return line['AST'] - line['TOV']
    if cat == 'NFT':
        return 2 * line['FTM'] - line['FTA']
    if cat == 'WIN%':
        return line['W']
    return line.get(cat)


def league_stats(league):
    """league_player_stats, cached SCALE_SECONDS per league and its settings."""
    from player_stats import league_player_stats
    return _cached(('stats', league.id, str(league.settings)), lambda: league_player_stats(league))


def league_scale(league):
    """{category: (mean, sd, pool rate)} for scoring one game in a category league.

    The mean is the league's scaling pool's per-game average (the same pool as player value,
    calculate_overall_scores). The SD is the SINGLE-GAME noise from the matchup model
    (CATEGORY_CATALOG `noise` / `attempt_sd`, wins as a coin flip), not the spread between players'
    season averages: a game's z then says how far it moved a week's matchup in that category, and
    one double-double or one technical doesn't read as a 3-SD season.
    Uses this season's stats once a pool has qualified, else the projection."""
    from player_stats import SCALING_POOL_FACTOR

    def build():
        stats = league_stats(league)
        n = '' if any(s.get('ELIGIBLE') for s in stats.values()) else '_proj'
        size = round(league.num_teams * league.roster_size * SCALING_POOL_FACTOR)
        pool = sorted((s for s in stats.values() if s.get(f'ELIGIBLE{n}')),
                      key=lambda s: s.get(f'VALUE{n}') or 0, reverse=True)[:size]
        avg = lambda stat: mean((s.get(f'{stat}{n}') or 0) for s in pool) if pool else 0.0
        scale = {}
        for cat in league.categories:
            spec = CATEGORY_CATALOG[cat]
            if spec['kind'] == 'wins':
                q = avg(cat)
                scale[cat] = (q, (q * (1 - q)) ** 0.5, None)
            elif spec['kind'] == 'ratio':
                att = {id(s): sum(c * (s.get(f'{st}{n}') or 0) for st, c in spec['attempts']) for s in pool}
                total = sum(att.values())
                rate = sum((s.get(f'{cat}{n}') or 0) * att[id(s)] for s in pool) / total if total else 0.0
                scale[cat] = (0.0, spec['attempt_sd'] * (total / len(pool)) ** 0.5 if pool else 0.0, rate)
            else:
                var = sum(c * (1.0 if st is None else abs(avg(st))) for st, c in spec['noise'])
                scale[cat] = (avg(cat), var ** 0.5, None)
        return scale
    return _cached(('scale', league.id, str(league.settings)), build)


def score_line(line, league, scale):
    """(value, {category: z}). Points leagues: the league's fantasy points, no z. Category leagues:
    per category (game value - pool mean) / single-game SD, capped at +/-Z_CAP, summed. A ratio
    counts as impact, attempts x (rate - pool rate), as in player value. Wins count once final."""
    from player_stats import Z_CAP
    if league.is_points:
        return fantasy_points(line, league.point_weights), {}
    inverse = set(league.inverse_categories)
    cap = Z_CAP if len(league.categories) > 1 else float('inf')
    zs = {}
    for cat in league.categories:
        mu, sd, pool_rate = scale[cat]
        if pool_rate is not None:
            rate, attempts = _ratio(cat, line)
            value = attempts * (rate - pool_rate) if attempts else 0.0
        else:
            value = game_value(cat, line)
        if value is None or not sd:
            zs[cat] = None
            continue
        sign = -1.0 if cat in inverse else 1.0
        zs[cat] = round(max(-cap, min(cap, sign * (value - mu) / sd)), 2)
    return round(sum(z for z in zs.values() if z is not None), 2), zs


# ---------------------------------------------------------------- signals

PACE_MIN_MINUTES = 6        # no pace call on a shorter stint
PACE_THRESHOLD = 1.5        # |pace| for an arrow (see pace)
MINUTES_UP_RATIO, MINUTES_UP_MIN = 1.25, 5   # minutes flag: 25% and 5 minutes over his usual
STREAK_GAMES = 10
STREAK_POINTS = 8           # last-10 OVR vs season OVR (0-100 display scale, 10 = 1 SD of value)
PACE_SKIP = {'WIN%', 'DD2', 'TD3', 'PLUS_MINUS'}  # team results and thresholds don't pro-rate


def _by_name(league):
    from projections import norm_name
    return _cached(('by_name', league.id, str(league.settings)),
                   lambda: {norm_name(name): st for name, st in league_stats(league).items()})


def pace(line, base, league, scale):
    """How far ahead of his own per-minute norm a player is tonight, in SDs, or None.

    Expected so far = his projected per-game line x (minutes tonight / projected minutes), so a
    hot first quarter counts as hot. Each category is (tonight - expected) / the single-game noise
    for that many minutes (variance grows with minutes, so a short stint needs a bigger surge);
    categories are capped at +/-3 and summed / sqrt(count), about N(0,1) for an ordinary night.
    Points leagues: the same on fantasy points. Baseline: the projection (`_proj`, the only
    timeframe with minutes)."""
    usual = base.get('MIN_proj') or 0
    if line['MIN'] < PACE_MIN_MINUTES or usual < 1:
        return None
    f = line['MIN'] / usual
    get = lambda stat: abs(base.get(f'{stat}_proj') or 0)
    if league.is_points:
        expected = fantasy_points({k: base.get(f'{k}_proj') or 0 for k in league.point_weights}, league.point_weights)
        coef = CATEGORY_CATALOG['FPTS']['noise'][0][1]
        var = coef * abs(expected) * f
        return round((fantasy_points(line, league.point_weights) - expected * f) / var ** 0.5, 2) if var > 0 else None
    inverse = set(league.inverse_categories)
    zs = []
    for cat in league.categories:
        if cat in PACE_SKIP:
            continue
        spec = CATEGORY_CATALOG[cat]
        if spec['kind'] == 'ratio':
            pool_rate = scale[cat][2]
            rate, att = _ratio(cat, line)
            got = att * (rate - pool_rate) if att else 0.0
            att_usual = sum(c * get(st) for st, c in spec['attempts'])
            exp = f * att_usual * ((base.get(f'{cat}_proj') or pool_rate) - pool_rate)
            var = f * att_usual * spec['attempt_sd'] ** 2
        else:
            got = game_value(cat, line)
            exp = f * (base.get(f'{cat}_proj') or 0)
            var = f * sum(c * (1.0 if st is None else get(st)) for st, c in spec['noise'])
        if got is None or var <= 0:
            continue
        sign = -1.0 if cat in inverse else 1.0
        zs.append(max(-3.0, min(3.0, sign * (got - exp) / var ** 0.5)))
    return round(sum(zs) / len(zs) ** 0.5, 2) if zs else None


def signals(line, base, league, scale, streaks_on, preseason=False):
    """{pace, pace_signal, min_usual, minutes_up, streak} for one stat line; base = his stats row."""
    if not base:
        return {'pace': None, 'pace_signal': None, 'min_usual': None, 'minutes_up': False, 'streak': None}
    p = pace(line, base, league, scale)
    usual = base.get('MIN_proj') or 0
    streak = None
    if streaks_on and (base.get('GP') or 0) >= STREAK_GAMES:
        diff = (base.get('SCORE_10') or 0) - (base.get('SCORE') or 0)
        streak = 'hot' if diff >= STREAK_POINTS else 'cold' if diff <= -STREAK_POINTS else None
    return {
        'pace': p,
        'pace_signal': None if p is None else 'up' if p >= PACE_THRESHOLD else 'down' if p <= -PACE_THRESHOLD else None,
        'min_usual': round(usual, 1) if usual else None,
        # Preseason minutes are rotations (starters sit second halves), not roles: no minutes flag.
        'minutes_up': (not preseason and bool(usual) and line['MIN'] >= usual * MINUTES_UP_RATIO
                       and line['MIN'] - usual >= MINUTES_UP_MIN),
        'streak': streak,
    }


# ---------------------------------------------------------------- the page

def _name_index():
    from projections import name_index
    return _cached(('names',), name_index)


def owners(league):
    """{NBA player id: (team abbreviation, team name)} for the league's rostered players."""
    from fantasy_database import FantasyTeam, FantasyTeamPlayer
    rows = (FantasyTeamPlayer.select(FantasyTeamPlayer.player_id, FantasyTeam.abv, FantasyTeam.name)
            .join(FantasyTeam).where(FantasyTeam.league == league.id).tuples())
    return {pid: (abv, name) for pid, abv, name in rows}


def daily_leaders(league, day=None, force=False):
    from projections import norm_name
    day = day or default_day()
    s = slate(day, force=force)
    from player_stats import is_preseason, season_first_game
    scale = None if league.is_points else league_scale(league)
    names, owned, bases = _name_index(), owners(league), _by_name(league)
    streaks_on = not is_preseason()
    states = {t['abbr']: g for g in s['scoreboard'] for t in g['teams']}
    players = []
    for lines in s['games'].values():
        for line in lines.values():
            value, zs = score_line(line, league, scale)
            pid = names.get(norm_name(line['name']))
            team = owned.get(pid)
            game = states.get(line['team'])
            players.append({
                **line, 'player_id': pid, 'value': value, 'z': zs,
                'owner': ('mine' if team[0] == league.my_team else 'taken') if team else 'free',
                'owner_abv': team[0] if team else None, 'owner_name': team[1] if team else None,
                'game_state': game['state'] if game else None,
                'preseason': bool(game and game.get('preseason')),
                **signals(line, bases.get(norm_name(line['name'])), league, scale, streaks_on,
                          preseason=bool(game and game.get('preseason'))),
            })
    players.sort(key=lambda p: p['value'], reverse=True)
    for rank, p in enumerate(players, start=1):
        p['rank'] = rank
    live = any(g['state'] == 'in' for g in s['scoreboard'])
    pending = any(g['state'] != 'post' for g in s['scoreboard'])
    fetched = datetime.fromtimestamp(s['fetched']).astimezone()
    return {
        'date': day.isoformat(), 'today': nba_today().isoformat(),
        'fetched_at': fetched.isoformat(),
        'next_refresh_at': (lambda t: datetime.fromtimestamp(max(t, time.time())).astimezone().isoformat() if t is not None else None)(
            due_at(s) if day in _polled_days() else (s['fetched'] + REFRESH_SECONDS if pending else None)),
        'refresh_seconds': REFRESH_SECONDS, 'live': live,
        'games': s['scoreboard'], 'players': players,
        'scoring': 'points' if league.is_points else 'categories',
        'preseason': any(g.get('preseason') for g in s['scoreboard']),
        'season_start': (lambda d: d.isoformat() if d else None)(season_first_game()),
        'stats_refresh': __import__('nightly_stats').status().get(day.isoformat()),
        'espn_folded': _folds.get(day),
    }
