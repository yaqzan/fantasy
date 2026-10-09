"""Nightly season-stats refresh, driven by the Daily Leaders poller (daily_leaders.poll_once).

Once every regular-season game of an NBA day is final (ESPN), `pull_api_data.py --after-games`
runs in its own process: it exits NOT_YET (75) until stats.nba.com's game log holds the whole
night (it lags the final buzzer), then does the full pull (schedule, standings, rosters, techs,
every player's season / last-5 / last-10). Retried every RETRY_SECONDS, given up after GIVE_UP_HOURS.
Preseason nights never run (they aren't in the regular-season stats).
"""
import os
import subprocess
import sys
import time
from datetime import datetime, timedelta

ROOT = os.path.dirname(os.path.abspath(__file__))
LOG = os.path.join(ROOT, 'stats_refresh.log')
RETRY_SECONDS = 30 * 60
GIVE_UP_HOURS = 12
NOT_YET = 75

_runs = {}  # NBA date -> {'proc', 'next', 'first', 'done', 'tries', 'last'}


def _log(msg):
    with open(LOG, 'a', encoding='utf-8') as f:
        f.write(f'{datetime.now():%Y-%m-%d %H:%M:%S} {msg}\n')


def _finals(board):
    """Regular-season games of the day that ended (postponed games never reach the NBA log)."""
    return [g for g in board if not g.get('preseason') and g['state'] == 'post'
            and str(g.get('detail') or '').startswith('Final')]


def _already_refreshed(board):
    """A pull finished after the night's last game could have ended (last tip + 3 h): a restarted
    server doesn't redo the night."""
    from fantasy_database import Player
    from peewee import fn
    starts = [datetime.fromisoformat(g['start'].replace('Z', '+00:00')) for g in board if g.get('start')]
    newest = Player.select(fn.MAX(Player.api_updated_at)).scalar()
    if not starts or newest is None:
        return False
    return newest.astimezone() >= (max(starts) + timedelta(hours=3)).astimezone()


def tick(day, cur, on_done=None):
    """One poller pass for one NBA date's cached slate."""
    board = cur['scoreboard'] if cur else []
    regular = [g for g in board if not g.get('preseason')]
    if not regular or any(g['state'] != 'post' for g in regular):
        return
    run = _runs.get(day)
    if run is None:
        run = _runs[day] = {'proc': None, 'next': 0.0, 'first': time.time(), 'done': False, 'tries': 0, 'last': None}
        if _already_refreshed(board):
            run.update(done=True, last='already refreshed')
    if run['done']:
        return
    proc = run['proc']
    if proc is not None:
        code = proc.poll()
        if code is None:
            return  # still pulling
        run['proc'] = None
        if code == 0:
            run.update(done=True, last='refreshed')
            _log(f'{day}: season stats refreshed (try {run["tries"]})')
            if on_done:
                on_done()
            return
        run['last'] = 'not in the NBA log yet' if code == NOT_YET else f'exit {code}'
        _log(f'{day}: {run["last"]}; retry in {RETRY_SECONDS // 60} min')
        run['next'] = time.time() + RETRY_SECONDS
    if time.time() - run['first'] > GIVE_UP_HOURS * 3600:
        run.update(done=True, last=f'gave up after {GIVE_UP_HOURS} h')
        _log(f'{day}: {run["last"]} ({run["tries"]} tries); run pull_api_data.py by hand')
        return
    if time.time() >= run['next']:
        run['tries'] += 1
        args = [sys.executable, os.path.join(ROOT, 'pull_api_data.py'),
                '--after-games', day.isoformat(), '--games', str(len(_finals(board)))]
        log = open(LOG, 'a', encoding='utf-8')
        log.write(f'{datetime.now():%Y-%m-%d %H:%M:%S} {day}: try {run["tries"]}: {" ".join(args[1:])}\n')
        log.flush()
        env = {**os.environ, 'PYTHONIOENCODING': 'utf-8'}
        run['proc'] = subprocess.Popen(args, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, env=env,
                                       creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        log.close()


def next_check(day):
    """Epoch the poller should look at this night's refresh again, or None: every 2 minutes while
    the pull runs (to catch its exit), else the retry time."""
    run = _runs.get(day)
    if run is None or run['done']:
        return None
    return time.time() + 120 if run['proc'] is not None else run['next']


def status():
    """{date: last outcome} for the API (what the page can show about season stats)."""
    return {d.isoformat(): {'done': r['done'], 'running': r['proc'] is not None, 'tries': r['tries'], 'last': r['last']}
            for d, r in _runs.items()}
