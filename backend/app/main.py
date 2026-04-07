"""CourtEdge FastAPI application entry point."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from app.api.v1.router import api_v1_router
from app.config import settings


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan handler for startup/shutdown."""
    logger.info("Starting CourtEdge API...")
    logger.info(f"Environment: {settings.environment}")
    # TODO: Initialize scheduler, DB connections
    yield
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
async def health_check() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "healthy", "version": "0.1.0"}
