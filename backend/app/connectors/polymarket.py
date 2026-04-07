"""Polymarket Gamma API connector for NBA market prices."""

from datetime import date
from typing import Any

import httpx
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential

from app.connectors.base import BaseConnector


# Team abbreviation to full name mapping for slug matching
TEAM_SLUG_MAP: dict[str, str] = {
    "ATL": "atl", "BOS": "bos", "BKN": "bkn", "CHA": "cha", "CHI": "chi",
    "CLE": "cle", "DAL": "dal", "DEN": "den", "DET": "det", "GSW": "gsw",
    "HOU": "hou", "IND": "ind", "LAC": "lac", "LAL": "lal", "MEM": "mem",
    "MIA": "mia", "MIL": "mil", "MIN": "min", "NOP": "nop", "NYK": "nyk",
    "OKC": "okc", "ORL": "orl", "PHI": "phi", "PHX": "phx", "POR": "por",
    "SAC": "sac", "SAS": "sas", "TOR": "tor", "UTA": "uta", "WAS": "was",
}

NBA_SERIES_ID = "10345"


class PolymarketConnector(BaseConnector):
    """Connector for Polymarket Gamma API."""

    def __init__(self) -> None:
        super().__init__(
            name="Polymarket",
            base_url="https://gamma-api.polymarket.com",
            timeout=15.0,
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
        wait=wait_exponential(multiplier=1, min=1, max=5),
        reraise=True,
    )
    async def fetch(self, endpoint: str, params: dict[str, Any] | None = None) -> Any:
        """Fetch data from Polymarket Gamma API with retry logic."""
        client = await self._get_client()
        try:
            response = await client.get(endpoint, params=params)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"Polymarket HTTP error: {e.response.status_code} for {endpoint}")
            raise
        except httpx.TimeoutException:
            logger.error(f"Polymarket timeout for {endpoint}")
            raise
        except Exception as e:
            logger.error(f"Polymarket unexpected error for {endpoint}: {e}")
            raise

    async def health_check(self) -> bool:
        """Check if Polymarket API is reachable."""
        try:
            await self.fetch("/markets", params={"limit": "1"})
            return True
        except Exception:
            return False

    async def get_nba_markets(self, active: bool = True) -> list[dict[str, Any]]:
        """Fetch all active NBA markets."""
        params: dict[str, str] = {}
        if active:
            params["active"] = "true"
        params["tag"] = "nba"
        
        all_markets: list[dict[str, Any]] = []
        offset = 0
        limit = 100
        
        while True:
            params["limit"] = str(limit)
            params["offset"] = str(offset)
            data = await self.fetch("/markets", params=params)
            
            if not data:
                break
            
            all_markets.extend(data)
            
            if len(data) < limit:
                break
            offset += limit
        
        return all_markets

    async def get_market_by_slug(self, slug: str) -> dict[str, Any] | None:
        """Fetch a specific market by its slug."""
        try:
            data = await self.fetch("/markets", params={"slug": slug})
            if data and len(data) > 0:
                return data[0]
            return None
        except Exception as e:
            logger.warning(f"Failed to fetch market {slug}: {e}")
            return None

    async def get_game_markets(
        self,
        away_team: str,
        home_team: str,
        game_date: date,
    ) -> list[dict[str, Any]]:
        """
        Fetch all markets for a specific NBA game.
        Slug format: nba-{away}-{home}-{YYYY-MM-DD}
        """
        away_slug = TEAM_SLUG_MAP.get(away_team, away_team.lower())
        home_slug = TEAM_SLUG_MAP.get(home_team, home_team.lower())
        base_slug = f"nba-{away_slug}-{home_slug}-{game_date.strftime('%Y-%m-%d')}"
        
        markets: list[dict[str, Any]] = []
        
        # Try to get the game markets by searching
        try:
            all_nba = await self.get_nba_markets()
            for market in all_nba:
                slug = market.get("slug", "")
                if base_slug in slug or (
                    away_slug in slug and home_slug in slug and game_date.strftime("%Y-%m-%d") in slug
                ):
                    markets.append(market)
        except Exception as e:
            logger.warning(f"Failed to fetch game markets for {base_slug}: {e}")
        
        return markets

    @staticmethod
    def parse_market_prices(market: dict[str, Any]) -> dict[str, float]:
        """Parse outcome prices from a Polymarket market response."""
        outcomes = market.get("outcomes", "")
        outcome_prices = market.get("outcomePrices", "")
        
        if isinstance(outcome_prices, str):
            try:
                import json
                outcome_prices = json.loads(outcome_prices)
            except (json.JSONDecodeError, TypeError):
                outcome_prices = []
        
        if isinstance(outcomes, str):
            try:
                import json
                outcomes = json.loads(outcomes)
            except (json.JSONDecodeError, TypeError):
                outcomes = []
        
        prices: dict[str, float] = {}
        for outcome, price in zip(outcomes, outcome_prices):
            prices[outcome] = float(price)
        
        return prices
