"""The platform (Yahoo / Fantrax) is the source of truth for my roster; the DB is a cache of it.

Pages load the DB's roster first. The page then calls `/api/roster-sync` (`refresh_my_team`): one platform call
(throttled 60 s per league, one at a time, silent on failure, so a miss leaves the DB data standing) writes Yahoo's /
Fantrax's roster (and Yahoo's IL slots) into the DB. When it changed anything the league's `version` goes up; every
/api response carries `X-Roster-Version`, and a page whose data was loaded under an older version reloads in place
(frontend `useRosterRefresh`). The hourly tasks still run: they cover every other team, free agents, waivers,
positions and the transaction log, and keep the DB warm when nobody has the app open."""
import threading

_lock = threading.Lock()
_versions = {}   # str(league id) -> number of refreshes that changed the DB's roster


def version(league_id):
    return _versions.get(str(league_id), 0)


def refresh_my_team(lg):
    """Refresh my roster from the platform. Returns the change lines ([] = already equal, None = throttled / unreachable /
    not a Yahoo or Fantrax league)."""
    with _lock:   # one platform call at a time: a second caller waits, then hits the throttle
        if lg.platform == 'yahoo':
            import pull_yahoo
            changes = pull_yahoo.sync_my_team(lg)
        elif lg.platform == 'fantrax':
            import pull_fantrax
            changes = pull_fantrax.sync_my_team(lg)
        else:
            return None
        if changes:
            _versions[str(lg.id)] = version(lg.id) + 1
        return changes
