"""
Background Scheduler — keeps injury and Polymarket data fresh.

Per PRD §7 Data Refresh Schedule:
- Injury reports: every 30 minutes on game days
- Polymarket prices: every 5 minutes
- Full pipeline (ratings + everything): every 5 minutes (piggybacks on pipeline TTL)

Uses APScheduler running inside the FastAPI process.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from loguru import logger

from app.config import settings

scheduler = AsyncIOScheduler()

# Track last refresh times for the status endpoint
_refresh_status: dict[str, datetime | None] = {
    "pipeline": None,
    "injuries": None,
    "polymarket": None,
}


def get_refresh_status() -> dict[str, str | None]:
    """Return last refresh timestamps for monitoring."""
    result: dict[str, str | None] = {}
    for key, ts in _refresh_status.items():
        result[key] = ts.isoformat() if ts else None
    return result


async def _refresh_pipeline() -> None:
    """Run the full daily pipeline — refreshes all data."""
    from app.services.pipeline import run_daily_pipeline

    try:
        logger.info("⏰ Scheduled pipeline refresh starting...")
        analysis = await run_daily_pipeline()
        _refresh_status["pipeline"] = datetime.now(timezone.utc)
        _refresh_status["injuries"] = datetime.now(timezone.utc)
        _refresh_status["polymarket"] = datetime.now(timezone.utc)
        logger.info(
            f"⏰ Scheduled refresh complete: {analysis.games_count} games, "
            f"{len(analysis.top_edges)} edges"
        )
    except Exception as e:
        logger.error(f"⏰ Scheduled pipeline refresh failed: {e}")


async def _refresh_prices_only() -> None:
    """Lightweight refresh — only clear Polymarket cache so next request re-fetches.
    
    The pipeline has a 300s TTL for the full analysis cache. By clearing just
    the cached result, the next API call will re-run the pipeline with fresh
    Polymarket prices while reusing cached ratings (3600s TTL).
    """
    from app.services.pipeline import _cache

    try:
        # Only clear the daily analysis cache, not the raw data cache.
        # This forces re-fetch of Polymarket prices on next request while
        # keeping expensive ratings data cached.
        keys_to_clear = [k for k in _cache._store if k.startswith("daily_")]
        for key in keys_to_clear:
            if key in _cache._store:
                del _cache._store[key]

        _refresh_status["polymarket"] = datetime.now(timezone.utc)
        logger.debug("⏰ Polymarket price cache invalidated")
    except Exception as e:
        logger.error(f"⏰ Polymarket cache invalidation failed: {e}")


def start_scheduler() -> None:
    """Start the background scheduler with configured intervals."""
    if scheduler.running:
        logger.warning("Scheduler already running, skipping start")
        return

    # Full pipeline refresh — every 5 minutes
    # This fetches fresh injuries + Polymarket + reuses cached ratings
    scheduler.add_job(
        _refresh_pipeline,
        trigger=IntervalTrigger(seconds=settings.polymarket_refresh_interval),
        id="pipeline_refresh",
        name="Full pipeline refresh (injuries + Polymarket + ratings)",
        replace_existing=True,
        max_instances=1,  # Don't stack if previous run is slow
    )

    # Polymarket price cache invalidation — every 2 minutes
    # Lightweight: just clears cache so next request gets fresh prices
    scheduler.add_job(
        _refresh_prices_only,
        trigger=IntervalTrigger(minutes=2),
        id="price_invalidation",
        name="Polymarket price cache invalidation",
        replace_existing=True,
        max_instances=1,
    )

    scheduler.start()
    logger.info(
        f"⏰ Scheduler started: pipeline every {settings.polymarket_refresh_interval}s, "
        f"price invalidation every 2min"
    )


def stop_scheduler() -> None:
    """Gracefully stop the scheduler."""
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("⏰ Scheduler stopped")
