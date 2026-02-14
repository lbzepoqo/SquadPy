"""Contract tests for authenticated REST control handlers."""

from unittest.mock import AsyncMock

import pytest

from squadpy.api.websocket_control import WebsocketControlService

pytestmark = [pytest.mark.contract, pytest.mark.api_security, pytest.mark.p0]


async def test_rest_command_endpoint_dispatch_contract() -> None:
    """P0-API-002: authenticated command endpoint dispatches to RCON."""
    rcon = AsyncMock()
    rcon.execute = AsyncMock(return_value="ACK")
    service = WebsocketControlService(
        token="control_token",
        rcon=rcon,
    )

    response = await service.process_command(
        {"request_id": "rest-1", "command": "ListPlayers"},
        token="control_token",
    )

    rcon.execute.assert_awaited_once_with("ListPlayers")
    assert response["ok"] is True
    assert response["request_id"] == "rest-1"
    assert response["result"]["response"] == "ACK"


async def test_rest_auth_rejection_contract() -> None:
    """P0-API-002: unauthorized status endpoint calls are rejected."""
    service = WebsocketControlService(
        token="control_token",
    )
    response = await service.process_status(token="wrong_token")
    assert response["ok"] is False
    assert response["code"] == "unauthorized"
