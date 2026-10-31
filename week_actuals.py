"""A matchup week already under way: what the games played so far added, and what is left to play.

The matchup model (lineup_optimizer.py) projects a whole week. Mid-week the played part is a fact:
final games count as their box scores, a game in progress counts as the box score so far plus the
share of the game still to play, and only unplayed games stay projected (and keep their variance, so a
category's chance converges on 0 or 100% as the week finishes). Lines come from Daily Leaders' ESPN
slates (daily_leaders.slate), keyed by player name.

Two limits, both from what the database knows: rosters are today's (there is no transaction history,
so a player added Wednesday also gets his Monday line counted, and one dropped Tuesday is missing), and
a daily lineup's played days assume the best fitting players from the roster started (the real
lineup you set is not read).
"""
import re
from collections import defaultdict

from leagues import fantasy_points
from player_stats import TEAM_DICT

NBA_MINUTES = 48.0
# Raw stat names a team total is built from (calculate_team_totals' `carried`).
COUNT_STATS = ('PTS', 'REB', 'AST', 'STL', 'BLK', 'FG3M', 'TOV', 'PF', 'BLKA', 'TECH', 'DD2', 'TD3', 'PLUS_MINUS',
               'FGA', 'FGM', 'FTA', 'FTM')


def game_left(game):
    """Share of a game still to play: 1 before tip-off, 0 once final, else by the clock (overtime counts as over)."""
    if game['state'] == 'pre':
        return 1.0
    if game['state'] == 'post':
        return 0.0
    period = game.get('period') or 1
    if period > 4:
        return 0.0
    text = str(game.get('clock') or '0:00')
    minutes = int(text.split(':')[0]) + float(text.split(':')[1]) / 60 if ':' in text else float(text or 0) / 60
    return max(0.0, min(1.0, (NBA_MINUTES - ((period - 1) * 12 + (12 - minutes))) / NBA_MINUTES))


def _team_name(name):
    return TEAM_DICT.get(name, name)


class WeekActuals:
    """The played part of one league-week.

    left     {(NBA team, day): share of that day's game still to play}; absent = no data for it (projected whole)
    lines    {normalised name: {day: stat line}} for every player with a line in a game on or after tip-off
    live/final  games in progress / over; partial: some day or box score could not be loaded
    """

    def __init__(self, week_start, week_end, today, slate, norm_name):
        self.today = today
        self.left, self.lines = {}, defaultdict(dict)
        self.tipped = set()    # {(NBA team, day)} games in progress: closed to new lineups
        self.loaded = set()    # days whose slate loaded: a team missing from one has no game that day
        self.live = self.final = 0
        self.partial = False
        self._cache = {}
        self._canon_cache = {}  # id(canon lines of one team) -> carried
        self.canon_gaps = 0    # canon player-days whose attempts ESPN's lines lacked
        self.lineups = {}      # (roster, suffix) -> {day: players whose played games count}
        days, day = [], week_start
        while day <= min(today, week_end):
            days.append(day)
            day = day.fromordinal(day.toordinal() + 1)

        def load(d):
            try:
                return slate(d)
            except Exception as e:  # ESPN down: this day stays projected, and the page says so
                print(f'week actuals {d}: {e}')
                return None
        slates = [load(d) for d in days]    # daily_leaders.slate holds one lock across its fetch: no gain from threads
        for day, cur in zip(days, slates):
            if cur is None:
                self.partial = True
                continue
            self.loaded.add(day)
            for game in cur['scoreboard']:
                left = game_left(game)
                if game['state'] == 'post':
                    self.final += 1
                    if game['id'] not in cur.get('final', ()):
                        self.partial = True    # over, but its last box score was not stored yet
                elif game['state'] == 'in':
                    self.live += 1
                for t in game['teams']:
                    if t.get('name'):
                        self.left[(_team_name(t['name']), day)] = left
                        if game['state'] == 'in':
                            self.tipped.add((_team_name(t['name']), day))
                if game['state'] != 'pre':
                    lines = cur['games'].get(game['id'])
                    if lines is None:
                        self.partial = True
                        continue
                    for line in lines.values():
                        self.lines[norm_name(line['name'])][day] = line
        self.norm_name = norm_name

    @property
    def started(self):
        return bool(self.left)

    def remaining(self, schedule):
        """(schedule of the unplayed games, {(team, day): share left}) for player_week_games."""
        remaining, weights = {}, {}
        for team, days in schedule.items():
            for day, p_win in days.items():
                # a loaded slate without this team: the game was moved or called off, nothing to project that day
                left = self.left.get((team, day), 0.0 if day in self.loaded else 1.0)
                if left > 0:
                    remaining.setdefault(team, {})[day] = p_win
                    if left < 1:
                        weights[(team, day)] = left
        return remaining, weights

    def canon_carried(self, lines, league):
        """The played part from the platform's own lineups (canon.py; see canon_carried_impl); adds, drops and bench moves are in it."""
        key = id(lines)
        if key not in self._canon_cache:
            self._canon_cache[key], gaps = canon_carried_impl(self, lines, league)
            self.canon_gaps += gaps
        return self._canon_cache[key]

    def carried(self, owned, stats, league, suffix, starters=None):
        """{stat: total} the `owned` players' played games added (cached per roster).

        Daily lineups: each day only the best players with a line who fit the league's slots count
        (fill_slots by the timeframe's Z-SCORE). Weekly lineups: the `starters` count every line."""
        from player_stats import fill_slots, _by_score
        key = (frozenset(owned), suffix)
        if key in self._cache:
            return self._cache[key]
        lineups = self.lineups[key] = {}
        by_day = defaultdict(dict)
        for p in owned:
            if p in stats:
                for day, line in self.lines.get(self.norm_name(p), {}).items():
                    by_day[day][p] = line
        carried = defaultdict(float)
        for day, got in by_day.items():
            if league.daily_lineups:
                counted = fill_slots(_by_score(list(got), stats, suffix), league.slots, stats)
            else:
                counted = {p: None for p in got if starters is None or p in starters}
            lineups[day] = set(counted) if league.daily_lineups else set()
            for p in counted:
                line = got[p]
                for stat in COUNT_STATS:
                    carried[stat] += line.get(stat) or 0
                carried['AST-TOV'] += (line.get('AST') or 0) - (line.get('TOV') or 0)
                carried['WIN%'] += line.get('W') or 0
                carried['GP'] += 1    # player-games counted so far (the page's games played)
                if league.is_points:
                    carried['FPTS'] += fantasy_points(line, league.point_weights)
        self._cache[key] = dict(carried)
        return self._cache[key]


def canon_carried_impl(actual, lines, league):
    """{stat: total} of the player-days the platform counted (canon.py: `lines` is {day: {norm name: {'name', 'stats'}}}).

    The platform decides WHICH player-days count and the values it shows (Fantrax: nine categories; Yahoo: FPTS); ESPN's line
    (same player, same day) adds what the platform doesn't show per player (attempts, so FG% and FT% add up as makes/attempts) and the rest."""
    carried, gaps = defaultdict(float), 0
    for day, got in lines.items():
        for nn, fx in got.items():
            espn = actual.lines.get(nn, {}).get(day)
            line = dict(espn or {})
            if espn is None:
                gaps += 1   # the platform counted him, ESPN has no line: attempts and the stats Fantrax doesn't show are 0
            for stat, value in fx['stats'].items():
                if stat not in ('FG%', 'FT%'):
                    line[stat] = value
            for pct, made, tried in (('FG%', 'FGM', 'FGA'), ('FT%', 'FTM', 'FTA')):
                if pct in fx['stats'] and (line.get(tried) or 0):
                    line[made] = round(fx['stats'][pct] * line[tried])
            for stat in COUNT_STATS:
                carried[stat] += line.get(stat) or 0
            carried['AST-TOV'] += (line.get('AST') or 0) - (line.get('TOV') or 0)
            carried['WIN%'] += line.get('W') or 0
            carried['GP'] += 1
            if league.is_points:
                # Yahoo's own points for the player-day (yahoo_canon) beat our re-scoring of ESPN's line
                carried['FPTS'] += fx['stats']['FPTS'] if 'FPTS' in fx['stats'] else fantasy_points(line, league.point_weights)
    return dict(carried), gaps


def lineup_of(actual, owned, suffix):
    """{day: players in that day's counted lineup} for a roster whose carried() was computed."""
    return actual.lineups.get((frozenset(owned), suffix), {})


def week_actuals(week_start, week_end, today=None):
    """The week's played part, or None before its first game day."""
    import daily_leaders
    from projections import norm_name
    today = today or daily_leaders.nba_today()
    if today < week_start:
        return None
    actuals = WeekActuals(week_start, week_end, today, daily_leaders.slate, norm_name)
    return actuals if actuals.started else None
