"""API v1 router — aggregates all v1 endpoint routers."""

from fastapi import APIRouter

from app.api.v1.bets import router as bets_router
from app.api.v1.games import router as games_router
from app.api.v1.injuries import router as injuries_router
from app.api.v1.results import router as results_router
from app.api.v1.simulation import router as simulation_router
from app.api.v1.teams import router as teams_router

api_v1_router = APIRouter()

api_v1_router.include_router(games_router)
api_v1_router.include_router(bets_router)
api_v1_router.include_router(teams_router)
api_v1_router.include_router(injuries_router)
api_v1_router.include_router(results_router)
api_v1_router.include_router(simulation_router)
