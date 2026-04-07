"""Pydantic schemas for game analysis — the main API response model."""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel

from app.schemas.market import MarketEdge
from app.schemas.prediction import DataQuality, GamePrediction
from app.schemas.team import AdjustedRatings, InjurySchema, ScheduleContext, StandingsInfo


class TeamGameData(BaseModel):
    """All data for one team in a game."""
    team: str
    full_name: str
    record: str = ""
    seed: int | None = None
    motivation: str = "NEUTRAL"
    season_ortg: float
    season_drtg: float
    season_nrtg: float
    adjusted_ortg: float
    adjusted_drtg: float
    adjusted_nrtg: float
    nrtg_delta: float
    injuries: list[InjurySchema] = []
    schedule: ScheduleContext = ScheduleContext()


class GameAnalysis(BaseModel):
    """Complete analysis for a single game — the core data object."""
    game_id: str
    tipoff: datetime | None = None
    tipoff_sgt: datetime | None = None
    venue: str = ""
    home: TeamGameData
    away: TeamGameData
    model: GamePrediction
    markets: dict[str, MarketEdge] = {}
    data_quality: DataQuality = DataQuality()


class TopEdge(BaseModel):
    """Summary of a top edge opportunity."""
    game: str
    market: str
    selection: str
    price: float
    model_prob: float
    edge: float
    verdict: str


class DailyAnalysis(BaseModel):
    """Full daily analysis — the response for /games/today."""
    date: date
    timezone_note: str = "All times in US Eastern. Operator is UTC+8."
    games_count: int = 0
    games: list[GameAnalysis] = []
    top_edges: list[TopEdge] = []
