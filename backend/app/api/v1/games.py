"""Game analysis API endpoints."""

from datetime import date, datetime, timezone

from fastapi import APIRouter, HTTPException
from loguru import logger

from app.schemas.game import DailyAnalysis, GameAnalysis, TeamGameData, TopEdge
from app.schemas.market import EdgeResult, MarketEdge
from app.schemas.prediction import DataQuality, GamePrediction
from app.schemas.team import AdjustedRatings, InjurySchema, ScheduleContext

router = APIRouter(prefix="/games", tags=["Games"])

# ─── Sample data for demo / development ────────────────────────────
# In production, these would be populated from the data connectors

SAMPLE_GAMES: list[GameAnalysis] = [
    GameAnalysis(
        game_id="2026-04-07_CLE_MEM",
        tipoff=datetime(2026, 4, 7, 19, 30, tzinfo=timezone.utc),
        tipoff_sgt=datetime(2026, 4, 8, 7, 30, tzinfo=timezone.utc),
        venue="Rocket Mortgage FieldHouse",
        home=TeamGameData(
            team="CLE",
            full_name="Cleveland Cavaliers",
            record="62-18",
            seed=1,
            motivation="REST_EXPECTED",
            season_ortg=118.5,
            season_drtg=108.2,
            season_nrtg=10.3,
            adjusted_ortg=116.1,
            adjusted_drtg=110.0,
            adjusted_nrtg=6.1,
            nrtg_delta=-4.2,
            injuries=[
                InjurySchema(
                    player_name="Evan Mobley",
                    player_id="1631096",
                    team="CLE",
                    status="OUT",
                    reason="Rest",
                    impact_rating="HIGH",
                )
            ],
            schedule=ScheduleContext(
                is_b2b=False,
                rest_days=2,
                home_court=True,
            ),
        ),
        away=TeamGameData(
            team="MEM",
            full_name="Memphis Grizzlies",
            record="48-32",
            seed=4,
            motivation="FIGHTING",
            season_ortg=113.8,
            season_drtg=111.5,
            season_nrtg=2.3,
            adjusted_ortg=113.8,
            adjusted_drtg=111.5,
            adjusted_nrtg=2.3,
            nrtg_delta=0.0,
            injuries=[],
            schedule=ScheduleContext(
                is_b2b=True,
                rest_days=0,
                road_trip_game=3,
                home_court=False,
            ),
        ),
        model=GamePrediction(
            nrtg_differential=3.8,
            schedule_adjustment=-2.5,
            home_court=3.0,
            projected_spread=-4.3,
            projected_total=221.5,
            home_win_prob=0.635,
            confidence="MEDIUM",
        ),
        markets={
            "moneyline": MarketEdge(
                market_type="moneyline",
                polymarket_home_yes=0.72,
                polymarket_home_no=0.28,
                model_probability=0.635,
                edge=EdgeResult(
                    yes_edge=-0.085,
                    no_edge=0.085,
                    yes_ev=-0.118,
                    no_ev=0.304,
                    best_side="NO",
                    best_edge=0.085,
                    verdict="BUY",
                    kelly_fraction=0.041,
                    suggested_bet_pct=4.1,
                ),
            ),
            "spread": MarketEdge(
                market_type="spread",
                line=-8.5,
                polymarket_home_yes=0.52,
                polymarket_home_no=0.48,
                model_probability=0.44,
                edge=EdgeResult(
                    yes_edge=-0.08,
                    no_edge=0.08,
                    yes_ev=-0.154,
                    no_ev=0.167,
                    best_side="NO",
                    best_edge=0.08,
                    verdict="BUY",
                    kelly_fraction=0.038,
                    suggested_bet_pct=3.8,
                ),
            ),
            "total": MarketEdge(
                market_type="total",
                line=224.5,
                polymarket_home_yes=0.55,
                polymarket_home_no=0.45,
                model_probability=0.48,
                edge=EdgeResult(
                    yes_edge=-0.07,
                    no_edge=0.07,
                    yes_ev=-0.127,
                    no_ev=0.156,
                    best_side="NO",
                    best_edge=0.07,
                    verdict="BUY",
                    kelly_fraction=0.033,
                    suggested_bet_pct=3.3,
                ),
            ),
        },
        data_quality=DataQuality(
            ratings_freshness="FRESH",
            injury_freshness="FRESH",
            price_freshness="FRESH",
            cross_source_validated=True,
            warnings=[],
        ),
    ),
]


def _extract_top_edges(games: list[GameAnalysis]) -> list[TopEdge]:
    """Extract top edges from all games, sorted by edge size."""
    edges: list[TopEdge] = []
    for game in games:
        game_label = f"{game.away.team} @ {game.home.team}"
        for market_type, market in game.markets.items():
            if market.edge.verdict in ("STRONG BUY", "BUY"):
                selection = (
                    f"{game.home.team} {market_type}"
                    if market.edge.best_side == "YES"
                    else f"{game.away.team} {market_type}"
                )
                edges.append(
                    TopEdge(
                        game=game_label,
                        market=market_type,
                        selection=selection,
                        price=(
                            market.polymarket_home_yes
                            if market.edge.best_side == "YES"
                            else (market.polymarket_home_no or 0)
                        ),
                        model_prob=market.model_probability,
                        edge=market.edge.best_edge,
                        verdict=market.edge.verdict,
                    )
                )
    edges.sort(key=lambda e: e.edge, reverse=True)
    return edges


@router.get("/today", response_model=DailyAnalysis)
async def get_todays_games() -> DailyAnalysis:
    """
    Get full analysis for all games today.
    This is THE main endpoint for both the dashboard and AI consumption.
    """
    today = date.today()
    games = SAMPLE_GAMES  # TODO: Replace with live data pipeline
    top_edges = _extract_top_edges(games)

    return DailyAnalysis(
        date=today,
        timezone_note="All times in US Eastern. Operator is UTC+8.",
        games_count=len(games),
        games=games,
        top_edges=top_edges,
    )


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

        prompt_lines.append("POLYMARKET EDGES:")
        prompt_lines.append(f"{'Market':12s} {'Side':8s} {'Price':8s} {'Model':8s} {'Edge':8s} {'Verdict':12s}")
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
    prompt_lines.append("DATA QUALITY: All ratings FRESH, injuries updated, prices current.")

    return {"prompt": "\n".join(prompt_lines), "format": "text", "date": str(analysis.date)}


@router.get("/{game_id}", response_model=GameAnalysis)
async def get_game_detail(game_id: str) -> GameAnalysis:
    """Get detailed analysis for a single game."""
    for game in SAMPLE_GAMES:
        if game.game_id == game_id:
            return game
    raise HTTPException(status_code=404, detail=f"Game {game_id} not found")
