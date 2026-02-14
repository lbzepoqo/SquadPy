"""Contract tests for privileged action audit records."""

from unittest.mock import AsyncMock

import pytest

from squadpy.api.websocket_control import WebsocketControlService

pytestmark = [pytest.mark.contract, pytest.mark.api_security, pytest.mark.p0]


async def test_audit_record_contract_success() -> None:
    """P0-API-003: successful privileged command writes actor/origin/target/outcome."""
    rcon = AsyncMock()
    rcon.execute = AsyncMock(return_value="ACK")
    service = WebsocketControlService(
        token="control_token",
        rcon=rcon,
    )

    await service.process_command(
        {"command": "ListPlayers"},
        token="control_token",
        origin="rest",
        actor="admin_1",
    )

    records = service.recent_audit_records()
    assert records
    latest = records[-1]
    assert latest["actor"] == "admin_1"
    assert latest["origin"] == "rest"
    assert latest["target"] == "ListPlayers"
    assert latest["outcome"] == "success"


async def test_audit_record_contract_rejected() -> None:
    """P0-API-003: rejected privileged command still writes audit record."""
    rcon = AsyncMock()
    rcon.execute = AsyncMock(return_value="ACK")
    service = WebsocketControlService(
        token="control_token",
        rcon=rcon,
    )

    await service.process_command(
        {"command": "ListPlayers"},
        token="wrong_token",
        origin="websocket",
        actor="intruder",
    )

    records = service.recent_audit_records()
    assert records
    latest = records[-1]
    assert latest["actor"] == "intruder"
    assert latest["origin"] == "websocket"
    assert latest["target"] == "rcon.execute"
    assert latest["outcome"] == "rejected"
