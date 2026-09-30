"""Fetch and build this season's projection sources into `player_projections`.

    python pull_projections.py [--season 2026-27] [--sources espn model]

espn: ESPN's fantasy projections (their unofficial public API). model: ours, from the history in
`player_seasons` (run pull_history.py first). Each source's rows for the season are replaced.
Players the NBA rosters list without a position get ESPN's.
"""
import argparse

from fantasy_database import Player
from projections import fetch_espn, model_rows, season_label, store


def main(season, sources):
    if 'model' in sources:
        rows = model_rows(season)
        store(season, 'model', rows)
        print(f"model: {len(rows)} players ({sum(r['exp'] == 0 for r in rows)} rookies)")
    if 'espn' in sources:
        rows, unmatched, positions = fetch_espn(season)
        store(season, 'espn', rows)
        filled = 0
        for player in Player.select().where(Player.pos.is_null() & Player.id.in_(list(positions))):
            player.pos = positions[player.id]
            player.save()
            filled += 1
        print(f'espn: {len(rows)} players, {len(unmatched)} unmatched'
              + (f" ({', '.join(unmatched[:12])}{'...' if len(unmatched) > 12 else ''})" if unmatched else '')
              + (f', {filled} positions filled' if filled else ''))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Build this season's projection sources.")
    parser.add_argument('--season', default=season_label())
    parser.add_argument('--sources', nargs='+', default=['model', 'espn'], choices=['model', 'espn'])
    args = parser.parse_args()
    main(args.season, args.sources)
