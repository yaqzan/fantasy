"""Read a Yahoo Fantasy Basketball league into this app: teams, rosters, position eligibility and
Yahoo's can't-cut list. The Yahoo counterpart of pull_fantrax.py.

One-time setup (the owner's Yahoo app): create an app at https://developer.yahoo.com/apps/
(client type Confidential; API permissions: Fantasy Sports, read; no OpenID Connect; redirect URI
https://localhost:8080, since Yahoo no longer takes `oob`), put its keys in .env as YAHOO_CLIENT_ID
and YAHOO_CLIENT_SECRET (plus YAHOO_REDIRECT_URI if you registered another address), then

    python pull_yahoo.py auth                  # prints a Yahoo URL; approve it
    python pull_yahoo.py auth --code <code>    # the code= value of the localhost address Yahoo sends you to
                                               # (that page won't load); saves yahoo_token.json (gitignored)

No app keys (Yahoo's developer program can take weeks): with no yahoo_token.json, or a token Yahoo refuses, every call goes to
the same v2 API on Yahoo's own web host (pub-api-ro.fantasysports.yahoo.com) with the owner's Firefox
login, saved to yahoo_web.cookie (gitignored) and re-read from Firefox once when Yahoo answers 401.
Sign in to Yahoo in Firefox ("keep me signed in") first.

Then, for a league whose settings say platform = yahoo and platform_league_id = <Yahoo league number>:

    python pull_yahoo.py sync --league <Yahoo league number> [--apply]
    python pull_yahoo.py draft --league <number> [--apply] [--watch 20]   # draft order + picks onto the board
    python pull_yahoo.py adp --league <number>                            # Yahoo's rank + ADP -> .cache/

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
`draft` stores the round-1 order (Yahoo `draft_position`, once set) in settings draft.order and puts
each drafted player on his team (Yahoo wins for a drafted player; an undrafted hand entry stays).
Read-only on Yahoo's side.
"""
import argparse
import base64
import json
import os
import pickle
import time
from datetime import date
import xml.etree.ElementTree as ET
from urllib.parse import urlencode

import requests
from dotenv import load_dotenv

ROOT = os.path.dirname(os.path.abspath(__file__))
TOKEN_FILE = os.path.join(ROOT, 'yahoo_token.json')
AUTH_URL = 'https://api.login.yahoo.com/oauth2/request_auth'
TOKEN_URL = 'https://api.login.yahoo.com/oauth2/get_token'
API = 'https://fantasysports.yahooapis.com/fantasy/v2'
WEB_API = 'https://pub-api-ro.fantasysports.yahoo.com/fantasy/v2'   # the same API behind Yahoo's site: login cookies
COOKIE_FILE = os.path.join(ROOT, 'yahoo_web.cookie')
ADP_DIR = os.path.join(ROOT, '.cache')
UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:131.0) Gecko/20100101 Firefox/131.0'
NS = {'y': 'http://fantasysports.yahooapis.com/fantasy/v2/base.rng'}
OUT_STATUSES = ('O', 'INJ')  # Yahoo statuses that mean he is not playing (same as fantasy_team_helper.OUT_STATUSES; that module needs the DB, this one imports without it)
PAGE = 25  # Yahoo's maximum players per request

load_dotenv(os.path.join(ROOT, '.env'))


# ------------------------------------------------------------------ auth

def _client():
    client_id, secret = os.getenv('YAHOO_CLIENT_ID'), os.getenv('YAHOO_CLIENT_SECRET')
    if not (client_id and secret):
        raise SystemExit('set YAHOO_CLIENT_ID and YAHOO_CLIENT_SECRET in .env (see the top of pull_yahoo.py)')
    return client_id, secret, os.getenv('YAHOO_REDIRECT_URI', 'https://localhost:8080')


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
        # Ask for Fantasy Sports read explicitly: without it Yahoo can grant a token that every
        # fantasy call answers 403 "not authorized" (seen 2026-09-30).
        query = urlencode({'client_id': client_id, 'redirect_uri': redirect, 'response_type': 'code',
                           'scope': 'fspt-r', 'language': 'en-us'})
        print(f"Open this and approve. Yahoo then sends you to {redirect}/?code=... (that page won't load):\n"
              f'copy the code and run `python pull_yahoo.py auth --code <code>`.\n{AUTH_URL}?{query}')
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


_web = None


def _firefox_cookies():
    """The owner's Yahoo login from Firefox, saved to COOKIE_FILE (a pickled list of dicts)."""
    import browser_cookie3
    cookies = [dict(name=c.name, value=c.value, domain=c.domain, path=c.path)
               for c in browser_cookie3.firefox(domain_name='yahoo.com')]
    with open(COOKIE_FILE, 'wb') as f:
        pickle.dump(cookies, f)
    return cookies


def _web_session(fresh=False):
    global _web
    if _web is None or fresh:
        if fresh or not os.path.exists(COOKIE_FILE):
            cookies = _firefox_cookies()
        else:
            with open(COOKIE_FILE, 'rb') as f:
                cookies = pickle.load(f)
        _web = requests.Session()
        _web.headers['User-Agent'] = UA
        for c in cookies:
            _web.cookies.set(c['name'], c['value'], domain=c['domain'], path=c.get('path', '/'))
    return _web


def fetch(path):
    reply = None
    if os.path.exists(TOKEN_FILE):
        reply = requests.get(f'{API}/{path}', headers={'Authorization': f'Bearer {access_token()}'}, timeout=60)
    # No app keys, or a token Yahoo refuses (403 "not authorized" while the developer program hasn't
    # approved the app, 2026-10): Yahoo's web host with the Firefox login; an expired one is re-read once.
    if reply is None or reply.status_code in (401, 403):
        reply = _web_session().get(f'{WEB_API}/{path}', timeout=60)
        if reply.status_code == 401:
            reply = _web_session(fresh=True).get(f'{WEB_API}/{path}', timeout=60)
        if reply.status_code == 401:
            raise SystemExit('Yahoo says not logged in: sign in to Yahoo in Firefox ("keep me signed in") and rerun')
    if reply.status_code != 200:
        raise SystemExit(f'Yahoo {path}: {reply.status_code} {reply.text[:300]}')
    return ET.fromstring(reply.content)


# ------------------------------------------------------------------ parsing (pure, tested)

def _text(node, path):
    found = node.find(path, NS)
    return found.text.strip() if found is not None and found.text else ''


def parse_player(node):
    """{name, positions, undroppable, status, il} from a Yahoo <player>. Positions keep the ones lineup slots
    understand (PG SG G SF PF F C); Util, IL and BN aren't positions. il: sits in the injured-list slot."""
    positions = [p.text for p in node.findall('y:eligible_positions/y:position', NS)]
    return {'name': _text(node, 'y:name/y:full'),
            'positions': [p for p in positions if p in ('PG', 'SG', 'G', 'SF', 'PF', 'F', 'C')],
            'undroppable': _text(node, 'y:is_undroppable') == '1',
            'status': _text(node, 'y:status'),    # '' healthy; O / INJ out, DTD / GTD day to day, NA not active
            'il': _text(node, 'y:selected_position/y:position') in ('IL', 'IL+')}


def _owner(team):
    """The first manager's nickname on a Yahoo <team>, '' when Yahoo hides it."""
    nick = _text(team, 'y:managers/y:manager/y:nickname')
    return '' if nick.startswith('--') else nick


def parse_rosters(root):
    """[{team_id, name, players: [parse_player], adds_used, adds_week}] from /league/<key>/teams/roster; adds are the
    pickups Yahoo counts for the team in that week number (its weekly limit is a league setting)."""
    return [{'team_id': _text(team, 'y:team_id'), 'name': _text(team, 'y:name'), 'owner': _owner(team),
             'adds_used': int(_text(team, 'y:roster_adds/y:value') or 0) if _text(team, 'y:roster_adds/y:value') else None,
             'adds_week': int(_text(team, 'y:roster_adds/y:coverage_value') or 0) or None,
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


def parse_draft(root):
    """(order, picks) from /league/<key>;out=teams,draftresults. order: Yahoo team ids by draft
    position (empty until Yahoo sets it); picks: [{pick, round, team_id, player_key}] made so far."""
    positions = {}
    for team in root.iter(f"{{{NS['y']}}}team"):
        pos = _text(team, 'y:draft_position')
        if pos:
            positions[int(pos)] = _text(team, 'y:team_id')
    picks = []
    for dr in root.iter(f"{{{NS['y']}}}draft_result"):
        key = _text(dr, 'y:player_key')
        if key:
            picks.append({'pick': int(_text(dr, 'y:pick')), 'round': int(_text(dr, 'y:round') or 0),
                          'team_id': _text(dr, 'y:team_key').rsplit('.t.', 1)[-1], 'player_key': key})
    return [positions[p] for p in sorted(positions)], sorted(picks, key=lambda p: p['pick'])


def parse_adp(root):
    """[{name, team, positions, rank, adp, drafted}] from /league/<key>/players;sort=OR;out=draft_analysis."""
    out = []
    for p in root.iter(f"{{{NS['y']}}}player"):
        adp = _text(p, 'y:draft_analysis/y:average_pick')
        drafted = _text(p, 'y:draft_analysis/y:percent_drafted')
        rank = next((_text(r, 'y:rank_value') for r in p.findall('y:player_ranks/y:player_rank', NS)
                     if _text(r, 'y:rank_type') == 'OR'), '')
        out.append({**parse_player(p), 'team': _text(p, 'y:editorial_team_abbr'),
                    'rank': int(rank) if rank.isdigit() else None,
                    'adp': float(adp) if adp not in ('', '-') else None,
                    'drafted': float(drafted) if drafted not in ('', '-') else None})
    return out


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


def waiver_players(key):
    """{name: the day he clears waivers} for every player Yahoo has on waivers, page by page."""
    out, start = {}, 0
    while True:
        root = fetch(f'league/{key}/players;status=W;start={start};count={PAGE};out=ownership')
        nodes = list(root.iter(f"{{{NS['y']}}}player"))
        for p in nodes:
            day = _text(p, 'y:ownership/y:waiver_date')
            if day:
                out[_text(p, 'y:name/y:full')] = date.fromisoformat(day)
        if len(nodes) < PAGE:
            return out
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
    stored_status = {p.id: p.injury_status for p in Player.select(Player.id, Player.injury_status)}

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
            if apply and yt.get('owner') and team.owner_name != yt['owner']:
                team.owner_name = yt['owner']
                team.save()
            if apply and (team.adds_used, team.adds_week) != (yt['adds_used'], yt['adds_week']):
                team.adds_used, team.adds_week = yt['adds_used'], yt['adds_week']
                team.save()
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
                on_il = {ours(p['name']).name for p in yt['players'] if p['il'] and ours(p['name'])}
                FantasyTeamPlayer.update(il=FantasyTeamPlayer.player_name.in_(list(on_il) or [''])).where(
                    FantasyTeamPlayer.fantasy_team_id == team.id).execute()

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
        statuses = {}
        for p in [p for t in rosters for p in t['players']] + free:
            if ours(p['name']):
                statuses[ours(p['name']).id] = p['status'] or None
        status_changes = 0
        for pid, status in statuses.items():
            if (stored_status.get(pid) or None) != status:
                status_changes += 1
                if apply:
                    Player.update(injury_status=status).where(Player.id == pid).execute()
        print(f'  injury status: {sum(1 for v in statuses.values() if v in OUT_STATUSES)} out, {status_changes} to update')
        changes += status_changes
        on_waivers = {ours(n).id: day for n, day in waiver_players(key).items() if ours(n)}
        waiver_changes = 0
        for pid in set(on_waivers) | {pid for pid, f in flags.items() if f.waiver_until}:
            want_day = on_waivers.get(pid)
            if (flags[pid].waiver_until if pid in flags else None) != want_day:
                waiver_changes += 1
                if apply:
                    set_league_flags(league, pid, waiver_until=want_day)
        print(f'  waivers: {len(on_waivers)} players, {waiver_changes} dates to update')
        changes += waiver_changes
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


def _league(yahoo_league):
    from leagues import list_leagues
    league = next((lg for lg in list_leagues() if lg.platform == 'yahoo' and lg.platform_league_id == str(yahoo_league)), None)
    if league is None:
        raise SystemExit(f'no Yahoo league here has platform_league_id {yahoo_league} (League settings)')
    return league


_names = {}     # Yahoo player key -> name, kept across --watch polls


def player_names(key, player_keys):
    missing = [k for k in player_keys if k not in _names]
    for i in range(0, len(missing), PAGE):
        root = fetch(f'league/{key}/players;player_keys={",".join(missing[i:i + PAGE])}')
        for p in root.iter(f"{{{NS['y']}}}player"):
            _names[_text(p, 'y:player_key')] = _text(p, 'y:name/y:full')
    return {k: _names.get(k, k) for k in player_keys}


def sync_draft(yahoo_league, apply):
    """Yahoo's draft order into settings draft.order, and its picks onto the draft board (team by Yahoo
    team id). Yahoo is the result, so a pick it lists replaces what the board has for that player;
    players Yahoo hasn't seen drafted are left alone (hand entries stay)."""
    from fantasy_database import DB, FantasyTeam, FantasyTeamPlayer, Player
    from leagues import update_league
    from projections import name_index, norm_name

    league = _league(yahoo_league)
    key = f'nba.l.{yahoo_league}'
    order, picks = parse_draft(fetch(f'league/{key};out=teams,draftresults'))
    teams = {t.platform_team_id: t for t in FantasyTeam.select().where(FantasyTeam.league == league.id) if t.platform_team_id}
    team_ids = [t.id for t in FantasyTeam.select().where(FantasyTeam.league == league.id)]
    changes = 0
    if order:
        abvs = [teams[t].abv if t in teams else f'?{t}' for t in order]
        if abvs != league.settings['draft']['order']:
            changes += 1
            print(f"  draft order: {' '.join(abvs)}" + (' (unknown Yahoo team ids: run sync first)' if any(a.startswith('?') for a in abvs) else ''))
            if apply and not any(a.startswith('?') for a in abvs):
                update_league(league.id, settings={**league.settings, 'draft': {**league.settings['draft'], 'order': abvs}})
    elif not picks:
        print('  no draft order on Yahoo yet')
    names = player_names(key, [p['player_key'] for p in picks])
    index = name_index()
    for p in picks:
        name = names[p['player_key']]
        team = teams.get(p['team_id'])
        player = Player.get_or_none(Player.id == index.get(norm_name(name)))
        if team is None or player is None:
            print(f"  #{p['pick']} {name}: SKIPPED, " + ('no team here with Yahoo id ' + p['team_id'] if team is None else 'no such player here'))
            continue
        held = FantasyTeamPlayer.get_or_none((FantasyTeamPlayer.player_id == player.id)
                                             & FantasyTeamPlayer.fantasy_team_id.in_(team_ids))
        if held and held.fantasy_team_id_id == team.id:
            continue
        changes += 1
        print(f"  #{p['pick']} (R{p['round']}) {player.name} -> {team.name}"
              + (f'  (board had {held.fantasy_team_name})' if held else ''))
        if apply:
            with DB.atomic():
                FantasyTeamPlayer.delete().where((FantasyTeamPlayer.player_id == player.id)
                                                 & FantasyTeamPlayer.fantasy_team_id.in_(team_ids)).execute()
                FantasyTeamPlayer.create(player_id=player, fantasy_team_id=team, player_name=player.name,
                                         fantasy_team_name=team.name)
    print(f"{time.strftime('%H:%M:%S')} {len(picks)} picks, {changes} new/changed"
          + ('' if apply else ' (dry run; pass --apply)'))


def pull_adp(yahoo_league, count=300):
    """Yahoo's pre-draft rank (what its draft room lists first) and average draft position for the top
    `count` players -> .cache/yahoo_adp_<league>.json, the room model for a snake draft."""
    key = f'nba.l.{yahoo_league}'
    rows = []
    for start in range(0, count, PAGE):
        rows += parse_adp(fetch(f'league/{key}/players;sort=OR;start={start};count={PAGE};out=draft_analysis,ranks'))
    os.makedirs(ADP_DIR, exist_ok=True)
    path = os.path.join(ADP_DIR, f'yahoo_adp_{yahoo_league}.json')
    with open(path, 'w', encoding='utf-8') as f:
        json.dump({'pulled': time.strftime('%Y-%m-%d %H:%M'), 'players': rows}, f, ensure_ascii=False, indent=0)
    print(f'{len(rows)} players -> {path}; top 5: ' + ', '.join(f"{r['name']} (#{r['rank']}, ADP {r['adp']})" for r in rows[:5]))


def sync_schedule(yahoo_league, apply):
    """Our league schedule from Yahoo's scoreboards: each regular week's start and my opponent (teams matched
    by Yahoo team number). Playoff weeks keep a blank opponent and what's already here; playoffs.first_week
    is filled when it is unset."""
    from datetime import date, timedelta
    from fantasy_database import FantasyTeam
    from leagues import update_league
    league = _league(yahoo_league)
    key = f'nba.l.{yahoo_league}'
    teams = list(FantasyTeam.select().where(FantasyTeam.league == league.id))
    abv = {str(t.platform_team_id): t.abv for t in teams if t.platform_team_id}
    mine = next((str(t.platform_team_id) for t in teams if t.abv == league.my_team and t.platform_team_id), None)
    if not mine:
        raise SystemExit(f'my team ({league.my_team!r}) has no Yahoo team number; run pull_yahoo.py sync first')
    first_playoff = int(fetch(f'league/{key}/settings').findtext('.//y:playoff_start_week', namespaces=NS))
    schedule, week_end = [], None
    for week in range(1, first_playoff):
        root = fetch(f'league/{key}/scoreboard;week={week}')
        start = root.findtext('.//y:week_start', namespaces=NS)
        week_end = date.fromisoformat(root.findtext('.//y:week_end', namespaces=NS))
        opponent = None
        for m in root.iter(f"{{{NS['y']}}}matchup"):
            ids = [t.findtext('y:team_key', namespaces=NS).rsplit('.t.', 1)[-1] for t in m.iter(f"{{{NS['y']}}}team")]
            if mine in ids:
                theirs = ids[1] if ids[0] == mine else ids[0]
                opponent = abv.get(theirs)
                if opponent is None:
                    raise SystemExit(f'week {week}: no team here with Yahoo team {theirs}')
        if opponent is None:
            raise SystemExit(f'week {week}: Yahoo lists no matchup for my team')
        schedule.append([start, opponent])
    old = dict(league.schedule)
    # Playoff weeks start the day after the last regular week; the ones already here stay.
    first_start = (week_end + timedelta(days=1)).isoformat()
    schedule += sorted([s, o] for s, o in old.items() if s >= first_start)
    for i, (start, opponent) in enumerate(schedule, 1):
        was = old.get(start)
        note = '' if was == opponent else ('  (new week)' if was is None else f'  (was {was or "blank"})')
        print(f'  week {i:2} {start}  {opponent or "-"}{note}')
    for start in sorted(set(old) - {s for s, _ in schedule}):
        print(f'  {start}: not a Yahoo week, dropped')
    settings = dict(league.settings, schedule=schedule)
    if not league.settings['playoffs']['first_week']:
        settings['playoffs'] = dict(league.settings['playoffs'], first_week=first_playoff)
        print(f'  playoffs start week {first_playoff}')
    if apply:
        update_league(league.id, settings=settings)
    print(f'{len(schedule)} weeks' + ('' if apply else ' (dry run; pass --apply)'))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Yahoo Fantasy league import (dry run unless --apply).')
    parser.add_argument('what', choices=['auth', 'sync', 'draft', 'adp', 'schedule'])
    parser.add_argument('--code', help='auth: the code Yahoo showed after approving')
    parser.add_argument('--league', help='sync: the Yahoo league number (settings platform_league_id)')
    parser.add_argument('--apply', action='store_true', help='sync, draft, schedule: write the changes')
    parser.add_argument('--watch', type=int, metavar='SECONDS', help='draft: repeat every N seconds until Ctrl+C')
    parser.add_argument('--log', metavar='FILE', help='append all output to FILE (background runs)')
    args = parser.parse_args()
    if args.log:
        import sys
        sys.stdout = sys.stderr = open(args.log, 'a', encoding='utf-8', buffering=1)
    if args.what == 'auth':
        auth(args.code)
    elif not args.league:
        parser.error(f'{args.what} needs --league')
    elif args.what == 'sync':
        sync(args.league, args.apply)
        if args.apply and args.log:   # the watchdog alerts when this stamp goes stale
            open(args.log + '.ok', 'w').close()
    elif args.what == 'adp':
        pull_adp(args.league)
    elif args.what == 'schedule':
        sync_schedule(args.league, args.apply)
    else:
        while True:
            try:
                sync_draft(args.league, args.apply)
            except (requests.RequestException, ET.ParseError) as e:   # one bad poll shouldn't end a draft-long watch
                print(f"{time.strftime('%H:%M:%S')} Yahoo unreachable: {e}")
            except SystemExit as e:                                 # nor a lapsed login: Firefox may be signed in by the next poll
                if not args.watch:
                    raise
                print(f"{time.strftime('%H:%M:%S')} {e}")
            if not args.watch:
                break
            time.sleep(args.watch)
