import React from 'react';
import useLeagueViewState from '../useLeagueViewState';
import { PlayerName } from './PlayerCard';
import OwnerChip from './OwnerChip';

// Tonight: who plays well tonight, built for a phone. Every player whose team has a posted NBA lineup carries a
// `rotation` payload (nba_rotation.py + role_minutes.py): his chance to play (p), minutes if he plays (mif) against his
// usual (base), the change against what his projection carries (opp), and in points leagues the expected FPTS if he
// plays (fpts) and the gain over his projection (gain), plus a one-line reason (why: "Duren out (back ~Nov 9): +8 min").
// `surge` (role_minutes.surges, any player): last 3 games' minutes vs his earlier games, the cause and how much usually holds.
// Ranked by expected FPTS x chance to play (points) or by the minutes change (categories). A * = lineup not confirmed.
const checkboxClass = 'h-4 w-4 text-nba-orange focus:ring-nba-orange border-gray-600 rounded bg-gray-700';
const LIMIT = 60;
const sign = (n, d = 1) => `${n > 0 ? '+' : ''}${n.toFixed(d)}`;

const TonightPickups = ({ players, config }) => {
  const points = config.capabilities?.scoring === 'points';
  const [view, setView] = useLeagueViewState(config.league?.id, 'tonight', { freeOnly: true, likely: true, sort: points ? 'expected' : 'minutes' });
  const mineAbv = config.MY_TEAM_ABV;
  const rows = players.filter(p => p.rotation && !p.rotation.inactive && !p.is_injured);
  const asOf = config.rotation_as_of?.slice(11, 16);
  const key = (p) => (view.sort === 'minutes' || !points ? p.rotation.opp
    : view.sort === 'gain' ? p.rotation.gain
      : p.rotation.fpts * p.rotation.p);
  const shown = rows
    .filter(p => !view.freeOnly || (!p.drafted && p.fantasy_team?.abbreviation !== mineAbv))
    .filter(p => !view.likely || p.rotation.p >= 0.8)
    .filter(p => key(p) != null)
    .sort((a, b) => key(b) - key(a))
    .slice(0, LIMIT);

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
        <label className="flex items-center" title="Hide players on any roster">
          <input type="checkbox" checked={view.freeOnly} onChange={(e) => setView({ freeOnly: e.target.checked })} className={checkboxClass} />
          <span className="ml-2 text-sm text-gray-300">Free agents</span>
        </label>
        <label className="flex items-center" title="At least an 80% chance of playing tonight">
          <input type="checkbox" checked={view.likely} onChange={(e) => setView({ likely: e.target.checked })} className={checkboxClass} />
          <span className="ml-2 text-sm text-gray-300">Likely to play</span>
        </label>
        {points && (
          <select value={view.sort} onChange={(e) => setView({ sort: e.target.value })}
                  className="px-2 py-1 bg-gray-700 border border-gray-600 rounded-md text-white text-sm">
            <option value="expected">Sort: expected FPTS</option>
            <option value="gain">Sort: FPTS gain</option>
            <option value="minutes">Sort: minutes gain</option>
          </select>
        )}
      </div>
      <div className="text-[11px] text-gray-500">
        {rows.length ? `${rows.length} players on teams with a posted lineup${asOf ? `, as of ${asOf}` : ''}. * = lineup not confirmed yet.`
          : 'No lineups posted yet. The NBA publishes them a few hours before tip-off; this fills in on its own.'}
      </div>
      <div className="bg-gray-800 rounded-lg shadow-xl divide-y divide-gray-700">
        {shown.map(p => {
          const r = p.rotation;
          const mine = p.fantasy_team?.abbreviation === mineAbv;
          const taken = p.fantasy_team?.abbreviation && !mine;
          const gain = points ? r.gain : null;
          return (
            <div key={p.name} className={`px-3 py-2 flex items-start gap-3 ${mine ? 'bg-row-mine' : ''} ${taken ? 'opacity-50' : ''}`}>
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-1.5 min-w-0 flex-wrap">
                  <PlayerName id={p.id} name={p.name} className={`font-medium ${mine ? 'text-mine' : 'text-white'}`} />
                  <span className="text-[11px] text-gray-400">{p.positions?.length ? p.positions.join('/') : p.position} · {p.team_abv}</span>
                  {r.starter && <span className="px-1.5 py-px rounded-full text-[10px] font-semibold text-white bg-emerald-700">{r.promoted ? 'Starting' : 'Starter'}</span>}
                  {r.p < 0.8 && <span className="px-1.5 py-px rounded-full text-[10px] font-semibold text-white bg-gray-600">{Math.round(r.p * 100)}% to play</span>}
                  {taken && <OwnerChip person={p.fantasy_team.owner_name} team={p.fantasy_team.name} />}
                </div>
                {r.why && r.opp >= 0.5 && <div className="text-xs text-emerald-400/90 mt-0.5">{r.why}</div>}
                {p.surge && (
                  <div className="text-[11px] text-gray-400 mt-0.5">
                    <span className={p.surge.kind === 'back' ? 'text-gray-300' : 'text-green-400'}>Minutes up {sign(p.surge.min)} last 3 ({p.surge.recent} vs {p.surge.before})</span>: {p.surge.why}
                  </div>
                )}
                <div className="text-[11px] text-gray-500 mt-0.5">{r.mif} min if he plays (usual {r.base}){r.confirmed ? '' : ' *'}</div>
              </div>
              <div className="text-right shrink-0 tabular-nums">
                {points && r.fpts != null ? (
                  <>
                    <div className="text-lg font-semibold text-gray-100 leading-tight">{r.fpts.toFixed(1)}{r.confirmed ? '' : <span className="text-gray-500">*</span>}</div>
                    <div className={`text-xs ${gain >= 2 ? 'text-green-400 font-semibold' : gain <= -2 ? 'text-red-400' : 'text-gray-400'}`}>{gain == null ? '' : `${sign(gain)} FPTS`}</div>
                  </>
                ) : (
                  <div className={`text-lg font-semibold leading-tight ${r.opp >= 2 ? 'text-green-400' : r.opp <= -2 ? 'text-red-400' : 'text-gray-200'}`}>{sign(r.opp)}m</div>
                )}
                {points && <div className="text-[11px] text-gray-500">{sign(r.opp)} min</div>}
              </div>
            </div>
          );
        })}
        {rows.length > 0 && !shown.length && <div className="px-3 py-4 text-sm text-gray-400">Nobody matches these filters.</div>}
      </div>
    </div>
  );
};

export default TonightPickups;
