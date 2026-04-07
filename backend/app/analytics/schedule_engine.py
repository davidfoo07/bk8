"""
Schedule Context Engine — calculates fatigue, rest advantage, and motivation.
"""

from __future__ import annotations

from datetime import date, timedelta

from loguru import logger

from app.schemas.team import ScheduleContext, StandingsInfo


def calculate_schedule_context(
    team_id: str,
    game_date: date,
    recent_games: list[dict] | None = None,
    is_home: bool = True,
) -> ScheduleContext:
    """
    Calculate schedule context for a team on a given game date.

    Args:
        team_id: Team abbreviation
        game_date: Date of the game
        recent_games: List of recent games with 'date' and 'is_home' fields
        is_home: Whether team is home for this game
    """
    if not recent_games:
        return ScheduleContext(
            is_b2b=False,
            is_3_in_4=False,
            is_4_in_6=False,
            rest_days=2,
            road_trip_game=0,
            home_court=is_home,
        )

    # Sort games by date descending (most recent first)
    sorted_games = sorted(recent_games, key=lambda g: g.get("date", ""), reverse=True)

    # Calculate rest days (days since last game)
    rest_days = _calculate_rest_days(game_date, sorted_games)

    # Check back-to-back
    is_b2b = rest_days == 0

    # Check 3-in-4 nights
    is_3_in_4 = _check_games_in_span(game_date, sorted_games, games_needed=2, span_days=3)

    # Check 4-in-6 nights
    is_4_in_6 = _check_games_in_span(game_date, sorted_games, games_needed=3, span_days=5)

    # Calculate road trip length
    road_trip_game = _calculate_road_trip(game_date, sorted_games, is_home)

    return ScheduleContext(
        is_b2b=is_b2b,
        is_3_in_4=is_3_in_4,
        is_4_in_6=is_4_in_6,
        rest_days=rest_days,
        road_trip_game=road_trip_game,
        home_court=is_home,
    )


def _calculate_rest_days(game_date: date, sorted_games: list[dict]) -> int:
    """Calculate days of rest since last game."""
    for game in sorted_games:
        game_dt = _parse_date(game.get("date"))
        if game_dt and game_dt < game_date:
            return (game_date - game_dt).days - 1
    return 3  # Default if no recent games found


def _check_games_in_span(
    game_date: date,
    sorted_games: list[dict],
    games_needed: int,
    span_days: int,
) -> bool:
    """Check if team has played N games in the last span_days (including today)."""
    start_date = game_date - timedelta(days=span_days)
    count = 0
    for game in sorted_games:
        game_dt = _parse_date(game.get("date"))
        if game_dt and start_date <= game_dt < game_date:
            count += 1
            if count >= games_needed:
                return True
    return False


def _calculate_road_trip(
    game_date: date,
    sorted_games: list[dict],
    is_home: bool,
) -> int:
    """Calculate current road trip game number (0 if home)."""
    if is_home:
        return 0

    consecutive_road = 1  # Count today's game
    for game in sorted_games:
        game_dt = _parse_date(game.get("date"))
        if game_dt and game_dt < game_date:
            if not game.get("is_home", True):
                consecutive_road += 1
            else:
                break  # Last home game breaks the road trip
    return consecutive_road


def _parse_date(date_str: str | date | None) -> date | None:
    """Parse a date string or return date object."""
    if isinstance(date_str, date):
        return date_str
    if isinstance(date_str, str):
        try:
            return date.fromisoformat(date_str[:10])
        except (ValueError, IndexError):
            return None
    return None


def determine_motivation(
    team: str,
    record: str,
    conference_seed: int,
    clinch_status: str = "NONE",
    games_remaining: int = 0,
) -> StandingsInfo:
    """
    Determine team motivation based on standings context.

    Motivation flags:
    - REST_EXPECTED: clinched seeding, nothing to play for
    - DESPERATE: 1-2 games from elimination or play-in bubble
    - FIGHTING: seeding still in flux
    - NEUTRAL: default
    """
    motivation_flag = "NEUTRAL"
    motivation_note = ""

    if clinch_status in ("CLINCHED_1_SEED", "CLINCHED_DIVISION", "CLINCHED_BEST_RECORD"):
        motivation_flag = "REST_EXPECTED"
        motivation_note = f"Clinched {clinch_status.replace('CLINCHED_', '').replace('_', ' ').lower()}. May rest players."
    elif clinch_status == "ELIMINATED":
        motivation_flag = "REST_EXPECTED"
        motivation_note = "Eliminated from playoff contention. Expect rest/development focus."
    elif conference_seed >= 9 and games_remaining <= 5:
        motivation_flag = "DESPERATE"
        motivation_note = f"Seed #{conference_seed}, {games_remaining} games left. Fighting for play-in."
    elif conference_seed >= 7 and games_remaining <= 10:
        motivation_flag = "FIGHTING"
        motivation_note = f"Seed #{conference_seed}, seeding still in flux."
    elif conference_seed <= 3:
        if clinch_status == "CLINCHED_PLAYOFF":
            motivation_flag = "FIGHTING"
            motivation_note = f"Clinched playoffs at #{conference_seed}, still fighting for seeding."
        else:
            motivation_flag = "FIGHTING"
            motivation_note = f"#{conference_seed} seed, competing for top seeding."

    return StandingsInfo(
        team=team,
        record=record,
        conference_seed=conference_seed,
        clinch_status=clinch_status,
        motivation_flag=motivation_flag,
        motivation_note=motivation_note,
    )
