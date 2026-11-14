import { useEffect, useRef } from 'react';
import { getRosterVersion, syncRoster } from './services/api';

// A page loads the DB's roster first. The refresh of MY roster from Yahoo / Fantrax (one call per league per minute,
// shared by every page and by RosterStatus, which may start it at mount) is compared once the page's data is in
// (`ready`): `onChange` runs when the refresh changed the roster after that data was loaded, so the page reloads in
// place. A failed refresh does nothing.
// The refresh is started once per league and its answer is compared whenever the page is ready: a page that blanks and
// reloads while the call is in flight (week switch, Refresh) is still compared against the version its new data came under.
export default function useRosterRefresh(leagueId, ready, onChange) {
  const loadedAt = useRef(null);   // the roster version the page's data was loaded under
  const sync = useRef({ league: null, promise: null, checked: false });
  const change = useRef(onChange);
  change.current = onChange;
  useEffect(() => {
    if (!ready) { loadedAt.current = null; return undefined; }
    if (loadedAt.current === null) loadedAt.current = getRosterVersion(leagueId);
    const s = sync.current;
    if (s.league !== leagueId) { s.league = leagueId; s.promise = syncRoster(leagueId); s.checked = false; }
    if (s.checked) return undefined;
    let cancelled = false;
    const at = loadedAt.current;
    s.promise.then(answer => {
      if (cancelled) return;   // the page went away or reloaded: the next ready compares again
      s.checked = true;
      if (answer && answer.version !== at) { loadedAt.current = null; change.current(); }
    });
    return () => { cancelled = true; };
  }, [leagueId, ready]);
}
