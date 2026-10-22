"""Pytest configuration and shared fixtures."""

import pytest


@pytest.fixture
def sample_player_absence():
    """Sample player absence for testing."""
    from app.schemas.team import PlayerAbsence
    return PlayerAbsence(
        player_id="1630595",
        name="Cade Cunningham",
        status="OUT",
        reason="Knee - Injury Management",
        ortg_impact=-3.5,
        drtg_impact=1.2,
        nrtg_impact=-4.7,
        minutes_share=0.38,
    )


@pytest.fixture
def sample_player_absences():
    """Multiple player absences for multi-player testing."""
    from app.schemas.team import PlayerAbsence
    return [
        PlayerAbsence(
            player_id="1630595",
            name="Cade Cunningham",
            status="OUT",
            ortg_impact=-3.5,
            drtg_impact=1.2,
            nrtg_impact=-4.7,
            minutes_share=0.38,
        ),
        PlayerAbsence(
            player_id="203999",
            name="Jalen Duren",
            status="OUT",
            ortg_impact=-1.5,
            drtg_impact=0.8,
            nrtg_impact=-2.3,
            minutes_share=0.30,
        ),
    ]


@pytest.fixture(autouse=True)
def _reset_db_pool():
    """Drop pooled asyncpg connections after each test.

    The module-level TestClient runs every request on a fresh event loop, so a
    connection pooled by one request is bound to a loop that is already closed
    by the next one ("attached to a different loop").
    """
    yield
    from app.models.database import engine
    engine.sync_engine.dispose(close=False)
