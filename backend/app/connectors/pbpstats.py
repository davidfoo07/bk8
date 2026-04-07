"""PBP Stats connector for player on/off splits and lineup data."""

from typing import Any

import httpx
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential

from app.connectors.base import BaseConnector


class PBPStatsConnector(BaseConnector):
    """Connector for PBP Stats API (pbpstats.com)."""

    def __init__(self) -> None:
        super().__init__(
            name="PBP Stats",
            base_url="https://api.pbpstats.com",
            timeout=30.0,
        )

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=httpx.Timeout(self.timeout),
                headers={"User-Agent": "CourtEdge/1.0"},
            )
        return self._client

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True,
    )
    async def fetch(self, endpoint: str, params: dict[str, Any] | None = None) -> Any:
        """Fetch data from PBP Stats API with retry logic."""
        client = await self._get_client()
        try:
            response = await client.get(endpoint, params=params)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"PBP Stats HTTP error: {e.response.status_code} for {endpoint}")
            raise
        except httpx.TimeoutException:
            logger.error(f"PBP Stats timeout for {endpoint}")
            raise
        except Exception as e:
            logger.error(f"PBP Stats unexpected error for {endpoint}: {e}")
            raise

    async def health_check(self) -> bool:
        """Check if PBP Stats API is reachable."""
        try:
            await self.fetch("/get-teams", params={"Season": "2025-26", "SeasonType": "Regular Season"})
            return True
        except Exception:
            return False

    async def get_player_on_off(
        self,
        team_id: str,
        season: str = "2025-26",
        season_type: str = "Regular Season",
    ) -> list[dict[str, Any]]:
        """
        Fetch player on/off splits for a team.
        Returns team ORtg/DRtg with each player on court vs off court.
        """
        params = {
            "TeamId": team_id,
            "Season": season,
            "SeasonType": season_type,
        }
        try:
            data = await self.fetch("/get-totals/stat", params=params)
            return data.get("multi_row_table_data", [])
        except Exception as e:
            logger.error(f"Failed to get on/off for team {team_id}: {e}")
            return []

    async def get_team_totals(
        self,
        season: str = "2025-26",
        season_type: str = "Regular Season",
    ) -> list[dict[str, Any]]:
        """Fetch team-level totals (ORtg, DRtg, Pace, etc.)."""
        params = {
            "Season": season,
            "SeasonType": season_type,
        }
        try:
            data = await self.fetch("/get-totals/stat", params=params)
            return data.get("single_row_table_data", [])
        except Exception as e:
            logger.error(f"Failed to get team totals: {e}")
            return []

    async def get_lineup_stats(
        self,
        team_id: str,
        season: str = "2025-26",
        lineup_size: int = 5,
    ) -> list[dict[str, Any]]:
        """
        Fetch N-man lineup combination stats.
        Used for multi-player absence adjustments.
        """
        params = {
            "TeamId": team_id,
            "Season": season,
            "SeasonType": "Regular Season",
            "Type": f"{lineup_size}Man",
        }
        try:
            data = await self.fetch("/get-totals/stat", params=params)
            return data.get("multi_row_table_data", [])
        except Exception as e:
            logger.error(f"Failed to get lineup stats for {team_id}: {e}")
            return []
