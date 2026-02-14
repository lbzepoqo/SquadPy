"""Integration-style tests for BattleMetrics connector with mocked HTTP API."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from unittest.mock import patch

import pytest

from squadpy.connectors import BattleMetricsConnector, BattleMetricsPlayer


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
            raise RuntimeError(f"HTTP error ({self.status})")


class FakeSession:
    def __init__(self, responses: dict[str, FakeResponse]):
        self._responses = responses
        self.urls: list[str] = []
        self.closed = False

    def get(self, url: str) -> FakeResponse:
        self.urls.append(url)
        response = self._responses.get(url)
        if response is None:
            return FakeResponse(status=404, payload={"errors": [{"status": "404"}]})
        return response

    async def close(self) -> None:
        self.closed = True


class TestBattleMetricsConnector:
    async def test_lookup_player_returns_normalized_player(self) -> None:
        base_url = "https://battlemetrics.test"
        target_url = f"{base_url}/players/12345"
        fake_session = FakeSession(
            responses={
                target_url: FakeResponse(
                    status=200,
                    payload={
                        "data": {
                            "id": "12345",
                            "type": "player",
                            "attributes": {
                                "name": "Test Player",
                                "positiveMatch": True,
                            },
                        }
                    },
                )
            }
        )
        connector = BattleMetricsConnector(api_token="secret_token", base_url=base_url)

        with patch("squadpy.connectors.battlemetrics.aiohttp.ClientSession", return_value=fake_session) as mock_session:
            await connector.start()
            player = await connector.lookup_player("12345")
            await connector.stop()

        assert isinstance(player, BattleMetricsPlayer)
        assert player.player_id == "12345"
        assert player.name == "Test Player"
        assert player.attributes["positiveMatch"] is True
        assert fake_session.urls == [target_url]
        assert fake_session.closed is True

        call_headers = mock_session.call_args.kwargs["headers"]
        assert call_headers["Authorization"] == "Bearer secret_token"
        assert call_headers["Accept"] == "application/json"

    async def test_lookup_player_returns_none_for_not_found(self) -> None:
        base_url = "https://battlemetrics.test"
        target_url = f"{base_url}/players/missing"
        fake_session = FakeSession(
            responses={target_url: FakeResponse(status=404, payload={"errors": [{"status": "404"}]})}
        )
        connector = BattleMetricsConnector(api_token="secret_token", base_url=base_url)

        with patch("squadpy.connectors.battlemetrics.aiohttp.ClientSession", return_value=fake_session):
            await connector.start()
            player = await connector.lookup_player("missing")
            await connector.stop()

        assert player is None

    async def test_lookup_player_requires_started_connector(self) -> None:
        connector = BattleMetricsConnector(api_token="secret_token", base_url="https://battlemetrics.test")
        with pytest.raises(RuntimeError, match="not started"):
            await connector.lookup_player("12345")

    async def test_lookup_player_rejects_invalid_payload(self) -> None:
        base_url = "https://battlemetrics.test"
        target_url = f"{base_url}/players/broken"
        fake_session = FakeSession(
            responses={target_url: FakeResponse(status=200, payload={"data": []})}
        )
        connector = BattleMetricsConnector(api_token="secret_token", base_url=base_url)

        with patch("squadpy.connectors.battlemetrics.aiohttp.ClientSession", return_value=fake_session):
            await connector.start()
            with pytest.raises(RuntimeError, match="Invalid BattleMetrics response payload"):
                await connector.lookup_player("broken")
            await connector.stop()
