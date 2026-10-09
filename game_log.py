"""Per-game history behind every player's season / last-5 / last-10 totals (table game_lines).

Two writers, one calculation:
- The NBA pull (pull_api_data.update_all_player_stats) stores every game of the official game log
  (source 'nba') and recomputes each player.
- ESPN, the moment it calls a regular-season game final (daily_leaders.slate), folds that game's
  lines in (source 'espn') and recomputes those players, so averages are fresh within ~5 minutes
  of the buzzer instead of waiting for stats.nba.com. Checked 2026-04-10: all 325 ESPN lines equal
  the NBA log on every box stat and W.
The NBA's rows replace ESPN's (same player and date) and an ESPN row older than the NBA log's
latest night with no NBA twin is dropped (a game the NBA doesn't count, e.g. the Cup final). Both go
through pull_api_data.apply_game_stats, so the totals are computed exactly one way.

Times blocked: the NBA game log has none per game, so Player.blka_nba* keeps the NBA's totals from
the last pull and ESPN-only games add their own on top (last N: the NBA's total scaled to the games
still in the window, as approximate as the NBA's own team-last-N filter). Technicals: NBA games from
the technical_fouls scan, ESPN games from ESPN's play-by-play.
"""
import pandas as pd

from fantasy_config import YEAR_START, YEAR_END
from fantasy_database import DB, Game, GameLine, Player

BOX = ['FGA', 'FGM', 'FTA', 'FTM', 'FG3M', 'PTS', 'AST', 'REB', 'STL', 'BLK', 'TOV', 'PF', 'PLUS_MINUS']


def season_label():
    return f'{YEAR_START}-{str(YEAR_END)[2:]}'


def _frame(rows):
    """game_lines rows as the game-log DataFrame apply_game_stats expects, newest first."""
    df = pd.DataFrame([{
        'GAME_ID': r.game_id, 'GAME_DATE': r.game_date.isoformat(), 'WL': 'W' if r.w else 'L',
        **{c: getattr(r, c.lower()) or 0 for c in BOX},
    } for r in rows])
    return df.sort_values('GAME_DATE', ascending=False)


def recompute(player, season):
    """Set the player's season / last-5 / last-10 totals from his game_lines rows of `season`."""
    from pull_api_data import apply_game_stats
    from pull_technical_fouls import technicals_by_player
    rows = list(GameLine.select().where((GameLine.player_id == player.id) & (GameLine.season == season))
                .order_by(GameLine.game_date.desc()))
    player.stats_season = season
    if not rows:
        player.gp = 0
        return
    nba_ids = [r.game_id for r in rows if r.source == 'nba']
    techs = technicals_by_player(nba_ids).get(player.id, {}) if nba_ids else {}
    techs.update({r.game_id: r.tech or 0 for r in rows if r.source == 'espn'})
    base = (player.blka_nba or 0, player.blka_nba_5 or 0, player.blka_nba_10 or 0) if nba_ids else (0, 0, 0)
    blka = []
    for total, n in zip(base, (None, 5, 10)):
        window = rows if n is None else rows[:n]
        espn = [r for r in window if r.source == 'espn']
        nba_part = total if n is None else round(total * (n - len(espn)) / n)
        blka.append(nba_part + sum(r.blka or 0 for r in espn))
    apply_game_stats(player, _frame(rows), techs, tuple(blka))


def store_nba(all_games, season):
    """Store the NBA game log (leaguegamelog, player mode) for `season`: its rows replace ESPN's,
    and ESPN rows before its latest night with no NBA twin are dropped."""
    if all_games is None or len(all_games) == 0:
        return
    rows = [{
        'player_id': int(r.PLAYER_ID), 'game_date': str(r.GAME_DATE)[:10], 'season': season, 'source': 'nba',
        'game_id': str(r.GAME_ID), 'team': r.TEAM_ABBREVIATION, 'w': int(r.WL == 'W'),
        'min': int(round(r.MIN or 0)), **{c.lower(): int(getattr(r, c) or 0) for c in BOX},
        'blka': None, 'tech': None,
    } for r in all_games.itertuples()]
    with DB.atomic():
        for i in range(0, len(rows), 500):
            GameLine.replace_many(rows[i:i + 500]).execute()
        latest = max(r['game_date'] for r in rows)
        GameLine.delete().where((GameLine.season == season) & (GameLine.source == 'espn')
                                & (GameLine.game_date < latest)).execute()


def fold_espn(day, lines, season=None):
    """Fold ESPN's final lines of one regular-season night in. lines: [(NBA player id, ESPN line)], each
    line carrying 'game_id' (ESPN's event id).
    Returns (folded, skipped). Skips (and leaves to the NBA pull) a player whose stored history
    doesn't account for every game he already played this season, and the whole night if the
    table is missing an earlier game night: totals are never built on a gap."""
    season = season or season_label()
    first = Game.select(Game.date).where(Game.date >= f'{YEAR_START}-07-01').order_by(Game.date).scalar()
    nights = {d for (d,) in Game.select(Game.date).where((Game.date >= first) & (Game.date < day)).distinct().tuples()} if first else set()
    covered = {d for (d,) in GameLine.select(GameLine.game_date)
               .where((GameLine.season == season) & (GameLine.game_date < day)).distinct().tuples()}
    if nights - covered:
        return 0, len(lines)
    folded = skipped = 0
    for pid, line in lines:
        player = Player.get_or_none(Player.id == pid) if pid else None
        if player is None:
            skipped += 1
            continue
        existing = GameLine.get_or_none((GameLine.player_id == pid) & (GameLine.game_date == day))
        if existing is not None and existing.source == 'nba':
            continue  # the NBA already has it
        prior = GameLine.select().where((GameLine.player_id == pid) & (GameLine.season == season)
                                        & (GameLine.game_date < day)).count()
        if prior != ((player.gp or 0) if player.stats_season == season else 0):
            skipped += 1
            continue
        with DB.atomic():
            GameLine.replace(
                player_id=pid, game_date=day, season=season, source='espn', game_id=f"espn{line['game_id']}",
                team=line['team'], w=line['W'], min=line['MIN'],
                **{c.lower(): int(line[c] or 0) for c in BOX}, blka=line['BLKA'], tech=line['TECH'],
            ).execute()
            recompute(player, season)
            player.save()
        folded += 1
    return folded, skipped
