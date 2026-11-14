import { useEffect, useRef } from 'react';
import { getRosterVersion, syncRoster } from './services/api';

// A page loads the DB's roster first. Once its data is in (`ready`), this asks the backend to refresh MY roster from
// Yahoo / Fantrax (one call per league per minute, shared by every page) and calls `onChange` when the refresh
// changed it after the page's data was loaded, so the page reloads in place. A failed refresh does nothing.
export default function useRosterRefresh(leagueId, ready, onChange) {
  const loadedAt = useRef(null);   // the roster version the page's data was loaded under
  const done = useRef(null);       // the league this page already refreshed for
  const change = useRef(onChange);
  change.current = onChange;
  useEffect(() => {
    if (!ready) { loadedAt.current = null; return undefined; }
    if (loadedAt.current === null) loadedAt.current = getRosterVersion();
    if (done.current === leagueId) return undefined;
    done.current = leagueId;
    let cancelled = false;
    syncRoster(leagueId).then(version => {
      if (!cancelled && version !== null && version !== loadedAt.current) { loadedAt.current = null; change.current(); }
    });
    return () => { cancelled = true; };
  }, [leagueId, ready]);
}
