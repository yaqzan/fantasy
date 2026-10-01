"""League rules that change who scores: roster slots, daily lineups, points vs categories.

    py -m pytest test_league_rules.py

No database: leagues are built from settings documents, players are synthetic.
"""
import json
from datetime import date, timedelta
from types import SimpleNamespace

from leagues import LeagueConfig, validate_settings, slot_reach
from player_stats import calculate_auction_values, fill_slots, player_week_games, team_week_totals

WEEK = [date(2026, 10, 26) + timedelta(days=i) for i in range(7)]
SCHEDULE = {'Team': {day: 0.5 for day in WEEK}}  # every player's team plays every day

# Shapes of the three kinds of league the app serves (no real league's data).
POSITIONS_POINTS = {'scoring': {'type': 'points', 'points': {'PTS': 1, 'REB': 1.25, 'AST': 2}},
                    'roster': {'size': 13, 'active': 9, 'daily_lineups': True,
                               'slots': ['PG', 'SG', 'G', 'SF', 'PF', 'F', 'C', 'UTIL', 'UTIL']}}
ALL_FLEX_CATEGORIES = {'categories': ['PTS', 'REB', 'AST', 'STL', 'BLK', 'FG3M', 'TOV', 'TS%', 'WIN%'],
                       'roster': {'size': 10, 'active': 6, 'daily_lineups': True}}


def league(settings):
    return LeagueConfig(SimpleNamespace(id='t', name='t', is_active=True, settings=json.dumps(settings)))


def players(positions):
    """Identical players (same stats) that differ only in positions."""
    stats = {}
    for i, pos in enumerate(positions):
        stats[f'p{i}'] = {'TEAM': 'Team', 'Positions': pos, 'Reach': frozenset(slot_reach(pos)), 'Z-SCORE': 50.0,
                          'PTS': 20.0, 'REB': 8.0, 'AST': 5.0, 'STL': 1.0, 'BLK': 1.0, 'FG3M': 2.0, 'TOV': 2.0,
                          'FGA': 15.0, 'FGM': 7.0, 'FTA': 4.0, 'FTM': 3.0, 'WIN%': 0.5, 'GP': 60}
        stats[f'p{i}']['FPTS'] = 20 + 1.25 * 8 + 2 * 5
    return stats


def week_totals(lg, stats):
    roster = list(stats)
    games, wins = player_week_games(roster, stats, SCHEDULE, lg)
    return team_week_totals(roster, stats, games, wins, lg.categories), sum(games.values())


BALANCED = [('PG',), ('SG',), ('G',), ('SF',), ('PF',), ('F',), ('C',), ('C',), ('G', 'F')]
CENTERS = [('C',)] * 9


def test_nine_centers_score_less_with_slots():
    lg = league(POSITIONS_POINTS)
    balanced, balanced_games = week_totals(lg, players(BALANCED))
    centers, center_games = week_totals(lg, players(CENTERS))
    assert balanced_games == 9 * 7            # every slot filled every day
    assert center_games == 3 * 7              # C + 2 UTIL only
    assert centers['FPTS'][0] < balanced['FPTS'][0]


def test_nine_centers_score_the_same_all_flex():
    lg = league(ALL_FLEX_CATEGORIES)
    balanced, _ = week_totals(lg, players(BALANCED))
    centers, _ = week_totals(lg, players(CENTERS))
    assert balanced == centers


def test_fill_slots_reshuffles_for_a_better_player():
    # p0 (G/F) would take SG first; p1 (G only) still gets in because p0 moves to F.
    stats = {'p0': {'Positions': ('G', 'F')}, 'p1': {'Positions': ('SG',)}}
    assert set(fill_slots(['p0', 'p1'], ['SG', 'F'], stats)) == {'p0', 'p1'}


def test_minimums_upgrade_to_slots():
    s = validate_settings({'roster': {'active': 6, 'min_guards': 2, 'min_forwards': 1, 'min_centers': 1},
                           'fantrax_league_id': 'abc'})
    assert s['roster']['slots'] == ['G', 'G', 'F', 'C', 'UTIL', 'UTIL']
    assert 'min_guards' not in s['roster'] and s['platform_league_id'] == 'abc'


def test_auction_values_skip_ineligible_players():
    """A high per-game value on too few (projected) games is not priced: $1, and the money goes to the rest."""
    league = SimpleNamespace(num_teams=2, roster_size=2, budget=10, price_exponent=1.0)
    stats = {'thin': {'VALUE_proj': 9.0, 'GP_proj': 10, 'ELIGIBLE_proj': False}}
    stats.update({f'p{i}': {'VALUE_proj': float(5 - i), 'GP_proj': 82, 'ELIGIBLE_proj': True} for i in range(6)})
    calculate_auction_values(stats, league, value_key='VALUE_proj', out_key='A')
    assert stats['thin']['A'] == 1
    assert sum(stats[f'p{i}']['A'] for i in range(4)) == 20
    assert stats['p0']['A'] > stats['p3']['A'] >= 1 and stats['p4']['A'] == 1


def test_auction_value_at_prices_extra_value():
    from player_stats import auction_value_at
    league = SimpleNamespace(num_teams=1, roster_size=3, budget=88, price_exponent=1.0)
    stats = {'full': {'VALUE_proj': 5.0, 'GP_proj': 82, 'ELIGIBLE_proj': True},
             'half': {'VALUE_proj': 5.0, 'GP_proj': 41, 'ELIGIBLE_proj': True},
             'low': {'VALUE_proj': 1.0, 'GP_proj': 82, 'ELIGIBLE_proj': True},
             'out': {'VALUE_proj': 0.0, 'GP_proj': 82, 'ELIGIBLE_proj': True}}
    assert auction_value_at(stats, league, 'low', 0.0) == 11       # as priced: 1 + 10
    assert auction_value_at(stats, league, 'low', 1.0) == 21       # twice the surplus
    assert auction_value_at(stats, league, 'out', 1.0) == 11       # an undrafted player reaching 'low'
    assert auction_value_at(stats, league, 'half', 5.0) == 51      # games share applies to the extra too


def test_projection_prices_count_projected_games():
    """Same per-game value, half the projected games: about half the surplus $."""
    league = SimpleNamespace(num_teams=1, roster_size=3, budget=88, price_exponent=1.0)
    stats = {'full': {'VALUE_proj': 5.0, 'GP_proj': 82, 'ELIGIBLE_proj': True},
             'half': {'VALUE_proj': 5.0, 'GP_proj': 41, 'ELIGIBLE_proj': True},
             'low': {'VALUE_proj': 1.0, 'GP_proj': 82, 'ELIGIBLE_proj': True},
             'out': {'VALUE_proj': 0.0, 'GP_proj': 82, 'ELIGIBLE_proj': True}}
    calculate_auction_values(stats, league, value_key='VALUE_proj', out_key='A')
    assert stats['full']['A'] - 1 == 2 * (stats['half']['A'] - 1)
    assert sum(stats[p]['A'] for p in ('full', 'half', 'low')) == 88
