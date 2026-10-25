"""The in-season update of the projection: preseason-adjusted prior + this season's games.

One estimate per stat, per game:   (K x prior + sum of w x game) / (K + sum of w)
w = 1 for older games, 1 + R for his last RECENT_GAMES. K = games the prior is worth, R = extra weight on the
recent games. Constants fit on 2016-2022, scored on 2023-2025 (.horizon/preseason-2026/inseason.py; results in
.claude/docs/projections.md "In-season update"). Stats the fit doesn't cover borrow a neighbour's."""

RECENT_GAMES = 10
# stat -> (K, R)
FIT = {
    'MIN': (16, 2), 'PTS': (12, 1), 'REB': (16, 1), 'AST': (12, 1), 'STL': (32, 0), 'BLK': (32, 0.5),
    'FG3M': (16, 0.5), 'TOV': (16, 0.5), 'FGA': (16, 2), 'FGM': (16, 1), 'FTA': (16, 0.5), 'FTM': (16, 0.5),
}
FOLLOW = {'BLKA': 'FGA', 'PF': 'MIN', 'DD2': 'PTS', 'TD3': 'PTS', 'TECH': 'STL'}   # unfitted stats take this stat's K, R


def constants(stat):
    return FIT.get(stat) or FIT[FOLLOW.get(stat, 'PTS')]


def blend(stat, prior, total, recent_total, games, recent_games):
    """Per-game estimate of `stat`: `total` over `games` games this season, `recent_total` over the last `recent_games`
    of them (also inside `total`), `prior` per game from the preseason-adjusted projection."""
    k, r = constants(stat)
    return (prior * k + total + r * recent_total) / (k + games + r * recent_games)
