"""Bet tracking API endpoints — PostgreSQL backed."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from loguru import logger
from sqlalchemy import select, func as sqlfunc
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.database import get_db
from app.models.tables import Bet
from app.schemas.bet import BetCreate, BetHistoryResponse, BetResponse

router = APIRouter(prefix="/bets", tags=["Bets"])


def _row_to_response(row: Bet) -> BetResponse:
    return BetResponse(
        id=row.id,
        game_id=row.game_id,
        market_type=row.market_type or "",
        selection=row.selection or "",
        side=row.side or "",
        entry_price=float(row.entry_price or 0),
        model_probability=float(row.model_probability or 0),
        edge_at_entry=float(row.edge_at_entry or 0),
        amount_usd=float(row.amount_usd or 0),
        kelly_fraction=float(row.kelly_fraction or 0),
        result=row.result,
        pnl=float(row.pnl) if row.pnl is not None else None,
        placed_at=row.placed_at,
        resolved_at=row.resolved_at,
    )


@router.post("", response_model=BetResponse)
async def create_bet(bet: BetCreate, db: AsyncSession = Depends(get_db)) -> BetResponse:
    """Log a new bet to PostgreSQL."""
    row = Bet(
        game_id=bet.game_id,
        prediction_id=bet.prediction_id,
        market_type=bet.market_type,
        selection=bet.selection,
        side=bet.side,
        entry_price=bet.entry_price,
        model_probability=bet.model_probability,
        edge_at_entry=bet.edge_at_entry,
        amount_usd=bet.amount_usd,
        kelly_fraction=bet.kelly_fraction,
        notes=bet.notes or None,
        placed_at=datetime.now(timezone.utc),
    )
    db.add(row)
    await db.flush()
    await db.refresh(row)

    logger.info(f"Bet #{row.id} saved: {bet.selection} @ {bet.entry_price} ({bet.amount_usd} USD)")
    return _row_to_response(row)


@router.get("/history", response_model=BetHistoryResponse)
async def get_bet_history(db: AsyncSession = Depends(get_db)) -> BetHistoryResponse:
    """Get bet history with aggregate stats from PostgreSQL."""
    result = await db.execute(select(Bet).order_by(Bet.placed_at.desc()))
    bets = result.scalars().all()

    responses = [_row_to_response(b) for b in bets]
    resolved = [b for b in bets if b.result is not None]
    wins = sum(1 for b in resolved if b.result == "WIN")
    losses = sum(1 for b in resolved if b.result == "LOSS")
    pushes = sum(1 for b in resolved if b.result == "PUSH")
    pending = sum(1 for b in bets if b.result is None)

    total_pnl = sum(float(b.pnl or 0) for b in resolved)
    total_wagered = sum(float(b.amount_usd or 0) for b in resolved) if resolved else 0
    win_rate = wins / len(resolved) if resolved else 0.0
    roi = (total_pnl / total_wagered * 100) if total_wagered > 0 else 0.0

    return BetHistoryResponse(
        total_bets=len(bets),
        wins=wins,
        losses=losses,
        pushes=pushes,
        pending=pending,
        total_pnl=round(total_pnl, 2),
        win_rate=round(win_rate, 4),
        roi=round(roi, 2),
        bets=responses,
    )
