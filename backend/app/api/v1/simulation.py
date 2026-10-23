"""System simulation API — virtual P&L if you followed every model recommendation.

Data sources (all owned, no external API dependency for historical data):
  - market_snapshots table → Polymarket prices, model edges, verdicts
  - NBA scores → scoreboardv3 (live) with leaguegamefinder fallback (historical)
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, HTTPException
from loguru import logger
from pydantic import BaseModel
from sqlalchemy import select, text

from app.connectors.nba_api import NBAApiConnector
from app.models.database import async_session_factory
from app.models.tables import MarketSnapshot
from app.services.pipeline import fetch_scores

router = APIRouter(prefix="/simulation", tags=["Simulation"])

KELLY_BANKROLL = 100.0  # $100 virtual bankroll for Kelly-sized bets


# ─── Pydantic Schemas ──────────────────────────────────────────────

class SimBet(BaseModel):
    game: str
    market_type: str
    selection: str
    side: str
    verdict: str
    entry_price: float
    model_prob: float
    edge: float
    kelly_fraction: float
    flat_result: str | None = None
    flat_pnl: float = 0.0
    kelly_amount: float = 0.0
    kelly_result: str | None = None
    kelly_pnl: float = 0.0


class DailySimulation(BaseModel):
    date: str
    total_bets: int
    flat_wins: int
    flat_losses: int
    flat_record: str
    flat_pnl: float
    flat_roi: float
    kelly_wins: int
    kelly_losses: int
    kelly_pnl: float
    kelly_roi: float
    bets: list[SimBet]


# ─── Grading Helpers ───────────────────────────────────────────────

def _grade_yes_outcome(
    market_type: str,
    line: float | None,
    home_score: int,
    away_score: int,
) -> bool | None:
    """Determine if YES (home-perspective) outcome occurred."""
    actual_margin = home_score - away_score
    actual_total = home_score + away_score

    if market_type == "moneyline":
        return actual_margin > 0
    if market_type == "spread":
        if line is None:
            return None
        return (actual_margin + line) > 0
    if market_type == "total":
        if line is None:
            return None
        return actual_total > line
    return None


def _calc_pnl(won: bool, amount: float, price: float) -> float:
    if won:
        return round(amount * (1 - price) / price, 2) if price > 0 else 0.0
    return round(-amount, 2)


def _build_selection_label(
    market_type: str,
    away_team: str,
    home_team: str,
    side: str,
    best_side_name: str,
    line: float | None,
) -> str:
    if market_type == "moneyline":
        team = home_team if side == "YES" else away_team
        return f"{team} ML"
    if market_type == "spread":
        if line is not None:
            if side == "YES":
                home_line = line
                sign = "+" if home_line > 0 else ""
                return f"{home_team} covers {sign}{home_line}"
            else:
                away_line = -line
                sign = "+" if away_line > 0 else ""
                return f"{away_team} covers {sign}{away_line}"
        return f"{best_side_name} covers"
    if market_type == "total":
        if line is not None:
            direction = "Over" if side == "YES" else "Under"
            return f"{direction} {line}"
        return best_side_name
    return best_side_name


# ─── NBA Score Fetching (with fallback) ────────────────────────────

async def _fetch_final_scores(
    game_date: date,
) -> dict[str, dict]:
    """Fetch final scores for a date.  Uses the ESPN scoreboard first;
    if it returns no FINAL games, falls back to leaguegamefinder.
    Returns dict keyed by "AWAY_HOME" → {home_score, away_score}.
    """
    actuals: dict[str, dict] = {}
    try:
        # ESPN scoreboard first (NBA fallback inside), works for any date
        for key, score in (await fetch_scores(game_date)).items():
            if score["status"] == 3:
                actuals[key] = {k: score[k] for k in ("home_score", "away_score")}
        if actuals:
            logger.info(f"Got {len(actuals)} final scores for {game_date}")
            return actuals
    except Exception as e:
        logger.warning(f"Scoreboard fetch failed for {game_date}: {e}")

    nba = NBAApiConnector()
    try:
        # Fallback: leaguegamefinder (more reliable for historical dates)
        logger.info(f"Scoreboard returned no finals for {game_date}, trying leaguegamefinder")
        client = await nba._get_client()
        params = {
            "LeagueID": "00",
            "DateFrom": game_date.strftime("%m/%d/%Y"),
            "DateTo": game_date.strftime("%m/%d/%Y"),
            "SeasonType": "Regular Season",
        }
        resp = await client.get("/leaguegamefinder", params=params)
        resp.raise_for_status()
        data = resp.json()
        rs = data.get("resultSets", [{}])[0]
        headers = rs.get("headers", [])
        rows = rs.get("rowSet", [])

        if not rows:
            logger.warning(f"leaguegamefinder also returned no data for {game_date}")
            return actuals

        # leaguegamefinder returns one row per team per game
        # Group by GAME_ID to pair home/away
        games_by_id: dict[str, list[dict]] = {}
        for row in rows:
            d = dict(zip(headers, row))
            gid = d.get("GAME_ID", "")
            games_by_id.setdefault(gid, []).append(d)

        for gid, entries in games_by_id.items():
            if len(entries) < 2:
                continue
            # "vs." means home, "@" means away
            home_entry = next((e for e in entries if "vs." in (e.get("MATCHUP", "") or "")), None)
            away_entry = next((e for e in entries if "@" in (e.get("MATCHUP", "") or "")), None)
            if not home_entry or not away_entry:
                continue

            ht_abbr = (home_entry.get("TEAM_ABBREVIATION") or "???").strip()
            at_abbr = (away_entry.get("TEAM_ABBREVIATION") or "???").strip()
            hs = int(home_entry.get("PTS", 0) or 0)
            as_ = int(away_entry.get("PTS", 0) or 0)

            if hs > 0 or as_ > 0:
                actuals[f"{at_abbr}_{ht_abbr}"] = {"home_score": hs, "away_score": as_}

        logger.info(f"Got {len(actuals)} final scores from leaguegamefinder for {game_date}")

    except Exception as e:
        logger.warning(f"Failed to fetch scores for simulation {game_date}: {e}")
    finally:
        await nba.close()

    return actuals


# ─── Endpoints ─────────────────────────────────────────────────────

@router.get("/", response_model=list[dict])
async def list_simulation_dates() -> list[dict]:
    """List all dates that have saved market snapshots."""
    async with async_session_factory() as session:
        result = await session.execute(text("""
            SELECT game_date,
                   COUNT(*) as total_markets,
                   SUM(CASE WHEN verdict IN ('BUY','STRONG BUY') THEN 1 ELSE 0 END) as buy_count
            FROM market_snapshots
            GROUP BY game_date
            ORDER BY game_date DESC
        """))
        return [
            {
                "date": str(row[0]),
                "games_count": row[1],  # total markets (kept for frontend compat)
                "buy_count": row[2],
            }
            for row in result
        ]


@router.get("/{game_date}", response_model=DailySimulation)
async def get_simulation(game_date: str) -> DailySimulation:
    """Run simulation from DB market snapshots — no JSON files needed."""
    try:
        parsed_date = date.fromisoformat(game_date)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid date: {game_date}")

    # Load market snapshots from DB
    async with async_session_factory() as session:
        result = await session.execute(
            select(MarketSnapshot)
            .where(MarketSnapshot.game_date == parsed_date)
            .where(MarketSnapshot.verdict.in_(["BUY", "STRONG BUY"]))
            .order_by(MarketSnapshot.game_id, MarketSnapshot.market_type)
        )
        snapshots = result.scalars().all()

    if not snapshots:
        raise HTTPException(status_code=404, detail=f"No market snapshots for {game_date}")

    # Fetch actual NBA scores
    actuals = await _fetch_final_scores(parsed_date)

    # Build virtual bets
    sim_bets: list[SimBet] = []

    for snap in snapshots:
        home = snap.home_team
        away = snap.away_team
        game_label = f"{away} @ {home}"
        key = f"{away}_{home}"
        actual = actuals.get(key)

        best_side_name = snap.best_side or ""
        home_label = (snap.home_label or "").lower()
        away_label = (snap.away_label or "").lower()

        # Determine side: map best_side to YES/NO
        if best_side_name.lower() == home_label:
            side = "YES"
        elif best_side_name.lower() in ("over",):
            side = "YES"
        elif best_side_name.lower() == away_label:
            side = "NO"
        elif best_side_name.lower() in ("under",):
            side = "NO"
        elif best_side_name.upper() == "YES":
            side = "YES"
        elif best_side_name.upper() == "NO":
            side = "NO"
        elif best_side_name.upper() == home:
            side = "YES"
        else:
            side = "NO"

        # Entry price
        poly_home_yes = float(snap.polymarket_home_yes or 0.5)
        entry_price = poly_home_yes if side == "YES" else round(1 - poly_home_yes, 4)
        entry_price = max(0.01, min(0.99, entry_price))

        # Kelly
        kelly_frac = float(snap.kelly_fraction or 0)
        kelly_amount = round(kelly_frac * KELLY_BANKROLL, 2)

        line = float(snap.line) if snap.line is not None else None
        selection = _build_selection_label(
            snap.market_type, away, home, side, best_side_name, line,
        )

        # Grade
        flat_result: str | None = None
        flat_pnl = 0.0
        kelly_result: str | None = None
        kelly_pnl = 0.0

        if actual:
            hs = actual["home_score"]
            as_ = actual["away_score"]
            yes_outcome = _grade_yes_outcome(snap.market_type, line, hs, as_)
            if yes_outcome is not None:
                won = yes_outcome if side == "YES" else not yes_outcome
                flat_result = "WIN" if won else "LOSS"
                flat_pnl = _calc_pnl(won, 1.0, entry_price)
                kelly_result = "WIN" if won else "LOSS"
                kelly_pnl = _calc_pnl(won, kelly_amount, entry_price)

        sim_bets.append(SimBet(
            game=game_label,
            market_type=snap.market_type,
            selection=selection,
            side=side,
            verdict=snap.verdict or "",
            entry_price=entry_price,
            model_prob=float(snap.model_probability or 0),
            edge=float(snap.best_edge or 0),
            kelly_fraction=kelly_frac,
            flat_result=flat_result,
            flat_pnl=flat_pnl,
            kelly_amount=kelly_amount,
            kelly_result=kelly_result,
            kelly_pnl=kelly_pnl,
        ))

    # Aggregate
    total_bets = len(sim_bets)
    flat_wins = sum(1 for b in sim_bets if b.flat_result == "WIN")
    flat_losses = sum(1 for b in sim_bets if b.flat_result == "LOSS")
    flat_pnl_total = round(sum(b.flat_pnl for b in sim_bets), 2)
    flat_wagered = sum(1.0 for b in sim_bets if b.flat_result is not None)
    flat_roi = round((flat_pnl_total / flat_wagered * 100) if flat_wagered > 0 else 0.0, 1)

    kelly_wins = sum(1 for b in sim_bets if b.kelly_result == "WIN")
    kelly_losses = sum(1 for b in sim_bets if b.kelly_result == "LOSS")
    kelly_pnl_total = round(sum(b.kelly_pnl for b in sim_bets), 2)
    kelly_wagered = round(sum(b.kelly_amount for b in sim_bets if b.kelly_result is not None), 2)
    kelly_roi = round((kelly_pnl_total / kelly_wagered * 100) if kelly_wagered > 0 else 0.0, 1)

    graded = flat_wins + flat_losses
    flat_record = f"{flat_wins}/{graded}" if graded > 0 else f"0/{total_bets}"

    logger.info(
        f"Simulation {game_date}: {total_bets} bets, "
        f"flat {flat_wins}W-{flat_losses}L PnL=${flat_pnl_total:+.2f}, "
        f"kelly PnL=${kelly_pnl_total:+.2f}"
    )

    return DailySimulation(
        date=game_date,
        total_bets=total_bets,
        flat_wins=flat_wins,
        flat_losses=flat_losses,
        flat_record=flat_record,
        flat_pnl=flat_pnl_total,
        flat_roi=flat_roi,
        kelly_wins=kelly_wins,
        kelly_losses=kelly_losses,
        kelly_pnl=kelly_pnl_total,
        kelly_roi=kelly_roi,
        bets=sim_bets,
    )
