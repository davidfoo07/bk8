"""Team ratings API endpoints."""

from fastapi import APIRouter, HTTPException

from app.schemas.team import AdjustedRatings, TeamBase
from app.services.pipeline import _cache, _fetch_team_ratings

router = APIRouter(prefix="/teams", tags=["Teams"])

# NBA Teams reference data
NBA_TEAMS: dict[str, TeamBase] = {
    "ATL": TeamBase(id="ATL", full_name="Atlanta Hawks", conference="EAST", division="Southeast"),
    "BOS": TeamBase(id="BOS", full_name="Boston Celtics", conference="EAST", division="Atlantic"),
    "BKN": TeamBase(id="BKN", full_name="Brooklyn Nets", conference="EAST", division="Atlantic"),
    "CHA": TeamBase(id="CHA", full_name="Charlotte Hornets", conference="EAST", division="Southeast"),
    "CHI": TeamBase(id="CHI", full_name="Chicago Bulls", conference="EAST", division="Central"),
    "CLE": TeamBase(id="CLE", full_name="Cleveland Cavaliers", conference="EAST", division="Central"),
    "DAL": TeamBase(id="DAL", full_name="Dallas Mavericks", conference="WEST", division="Southwest"),
    "DEN": TeamBase(id="DEN", full_name="Denver Nuggets", conference="WEST", division="Northwest"),
    "DET": TeamBase(id="DET", full_name="Detroit Pistons", conference="EAST", division="Central"),
    "GSW": TeamBase(id="GSW", full_name="Golden State Warriors", conference="WEST", division="Pacific"),
    "HOU": TeamBase(id="HOU", full_name="Houston Rockets", conference="WEST", division="Southwest"),
    "IND": TeamBase(id="IND", full_name="Indiana Pacers", conference="EAST", division="Central"),
    "LAC": TeamBase(id="LAC", full_name="LA Clippers", conference="WEST", division="Pacific"),
    "LAL": TeamBase(id="LAL", full_name="Los Angeles Lakers", conference="WEST", division="Pacific"),
    "MEM": TeamBase(id="MEM", full_name="Memphis Grizzlies", conference="WEST", division="Southwest"),
    "MIA": TeamBase(id="MIA", full_name="Miami Heat", conference="EAST", division="Southeast"),
    "MIL": TeamBase(id="MIL", full_name="Milwaukee Bucks", conference="EAST", division="Central"),
    "MIN": TeamBase(id="MIN", full_name="Minnesota Timberwolves", conference="WEST", division="Northwest"),
    "NOP": TeamBase(id="NOP", full_name="New Orleans Pelicans", conference="WEST", division="Southwest"),
    "NYK": TeamBase(id="NYK", full_name="New York Knicks", conference="EAST", division="Atlantic"),
    "OKC": TeamBase(id="OKC", full_name="Oklahoma City Thunder", conference="WEST", division="Northwest"),
    "ORL": TeamBase(id="ORL", full_name="Orlando Magic", conference="EAST", division="Southeast"),
    "PHI": TeamBase(id="PHI", full_name="Philadelphia 76ers", conference="EAST", division="Atlantic"),
    "PHX": TeamBase(id="PHX", full_name="Phoenix Suns", conference="WEST", division="Pacific"),
    "POR": TeamBase(id="POR", full_name="Portland Trail Blazers", conference="WEST", division="Northwest"),
    "SAC": TeamBase(id="SAC", full_name="Sacramento Kings", conference="WEST", division="Pacific"),
    "SAS": TeamBase(id="SAS", full_name="San Antonio Spurs", conference="WEST", division="Southwest"),
    "TOR": TeamBase(id="TOR", full_name="Toronto Raptors", conference="EAST", division="Atlantic"),
    "UTA": TeamBase(id="UTA", full_name="Utah Jazz", conference="WEST", division="Northwest"),
    "WAS": TeamBase(id="WAS", full_name="Washington Wizards", conference="EAST", division="Southeast"),
}


@router.get("", response_model=list[TeamBase])
async def list_teams() -> list[TeamBase]:
    """List all NBA teams."""
    return list(NBA_TEAMS.values())


@router.get("/{team_id}", response_model=TeamBase)
async def get_team(team_id: str) -> TeamBase:
    """Get team info by abbreviation."""
    team = NBA_TEAMS.get(team_id.upper())
    if not team:
        raise HTTPException(status_code=404, detail=f"Team {team_id} not found")
    return team


@router.get("/{team_id}/ratings")
async def get_team_ratings(team_id: str) -> dict:
    """Get current ratings for a team (live from NBA API)."""
    team_id = team_id.upper()
    if team_id not in NBA_TEAMS:
        raise HTTPException(status_code=404, detail=f"Team {team_id} not found")

    # Fetch live ratings (cached in pipeline)
    warnings: list[str] = []
    ratings = await _fetch_team_ratings(warnings)
    team_data = ratings.get(team_id)

    if team_data:
        return {
            "team_id": team_id,
            "full_name": NBA_TEAMS[team_id].full_name,
            "current_ratings": {
                "ortg": team_data["ortg"],
                "drtg": team_data["drtg"],
                "nrtg": team_data["nrtg"],
                "pace": team_data.get("pace", 100.0),
                "source": "nba_api (live)",
            },
        }
    else:
        return {
            "team_id": team_id,
            "full_name": NBA_TEAMS[team_id].full_name,
            "current_ratings": {
                "ortg": 112.0,
                "drtg": 110.0,
                "nrtg": 2.0,
                "pace": 100.0,
                "source": "fallback (NBA API unavailable)",
            },
            "warnings": warnings,
        }
