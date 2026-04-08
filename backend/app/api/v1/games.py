"""Game analysis API endpoints — wired to live data pipeline."""

from datetime import date, datetime, timezone

from fastapi import APIRouter, HTTPException, Query
from loguru import logger
from pydantic import BaseModel

from app.schemas.game import DailyAnalysis, GameAnalysis, TeamGameData, TopEdge
from app.schemas.market import EdgeResult, MarketEdge
from app.schemas.prediction import DataQuality, GamePrediction
from app.schemas.team import AdjustedRatings, InjurySchema, ScheduleContext
from app.services.pipeline import clear_pipeline_cache, run_daily_pipeline
from app.services.prediction_store import list_saved_dates, load_predictions

router = APIRouter(prefix="/games", tags=["Games"])

# ─── In-memory store for game lookups within a session ──────────────
_last_analysis: DailyAnalysis | None = None


class InjuryOverrideRequest(BaseModel):
    """Request body for customizing QUESTIONABLE player handling.

    injury_overrides: dict of player_name → mode
      "FULL" = definitely missing (100% impact)
      "HALF" = uncertain (50% impact) — default for QUESTIONABLE
      "OFF"  = expected to play (0% impact, excluded)
    """
    injury_overrides: dict[str, str] = {}


@router.get("/today", response_model=DailyAnalysis)
async def get_todays_games() -> DailyAnalysis:
    """
    Get full analysis for all games today.
    This is THE main endpoint for both the dashboard and AI consumption.
    Pulls live data from NBA API, Polymarket, and injury feeds.
    """
    global _last_analysis
    try:
        analysis = await run_daily_pipeline()
        _last_analysis = analysis
        return analysis
    except Exception as e:
        logger.error(f"Pipeline failed: {e}")
        return DailyAnalysis(
            date=date.today(),
            games_count=0,
            games=[],
            top_edges=[],
        )


@router.post("/today", response_model=DailyAnalysis)
async def get_todays_games_with_overrides(body: InjuryOverrideRequest) -> DailyAnalysis:
    """
    Get full analysis with custom injury overrides.
    Use this to toggle QUESTIONABLE players between FULL/HALF/OFF.
    Bypasses cache so you get fresh recalculation.
    """
    global _last_analysis
    try:
        analysis = await run_daily_pipeline(
            injury_overrides=body.injury_overrides if body.injury_overrides else None,
        )
        _last_analysis = analysis
        return analysis
    except Exception as e:
        logger.error(f"Pipeline with overrides failed: {e}")
        return DailyAnalysis(
            date=date.today(),
            games_count=0,
            games=[],
            top_edges=[],
        )


# ─── History Endpoints ──────────────────────────────────────────────


@router.get("/history", response_model=list[dict])
async def get_prediction_history() -> list[dict]:
    """List all dates that have saved predictions.
    
    Returns [{date, games_count, saved_at, file_size_kb}] sorted by date desc.
    """
    return list_saved_dates()


@router.get("/history/{game_date}", response_model=DailyAnalysis)
async def get_predictions_for_date(game_date: str) -> DailyAnalysis:
    """Load saved predictions for a specific date.
    
    Date format: YYYY-MM-DD (e.g. 2026-04-08)
    """
    try:
        parsed_date = date.fromisoformat(game_date)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid date format: {game_date}. Use YYYY-MM-DD.")
    
    analysis = load_predictions(parsed_date)
    if analysis is None:
        raise HTTPException(status_code=404, detail=f"No saved predictions for {game_date}")
    
    return analysis


@router.get("/upcoming", response_model=DailyAnalysis)
async def get_upcoming_games() -> DailyAnalysis:
    """Get all games that haven't tipped off yet — merges today's live data
    with any saved predictions for games still in the future.
    
    This is what the dashboard should use so you never miss a game that was
    predicted yesterday but tips off today.
    """
    now_utc = datetime.now(timezone.utc)
    today = date.today()
    
    # 1. Get today's live analysis
    try:
        today_analysis = await run_daily_pipeline()
    except Exception as e:
        logger.error(f"Pipeline failed for upcoming: {e}")
        today_analysis = DailyAnalysis(date=today, games_count=0, games=[], top_edges=[])
    
    # Collect all upcoming games, keyed by game_id to dedupe
    upcoming: dict[str, GameAnalysis] = {}
    
    # Add today's games that haven't tipped off (or all if no tipoff info)
    for game in today_analysis.games:
        if game.tipoff is None or game.tipoff > now_utc:
            upcoming[game.game_id] = game
        # Also include games that tipped off within last 3 hours (still in progress)
        elif game.tipoff and (now_utc - game.tipoff).total_seconds() < 10800:
            upcoming[game.game_id] = game
    
    # 2. Check saved predictions from yesterday/day-before for late games
    # (e.g., games predicted yesterday at 10am SGT that play at 11am SGT today)
    for days_back in range(1, 3):
        past_date = today - __import__("datetime").timedelta(days=days_back)
        saved = load_predictions(past_date)
        if saved:
            for game in saved.games:
                # Only add if game hasn't tipped off yet and not already in list
                if game.game_id not in upcoming:
                    if game.tipoff and game.tipoff > now_utc:
                        upcoming[game.game_id] = game
    
    # Sort by tipoff time
    sorted_games = sorted(
        upcoming.values(),
        key=lambda g: g.tipoff or datetime.max.replace(tzinfo=timezone.utc),
    )
    
    # Rebuild top edges from the merged set
    from app.services.pipeline import _extract_top_edges
    top_edges = _extract_top_edges(sorted_games)
    
    return DailyAnalysis(
        date=today,
        games_count=len(sorted_games),
        games=sorted_games,
        top_edges=top_edges,
    )


# ─── Existing Endpoints ─────────────────────────────────────────────


@router.get("/today/ai-prompt", response_model=dict)
async def get_ai_prompt() -> dict:
    """
    Get pre-formatted text prompt for Claude/Gemini.
    Returns structured analysis optimized for AI consumption.
    """
    analysis = await get_todays_games()
    prompt_lines: list[str] = []
    prompt_lines.append(f"COURTEDGE ANALYSIS — {analysis.date.strftime('%B %d, %Y')}")
    prompt_lines.append("=" * 50)
    prompt_lines.append("")

    if not analysis.games:
        prompt_lines.append("No NBA games scheduled today.")
        return {"prompt": "\n".join(prompt_lines), "format": "text", "date": str(analysis.date)}

    for i, game in enumerate(analysis.games, 1):
        tipoff_str = game.tipoff.strftime("%I:%M %p ET") if game.tipoff else "TBD"
        prompt_lines.append(
            f"GAME {i}: {game.away.team} @ {game.home.team} | {tipoff_str}"
        )
        prompt_lines.append(f"Venue: {game.venue} ({game.home.team} home)")
        prompt_lines.append("")
        prompt_lines.append("LINEUP-ADJUSTED RATINGS:")
        prompt_lines.append(f"{'':18s} Season NRtg    Adjusted NRtg    Delta")
        prompt_lines.append(
            f"{game.home.team} ({game.home.record}, #{game.home.seed}):  "
            f"{game.home.season_nrtg:+6.1f}       {game.home.adjusted_nrtg:+6.1f}       "
            f"{game.home.nrtg_delta:+5.1f}"
        )
        inj_str = ", ".join(
            f"{inj.player_name} ({inj.status})" for inj in game.home.injuries
        ) or "Full strength"
        prompt_lines.append(f"  Injuries: {inj_str}")

        prompt_lines.append(
            f"{game.away.team} ({game.away.record}, #{game.away.seed}):  "
            f"{game.away.season_nrtg:+6.1f}       {game.away.adjusted_nrtg:+6.1f}       "
            f"{game.away.nrtg_delta:+5.1f}"
        )
        inj_str = ", ".join(
            f"{inj.player_name} ({inj.status})" for inj in game.away.injuries
        ) or "Full strength"
        prompt_lines.append(f"  Injuries: {inj_str}")
        prompt_lines.append("")

        prompt_lines.append("MODEL PROJECTION:")
        prompt_lines.append(
            f"  NRtg diff: {game.model.nrtg_differential:+.1f} → "
            f"Spread: {game.model.projected_spread:+.1f} → "
            f"Win prob: {game.home.team} {game.model.home_win_prob:.1%}"
        )
        prompt_lines.append(f"  Projected total: {game.model.projected_total}")
        prompt_lines.append("")

        if game.markets:
            prompt_lines.append("POLYMARKET EDGES:")
            prompt_lines.append(
                f"{'Market':12s} {'Side':8s} {'Price':8s} {'Model':8s} {'Edge':8s} {'Verdict':12s}"
            )
            for mtype, mkt in game.markets.items():
                side_label = mkt.edge.best_side
                price = (
                    mkt.polymarket_home_yes
                    if mkt.edge.best_side == "YES"
                    else (mkt.polymarket_home_no or 0)
                )
                prompt_lines.append(
                    f"{mtype:12s} {side_label:8s} ${price:.2f}    "
                    f"{mkt.model_probability:.1%}    {mkt.edge.best_edge:+.1%}    {mkt.edge.verdict}"
                )
        else:
            prompt_lines.append("POLYMARKET EDGES: No markets found for this game")

        prompt_lines.append("")
        prompt_lines.append("-" * 50)
        prompt_lines.append("")

    # Top edges summary
    if analysis.top_edges:
        prompt_lines.append("TOP EDGES:")
        for edge in analysis.top_edges[:5]:
            prompt_lines.append(
                f"  {edge.verdict}: {edge.selection} @ ${edge.price:.2f} "
                f"(edge: {edge.edge:+.1%})"
            )

    prompt_lines.append("")
    prompt_lines.append("=" * 50)

    # Data quality summary
    dq_parts = []
    for game in analysis.games:
        dq = game.data_quality
        dq_parts.append(f"ratings={dq.ratings_freshness}")
        dq_parts.append(f"injuries={dq.injury_freshness}")
        dq_parts.append(f"prices={dq.price_freshness}")
        break
    prompt_lines.append(f"DATA QUALITY: {', '.join(dq_parts) if dq_parts else 'N/A'}")

    return {"prompt": "\n".join(prompt_lines), "format": "text", "date": str(analysis.date)}


@router.get("/{game_id}", response_model=GameAnalysis)
async def get_game_detail(game_id: str) -> GameAnalysis:
    """Get detailed analysis for a single game."""
    global _last_analysis
    if _last_analysis:
        for game in _last_analysis.games:
            if game.game_id == game_id:
                return game

    analysis = await run_daily_pipeline()
    _last_analysis = analysis
    for game in analysis.games:
        if game.game_id == game_id:
            return game

    raise HTTPException(status_code=404, detail=f"Game {game_id} not found")


@router.post("/refresh")
async def refresh_pipeline() -> dict:
    """Force refresh the pipeline cache. Hit this to re-fetch all data."""
    clear_pipeline_cache()
    analysis = await run_daily_pipeline()
    return {
        "status": "refreshed",
        "games_count": analysis.games_count,
        "top_edges_count": len(analysis.top_edges),
    }
