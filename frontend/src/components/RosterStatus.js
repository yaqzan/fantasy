import React, { useEffect, useState } from 'react';
import { getSelectedLeague, syncRoster } from '../services/api';

// One quiet line when my roster could not be refreshed from the platform (the home server's saved login expired, or the
// site is down): the page is showing the last synced copy. Nothing renders while refreshes work (live_roster.status).
const RosterStatus = () => {
  const [status, setStatus] = useState(null);
  useEffect(() => {
    let cancelled = false;
    syncRoster(getSelectedLeague()).then(answer => { if (!cancelled) setStatus(answer?.status || null); });
    return () => { cancelled = true; };
  }, []);
  if (!status || !status.error) return null;
  return (
    <p className="text-xs text-amber-400 mb-2" title={status.detail}>
      {status.error === 'login'
        ? "The server's saved login expired: this roster is the last synced copy (log in again in Firefox)."
        : "Couldn't reach the league site: this roster is the last synced copy."}
    </p>
  );
};

export default RosterStatus;
