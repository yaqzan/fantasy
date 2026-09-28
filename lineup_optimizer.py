"""Weekly matchup analysis: best lineup, best waiver pickup, and manual pickup/drop what-ifs.

Everything is scoped to one league (leagues.LeagueConfig):
- weekly-lineup leagues pick `active` starters from the healthy roster (position minimums apply);
- daily-lineup leagues score the best `active` players of each day (player_week_games), so the
  "lineup" is the whole roster and a pickup means choosing which player to drop.

    python lineup_optimizer.py [--league <id>] [--timeframe projected|season|5|10] [--pickup]
"""
from itertools import combinations

from fantasy_database import FantasyTeam, FantasyTeamPlayer
from player_stats import (load_player_stats, calculate_overall_scores, calculate_team_totals, week_schedule,
                          team_games, player_week_games, positions_ok, best_starters, team_week_totals,
                          average_week_totals, category_win_chances, games_floor)
from fantasy_team_helper import (get_my_team_players, get_all_my_team_players, get_opponent_team_players,
                                 get_available_players, get_current_fantasy_week_dates, get_undroppable_players,
                                 get_injured_players)

TIMEFRAME_SUFFIX = {'': '', 'season': '', '5': '_5', '10': '_10', 'projected': '_projected'}


def timeframe_suffix(timeframe):
    return TIMEFRAME_SUFFIX.get(timeframe or '', '')


def calculate_category_weight(category):
    """(variance, weight): how swingy a category is week to week, and how much to trust a lead in it."""
    weights = {
        'PTS': (0.15, 1.0),
        'FG3M': (0.25, 0.9),
        'AST': (0.25, 0.9),
        'TOV': (0.35, 0.80),
        'AST-TOV': (0.30, 0.85),
        'REB': (0.20, 0.95),
        'STL': (0.35, 0.80),
        'BLK': (0.35, 0.80),
        'BLKA': (0.35, 0.80),
        'TECH': (0.50, 0.65),
        'WIN%': (0.30, 0.85),
        'EFG%': (0.10, 1.0),
        'TS%': (0.12, 0.95),
        'FT%': (0.20, 0.95),
        'PF': (0.30, 0.85),
        'PLUS_MINUS': (0.25, 0.90),
        'DD2': (0.30, 0.80),
        'NFT': (0.20, 0.95)
    }
    return weights.get(category, (0.25, 1.0))


def calculate_lineup_score(the_stats, their_stats, league, last_n_games=''):
    """
    Value of a lineup against the opponent's totals.

    :return: tuple: (lineup_value, categories won)
    """
    inverse = league.inverse_categories
    weighted_margins = {}
    the_score = 0

    for category in league.categories:
        key = category + last_n_games
        stat, their_stat = the_stats.get(key, 0), their_stats.get(key, 0)
        denominator = (abs(stat) + abs(their_stat)
                       if category == 'PLUS_MINUS'
                       else abs(their_stat) if category in inverse
                       else abs(stat))

        if category in inverse:
            margin = (-1.0 if denominator == 0 and stat < 0
                      else 1.0 if denominator == 0
                      else (their_stat - stat) / denominator)
        else:
            margin = (1.0 if denominator == 0 and their_stat < 0
                      else -1.0 if denominator == 0
                      else (stat - their_stat) / denominator)

        variance, weight = calculate_category_weight(category)
        weighted_margins[category] = margin * (1 - variance) * weight
        if margin > 0:
            the_score += 1

    winning_margins = [m for m in weighted_margins.values() if m > 0]
    if not winning_margins:
        return float('-inf'), 0

    risk_penalty = 0
    for category, margin in weighted_margins.items():
        if margin > 0:
            variance, _ = calculate_category_weight(category)
            if margin < 0.1 and variance > 0.25:
                risk_penalty += variance * 0.5

    lineup_value = (
        the_score * 15 +
        min(winning_margins) * 8 +
        sum(winning_margins) / len(winning_margins) * 4 -
        risk_penalty * 2
    )
    return lineup_value, the_score


class Week:
    """Everything the analysis of one league-week needs, loaded once."""

    def __init__(self, league, week_start, week_end):
        self.league = league
        self.week_start, self.week_end = week_start, week_end
        self.player_stats = load_player_stats()
        calculate_overall_scores(self.player_stats, league)
        self.schedule = week_schedule(week_start, week_end)
        self.games_played = team_games(self.schedule)
        self.injured = set(get_injured_players())

    def totals(self, lineup, suffix):
        """(category totals, games per player) for a lineup over this week."""
        lineup = [p for p in lineup if p in self.player_stats]
        games, wins = player_week_games(lineup, self.player_stats, self.schedule, self.league, suffix, self.injured)
        return calculate_team_totals(lineup, self.player_stats, games, wins, self.league.categories, suffix), games

    def positions_ok(self, lineup):
        return positions_ok(self.league, self.player_stats, lineup)

    def best_lineup(self, pool, their_stats, suffix, required=()):
        """Best lineup_size-player lineup from pool: (value, lineup, totals, categories won)."""
        pool = [p for p in dict.fromkeys(pool) if p in self.player_stats]
        size = min(self.league.lineup_size, len(pool))
        required = [p for p in required if p in pool]
        best = (float('-inf'), None, None, 0)
        for lineup in combinations(pool, size):
            if any(p not in lineup for p in required) or not self.positions_ok(lineup):
                continue
            stats, _ = self.totals(lineup, suffix)
            value, score = calculate_lineup_score(stats, their_stats, self.league, suffix)
            if best[1] is None or value > best[0]:
                best = (value, list(lineup), stats, score)
        return best


def _my_pool(league, week):
    """Players the optimizer may play: in daily-lineup leagues the whole roster (injured players
    hold a spot but score nothing, so dropping them shows up as a real gain), else the healthy ones."""
    return get_all_my_team_players(league) if league.daily_lineups else get_my_team_players(league)


def _opponent_lineup(league, week, their_players, suffix):
    """The opponent's scoring players: whole healthy roster in daily leagues, else their best starters."""
    their_players = [p for p in their_players if p in week.player_stats]
    if league.daily_lineups or len(their_players) <= league.lineup_size:
        return their_players
    rank_key = f'Z-RANK{suffix}'
    return sorted(their_players, key=lambda p: week.player_stats[p].get(rank_key) or 999)[:league.lineup_size]


def _matchup(league, week, lineup, their_lineup, suffix):
    """Category-by-category comparison dict for the frontend."""
    the_stats, my_games = week.totals(lineup, suffix)
    their_stats, their_games = week.totals(their_lineup, suffix)
    _, score = calculate_lineup_score(the_stats, their_stats, league, suffix) if lineup else (0, 0)
    categories = {}
    for category in league.categories:
        key = category + suffix
        mine, theirs = the_stats.get(key, 0), their_stats.get(key, 0)
        categories[category] = {'your_team': mine, 'opponent': theirs,
                                'margin': theirs - mine if category in league.inverse_categories else mine - theirs}
    return {'score': score, 'categories': categories, 'my_team_player_games': my_games,
            'their_team_player_games': their_games, 'best_stats': the_stats, 'their_stats': their_stats}


def _resolve_week(league, week_start, week_end, opponent):
    if not (week_start and week_end):
        week_start, week_end, opponent = get_current_fantasy_week_dates(league)
    return week_start, week_end, opponent


def get_analysis_data(league, timeframe, week_start=None, week_end=None, opponent_team_name=None, pickup=False,
                      pickup_timeframe=None):
    """
    Structured matchup analysis for the API.

    :param league: leagues.LeagueConfig
    :param str timeframe: stats compared: 'projected', '5', '10', or 'season'/'' (season average)
    :param bool pickup: find the best waiver pickup (and the drop it forces) instead of the current roster
    :param str pickup_timeframe: stats used to choose the pickup (defaults to timeframe)
    """
    week_start, week_end, opponent_team_name = _resolve_week(league, week_start, week_end, opponent_team_name)
    if not opponent_team_name:
        return {'error': "No opponent for this week: add the matchup schedule in the league's settings"}
    their_players = get_opponent_team_players(league, week_start.strftime('%Y-%m-%d'))
    if not their_players:
        return {'error': f"No players on {opponent_team_name}'s roster in this league yet"}

    suffix = timeframe_suffix(timeframe)
    week = Week(league, week_start, week_end)
    their_lineup = _opponent_lineup(league, week, their_players, suffix)
    their_stats, _ = week.totals(their_lineup, suffix)
    my_pool = _my_pool(league, week)
    undroppable = get_undroppable_players(league)
    available = get_available_players(league, week.player_stats)

    if pickup:
        pick_suffix = timeframe_suffix(pickup_timeframe) if pickup_timeframe else suffix
        their_pick_stats, _ = week.totals(_opponent_lineup(league, week, their_players, pick_suffix), pick_suffix)
        best_value, the_lineup, _, _ = week.best_lineup(my_pool, their_pick_stats, pick_suffix, undroppable)
        for combo in combinations(sorted(available), league.claims_per_week):
            value, lineup, _, _ = week.best_lineup(my_pool + list(combo), their_pick_stats, pick_suffix, undroppable)
            if lineup is not None and value > best_value:
                best_value, the_lineup = value, lineup
    else:
        _, the_lineup, _, _ = week.best_lineup(my_pool, their_stats, suffix, undroppable)
    the_lineup = the_lineup or list(my_pool)

    matchup = _matchup(league, week, the_lineup, their_lineup, suffix)
    all_mine = get_all_my_team_players(league)
    matchup_data = {
        'opponent': opponent_team_name,
        'score': matchup['score'],
        'week_start': week_start.strftime('%Y-%m-%d'),
        'week_end': week_end.strftime('%Y-%m-%d'),
        'my_team_player_games': matchup['my_team_player_games'],
        'their_team_player_games': matchup['their_team_player_games'],
        'timeframe': timeframe,
        'is_pickup': pickup,
        'pickups': [p for p in the_lineup if p not in all_mine],
        'drops': [p for p in my_pool if p not in the_lineup and p not in undroppable],
        'categories': matchup['categories'],
    }
    z_key = 'Z-SCORE_projected'
    return {
        'matchup': matchup_data,
        'timeframe': timeframe,
        'best_stats': matchup['best_stats'],
        'their_stats': matchup['their_stats'],
        'best_lineup': the_lineup,
        'games_played': week.games_played,
        'fantasy_schedule': league.schedule,
        'undroppable_players': undroppable,
        'available_players': sorted(available, key=lambda p: week.player_stats[p].get(z_key, 0), reverse=True),
        'all_my_team_players': all_mine,
        'num_starters': league.lineup_size,
        'active_slots': league.active_slots,
        'daily_lineups': league.daily_lineups,
        'num_categories': len(league.categories),
    }


def _week_team(week, players, suffix):
    """(team_week_totals, games, wins) for a roster's week. Daily-lineup leagues let
    player_week_games pick each day's best `active` from all of them; weekly-lineup leagues count
    their best healthy starters."""
    league = week.league
    players = [p for p in players if p in week.player_stats]
    if not league.daily_lineups:
        players = best_starters(league, [p for p in players if p not in week.injured], week.player_stats, suffix)
    games, wins = player_week_games(players, week.player_stats, week.schedule, league, suffix, week.injured)
    return team_week_totals(players, week.player_stats, games, wins, league.categories, suffix), games, wins


def _week_opponent(league, week, week_start, opponent_team_name, suffix):
    """(label, weekly totals) that pickups are judged against: the week's opponent once its roster
    is in; else the average of the league's other rostered teams; else (None, None), meaning an
    opponent exactly as strong as my team."""
    if opponent_team_name:
        theirs = get_opponent_team_players(league, week_start.strftime('%Y-%m-%d'))
        if theirs:
            return opponent_team_name, _week_team(week, theirs, suffix)[0]
    others = []
    for team in FantasyTeam.select().where((FantasyTeam.league == league.id) & (FantasyTeam.abv != league.my_team)):
        roster = [ftp.player_name for ftp in FantasyTeamPlayer.select().where(FantasyTeamPlayer.fantasy_team_id == team.id)]
        if any(p in week.player_stats for p in roster):
            others.append(_week_team(week, roster, suffix)[0])
    if others:
        return 'league average', average_week_totals(others)
    return None, None


def get_pickup_candidates(league, week_start=None, week_end=None, opponent_team_name=None, timeframe='projected',
                          limit=40, pool=150):
    """Free agents ranked by how many more categories they'd win me this week: one pickup and the
    drop that suits him best (or an open roster spot).

    Uses the NBA schedule: only games his team plays count, and in daily-lineup leagues only on
    days he'd crack my best `active` (player_week_games). Wins are the summed chances of his team
    winning each of those games, so 4-5 games against weak teams add up. Each category's weekly
    total gets a win chance against the opponent (_week_opponent) from its projection and
    game-to-game noise (team_week_totals, category_win_chances); gain = change in the sum of those
    chances. `pool`: how many free agents with games to try, best Z-VALUE first."""
    week_start, week_end, opponent_team_name = _resolve_week(league, week_start, week_end, opponent_team_name)
    suffix = timeframe_suffix(timeframe)
    week = Week(league, week_start, week_end)
    stats = week.player_stats
    roster = get_all_my_team_players(league)
    if not any(p in stats for p in roster):
        return {'error': f"No players on your team ({league.my_team or 'set Your team in the league settings'}) "
                         "in this league yet"}

    base, base_games, base_wins = _week_team(week, roster, suffix)
    label, theirs = _week_opponent(league, week, week_start, opponent_team_name, suffix)
    theirs = theirs or base
    base_chances = category_win_chances(base, theirs, league)
    base_expected = sum(base_chances.values())

    undroppable = set(get_undroppable_players(league))
    drops = [p for p in roster if p not in undroppable] + ([None] if len(roster) < league.roster_size else [])
    playing = [p for p in get_available_players(league, stats) if week.schedule.get(stats[p]['TEAM'])]
    playing = sorted(playing, key=lambda p: stats[p].get(f'Z-VALUE{suffix}', 0), reverse=True)[:pool]

    floor = games_floor(stats)
    candidates = []
    for pickup in playing:
        best = None
        for drop in drops:
            totals, games, wins = _week_team(week, [p for p in roster if p != drop] + [pickup], suffix)
            chances = category_win_chances(totals, theirs, league)
            gain = sum(chances.values()) - base_expected
            if best is None or gain > best[0]:
                best = (gain, drop, totals, games, wins, chances)
        gain, drop, totals, games, wins, chances = best
        days = sorted(week.schedule[stats[pickup]['TEAM']])
        candidates.append({
            'name': pickup, 'team': stats[pickup]['TEAM'], 'position': stats[pickup].get('Pos'),
            'gp': stats[pickup].get('GP') or 0, 'small_sample': (stats[pickup].get('GP') or 0) < floor,
            'games': len(days), 'days': [d.isoformat() for d in days],
            'plays': games.get(pickup, 0), 'expected_wins': round(wins.get(pickup, 0.0), 2),
            'score': round(stats[pickup].get(f'Z-SCORE{suffix}', 0), 1),
            'gain': round(gain, 3), 'drop': drop,
            'category_changes': {c: totals[c][0] - base[c][0] for c in league.categories},
            'chance_changes': {c: round(chances[c] - base_chances[c], 3) for c in league.categories},
        })
    candidates.sort(key=lambda c: (c['gain'], c['score']), reverse=True)
    return {
        'week_start': week_start.isoformat(), 'week_end': week_end.isoformat(), 'timeframe': timeframe,
        'opponent': label, 'expected_categories': round(base_expected, 2),
        'my_week': {c: {'total': base[c][0], 'opponent': theirs[c][0], 'chance': round(base_chances[c], 3)}
                    for c in league.categories},
        'candidates': candidates[:limit], 'tried': len(playing), 'claims_per_week': league.claims_per_week,
    }


def get_custom_analysis(league, week_start, week_end, opponent_team_name, pickup, drop=None):
    """What-if: add `pickup` (dropping `drop`), re-pick the best lineup, compare in every timeframe."""
    their_players = get_opponent_team_players(league, week_start.strftime('%Y-%m-%d'))
    if not opponent_team_name or not their_players:
        return {'error': 'No opponent roster for this week'}
    week = Week(league, week_start, week_end)
    pool = [p for p in _my_pool(league, week) if p != drop] + ([pickup] if pickup else [])
    undroppable = get_undroppable_players(league)
    result = {}
    for key, timeframe in (('current', 'season'), ('last_5', '5'), ('last_10', '10'), ('projected', 'projected')):
        suffix = timeframe_suffix(timeframe)
        their_lineup = _opponent_lineup(league, week, their_players, suffix)
        their_stats, _ = week.totals(their_lineup, suffix)
        _, lineup, _, _ = week.best_lineup(pool, their_stats, suffix, undroppable)
        matchup = _matchup(league, week, lineup or pool, their_lineup, suffix)
        result[key] = {'score': matchup['score'], 'categories': matchup['categories'], 'opponent': opponent_team_name,
                       'my_team_player_games': matchup['my_team_player_games'],
                       'their_team_player_games': matchup['their_team_player_games'],
                       'lineup': lineup or pool}
    return result


def main(league=None, timeframe='projected', pickup=False):
    """Print this week's matchup analysis for a league (default: the active one).

    :param str league: league id
    :param str timeframe: projected, season, 5 or 10
    :param bool pickup: look for the best waiver pickup
    """
    from leagues import get_league, CATEGORY_CATALOG
    config = get_league(league)
    data = get_analysis_data(config, timeframe, pickup=pickup)
    if 'error' in data:
        print(data['error'])
        return
    m = data['matchup']
    print(f"{config.name}: week of {m['week_start']} vs {m['opponent']} ({timeframe})")
    print(f"projected {m['score']}-{len(config.categories) - m['score']}")
    for category, row in m['categories'].items():
        mark = '+' if row['margin'] > 0 else '-' if row['margin'] < 0 else '='
        print(f"  {mark} {CATEGORY_CATALOG[category]['label']:>5}  {row['your_team']:9.2f}  {row['opponent']:9.2f}")
    if m['pickups']:
        print(f"pick up: {', '.join(m['pickups'])}")
    if m['drops']:
        print(f"{'drop' if pickup or config.daily_lineups else 'bench'}: {', '.join(m['drops'])}")


if __name__ == '__main__':
    import defopt
    defopt.run(main)
