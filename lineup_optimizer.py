"""Weekly matchups: a roster's week against its opponent, the pickups that help most, and what-ifs.

One model for the Lineup Optimizer, Weekly Pickups and this CLI. A team's week is the games its
players make the lineup for (player_week_games: daily leagues fill each day's slots, weekly
leagues play their best starters every game). Each category total has a variance from game-to-game
noise, and the chance of beating the opponent in it is normal on the difference
(category_win_chances). A roster's value is its expected categories won; a points league has one
category (FPTS), so that is its chance of winning the week.

    python lineup_optimizer.py [--league <id>] [--timeframe projected|season|5|10|proj] [--moves]
"""
from collections import namedtuple

from fantasy_database import FantasyTeam, FantasyTeamPlayer
from player_stats import (league_player_stats, week_schedule, player_week_games, best_starters, team_week_totals,
                          average_week_totals, category_win_chances, category_margins, games_floor, STAT_SUFFIXES)
from fantasy_team_helper import (get_all_my_team_players, get_available_players, get_current_fantasy_week_dates,
                                 get_undroppable_players, get_injured_players, get_team_by_abv)

Side = namedtuple('Side', 'totals games wins')          # a roster's week: team_week_totals, games, wins per player
# One pickup (add) for one drop (None = open spot). gain: change in expected categories won;
# key: what moves are ranked by (gain, then the margin tie-break, see _value).
Move = namedtuple('Move', 'key gain add drop side chances')
MARGIN_WEIGHT = 0.01  # a whole SD of lead in a category counts as 1% of a category won
MOVE_POOL = 150      # free agents with games this week tried per claim, best Z-VALUE first
NEXT_CLAIM_POOL = 30  # later claims only retry the best candidates of the claim before


def timeframe_suffix(timeframe):
    return STAT_SUFFIXES.get(timeframe or 'projected', '_projected')


def _roster(team):
    return [ftp.player_name for ftp in FantasyTeamPlayer.select().where(FantasyTeamPlayer.fantasy_team_id == team.id)]


class Week:
    """Everything one league-week needs, loaded once: stats as the league sees them, the NBA
    schedule, injuries."""

    def __init__(self, league, week_start, week_end):
        self.league = league
        self.week_start, self.week_end = week_start, week_end
        self.stats = league_player_stats(league)
        self.schedule = week_schedule(week_start, week_end)
        self.injured = set(get_injured_players())

    def team(self, players, suffix):
        """Side for a roster. Weekly-lineup leagues count their best healthy starters' games."""
        league = self.league
        players = [p for p in players if p in self.stats]
        if not league.daily_lineups:
            players = list(best_starters(league, [p for p in players if p not in self.injured], self.stats, suffix))
        games, wins = player_week_games(players, self.stats, self.schedule, league, suffix, self.injured)
        return Side(team_week_totals(players, self.stats, games, wins, league.categories, suffix), games, wins)

    def opponent(self, opponent_abv, suffix):
        """(label, weekly totals) a roster is judged against: the week's opponent once its roster is
        in, else the average of the league's other teams still playing, else (None, None)."""
        league = self.league
        team = get_team_by_abv(league, opponent_abv) if opponent_abv else None
        if team is not None and any(p in self.stats for p in _roster(team)):
            return team.name, self.team(_roster(team), suffix).totals
        others = [self.team(roster, suffix).totals
                  for roster in (_roster(t) for t in FantasyTeam.select().where(
                      (FantasyTeam.league == league.id) & (FantasyTeam.abv != league.my_team)
                      & FantasyTeam.eliminated_stage.is_null()))
                  if any(p in self.stats for p in roster)]
        return ('league average', average_week_totals(others)) if others else (None, None)

    def free_agents(self, suffix, pool=MOVE_POOL):
        """The best `pool` free agents (by Z-VALUE) whose team plays this week."""
        playing = [p for p in get_available_players(self.league, self.stats) if self.schedule.get(self.stats[p]['TEAM'])]
        return sorted(playing, key=lambda p: self.stats[p].get(f'Z-VALUE{suffix}', 0), reverse=True)[:pool]


def _value(totals, theirs, league):
    """(expected categories won, ranking value). The ranking value adds MARGIN_WEIGHT x the summed
    leads in SDs, so once a category is as good as won or lost (a points league against a much
    weaker team) a bigger margin still ranks higher instead of every move tying at 0. At 0.01 a
    10-SD swing is worth a tenth of a category: a tie-break, never a reason to give up a win."""
    chances = category_win_chances(totals, theirs, league)
    margins = category_margins(totals, theirs, league)
    expected = sum(chances.values())
    lead = sum(z for z in margins.values() if abs(z) != float('inf'))
    return expected, expected + MARGIN_WEIGHT * lead, chances


def rank_moves(week, roster, theirs, suffix, candidates, keep=()):
    """Every candidate with the drop that suits him best, best first. `keep`: players that can't
    be dropped (undroppable, or added by an earlier claim)."""
    league = week.league
    base_expected, base_key, base = _value(week.team(roster, suffix).totals, theirs, league)
    drops = [p for p in roster if p not in keep] + ([None] if len(roster) < league.roster_size else [])
    moves = []
    for add in candidates:
        best = None
        for drop in drops:
            side = week.team([p for p in roster if p != drop] + [add], suffix)
            expected, key, chances = _value(side.totals, theirs, league)
            if best is None or key - base_key > best.key:
                best = Move(key - base_key, expected - base_expected, add, drop, side, chances)
        if best:
            moves.append(best)
    moves.sort(key=lambda m: m.key, reverse=True)
    return moves, base


def best_moves(week, roster, theirs, suffix, keep, claims):
    """Up to `claims` pickups, greedily: the best single move, then the best move on top of it,
    until the week's claims run out or nothing helps. Exhaustive search over claim combinations is
    out of reach (5 claims from 150 free agents); later claims retry the best NEXT_CLAIM_POOL
    candidates of the claim before."""
    moves, roster, keep = [], list(roster), set(keep)
    candidates = week.free_agents(suffix)
    for _ in range(claims):
        ranked, _ = rank_moves(week, roster, theirs, suffix, candidates, keep)
        if not ranked or ranked[0].key <= 1e-4:
            break
        move = ranked[0]
        moves.append(move)
        roster = [p for p in roster if p != move.drop] + [move.add]
        keep.add(move.add)
        candidates = [m.add for m in ranked[1:NEXT_CLAIM_POOL + 1]]
    return moves, roster


def _side_json(week, side, theirs, suffix):
    """A roster's week for the frontend: per category my total, theirs and my chance; per player
    the games his team plays and the ones he'd count for."""
    league, stats = week.league, week.stats
    chances = category_win_chances(side.totals, theirs, league) if theirs else {}
    return {
        'expected': round(sum(chances.values()), 2) if theirs else None,
        'categories': {c: {'mine': side.totals[c][0], 'theirs': theirs[c][0] if theirs else None,
                           'chance': round(chances[c], 3) if theirs else None} for c in league.categories},
        'players': sorted(({'name': p, 'positions': list(stats[p]['Positions']), 'plays': side.games.get(p, 0),
                            'games': len(week.schedule.get(stats[p]['TEAM'], {})), 'injured': p in week.injured,
                            'score': round(stats[p].get(f'Z-SCORE{suffix}', 0), 1)}
                           for p in side.games), key=lambda r: (-r['plays'], -r['score'])),
    }


def _resolve_week(league, week_start, week_end, opponent):
    if not (week_start and week_end):
        week_start, week_end, opponent = get_current_fantasy_week_dates(league)
    return week_start, week_end, opponent


def get_matchup(league, timeframe='projected', week_start=None, week_end=None, opponent_abv=None,
                adds=(), drops=(), moves=False):
    """The Lineup Optimizer: my roster's week against the opponent (league average until the
    opponent's roster is in; no comparison when there's neither). `adds`/`drops`: a what-if roster.
    `moves`: the best pickups for the week's claims (best_moves)."""
    week_start, week_end, opponent_abv = _resolve_week(league, week_start, week_end, opponent_abv)
    suffix = timeframe_suffix(timeframe)
    week = Week(league, week_start, week_end)
    roster = get_all_my_team_players(league)
    if not any(p in week.stats for p in roster):
        return {'error': f"No players on your team ({league.my_team or 'set Your team in the league settings'}) "
                         "in this league yet"}
    label, theirs = week.opponent(opponent_abv, suffix)
    undroppable = get_undroppable_players(league)
    result = {
        'week_start': week_start.isoformat(), 'week_end': week_end.isoformat(),
        'days': (week_end - week_start).days + 1, 'timeframe': timeframe,
        'opponent': label, 'scheduled_opponent': opponent_abv,
        'current': _side_json(week, week.team(roster, suffix), theirs, suffix),
        'roster': roster, 'undroppable': undroppable, 'claims_per_week': league.claims_per_week,
        'free_agents': sorted(get_available_players(league, week.stats),
                              key=lambda p: week.stats[p].get(f'Z-VALUE{suffix}', 0), reverse=True)[:400],
    }
    if adds or drops:
        what_if = [p for p in roster if p not in drops] + [p for p in adds if p in week.stats and p not in roster]
        result['what_if'] = {**_side_json(week, week.team(what_if, suffix), theirs, suffix),
                             'adds': list(adds), 'drops': list(drops)}
    if moves:
        steps, final = best_moves(week, roster, theirs or week.team(roster, suffix).totals, suffix,
                                  undroppable, league.claims_per_week)
        result['moves'] = {**_side_json(week, week.team(final, suffix), theirs, suffix),
                           'steps': [{'add': m.add, 'drop': m.drop, 'gain': round(m.gain, 3)} for m in steps]}
    return result


def get_pickup_candidates(league, week_start=None, week_end=None, opponent_abv=None, timeframe='projected',
                          limit=40):
    """Weekly Pickups: free agents ranked by how many more categories they'd win me this week, each
    with the drop that suits him best (or an open spot). Only his team's games count, and in
    daily-lineup leagues only the days he'd make my lineup. Judged against Week.opponent, else a
    copy of my team (an even match)."""
    week_start, week_end, opponent_abv = _resolve_week(league, week_start, week_end, opponent_abv)
    suffix = timeframe_suffix(timeframe)
    week = Week(league, week_start, week_end)
    stats = week.stats
    roster = get_all_my_team_players(league)
    if not any(p in stats for p in roster):
        return {'error': f"No players on your team ({league.my_team or 'set Your team in the league settings'}) "
                         "in this league yet"}
    mine = week.team(roster, suffix).totals
    label, theirs = week.opponent(opponent_abv, suffix)
    theirs = theirs or mine
    undroppable = set(get_undroppable_players(league))
    if len(roster) >= league.roster_size and all(p in undroppable for p in roster):
        return {'error': 'Your roster is full and every player on it is marked undroppable'}
    candidates = week.free_agents(suffix)
    ranked, base = rank_moves(week, roster, theirs, suffix, candidates, undroppable)
    floor = games_floor(stats)
    rows = []
    for m in ranked[:limit]:
        p = stats[m.add]
        days = sorted(week.schedule[p['TEAM']])
        rows.append({
            'name': m.add, 'team': p['TEAM'], 'positions': list(p['Positions']),
            'gp': p.get('GP') or 0, 'small_sample': (p.get('GP') or 0) < floor,
            'games': len(days), 'days': [d.isoformat() for d in days],
            'plays': m.side.games.get(m.add, 0), 'expected_wins': round(m.side.wins.get(m.add, 0.0), 2),
            'score': round(p.get(f'Z-SCORE{suffix}', 0), 1), 'gain': round(m.gain, 3), 'drop': m.drop,
            'category_changes': {c: m.side.totals[c][0] - mine[c][0] for c in league.categories},
            'chance_changes': {c: round(m.chances[c] - base[c], 3) for c in league.categories},
        })
    return {
        'week_start': week_start.isoformat(), 'week_end': week_end.isoformat(), 'timeframe': timeframe,
        'opponent': label, 'expected_categories': round(sum(base.values()), 2),
        'my_week': {c: {'total': mine[c][0], 'opponent': theirs[c][0], 'chance': round(base[c], 3)}
                    for c in league.categories},
        'candidates': rows, 'tried': len(candidates), 'claims_per_week': league.claims_per_week,
    }


def main(league=None, timeframe='projected', moves=False):
    """Print this week's matchup for a league (default: the active one).

    :param str league: league id
    :param str timeframe: projected, season, 5, 10 or proj
    :param bool moves: also find the best pickups for the week's claims
    """
    from leagues import get_league, CATEGORY_CATALOG
    config = get_league(league)
    data = get_matchup(config, timeframe, moves=moves)
    if 'error' in data:
        print(data['error'])
        return
    current = data['current']
    against = data['opponent'] or 'opponent TBD'
    print(f"{config.name}: {data['week_start']} to {data['week_end']} vs {against} ({timeframe})")
    if current['expected'] is not None:
        print(f"expected categories won: {current['expected']} of {len(config.categories)}")
    for category, row in current['categories'].items():
        theirs = '' if row['theirs'] is None else f"{row['theirs']:9.2f}  {row['chance']:4.0%}"
        print(f"  {CATEGORY_CATALOG[category]['label']:>5}  {row['mine']:9.2f}  {theirs}")
    for step in data.get('moves', {}).get('steps', []):
        print(f"  + {step['add']}  - {step['drop'] or 'open spot'}  (+{step['gain']:.2f})")


if __name__ == '__main__':
    import defopt
    defopt.run(main)
