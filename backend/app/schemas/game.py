"""Pydantic schemas for game analysis — the main API response model."""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel

from app.schemas.market import MarketEdge
from app.schemas.prediction import DataQuality, GamePrediction, LivePrediction
from app.schemas.team import AdjustedRatings, InjurySchema, ScheduleContext, StandingsInfo


# ─── Live Game State ────────────────────────────────────────────────

class LivePlayerStats(BaseModel):
    """Per-player live box score during a game."""
    name: str
    player_id: str = ""
    position: str = ""
    team: str = ""
    minutes: str = "0:00"
    points: int = 0
    rebounds: int = 0
    assists: int = 0
    steals: int = 0
    blocks: int = 0
    turnovers: int = 0
    fouls: int = 0
    plus_minus: int = 0
    fg_pct: float = 0.0
    three_pct: float = 0.0
    ft_pct: float = 0.0


class LiveGameState(BaseModel):
    """Real-time game state from NBA scoreboardv3 + boxscoretraditionalv3."""
    game_status: int = 1  # 1=SCHEDULED, 2=LIVE, 3=FINAL
    game_status_text: str = ""  # "7:30 pm ET", "Q3 5:47", "Final"
    period: int = 0  # 0=not started, 1-4=regulation, 5+=OT
    game_clock: str = ""  # "5:47" remaining in period, "" if not live
    home_score: int = 0
    away_score: int = 0
    nba_game_id: str = ""  # Real NBA 10-digit game ID for boxscore calls
    # Quarter scores: [{period: 1, score: 28}, ...]
    home_periods: list[dict] = []
    away_periods: list[dict] = []
    # Game leaders from scoreboardv3
    home_leader: dict = {}  # {name, points, rebounds, assists}
    away_leader: dict = {}
    # Live box score (only populated for LIVE games, from boxscoretraditionalv3)
    home_players: list[LivePlayerStats] = []
    away_players: list[LivePlayerStats] = []


# ─── Team + Game Analysis ──────────────────────────────────────────

class TeamGameData(BaseModel):
    """All data for one team in a game."""
    team: str
    full_name: str
    record: str = ""
    seed: int | None = None
    motivation: str = "NEUTRAL"
    season_ortg: float
    season_drtg: float
    season_nrtg: float
    adjusted_ortg: float
    adjusted_drtg: float
    adjusted_nrtg: float
    nrtg_delta: float
    injuries: list[InjurySchema] = []
    schedule: ScheduleContext = ScheduleContext()


class GameAnalysis(BaseModel):
    """Complete analysis for a single game — the core data object."""
    game_id: str
    tipoff: datetime | None = None
    tipoff_sgt: datetime | None = None
    venue: str = ""
    home: TeamGameData
    away: TeamGameData
    model: GamePrediction  # Pre-game prediction (always present)
    live: LiveGameState = LiveGameState()  # Live scores + status + box score
    live_prediction: LivePrediction | None = None  # Score-adjusted prediction (only when LIVE or FINAL)
    markets: dict[str, MarketEdge] = {}
    data_quality: DataQuality = DataQuality()


class TopEdge(BaseModel):
    """Summary of a top edge opportunity."""
    game: str
    game_id: str = ""
    market: str
    selection: str
    price: float
    model_prob: float
    edge: float
    verdict: str


class DailyAnalysis(BaseModel):
    """Full daily analysis — the response for /games/today."""
    date: date
    timezone_note: str = "All times in US Eastern. Operator is UTC+8."
    games_count: int = 0
    games: list[GameAnalysis] = []
    top_edges: list[TopEdge] = []
