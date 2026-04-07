"""Pydantic schemas for team-related data."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field


class TeamBase(BaseModel):
    id: str = Field(..., max_length=3)
    full_name: str
    conference: str
    division: str


class TeamRatingSchema(BaseModel):
    team_id: str
    date: date
    ortg: float
    drtg: float
    nrtg: float
    pace: float | None = None
    source: str | None = None


class PlayerAbsence(BaseModel):
    """Represents a player who is absent from tonight's game."""
    player_id: str
    name: str
    status: str  # OUT, DOUBTFUL, QUESTIONABLE, PROBABLE, GTD, AVAILABLE
    reason: str | None = None
    ortg_impact: float = 0.0
    drtg_impact: float = 0.0
    nrtg_impact: float = 0.0
    minutes_share: float = 0.0


class AdjustedRatings(BaseModel):
    """Lineup-adjusted team ratings for a specific game."""
    team: str
    season_ortg: float
    season_drtg: float
    season_nrtg: float
    adjusted_ortg: float
    adjusted_drtg: float
    adjusted_nrtg: float
    ortg_delta: float
    drtg_delta: float
    nrtg_delta: float
    missing_players: list[PlayerAbsence] = []
    confidence: str = "MEDIUM"  # HIGH, MEDIUM, LOW
    data_source: str = "pbpstats"
    last_updated: datetime | None = None


class InjurySchema(BaseModel):
    player_name: str
    player_id: str
    team: str
    status: str
    reason: str | None = None
    source: str = "NBA Official"
    last_updated: datetime | None = None
    confirmed_at: datetime | None = None
    impact_rating: str = "MEDIUM"


class ScheduleContext(BaseModel):
    is_b2b: bool = False
    is_3_in_4: bool = False
    is_4_in_6: bool = False
    rest_days: int = 1
    road_trip_game: int = 0
    home_court: bool = False
    travel_distance_miles: float = 0.0


class StandingsInfo(BaseModel):
    team: str
    record: str
    conference_seed: int
    games_back: float = 0.0
    clinch_status: str = "NONE"
    magic_number: int | None = None
    motivation_flag: str = "NEUTRAL"  # REST_EXPECTED, NEUTRAL, DESPERATE, FIGHTING
    motivation_note: str = ""
    remaining_schedule_strength: float = 0.500
