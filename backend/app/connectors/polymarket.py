"""Polymarket Gamma API connector — event-based NBA market lookup."""

from __future__ import annotations

import asyncio
import json
from datetime import date
from typing import Any

import httpx
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential

from app.connectors.base import BaseConnector

# Uppercase abbreviation → lowercase slug token used by Polymarket.
TEAM_SLUG_MAP: dict[str, str] = {
    "ATL": "atl", "BOS": "bos", "BKN": "bkn", "CHA": "cha", "CHI": "chi",
    "CLE": "cle", "DAL": "dal", "DEN": "den", "DET": "det", "GSW": "gsw",
    "HOU": "hou", "IND": "ind", "LAC": "lac", "LAL": "lal", "MEM": "mem",
    "MIA": "mia", "MIL": "mil", "MIN": "min", "NOP": "nop", "NYK": "nyk",
    "OKC": "okc", "ORL": "orl", "PHI": "phi", "PHX": "phx", "POR": "por",
    "SAC": "sac", "SAS": "sas", "TOR": "tor", "UTA": "uta", "WAS": "was",
}


class PolymarketConnector(BaseConnector):
    """Connector for Polymarket Gamma API using the /events endpoint."""

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
            await self.fetch("/events", params={"slug": "nba", "limit": "1"})
            return True
        except Exception:
            return False

    async def get_game_event(
        self,
        away_abbr: str,
        home_abbr: str,
        game_date: date,
    ) -> dict[str, Any] | None:
        """Fetch a single NBA game event by its slug.

        Slug format: nba-{away_slug}-{home_slug}-{YYYY-MM-DD}
        Returns the first matching event dict (with its ``markets`` list),
        or ``None`` if not found.
        """
        away_slug = TEAM_SLUG_MAP.get(away_abbr, away_abbr.lower())
        home_slug = TEAM_SLUG_MAP.get(home_abbr, home_abbr.lower())
        slug = f"nba-{away_slug}-{home_slug}-{game_date.strftime('%Y-%m-%d')}"

        try:
            data = await self.fetch("/events", params={"slug": slug})
            if data and isinstance(data, list) and len(data) > 0:
                event = data[0]
                n_markets = len(event.get("markets", []))
                logger.info(
                    f"Polymarket event found: {slug} — {n_markets} markets"
                )
                return event
            logger.debug(f"No Polymarket event for slug: {slug}")
            return None
        except Exception as e:
            logger.warning(f"Failed to fetch Polymarket event {slug}: {e}")
            return None

    async def get_games_for_date(
        self,
        games: list[tuple[str, str]],
        game_date: date,
    ) -> dict[str, dict[str, Any] | None]:
        """Fetch events for multiple games in parallel.

        Args:
            games: List of (away_abbr, home_abbr) tuples.
            game_date: The date of the games.

        Returns:
            Dict keyed by ``"{away_abbr}@{home_abbr}"`` → event dict or None.
        """
        async def _fetch_one(away: str, home: str) -> tuple[str, dict[str, Any] | None]:
            key = f"{away}@{home}"
            event = await self.get_game_event(away, home, game_date)
            return key, event

        tasks = [_fetch_one(away, home) for away, home in games]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        events: dict[str, dict[str, Any] | None] = {}
        for result in results:
            if isinstance(result, Exception):
                logger.error(f"Polymarket parallel fetch error: {result}")
                continue
            key, event = result
            events[key] = event
        return events

    @staticmethod
    def parse_market_prices(market: dict[str, Any]) -> dict[str, float]:
        """Parse outcome prices from a Polymarket market response.

        Handles both JSON-string and list formats for outcomes/outcomePrices.
        Returns ``{outcome_label: float_price}``.
        """
        outcomes = market.get("outcomes", "")
        outcome_prices = market.get("outcomePrices", "")

        if isinstance(outcome_prices, str):
            try:
                outcome_prices = json.loads(outcome_prices)
            except (json.JSONDecodeError, TypeError):
                outcome_prices = []

        if isinstance(outcomes, str):
            try:
                outcomes = json.loads(outcomes)
            except (json.JSONDecodeError, TypeError):
                outcomes = []

        prices: dict[str, float] = {}
        for outcome, price in zip(outcomes, outcome_prices):
            try:
                prices[str(outcome)] = float(price)
            except (ValueError, TypeError):
                continue
        return prices
