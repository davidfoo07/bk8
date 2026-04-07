"""Pydantic schemas package."""

from app.schemas.bet import BetCreate, BetHistoryResponse, BetResponse
from app.schemas.game import DailyAnalysis, GameAnalysis, TeamGameData, TopEdge
from app.schemas.market import EdgeResult, MarketEdge, MarketPrice
from app.schemas.prediction import DataQuality, GamePrediction
from app.schemas.team import (
    AdjustedRatings,
    InjurySchema,
    PlayerAbsence,
    ScheduleContext,
    StandingsInfo,
    TeamBase,
    TeamRatingSchema,
)

__all__ = [
    "AdjustedRatings",
    "BetCreate",
    "BetHistoryResponse",
    "BetResponse",
    "DailyAnalysis",
    "DataQuality",
    "EdgeResult",
    "GameAnalysis",
    "GamePrediction",
    "InjurySchema",
    "MarketEdge",
    "MarketPrice",
    "PlayerAbsence",
    "ScheduleContext",
    "StandingsInfo",
    "TeamBase",
    "TeamGameData",
    "TeamRatingSchema",
    "TopEdge",
]
