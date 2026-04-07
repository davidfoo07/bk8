"""Base connector interface for all external data sources."""

from abc import ABC, abstractmethod
from typing import Any

from loguru import logger


class BaseConnector(ABC):
    """Abstract base class for data connectors."""

    def __init__(self, name: str, base_url: str, timeout: float = 30.0) -> None:
        self.name = name
        self.base_url = base_url
        self.timeout = timeout
        self._client = None

    @abstractmethod
    async def fetch(self, endpoint: str, params: dict[str, Any] | None = None) -> Any:
        """Fetch data from the external API."""
        ...

    @abstractmethod
    async def health_check(self) -> bool:
        """Check if the external API is reachable."""
        ...

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client:
            await self._client.aclose()
            logger.info(f"Closed {self.name} connector")
