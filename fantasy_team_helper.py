"""
Fantasy team helper functions, all scoped to one league (a leagues.LeagueConfig).
Handles the league's matchup schedule and its teams' rosters.
"""
from datetime import datetime, date, timedelta
from fantasy_database import FantasyTeam, FantasyTeamPlayer, Player, LeaguePlayerFlag


def string_to_date(value):
    return datetime.strptime(value, '%Y-%m-%d').date()


def _week_end(schedule, index):
    """Last day of schedule[index]: the day before the next week starts, else 7 days."""
    week_start = string_to_date(schedule[index][0])
    if index + 1 < len(schedule):
        return string_to_date(schedule[index + 1][0]) - timedelta(days=1)
    return week_start + timedelta(days=6)


def get_week_info_from_schedule(league, week_start_param):
    """
    Week information for a week start date in the league's schedule.

    :param league: leagues.LeagueConfig
    :param str week_start_param: Week start date in 'YYYY-MM-DD' format
    :return: tuple: (week_start, week_end, opponent) or (None, None, None) if not found
    """
    schedule = league.schedule
    for i, (start, opponent) in enumerate(schedule):
        if start == week_start_param:
            return string_to_date(start), _week_end(schedule, i), opponent or None
    return None, None, None


def get_current_fantasy_week_dates(league, target_date=None):
    """
    The fantasy week containing target_date (default today): (week_start, week_end, opponent).

    Before the season: the first week. Between weeks: the next one. After the season: the last.
    With no schedule yet: the Monday-Sunday week around target_date, with no opponent.
    """
    target = string_to_date(target_date) if target_date else date.today()
    schedule = league.schedule
    if not schedule:
        week_start = target - timedelta(days=target.weekday())
        return week_start, week_start + timedelta(days=6), None
    for i, (start, opponent) in enumerate(schedule):
        week_end = _week_end(schedule, i)
        if target <= week_end:
            return string_to_date(start), week_end, opponent or None
    start, opponent = schedule[-1]
    return string_to_date(start), _week_end(schedule, len(schedule) - 1), opponent or None


def get_next_week_dates(league, week_start):
    """(start, end) of the week after the one starting on week_start, or (None, None)."""
    schedule = league.schedule
    key = week_start.strftime('%Y-%m-%d') if hasattr(week_start, 'strftime') else week_start
    for i, (start, _) in enumerate(schedule):
        if start == key and i + 1 < len(schedule):
            return string_to_date(schedule[i + 1][0]), _week_end(schedule, i + 1)
    return None, None


def league_team_ids(league):
    return [t.id for t in FantasyTeam.select(FantasyTeam.id).where(FantasyTeam.league == league.id)]


def get_team_by_abv(league, abv):
    return FantasyTeam.get_or_none((FantasyTeam.league == league.id) & (FantasyTeam.abv == abv))


def _team_players(team, healthy_only):
    query = (Player
             .select()
             .join(FantasyTeamPlayer, on=(Player.id == FantasyTeamPlayer.player_id))
             .where(FantasyTeamPlayer.fantasy_team_id == team.id))
    if healthy_only:
        query = query.where((Player.injured == 0) | (Player.injured.is_null()))
    return [player.name for player in query]


def get_all_my_team_players(league):
    """Every player on my team in this league, injured included."""
    team = get_team_by_abv(league, league.my_team)
    return _team_players(team, healthy_only=False) if team else []


def get_all_taken_players(league):
    """Every player on any team in this league."""
    team_ids = league_team_ids(league)
    if not team_ids:
        return []
    return [ftp.player_name for ftp in FantasyTeamPlayer.select(FantasyTeamPlayer.player_name)
            .where(FantasyTeamPlayer.fantasy_team_id.in_(team_ids))]


def get_undroppable_players(league):
    return [flag.player.name for flag in LeaguePlayerFlag.select(LeaguePlayerFlag, Player)
            .join(Player).where((LeaguePlayerFlag.league == league.id) & (LeaguePlayerFlag.undroppable == True))]  # noqa: E712


def league_positions(league):
    """{player name: positions} the league's platform lists (pull_yahoo.py); players without an
    import fall back to NBA's positions (player_stats.nba_positions)."""
    rows = (LeaguePlayerFlag.select(LeaguePlayerFlag.positions, Player.name).join(Player)
            .where((LeaguePlayerFlag.league == league.id) & LeaguePlayerFlag.positions.is_null(False)))
    return {row.player.name: tuple(p for p in row.positions.split(',') if p) for row in rows}


def set_league_flags(league, player_id, **fields):
    """Upsert one player's per-league flags, touching only `fields` (undroppable, positions)."""
    updated = (LeaguePlayerFlag.update(**fields)
               .where((LeaguePlayerFlag.league == league.id) & (LeaguePlayerFlag.player == player_id)).execute())
    if not updated and not LeaguePlayerFlag.select().where((LeaguePlayerFlag.league == league.id)
                                                           & (LeaguePlayerFlag.player == player_id)).exists():
        LeaguePlayerFlag.create(league=league.id, player=player_id, **fields)


def get_injured_players():
    """Injured players (NBA-wide, not per league)."""
    return [player.name for player in Player.select(Player.name).where(Player.injured == 1)]


def get_available_players(league, player_stats):
    """Players not on any team in this league and not injured."""
    taken = set(get_all_taken_players(league))
    injured = set(get_injured_players())
    return {name for name in player_stats if name not in taken and name not in injured}
