"""Injury management API endpoints."""

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from loguru import logger
from pydantic import BaseModel

from app.schemas.team import InjurySchema

router = APIRouter(prefix="/injuries", tags=["Injuries"])

# In-memory override store
_manual_overrides: dict[str, InjurySchema] = {}


class InjuryOverrideRequest(BaseModel):
    """Request to manually override a player's injury status."""
    player_name: str
    player_id: str
    team: str
    status: str  # OUT, DOUBTFUL, QUESTIONABLE, PROBABLE, GTD, AVAILABLE
    reason: str = ""


@router.post("/override", response_model=InjurySchema)
async def override_injury(override: InjuryOverrideRequest) -> InjurySchema:
    """
    Manually set a player's injury status.
    Useful when official reports haven't updated yet but operator has info.
    """
    valid_statuses = {"OUT", "DOUBTFUL", "QUESTIONABLE", "PROBABLE", "GTD", "AVAILABLE"}
    if override.status.upper() not in valid_statuses:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid status. Must be one of: {', '.join(valid_statuses)}",
        )

    injury = InjurySchema(
        player_name=override.player_name,
        player_id=override.player_id,
        team=override.team,
        status=override.status.upper(),
        reason=override.reason or "Manual override",
        source="Manual Override",
        last_updated=datetime.now(timezone.utc),
        impact_rating="UNKNOWN",
    )

    _manual_overrides[override.player_id] = injury
    logger.info(
        f"Manual override: {override.player_name} ({override.team}) → {override.status}"
    )
    return injury


@router.get("/overrides", response_model=list[InjurySchema])
async def get_overrides() -> list[InjurySchema]:
    """Get all manual injury overrides."""
    return list(_manual_overrides.values())


@router.delete("/override/{player_id}")
async def delete_override(player_id: str) -> dict:
    """Remove a manual injury override."""
    if player_id in _manual_overrides:
        removed = _manual_overrides.pop(player_id)
        logger.info(f"Removed override for {removed.player_name}")
        return {"status": "removed", "player": removed.player_name}
    raise HTTPException(status_code=404, detail=f"No override for player {player_id}")
