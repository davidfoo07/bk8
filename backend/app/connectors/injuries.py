"""Injury feed connector combining NBA official and backup sources."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

import httpx
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential

from app.connectors.base import BaseConnector


class InjuryFeedConnector(BaseConnector):
    """Connector for NBA injury reports."""

    def __init__(self) -> None:
        super().__init__(
            name="Injury Feed",
            base_url="https://cdn.nba.com",
            timeout=15.0,
        )

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(self.timeout),
                headers={
                    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
                    "Referer": "https://www.nba.com/",
                },
            )
        return self._client

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True,
    )
    async def fetch(self, endpoint: str, params: dict[str, Any] | None = None) -> Any:
        """Fetch injury data with retry logic."""
        client = await self._get_client()
        url = f"{self.base_url}{endpoint}" if not endpoint.startswith("http") else endpoint
        try:
            response = await client.get(url, params=params)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"Injury feed HTTP error: {e.response.status_code}")
            raise
        except httpx.TimeoutException:
            logger.error("Injury feed timeout")
            raise
        except Exception as e:
            logger.error(f"Injury feed unexpected error: {e}")
            raise

    async def health_check(self) -> bool:
        """Check if injury feed is reachable."""
        try:
            await self.fetch("/static/json/liveData/odds/odds_todaysGames.json")
            return True
        except Exception:
            return False

    async def get_injury_report(self, game_date: date | None = None) -> list[dict[str, Any]]:
        """
        Fetch the current injury report.
        Tries NBA official API first, falls back to scraping if needed.
        """
        injuries: list[dict[str, Any]] = []
        
        # Try NBA official injury endpoint
        try:
            client = await self._get_client()
            response = await client.get(
                "https://stats.nba.com/stats/playerindex",
                params={"LeagueID": "00", "Season": "2025-26"},
                headers={
                    "Host": "stats.nba.com",
                    "Referer": "https://www.nba.com/",
                    "x-nba-stats-origin": "stats",
                    "x-nba-stats-token": "true",
                },
            )
            if response.status_code == 200:
                data = response.json()
                logger.info("Fetched injury data from NBA official API")
                return self._parse_nba_injuries(data)
        except Exception as e:
            logger.warning(f"NBA official injury fetch failed: {e}")

        # Fallback: try the CDN endpoint
        try:
            data = await self.fetch("/static/json/liveData/odds/odds_todaysGames.json")
            logger.info("Fetched injury data from NBA CDN")
            return self._parse_cdn_injuries(data)
        except Exception as e:
            logger.warning(f"CDN injury fetch failed: {e}")

        return injuries

    def _parse_nba_injuries(self, data: dict[str, Any]) -> list[dict[str, Any]]:
        """Parse injury data from NBA official API response."""
        injuries: list[dict[str, Any]] = []
        try:
            result_sets = data.get("resultSets", [])
            if result_sets:
                headers = result_sets[0].get("headers", [])
                rows = result_sets[0].get("rowSet", [])
                for row in rows:
                    player_data = dict(zip(headers, row))
                    if player_data.get("ROSTERSTATUS") == "Inactive":
                        injuries.append({
                            "player_name": f"{player_data.get('PLAYER_FIRST_NAME', '')} {player_data.get('PLAYER_LAST_NAME', '')}".strip(),
                            "player_id": str(player_data.get("PERSON_ID", "")),
                            "team": player_data.get("TEAM_ABBREVIATION", ""),
                            "status": "OUT",
                            "reason": "Inactive",
                            "source": "NBA Official",
                            "last_updated": datetime.now().isoformat(),
                        })
        except Exception as e:
            logger.error(f"Error parsing NBA injuries: {e}")
        return injuries

    def _parse_cdn_injuries(self, data: dict[str, Any]) -> list[dict[str, Any]]:
        """Parse injury data from NBA CDN endpoint."""
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
