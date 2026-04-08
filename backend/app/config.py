"""Application configuration using pydantic-settings."""

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

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
