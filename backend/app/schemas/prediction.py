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
    spread_cover_prob: float = 0.5  # Prob that home team covers the spread
    over_prob: float = 0.5          # Prob that game goes over the total
    confidence: str = "MEDIUM"


class LivePrediction(BaseModel):
    """Live-adjusted prediction that blends pre-game model with current score.

    As the game progresses, the live score increasingly dominates over the
    pre-game model rating. When the game is FINAL, this reflects the actual
    result.
    """
    home_win_prob: float  # Blended live win probability
    pre_game_home_win_prob: float  # Original pre-game model for comparison
    projected_final_margin: float  # Expected final margin from home perspective
    live_margin: int  # Current score difference (home - away)
    time_remaining_pct: float  # 1.0 = full game, 0.0 = game over
    is_final: bool = False  # True when game is decided
    home_won: bool | None = None  # Only set when is_final=True


class DataQuality(BaseModel):
    """Data quality indicators for a game analysis."""
    ratings_freshness: str = "FRESH"  # FRESH, STALE, MISSING
    injury_freshness: str = "FRESH"
    price_freshness: str = "FRESH"
    cross_source_validated: bool = True
    warnings: list[str] = []
