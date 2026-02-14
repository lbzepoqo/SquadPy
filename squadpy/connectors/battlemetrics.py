"""BattleMetrics moderation connector."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import aiohttp

from squadpy.connectors.base import Connector

DEFAULT_BATTLEMETRICS_API_URL = "https://api.battlemetrics.com"


@dataclass(slots=True, frozen=True)
class BattleMetricsPlayer:
    player_id: str
    name: str
    attributes: dict[str, Any]


class BattleMetricsConnector(Connector):
    """External moderation/community API connector for BattleMetrics."""

    def __init__(
        self,
        *,
        api_token: str,
        base_url: str = DEFAULT_BATTLEMETRICS_API_URL,
        timeout_seconds: float = 8.0,
    ):
        super().__init__(name="battlemetrics")
        self._api_token = str(api_token).strip()
        self._base_url = str(base_url).strip().rstrip("/") or DEFAULT_BATTLEMETRICS_API_URL
        self._timeout_seconds = timeout_seconds if timeout_seconds > 0 else 8.0
        self._session: aiohttp.ClientSession | None = None

    async def _start(self) -> None:
        headers = {"Accept": "application/json"}
        if self._api_token:
            headers["Authorization"] = f"Bearer {self._api_token}"
        timeout = aiohttp.ClientTimeout(total=self._timeout_seconds)
        self._session = aiohttp.ClientSession(timeout=timeout, headers=headers)

    async def _stop(self) -> None:
        if self._session:
            await self._session.close()
            self._session = None

    async def lookup_player(self, player_id: str) -> BattleMetricsPlayer | None:
        """Fetch a BattleMetrics player record by player id."""
        target = str(player_id).strip()
        if not target:
            raise ValueError("player_id must not be empty")
        session = self._require_session()
        url = f"{self._base_url}/players/{target}"
        async with session.get(url) as response:
            if response.status == 404:
                return None
            response.raise_for_status()
            payload = await response.json()

        data = payload.get("data")
        if not isinstance(data, dict):
            raise RuntimeError("Invalid BattleMetrics response payload")

        raw_attributes = data.get("attributes", {})
        attributes = raw_attributes if isinstance(raw_attributes, dict) else {}
        return BattleMetricsPlayer(
            player_id=str(data.get("id", target)),
            name=str(attributes.get("name", "")),
            attributes=attributes,
        )

    def _require_session(self) -> aiohttp.ClientSession:
        if self._session is None:
            raise RuntimeError("BattleMetricsConnector is not started")
        return self._session

