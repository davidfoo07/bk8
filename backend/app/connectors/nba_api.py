"""NBA API connector for team/player stats, schedule, and injuries."""

from __future__ import annotations

import time
from datetime import date, datetime
from typing import Any

import httpx
from loguru import logger
from tenacity import retry, retry_if_not_exception_type, stop_after_attempt, wait_exponential

from app.config import current_season
from app.connectors import disk_cache
from app.connectors.base import BaseConnector

# Season stats change at most daily → keep them on disk this long (seconds).
DISK_CACHE_TTL: dict[str, int] = {
    "/teamestimatedmetrics": 6 * 3600,
    "/leaguedashteamstats": 6 * 3600,
    "/playerestimatedmetrics": 12 * 3600,
    "/commonteamroster": 12 * 3600,
    "/leaguestandingsv3": 3 * 3600,
    "/teamgamelog": 6 * 3600,
}

# After a 403 (IP block), stop calling stats.nba.com for this long.
BLOCK_PAUSE_SECONDS = 15 * 60
_blocked_until = 0.0

# Endpoints served from a stale disk copy since the last reset (see pipeline).
stale_endpoints: set[str] = set()


class NBABlockedError(Exception):
    """stats.nba.com refused us (403) or calls are paused after one."""


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

    async def fetch(self, endpoint: str, params: dict[str, Any] | None = None) -> Any:
        """Fetch from stats.nba.com through the on-disk cache.

        Season stats (anything in DISK_CACHE_TTL) are served from disk while
        fresh, so normal use costs ~one request per endpoint per day.  If the
        API fails — or is paused after a 403 block — the last saved copy is
        served at any age (recorded in ``stale_endpoints``).  Live endpoints
        (scoreboard, box score) are never cached.
        """
        ttl = DISK_CACHE_TTL.get(endpoint)
        path = disk_cache.cache_path("nba", endpoint, params) if ttl else None
        if path is not None:
            fresh = disk_cache.read(path, ttl)
            if fresh is not None:
                return fresh

        try:
            if _blocked_until > time.monotonic():
                raise NBABlockedError(f"stats.nba.com paused after 403 ({endpoint})")
            data = await self._fetch_remote(endpoint, params)
        except Exception:
            stale = disk_cache.read(path, None) if path is not None else None
            if stale is None:
                raise
            age = disk_cache.age_hours(path)
            logger.warning(f"NBA API unavailable — serving cached {endpoint} ({age:.0f}h old)")
            stale_endpoints.add(endpoint)
            return stale

        if path is not None:
            disk_cache.write(path, data)
        return data

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_not_exception_type(NBABlockedError),
        reraise=True,
    )
    async def _fetch_remote(self, endpoint: str, params: dict[str, Any] | None = None) -> Any:
        """Fetch data from NBA Stats API with retry logic (no retry once blocked)."""
        global _blocked_until
        client = await self._get_client()
        try:
            response = await client.get(endpoint, params=params)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"NBA API HTTP error: {e.response.status_code} for {endpoint}")
            if e.response.status_code == 403:
                # Akamai block: retrying only prolongs it.  Pause all calls.
                _blocked_until = time.monotonic() + BLOCK_PAUSE_SECONDS
                raise NBABlockedError(f"stats.nba.com returned 403 for {endpoint}") from e
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

    async def get_team_ratings(self, season: str | None = None) -> list[dict[str, Any]]:
        """Fetch team offensive/defensive ratings for the season.

        Priority order (fastest-to-slowest, most reliable first):
          1. teamestimatedmetrics — lightweight, rarely fails
          2. leaguedashteamstats Advanced — returns real ORtg/DRtg but often 500s
          3. leaguedashteamstats Base — PTS-based fallback
        """
        # Try teamestimatedmetrics first (most reliable, ~200ms)
        try:
            params = {"LeagueID": "00", "Season": season or current_season(), "SeasonType": "Regular Season"}
            data = await self.fetch("/teamestimatedmetrics", params=params)
            result_set = data.get("resultSets") or data.get("resultSet")
            if isinstance(result_set, list):
                result_set = result_set[0]
            if result_set:
                headers = result_set["headers"]
                rows = result_set["rowSet"]
                result = [dict(zip(headers, row)) for row in rows]
                logger.info(f"✅ Got team ratings via teamestimatedmetrics ({len(result)} teams)")
                return result
        except Exception as e:
            logger.warning(f"teamestimatedmetrics failed: {e}")

        # Fallback: leaguedashteamstats (often returns 500, slow retries)
        for measure_type in ("Advanced", "Base"):
            try:
                params = {
                    "LeagueID": "00", "Season": season or current_season(),
                    "SeasonType": "Regular Season",
                    "PerMode": "PerGame", "MeasureType": measure_type,
                }
                data = await self.fetch("/leaguedashteamstats", params=params)
                headers = data["resultSets"][0]["headers"]
                rows = data["resultSets"][0]["rowSet"]
                result = [dict(zip(headers, row)) for row in rows]
                logger.info(f"Got team ratings via leaguedashteamstats MeasureType={measure_type}")
                return result
            except Exception as e:
                logger.warning(f"leaguedashteamstats MeasureType={measure_type} failed: {e}")
                continue

        return []

    async def get_player_estimated_metrics(self, season: str | None = None) -> list[dict[str, Any]]:
        """Fetch per-player estimated metrics (E_NET_RATING, E_USG_PCT, MIN, etc).

        Returns list of dicts with keys: PLAYER_ID, PLAYER_NAME, GP, MIN,
        E_OFF_RATING, E_DEF_RATING, E_NET_RATING, E_USG_PCT, E_PACE, etc.
        """
        try:
            params = {"LeagueID": "00", "Season": season or current_season(), "SeasonType": "Regular Season"}
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

    async def get_team_roster(
        self, team_id: int, season: str | None = None,
    ) -> list[dict[str, Any]]:
        """Fetch a team's roster (commonteamroster) for the season.

        Returns list of dicts with keys: TeamID, PLAYER, PLAYER_ID, POSITION,
        HOW_ACQUIRED, SUPPLEMENTAL_STATUS, etc.  Raises on HTTP/timeout errors
        (after fetch's retries) so callers can fall back.
        """
        params = {"LeagueID": "00", "Season": season or current_season(), "TeamID": team_id}
        data = await self.fetch("/commonteamroster", params=params)
        for result_set in data.get("resultSets") or []:
            if result_set.get("name") == "CommonTeamRoster":
                headers = result_set["headers"]
                return [dict(zip(headers, row, strict=False)) for row in result_set["rowSet"]]
        return []

    async def get_todays_games(self, game_date: date | None = None) -> list[dict[str, Any]]:
        if game_date is None:
            game_date = date.today()
        params = {"GameDate": game_date.strftime("%Y-%m-%d"), "LeagueID": "00"}
        data = await self.fetch("/scoreboardv3", params=params)
        return data.get("scoreboard", {}).get("games", [])

    async def get_live_boxscore(self, nba_game_id: str) -> dict[str, Any]:
        """Fetch live box score for a game in progress.

        Uses boxscoretraditionalv3 which returns per-player stats during live games:
        minutes, points, rebounds, assists, steals, blocks, turnovers, fouls,
        +/-, FG%, 3P%, FT%.

        Args:
            nba_game_id: The real NBA 10-digit game ID (e.g. "0022501161"),
                         NOT our synthesized "2026-04-09_MEM_DEN" format.
        """
        params = {
            "GameID": nba_game_id,
            "StartPeriod": 0,
            "EndPeriod": 0,
            "StartRange": 0,
            "EndRange": 0,
            "RangeType": 0,
        }
        data = await self.fetch("/boxscoretraditionalv3", params=params)
        return data

    async def get_standings(self, season: str | None = None) -> list[dict[str, Any]]:
        params = {
            "LeagueID": "00", "Season": season or current_season(), "SeasonType": "Regular Season",
        }
        data = await self.fetch("/leaguestandingsv3", params=params)
        headers = data["resultSets"][0]["headers"]
        rows = data["resultSets"][0]["rowSet"]
        return [dict(zip(headers, row)) for row in rows]

    async def get_team_schedule(
        self, team_id: str, season: str | None = None
    ) -> list[dict[str, Any]]:
        params = {"LeagueID": "00", "Season": season or current_season(), "TeamID": team_id}
        data = await self.fetch("/teamgamelog", params=params)
        headers = data["resultSets"][0]["headers"]
        rows = data["resultSets"][0]["rowSet"]
        return [dict(zip(headers, row)) for row in rows]
