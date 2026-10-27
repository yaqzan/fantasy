"""Weekly matchups: a roster's week against its opponent, the pickups that help most, and what-ifs.

One model for the Lineup Optimizer, Weekly Pickups and this CLI. A team's week is the games its
players make the lineup for (player_week_games: daily leagues fill each day's slots, weekly
leagues play their best starters every game). Each category total has a variance from game-to-game
noise, and the chance of beating the opponent in it is normal on the difference
(category_win_chances). A roster's value is its expected categories won; a points league has one
category (FPTS), so that is its chance of winning the week.

    python lineup_optimizer.py [league] [timeframe] [moves] [plan]   # plan: a guillotine stage's claims, week by week
"""
from collections import namedtuple
from datetime import date, timedelta
from statistics import mean

from fantasy_database import FantasyTeam, FantasyTeamPlayer
from player_stats import (league_player_stats, week_schedule, player_week_games, best_starters, team_week_totals,
                          calculate_team_totals, AVAILABILITY,
                          average_week_totals, category_win_chances, category_margins, small_sample_floor, STAT_SUFFIXES, default_stat_type)
from week_actuals import week_actuals, lineup_of
from fantasy_team_helper import (get_all_my_team_players, my_il_players, claims_left, get_available_players, get_waiver_dates, get_current_fantasy_week_dates,
                                 get_undroppable_players, get_injured_players, get_day_to_day_players, get_team_by_abv)

Side = namedtuple('Side', 'totals games wins carried')  # a roster's week: team_week_totals, games, wins per player, the played part (week_actuals)
# One pickup (add) for one drop (None = open spot), made on `day`: the add plays from that day, the drop until
# the day before (a mid-week claim; player_week_games `windows`). gain: change in expected categories won;
# key: what moves are ranked by (gain, then the margin tie-break, see _value).
Move = namedtuple('Move', 'key gain add drop side chances day')
MARGIN_WEIGHT = 0.01  # a whole SD of lead in a category counts as 1% of a category won
MOVE_POOL = 250      # free agents with games this week tried per claim, best Z-VALUE first (the best move
                     # sat at rank 130 of 421 on 2026-10-13, so 150 was cutting it close)
NEXT_CLAIM_POOL = 30  # later claims only retry the best candidates of the claim before


def timeframe_suffix(timeframe):
    """The key suffix of a stats choice. Callers pass the league's `default_stat_type`."""
    return STAT_SUFFIXES.get(timeframe or 'projected', '_projected')


def _active_roster(league):
    """(my roster without the injured-list slot, the injured-list players): IL players hold no spot and score nothing."""
    il = my_il_players(league)
    return [p for p in get_all_my_team_players(league) if p not in il], sorted(il)


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
        self.doubtful = get_day_to_day_players()   # {name: chance he plays his next game}
        # A week under way: games already played are facts (self.actual), the model projects only the rest.
        self.actual = week_actuals(week_start, week_end)
        self.remaining, self.day_weights = self.actual.remaining(self.schedule) if self.actual else (self.schedule, None)
        self.waivers = get_waiver_dates(league)   # {free agent: the day he clears waivers}
        self.opponent_now = None   # {category: total so far} of the opponent Week.opponent last returned

    @property
    def start_day(self):
        """The first day a claim can take effect: today in a week under way, else the week's first day."""
        return max(self.week_start, self.actual.today) if self.actual else self.week_start

    def add_games(self, name):
        """The days of his team's games a claim could still catch (unplayed, not under way, and not before he
        clears waivers: a claim on him lands on that day), earliest first."""
        team = self.stats[name]['TEAM']
        tipped = self.actual.tipped if self.actual else ()
        first = max(self.start_day, self.waivers.get(name, self.start_day))
        return sorted(d for d in self.remaining.get(team, {}) if d >= first and (team, d) not in tipped)

    def add_days(self, name):
        """The days a pickup can start from, earliest first: now (a drop that is not worth keeping goes at once), then
        each of his team's games that has not tipped (adding him later keeps the drop's earlier games)."""
        games = self.add_games(name)
        if not games:
            return []
        return sorted({max(self.start_day, self.waivers.get(name, self.start_day)), *games})

    def can_drop_on(self, name, day):
        """A player whose team's game is under way is locked in his slot: no claim can drop him that day."""
        return not (self.actual and (self.stats.get(name, {}).get('TEAM'), day) in self.actual.tipped)

    def team(self, players, suffix, owned=None, windows=None):
        """Side for a roster. Weekly-lineup leagues count their best healthy starters' games.
        `owned`: who the played games belong to (default `players`). A what-if roster passes today's: a
        pickup adds only the games still to play, a drop keeps the games he already played for you.
        `windows`: {player: (first day, last day)} for mid-week adds and drops (player_week_games)."""
        league = self.league
        players = [p for p in players if p in self.stats]
        owned = [p for p in (owned if owned is not None else players) if p in self.stats]
        if not league.daily_lineups:
            players = list(best_starters(league, [p for p in players if p not in self.injured], self.stats, suffix))
        carried, locked, taken = None, (), None
        if self.actual:
            starters = None if league.daily_lineups else set(best_starters(league, owned, self.stats, suffix))
            carried = self.actual.carried(owned, self.stats, league, suffix, starters)
            lineups = lineup_of(self.actual, owned, suffix)
            locked = {(p, day) for day, got in lineups.items() for p in got}
            taken = {day: len(got) for day, got in lineups.items()}
        games, wins, game_var = player_week_games(players, self.stats, self.remaining, league, suffix, self.injured,
                                                  availability=AVAILABILITY, variance=True, day_weights=self.day_weights,
                                                  tipped=self.actual.tipped if self.actual else (), locked=locked, taken=taken,
                                                  windows=windows, doubtful=self.doubtful)
        totals = team_week_totals(players, self.stats, games, wins, league.categories, suffix, game_var, carried)
        return Side(totals, games, wins, carried)

    def so_far(self, carried):
        """{category: total so far} for a played part (week_actuals carried), or None before the first game."""
        if carried is None:
            return None
        totals = calculate_team_totals([], self.stats, {}, {}, self.league.categories, '', carried)
        return {c: totals[c] for c in self.league.categories}

    def opponent(self, opponent_abv, suffix):
        """(label, weekly totals) a roster is judged against: the week's opponent once its roster is
        in, else the average of the league's other teams still playing, else (None, None)."""
        league = self.league
        team = get_team_by_abv(league, opponent_abv) if opponent_abv else None
        if team is not None and any(p in self.stats for p in _roster(team)):
            side = self.team(_roster(team), suffix)
            self.opponent_now = self.so_far(side.carried)
            return team.name, side.totals
        sides = [self.team(roster, suffix)
                 for roster in (_roster(t) for t in FantasyTeam.select().where(
                     (FantasyTeam.league == league.id) & (FantasyTeam.abv != league.my_team)
                     & FantasyTeam.eliminated_stage.is_null()))
                 if any(p in self.stats for p in roster)]
        others = [side.totals for side in sides]
        nows = [self.so_far(side.carried) for side in sides]
        self.opponent_now = {c: mean(n[c] for n in nows) for c in league.categories} if nows and all(nows) else None
        return ('league average', average_week_totals(others)) if others else (None, None)

    def free_agents(self, suffix, pool=MOVE_POOL):
        """The best `pool` free agents (by Z-VALUE) with a game left that a claim made now could still catch."""
        playing = [p for p in get_available_players(self.league, self.stats) if self.add_days(p)]
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


def _claim_windows(base, add, drop, day):
    """`base` plus one claim made on `day`: the add plays from it, the drop until the day before."""
    windows = dict(base or {})
    windows[add] = (day, None)
    if drop:
        first, last = windows.get(drop, (None, None))
        before = day - timedelta(days=1)
        windows[drop] = (first, before if last is None else min(last, before))
    return windows


def rank_moves(week, roster, theirs, suffix, candidates, keep=(), owned=None, windows=None, ghosts=()):
    """Every candidate with the drop and the day that suit him best, best first. `keep`: players that
    can't be dropped (undroppable, or added by an earlier claim). `owned`: whose played games count
    (Week.team). `windows`/`ghosts`: earlier claims of the same plan (best_moves): a player dropped
    earlier still plays the days before his drop.

    A daily-lineup claim can be made on any day, and the day matters: DeRozan plays Monday and Tuesday,
    so a pickup whose games start Wednesday should replace him on Wednesday, not now. For each candidate
    every drop is tried for an immediate claim, then the other start days with the drops that did best
    (and the weakest players), the full search being too slow."""
    league = week.league
    owned = roster if owned is None else owned
    daily = league.daily_lineups
    base_expected, base_key, base = _value(week.team(list(roster) + list(ghosts), suffix, owned, windows).totals, theirs, league)
    drops = [p for p in roster if p not in keep] + ([None] if len(roster) < league.roster_size else [])
    weakest = sorted((p for p in drops if p), key=lambda p: week.stats[p].get(f'Z-SCORE{suffix}', 0) if p in week.stats else -1e9)[:3]
    moves = []

    def play(add, drop, day):
        if drop and not week.can_drop_on(drop, day):
            return None
        if daily:
            side = week.team(list(roster) + list(ghosts) + [add], suffix, owned, _claim_windows(windows, add, drop, day))
        else:    # a weekly lineup is set once: the swap is for the whole week
            side = week.team([p for p in roster if p != drop] + [add], suffix, owned)
        expected, key, chances = _value(side.totals, theirs, league)
        return Move(key - base_key, expected - base_expected, add, drop, side, chances, day)

    for add in candidates:
        options = week.add_days(add)
        if not options:
            continue
        if not daily:
            options = options[:1]
        # Every drop is scored for a claim at his first playable game (options[0] is "now", which only differs
        # when the drop is worth losing before then); the other days try the best of those drops and the weakest players.
        first = week.add_games(add)[0] if daily else options[0]
        tried = [m for m in (play(add, drop, first) for drop in drops) if m]
        best = max(tried, key=lambda m: m.key, default=None)
        if len(options) > 1:
            ranked_drops = [m.drop for m in sorted(tried, key=lambda m: m.key, reverse=True)]
            blocked = [d for d in drops if d and not week.can_drop_on(d, first)]    # locked at `first`: only a later claim can drop them
            for i, day in enumerate(options):
                if day == first:
                    continue
                if day > first:
                    # a later day only beats the day before it when the drop plays in between
                    plays_between = lambda d: d is not None and any(
                        options[i - 1] <= g < day for g in week.remaining.get(week.stats.get(d, {}).get('TEAM'), {}))
                    shortlist = [d for d in ranked_drops + blocked if plays_between(d)]    # every drop who plays in between
                else:
                    shortlist = ranked_drops[:3] + weakest + blocked
                for drop in dict.fromkeys(shortlist):
                    m = play(add, drop, day)
                    if m and (best is None or m.key > best.key):
                        best = m
        if best:
            moves.append(best)
    moves.sort(key=lambda m: m.key, reverse=True)
    return moves, base


def best_moves(week, roster, theirs, suffix, keep, claims, owned=None):
    """Up to `claims` pickups, greedily: the best single move, then the best move on top of it,
    until the week's claims run out or nothing helps. Exhaustive search over claim combinations is
    out of reach (5 claims from 150 free agents); later claims retry the best NEXT_CLAIM_POOL
    candidates of the claim before. Returns (moves, everyone who plays: the final roster plus players
    dropped on the way, the claims' windows)."""
    owned = list(roster if owned is None else owned)
    moves, roster, keep = [], list(roster), set(keep)
    ghosts, windows = [], {}
    candidates = week.free_agents(suffix)
    for _ in range(claims):
        ranked, _ = rank_moves(week, roster, theirs, suffix, candidates, keep, owned, windows, ghosts)
        if not ranked or ranked[0].key <= 1e-4:
            break
        move = ranked[0]
        moves.append(move)
        if week.league.daily_lineups:
            windows = _claim_windows(windows, move.add, move.drop, move.day)
            ghosts += [move.drop] if move.drop else []
        roster = [p for p in roster if p != move.drop] + [move.add]
        keep.add(move.add)
        candidates = [m.add for m in ranked[1:NEXT_CLAIM_POOL + 1]]
    return moves, roster + ghosts, windows


def _side_json(week, side, theirs, suffix, theirs_now=None):
    """A roster's week for the frontend: per category my total, theirs and my chance (whole-week
    totals: the played part plus the projection); with a game played, what each side has so far
    (now_mine / now_theirs) and the categories I lead; per player the games his team plays and the
    ones he'd count for."""
    league, stats = week.league, week.stats
    chances = category_win_chances(side.totals, theirs, league) if theirs else {}
    mine_now = week.so_far(side.carried)
    return {
        'expected': round(sum(chances.values()), 2) if theirs else None,
        'leading': _leading(mine_now, theirs_now, league) if mine_now and theirs_now else None,
        'categories': {c: {'mine': side.totals[c][0], 'theirs': theirs[c][0] if theirs else None,
                           'chance': round(chances[c], 3) if theirs else None,
                           'now_mine': mine_now[c] if mine_now else None,
                           'now_theirs': theirs_now[c] if theirs_now else None} for c in league.categories},
        'players': sorted(({'name': p, 'positions': list(stats[p]['Positions']), 'plays': round(side.games.get(p, 0), 1),
                            'games': len(week.schedule.get(stats[p]['TEAM'], {})), 'injured': p in week.injured,
                            'days': sorted(d.isoformat() for d in week.schedule.get(stats[p]['TEAM'], {})),
                            # the games a claim could still catch: unplayed and not under way
                            'open_days': sorted(d.isoformat() for d in week.remaining.get(stats[p]['TEAM'], {})
                                                if not (week.actual and (stats[p]['TEAM'], d) in week.actual.tipped)),
                            'score': round(stats[p].get(f'Z-SCORE{suffix}', 0), 1)}
                           for p in side.games), key=lambda r: (-r['plays'], -r['score'])),
    }


def _leading(mine, theirs, league):
    """Categories I am ahead in right now (an exact tie counts as half)."""
    lead = 0.0
    for c in league.categories:
        a, b = mine[c], theirs[c]
        if c in league.inverse_categories:
            a, b = b, a
        lead += 1.0 if a > b else 0.5 if a == b else 0.0
    return lead


def _progress(week):
    actual = week.actual
    return {'started': bool(actual), 'today': actual.today.isoformat() if actual else None,
            'live': actual.live if actual else 0, 'final': actual.final if actual else 0,
            'partial': actual.partial if actual else False}


def _resolve_week(league, week_start, week_end, opponent):
    if not (week_start and week_end):
        week_start, week_end, opponent = get_current_fantasy_week_dates(league)
    return week_start, week_end, opponent


def get_matchup(league, timeframe='projected', week_start=None, week_end=None, opponent_abv=None,
                adds=(), drops=(), moves=False, day=None):
    """The Lineup Optimizer: my roster's week against the opponent (league average until the
    opponent's roster is in; no comparison when there's neither). `adds`/`drops`: a what-if roster.
    `day`: the claim date of the what-if (default: now; a pickup plays from it, a drop until the day
    before). `moves`: the best pickups for the week's claims (best_moves)."""
    week_start, week_end, opponent_abv = _resolve_week(league, week_start, week_end, opponent_abv)
    suffix = timeframe_suffix(timeframe)
    week = Week(league, week_start, week_end)
    roster, il = _active_roster(league)
    if not any(p in week.stats for p in roster):
        return {'error': f"No players on your team ({league.my_team or 'set Your team in the league settings'}) "
                         "in this league yet"}
    label, theirs = week.opponent(opponent_abv, suffix)
    undroppable = get_undroppable_players(league)
    claims = claims_left(league, week_start)
    owned = roster + il          # whose played games count: an injured-list player keeps what he played for you
    mine = week.team(roster, suffix, owned)
    theirs_now = week.opponent_now
    result = {
        'progress': _progress(week),
        'week_start': week_start.isoformat(), 'week_end': week_end.isoformat(),
        'days': (week_end - week_start).days + 1, 'timeframe': timeframe,
        'opponent': label, 'scheduled_opponent': opponent_abv,
        'current': _side_json(week, mine, theirs, suffix, theirs_now),
        'roster': roster, 'il': il, 'undroppable': undroppable, 'claims_per_week': league.claims_per_week,
        'claims_left': claims,
        'free_agents': sorted(get_available_players(league, week.stats),
                              key=lambda p: week.stats[p].get(f'Z-VALUE{suffix}', 0), reverse=True)[:400],
    }
    opponent_team = get_team_by_abv(league, opponent_abv) if opponent_abv else None
    if label and label != 'league average' and opponent_team is not None:
        # players only: theirs=None skips the category chances this would throw away
        result['opponent_players'] = _side_json(week, week.team(_roster(opponent_team), suffix), None, suffix)['players']
    if adds or drops:
        added = [p for p in adds if p in week.stats and p not in roster]
        what_if = [p for p in roster if p not in drops] + added
        start = max(day, week.start_day) if day else week.start_day
        locked_drop = next((p for p in drops if p in week.stats and not week.can_drop_on(p, start)), None) if league.daily_lineups else None
        if day and not (week.week_start <= day <= week.week_end):
            result['what_if'] = {'error': f'{day.isoformat()} is outside this week'}
        elif locked_drop:
            result['what_if'] = {'error': f"{locked_drop}'s game is under way, so he can't be dropped before tomorrow"}
        elif len(what_if) > league.roster_size:
            result['what_if'] = {'error': f"That roster has {len(what_if)} players and the league allows "
                                          f"{league.roster_size}: drop {len(what_if) - league.roster_size} more"}
        else:
            windows = {}
            if league.daily_lineups:
                for p in added:
                    windows[p] = (start, None)
                for p in drops:
                    windows[p] = (None, start - timedelta(days=1))
            players = what_if + ([p for p in drops if p in roster] if windows else [])
            result['what_if'] = {**_side_json(week, week.team(players, suffix, owned, windows), theirs, suffix, theirs_now),
                                 'adds': list(adds), 'drops': list(drops), 'day': start.isoformat(),
                                 'day_options': {p: [d.isoformat() for d in week.add_days(p)] if league.daily_lineups else [] for p in added}}
    if moves:
        steps, final, windows = best_moves(week, roster, theirs or mine.totals, suffix,
                                           undroppable, claims, owned)
        result['moves'] = {**_side_json(week, week.team(final, suffix, owned, windows), theirs, suffix, theirs_now),
                           'steps': [{'add': m.add, 'drop': m.drop, 'day': m.day.isoformat(), 'gain': round(m.gain, 3),
                                      'add_score': round(week.stats[m.add].get(f'Z-SCORE{suffix}', 0), 1),
                                      'drop_score': round(week.stats[m.drop].get(f'Z-SCORE{suffix}', 0), 1) if m.drop else None}
                                     for m in steps]}
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
    roster, il = _active_roster(league)
    if not any(p in stats for p in roster):
        return {'error': f"No players on your team ({league.my_team or 'set Your team in the league settings'}) "
                         "in this league yet"}
    owned = roster + il
    mine = week.team(roster, suffix, owned).totals
    label, theirs = week.opponent(opponent_abv, suffix)
    theirs = theirs or mine
    undroppable = set(get_undroppable_players(league))
    if len(roster) >= league.roster_size and all(p in undroppable for p in roster):
        return {'error': 'Your roster is full and every player on it is marked undroppable'}
    candidates = week.free_agents(suffix)
    ranked, base = rank_moves(week, roster, theirs, suffix, candidates, undroppable, owned)
    floor = small_sample_floor(stats)
    rows = []
    for m in ranked[:limit]:
        p = stats[m.add]
        team = p['TEAM']
        tipped = week.actual.tipped if week.actual else ()
        days = sorted(d for d in week.remaining.get(team, {}) if d >= m.day and (team, d) not in tipped)   # his games from the claim day
        rows.append({
            'name': m.add, 'team': p['TEAM'], 'positions': list(p['Positions']),
            'gp': p.get('GP') or 0, 'small_sample': (p.get('GP') or 0) < floor,
            'games': len(days), 'days': [d.isoformat() for d in days], 'day': m.day.isoformat(),
            'day_options': [d.isoformat() for d in week.add_days(m.add)] if league.daily_lineups else [],   # a weekly lineup is set once
            'plays': round(m.side.games.get(m.add, 0), 1), 'expected_wins': round(m.side.wins.get(m.add, 0.0), 2),
            'score': round(p.get(f'Z-SCORE{suffix}', 0), 1), 'gain': round(m.gain, 3), 'drop': m.drop,
            'drop_score': round(stats[m.drop].get(f'Z-SCORE{suffix}', 0), 1) if m.drop else None,
            'category_changes': {c: m.side.totals[c][0] - mine[c][0] for c in league.categories},
            'chance_changes': {c: round(m.chances[c] - base[c], 3) for c in league.categories},
        })
    return {
        'week_start': week_start.isoformat(), 'week_end': week_end.isoformat(), 'timeframe': timeframe,
        'today': week.actual.today.isoformat() if week.actual else None,
        'opponent': label, 'expected_categories': round(sum(base.values()), 2),
        'my_week': {c: {'total': mine[c][0], 'opponent': theirs[c][0], 'chance': round(base[c], 3)}
                    for c in league.categories},
        'candidates': rows, 'tried': len(candidates), 'claims_per_week': league.claims_per_week,
        'claims_left': claims_left(league, week_start), 'il': il,
    }


def plan_stage(league, timeframe='projected', beam=4, alternatives=5):
    """The claims for the rest of the current guillotine stage, week by week. Each week has
    `claims_per_week` claims, the roster carries over, and every week is judged against that
    week's scheduled opponent (the league average where its roster isn't in). A beam search keeps
    the `beam` best rosters by summed expected categories won, so a pickup that only pays off a
    week later (a 4-game week next, a better matchup) still shows. The stage's weeks only: the
    pool of eliminated teams' players and next stage's opponents aren't known yet.
    Per week: the claim(s), the week's expected categories before and after, and `alternatives`
    next-best claims on that path (the blind auction can be lost)."""
    info = league.stage_info()
    if not info or info.get('stage') is None:
        return {'error': 'This league has no stage in play (not a guillotine league, or the season is over)'}
    suffix = timeframe_suffix(timeframe)
    today = date.today().isoformat()
    weeks = [w for w in league.weeks()[info['first_week'] - 1:info['last_week']] if w['end'] >= today]
    if not weeks:
        return {'error': 'No weeks left in this stage'}
    roster = get_all_my_team_players(league)
    undroppable = set(get_undroppable_players(league))
    owned0 = list(roster)    # the current week's played games belong to today's roster, not to a path's claims
    states = [(0.0, roster, undroppable, [])]    # (summed expected, roster, keep, plan so far)
    for w in weeks:
        week = Week(league, date.fromisoformat(w['start']), date.fromisoformat(w['end']))
        if not any(p in week.stats for p in roster):
            return {'error': f"No players on your team ({league.my_team}) in this league yet"}
        pool = week.free_agents(suffix)
        label, theirs = week.opponent(w['opponent'] or None, suffix)
        grown = []
        for total, state_roster, keep, plan in states:
            theirs_now = theirs or week.team(state_roster, suffix, owned0).totals
            expected0, _, _ = _value(week.team(state_roster, suffix, owned0).totals, theirs_now, league)
            options = [(expected0, state_roster, keep, [], None)]       # no claim
            frontier = [(state_roster, keep, [], expected0, {}, [])]    # + the claims' windows and dropped players
            for _ in range(league.claims_per_week):
                nxt = []
                for r, k, made, _e, win, ghosts in frontier:
                    ranked, _ = rank_moves(week, r, theirs_now, suffix, [c for c in pool if c not in r], k, owned0, win, ghosts)
                    for m in ranked[:beam]:
                        r2 = [p for p in r if p != m.drop] + [m.add]
                        e = _e + m.gain
                        daily = league.daily_lineups
                        nxt.append((r2, k | {m.add}, made + [m], e,
                                    _claim_windows(win, m.add, m.drop, m.day) if daily else win,
                                    ghosts + ([m.drop] if daily and m.drop else [])))
                nxt.sort(key=lambda t: -t[3])
                for r2, k2, made, e, _w, _g in nxt[:beam]:
                    options.append((e, r2, k2, made, None))
                frontier = nxt[:beam]
            for e, r2, k2, made, _ in options:
                grown.append((total + e, r2, k2, plan + [{
                    'week': w['week'], 'start': w['start'], 'end': w['end'], 'opponent': label,
                    'before': round(expected0, 2), 'after': round(e, 2),
                    'claims': [{'add': m.add, 'drop': m.drop, 'day': m.day.isoformat(), 'gain': round(m.gain, 3),
                                'games': sum(1 for d in week.add_games(m.add) if d >= m.day)} for m in made],
                    'alternatives': []}]))
        # one state per distinct roster, the best total
        best = {}
        for t in grown:
            key = tuple(sorted(t[1]))
            if key not in best or t[0] > best[key][0]:
                best[key] = t
        states = sorted(best.values(), key=lambda t: -t[0])[:beam]
        roster = states[0][1]
    total, final, _, plan = states[0]
    # the next-best claims for each week of the chosen path
    path = list(get_all_my_team_players(league))
    for step, w in zip(plan, weeks):
        week = Week(league, date.fromisoformat(w['start']), date.fromisoformat(w['end']))
        label, theirs = week.opponent(w['opponent'] or None, suffix)
        theirs = theirs or week.team(path, suffix, owned0).totals
        ranked, _ = rank_moves(week, path, theirs, suffix, [c for c in week.free_agents(suffix) if c not in path],
                               undroppable, owned0)
        chosen = {c['add'] for c in step['claims']}
        step['alternatives'] = [{'add': m.add, 'drop': m.drop, 'day': m.day.isoformat(), 'gain': round(m.gain, 3)}
                                for m in ranked if m.add not in chosen][:alternatives]
        for c in step['claims']:
            path = [p for p in path if p != c['drop']] + [c['add']]
    return {'stage': info['stage'], 'timeframe': timeframe, 'claims_per_week': league.claims_per_week,
            'expected_total': round(total, 2), 'weeks': plan, 'final_roster': final}


def main(league=None, timeframe=None, moves=False, plan=False):
    """Print this week's matchup for a league (default: the active one).

    :param str league: league id
    :param str timeframe: pre, proj, projected (recent form), season, 5 or 10; default: the league's
    :param bool moves: also find the best pickups for the week's claims
    :param bool plan: the claims for each remaining week of the guillotine stage
    """
    from leagues import get_league, CATEGORY_CATALOG
    config = get_league(league)
    timeframe = timeframe or default_stat_type(config)
    if plan:
        result = plan_stage(config, timeframe)
        if 'error' in result:
            print(result['error'])
            return
        print(f"{config.name}: stage {result['stage']} plan ({timeframe}), "
              f"{result['expected_total']} expected categories over {len(result['weeks'])} weeks")
        for w in result['weeks']:
            print(f"week {w['week']} {w['start']} vs {w['opponent'] or 'TBD'}: {w['before']} -> {w['after']}")
            for c in w['claims']:
                print(f"  + {c['add']} ({c['games']} g, from {c['day']})  - {c['drop'] or 'open spot'}  (+{c['gain']:.2f})")
            for c in w['alternatives']:
                print(f"    alt {c['add']} (from {c['day']})  - {c['drop'] or 'open spot'}  (+{c['gain']:.2f})")
        return
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
        print(f"  + {step['add']} (from {step['day']})  - {step['drop'] or 'open spot'}  (+{step['gain']:.2f})")


if __name__ == '__main__':
    import defopt
    defopt.run(main)
