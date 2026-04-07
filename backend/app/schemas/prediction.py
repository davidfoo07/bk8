"""Pydantic schemas for model predictions."""

from pydantic import BaseModel


class GamePrediction(BaseModel):
    """Full prediction for a single game."""
    nrtg_differential: float
    schedule_adjustment: float
    home_court: float = 3.0
    projected_spread: float
    projected_total: float
    home_win_prob: float
    confidence: str = "MEDIUM"


class DataQuality(BaseModel):
    """Data quality indicators for a game analysis."""
    ratings_freshness: str = "FRESH"  # FRESH, STALE, MISSING
    injury_freshness: str = "FRESH"
    price_freshness: str = "FRESH"
    cross_source_validated: bool = True
    warnings: list[str] = []
