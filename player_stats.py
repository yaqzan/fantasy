"""
Player statistics calculation.
Builds player_stats dictionary from fantasy_database data.
"""
from datetime import date
from statistics import NormalDist, mean, pstdev
from peewee import fn
from fantasy_database import Player, Team, Game
from fantasy_config import API_ATTRIBUTES, FPOINTS_SCORING
from leagues import CATEGORY_CATALOG


TIME_PERIODS = ['', '_5', '_10']
TIMEFRAMES = ['', '_5', '_10', '_projected']
Z_CAP = 3.0       # a category's z-score is capped at +/-Z_CAP before categories are summed
POOL_PASSES = 3   # re-rank passes that settle the draftable pool the z-scores are measured against
_NORMAL = NormalDist()
VALID_POSITIONS = ['C', 'F', 'G']
STAT_AVG_WEIGHTS = {'': 0.5, '_10': 0.5, '_5': 0.0}
TEAM_DICT = {
    'LA Clippers': 'Los Angeles Clippers',
    'LA Lakers': 'Los Angeles Lakers',
}

def is_preseason(today=None):
    """True from July 1 until the NBA season's first regular-season game (stored schedule): the
    players table still holds last season's stats."""
    today = today or date.today()
    season_start = date(today.year if today.month >= 7 else today.year - 1, 7, 1)
    first = Game.select(fn.MIN(Game.date)).where(Game.date >= season_start).scalar()
    return first is not None and today < first


# populates a full dictionary of player stats from the db
def load_player_stats():
    """
    Build player statistics dictionary from fantasy_database.
    
    Returns:
        dict: Player statistics keyed by player name
    """
    player_stats = {}
    team_win_percentages = {team.name: team.win_percentage for team in Team.select()}
    preseason = is_preseason()

    for player in Player.select().where(Player.team.is_null(False)).where(Player.pos.is_null(False)).where(Player.gp > 0):
        team_name = TEAM_DICT.get(player.team, player.team)
        player_stats[player.name] = {
            'TEAM': team_name,
            'Pos': player.pos,
            'GP': player.gp,
        }

        for n in TIME_PERIODS:
            gp = min(player.gp, int(n.replace('_', '')) if n else 100)
            player_stats[player.name][f'GP{n}'] = gp

            for key in API_ATTRIBUTES:
                player_stats[player.name][f'{key}{n}'] = getattr(player, f'{key.lower()}{n}', 0) / gp if getattr(player, f'{key.lower()}{n}', 0) is not None else 0

            player_stats[player.name][f'PLUS_MINUS{n}'] = getattr(player, f'plus_minus{n}', 0)
            player_stats[player.name][f'AST-TOV{n}'] = player_stats[player.name][f'AST{n}'] - player_stats[player.name][f'TOV{n}']
            player_stats[player.name][f'PPS{n}'] = player_stats[player.name][f'PTS{n}'] / player_stats[player.name][f'FGA{n}'] if player_stats[player.name][f'FGA{n}'] != 0 else 0
            player_stats[player.name][f'NFT{n}'] = 2 * player_stats[player.name][f'FTM{n}'] - player_stats[player.name][f'FTA{n}']
            player_stats[player.name][f'FG%{n}'] = player_stats[player.name][f'FGM{n}'] / player_stats[player.name][f'FGA{n}'] if player_stats[player.name][f'FGA{n}'] != 0 else 0
            player_stats[player.name][f'FT%{n}'] = player_stats[player.name][f'FTM{n}'] / player_stats[player.name][f'FTA{n}'] if player_stats[player.name][f'FTA{n}'] != 0 else 0
            player_stats[player.name][f'TS%{n}'] = player_stats[player.name][f'PTS{n}'] / (2 * (player_stats[player.name][f'FGA{n}'] + (0.44 * player_stats[player.name][f'FTA{n}']))) if player_stats[player.name][f'FGA{n}'] != 0 or player_stats[player.name][f'FTA{n}'] != 0 else 0
            player_stats[player.name][f'EFG%{n}'] = (player_stats[player.name][f'FGM{n}'] + 0.5 * player_stats[player.name][f'FG3M{n}']) / player_stats[player.name][f'FGA{n}'] if player_stats[player.name][f'FGA{n}'] != 0 else 0
            # Wins per game played. Before the season's first game (last season's stats, and after
            # the Oct 1 roster update maybe another team) and before player wins were ingested:
            # his current team's win %.
            player_stats[player.name][f'WIN%{n}'] = (
                (team_win_percentages.get(team_name) or 0) if preseason or player.w is None
                else player_stats[player.name][f'W{n}'])

        for stat in API_ATTRIBUTES + ['PLUS_MINUS']:
            player_stats[player.name][f'{stat}_projected'] = sum((player_stats[player.name].get(f'{stat}{n}', 0) or 0) * STAT_AVG_WEIGHTS[n] for n in STAT_AVG_WEIGHTS)

        player_stats[player.name]['FG%_projected'] = (
            (player_stats[player.name].get('FGM_projected', 0) or 0) / (player_stats[player.name].get('FGA_projected', 0) or 1)
            if (player_stats[player.name].get('FGA_projected', 0) or 0) != 0 else 0
        )
        
        player_stats[player.name]['FT%_projected'] = (
            (player_stats[player.name].get('FTM_projected', 0) or 0) / (player_stats[player.name].get('FTA_projected', 0) or 1)
            if (player_stats[player.name].get('FTA_projected', 0) or 0) != 0 else 0
        )

        player_stats[player.name]['TS%_projected'] = (
            (player_stats[player.name].get('PTS_projected', 0) or 0) / 
            (2 * ((player_stats[player.name].get('FGA_projected', 0) or 0) + 
                  (0.44 * (player_stats[player.name].get('FTA_projected', 0) or 0))))
            if ((player_stats[player.name].get('FGA_projected', 0) or 0) != 0 or 
                (player_stats[player.name].get('FTA_projected', 0) or 0) != 0) else 0
        )
        player_stats[player.name]['EFG%_projected'] = (
            ((player_stats[player.name].get('FGM_projected', 0) or 0) + 
             0.5 * (player_stats[player.name].get('FG3M_projected', 0) or 0)) / 
            (player_stats[player.name].get('FGA_projected', 0) or 1)
            if (player_stats[player.name].get('FGA_projected', 0) or 0) != 0 else 0
        )
        player_stats[player.name]['AST-TOV_projected'] = (
            (player_stats[player.name].get('AST_projected', 0) or 0) - 
            (player_stats[player.name].get('TOV_projected', 0) or 0)
        )
        player_stats[player.name]['PPS_projected'] = (
            (player_stats[player.name].get('PTS_projected', 0) or 0) / 
            (player_stats[player.name].get('FGA_projected', 0) or 1)
            if (player_stats[player.name].get('FGA_projected', 0) or 0) != 0 else 0
        )
        player_stats[player.name]['WIN%_projected'] = sum(player_stats[player.name][f'WIN%{n}'] * STAT_AVG_WEIGHTS[n] for n in STAT_AVG_WEIGHTS)
        player_stats[player.name]['NFT_projected'] = (
            2 * (player_stats[player.name].get('FTM_projected', 0) or 0) -
            (player_stats[player.name].get('FTA_projected', 0) or 0)
        )
        # Games behind the projected (blended) rate, same weights as the rate itself: ratio
        # shrinkage (_category_values) needs total attempts in every timeframe.
        player_stats[player.name]['GP_projected'] = sum(
            player_stats[player.name].get(f'GP{n}', 0) * STAT_AVG_WEIGHTS[n] for n in STAT_AVG_WEIGHTS
        )

    return player_stats

def _log5(p_a, p_b):
    """Chance team A beats team B from their win percentages."""
    p_a, p_b = min(max(p_a, 0.05), 0.95), min(max(p_b, 0.05), 0.95)
    return p_a * (1 - p_b) / (p_a * (1 - p_b) + p_b * (1 - p_a))

def week_schedule(week_start, week_end):
    """{NBA team: {game date: chance of winning}} for every game in the week."""
    win_pct = {team.name: team.win_percentage if team.win_percentage is not None else 0.5 for team in Team.select()}
    schedule = {}
    for game in Game.select().where(Game.date >= week_start, Game.date <= week_end):
        p_home = _log5(win_pct.get(game.team_home, 0.5), win_pct.get(game.team_away, 0.5))
        schedule.setdefault(game.team_home, {})[game.date] = p_home
        schedule.setdefault(game.team_away, {})[game.date] = 1 - p_home
    return schedule

def team_games(schedule):
    """{NBA team: games this week} from week_schedule()."""
    return {team: len(days) for team, days in schedule.items()}

def positions_ok(league, player_stats, lineup):
    """Whether a lineup meets the league's position minimums (every player has one position)."""
    if not (league.min_guards or league.min_forwards or league.min_centers):
        return True
    counts = {'C': 0, 'F': 0, 'G': 0}
    for p in lineup:
        pos = player_stats[p].get('Pos')
        if pos in counts:
            counts[pos] += 1
    return counts['G'] >= league.min_guards and counts['F'] >= league.min_forwards and counts['C'] >= league.min_centers


def best_starters(league, roster, player_stats, last_n_games=''):
    """The `active` players with the highest Z-SCORE that meet the position minimums.

    Each player has exactly one position, so this is exact: the best players of each required
    position up to its minimum, then the best of the rest. A position short of players stays
    short and its spots go to the best of the rest."""
    ranked = sorted((p for p in roster if p in player_stats),
                    key=lambda p: player_stats[p].get(f'Z-SCORE{last_n_games}', 0), reverse=True)
    size = min(league.active_slots, len(ranked))
    chosen = []
    for pos, minimum in (('C', league.min_centers), ('G', league.min_guards), ('F', league.min_forwards)):
        chosen += [p for p in ranked if player_stats[p].get('Pos') == pos][:minimum]
    chosen = chosen[:size]
    chosen += [p for p in ranked if p not in chosen][:size - len(chosen)]
    return chosen


def player_week_games(roster, player_stats, schedule, league, last_n_games='', unavailable=()):
    """Games and expected wins each rostered player contributes over the week.

    Daily lineups: each day only the best `active` players whose team plays that day count (best =
    Z-SCORE for the timeframe), so a deep bench adds little. Weekly lineups: every game of every
    player in `roster` counts. Players in `unavailable` (injured) contribute nothing.
    """
    games = {p: 0 for p in roster}
    wins = {p: 0.0 for p in roster}
    players = [p for p in roster if p in player_stats and p not in unavailable]
    if not league.daily_lineups:
        for p in players:
            days = schedule.get(player_stats[p]['TEAM'], {})
            games[p], wins[p] = len(days), sum(days.values())
        return games, wins
    by_day = {}
    for p in sorted(players, key=lambda p: player_stats[p].get(f'Z-SCORE{last_n_games}', 0), reverse=True):
        for day, p_win in schedule.get(player_stats[p]['TEAM'], {}).items():
            by_day.setdefault(day, []).append((p, p_win))
    for entries in by_day.values():
        for p, p_win in entries[:league.active_slots]:
            games[p] += 1
            wins[p] += p_win
    return games, wins

def calculate_team_totals(roster, player_stats, player_games, player_wins, categories, last_n_games=''):
    """Category totals for a group of players. Counting stats are per-game rate x games; ratios are
    built from summed components; wins are summed expected wins. Pass games of 1 for per-game totals."""
    players = [p for p in roster if p in player_stats]

    def total(stat):
        return sum((player_stats[p].get(f'{stat}{last_n_games}', 0) or 0) * player_games.get(p, 0) for p in players)

    totals = {'TOT': sum(player_games.get(p, 0) for p in players)}
    for category in categories:
        key = f'{category}{last_n_games}'
        if category == 'WIN%':
            totals[key] = sum(player_wins.get(p, 0) for p in players)
        elif category == 'TS%':
            denominator = 2 * (total('FGA') + 0.44 * total('FTA'))
            totals[key] = total('PTS') / denominator if denominator else 0
        elif category == 'EFG%':
            fga = total('FGA')
            totals[key] = (total('FGM') + 0.5 * total('FG3M')) / fga if fga else 0
        elif category == 'FG%':
            fga = total('FGA')
            totals[key] = total('FGM') / fga if fga else 0
        elif category == 'FT%':
            fta = total('FTA')
            totals[key] = total('FTM') / fta if fta else 0
        elif category == 'PPS':
            fga = total('FGA')
            totals[key] = total('PTS') / fga if fga else 0
        elif category == 'NFT':
            totals[key] = 2 * total('FTM') - total('FTA')
        else:
            totals[key] = total(category)
    return totals

def team_week_totals(players, player_stats, player_games, player_wins, categories, last_n_games=''):
    """{category: (total, variance)} for a team's week: calculate_team_totals' totals, and how far
    each can swing on game-to-game noise (CATEGORY_CATALOG `noise` / `attempt_sd`; wins as coin
    flips at each game's win chance)."""
    n = last_n_games
    totals = calculate_team_totals(players, player_stats, player_games, player_wins, categories, n)
    played = [p for p in players if p in player_stats and player_games.get(p)]

    def per_game(p, terms):
        return sum(coef * (1.0 if stat is None else abs(player_stats[p].get(f'{stat}{n}') or 0)) for stat, coef in terms)

    result = {}
    for category in categories:
        spec = CATEGORY_CATALOG[category]
        if spec['kind'] == 'wins':
            variance = 0.0
            for p in played:
                q = min(max(player_wins.get(p, 0) / player_games[p], 0.0), 1.0)
                variance += player_games[p] * q * (1 - q)
        elif spec['kind'] == 'ratio':
            attempts = sum(player_games[p] * per_game(p, spec['attempts']) for p in played)
            variance = spec['attempt_sd'] ** 2 / attempts if attempts else 0.0
        else:
            variance = sum(player_games[p] * per_game(p, spec['noise']) for p in played)
        result[category] = (totals.get(category + n, 0), variance)
    return result


def average_week_totals(teams):
    """A league-average team from several team_week_totals results: mean totals, mean variances."""
    return {c: (mean(t[c][0] for t in teams), mean(t[c][1] for t in teams)) for c in teams[0]}


def category_win_chances(mine, theirs, league):
    """{category: chance `mine` beats `theirs` this week}. Each weekly total is taken as normal
    around its projection with its team_week_totals variance; an exact tie counts as half."""
    chances = {}
    for category in league.categories:
        (a, var_a), (b, var_b) = mine[category], theirs[category]
        lead = (b - a) if category in league.inverse_categories else (a - b)
        sd = (var_a + var_b) ** 0.5
        chances[category] = _NORMAL.cdf(lead / sd) if sd > 0 else (1.0 if lead > 0 else 0.0 if lead < 0 else 0.5)
    return chances


def games_floor(player_stats):
    """Games a player needs for his numbers to count as more than a small sample: 15% of the most
    anyone has played this season, at least 5 (12 at the end of a full season)."""
    return max(5, round(0.15 * max((stats.get('GP') or 0 for stats in player_stats.values()), default=0)))


def _qualified_pool(player_stats):
    """Players whose stats may set a category's mean/SD (games_floor), so a 1-2 game call-up
    can't define the scale. Everyone qualifies while nobody has reached the floor yet."""
    floor = games_floor(player_stats)
    qualified = {name for name, stats in player_stats.items() if (stats.get('GP') or 0) >= floor}
    return qualified or set(player_stats)


def _category_values(player_stats, category, n, pool):
    """{player: the number category `category` is scored on in timeframe `n`}.

    Counting stats and wins: the per-game value. Ratio categories: impact, attempts per game x
    (rate - the pool's combined rate). A ratio only moves a team's ratio in proportion to the
    attempts behind it: .770 TS% on 3 shots a game barely moves a team, .665 on 23 moves it a lot.
    The rate is first blended with `prior` attempts of pool-average shooting (CATEGORY_CATALOG),
    so a few hot games don't read as talent."""
    key = category + n
    raw = {p: s[key] for p, s in player_stats.items() if s.get(key) is not None}
    spec = CATEGORY_CATALOG[category]
    if spec.get('kind') != 'ratio' or not spec.get('attempts'):
        return raw
    attempts = {p: sum(coef * (player_stats[p].get(f'{stat}{n}') or 0) for stat, coef in spec['attempts'])
                for p in raw}
    in_pool = [p for p in pool if p in raw]
    pool_attempts = sum(attempts[p] for p in in_pool)
    pool_rate = sum(raw[p] * attempts[p] for p in in_pool) / pool_attempts if pool_attempts else 0.0
    prior = spec.get('prior', 0)
    values = {}
    for p, rate in raw.items():
        total = attempts[p] * (player_stats[p].get(f'GP{n}') or 0)
        shrunk = (total * rate + prior * pool_rate) / (total + prior) if total + prior else pool_rate
        values[p] = attempts[p] * (shrunk - pool_rate)
    return values


def _z_scores(player_stats, categories, inverse, n, eligible, pool_size):
    """{player: {category: z}}, each z capped at +/-Z_CAP, measured against the draftable pool.

    The pool starts as every eligible player and becomes the top `pool_size` of them by summed z,
    re-ranked POOL_PASSES times: value is relative to the players who actually get drafted, not
    to hundreds of bench players (the average scorer in the whole pool is at 10 PPG, the average
    drafted one at 17)."""
    pool = sorted(eligible)
    z = {}
    for _ in range(POOL_PASSES):
        z = {p: {} for p in player_stats}
        for category in categories:
            values = _category_values(player_stats, category, n, pool)
            ref = [values[p] for p in pool if p in values]
            mu = mean(ref) if ref else 0.0
            sd = pstdev(ref) if len(ref) > 1 else 0.0
            sign = -1.0 if category in inverse else 1.0
            for p in player_stats:
                if p not in values:
                    z[p][category] = -Z_CAP
                else:
                    z[p][category] = max(-Z_CAP, min(Z_CAP, sign * (values[p] - mu) / sd)) if sd else 0.0
        pool = sorted(eligible, key=lambda p: sum(z[p].values()), reverse=True)[:pool_size]
    return z


def _category_display(z):
    """0-100 display scale for one category's z: 50 is the average drafted player, 0 and 100
    are -/+Z_CAP."""
    return 50.0 + 50.0 * z / Z_CAP


def _overall_display(player_stats, value_key, eligible, pool_size):
    """{player: 0-100 overall score}: 50 + 10 per standard deviation of `value_key` among the
    draftable pool (its top `pool_size` eligible players), so 50 is the average drafted player
    and the best players land in the 80s-90s."""
    pool = sorted(eligible, key=lambda p: player_stats[p][value_key], reverse=True)[:pool_size]
    ref = [player_stats[p][value_key] for p in pool]
    mu = mean(ref) if ref else 0.0
    sd = pstdev(ref) if len(ref) > 1 else 0.0
    return {p: max(0.0, min(100.0, 50.0 + 10.0 * (s[value_key] - mu) / sd)) if sd else 50.0
            for p, s in player_stats.items()}


def calculate_overall_scores(player_stats, league, punt_categories=()):
    """Category z-scores and overall value for every player, per timeframe.

    For each category, a player's per-game value (ratios: impact, see _category_values) is turned
    into a z-score against the draftable pool (see _z_scores) and capped at +/-Z_CAP. The cap
    keeps one freak number from outweighing whole categories (Dillon Brooks' technical fouls sit
    6.8 SD out) while a real specialist still counts in full up to 3 SD. Categories are then
    summed, so each one is worth the same, as in the league's scoring. Scarce stats are weighted
    by their spread: one block is worth about sixteen points.

    Keys written, per timeframe n ('', '_5', '_10', '_projected'):
      SCORE-{cat}{n}     one category, 0-100: 50 + 50 * z / Z_CAP (50 = average drafted player)
      VALUE{n}, RANK{n}  summed z over every category, and the rank by it
      Z-VALUE{n}, Z-RANK{n}  summed z over the categories not punted, and the rank by it
      SCORE{n}, Z-SCORE{n}   VALUE / Z-VALUE as 0-100 display scores (see _overall_display)
    Punted categories keep their SCORE-{cat} and count in VALUE, but not in Z-VALUE.
    """
    if not player_stats:
        return
    categories = league.categories
    inverse = set(league.inverse_categories)
    scored = [c for c in categories if c not in punt_categories]
    eligible = _qualified_pool(player_stats)
    pool_size = max(league.num_teams * league.roster_size, 1)

    for n in TIMEFRAMES:
        z_all = _z_scores(player_stats, categories, inverse, n, eligible, pool_size)
        z_scored = (z_all if len(scored) == len(categories)
                    else _z_scores(player_stats, scored, inverse, n, eligible, pool_size))
        for p, stats in player_stats.items():
            for category in categories:
                stats[f'SCORE-{category}{n}'] = _category_display(z_all[p][category])
            stats[f'VALUE{n}'] = sum(z_all[p][c] for c in categories)
            stats[f'Z-VALUE{n}'] = sum(z_scored[p][c] for c in scored)

        for rank_key, value_key, score_key in ((f'RANK{n}', f'VALUE{n}', f'SCORE{n}'),
                                               (f'Z-RANK{n}', f'Z-VALUE{n}', f'Z-SCORE{n}')):
            display = _overall_display(player_stats, value_key, eligible, pool_size)
            ranked = sorted(player_stats, key=lambda p: player_stats[p][value_key], reverse=True)
            for i, p in enumerate(ranked, start=1):
                player_stats[p][rank_key] = i
                player_stats[p][score_key] = display[p]

def calculate_fantasy_points(player_stats):
    for player_name, stats in player_stats.items():
        for n in ['', '_5', '_10', '_projected']:
            fpoints = 0
            for stat, multiplier in FPOINTS_SCORING.items():
                stat_key = f'{stat}{n}'
                fpoints += stats.get(stat_key, 0) * multiplier
            player_stats[player_name][f'FPOINTS{n}'] = round(fpoints, 2)
    
    for n in ['', '_5', '_10', '_projected']:
        sorted_by_fpoints = sorted(player_stats.items(), key=lambda kv: kv[1].get(f'FPOINTS{n}', 0), reverse=True)
        for i, (key, val) in enumerate(sorted_by_fpoints, start=1):
            player_stats[key][f'FPOINTS-RANK{n}'] = i

def calculate_auction_values(player_stats, league, price_exponent=None, value_key='VALUE', out_key='AUCTION_VALUE'):
    """Whole-dollar auction values by value over replacement, written to `out_key`.

    The num_teams x roster-size players who get drafted each cost at least $1. The rest of the
    league's money is split by how far each sits above replacement (the best player left
    undrafted), raised to `price_exponent`: 1 is linear, above 1 pays stars more. The default is
    the league's draft.price_exponent. Undrafted players are $1. Rounded so the drafted players
    add up to exactly the league's budget."""
    if price_exponent is None:
        price_exponent = league.price_exponent
    ranked = sorted(player_stats, key=lambda p: player_stats[p].get(value_key, 0), reverse=True)
    for p in ranked:
        player_stats[p][out_key] = 1
    drafted = ranked[:league.num_teams * league.roster_size]
    if not drafted:
        return
    undrafted = ranked[len(drafted):]
    replacement = (player_stats[undrafted[0]][value_key] if undrafted
                   else min(player_stats[p][value_key] for p in drafted))
    surplus = {p: max(player_stats[p][value_key] - replacement, 0.0) ** price_exponent for p in drafted}
    total_surplus = sum(surplus.values())
    spend = max(league.num_teams * league.budget - len(drafted), 0)
    exact = {p: 1 + (surplus[p] / total_surplus * spend if total_surplus else spend / len(drafted))
             for p in drafted}
    # Largest remainder: floor everything, then hand the leftover dollars to the biggest fractions.
    dollars = {p: int(v) for p, v in exact.items()}
    leftover = league.num_teams * league.budget - sum(dollars.values())
    for p in sorted(drafted, key=lambda p: exact[p] - dollars[p], reverse=True)[:max(leftover, 0)]:
        dollars[p] += 1
    for p, v in dollars.items():
        player_stats[p][out_key] = v

