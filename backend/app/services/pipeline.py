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

import re

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

TRICODE_TO_ABBR: dict[str, str] = {
    "ATL": "ATL", "BOS": "BOS", "BKN": "BKN", "CHA": "CHA", "CHI": "CHI",
    "CLE": "CLE", "DAL": "DAL", "DEN": "DEN", "DET": "DET", "GSW": "GSW",
    "HOU": "HOU", "IND": "IND", "LAC": "LAC", "LAL": "LAL", "MEM": "MEM",
    "MIA": "MIA", "MIL": "MIL", "MIN": "MIN", "NOP": "NOP", "NYK": "NYK",
    "OKC": "OKC", "ORL": "ORL", "PHI": "PHI", "PHX": "PHX", "POR": "POR",
    "SAC": "SAC", "SAS": "SAS", "TOR": "TOR", "UTA": "UTA", "WAS": "WAS",
}

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

async def run_daily_pipeline(
    game_date: date | None = None,
    injury_overrides: dict[str, str] | None = None,
) -> DailyAnalysis:
    if game_date is None:
        game_date = date.today()

    cache_key = f"daily_{game_date.isoformat()}"
    # Skip cache if user passed injury overrides (custom scenario)
    if not injury_overrides:
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
        result = DailyAnalysis(date=game_date, games_count=0, games=[], top_edges=[])
        _cache.set(cache_key, result)
        return result

    logger.info(f"Found {len(games_raw)} games for {game_date}")

    # Step 2: Fetch supporting data
    # Phase 2a: Standings first (needed as fallback for ratings)
    standings_data = await _fetch_standings(warnings)

    # Phase 2b: Ratings + injuries + Polymarket + player metrics in parallel
    ratings_task = _fetch_team_ratings(warnings, standings_fallback=standings_data)
    injuries_task = _fetch_injuries(warnings)
    polymarket_task = _fetch_all_polymarket_events(games_raw, game_date, warnings)
    player_metrics_task = _fetch_player_metrics(warnings)

    ratings_data, injuries_data, polymarket_events, player_metrics = await asyncio.gather(
        ratings_task, injuries_task, polymarket_task, player_metrics_task
    )

    # Step 3: Process each game
    game_analyses: list[GameAnalysis] = []
    for game_raw in games_raw:
        try:
            away_abbr = game_raw["away_team"]
            home_abbr = game_raw["home_team"]
            event_key = f"{away_abbr}@{home_abbr}"
            game_event = polymarket_events.get(event_key)

            analysis = await _process_single_game(
                game_raw=game_raw,
                game_date=game_date,
                ratings_data=ratings_data,
                standings_data=standings_data,
                injuries_data=injuries_data,
                player_metrics=player_metrics,
                polymarket_event=game_event,
                warnings=warnings,
                injury_overrides=injury_overrides,
            )
            game_analyses.append(analysis)
        except Exception as e:
            logger.error(f"Failed to process game {game_raw.get('game_id', '?')}: {e}")
            warnings.append(f"Failed to process game: {e}")

    # Step 4: Extract top edges
    top_edges = _extract_top_edges(game_analyses)

    result = DailyAnalysis(
        date=game_date,
        games_count=len(game_analyses),
        games=game_analyses,
        top_edges=top_edges,
    )
    if not injury_overrides:
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
    team = game_data.get(team_key, {})
    if isinstance(team, dict):
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
    standings_fallback: dict[str, dict[str, Any]] | None = None,
) -> dict[str, dict[str, float]]:
    cached = _cache.get("team_ratings", ttl_seconds=3600)
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
            ortg = row.get("OFF_RATING") or row.get("E_OFF_RATING")
            drtg = row.get("DEF_RATING") or row.get("E_DEF_RATING")
            nrtg = row.get("NET_RATING") or row.get("E_NET_RATING")
            pace = row.get("PACE") or row.get("E_PACE")

            if ortg is None:
                pts = float(row.get("PTS", 110))
                ortg = pts
                drtg = float(row.get("OPP_PTS", 110)) if "OPP_PTS" in row else 110.0
                nrtg = ortg - drtg

            result[abbr] = {
                "ortg": float(ortg or 112),
                "drtg": float(drtg or 110),
                "nrtg": float(nrtg or 2),
                "pace": float(pace or 100),
            }
        if result:
            logger.info(f"✅ Fetched ratings for {len(result)} teams from NBA API")
            _cache.set("team_ratings", result)
        else:
            logger.warning("NBA API returned 0 team ratings rows")
    except Exception as e:
        logger.error(f"Failed to fetch team ratings from NBA API: {e}")
        warnings.append(f"Team ratings API unavailable: {e}")
    finally:
        await nba.close()

    # Fallback: estimate from standings
    if not result and standings_fallback:
        result = _estimate_ratings_from_standings(standings_fallback)
        if result:
            logger.info(f"⚠️ Using estimated ratings from standings for {len(result)} teams")
            warnings.append("Team ratings estimated from standings (NBA API returned HTTP 500).")
            _cache.set("team_ratings", result)
    elif not result:
        logger.error("❌ No team ratings available from any source.")
        warnings.append("No team ratings data available from any source")

    return result


def _estimate_ratings_from_standings(
    standings: dict[str, dict[str, Any]],
) -> dict[str, dict[str, float]]:
    LEAGUE_AVG_ORTG = 112.0
    NRTG_COEFFICIENT = 28.0

    result: dict[str, dict[str, float]] = {}
    for abbr, data in standings.items():
        wins = data.get("wins", 0)
        losses = data.get("losses", 0)
        total_games = wins + losses
        win_pct = wins / total_games if total_games > 0 else 0.5

        nrtg = (win_pct - 0.5) * NRTG_COEFFICIENT
        ortg = LEAGUE_AVG_ORTG + nrtg / 2.0
        drtg = LEAGUE_AVG_ORTG - nrtg / 2.0

        result[abbr] = {
            "ortg": round(ortg, 1),
            "drtg": round(drtg, 1),
            "nrtg": round(nrtg, 1),
            "pace": 100.0,
        }
    return result


async def _fetch_standings(warnings: list[str]) -> dict[str, dict[str, Any]]:
    cached = _cache.get("standings", ttl_seconds=3600)
    if cached:
        return cached

    nba = NBAApiConnector()
    result: dict[str, dict[str, Any]] = {}
    try:
        raw = await nba.get_standings()
        for row in raw:
            team_id = row.get("TeamID")
            abbr = NBA_TEAM_ID_TO_ABBR.get(team_id)
            if not abbr:
                continue
            wins = int(row.get("WINS", row.get("W", 0)))
            losses = int(row.get("LOSSES", row.get("L", 0)))
            seed = int(row.get("PlayoffRank", row.get("SEED", row.get("ConferenceRank", 15))))
            clinch = row.get("ClinchIndicator", row.get("ClinchedPlayoffs", ""))

            clinch_status = "NONE"
            if clinch:
                cl = str(clinch).lower()
                if "1" in cl or "z" in cl:
                    clinch_status = "CLINCHED_1_SEED"
                elif "x" in cl or "playoff" in cl:
                    clinch_status = "CLINCHED_PLAYOFF"
                elif "e" in cl or "elim" in cl:
                    clinch_status = "ELIMINATED"

            result[abbr] = {
                "wins": wins, "losses": losses, "record": f"{wins}-{losses}",
                "seed": seed, "clinch_status": clinch_status,
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


async def _fetch_injuries(warnings: list[str]) -> dict[str, list[dict[str, Any]]]:
    cached = _cache.get("injuries", ttl_seconds=600)
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


async def _fetch_all_polymarket_events(
    games_raw: list[dict[str, Any]],
    game_date: date,
    warnings: list[str],
) -> dict[str, dict[str, Any] | None]:
    poly = PolymarketConnector()
    try:
        game_tuples = [(g["away_team"], g["home_team"]) for g in games_raw]
        events = await poly.get_games_for_date(game_tuples, game_date)
        found = sum(1 for v in events.values() if v is not None)
        logger.info(f"Polymarket: fetched {found}/{len(game_tuples)} game events")

        for key, event in events.items():
            away, home = key.split("@")
            cache_key = f"poly_event_{away}_{home}_{game_date.isoformat()}"
            _cache.set(cache_key, event or {})

        return events
    except Exception as e:
        logger.error(f"Failed to fetch Polymarket events: {e}")
        warnings.append(f"Polymarket batch fetch failed: {e}")
        return {}
    finally:
        await poly.close()


async def _fetch_player_metrics(
    warnings: list[str],
) -> dict[str, dict[str, Any]]:
    """Fetch per-player estimated metrics → {player_name: stats_dict}.

    Used to calculate real injury impact (E_NET_RATING × minutes_share).
    Cached for 1 hour since these don't change during a game day.
    """
    cached = _cache.get("player_metrics", ttl_seconds=3600)
    if cached:
        return cached

    nba = NBAApiConnector()
    result: dict[str, dict[str, Any]] = {}
    try:
        raw = await nba.get_player_estimated_metrics()
        for row in raw:
            name = row.get("PLAYER_NAME", "")
            if name:
                result[name] = row
        if result:
            logger.info(f"✅ Fetched estimated metrics for {len(result)} players")
            _cache.set("player_metrics", result)
        else:
            logger.warning("playerestimatedmetrics returned 0 rows")
    except Exception as e:
        logger.error(f"Failed to fetch player metrics: {e}")
        warnings.append(f"Player metrics unavailable: {e}")
    finally:
        await nba.close()
    return result


# ─── Step 3: Process Single Game ───────────────────────────────────

async def _process_single_game(
    game_raw: dict[str, Any],
    game_date: date,
    ratings_data: dict[str, dict[str, float]],
    standings_data: dict[str, dict[str, Any]],
    injuries_data: dict[str, list[dict[str, Any]]],
    player_metrics: dict[str, dict[str, Any]],
    polymarket_event: dict[str, Any] | None,
    warnings: list[str],
    injury_overrides: dict[str, str] | None = None,
) -> GameAnalysis:
    home_abbr = game_raw["home_team"]
    away_abbr = game_raw["away_team"]
    game_id = game_raw["game_id"]
    tipoff: datetime | None = game_raw.get("tipoff")
    venue = game_raw.get("venue", "")

    logger.info(f"Processing {away_abbr} @ {home_abbr}")

    # Team ratings
    home_ratings = ratings_data.get(home_abbr, {"ortg": 112.0, "drtg": 110.0, "nrtg": 2.0, "pace": 100.0})
    away_ratings = ratings_data.get(away_abbr, {"ortg": 112.0, "drtg": 110.0, "nrtg": 2.0, "pace": 100.0})

    # Standings
    home_standings = standings_data.get(home_abbr, {"record": "0-0", "seed": 15, "clinch_status": "NONE", "wins": 0, "losses": 0})
    away_standings = standings_data.get(away_abbr, {"record": "0-0", "seed": 15, "clinch_status": "NONE", "wins": 0, "losses": 0})

    # Injuries
    home_injuries_raw = injuries_data.get(home_abbr, [])
    away_injuries_raw = injuries_data.get(away_abbr, [])

    # Player absences with real per-player impact from NBA stats
    home_absences = _build_player_absences(home_injuries_raw, player_metrics, injury_overrides)
    away_absences = _build_player_absences(away_injuries_raw, player_metrics, injury_overrides)

    # Lineup-adjusted ratings
    home_adj = _lineup_model.calculate_adjusted_ratings(
        team_id=home_abbr, season_ortg=home_ratings["ortg"],
        season_drtg=home_ratings["drtg"], missing_players=home_absences,
    )
    away_adj = _lineup_model.calculate_adjusted_ratings(
        team_id=away_abbr, season_ortg=away_ratings["ortg"],
        season_drtg=away_ratings["drtg"], missing_players=away_absences,
    )

    # Schedule context
    home_schedule = ScheduleContext(home_court=True)
    away_schedule = ScheduleContext(home_court=False)

    home_sched_mod = calculate_schedule_modifier(
        is_b2b=home_schedule.is_b2b, rest_days=home_schedule.rest_days,
        road_trip_game=home_schedule.road_trip_game,
    )
    away_sched_mod = calculate_schedule_modifier(
        is_b2b=away_schedule.is_b2b, rest_days=away_schedule.rest_days,
        road_trip_game=away_schedule.road_trip_game,
    )

    # Motivation
    games_remaining = 82 - (home_standings.get("wins", 0) + home_standings.get("losses", 0))
    home_motivation = determine_motivation(
        team=home_abbr, record=home_standings.get("record", "0-0"),
        conference_seed=home_standings.get("seed", 15),
        clinch_status=home_standings.get("clinch_status", "NONE"),
        games_remaining=max(0, games_remaining),
    )
    away_games_remaining = 82 - (away_standings.get("wins", 0) + away_standings.get("losses", 0))
    away_motivation = determine_motivation(
        team=away_abbr, record=away_standings.get("record", "0-0"),
        conference_seed=away_standings.get("seed", 15),
        clinch_status=away_standings.get("clinch_status", "NONE"),
        games_remaining=max(0, away_games_remaining),
    )

    # Polymarket prices
    poly_prices = _find_polymarket_prices(away_abbr, home_abbr, game_date, polymarket_event)

    # Prediction model
    prediction = predict_game(
        home_adj_nrtg=home_adj.adjusted_nrtg, away_adj_nrtg=away_adj.adjusted_nrtg,
        home_adj_ortg=home_adj.adjusted_ortg, home_adj_drtg=home_adj.adjusted_drtg,
        away_adj_ortg=away_adj.adjusted_ortg, away_adj_drtg=away_adj.adjusted_drtg,
        home_schedule_mod=home_sched_mod, away_schedule_mod=away_sched_mod,
        spread_line=poly_prices.get("spread_line"),
        total_line=poly_prices.get("total_line"),
    )

    # Team nicknames for labels
    home_nick = _get_team_nickname(home_abbr).title()  # "Nuggets"
    away_nick = _get_team_nickname(away_abbr).title()  # "Grizzlies"

    # Edge calculation with real team names
    markets: dict[str, MarketEdge] = {}

    ml_price = poly_prices.get("moneyline_home_yes")
    if ml_price is not None:
        ml_edge = calculate_edge(prediction.home_win_prob, ml_price)
        # Replace YES/NO with team names in the edge result
        ml_edge_named = EdgeResult(
            yes_edge=ml_edge.yes_edge, no_edge=ml_edge.no_edge,
            yes_ev=ml_edge.yes_ev, no_ev=ml_edge.no_ev,
            best_side=home_nick if ml_edge.best_side == "YES" else away_nick,
            best_edge=ml_edge.best_edge, verdict=ml_edge.verdict,
            kelly_fraction=ml_edge.kelly_fraction,
            suggested_bet_pct=ml_edge.suggested_bet_pct,
        )
        markets["moneyline"] = MarketEdge(
            market_type="moneyline",
            polymarket_home_yes=ml_price,
            polymarket_home_no=round(1.0 - ml_price, 3),
            home_label=home_nick,
            away_label=away_nick,
            model_probability=prediction.home_win_prob,
            edge=ml_edge_named,
        )

    spread_price = poly_prices.get("spread_home_yes")
    if spread_price is not None:
        spread_cover_prob = prediction.home_win_prob
        spread_edge = calculate_edge(spread_cover_prob, spread_price)
        spread_edge_named = EdgeResult(
            yes_edge=spread_edge.yes_edge, no_edge=spread_edge.no_edge,
            yes_ev=spread_edge.yes_ev, no_ev=spread_edge.no_ev,
            best_side=home_nick if spread_edge.best_side == "YES" else away_nick,
            best_edge=spread_edge.best_edge, verdict=spread_edge.verdict,
            kelly_fraction=spread_edge.kelly_fraction,
            suggested_bet_pct=spread_edge.suggested_bet_pct,
        )
        markets["spread"] = MarketEdge(
            market_type="spread",
            line=poly_prices.get("spread_line"),
            polymarket_home_yes=spread_price,
            polymarket_home_no=round(1.0 - spread_price, 3),
            home_label=home_nick,
            away_label=away_nick,
            model_probability=spread_cover_prob,
            edge=spread_edge_named,
        )

    total_price = poly_prices.get("total_over_yes")
    if total_price is not None:
        over_prob = 0.5
        total_edge = calculate_edge(over_prob, total_price)
        total_edge_named = EdgeResult(
            yes_edge=total_edge.yes_edge, no_edge=total_edge.no_edge,
            yes_ev=total_edge.yes_ev, no_ev=total_edge.no_ev,
            best_side="Over" if total_edge.best_side == "YES" else "Under",
            best_edge=total_edge.best_edge, verdict=total_edge.verdict,
            kelly_fraction=total_edge.kelly_fraction,
            suggested_bet_pct=total_edge.suggested_bet_pct,
        )
        markets["total"] = MarketEdge(
            market_type="total",
            line=poly_prices.get("total_line"),
            polymarket_home_yes=total_price,
            polymarket_home_no=round(1.0 - total_price, 3),
            home_label="Over",
            away_label="Under",
            model_probability=over_prob,
            edge=total_edge_named,
        )

    # Injury schemas
    home_injury_schemas = [
        InjurySchema(
            player_name=inj.get("player_name", "Unknown"), player_id=inj.get("player_id", ""),
            team=home_abbr, status=inj.get("status", "OUT"), reason=inj.get("reason"),
            source=inj.get("source", "NBA"), impact_rating=_rate_impact(inj),
        )
        for inj in home_injuries_raw
    ]
    away_injury_schemas = [
        InjurySchema(
            player_name=inj.get("player_name", "Unknown"), player_id=inj.get("player_id", ""),
            team=away_abbr, status=inj.get("status", "OUT"), reason=inj.get("reason"),
            source=inj.get("source", "NBA"), impact_rating=_rate_impact(inj),
        )
        for inj in away_injuries_raw
    ]

    # Tipoff SGT
    tipoff_sgt = tipoff + timedelta(hours=8) if tipoff else None

    # Data quality
    data_quality = DataQuality(
        ratings_freshness="FRESH" if ratings_data else "MISSING",
        injury_freshness="FRESH" if injuries_data else "MISSING",
        price_freshness="FRESH" if poly_prices else "MISSING",
        cross_source_validated=bool(ratings_data and standings_data),
        warnings=warnings[:5],
    )

    return GameAnalysis(
        game_id=game_id, tipoff=tipoff, tipoff_sgt=tipoff_sgt, venue=venue,
        home=TeamGameData(
            team=home_abbr, full_name=NBA_TEAM_NAMES.get(home_abbr, home_abbr),
            record=home_standings.get("record", ""), seed=home_standings.get("seed"),
            motivation=home_motivation.motivation_flag,
            season_ortg=home_ratings["ortg"], season_drtg=home_ratings["drtg"],
            season_nrtg=home_ratings["nrtg"],
            adjusted_ortg=home_adj.adjusted_ortg, adjusted_drtg=home_adj.adjusted_drtg,
            adjusted_nrtg=home_adj.adjusted_nrtg, nrtg_delta=home_adj.nrtg_delta,
            injuries=home_injury_schemas, schedule=home_schedule,
        ),
        away=TeamGameData(
            team=away_abbr, full_name=NBA_TEAM_NAMES.get(away_abbr, away_abbr),
            record=away_standings.get("record", ""), seed=away_standings.get("seed"),
            motivation=away_motivation.motivation_flag,
            season_ortg=away_ratings["ortg"], season_drtg=away_ratings["drtg"],
            season_nrtg=away_ratings["nrtg"],
            adjusted_ortg=away_adj.adjusted_ortg, adjusted_drtg=away_adj.adjusted_drtg,
            adjusted_nrtg=away_adj.adjusted_nrtg, nrtg_delta=away_adj.nrtg_delta,
            injuries=away_injury_schemas, schedule=away_schedule,
        ),
        model=prediction, markets=markets, data_quality=data_quality,
    )


# ─── Polymarket Price Matching ──────────────────────────────────────

def _get_team_nickname(abbr: str) -> str:
    """Return team nickname in lowercase. e.g. 'DEN' → 'nuggets'."""
    full = NBA_TEAM_NAMES.get(abbr, "")
    if full:
        return full.split()[-1].lower()
    return abbr.lower()


def _find_polymarket_prices(
    away_abbr: str,
    home_abbr: str,
    game_date: date,
    event: dict[str, Any] | None,
) -> dict[str, Any]:
    """Parse Polymarket event into moneyline / spread / total prices."""
    prices: dict[str, Any] = {}

    if not event or not isinstance(event, dict):
        logger.warning(f"No Polymarket event for {away_abbr}@{home_abbr}")
        return prices

    markets = event.get("markets") or []
    if not markets:
        logger.warning(f"Polymarket event has 0 markets for {away_abbr}@{home_abbr}")
        return prices

    home_nick = _get_team_nickname(home_abbr)
    away_nick = _get_team_nickname(away_abbr)

    moneyline_market = None
    spread_candidates: list[dict[str, Any]] = []
    total_candidates: list[dict[str, Any]] = []

    for mkt in markets:
        question = (mkt.get("question") or "").strip()
        q_lower = question.lower()

        # Skip first-half (1H), quarter (1Q/2Q), and player prop markets
        is_partial = any(tag in q_lower for tag in ["1h ", "2h ", "1q ", "2q ", "3q ", "4q ", "1h:", "2h:"])

        if "spread" in q_lower:
            if not is_partial:
                spread_candidates.append(mkt)
        elif "o/u" in q_lower or "over/under" in q_lower:
            # Only full-game totals, not player props or half totals
            has_both_teams = home_nick in q_lower and away_nick in q_lower
            has_vs = "vs." in q_lower or "vs " in q_lower
            if (has_both_teams or has_vs) and not is_partial:
                total_candidates.append(mkt)
        elif "vs." in q_lower or "vs " in q_lower:
            if "spread" not in q_lower and "o/u" not in q_lower and not is_partial:
                moneyline_market = mkt
        elif home_nick in q_lower and away_nick in q_lower:
            if "spread" not in q_lower and "o/u" not in q_lower and not is_partial:
                moneyline_market = mkt

    # ── Moneyline ──
    if moneyline_market:
        parsed = PolymarketConnector.parse_market_prices(moneyline_market)
        home_price = _match_outcome_price(parsed, home_nick)
        away_price = _match_outcome_price(parsed, away_nick)
        if home_price is not None:
            prices["moneyline_home_yes"] = home_price
            prices["moneyline_home_no"] = round(1.0 - home_price, 4)
            logger.debug(f"  ML: {home_abbr}=${home_price:.3f}, {away_abbr}=${away_price or '?'}")

    # ── Spread ──
    if spread_candidates:
        best_spread = _pick_best_spread(spread_candidates)
        if best_spread:
            parsed = PolymarketConnector.parse_market_prices(best_spread)
            question = best_spread.get("question", "")
            line = _extract_spread_line(question)
            home_price = _match_outcome_price(parsed, home_nick)
            if home_price is not None:
                prices["spread_home_yes"] = home_price
                if line is not None:
                    prices["spread_line"] = _orient_spread_line(question, line, home_nick)
                logger.debug(f"  Spread: {question} → home=${home_price:.3f}, line={prices.get('spread_line')}")

    # ── Total (Over/Under) — game totals only ──
    if total_candidates:
        best_total = _pick_best_total(total_candidates)
        if best_total:
            parsed = PolymarketConnector.parse_market_prices(best_total)
            question = best_total.get("question", "")
            line = _extract_total_line(question)
            over_price = parsed.get("Over")
            if over_price is not None:
                prices["total_over_yes"] = float(over_price)
                prices["total_under_yes"] = round(1.0 - float(over_price), 4)
            if line is not None:
                prices["total_line"] = line
            logger.debug(f"  Total: {question} → over=${prices.get('total_over_yes')}, line={prices.get('total_line')}")

    if prices:
        logger.info(f"Polymarket prices for {away_abbr}@{home_abbr}: {prices}")
    else:
        logger.warning(f"No Polymarket markets matched for {away_abbr}@{home_abbr} (event had {len(markets)} markets)")

    return prices


def _match_outcome_price(parsed: dict[str, float], nickname: str) -> float | None:
    nick_lower = nickname.lower()
    for label, price in parsed.items():
        if nick_lower in label.lower():
            return float(price)
    return None


def _extract_spread_line(question: str) -> float | None:
    m = re.search(r'\(([+-]?\d+(?:\.\d+)?)\)', question)
    if m:
        return float(m.group(1))
    m = re.search(r'([+-]\d+(?:\.\d+)?)', question)
    if m:
        return float(m.group(1))
    return None


def _orient_spread_line(question: str, line: float, home_nick: str) -> float:
    """Orient spread line from home team's perspective."""
    q_lower = question.lower()
    paren_idx = q_lower.find("(")
    if paren_idx > 0:
        pre_paren = q_lower[:paren_idx].strip()
        if home_nick.lower() in pre_paren:
            return line
        else:
            return -line
    return line


def _extract_total_line(question: str) -> float | None:
    m = re.search(r'O/U\s+(\d+(?:\.\d+)?)', question, re.IGNORECASE)
    if m:
        return float(m.group(1))
    m = re.search(r'Over/Under\s+(\d+(?:\.\d+)?)', question, re.IGNORECASE)
    if m:
        return float(m.group(1))
    return None


def _pick_best_spread(candidates: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Pick the spread with the SMALLEST absolute line (main line, not alt)."""
    best: dict[str, Any] | None = None
    best_abs_line = float("inf")
    for mkt in candidates:
        q = mkt.get("question", "")
        line = _extract_spread_line(q)
        if line is not None:
            if abs(line) < best_abs_line:
                best_abs_line = abs(line)
                best = mkt
        elif best is None:
            best = mkt
    return best


def _pick_best_total(candidates: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Pick the first game total with a parseable O/U line."""
    for mkt in candidates:
        q = mkt.get("question", "")
        if _extract_total_line(q) is not None:
            return mkt
    return candidates[0] if candidates else None


# ─── Helper Functions ───────────────────────────────────────────────

def _build_player_absences(
    injuries_raw: list[dict[str, Any]],
    player_metrics: dict[str, dict[str, Any]] | None = None,
    injury_overrides: dict[str, str] | None = None,
) -> list[PlayerAbsence]:
    """Build player absence list with real per-player impact from NBA stats.

    Three-state override for QUESTIONABLE players (user-controlled via frontend):
      "FULL" = 100% miss weight (user knows they are sitting)
      "HALF" = 50% miss weight (uncertain, default for QUESTIONABLE)
      "OFF"  = 0%, excluded, user thinks they will play

    Key fixes:
      - Players under 10 min/game are filtered (too noisy from small samples)
      - ORtg/DRtg impacts derived symmetrically from NRtg so losing a star
        always makes the team WORSE (no paradoxical NRtg-goes-up scenarios)
      - Results sorted by |impact| descending so diminishing returns is fair
    """
    MIN_MINUTES_THRESHOLD = 10.0  # Ignore < 10 min/game (sample size noise)

    DEFAULT_MISS: dict[str, float] = {
        "OUT": 1.0,
        "DOUBTFUL": 0.75,
        "QUESTIONABLE": 0.50,
    }

    overrides = injury_overrides or {}
    absences: list[PlayerAbsence] = []
    pm = player_metrics or {}

    for inj in injuries_raw:
        status = inj.get("status", "OUT").upper()
        player_name = inj.get("player_name", "Unknown")

        # Determine miss probability
        if player_name in overrides:
            mode = overrides[player_name].upper()
            if mode == "FULL":
                miss_prob = 1.0
            elif mode == "HALF":
                miss_prob = 0.5
            else:  # OFF
                miss_prob = 0.0
        else:
            miss_prob = DEFAULT_MISS.get(status, 0.0)

        if miss_prob <= 0:
            continue  # PROBABLE or overridden OFF

        # Look up real stats
        stats = pm.get(player_name)

        if stats:
            minutes = float(stats.get("MIN", 0) or 0)
            e_net = float(stats.get("E_NET_RATING", 0) or 0)

            # Filter out low-minute players: their E_NET is just noise
            # (e.g. Emanuel Miller 6.6 min with E_NET=-32 is meaningless)
            if minutes < MIN_MINUTES_THRESHOLD:
                logger.debug(
                    f"  Skipping {player_name} ({status}) -- "
                    f"only {minutes:.1f} min/game (noise)"
                )
                continue

            min_share = minutes / 48.0
            dampening = 0.6

            # Core impact: losing a +16 NRtg player hurts by ~6 NRtg
            nrtg_impact = -e_net * min_share * dampening * miss_prob

            # Split NRtg impact symmetrically into ORtg and DRtg.
            # This prevents paradoxes where NRtg goes UP when a star is out
            # (which happened when we used separate E_OFF/E_DEF because
            # defense could drop more than offense, making NRtg = ORtg-DRtg rise).
            # With symmetric split: losing a good player always hurts NRtg.
            ortg_impact = nrtg_impact / 2.0    # team offense worse (negative)
            drtg_impact = -nrtg_impact / 2.0   # team defense worse (positive = higher DRtg)

            logger.debug(
                f"  Injury impact: {player_name} ({status}, {miss_prob:.0%} miss) -- "
                f"E_NET={e_net:+.1f}, MIN={minutes:.1f}, "
                f"NRtg impact={nrtg_impact:+.2f}"
            )
        else:
            min_share = 0.15
            ortg_impact = -0.5 * miss_prob
            drtg_impact = 0.3 * miss_prob
            nrtg_impact = -0.8 * miss_prob
            logger.debug(
                f"  Injury impact: {player_name} ({status}, {miss_prob:.0%} miss) -- "
                f"no stats, using default"
            )

        absences.append(PlayerAbsence(
            player_id=inj.get("player_id", "unknown"),
            name=player_name,
            status=status,
            reason=inj.get("reason"),
            ortg_impact=round(ortg_impact, 2),
            drtg_impact=round(drtg_impact, 2),
            nrtg_impact=round(nrtg_impact, 2),
            minutes_share=round(min_share, 3),
        ))

    # Sort by absolute impact descending so the biggest star gets
    # diminishing_returns factor=1.0 in the lineup model (not random ESPN order)
    absences.sort(key=lambda a: abs(a.nrtg_impact), reverse=True)
    return absences


def _rate_impact(inj: dict[str, Any]) -> str:
    status = inj.get("status", "").upper()
    if status in ("OUT", "DOUBTFUL"):
        return "HIGH"
    elif status in ("QUESTIONABLE", "GTD"):
        return "MEDIUM"
    return "LOW"


def _extract_top_edges(games: list[GameAnalysis]) -> list[TopEdge]:
    edges: list[TopEdge] = []
    for game in games:
        game_label = f"{game.away.team} @ {game.home.team}"
        home_nick = _get_team_nickname(game.home.team).title()
        away_nick = _get_team_nickname(game.away.team).title()

        for market_type, market in game.markets.items():
            if market.edge.verdict in ("STRONG BUY", "BUY"):
                # Use real team names for selection
                if market_type == "total":
                    selection = f"{market.edge.best_side} {market.line}" if market.line else market.edge.best_side
                elif market.edge.best_side == home_nick:
                    selection = f"{game.home.team} {market_type}"
                else:
                    selection = f"{game.away.team} {market_type}"

                # Price for the recommended side
                if market.edge.best_side in (home_nick, "Over"):
                    price = market.polymarket_home_yes or 0
                else:
                    price = market.polymarket_home_no or 0

                edges.append(TopEdge(
                    game=game_label, market=market_type, selection=selection,
                    price=price, model_prob=market.model_probability,
                    edge=market.edge.best_edge, verdict=market.edge.verdict,
                ))
    edges.sort(key=lambda e: e.edge, reverse=True)
    return edges


# ─── Cache Management ───────────────────────────────────────────────

def clear_pipeline_cache() -> None:
    _cache.clear()
    logger.info("Pipeline cache cleared")
