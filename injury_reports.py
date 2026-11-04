"""ESPN's public NBA injuries feed, snapshotted into `injury_reports` so return-date estimates can be scored later.

Feed: site.api.espn.com/apis/site/v2/sports/basketball/nba/injuries (a browser User-Agent; one ~1 MB call for the
whole league). Every injured player carries status Out / Day-To-Day and `details.returnDate`; quality is mixed
(.claude/docs/rotation.md "Return dates"): day-to-day entries hold a next-day placeholder, "week-to-week" ~7 days,
long ones ("re-evaluated in two weeks", surgery) look like real estimates. `quality()` sorts them.

One row per (snapshot day, ESPN athlete id): the poller (nba_rotation.start_poller) calls `maybe_snapshot()` every
round and it fetches at most every SNAPSHOT_EVERY; a 403/429 is a block: no fetch for BLOCK_COOLDOWN.
`latest()` is what role_minutes reads (CLI runs too: it is the database, not poller state).
`python injury_reports.py` takes a snapshot now; `python injury_reports.py score` -> injury_score.py.
"""
import re
import time
from datetime import date, datetime, timedelta

import requests
from zoneinfo import ZoneInfo

NBA_TZ = ZoneInfo('America/New_York')   # same Eastern day as daily_leaders.NBA_TZ

URL = 'https://site.api.espn.com/apis/site/v2/sports/basketball/nba/injuries'
HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36',
           'Accept': 'application/json'}
ESPN_TEAM = {'NO': 'NOP', 'NY': 'NYK', 'WSH': 'WAS', 'GS': 'GSW', 'SA': 'SAS', 'UTAH': 'UTA', 'PHO': 'PHX', 'BRK': 'BKN', 'CHO': 'CHA'}
SNAPSHOT_EVERY = 3 * 3600       # seconds between fetches (the feed changes a few times a day)
BLOCK_COOLDOWN = 6 * 3600       # after a 403/429
LONG_DAYS = 7                   # a stated absence this long or longer is a real estimate ("long")
LONG_WORDS = re.compile(r'week|surgery|re-?evaluat|indefinite|season|month|fracture|torn|tear|sprain', re.I)

_state = {'last': 0.0, 'blocked_until': 0.0}


def fetch():
    """The feed's injury entries as dicts, or None when it can't be read (a block starts the cooldown)."""
    try:
        r = requests.get(URL, headers=HEADERS, timeout=30)
        if r.status_code in (403, 429):
            _state['blocked_until'] = time.time() + BLOCK_COOLDOWN
            print(f'injury_reports: ESPN {r.status_code}, cooling down {BLOCK_COOLDOWN // 3600} h')
            return None
        r.raise_for_status()
        teams = r.json().get('injuries', [])
    except Exception as e:
        print(f'injury_reports: {e}')
        return None
    out = []
    for t in teams:
        for i in t.get('injuries', []):
            a = i.get('athlete') or {}
            m = re.search(r'/id/(\d+)/', ' '.join(l.get('href', '') for l in a.get('links', [])))
            if not m:
                continue
            det = i.get('details') or {}
            team = (a.get('team') or {}).get('abbreviation')
            out.append({'espn_id': int(m.group(1)), 'name': a.get('displayName') or '', 'team': ESPN_TEAM.get(team, team),
                        'status': i.get('status') or '', 'fantasy_status': (det.get('fantasyStatus') or {}).get('abbreviation'),
                        'return_date': _date(det.get('returnDate')), 'injury_type': (det.get('type') or '')[:32] or None,
                        'detail': (det.get('detail') or '')[:64] or None, 'side': (det.get('side') or '')[:16] or None,
                        'comment': (i.get('shortComment') or '')[:500] or None, 'reported': _datetime(i.get('date'))})
    return out


def _date(s):
    try:
        return date.fromisoformat(s[:10]) if s else None
    except ValueError:
        return None


def _datetime(s):
    try:
        # ESPN stamps UTC; the app's days are Eastern (an evening note belongs to that evening's date)
        return datetime.fromisoformat(s.replace('Z', '+00:00')).astimezone(NBA_TZ).replace(tzinfo=None) if s else None
    except ValueError:
        return None


def store(entries, day=None):
    """Upsert one snapshot (rows for `day`, default today ET). Names match players via norm_name. Returns rows."""
    from fantasy_database import DB, InjuryReport
    from projections import name_index, norm_name
    from daily_leaders import nba_today
    day = day or nba_today()
    index = name_index()
    now = datetime.now()
    rows = [{'snapshot_date': day, 'espn_id': e['espn_id'], 'player_id': index.get(norm_name(e['name'])), 'name': e['name'][:64],
             'team': e['team'], 'status': e['status'][:16], 'fantasy_status': (e['fantasy_status'] or '')[:8] or None,
             'return_date': e['return_date'], 'injury_type': e['injury_type'], 'detail': e['detail'], 'side': e['side'],
             'comment': e['comment'], 'reported': e['reported'], 'source': 'espn', 'fetched_at': now} for e in entries]
    with DB.atomic():
        for i in range(0, len(rows), 200):
            InjuryReport.replace_many(rows[i:i + 200]).execute()
    return len(rows)


def maybe_snapshot(force=False):
    """Fetch + store when due (SNAPSHOT_EVERY) and not cooling down after a block. Returns rows written or 0."""
    now = time.time()
    if not force and (now < _state['blocked_until'] or now - _state['last'] < SNAPSHOT_EVERY):
        return 0
    _state['last'] = now
    entries = fetch()
    return store(entries) if entries else 0


def quality(row):
    """'long' = a real estimate (stated absence >= LONG_DAYS from the report, or the note says weeks / surgery /
    re-evaluated), 'short' = day-to-day / next-day placeholder / a few days, None = no date."""
    if not row.get('return_date'):
        return None
    rep = (row.get('reported') or datetime.combine(row['snapshot_date'], datetime.min.time())).date()
    if (row['return_date'] - rep).days >= LONG_DAYS or (row.get('status') == 'Out' and LONG_WORDS.search(row.get('comment') or '')):
        return 'long'
    return 'short'


def latest(today=None, max_age_days=2):
    """{player_id: row dict + 'quality'} from the newest snapshot at most `max_age_days` old (none = {})."""
    from fantasy_database import InjuryReport
    from daily_leaders import nba_today
    today = today or nba_today()
    from peewee import fn
    day = (InjuryReport.select(fn.MAX(InjuryReport.snapshot_date))
           .where(InjuryReport.snapshot_date <= today, InjuryReport.snapshot_date >= today - timedelta(days=max_age_days)).scalar())
    if not day:
        return {}
    # only the newest fetch of that day: the upsert never deletes, so a player ESPN cleared since would linger as Out
    fetched = InjuryReport.select(fn.MAX(InjuryReport.fetched_at)).where(InjuryReport.snapshot_date == day).scalar()
    out = {}
    for r in InjuryReport.select().where(InjuryReport.snapshot_date == day, InjuryReport.fetched_at == fetched,
                                         InjuryReport.player_id.is_null(False)).dicts():
        r['quality'] = quality(r)
        out[r['player_id']] = r
    return out


if __name__ == '__main__':
    import sys
    if sys.argv[1:2] == ['score']:
        import injury_score
        injury_score.main()
    else:
        print('rows', maybe_snapshot(force=True))
