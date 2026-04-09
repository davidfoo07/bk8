"""Bet tracking API endpoints — PostgreSQL backed."""

from __future__ import annotations

import re
from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.connectors.nba_api import NBAApiConnector
from app.models.database import get_db
from app.models.tables import Bet
from app.schemas.bet import BetCreate, BetHistoryResponse, BetResponse

router = APIRouter(prefix="/bets", tags=["Bets"])

NBA_TEAM_ID_TO_ABBR: dict[int, str] = {
    1610612737: "ATL", 1610612738: "BOS", 1610612751: "BKN", 1610612766: "CHA",
    1610612741: "CHI", 1610612739: "CLE", 1610612742: "DAL", 1610612743: "DEN",
    1610612765: "DET", 1610612744: "GSW", 1610612745: "HOU", 1610612754: "IND",
    1610612746: "LAC", 1610612747: "LAL", 1610612763: "MEM", 1610612748: "MIA",
    1610612749: "MIL", 1610612750: "MIN", 1610612740: "NOP", 1610612752: "NYK",
    1610612760: "OKC", 1610612753: "ORL", 1610612755: "PHI", 1610612756: "PHX",
    1610612757: "POR", 1610612758: "SAC", 1610612759: "SAS", 1610612761: "TOR",
    1610612762: "UTA", 1610612764: "WAS",
}

ABBR_TO_NICKNAME: dict[str, str] = {
    "ATL": "hawks", "BOS": "celtics", "BKN": "nets", "CHA": "hornets",
    "CHI": "bulls", "CLE": "cavaliers", "DAL": "mavericks", "DEN": "nuggets",
    "DET": "pistons", "GSW": "warriors", "HOU": "rockets", "IND": "pacers",
    "LAC": "clippers", "LAL": "lakers", "MEM": "grizzlies", "MIA": "heat",
    "MIL": "bucks", "MIN": "timberwolves", "NOP": "pelicans", "NYK": "knicks",
    "OKC": "thunder", "ORL": "magic", "PHI": "76ers", "PHX": "suns",
    "POR": "blazers", "SAC": "kings", "SAS": "spurs", "TOR": "raptors",
    "UTA": "jazz", "WAS": "wizards",
}


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
        system_aligned=row.system_aligned if row.system_aligned is not None else True,
        placed_at=row.placed_at,
        resolved_at=row.resolved_at,
    )


def _parse_game_date(game_id: str) -> date | None:
    parts = game_id.split("_")
    if len(parts) >= 3:
        try:
            return date.fromisoformat(parts[0])
        except ValueError:
            pass
    return None


def _parse_teams(game_id: str) -> tuple[str, str] | None:
    parts = game_id.split("_")
    if len(parts) >= 3:
        return parts[1], parts[2]
    return None


def _grade_bet(
    bet: Bet,
    home_score: int,
    away_score: int,
) -> tuple[str, float]:
    """Grade a bet. YES/NO mapping:
      YES = home-perspective: ML=home wins, Spread=home covers, Total=Over
      NO  = opposite: ML=away wins, Spread=away covers, Total=Under
    """
    market = (bet.market_type or "").lower()
    selection = bet.selection or ""
    side = (bet.side or "").upper()
    amount = float(bet.amount_usd or 0)
    price = float(bet.entry_price or 0)

    teams = _parse_teams(bet.game_id)
    if not teams:
        return "PENDING", 0.0
    away_abbr, home_abbr = teams
    actual_margin = home_score - away_score
    actual_total = home_score + away_score

    yes_outcome: bool | None = None

    if market == "moneyline":
        yes_outcome = actual_margin > 0

    elif market == "spread":
        m = re.search(r"—\s*(\w[\w\s]*?)\s+([+-]?\d+\.?\d*)", selection)
        if m:
            line = float(m.group(2))
            team_name_raw = m.group(1).strip().lower()
            home_nick = ABBR_TO_NICKNAME.get(home_abbr, home_abbr.lower())
            home_line = line if team_name_raw == home_nick else -line
            yes_outcome = (actual_margin + home_line) > 0

    elif market == "total":
        m = re.search(r"—\s*(?:Over|Under)\s+(\d+\.?\d*)", selection, re.IGNORECASE)
        if m:
            line = float(m.group(1))
            yes_outcome = actual_total > line

    if yes_outcome is None:
        logger.warning(f"Could not grade bet #{bet.id}: {selection}")
        return "PENDING", 0.0

    won = yes_outcome if side == "YES" else not yes_outcome

    if won:
        pnl = round(amount * (1 - price) / price, 2) if price > 0 else 0
        return "WIN", pnl
    else:
        return "LOSS", round(-amount, 2)


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
        system_aligned=bet.system_aligned,
        placed_at=datetime.now(timezone.utc),
    )
    db.add(row)
    await db.flush()
    await db.refresh(row)

    aligned = "✓ system" if bet.system_aligned else "✗ against"
    logger.info(f"Bet #{row.id} saved: {bet.selection} @ {bet.entry_price} ({aligned})")
    return _row_to_response(row)


@router.post("/resolve", response_model=dict)
async def resolve_bets(db: AsyncSession = Depends(get_db)) -> dict:
    """Auto-resolve all pending bets against actual NBA scores."""
    result = await db.execute(select(Bet).where(Bet.result.is_(None)))
    pending = result.scalars().all()

    if not pending:
        return {"resolved": 0, "message": "No pending bets to resolve"}

    dates_needed: set[date] = set()
    for bet in pending:
        d = _parse_game_date(bet.game_id)
        if d:
            dates_needed.add(d)

    actuals: dict[str, dict] = {}
    nba = NBAApiConnector()
    try:
        for game_date in dates_needed:
            raw_games = await nba.get_todays_games(game_date)
            for g in raw_games:
                home_team = g.get("homeTeam", {})
                away_team = g.get("awayTeam", {})
                ht_id = home_team.get("teamId", 0)
                at_id = away_team.get("teamId", 0)
                ht = NBA_TEAM_ID_TO_ABBR.get(ht_id, home_team.get("teamTricode", "???"))
                at = NBA_TEAM_ID_TO_ABBR.get(at_id, away_team.get("teamTricode", "???"))
                hs = int(home_team.get("score", 0) or 0)
                as_ = int(away_team.get("score", 0) or 0)
                status = g.get("gameStatus", 1)
                if status == 3:
                    actuals[f"{at}_{ht}"] = {"home_score": hs, "away_score": as_}
    except Exception as e:
        logger.error(f"Failed to fetch scores for bet resolution: {e}")
        raise HTTPException(status_code=502, detail=f"NBA API error: {e}")
    finally:
        await nba.close()

    resolved_count = 0
    wins = 0
    losses = 0
    details: list[dict] = []

    for bet in pending:
        teams = _parse_teams(bet.game_id)
        if not teams:
            continue
        key = f"{teams[0]}_{teams[1]}"
        actual = actuals.get(key)
        if not actual:
            continue

        result_str, pnl = _grade_bet(bet, actual["home_score"], actual["away_score"])
        if result_str == "PENDING":
            continue

        bet.result = result_str
        bet.pnl = pnl
        bet.resolved_at = datetime.now(timezone.utc)
        resolved_count += 1
        if result_str == "WIN":
            wins += 1
        else:
            losses += 1

        details.append({
            "id": bet.id, "selection": bet.selection, "side": bet.side,
            "result": result_str, "pnl": pnl,
        })

    await db.flush()
    total_pnl = sum(d["pnl"] for d in details)
    logger.info(f"Resolved {resolved_count} bets: {wins}W {losses}L, PnL: ${total_pnl:+.2f}")

    return {
        "resolved": resolved_count, "wins": wins, "losses": losses,
        "total_pnl": round(total_pnl, 2), "details": details,
    }


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
        total_bets=len(bets), wins=wins, losses=losses, pushes=pushes,
        pending=pending, total_pnl=round(total_pnl, 2),
        win_rate=round(win_rate, 4), roi=round(roi, 2), bets=responses,
    )
