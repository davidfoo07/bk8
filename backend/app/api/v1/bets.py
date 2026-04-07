"""Bet tracking API endpoints."""

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from loguru import logger

from app.schemas.bet import BetCreate, BetHistoryResponse, BetResponse

router = APIRouter(prefix="/bets", tags=["Bets"])

# In-memory store for MVP (replace with DB in production)
_bets: list[BetResponse] = []
_bet_counter = 0


@router.post("", response_model=BetResponse)
async def create_bet(bet: BetCreate) -> BetResponse:
    """Log a new bet."""
    global _bet_counter
    _bet_counter += 1

    bet_response = BetResponse(
        id=_bet_counter,
        game_id=bet.game_id,
        market_type=bet.market_type,
        selection=bet.selection,
        side=bet.side,
        entry_price=bet.entry_price,
        model_probability=bet.model_probability,
        edge_at_entry=bet.edge_at_entry,
        amount_usd=bet.amount_usd,
        kelly_fraction=bet.kelly_fraction,
        placed_at=datetime.now(timezone.utc),
    )

    _bets.append(bet_response)
    logger.info(f"Bet logged: {bet.selection} @ {bet.entry_price} ({bet.amount_usd} USD)")
    return bet_response


@router.get("/history", response_model=BetHistoryResponse)
async def get_bet_history() -> BetHistoryResponse:
    """Get bet history with aggregate stats."""
    resolved = [b for b in _bets if b.result is not None]
    wins = sum(1 for b in resolved if b.result == "WIN")
    losses = sum(1 for b in resolved if b.result == "LOSS")
    pushes = sum(1 for b in resolved if b.result == "PUSH")
    pending = sum(1 for b in _bets if b.result is None)

    total_pnl = sum(b.pnl or 0 for b in resolved)
    total_wagered = sum(b.amount_usd for b in resolved) if resolved else 0
    win_rate = wins / len(resolved) if resolved else 0.0
    roi = (total_pnl / total_wagered * 100) if total_wagered > 0 else 0.0

    return BetHistoryResponse(
        total_bets=len(_bets),
        wins=wins,
        losses=losses,
        pushes=pushes,
        pending=pending,
        total_pnl=round(total_pnl, 2),
        win_rate=round(win_rate, 4),
        roi=round(roi, 2),
        bets=list(reversed(_bets)),  # Most recent first
    )
