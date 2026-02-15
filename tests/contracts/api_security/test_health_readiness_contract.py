"""Contract tests for dependency-aware health/readiness probes."""

from unittest.mock import AsyncMock

import pytest

from squadpy.api.websocket_control import WebsocketControlService

pytestmark = [pytest.mark.contract, pytest.mark.api_security]


async def test_readiness_reports_unavailable_when_required_dependency_is_unhealthy() -> None:
    """P2-BEYOND-005: readiness returns unavailable when required dependency is down."""
    server = AsyncMock()
    server.running = True
    rcon = AsyncMock()
    rcon.connected = False
    service = WebsocketControlService(
        token="control_token",
        server=server,
        rcon=rcon,
    )

    response = await service.process_readiness(token="control_token")

    assert response["ok"] is False
    assert response["code"] == "unavailable"
    assert response["result"]["status"] == "not_ready"
    assert response["result"]["dependencies"]["rcon"]["required"] is True
    assert response["result"]["dependencies"]["rcon"]["healthy"] is False


async def test_health_includes_dependency_states() -> None:
    """P2-BEYOND-005: health returns dependency status details for operators."""
    server = AsyncMock()
    server.running = True
    rcon = AsyncMock()
    rcon.connected = True
    service = WebsocketControlService(
        token="control_token",
        server=server,
        rcon=rcon,
    )

    response = await service.process_health(token="control_token")

    assert response["ok"] is True
    assert response["result"]["status"] == "ok"
    assert response["result"]["dependencies"]["server"]["healthy"] is True
    assert response["result"]["dependencies"]["rcon"]["healthy"] is True
