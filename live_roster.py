"""The platform (Yahoo / Fantrax) is the source of truth for my roster; the DB is a cache of it.

Pages load the DB's roster first. The page then calls `/api/roster-sync` (`refresh_my_team`): one platform call
(throttled 60 s per league, one at a time) writes Yahoo's / Fantrax's roster (and Yahoo's IL slots and pickups used)
into the DB. When it changed anything the league's `version` goes up; every /api response carries `X-Roster-Version`,
and a page whose data was loaded under an older version reloads in place (frontend `useRosterRefresh`).

When the platform can't be reached (the home server's login expired, or the site is down) the DB copy stands and the
answer says so (`status`): the page shows a note, and an expired login pushes once through Pharos (`incident`:
re-pushed after 12 h, and "recovered" when a refresh works again). The hourly tasks still run: they cover every other
team, free agents, waivers, positions and the transaction log, and keep the DB warm when nobody has the app open."""
import threading
import time

_lock = threading.Lock()
FAIL_BACKOFF = 60   # seconds a failed refresh is not retried
_versions = {}   # str(league id) -> number of refreshes that changed the DB's roster
_status = {}     # str(league id) -> {'error': None | 'login' | 'down', 'detail': str, 'error_at': epoch}


class SyncFailed(Exception):
    """The platform could not be read (the message is what the platform helper said)."""


def classify(message):
    """'login' when the platform helper says the saved login is no good (Yahoo: 'says not logged in'; Fantrax: a page error,
    which its helper blames on the login, or no Firefox cookies), else 'down'. Any other text, even one that mentions
    'sign in' in a returned HTML page, is 'down'."""
    m = str(message).lower()
    return 'login' if any(w in m for w in ('not logged in', 'log in to fantrax.com')) else 'down'


def version(league_id):
    return _versions.get(str(league_id), 0)


def status(league_id):
    return dict(_status.get(str(league_id)) or {'error': None, 'detail': ''})


def _incident(lg, failing):
    """One Pharos incident per PLATFORM (two Fantrax leagues share the one Firefox login: one page, not one per league).
    Called with failing=True on a login failure and failing=False after every good refresh (Pharos's contract: it can only
    send 'recovered' if it hears the all-clear, and it ignores the call when nothing was failing)."""
    try:   # a push is a courtesy: never let it break a refresh
        import pharos
        pharos.incident(f'{lg.platform}-login', {f'{lg.platform} login': 'saved login expired'} if failing else {},
                        source='fantasy', noun='login')
    except Exception as e:
        print(f'roster refresh: pharos: {e}')


def refresh_my_team(lg):
    """Refresh my roster from the platform. Returns the change lines ([] = already equal, None = throttled / failed /
    not a Yahoo or Fantrax league); `status(lg.id)` says whether the last attempt failed and why."""
    key = str(lg.id)
    with _lock:   # one platform call at a time: a second caller waits, then hits the throttle
        bad = _status.get(key)
        if bad and bad['error'] and time.time() - bad.get('error_at', 0) < FAIL_BACKOFF:
            return None   # it just failed: don't hammer a dead login on every page open
        try:
            if lg.platform == 'yahoo':
                import pull_yahoo
                changes = pull_yahoo.sync_my_team(lg)
            elif lg.platform == 'fantrax':
                import pull_fantrax
                changes = pull_fantrax.sync_my_team(lg)
            else:
                return None
        except SyncFailed as e:
            kind = classify(e)
            _status[key] = {'error': kind, 'detail': str(e)[:200], 'error_at': time.time()}
            if kind == 'login':
                _incident(lg, True)
            return None
        if changes is None:   # throttled, or nothing to compare: no news either way
            return None
        _status[key] = {'error': None, 'detail': ''}
        _incident(lg, False)   # every good refresh: survives a restart or a 'down' between the failure and the recovery
        if changes:
            _versions[key] = version(key) + 1
        return changes
