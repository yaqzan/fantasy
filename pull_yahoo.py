"""Read a Yahoo Fantasy Basketball league into this app: teams, rosters, position eligibility and
Yahoo's can't-cut list. The Yahoo counterpart of pull_fantrax.py.

One-time setup (the owner's Yahoo app): create an app at https://developer.yahoo.com/apps/
(API permissions: Fantasy Sports, read; redirect URI `oob`), put its keys in .env as
YAHOO_CLIENT_ID and YAHOO_CLIENT_SECRET, then

    python pull_yahoo.py auth                  # prints a Yahoo URL; approve, copy the code
    python pull_yahoo.py auth --code <code>    # saves yahoo_token.json (gitignored), refreshed automatically

Then, for a league whose settings say platform = yahoo and platform_league_id = <Yahoo league number>:

    python pull_yahoo.py sync --league <Yahoo league number> [--apply]

Dry run unless --apply. What --apply writes, all scoped to that league:
- teams: linked by Yahoo team id (`fantasy_teams.platform_team_id`; a team without one links by its
  current name) and renamed to Yahoo's name. Teams missing here are reported, not created.
- rosters: each team's players become exactly Yahoo's roster (Yahoo is the league's record).
- positions: every rostered or available player's Yahoo eligibility -> league_player_flags.positions,
  which the lineup slots use instead of NBA's G/F/C.
- can't cut: Yahoo's undroppable players are flagged undroppable. A flag set here by hand is never
  cleared (reported as a conflict instead).
The league's starting slots are compared with Yahoo's roster positions and only reported: the
league settings are the owner's.
Read-only on Yahoo's side.
"""
import argparse
import base64
import json
import os
import time
import xml.etree.ElementTree as ET

import requests
from dotenv import load_dotenv

ROOT = os.path.dirname(os.path.abspath(__file__))
TOKEN_FILE = os.path.join(ROOT, 'yahoo_token.json')
AUTH_URL = 'https://api.login.yahoo.com/oauth2/request_auth'
TOKEN_URL = 'https://api.login.yahoo.com/oauth2/get_token'
API = 'https://fantasysports.yahooapis.com/fantasy/v2'
NS = {'y': 'http://fantasysports.yahooapis.com/fantasy/v2/base.rng'}
PAGE = 25  # Yahoo's maximum players per request

load_dotenv(os.path.join(ROOT, '.env'))


# ------------------------------------------------------------------ auth

def _client():
    client_id, secret = os.getenv('YAHOO_CLIENT_ID'), os.getenv('YAHOO_CLIENT_SECRET')
    if not (client_id and secret):
        raise SystemExit('set YAHOO_CLIENT_ID and YAHOO_CLIENT_SECRET in .env (see the top of pull_yahoo.py)')
    return client_id, secret, os.getenv('YAHOO_REDIRECT_URI', 'oob')


def _token_request(data):
    client_id, secret, redirect = _client()
    basic = base64.b64encode(f'{client_id}:{secret}'.encode()).decode()
    reply = requests.post(TOKEN_URL, data={**data, 'redirect_uri': redirect}, timeout=30,
                          headers={'Authorization': f'Basic {basic}'})
    if reply.status_code != 200:
        raise SystemExit(f'Yahoo token request failed ({reply.status_code}): {reply.text[:300]}')
    token = reply.json()
    token['expires_at'] = time.time() + int(token.get('expires_in', 3600)) - 60
    with open(TOKEN_FILE, 'w', encoding='utf-8') as f:
        json.dump(token, f)
    return token


def auth(code=None):
    client_id, _, redirect = _client()
    if not code:
        print(f'Open this, approve, and run `python pull_yahoo.py auth --code <the code Yahoo shows>`:\n'
              f'{AUTH_URL}?client_id={client_id}&redirect_uri={redirect}&response_type=code&language=en-us')
        return
    _token_request({'grant_type': 'authorization_code', 'code': code})
    print(f'saved {TOKEN_FILE}')


def access_token():
    if not os.path.exists(TOKEN_FILE):
        raise SystemExit('no Yahoo login yet: run `python pull_yahoo.py auth`')
    with open(TOKEN_FILE, encoding='utf-8') as f:
        token = json.load(f)
    if time.time() >= token.get('expires_at', 0):
        token = _token_request({'grant_type': 'refresh_token', 'refresh_token': token['refresh_token']})
    return token['access_token']


def fetch(path):
    reply = requests.get(f'{API}/{path}', headers={'Authorization': f'Bearer {access_token()}'}, timeout=60)
    if reply.status_code != 200:
        raise SystemExit(f'Yahoo {path}: {reply.status_code} {reply.text[:300]}')
    return ET.fromstring(reply.content)


# ------------------------------------------------------------------ parsing (pure, tested)

def _text(node, path):
    found = node.find(path, NS)
    return found.text.strip() if found is not None and found.text else ''


def parse_player(node):
    """{name, positions, undroppable} from a Yahoo <player>. Positions keep the ones lineup slots
    understand (PG SG G SF PF F C); Util, IL and BN aren't positions."""
    positions = [p.text for p in node.findall('y:eligible_positions/y:position', NS)]
    return {'name': _text(node, 'y:name/y:full'),
            'positions': [p for p in positions if p in ('PG', 'SG', 'G', 'SF', 'PF', 'F', 'C')],
            'undroppable': _text(node, 'y:is_undroppable') == '1'}


def parse_rosters(root):
    """[{team_id, name, players: [parse_player]}] from /league/<key>/teams/roster."""
    return [{'team_id': _text(team, 'y:team_id'), 'name': _text(team, 'y:name'),
             'players': [parse_player(p) for p in team.findall('y:roster/y:players/y:player', NS)]}
            for team in root.iter(f"{{{NS['y']}}}team")]


def parse_players(root):
    return [parse_player(p) for p in root.iter(f"{{{NS['y']}}}player")]


def parse_slots(root):
    """Starting slots from /league/<key>/settings, in our SLOT_TYPES names (Yahoo's Util = UTIL;
    bench and injured spots aren't starting slots)."""
    slots = []
    for rp in root.iter(f"{{{NS['y']}}}roster_position"):
        position, count = _text(rp, 'y:position'), int(_text(rp, 'y:count') or 0)
        if position in ('BN', 'IL', 'IL+'):
            continue
        slots += ['UTIL' if position == 'Util' else position] * count
    return slots


# ------------------------------------------------------------------ sync

def available_players(key):
    """Every available (free agent or waivers) player Yahoo lists, page by page."""
    players, start = [], 0
    while True:
        page = parse_players(fetch(f'league/{key}/players;status=A;start={start};count={PAGE}'))
        players += page
        if len(page) < PAGE:
            return players
        start += PAGE


def sync(yahoo_league, apply):
    from fantasy_database import DB, FantasyTeam, FantasyTeamPlayer, LeaguePlayerFlag, Player
    from fantasy_team_helper import set_league_flags, league_team_ids
    from leagues import list_leagues
    from projections import name_index, norm_name

    league = next((lg for lg in list_leagues() if lg.platform == 'yahoo' and lg.platform_league_id == str(yahoo_league)), None)
    if league is None:
        raise SystemExit(f'no Yahoo league here has platform_league_id {yahoo_league} (League settings)')
    key = f'nba.l.{yahoo_league}'
    rosters = parse_rosters(fetch(f'league/{key}/teams/roster'))
    free = available_players(key)
    yahoo_slots = parse_slots(fetch(f'league/{key}/settings'))
    ids = name_index()
    players_by_id = {p.id: p for p in Player.select(Player.id, Player.name)}

    def ours(yahoo_name):
        return players_by_id.get(ids.get(norm_name(yahoo_name)))

    unmatched = set()
    changes = 0
    print(f'{league.name}: {len(rosters)} Yahoo teams, {sum(len(t["players"]) for t in rosters)} rostered, '
          f'{len(free)} available')
    if sorted(yahoo_slots) != sorted(league.slots):
        print(f'  starting slots differ: Yahoo {" ".join(yahoo_slots)} / here {" ".join(league.slots)} '
              '(edit League settings if Yahoo is right)')

    teams = list(FantasyTeam.select().where(FantasyTeam.league == league.id))
    by_id = {t.platform_team_id: t for t in teams if t.platform_team_id}
    by_name = {t.name: t for t in teams if not t.platform_team_id}
    with DB.atomic():
        for yt in rosters:
            team = by_id.get(yt['team_id']) or by_name.get(yt['name'])
            if team is None:
                print(f'  no team here for Yahoo team {yt["team_id"]} "{yt["name"]}": add it in the Team Manager, '
                      'then set its name to match')
                continue
            if team.platform_team_id != yt['team_id'] or team.name != yt['name']:
                changes += 1
                print(f'  {team.abv}: "{team.name}" -> "{yt["name"]}" (Yahoo team {yt["team_id"]})')
                if apply:
                    team.platform_team_id, team.name = yt['team_id'], yt['name']
                    team.save()
            want = {}
            for p in yt['players']:
                player = ours(p['name'])
                if player is None:
                    unmatched.add(p['name'])
                else:
                    want[player.name] = player
            have = {ftp.player_name for ftp in FantasyTeamPlayer.select().where(FantasyTeamPlayer.fantasy_team_id == team.id)}
            adds, drops = sorted(set(want) - have), sorted(have - set(want))
            if adds or drops:
                changes += len(adds) + len(drops)
                print(f'  {team.abv} roster: +{len(adds)} {adds[:6]}{"..." if len(adds) > 6 else ""}  '
                      f'-{len(drops)} {drops[:6]}{"..." if len(drops) > 6 else ""}')
            if apply:
                FantasyTeamPlayer.delete().where((FantasyTeamPlayer.fantasy_team_id == team.id)
                                                 & FantasyTeamPlayer.player_name.in_(drops or [''])).execute()
                for name in adds:  # off any other team in this league first
                    FantasyTeamPlayer.delete().where((FantasyTeamPlayer.player_name == name)
                                                     & FantasyTeamPlayer.fantasy_team_id.in_(league_team_ids(league))).execute()
                    FantasyTeamPlayer.create(player_id=want[name], fantasy_team_id=team, player_name=name,
                                             fantasy_team_name=team.name)

        flags = {f.player_id: f for f in LeaguePlayerFlag.select().where(LeaguePlayerFlag.league == league.id)}
        position_changes = undroppable_adds = 0
        for p in [p for t in rosters for p in t['players']] + free:
            player = ours(p['name'])
            if player is None:
                unmatched.add(p['name'])
                continue
            flag = flags.get(player.id)
            positions = ','.join(p['positions']) or None
            if positions and (flag is None or flag.positions != positions):
                position_changes += 1
                if apply:
                    set_league_flags(league, player.id, positions=positions)
            if p['undroppable'] and not (flag and flag.undroppable):
                undroppable_adds += 1
                if apply:
                    set_league_flags(league, player.id, undroppable=True)
        yahoo_undroppable = {ours(p['name']) for t in rosters for p in t['players'] if p['undroppable']}
        kept = [players_by_id[pid].name for pid, f in flags.items()
                if f.undroppable and players_by_id.get(pid) not in yahoo_undroppable]
        print(f'  positions: {position_changes} to update; can\'t cut: {undroppable_adds} to flag')
        if kept:
            print(f'  flagged undroppable here but not on Yahoo (kept, yours): {", ".join(sorted(kept)[:10])}')
        changes += position_changes + undroppable_adds
    if unmatched:
        print(f'  {len(unmatched)} Yahoo names with no NBA player here: {", ".join(sorted(unmatched)[:12])}'
              + ('' if len(unmatched) <= 12 else ' ...'))
    print(f'{changes} change(s)' + ('' if apply else ' (dry run; pass --apply)'))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Yahoo Fantasy league import (dry run unless --apply).')
    parser.add_argument('what', choices=['auth', 'sync'])
    parser.add_argument('--code', help='auth: the code Yahoo showed after approving')
    parser.add_argument('--league', help='sync: the Yahoo league number (settings platform_league_id)')
    parser.add_argument('--apply', action='store_true', help='sync: write the changes')
    args = parser.parse_args()
    if args.what == 'auth':
        auth(args.code)
    else:
        if not args.league:
            parser.error('sync needs --league')
        sync(args.league, args.apply)
