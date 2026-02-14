"""Contract tests for API RBAC allow/deny behavior."""

from unittest.mock import AsyncMock

import pytest

from squadpy.api.websocket_control import WebsocketControlService

pytestmark = [pytest.mark.contract, pytest.mark.api_security, pytest.mark.p1]


async def test_rbac_allows_permitted_role_contract() -> None:
    """P1-API-004: role with action permission can execute privileged commands."""
    rcon = AsyncMock()
    rcon.execute = AsyncMock(return_value="ACK")
    service = WebsocketControlService(
        token="control_token",
        rcon=rcon,
        rbac_enabled=True,
        rbac_default_role="observer",
        rbac_role_permissions={
            "observer": ["control.health", "control.status"],
            "moderator": ["rcon.execute"],
            "admin": ["*"],
        },
    )

    response = await service.process_command(
        {"request_id": "rbac-allow", "command": "ListPlayers"},
        token="control_token",
        role="moderator",
    )

    rcon.execute.assert_awaited_once_with("ListPlayers")
    assert response["ok"] is True
    assert response["request_id"] == "rbac-allow"


async def test_rbac_denies_disallowed_role_contract() -> None:
    """P1-API-004: role without action permission is denied for privileged commands."""
    rcon = AsyncMock()
    rcon.execute = AsyncMock(return_value="ACK")
    service = WebsocketControlService(
        token="control_token",
        rcon=rcon,
        rbac_enabled=True,
        rbac_default_role="observer",
        rbac_role_permissions={
            "observer": ["control.health", "control.status"],
            "admin": ["*"],
        },
    )

    response = await service.process_command(
        {"request_id": "rbac-deny", "command": "ListPlayers"},
        token="control_token",
        role="observer",
    )

    rcon.execute.assert_not_awaited()
    assert response["ok"] is False
    assert response["request_id"] == "rbac-deny"
    assert response["code"] == "forbidden"
