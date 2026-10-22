"""Application configuration using pydantic-settings."""

from datetime import date

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Database
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/courtedge"
    database_url_sync: str = "postgresql://postgres:postgres@localhost:5432/courtedge"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # Environment
    environment: str = "development"
    log_level: str = "DEBUG"

    # CORS
    cors_origins: str = "http://localhost:3000,http://localhost:3001"

    # API
    api_v1_prefix: str = "/api/v1"

    # Data refresh intervals (seconds)
    injury_refresh_interval: int = 1800  # 30 minutes
    polymarket_refresh_interval: int = 300  # 5 minutes
    ratings_refresh_interval: int = 86400  # 24 hours

    # Validation
    ortg_min: float = 90.0
    ortg_max: float = 130.0
    drtg_min: float = 90.0
    drtg_max: float = 130.0
    nrtg_min: float = -25.0
    nrtg_max: float = 25.0
    pace_min: float = 90.0
    pace_max: float = 110.0

    # Season handling
    # Pin a season (e.g. "2025-26") instead of deriving it from today's date.
    nba_season_override: str | None = None
    # Month (1-12) in which a new NBA season starts; Oct = preseason/opening night.
    season_rollover_month: int = 10
    # Early-season rating blend: weight on current season = gp / (gp + K).
    # Higher K leans on last season longer (K=15 → 50/50 at 15 games played).
    rating_blend_k: float = 15.0
    player_blend_k: float = 10.0
    # Motivation flags (FIGHTING/DESPERATE/...) are forced NEUTRAL until
    # a team has played this many games — early standings mean nothing.
    early_season_games: int = 20

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()


def season_for_date(d: date, rollover_month: int = 10) -> str:
    """NBA season string ("2026-27") that is in progress on date ``d``.

    Seasons start in October and end in June, so dates on/after the rollover
    month belong to the season starting that year; earlier dates belong to the
    season that started the previous year.
    """
    start_year = d.year if d.month >= rollover_month else d.year - 1
    return f"{start_year}-{(start_year + 1) % 100:02d}"


def previous_season(season: str) -> str:
    """The season before ``season`` ("2026-27" → "2025-26")."""
    start_year = int(season[:4]) - 1
    return f"{start_year}-{(start_year + 1) % 100:02d}"


def current_season(today: date | None = None) -> str:
    """Current NBA season string, honouring ``NBA_SEASON_OVERRIDE`` if set."""
    if settings.nba_season_override:
        return settings.nba_season_override
    return season_for_date(today or date.today(), settings.season_rollover_month)
