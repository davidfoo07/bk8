"""Pydantic schemas for bet tracking."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class BetCreate(BaseModel):
    """Schema for creating a new bet."""
    game_id: str
    prediction_id: int | None = None
    market_type: str
    selection: str
    side: str  # YES or NO
    entry_price: float = Field(..., ge=0.01, le=0.99)
    model_probability: float = Field(..., ge=0.0, le=1.0)
    edge_at_entry: float
    amount_usd: float = Field(..., gt=0)
    kelly_fraction: float = 0.0
    notes: str = ""
    system_aligned: bool = True  # True = user agrees with model recommendation


class BetResponse(BaseModel):
    """Schema for bet response."""
    id: int
    game_id: str
    market_type: str
    selection: str
    side: str
    entry_price: float
    model_probability: float
    edge_at_entry: float
    amount_usd: float
    kelly_fraction: float
    result: str | None = None
    pnl: float | None = None
    system_aligned: bool = True
    placed_at: datetime
    resolved_at: datetime | None = None


class BetHistoryResponse(BaseModel):
    """Schema for bet history with stats."""
    total_bets: int = 0
    wins: int = 0
    losses: int = 0
    pushes: int = 0
    pending: int = 0
    total_pnl: float = 0.0
    win_rate: float = 0.0
    roi: float = 0.0
    bets: list[BetResponse] = []
