"""Injury feed connector — ESPN API primary, NBA CDN fallback."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

import httpx
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential

from app.connectors.base import BaseConnector

# ESPN team name → NBA 3-letter abbreviation
ESPN_TEAM_TO_ABBR: dict[str, str] = {
    "Atlanta Hawks": "ATL", "Boston Celtics": "BOS", "Brooklyn Nets": "BKN",
    "Charlotte Hornets": "CHA", "Chicago Bulls": "CHI", "Cleveland Cavaliers": "CLE",
    "Dallas Mavericks": "DAL", "Denver Nuggets": "DEN", "Detroit Pistons": "DET",
    "Golden State Warriors": "GSW", "Houston Rockets": "HOU", "Indiana Pacers": "IND",
    "LA Clippers": "LAC", "Los Angeles Clippers": "LAC",
    "Los Angeles Lakers": "LAL", "Memphis Grizzlies": "MEM",
    "Miami Heat": "MIA", "Milwaukee Bucks": "MIL", "Minnesota Timberwolves": "MIN",
    "New Orleans Pelicans": "NOP", "New York Knicks": "NYK",
    "Oklahoma City Thunder": "OKC", "Orlando Magic": "ORL",
    "Philadelphia 76ers": "PHI", "Phoenix Suns": "PHX",
    "Portland Trail Blazers": "POR", "Sacramento Kings": "SAC",
    "San Antonio Spurs": "SAS", "Toronto Raptors": "TOR",
    "Utah Jazz": "UTA", "Washington Wizards": "WAS",
}


# ESPN uses slightly different abbreviations for some teams
ESPN_ABBR_FIX: dict[str, str] = {
    "GS": "GSW", "NO": "NOP", "SA": "SAS", "UTAH": "UTA", "WSH": "WAS",
    "NY": "NYK", "BK": "BKN", "PHO": "PHX",
}


class InjuryFeedConnector(BaseConnector):
    """Connector for NBA injury reports via ESPN API."""

    def __init__(self) -> None:
        super().__init__(
            name="Injury Feed",
            base_url="https://site.api.espn.com",
            timeout=15.0,
        )

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(self.timeout),
                headers={"User-Agent": "CourtEdge/1.0"},
            )
        return self._client

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=5),
        reraise=True,
    )
    async def fetch(self, url: str, params: dict[str, Any] | None = None) -> Any:
        """Fetch data with retry logic."""
        client = await self._get_client()
        try:
            response = await client.get(url, params=params)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"Injury feed HTTP error: {e.response.status_code} for {url}")
            raise
        except httpx.TimeoutException:
            logger.error(f"Injury feed timeout for {url}")
            raise
        except Exception as e:
            logger.error(f"Injury feed unexpected error for {url}: {e}")
            raise

    async def health_check(self) -> bool:
        try:
            await self.fetch(
                "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/injuries"
            )
            return True
        except Exception:
            return False

    async def get_injury_report(self, game_date: date | None = None) -> list[dict[str, Any]]:
        """Fetch current injury report. ESPN primary, NBA CDN fallback."""
        # Primary: ESPN injury API
        try:
            data = await self.fetch(
                "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/injuries"
            )
            injuries = self._parse_espn_injuries(data)
            if injuries:
                logger.info(
                    f"✅ Fetched {len(injuries)} injuries from ESPN "
                    f"({len(set(i['team'] for i in injuries))} teams)"
                )
                return injuries
        except Exception as e:
            logger.warning(f"ESPN injury fetch failed: {e}")

        # Fallback: NBA CDN
        try:
            data = await self.fetch(
                "https://cdn.nba.com/static/json/liveData/odds/odds_todaysGames.json"
            )
            injuries = self._parse_cdn_injuries(data)
            logger.info(f"Fetched {len(injuries)} injuries from NBA CDN (fallback)")
            return injuries
        except Exception as e:
            logger.warning(f"NBA CDN injury fetch also failed: {e}")

        return []

    def _parse_espn_injuries(self, data: dict[str, Any]) -> list[dict[str, Any]]:
        """Parse ESPN injury API response.

        Structure: {injuries: [{team: {}, injuries: [{athlete: {team: {abbreviation}}, status, ...}]}]}
        Note: The top-level team object is often empty; the real team info
        is nested inside each athlete object.
        """
        injuries: list[dict[str, Any]] = []
        try:
            for team_entry in data.get("injuries", []):
                # Top-level team (sometimes populated, sometimes empty)
                top_team = team_entry.get("team", {})
                top_team_abbr = top_team.get("abbreviation", "")
                if not top_team_abbr:
                    top_team_name = top_team.get("displayName", "")
                    top_team_abbr = ESPN_TEAM_TO_ABBR.get(top_team_name, "")

                for inj in team_entry.get("injuries", []):
                    # Player info — team is nested inside athlete
                    athlete = inj.get("athlete", {})
                    player_name = athlete.get("displayName", "Unknown")
                    player_id = str(athlete.get("id", ""))

                    # Get team from athlete object (most reliable source)
                    athlete_team = athlete.get("team", {})
                    raw_abbr = athlete_team.get("abbreviation", "") or top_team_abbr
                    # Normalize ESPN abbreviation differences
                    team_abbr = ESPN_ABBR_FIX.get(raw_abbr, raw_abbr)
                    if not team_abbr:
                        athlete_team_name = athlete_team.get("displayName", "")
                        team_abbr = ESPN_TEAM_TO_ABBR.get(athlete_team_name, "")

                    # Status: "Out", "Day-To-Day", "Questionable", etc.
                    espn_status = inj.get("status", "Unknown")

                    # Map ESPN status to our status codes
                    status = self._map_espn_status(espn_status)

                    # Injury details
                    details = inj.get("details", {})
                    reason = ""
                    if isinstance(details, dict):
                        detail = details.get("detail", "")
                        injury_type = details.get("type", "")
                        side = details.get("side", "")
                        parts = [p for p in [side, detail, injury_type] if p]
                        reason = " — ".join(parts) if parts else espn_status
                    elif isinstance(details, str):
                        reason = details

                    injuries.append({
                        "player_name": player_name,
                        "player_id": player_id,
                        "team": team_abbr,
                        "status": status,
                        "reason": reason or espn_status,
                        "source": "ESPN",
                        "last_updated": datetime.now().isoformat(),
                    })
        except Exception as e:
            logger.error(f"Error parsing ESPN injuries: {e}")
        return injuries

    @staticmethod
    def _map_espn_status(espn_status: str) -> str:
        """Map ESPN injury status to our internal codes."""
        s = espn_status.lower().strip()
        if s == "out":
            return "OUT"
        elif s in ("day-to-day", "questionable"):
            return "QUESTIONABLE"
        elif s == "doubtful":
            return "DOUBTFUL"
        elif s == "probable":
            return "PROBABLE"
        return "QUESTIONABLE"  # default for unknown

    def _parse_cdn_injuries(self, data: dict[str, Any]) -> list[dict[str, Any]]:
        """Parse injury data from NBA CDN endpoint (fallback)."""
        injuries: list[dict[str, Any]] = []
        try:
            games = data.get("games", [])
            for game in games:
                for team_key in ["homeTeam", "awayTeam"]:
                    team = game.get(team_key, {})
                    team_abbr = team.get("teamTricode", "")
                    for player in team.get("injuries", []):
                        injuries.append({
                            "player_name": player.get("name", ""),
                            "player_id": str(player.get("personId", "")),
                            "team": team_abbr,
                            "status": player.get("status", "OUT"),
                            "reason": player.get("comment", ""),
                            "source": "NBA CDN",
                            "last_updated": datetime.now().isoformat(),
                        })
        except Exception as e:
            logger.error(f"Error parsing CDN injuries: {e}")
        return injuries
