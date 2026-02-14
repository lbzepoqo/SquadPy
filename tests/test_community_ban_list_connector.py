"""Integration-style tests for Community Ban List connector with mocked HTTP API."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from unittest.mock import patch

import pytest

from squadpy.connectors import CommunityBanListConnector, CommunityBanListPlayer


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


class TestCommunityBanListConnector:
    async def test_lookup_player_returns_normalized_player(self) -> None:
        base_url = "https://cbl.test/api"
        target_url = f"{base_url}/players/76561198000000000"
        fake_session = FakeSession(
            responses={
                target_url: FakeResponse(
                    status=200,
                    payload={
                        "data": {
                            "id": "76561198000000000",
                            "attributes": {
                                "reputation": "trusted",
                                "risk": "low",
                                "bans": [
                                    {
                                        "reason": "Cheating",
                                        "source": "CBL",
                                        "active": True,
                                        "issued_at": "2025-01-01T00:00:00Z",
                                    },
                                    {
                                        "reason": "Old ban",
                                        "source": "CBL",
                                        "active": False,
                                    },
                                ],
                            },
                        }
                    },
                )
            }
        )
        connector = CommunityBanListConnector(api_token="cbl_token", base_url=base_url)

        with patch("squadpy.connectors.community_ban_list.aiohttp.ClientSession", return_value=fake_session) as mock_session:
            await connector.start()
            player = await connector.lookup_player("76561198000000000")
            await connector.stop()

        assert isinstance(player, CommunityBanListPlayer)
        assert player.steam_id == "76561198000000000"
        assert player.reputation == "trusted"
        assert player.risk_level == "low"
        assert len(player.active_bans) == 1
        assert player.active_bans[0].reason == "Cheating"
        assert player.active_bans[0].source == "CBL"
        assert fake_session.urls == [target_url]
        assert fake_session.closed is True

        call_headers = mock_session.call_args.kwargs["headers"]
        assert call_headers["Authorization"] == "Bearer cbl_token"
        assert call_headers["Accept"] == "application/json"

    async def test_lookup_player_returns_none_for_not_found(self) -> None:
        base_url = "https://cbl.test/api"
        target_url = f"{base_url}/players/unknown"
        fake_session = FakeSession(
            responses={target_url: FakeResponse(status=404, payload={"errors": [{"status": "404"}]})}
        )
        connector = CommunityBanListConnector(api_token="cbl_token", base_url=base_url)

        with patch("squadpy.connectors.community_ban_list.aiohttp.ClientSession", return_value=fake_session):
            await connector.start()
            player = await connector.lookup_player("unknown")
            await connector.stop()

        assert player is None

    async def test_lookup_player_requires_started_connector(self) -> None:
        connector = CommunityBanListConnector(api_token="cbl_token", base_url="https://cbl.test/api")
        with pytest.raises(RuntimeError, match="not started"):
            await connector.lookup_player("76561198000000000")

    async def test_lookup_player_rejects_invalid_payload(self) -> None:
        base_url = "https://cbl.test/api"
        target_url = f"{base_url}/players/broken"
        fake_session = FakeSession(
            responses={target_url: FakeResponse(status=200, payload={"data": []})}
        )
        connector = CommunityBanListConnector(api_token="cbl_token", base_url=base_url)

        with patch("squadpy.connectors.community_ban_list.aiohttp.ClientSession", return_value=fake_session):
            await connector.start()
            with pytest.raises(RuntimeError, match="Invalid Community Ban List response payload"):
                await connector.lookup_player("broken")
            await connector.stop()

    async def test_lookup_player_rejects_empty_steam_id(self) -> None:
        connector = CommunityBanListConnector(api_token="cbl_token", base_url="https://cbl.test/api")
        with patch("squadpy.connectors.community_ban_list.aiohttp.ClientSession", return_value=FakeSession({})):
            await connector.start()
            with pytest.raises(ValueError, match="must not be empty"):
                await connector.lookup_player("  ")
            await connector.stop()

