"""Contract tests for websocket control authentication and dispatch."""

from unittest.mock import AsyncMock

import pytest

from squadpy.api.websocket_control import WebsocketControlService

pytestmark = [pytest.mark.contract, pytest.mark.api_security, pytest.mark.p0]


async def test_authenticated_command_dispatch_contract() -> None:
    """P0-API-001: valid token dispatches privileged command to RCON."""
    rcon = AsyncMock()
    rcon.execute = AsyncMock(return_value="ACK")
    service = WebsocketControlService(
        token="control_token",
        rcon=rcon,
    )

    response = await service.process_payload(
        {"request_id": "req-1", "action": "rcon.execute", "command": "ListPlayers"},
        token="control_token",
    )

    rcon.execute.assert_awaited_once_with("ListPlayers")
    assert response["ok"] is True
    assert response["request_id"] == "req-1"
    assert response["result"]["response"] == "ACK"


async def test_auth_rejection_contract() -> None:
    """P0-API-001: invalid token is rejected and command is not dispatched."""
    rcon = AsyncMock()
    rcon.execute = AsyncMock(return_value="ACK")
    service = WebsocketControlService(
        token="control_token",
        rcon=rcon,
    )

    response = await service.process_payload(
        {"request_id": "req-2", "action": "rcon.execute", "command": "ListPlayers"},
        token="wrong_token",
    )

    rcon.execute.assert_not_awaited()
    assert response["ok"] is False
    assert response["request_id"] == "req-2"
    assert response["code"] == "unauthorized"
