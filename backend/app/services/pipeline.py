"""
Live Data Pipeline — Orchestrates all connectors and analytics engines.

Flow:
1. Fetch today's games from NBA API
2. Fetch team ratings, standings, injury reports, Polymarket prices
3. Compute on/off player impacts, lineup-adjusted ratings
4. Run prediction model, edge calculator
5. Assemble GameAnalysis objects → DailyAnalysis
"""

from __future__ import annotations

import asyncio
from datetime import date, datetime, timedelta, timezone
from typing import Any

from loguru import logger

from app.analytics.edge_calculator import calculate_edge, calculate_game_edges
from app.analytics.lineup_adjustment import OnOffSplitModel, compute_player_impact
from app.analytics.prediction_model import calculate_schedule_modifier, predict_game
from app.analytics.schedule_engine import calculate_schedule_context, determine_motivation
from app.connectors.injuries import InjuryFeedConnector
from app.connectors.nba_api import NBAApiConnector
from app.connectors.pbpstats import PBPStatsConnector
from app.connectors.polymarket import PolymarketConnector
from app.schemas.game import DailyAnalysis, GameAnalysis, TeamGameData, TopEdge
from app.schemas.market import EdgeResult, MarketEdge
from app.schemas.prediction import DataQuality, GamePrediction
from app.schemas.team import InjurySchema, PlayerAbsence, ScheduleContext


# ─── NBA Team ID ↔ Abbreviation maps ───────────────────────────────
# stats.nba.com uses numeric TEAM_ID; we use 3-letter abbreviations.
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

NBA_ABBR_TO_TEAM_ID: dict[str, int] = {v: k for k, v in NBA_TEAM_ID_TO_ABBR.items()}

# Full team names (for display)
NBA_TEAM_NAMES: dict[str, str] = {
    "ATL": "Atlanta Hawks", "BOS": "Boston Celtics", "BKN": "Brooklyn Nets",
    "CHA": "Charlotte Hornets", "CHI": "Chicago Bulls", "CLE": "Cleveland Cavaliers",
    "DAL": "Dallas Mavericks", "DEN": "Denver Nuggets", "DET": "Detroit Pistons",
    "GSW": "Golden State Warriors", "HOU": "Houston Rockets", "IND": "Indiana Pacers",
    "LAC": "LA Clippers", "LAL": "Los Angeles Lakers", "MEM": "Memphis Grizzlies",
    "MIA": "Miami Heat", "MIL": "Milwaukee Bucks", "MIN": "Minnesota Timberwolves",
    "NOP": "New Orleans Pelicans", "NYK": "New York Knicks", "OKC": "Oklahoma City Thunder",
    "ORL": "Orlando Magic", "PHI": "Philadelphia 76ers", "PHX": "Phoenix Suns",
    "POR": "Portland Trail Blazers", "SAC": "Sacramento Kings", "SAS": "San Antonio Spurs",
    "TOR": "Toronto Raptors", "UTA": "Utah Jazz", "WAS": "Washington Wizards",
}

# NBA Tricode mapping (scoreboard API uses triCode)
TRICODE_TO_ABBR: dict[str, str] = {
    "ATL": "ATL", "BOS": "BOS", "BKN": "BKN", "CHA": "CHA", "CHI": "CHI",
    "CLE": "CLE", "DAL": "DAL", "DEN": "DEN", "DET": "DET", "GSW": "GSW",
    "HOU": "HOU", "IND": "IND", "LAC": "LAC", "LAL": "LAL", "MEM": "MEM",
    "MIA": "MIA", "MIL": "MIL", "MIN": "MIN", "NOP": "NOP", "NYK": "NYK",
    "OKC": "OKC", "ORL": "ORL", "PHI": "PHI", "PHX": "PHX", "POR": "POR",
    "SAC": "SAC", "SAS": "SAS", "TOR": "TOR", "UTA": "UTA", "WAS": "WAS",
}

# Lineup model singleton
_lineup_model = OnOffSplitModel()


# ─── Pipeline Cache ─────────────────────────────────────────────────
class PipelineCache:
    """Simple in-memory TTL cache for pipeline data."""

    def __init__(self) -> None:
        self._store: dict[str, tuple[Any, datetime]] = {}

    def get(self, key: str, ttl_seconds: int = 300) -> Any | None:
        if key not in self._store:
            return None
        value, ts = self._store[key]
        if (datetime.now(timezone.utc) - ts).total_seconds() > ttl_seconds:
            del self._store[key]
            return None
        return value

    def set(self, key: str, value: Any) -> None:
        self._store[key] = (value, datetime.now(timezone.utc))

    def clear(self) -> None:
        self._store.clear()


_cache = PipelineCache()


# ─── Main Pipeline ──────────────────────────────────────────────────

async def run_daily_pipeline(game_date: date | None = None) -> DailyAnalysis:
    """
    Run the full data pipeline for today's games.
    This is THE function that replaces SAMPLE_GAMES.
    """
    if game_date is None:
        game_date = date.today()

    # Check cache first (5 min TTL for full analysis)
    cache_key = f"daily_{game_date.isoformat()}"
    cached = _cache.get(cache_key, ttl_seconds=300)
    if cached is not None:
        logger.info(f"Returning cached analysis for {game_date}")
        return cached

    logger.info(f"=== Starting live pipeline for {game_date} ===")
    warnings: list[str] = []

    # Step 1: Fetch today's schedule
    games_raw = await _fetch_todays_games(game_date, warnings)
    if not games_raw:
        logger.warning("No games found for today. Returning empty analysis.")
        result = DailyAnalysis(
            date=game_date,
            games_count=0,
            games=[],
            top_edges=[],
        )
        _cache.set(cache_key, result)
        return result

    logger.info(f"Found {len(games_raw)} games for {game_date}")

    # Step 2: Fetch supporting data in parallel
    team_abbrs = set()
    for g in games_raw:
        team_abbrs.add(g["home_team"])
        team_abbrs.add(g["away_team"])

    ratings_task = _fetch_team_ratings(warnings)
    standings_task = _fetch_standings(warnings)
    injuries_task = _fetch_injuries(warnings)
    polymarket_task = _fetch_all_polymarket_markets(warnings)

    ratings_data, standings_data, injuries_data, polymarket_markets = await asyncio.gather(
        ratings_task, standings_task, injuries_task, polymarket_task
    )

    # Step 3: Process each game
    game_analyses: list[GameAnalysis] = []
    for game_raw in games_raw:
        try:
            analysis = await _process_single_game(
                game_raw=game_raw,
                game_date=game_date,
                ratings_data=ratings_data,
                standings_data=standings_data,
                injuries_data=injuries_data,
                polymarket_markets=polymarket_markets,
                warnings=warnings,
            )
            game_analyses.append(analysis)
        except Exception as e:
            logger.error(f"Failed to process game {game_raw.get('game_id', '?')}: {e}")
            warnings.append(f"Failed to process game: {e}")

    # Step 4: Extract top edges
    top_edges = _extract_top_edges(game_analyses)

    # Step 5: Assemble final response
    result = DailyAnalysis(
        date=game_date,
        games_count=len(game_analyses),
        games=game_analyses,
        top_edges=top_edges,
    )

    _cache.set(cache_key, result)
    logger.info(
        f"=== Pipeline complete: {len(game_analyses)} games, "
        f"{len(top_edges)} edges, {len(warnings)} warnings ==="
    )
    return result


# ─── Step 1: Fetch Schedule ────────────────────────────────────────

async def _fetch_todays_games(
    game_date: date, warnings: list[str]
) -> list[dict[str, Any]]:
    """Fetch and normalize today's game schedule from NBA API."""
    nba = NBAApiConnector()
    try:
        raw_games = await nba.get_todays_games(game_date)
        games = []
        for g in raw_games:
            home_team = _resolve_team_abbr(g, "homeTeam")
            away_team = _resolve_team_abbr(g, "awayTeam")
            if not home_team or not away_team:
                logger.warning(f"Could not resolve teams for game: {g}")
                continue

            # Parse tipoff time
            tipoff = None
            game_time_utc = g.get("gameTimeUTC") or g.get("gameEt") or g.get("gameDateTimeUtc")
            if game_time_utc:
                try:
                    tipoff = datetime.fromisoformat(game_time_utc.replace("Z", "+00:00"))
                except (ValueError, AttributeError):
                    pass

            game_id = f"{game_date.isoformat()}_{away_team}_{home_team}"
            venue = g.get("arenaName", "") or g.get("arena", {}).get("arenaName", "") or ""

            games.append({
                "game_id": game_id,
                "home_team": home_team,
                "away_team": away_team,
                "tipoff": tipoff,
                "venue": venue,
                "raw": g,
            })
        return games
    except Exception as e:
        logger.error(f"Failed to fetch today's games: {e}")
        warnings.append(f"NBA schedule fetch failed: {e}")
        return []
    finally:
        await nba.close()


def _resolve_team_abbr(game_data: dict, team_key: str) -> str | None:
    """Extract team abbreviation from NBA scoreboard response."""
    team = game_data.get(team_key, {})
    if isinstance(team, dict):
        # scoreboardv3 format: {"teamTricode": "BOS", "teamId": 1610612738, ...}
        tricode = team.get("teamTricode", "")
        if tricode and tricode in TRICODE_TO_ABBR:
            return TRICODE_TO_ABBR[tricode]
        team_id = team.get("teamId")
        if team_id and team_id in NBA_TEAM_ID_TO_ABBR:
            return NBA_TEAM_ID_TO_ABBR[team_id]
    return None


# ─── Step 2: Fetch Supporting Data ─────────────────────────────────

async def _fetch_team_ratings(
    warnings: list[str],
) -> dict[str, dict[str, float]]:
    """Fetch team ratings from NBA API → {team_abbr: {ortg, drtg, nrtg, pace}}."""
    cached = _cache.get("team_ratings", ttl_seconds=3600)  # 1hr cache
    if cached:
        return cached

    nba = NBAApiConnector()
    result: dict[str, dict[str, float]] = {}
    try:
        raw = await nba.get_team_ratings()
        for row in raw:
            team_id = row.get("TEAM_ID")
            abbr = NBA_TEAM_ID_TO_ABBR.get(team_id)
            if not abbr:
                continue
            # Handle both Advanced (OFF_RATING) and Base stats column names
            ortg = row.get("OFF_RATING") or row.get("E_OFF_RATING")
            drtg = row.get("DEF_RATING") or row.get("E_DEF_RATING")
            nrtg = row.get("NET_RATING") or row.get("E_NET_RATING")
            pace = row.get("PACE") or row.get("E_PACE")

            # If Advanced columns not present, estimate from basic stats
            if ortg is None:
                # Basic stats don't have ORtg directly. Use PTS + league avg.
                pts = float(row.get("PTS", 110))
                # Rough estimate: ORtg ≈ PTS * (100 / pace_est)
                ortg = pts  # simplified fallback
                drtg = float(row.get("OPP_PTS", 110)) if "OPP_PTS" in row else 110.0
                nrtg = ortg - drtg

            result[abbr] = {
                "ortg": float(ortg or 112),
                "drtg": float(drtg or 110),
                "nrtg": float(nrtg or 2),
                "pace": float(pace or 100),
            }
        logger.info(f"Fetched ratings for {len(result)} teams")
        _cache.set("team_ratings", result)
    except Exception as e:
        logger.error(f"Failed to fetch team ratings: {e}")
        warnings.append(f"Team ratings unavailable: {e}")
    finally:
        await nba.close()
    return result


async def _fetch_standings(
    warnings: list[str],
) -> dict[str, dict[str, Any]]:
    """Fetch standings → {team_abbr: {wins, losses, seed, clinch, ...}}."""
    cached = _cache.get("standings", ttl_seconds=3600)
    if cached:
        return cached

    nba = NBAApiConnector()
    result: dict[str, dict[str, Any]] = {}
    try:
        raw = await nba.get_standings()
        for row in raw:
            # leaguestandingsv3 returns various column names
            team_id = row.get("TeamID")
            abbr = NBA_TEAM_ID_TO_ABBR.get(team_id)
            if not abbr:
                # Try matching by name/city
                continue
            wins = int(row.get("WINS", row.get("W", 0)))
            losses = int(row.get("LOSSES", row.get("L", 0)))
            seed = int(row.get("PlayoffRank", row.get("SEED", row.get("ConferenceRank", 15))))
            clinch = row.get("ClinchIndicator", row.get("ClinchedPlayoffs", ""))

            # Map clinch indicator
            clinch_status = "NONE"
            if clinch:
                clinch_lower = str(clinch).lower()
                if "1" in clinch_lower or "z" in clinch_lower:
                    clinch_status = "CLINCHED_1_SEED"
                elif "x" in clinch_lower or "playoff" in clinch_lower:
                    clinch_status = "CLINCHED_PLAYOFF"
                elif "e" in clinch_lower or "elim" in clinch_lower:
                    clinch_status = "ELIMINATED"

            result[abbr] = {
                "wins": wins,
                "losses": losses,
                "record": f"{wins}-{losses}",
                "seed": seed,
                "clinch_status": clinch_status,
                "games_back": float(row.get("GB", row.get("ConferenceGamesBack", 0)) or 0),
            }
        logger.info(f"Fetched standings for {len(result)} teams")
        _cache.set("standings", result)
    except Exception as e:
        logger.error(f"Failed to fetch standings: {e}")
        warnings.append(f"Standings unavailable: {e}")
    finally:
        await nba.close()
    return result


async def _fetch_injuries(
    warnings: list[str],
) -> dict[str, list[dict[str, Any]]]:
    """Fetch injuries → {team_abbr: [injury_dicts]}."""
    cached = _cache.get("injuries", ttl_seconds=600)  # 10min
    if cached:
        return cached

    feed = InjuryFeedConnector()
    result: dict[str, list[dict[str, Any]]] = {}
    try:
        raw = await feed.get_injury_report()
        for inj in raw:
            team = inj.get("team", "")
            if team:
                result.setdefault(team, []).append(inj)
        logger.info(f"Fetched injuries for {len(result)} teams ({sum(len(v) for v in result.values())} players)")
        _cache.set("injuries", result)
    except Exception as e:
        logger.error(f"Failed to fetch injuries: {e}")
        warnings.append(f"Injury data unavailable: {e}")
    finally:
        await feed.close()
    return result


async def _fetch_all_polymarket_markets(
    warnings: list[str],
) -> list[dict[str, Any]]:
    """Fetch all active NBA Polymarket markets."""
    cached = _cache.get("polymarket_markets", ttl_seconds=120)  # 2min
    if cached:
        return cached

    poly = PolymarketConnector()
    result: list[dict[str, Any]] = []
    try:
        result = await poly.get_nba_markets()
        logger.info(f"Fetched {len(result)} Polymarket NBA markets")
        _cache.set("polymarket_markets", result)
    except Exception as e:
        logger.error(f"Failed to fetch Polymarket markets: {e}")
        warnings.append(f"Polymarket data unavailable: {e}")
    finally:
        await poly.close()
    return result


# ─── Step 3: Process Single Game ───────────────────────────────────

async def _process_single_game(
    game_raw: dict[str, Any],
    game_date: date,
    ratings_data: dict[str, dict[str, float]],
    standings_data: dict[str, dict[str, Any]],
    injuries_data: dict[str, list[dict[str, Any]]],
    polymarket_markets: list[dict[str, Any]],
    warnings: list[str],
) -> GameAnalysis:
    """Process a single game through the full analytics pipeline."""
    home_abbr = game_raw["home_team"]
    away_abbr = game_raw["away_team"]
    game_id = game_raw["game_id"]
    tipoff: datetime | None = game_raw.get("tipoff")
    venue = game_raw.get("venue", "")

    logger.info(f"Processing {away_abbr} @ {home_abbr}")

    # ── Get team ratings ──
    home_ratings = ratings_data.get(home_abbr, {"ortg": 112.0, "drtg": 110.0, "nrtg": 2.0, "pace": 100.0})
    away_ratings = ratings_data.get(away_abbr, {"ortg": 112.0, "drtg": 110.0, "nrtg": 2.0, "pace": 100.0})

    # ── Get standings ──
    home_standings = standings_data.get(home_abbr, {"record": "0-0", "seed": 15, "clinch_status": "NONE", "wins": 0, "losses": 0})
    away_standings = standings_data.get(away_abbr, {"record": "0-0", "seed": 15, "clinch_status": "NONE", "wins": 0, "losses": 0})

    # ── Get injuries ──
    home_injuries_raw = injuries_data.get(home_abbr, [])
    away_injuries_raw = injuries_data.get(away_abbr, [])

    # ── Build player absences with impact ──
    home_absences = _build_player_absences(home_injuries_raw)
    away_absences = _build_player_absences(away_injuries_raw)

    # ── Lineup-adjusted ratings ──
    home_adj = _lineup_model.calculate_adjusted_ratings(
        team_id=home_abbr,
        season_ortg=home_ratings["ortg"],
        season_drtg=home_ratings["drtg"],
        missing_players=home_absences,
    )
    away_adj = _lineup_model.calculate_adjusted_ratings(
        team_id=away_abbr,
        season_ortg=away_ratings["ortg"],
        season_drtg=away_ratings["drtg"],
        missing_players=away_absences,
    )

    # ── Schedule context ──
    home_schedule = ScheduleContext(home_court=True)
    away_schedule = ScheduleContext(home_court=False)

    home_sched_mod = calculate_schedule_modifier(
        is_b2b=home_schedule.is_b2b,
        rest_days=home_schedule.rest_days,
        road_trip_game=home_schedule.road_trip_game,
    )
    away_sched_mod = calculate_schedule_modifier(
        is_b2b=away_schedule.is_b2b,
        rest_days=away_schedule.rest_days,
        road_trip_game=away_schedule.road_trip_game,
    )

    # ── Motivation ──
    games_remaining = 82 - (home_standings.get("wins", 0) + home_standings.get("losses", 0))
    home_motivation = determine_motivation(
        team=home_abbr,
        record=home_standings.get("record", "0-0"),
        conference_seed=home_standings.get("seed", 15),
        clinch_status=home_standings.get("clinch_status", "NONE"),
        games_remaining=max(0, games_remaining),
    )
    away_games_remaining = 82 - (away_standings.get("wins", 0) + away_standings.get("losses", 0))
    away_motivation = determine_motivation(
        team=away_abbr,
        record=away_standings.get("record", "0-0"),
        conference_seed=away_standings.get("seed", 15),
        clinch_status=away_standings.get("clinch_status", "NONE"),
        games_remaining=max(0, away_games_remaining),
    )

    # ── Prediction model ──
    # Find Polymarket prices for this game
    poly_prices = _find_polymarket_prices(
        away_abbr, home_abbr, game_date, polymarket_markets
    )

    prediction = predict_game(
        home_adj_nrtg=home_adj.adjusted_nrtg,
        away_adj_nrtg=away_adj.adjusted_nrtg,
        home_adj_ortg=home_adj.adjusted_ortg,
        home_adj_drtg=home_adj.adjusted_drtg,
        away_adj_ortg=away_adj.adjusted_ortg,
        away_adj_drtg=away_adj.adjusted_drtg,
        home_schedule_mod=home_sched_mod,
        away_schedule_mod=away_sched_mod,
        spread_line=poly_prices.get("spread_line"),
        total_line=poly_prices.get("total_line"),
    )

    # ── Edge calculation ──
    markets: dict[str, MarketEdge] = {}

    ml_price = poly_prices.get("moneyline_home_yes")
    if ml_price is not None:
        ml_edge = calculate_edge(prediction.home_win_prob, ml_price)
        markets["moneyline"] = MarketEdge(
            market_type="moneyline",
            polymarket_home_yes=ml_price,
            polymarket_home_no=round(1.0 - ml_price, 3) if ml_price else None,
            model_probability=prediction.home_win_prob,
            edge=ml_edge,
        )

    spread_price = poly_prices.get("spread_home_yes")
    if spread_price is not None:
        # Use spread cover prob from prediction (default 0.5 if no line)
        spread_cover_prob = prediction.home_win_prob  # simplified for v1
        spread_edge = calculate_edge(spread_cover_prob, spread_price)
        markets["spread"] = MarketEdge(
            market_type="spread",
            line=poly_prices.get("spread_line"),
            polymarket_home_yes=spread_price,
            polymarket_home_no=round(1.0 - spread_price, 3) if spread_price else None,
            model_probability=spread_cover_prob,
            edge=spread_edge,
        )

    total_price = poly_prices.get("total_over_yes")
    if total_price is not None:
        over_prob = 0.5  # Default; will improve when we have total line
        total_edge = calculate_edge(over_prob, total_price)
        markets["total"] = MarketEdge(
            market_type="total",
            line=poly_prices.get("total_line"),
            polymarket_home_yes=total_price,
            polymarket_home_no=round(1.0 - total_price, 3) if total_price else None,
            model_probability=over_prob,
            edge=total_edge,
        )

    # ── Build injury schemas for display ──
    home_injury_schemas = [
        InjurySchema(
            player_name=inj.get("player_name", "Unknown"),
            player_id=inj.get("player_id", ""),
            team=home_abbr,
            status=inj.get("status", "OUT"),
            reason=inj.get("reason"),
            source=inj.get("source", "NBA"),
            impact_rating=_rate_impact(inj),
        )
        for inj in home_injuries_raw
    ]
    away_injury_schemas = [
        InjurySchema(
            player_name=inj.get("player_name", "Unknown"),
            player_id=inj.get("player_id", ""),
            team=away_abbr,
            status=inj.get("status", "OUT"),
            reason=inj.get("reason"),
            source=inj.get("source", "NBA"),
            impact_rating=_rate_impact(inj),
        )
        for inj in away_injuries_raw
    ]

    # ── Tipoff in SGT (UTC+8) ──
    tipoff_sgt = None
    if tipoff:
        tipoff_sgt = tipoff + timedelta(hours=8)

    # ── Data quality ──
    data_quality = DataQuality(
        ratings_freshness="FRESH" if ratings_data else "MISSING",
        injury_freshness="FRESH" if injuries_data else "MISSING",
        price_freshness="FRESH" if poly_prices else "MISSING",
        cross_source_validated=bool(ratings_data and standings_data),
        warnings=warnings[:5],  # Cap warnings
    )

    # ── Assemble ──
    return GameAnalysis(
        game_id=game_id,
        tipoff=tipoff,
        tipoff_sgt=tipoff_sgt,
        venue=venue,
        home=TeamGameData(
            team=home_abbr,
            full_name=NBA_TEAM_NAMES.get(home_abbr, home_abbr),
            record=home_standings.get("record", ""),
            seed=home_standings.get("seed"),
            motivation=home_motivation.motivation_flag,
            season_ortg=home_ratings["ortg"],
            season_drtg=home_ratings["drtg"],
            season_nrtg=home_ratings["nrtg"],
            adjusted_ortg=home_adj.adjusted_ortg,
            adjusted_drtg=home_adj.adjusted_drtg,
            adjusted_nrtg=home_adj.adjusted_nrtg,
            nrtg_delta=home_adj.nrtg_delta,
            injuries=home_injury_schemas,
            schedule=home_schedule,
        ),
        away=TeamGameData(
            team=away_abbr,
            full_name=NBA_TEAM_NAMES.get(away_abbr, away_abbr),
            record=away_standings.get("record", ""),
            seed=away_standings.get("seed"),
            motivation=away_motivation.motivation_flag,
            season_ortg=away_ratings["ortg"],
            season_drtg=away_ratings["drtg"],
            season_nrtg=away_ratings["nrtg"],
            adjusted_ortg=away_adj.adjusted_ortg,
            adjusted_drtg=away_adj.adjusted_drtg,
            adjusted_nrtg=away_adj.adjusted_nrtg,
            nrtg_delta=away_adj.nrtg_delta,
            injuries=away_injury_schemas,
            schedule=away_schedule,
        ),
        model=prediction,
        markets=markets,
        data_quality=data_quality,
    )


# ─── Polymarket Price Matching ──────────────────────────────────────

def _find_polymarket_prices(
    away_abbr: str,
    home_abbr: str,
    game_date: date,
    all_markets: list[dict[str, Any]],
) -> dict[str, Any]:
    """
    Find Polymarket prices for a specific game.
    Slug convention: contains team abbreviations + date.
    Returns dict with moneyline_home_yes, spread_home_yes, spread_line, etc.
    """
    prices: dict[str, Any] = {}
    away_lower = away_abbr.lower()
    home_lower = home_abbr.lower()
    date_str = game_date.strftime("%Y-%m-%d")

    # Also search with team city names for fuzzy matching
    away_names = _team_search_terms(away_abbr)
    home_names = _team_search_terms(home_abbr)

    for market in all_markets:
        slug = (market.get("slug") or "").lower()
        question = (market.get("question") or "").lower()
        search_text = f"{slug} {question}"

        # Match: slug or question must contain both teams
        has_away = any(t in search_text for t in away_names)
        has_home = any(t in search_text for t in home_names)
        has_date = date_str in search_text

        if not (has_away and has_home):
            continue

        # Parse prices
        parsed = PolymarketConnector.parse_market_prices(market)
        if not parsed:
            continue

        # Determine market type from slug/question
        slug_q = f"{slug} {question}"
        if any(kw in slug_q for kw in ["spread", "cover", "point"]):
            # Spread market
            home_outcome = _find_outcome_for_team(parsed, home_abbr, home_names)
            if home_outcome is not None:
                prices["spread_home_yes"] = home_outcome
                # Try to extract spread line from question
                line = _extract_line_from_text(question)
                if line is not None:
                    prices["spread_line"] = line
        elif any(kw in slug_q for kw in ["over", "under", "total", "points"]):
            # Total market
            over_price = parsed.get("Over") or parsed.get("Yes")
            if over_price is not None:
                prices["total_over_yes"] = float(over_price)
            line = _extract_line_from_text(question)
            if line is not None:
                prices["total_line"] = line
        else:
            # Default: moneyline
            home_outcome = _find_outcome_for_team(parsed, home_abbr, home_names)
            if home_outcome is not None:
                prices["moneyline_home_yes"] = home_outcome

    if prices:
        logger.info(f"Found Polymarket prices for {away_abbr}@{home_abbr}: {prices}")
    else:
        logger.warning(f"No Polymarket markets found for {away_abbr}@{home_abbr} on {date_str}")

    return prices


def _team_search_terms(abbr: str) -> list[str]:
    """Get lowercase search terms for a team."""
    full_name = NBA_TEAM_NAMES.get(abbr, "")
    terms = [abbr.lower()]
    if full_name:
        parts = full_name.lower().split()
        terms.extend(parts)  # e.g. ["los", "angeles", "lakers"]
        if len(parts) >= 2:
            terms.append(parts[-1])  # team nickname: "lakers"
    return terms


def _find_outcome_for_team(
    parsed_prices: dict[str, float],
    team_abbr: str,
    team_names: list[str],
) -> float | None:
    """Find the price for a team in parsed market outcomes."""
    for outcome, price in parsed_prices.items():
        outcome_lower = outcome.lower()
        if any(t in outcome_lower for t in team_names):
            return float(price)
    # Check for Yes/No format
    if "Yes" in parsed_prices:
        return float(parsed_prices["Yes"])
    return None


def _extract_line_from_text(text: str) -> float | None:
    """Extract a numeric line from text like 'cover -6.5' or 'over 224.5'."""
    import re
    # Match patterns like -6.5, +8.5, 224.5
    matches = re.findall(r'[+-]?\d+\.5', text)
    if matches:
        return float(matches[-1])
    # Also try whole numbers
    matches = re.findall(r'[+-]?\d{2,3}(?:\.\d)?', text)
    if matches:
        return float(matches[-1])
    return None


# ─── Helper Functions ───────────────────────────────────────────────

def _build_player_absences(injuries_raw: list[dict[str, Any]]) -> list[PlayerAbsence]:
    """Convert raw injury data to PlayerAbsence objects with estimated impacts."""
    absences: list[PlayerAbsence] = []
    for inj in injuries_raw:
        status = inj.get("status", "OUT").upper()
        # Only count OUT and DOUBTFUL as likely missing
        if status not in ("OUT", "DOUBTFUL"):
            continue

        # Estimate impact based on status (will be refined with PBP on/off data)
        # Default: assume medium-impact player
        absences.append(PlayerAbsence(
            player_id=inj.get("player_id", "unknown"),
            name=inj.get("player_name", "Unknown"),
            status=status,
            reason=inj.get("reason"),
            ortg_impact=-1.5,   # Default: team loses 1.5 ORtg per missing player
            drtg_impact=1.0,    # Default: team loses 1.0 DRtg per missing player
            nrtg_impact=-2.5,   # Net impact
            minutes_share=0.25,  # Assume ~25% minutes share
        ))
    return absences


def _rate_impact(inj: dict[str, Any]) -> str:
    """Rate injury impact as HIGH/MEDIUM/LOW based on available info."""
    status = inj.get("status", "").upper()
    if status in ("OUT", "DOUBTFUL"):
        return "HIGH"
    elif status in ("QUESTIONABLE", "GTD"):
        return "MEDIUM"
    return "LOW"


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


# ─── Cache Management (for API use) ────────────────────────────────

def clear_pipeline_cache() -> None:
    """Clear all cached pipeline data. Call on manual refresh."""
    _cache.clear()
    logger.info("Pipeline cache cleared")
