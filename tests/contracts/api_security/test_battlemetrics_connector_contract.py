"""Contract tests for BattleMetrics connector behavior."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from unittest.mock import patch

import pytest

from squadpy.connectors import BattleMetricsConnector

pytestmark = [pytest.mark.contract, pytest.mark.api_security, pytest.mark.p1]


@dataclass(slots=True)
class FakeResponse:
    status: int
    payload: dict[str, Any]

    async def __aenter__(self) -> "FakeResponse":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    async def json(self) -> dict[str, Any]:
        return self.payload

    def raise_for_status(self) -> None:
        if self.status >= 400:
            raise RuntimeError("unexpected HTTP error")


class FakeSession:
    def __init__(self, response: FakeResponse):
        self._response = response
        self.last_url = ""
        self.closed = False

    def get(self, url: str) -> FakeResponse:
        self.last_url = url
        return self._response

    async def close(self) -> None:
        self.closed = True


async def test_battlemetrics_connector_player_lookup_contract() -> None:
    """P1-CONN-002: connector sends token auth and maps BattleMetrics player payload."""
    base_url = "https://battlemetrics.contract"
    fake_session = FakeSession(
        FakeResponse(
            status=200,
            payload={
                "data": {
                    "id": "bm_101",
                    "attributes": {"name": "Contract Player"},
                }
            },
        )
    )
    connector = BattleMetricsConnector(api_token="contract_token", base_url=base_url)

    with patch("squadpy.connectors.battlemetrics.aiohttp.ClientSession", return_value=fake_session) as mock_session:
        await connector.start()
        player = await connector.lookup_player("bm_101")
        await connector.stop()

    assert player is not None
    assert player.player_id == "bm_101"
    assert player.name == "Contract Player"
    assert fake_session.last_url == f"{base_url}/players/bm_101"
    assert fake_session.closed is True

    call_headers = mock_session.call_args.kwargs["headers"]
    assert call_headers["Authorization"] == "Bearer contract_token"

