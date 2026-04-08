"""Pydantic schemas for Polymarket data and edge calculations."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class MarketPrice(BaseModel):
    """Raw Polymarket market data."""
    game_id: str
    market_type: str  # moneyline, spread, total
    polymarket_slug: str | None = None
    condition_id: str | None = None
    yes_price: float = Field(..., ge=0.01, le=0.99)
    no_price: float = Field(..., ge=0.01, le=0.99)
    volume: float = 0.0
    liquidity: float = 0.0
    fetched_at: datetime | None = None


class EdgeResult(BaseModel):
    """Result of edge calculation between model and market."""
    yes_edge: float
    no_edge: float
    yes_ev: float
    no_ev: float
    best_side: str  # YES or NO — or team name like "Nuggets"
    best_edge: float
    verdict: str  # STRONG BUY, BUY, LEAN, NO EDGE
    kelly_fraction: float = 0.0
    suggested_bet_pct: float = 0.0


class MarketEdge(BaseModel):
    """Full market analysis combining price and edge."""
    market_type: str
    line: float | None = None  # spread line or total line
    polymarket_home_yes: float | None = None
    polymarket_home_no: float | None = None
    home_label: str | None = None  # e.g. "Nuggets" instead of "YES"
    away_label: str | None = None  # e.g. "Grizzlies" instead of "NO"
    model_probability: float
    edge: EdgeResult
