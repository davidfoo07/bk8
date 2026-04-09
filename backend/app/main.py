"""CourtEdge FastAPI application entry point."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger
from sqlalchemy import text

from app.api.v1.router import api_v1_router
from app.config import settings
from app.models.database import engine
from app.services.scheduler import get_refresh_status, start_scheduler, stop_scheduler


async def _auto_migrate() -> None:
    """Ensure DB schema has all columns the ORM expects.

    Lightweight forward-only migration — only ADDs missing columns,
    never drops or renames. Safe to run on every startup.
    """
    migrations: list[str] = [
        # 2026-04-10: notes column for bets
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'bets' AND column_name = 'notes'
            ) THEN
                ALTER TABLE bets ADD COLUMN notes TEXT;
            END IF;
        END $$;
        """,
        # 2026-04-10: system_aligned flag for bet tracking
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'bets' AND column_name = 'system_aligned'
            ) THEN
                ALTER TABLE bets ADD COLUMN system_aligned BOOLEAN DEFAULT TRUE;
                UPDATE bets SET system_aligned = TRUE;
            END IF;
        END $$;
        """,
        # 2026-04-10: widen selection from VARCHAR(100) to VARCHAR(200)
        """
        ALTER TABLE bets ALTER COLUMN selection TYPE VARCHAR(200);
        """,
    ]
    async with engine.begin() as conn:
        for sql in migrations:
            try:
                await conn.execute(text(sql))
            except Exception as e:
                logger.warning(f"Auto-migrate statement skipped: {e}")
    logger.info("Auto-migration check complete")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan handler for startup/shutdown."""
    logger.info("Starting CourtEdge API...")
    logger.info(f"Environment: {settings.environment}")

    # Ensure DB schema is up to date
    await _auto_migrate()

    # Start background scheduler for auto data refresh
    start_scheduler()

    yield

    # Graceful shutdown
    stop_scheduler()
    logger.info("Shutting down CourtEdge API...")


app = FastAPI(
    title="CourtEdge API",
    description="Lineup-adjusted NBA analytics platform for Polymarket edge detection",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins.split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API v1 routes
app.include_router(api_v1_router, prefix=settings.api_v1_prefix)


@app.get("/health")
async def health_check() -> dict[str, str | None]:
    """Health check endpoint with scheduler status."""
    status = get_refresh_status()
    return {
        "status": "healthy",
        "version": "0.1.0",
        "last_pipeline_refresh": status.get("pipeline"),
        "last_price_refresh": status.get("polymarket"),
    }
