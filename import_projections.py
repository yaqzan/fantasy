"""Load a projection CSV (one source's player lines, or several sources' team wins) into the DB.

Players (into `player_projections`), columns:
  player, team, basis (per_game | total), gp, min, pts, reb, ast, stl, blk, fg3m, tov, fgm, fga,
  ftm, fta [, extra "key=value;..." with nba_id=<id> if known]
  --by-player: the file has a `source` column with several sources per player (e.g. a rookie
  survey); their numbers are averaged into one row per player.
Team wins (into `team_projections`, one row per source and team), columns:
  season, source, team, projected_wins [, url]

    python import_projections.py players <csv> --source cbs [--season 2026-27] [--by-player]
    python import_projections.py teams <csv> [--season 2026-27]
Rows for that season and source are replaced. Unmatched player names are listed.
"""
import argparse
import csv
from datetime import datetime

from fantasy_database import DB, PlayerProjection, Team, TeamProjection
from projections import name_index, norm_name, season_label

STATS = ['min', 'pts', 'reb', 'ast', 'stl', 'blk', 'fg3m', 'tov', 'fgm', 'fga', 'ftm', 'fta']


def _num(value):
    try:
        return float(value) if value not in (None, '') else None
    except ValueError:
        return None


def player_rows(path, by_player=False):
    index = name_index()
    raw = list(csv.DictReader(open(path, encoding='utf-8-sig')))
    grouped = {}
    for r in raw:
        extra = dict(kv.split('=', 1) for kv in (r.get('extra') or '').split(';') if '=' in kv)
        pid = int(extra['nba_id']) if extra.get('nba_id', '').isdigit() else index.get(norm_name(r['player']))
        if pid is None:
            grouped.setdefault(('unmatched', r['player']), []).append(r)
            continue
        gp = _num(r.get('gp'))
        per_game = (r.get('basis') or 'per_game') == 'per_game'
        line = {'name': r['player'], 'gp': gp}
        for s in STATS:
            v = _num(r.get(s))
            if v is not None and not per_game:
                v = v / gp if gp else None
            line[s] = v
        grouped.setdefault(pid, []).append(line)
    rows, unmatched = [], []
    for pid, lines in grouped.items():
        if isinstance(pid, tuple):
            unmatched.append(pid[1])
            continue
        if not by_player:
            lines = lines[:1]
        merged = {'player_id': pid, 'name': lines[0]['name']}
        for s in ['gp'] + STATS:
            values = [ln[s] for ln in lines if ln.get(s) is not None]
            merged[s] = sum(values) / len(values) if values else None
        if merged['pts'] is None:
            continue
        rows.append(merged)
    return rows, sorted(set(unmatched))


def import_players(path, source, season, by_player=False):
    rows, unmatched = player_rows(path, by_player)
    with DB.atomic():
        PlayerProjection.delete().where((PlayerProjection.season == season) & (PlayerProjection.source == source)).execute()
        for i in range(0, len(rows), 300):
            PlayerProjection.insert_many([{'season': season, 'source': source, 'updated_at': datetime.now(), **r}
                                          for r in rows[i:i + 300]]).execute()
    print(f'{source}: {len(rows)} players for {season}, {len(unmatched)} unmatched'
          + (f" ({', '.join(unmatched[:10])}{'...' if len(unmatched) > 10 else ''})" if unmatched else ''))


def import_teams(path, season):
    teams = {t.name for t in Team.select()}
    rows = [r for r in csv.DictReader(open(path, encoding='utf-8-sig')) if r['season'] == season]
    bad = sorted({r['team'] for r in rows if r['team'] not in teams})
    if bad:
        raise SystemExit(f'unknown team names: {bad}')
    sources = sorted({r['source'] for r in rows})
    with DB.atomic():
        TeamProjection.delete().where((TeamProjection.season == season) & TeamProjection.source.in_(sources)).execute()
        TeamProjection.insert_many([{'season': season, 'source': r['source'], 'team': r['team'],
                                     'wins': float(r['projected_wins']), 'url': (r.get('url') or '')[:512] or None,
                                     'updated_at': datetime.now()} for r in rows]).execute()
    print(f"teams: {len(rows)} rows for {season} from {', '.join(sources)}")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Load projection CSVs into the database.')
    parser.add_argument('kind', choices=['players', 'teams'])
    parser.add_argument('path')
    parser.add_argument('--source', help='source name for a players file')
    parser.add_argument('--season', default=season_label())
    parser.add_argument('--by-player', action='store_true', help='average several sources per player (a survey file)')
    args = parser.parse_args()
    if args.kind == 'players':
        if not args.source:
            parser.error('players files need --source')
        import_players(args.path, args.source, args.season, args.by_player)
    else:
        import_teams(args.path, args.season)
