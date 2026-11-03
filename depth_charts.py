"""ESPN's editorial NBA depth charts, one snapshot a day, as a prior for who succeeds an absent player (role_minutes).

Feed: site.api.espn.com/apis/site/v2/sports/basketball/nba/teams/{id}/depthcharts (30 calls, one a second, browser UA).
Editorial and can be stale, so role_minutes only tilts the allocation toward the next man listed behind the absent
player (DEPTH_BOOST in role_minutes_model.json); the learned pair effects take over as games come in. Checked
2026-11-03 on 2026-27 new absences: the charted successor gained +1.25 min vs his recent level, the stat-profile
nearest -0.42 (n=148, they agree 10% of the time; the chart is today's, so this flatters it). rotation.md.
Polled from nba_rotation's poller at most daily; a 403/429 stops the round and cools down 6 h.
"""
import time
from datetime import datetime

import requests

TEAMS_URL = 'https://site.api.espn.com/apis/site/v2/sports/basketball/nba/teams'
URL = 'https://site.api.espn.com/apis/site/v2/sports/basketball/nba/teams/{}/depthcharts'
HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36'}
ESPN_TEAM = {'NO': 'NOP', 'NY': 'NYK', 'WSH': 'WAS', 'GS': 'GSW', 'SA': 'SAS', 'UTAH': 'UTA'}
SNAPSHOT_EVERY = 20 * 3600
BLOCK_COOLDOWN = 6 * 3600
_state = {'last': 0.0, 'blocked_until': 0.0}


def fetch():
    """[(team, pos, rank, espn_id, name)] for every team, or None on a block / error."""
    try:
        r = requests.get(TEAMS_URL, headers=HEADERS, timeout=20)
        r.raise_for_status()
        teams = [(t['team']['id'], t['team']['abbreviation']) for t in r.json()['sports'][0]['leagues'][0]['teams']]
    except Exception as e:
        print(f'depth_charts: teams {e}')
        return None
    rows = []
    for tid, abv in teams:
        try:
            r = requests.get(URL.format(tid), headers=HEADERS, timeout=20)
            if r.status_code in (403, 429):
                _state['blocked_until'] = time.time() + BLOCK_COOLDOWN
                print(f'depth_charts: ESPN {r.status_code}, cooling down')
                return None
            r.raise_for_status()
            for chart in r.json().get('depthchart', []):
                for pos, v in chart.get('positions', {}).items():
                    for k, a in enumerate(v.get('athletes', [])):
                        rows.append((ESPN_TEAM.get(abv, abv), pos[:4], k, int(a['id']), a.get('displayName', '')[:64]))
        except Exception as e:
            print(f'depth_charts: {abv} {e}')
        time.sleep(1.0)
    return rows


def store(rows, day=None):
    from fantasy_database import DB, DepthChart
    from projections import name_index, norm_name
    from daily_leaders import nba_today
    day = day or nba_today()
    index = name_index()
    now = datetime.now()
    data = [{'snapshot_date': day, 'team': t, 'pos': pos, 'rank': k, 'espn_id': eid, 'player_id': index.get(norm_name(n)),
             'name': n, 'fetched_at': now} for t, pos, k, eid, n in rows]
    with DB.atomic():
        DepthChart.delete().where(DepthChart.snapshot_date == day).execute()
        for i in range(0, len(data), 300):
            DepthChart.insert_many(data[i:i + 300]).execute()
    return len(data)


def maybe_snapshot(force=False):
    now = time.time()
    if not force and (now < _state['blocked_until'] or now - _state['last'] < SNAPSHOT_EVERY):
        return 0
    _state['last'] = now
    rows = fetch()
    return store(rows) if rows else 0


def latest(today=None, max_age_days=7):
    """{team: {pos: [player_id or None, ...]}} from the newest snapshot within `max_age_days` ({} if none)."""
    from datetime import timedelta
    from peewee import fn
    from fantasy_database import DepthChart
    from daily_leaders import nba_today
    today = today or nba_today()
    day = (DepthChart.select(fn.MAX(DepthChart.snapshot_date))
           .where(DepthChart.snapshot_date <= today, DepthChart.snapshot_date >= today - timedelta(days=max_age_days)).scalar())
    if not day:
        return {}
    out = {}
    for r in DepthChart.select().where(DepthChart.snapshot_date == day).order_by(DepthChart.team, DepthChart.pos, DepthChart.rank):
        out.setdefault(r.team, {}).setdefault(r.pos, []).append(r.player_id)
    return out


if __name__ == '__main__':
    print('rows', maybe_snapshot(force=True))
