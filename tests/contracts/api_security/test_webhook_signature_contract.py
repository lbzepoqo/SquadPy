"""Contract tests for signed webhook policy."""

import hashlib
import hmac
import json
from unittest.mock import AsyncMock

import pytest

from squadpy.api.websocket_control import WebsocketControlService

pytestmark = [pytest.mark.contract, pytest.mark.api_security, pytest.mark.p1]


def _sign(secret: str, timestamp: str, raw_body: str) -> str:
    payload = f"{timestamp}.{raw_body}".encode("utf-8")
    digest = hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


async def test_webhook_valid_signature_contract() -> None:
    """P1-API-005: valid webhook signatures are accepted and dispatched."""
    rcon = AsyncMock()
    rcon.execute = AsyncMock(return_value="ACK")
    service = WebsocketControlService(
        token="control_token",
        rcon=rcon,
        webhook_signing_enabled=True,
        webhook_signing_secret="webhook_secret",
    )
    payload = {"request_id": "wh-contract-allow", "command": "ListPlayers"}
    raw_body = json.dumps(payload, separators=(",", ":"))
    timestamp = "1700000000"
    service._epoch_seconds = lambda: 1700000000  # type: ignore[assignment]

    response = await service.process_webhook_command(
        payload,
        raw_body=raw_body,
        signature=_sign("webhook_secret", timestamp, raw_body),
        timestamp=timestamp,
    )

    rcon.execute.assert_awaited_once_with("ListPlayers")
    assert response["ok"] is True
    assert response["request_id"] == "wh-contract-allow"


async def test_webhook_invalid_signature_contract() -> None:
    """P1-API-005: invalid webhook signatures are rejected."""
    rcon = AsyncMock()
    rcon.execute = AsyncMock(return_value="ACK")
    service = WebsocketControlService(
        token="control_token",
        rcon=rcon,
        webhook_signing_enabled=True,
        webhook_signing_secret="webhook_secret",
    )
    payload = {"request_id": "wh-contract-deny", "command": "ListPlayers"}
    raw_body = json.dumps(payload, separators=(",", ":"))
    timestamp = "1700000000"
    service._epoch_seconds = lambda: 1700000000  # type: ignore[assignment]

    response = await service.process_webhook_command(
        payload,
        raw_body=raw_body,
        signature="sha256=invalid",
        timestamp=timestamp,
    )

    rcon.execute.assert_not_awaited()
    assert response["ok"] is False
    assert response["request_id"] == "wh-contract-deny"
    assert response["code"] == "invalid_signature"
