"""NBA API connector for team/player stats, schedule, and injuries."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

import httpx
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential

from app.connectors.base import BaseConnector


class NBAApiConnector(BaseConnector):
    """Connector for stats.nba.com API."""

    HEADERS = {
        "Host": "stats.nba.com",
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.5",
        "Referer": "https://www.nba.com/",
        "x-nba-stats-origin": "stats",
        "x-nba-stats-token": "true",
        "Origin": "https://www.nba.com",
    }

    def __init__(self) -> None:
        super().__init__(
            name="NBA API",
            base_url="https://stats.nba.com/stats",
            timeout=30.0,
        )

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                headers=self.HEADERS,
                timeout=httpx.Timeout(self.timeout),
            )
        return self._client

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True,
    )
    async def fetch(self, endpoint: str, params: dict[str, Any] | None = None) -> Any:
        """Fetch data from NBA Stats API with retry logic."""
        client = await self._get_client()
        try:
            response = await client.get(endpoint, params=params)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"NBA API HTTP error: {e.response.status_code} for {endpoint}")
            raise
        except httpx.TimeoutException:
            logger.error(f"NBA API timeout for {endpoint}")
            raise
        except Exception as e:
            logger.error(f"NBA API unexpected error for {endpoint}: {e}")
            raise

    async def health_check(self) -> bool:
        try:
            await self.fetch("/scoreboardv3", params={"GameDate": "2026-04-07", "LeagueID": "00"})
            return True
        except Exception:
            return False

    async def get_team_ratings(self, season: str = "2025-26") -> list[dict[str, Any]]:
        """Fetch team offensive/defensive ratings for the season."""
        for measure_type in ("Advanced", "Base"):
            try:
                params = {
                    "LeagueID": "00", "Season": season,
                    "SeasonType": "Regular Season",
                    "PerMode": "PerGame", "MeasureType": measure_type,
                }
                data = await self.fetch("/leaguedashteamstats", params=params)
                headers = data["resultSets"][0]["headers"]
                rows = data["resultSets"][0]["rowSet"]
                result = [dict(zip(headers, row)) for row in rows]
                logger.info(f"Got team ratings via MeasureType={measure_type}")
                return result
            except Exception as e:
                logger.warning(f"leaguedashteamstats MeasureType={measure_type} failed: {e}")
                continue

        # Fallback: teamestimatedmetrics
        try:
            params = {"LeagueID": "00", "Season": season, "SeasonType": "Regular Season"}
            data = await self.fetch("/teamestimatedmetrics", params=params)
            result_set = data.get("resultSets") or data.get("resultSet")
            if isinstance(result_set, list):
                result_set = result_set[0]
            if result_set:
                headers = result_set["headers"]
                rows = result_set["rowSet"]
                result = [dict(zip(headers, row)) for row in rows]
                logger.info("Got team ratings via teamestimatedmetrics fallback")
                return result
        except Exception as e:
            logger.warning(f"teamestimatedmetrics also failed: {e}")

        return []

    async def get_player_estimated_metrics(self, season: str = "2025-26") -> list[dict[str, Any]]:
        """Fetch per-player estimated metrics (E_NET_RATING, E_USG_PCT, MIN, etc).

        Returns list of dicts with keys: PLAYER_ID, PLAYER_NAME, GP, MIN,
        E_OFF_RATING, E_DEF_RATING, E_NET_RATING, E_USG_PCT, E_PACE, etc.
        """
        try:
            params = {"LeagueID": "00", "Season": season, "SeasonType": "Regular Season"}
            data = await self.fetch("/playerestimatedmetrics", params=params)
            # Uses "resultSet" (singular) like teamestimatedmetrics
            result_set = data.get("resultSet") or data.get("resultSets")
            if isinstance(result_set, list):
                result_set = result_set[0]
            if result_set:
                headers = result_set["headers"]
                rows = result_set["rowSet"]
                result = [dict(zip(headers, row)) for row in rows]
                logger.info(f"✅ Fetched estimated metrics for {len(result)} players")
                return result
        except Exception as e:
            logger.warning(f"playerestimatedmetrics failed: {e}")

        return []

    async def get_todays_games(self, game_date: date | None = None) -> list[dict[str, Any]]:
        if game_date is None:
            game_date = date.today()
        params = {"GameDate": game_date.strftime("%Y-%m-%d"), "LeagueID": "00"}
        data = await self.fetch("/scoreboardv3", params=params)
        return data.get("scoreboard", {}).get("games", [])

    async def get_standings(self, season: str = "2025-26") -> list[dict[str, Any]]:
        params = {
            "LeagueID": "00", "Season": season, "SeasonType": "Regular Season",
        }
        data = await self.fetch("/leaguestandingsv3", params=params)
        headers = data["resultSets"][0]["headers"]
        rows = data["resultSets"][0]["rowSet"]
        return [dict(zip(headers, row)) for row in rows]

    async def get_team_schedule(
        self, team_id: str, season: str = "2025-26"
    ) -> list[dict[str, Any]]:
        params = {"LeagueID": "00", "Season": season, "TeamID": team_id}
        data = await self.fetch("/teamgamelog", params=params)
        headers = data["resultSets"][0]["headers"]
        rows = data["resultSets"][0]["rowSet"]
        return [dict(zip(headers, row)) for row in rows]
