"""Contract tests for Community Ban List connector behavior."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from unittest.mock import patch

import pytest

from squadpy.connectors import CommunityBanListConnector

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


async def test_community_ban_list_connector_lookup_contract() -> None:
    """P1-CONN-003: connector sends token auth and maps active-ban metadata."""
    base_url = "https://cbl.contract/api"
    fake_session = FakeSession(
        FakeResponse(
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
                            }
                        ],
                    },
                }
            },
        )
    )
    connector = CommunityBanListConnector(api_token="contract_token", base_url=base_url)

    with patch("squadpy.connectors.community_ban_list.aiohttp.ClientSession", return_value=fake_session) as mock_session:
        await connector.start()
        player = await connector.lookup_player("76561198000000000")
        await connector.stop()

    assert player is not None
    assert player.steam_id == "76561198000000000"
    assert player.reputation == "trusted"
    assert len(player.active_bans) == 1
    assert player.active_bans[0].reason == "Cheating"
    assert fake_session.last_url == f"{base_url}/players/76561198000000000"
    assert fake_session.closed is True

    call_headers = mock_session.call_args.kwargs["headers"]
    assert call_headers["Authorization"] == "Bearer contract_token"

