"""Read Fantrax data with the owner's saved login (fantraxloggedin.cookie, gitignored).

- projections: Fantrax's season projections (per game) for every player it projects, stored as
  source 'fantrax' in `player_projections`. Any league of the season works; the stats come from
  the "Standard" group, so the league's own categories don't matter.
- techs: technical fouls per player per past season (Fantrax "Extra" stats), stored in
  `player_seasons.tech`: the history technical-foul projections are built from. Fantrax projects
  no technicals itself (they're all 0).

    python pull_fantrax.py projections --league <fantrax league id of this season>
    python pull_fantrax.py techs --league <any Fantrax NBA league id> [--seasons 2023-24 2024-25 2025-26]
- teams: keep our team names in step with Fantrax, matched by Fantrax's permanent team id (names
  change, ids don't). Teams without an id are linked by their current name. Dry run unless --apply.

    python pull_fantrax.py teams --league <fantrax league id> [--apply]
Read-only: only Fantrax's player-stats listing and standings are requested.
"""
import argparse
import os
import pickle
import time

import requests

from fantasy_database import DB, FantasyTeam, PlayerSeason
from leagues import list_leagues
from projections import name_index, norm_name, season_label, store

ROOT = os.path.dirname(os.path.abspath(__file__))
COOKIE = os.path.join(ROOT, 'fantraxloggedin.cookie')
URL = 'https://www.fantrax.com/fxpa/req'
# Fantrax's season codes ("SEASON_<code>_YEAR_TO_DATE"), from its player-stats season list.
SEASON_CODES = {'2018-19': '40x', '2019-20': '40z', '2020-21': '41b', '2021-22': '41d', '2022-23': '41f',
                '2023-24': '41h', '2024-25': '41j', '2025-26': '41l', '2026-27': '41n'}
STANDARD = {'GP': 'gp', 'MIN': 'min', 'FGM': 'fgm', 'FGA': 'fga', 'FTM': 'ftm', 'FTA': 'fta', '3PTM': 'fg3m',
            'REB': 'reb', 'AST': 'ast', 'ST': 'stl', 'BLK': 'blk', 'TO': 'tov', 'PTS': 'pts'}


def session():
    if not os.path.exists(COOKIE):
        raise SystemExit(f'no saved Fantrax login ({COOKIE}); see fantrax_client.py')
    s = requests.Session()
    s.headers['User-Agent'] = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:128.0) Gecko/20100101 Firefox/128.0'
    for c in pickle.load(open(COOKIE, 'rb')):
        s.cookies.set(c['name'], c['value'], domain=c.get('domain'), path=c.get('path', '/'))
    return s


def player_table(s, league_id, season_or_projection, group):
    """Every row of Fantrax's player-stats table: [(name, {column: text})]."""
    rows, page, pages = [], 1, 1
    while page <= pages:
        data = {'leagueId': league_id, 'statusOrTeamFilter': 'ALL', 'pageNumber': str(page),
                'maxResultsPerPage': '500', 'scoringCategoryType': group, 'seasonOrProjection': season_or_projection}
        reply = s.post(URL, params={'leagueId': league_id}, json={'msgs': [{'method': 'getPlayerStats', 'data': data}]},
                       timeout=90)
        reply.raise_for_status()
        response = reply.json()['responses'][0]
        if response.get('pageError'):
            raise SystemExit(f"Fantrax: {response['pageError']} (log in again in the browser and re-save the cookie)")
        table = response['data']
        columns = [c.get('shortName') for c in table['tableHeader']['cells']]
        for r in table['statsTable']:
            rows.append((r['scorer']['name'], dict(zip(columns, [c.get('content') for c in r['cells']]))))
        pages = table['paginatedResultSet']['totalNumPages']
        page += 1
        time.sleep(1)
    return rows


def _num(text):
    try:
        return float(str(text).replace(',', ''))
    except ValueError:
        return None


def pull_projections(league_id, season):
    s, index = session(), name_index()
    rows, unmatched = [], []
    for name, cells in player_table(s, league_id, f'PROJECTION_0_{SEASON_CODES[season]}_SEASON', '1'):
        line = {ours: _num(cells.get(theirs)) for theirs, ours in STANDARD.items()}
        if not line['gp'] or not line['pts']:
            continue
        pid = index.get(norm_name(name))
        if pid is None:
            unmatched.append(name)
            continue
        rows.append({'player_id': pid, 'name': name, **line})
    store(season, 'fantrax', rows)
    print(f'fantrax: {len(rows)} players for {season}, {len(unmatched)} unmatched'
          + (f" ({', '.join(unmatched[:10])}{'...' if len(unmatched) > 10 else ''})" if unmatched else ''))


def pull_techs(league_id, seasons):
    s, index = session(), name_index()
    for season in seasons:
        stored = {p.player_id: p for p in PlayerSeason.select().where(PlayerSeason.season == season)}
        matched = 0
        with DB.atomic():
            for name, cells in player_table(s, league_id, f'SEASON_{SEASON_CODES[season]}_YEAR_TO_DATE', '2'):
                techs = _num(cells.get('TF'))
                pid = index.get(norm_name(name))
                if techs is None or pid not in stored:
                    continue
                PlayerSeason.update(tech=int(techs)).where((PlayerSeason.season == season)
                                                           & (PlayerSeason.player_id == pid)).execute()
                matched += 1
        total = sum(p.tech or 0 for p in PlayerSeason.select().where(PlayerSeason.season == season))
        print(f'{season}: technicals for {matched} players ({total} in all)')


def sync_teams(fantrax_league_id, apply):
    league = next((lg for lg in list_leagues() if lg.platform == 'fantrax' and lg.platform_league_id == fantrax_league_id), None)
    if league is None:
        raise SystemExit(f'no Fantrax league here has platform_league_id {fantrax_league_id}')
    reply = session().post(URL, params={'leagueId': fantrax_league_id}, timeout=60,
                           json={'msgs': [{'method': 'getStandings', 'data': {'leagueId': fantrax_league_id}}]})
    reply.raise_for_status()
    response = reply.json()['responses'][0]
    if response.get('pageError'):
        raise SystemExit(f"Fantrax: {response['pageError']} (log in again in the browser and re-save the cookie)")
    theirs = {tid: info['name'] for tid, info in response['data']['fantasyTeamInfo'].items()}
    teams = list(FantasyTeam.select().where(FantasyTeam.league == league.id))
    by_id = {t.platform_team_id: t for t in teams if t.platform_team_id}
    by_name = {t.name: t for t in teams if not t.platform_team_id}
    changes = []
    for tid, name in theirs.items():
        team = by_id.get(tid) or by_name.get(name)
        if team is None:
            print(f'  no team here for Fantrax {tid} "{name}"; set its platform_team_id by hand')
            continue
        if team.platform_team_id != tid or team.name != name:
            changes.append((team, tid, name))
    for team in teams:
        if team.platform_team_id and team.platform_team_id not in theirs:
            print(f'  {team.name} ({team.abv}): id {team.platform_team_id} is not in the Fantrax league')
    taken = {t.name for t in teams}
    for team, tid, name in changes:
        clash = name in taken and name != team.name
        print(f'  {team.abv}: "{team.name}" -> "{name}"' + ('' if team.platform_team_id else f'  (link {tid})')
              + ('  SKIPPED, name taken by another team' if clash else ''))
        if apply and not clash:
            team.platform_team_id, team.name = tid, name
            team.save()
            taken.add(name)
    print(f'{len(changes)} change(s)' + ('' if apply else ' (dry run; pass --apply)'))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Fantrax projections and technical-foul history.')
    parser.add_argument('what', choices=['projections', 'techs', 'teams'])
    parser.add_argument('--league', required=True, help='a Fantrax NBA league id (projections: this season\'s)')
    parser.add_argument('--season', default=season_label())
    parser.add_argument('--apply', action='store_true', help='teams: write the changes')
    parser.add_argument('--seasons', nargs='+', default=['2023-24', '2024-25', '2025-26'])
    args = parser.parse_args()
    if args.what == 'teams':
        sync_teams(args.league, args.apply)
    elif args.what == 'projections':
        pull_projections(args.league, args.season)
    else:
        pull_techs(args.league, args.seasons)
