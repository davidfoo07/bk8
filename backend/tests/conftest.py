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
